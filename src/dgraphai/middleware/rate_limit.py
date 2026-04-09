"""
Redis-backed rate limiting middleware.

Replaces the in-process dict-based limiter which:
  - Doesn't work across multiple API replicas
  - Resets on process restart (restart = instant unban)
  - Can't be shared or inspected

Uses a sliding window algorithm in Redis:
  Key: rl:{ip}:{endpoint_path}
  Value: sorted set of request timestamps
  TTL:   window_secs * 2

Limits (configurable via env):
  Auth endpoints:   10 req/min  (signup, login, forgot-password)
  API endpoints:    300 req/min (per IP)
  GraphQL:          60 req/min
  Bulk/export:      5 req/min

Returns 429 with Retry-After header when exceeded.
Adds X-RateLimit-Remaining header on every response.
"""
from __future__ import annotations
import os
import time
import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

log = logging.getLogger("dgraphai.ratelimit")

REDIS_URL = os.getenv("REDIS_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))

# Limits: (max_requests, window_seconds)
LIMITS: dict[str, tuple[int, int]] = {
    "/api/auth/login":          (10,  60),
    "/api/auth/signup":         (5,   60),
    "/api/auth/forgot-password":(5,   60),
    "/api/auth/reset-password": (5,   60),
    "/graphql":                 (60,  60),
    "/api/search":              (30,  60),
    "/api/stream":              (5,   60),
    "DEFAULT":                  (300, 60),
}


class RedisRateLimiter:
    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = await aioredis.from_url(REDIS_URL, decode_responses=False)
            except Exception as e:
                log.warning(f"Redis rate limiter unavailable: {e}")
                self._redis = None
        return self._redis

    async def is_allowed(
        self, ip: str, path: str
    ) -> tuple[bool, int, int]:
        """
        Check if this request is allowed.
        Returns (allowed, remaining, retry_after_secs).
        """
        r = await self._get_redis()
        if r is None:
            # Redis unavailable — fail open (allow request)
            return True, 999, 0

        limit, window = self._get_limit(path)
        key  = f"rl:{ip}:{path}"
        now  = time.time()
        cutoff = now - window

        try:
            pipe = r.pipeline()
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, cutoff)
            # Count current window
            pipe.zcard(key)
            # Add this request
            pipe.zadd(key, {str(now).encode(): now})
            # Set TTL
            pipe.expire(key, window * 2)
            results = await pipe.execute()

            count = results[1]  # count after removing expired, before adding

            if count >= limit:
                # Find oldest entry to compute retry_after
                oldest = await r.zrange(key, 0, 0, withscores=True)
                retry_after = int(window - (now - oldest[0][1])) + 1 if oldest else window
                return False, 0, retry_after

            remaining = limit - count - 1
            return True, max(0, remaining), 0

        except Exception as e:
            log.warning(f"Rate limit Redis error: {e}")
            return True, 999, 0   # fail open

    def _get_limit(self, path: str) -> tuple[int, int]:
        for pattern, limit in LIMITS.items():
            if pattern != "DEFAULT" and path.startswith(pattern):
                return limit
        return LIMITS["DEFAULT"]


_limiter = RedisRateLimiter()


async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    """FastAPI middleware — apply rate limiting to all requests."""
    ip   = request.client.host if request.client else "unknown"
    path = request.url.path

    # Skip health checks and static assets
    if path in ("/api/health", "/metrics") or path.startswith("/assets/"):
        return await call_next(request)

    allowed, remaining, retry_after = await _limiter.is_allowed(ip, path)

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Too many requests. Please slow down.",
                "retry_after": retry_after,
            },
            headers={
                "Retry-After":          str(retry_after),
                "X-RateLimit-Remaining":"0",
                "X-RateLimit-Limit":    str(_limiter._get_limit(path)[0]),
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response
