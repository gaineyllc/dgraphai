"""
Circuit breaker for graph database queries.

Prevents a slow or failing graph DB from taking down the API server.
Uses a simple state machine: CLOSED → OPEN → HALF_OPEN → CLOSED

States:
  CLOSED:    Normal operation. Failures counted.
  OPEN:      DB is considered down. Requests fail immediately.
             Entered after failure_threshold failures within window_secs.
  HALF_OPEN: Testing recovery. One request allowed through.
             Entered after reset_timeout_secs in OPEN state.

Configuration (env vars):
  GRAPH_CB_FAILURE_THRESHOLD  — failures before opening (default: 5)
  GRAPH_CB_WINDOW_SECS        — failure counting window (default: 60)
  GRAPH_CB_RESET_TIMEOUT_SECS — how long to stay OPEN (default: 30)
  GRAPH_CB_QUERY_TIMEOUT_SECS — individual query timeout (default: 30)
"""
from __future__ import annotations
import asyncio
import os
import time
import logging
from enum import Enum
from typing import Any, Callable

log = logging.getLogger("dgraphai.graph.circuit_breaker")

FAILURE_THRESHOLD  = int(os.getenv("GRAPH_CB_FAILURE_THRESHOLD",  "5"))
WINDOW_SECS        = int(os.getenv("GRAPH_CB_WINDOW_SECS",        "60"))
RESET_TIMEOUT_SECS = int(os.getenv("GRAPH_CB_RESET_TIMEOUT_SECS", "30"))
QUERY_TIMEOUT_SECS = int(os.getenv("GRAPH_CB_QUERY_TIMEOUT_SECS", "30"))


class State(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when circuit is open — graph DB considered unavailable."""
    pass


class GraphCircuitBreaker:
    """
    Per-tenant circuit breaker for graph queries.
    Thread-safe via asyncio.Lock.
    """

    def __init__(self):
        self._state      = State.CLOSED
        self._failures:  list[float] = []   # timestamps of recent failures
        self._opened_at: float | None = None
        self._lock       = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == State.OPEN

    async def call(self, fn: Callable, *args, **kwargs) -> Any:
        """
        Execute a graph query through the circuit breaker.
        Raises CircuitBreakerOpen if circuit is open.
        Raises TimeoutError if query exceeds QUERY_TIMEOUT_SECS.
        """
        async with self._lock:
            await self._maybe_transition()

            if self._state == State.OPEN:
                raise CircuitBreakerOpen(
                    f"Graph circuit breaker is OPEN (will retry in "
                    f"{int(RESET_TIMEOUT_SECS - (time.time() - self._opened_at))}s)"
                )

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                fn(*args, **kwargs),
                timeout=QUERY_TIMEOUT_SECS,
            )
            await self._on_success()
            return result
        except asyncio.TimeoutError:
            await self._on_failure()
            raise TimeoutError(f"Graph query timed out after {QUERY_TIMEOUT_SECS}s")
        except CircuitBreakerOpen:
            raise
        except Exception as e:
            await self._on_failure()
            raise

    async def _maybe_transition(self):
        """Check if we should transition from OPEN → HALF_OPEN."""
        if self._state == State.OPEN and self._opened_at:
            elapsed = time.time() - self._opened_at
            if elapsed >= RESET_TIMEOUT_SECS:
                self._state = State.HALF_OPEN
                log.info("Circuit breaker: OPEN → HALF_OPEN (testing recovery)")

    async def _on_success(self):
        async with self._lock:
            if self._state == State.HALF_OPEN:
                self._state    = State.CLOSED
                self._failures = []
                log.info("Circuit breaker: HALF_OPEN → CLOSED (recovery confirmed)")

    async def _on_failure(self):
        async with self._lock:
            now = time.time()
            self._failures = [t for t in self._failures if now - t < WINDOW_SECS]
            self._failures.append(now)

            if self._state == State.HALF_OPEN:
                # Recovery attempt failed — go back to OPEN
                self._state     = State.OPEN
                self._opened_at = now
                log.warning("Circuit breaker: HALF_OPEN → OPEN (recovery failed)")

            elif len(self._failures) >= FAILURE_THRESHOLD:
                self._state     = State.OPEN
                self._opened_at = now
                log.error(
                    f"Circuit breaker: CLOSED → OPEN "
                    f"({len(self._failures)} failures in {WINDOW_SECS}s)"
                )

    def stats(self) -> dict:
        return {
            "state":            self._state,
            "recent_failures":  len(self._failures),
            "failure_threshold":FAILURE_THRESHOLD,
            "opened_at":        self._opened_at,
            "seconds_until_retry": (
                max(0, RESET_TIMEOUT_SECS - (time.time() - self._opened_at))
                if self._opened_at and self._state == State.OPEN else None
            ),
        }


# ── Global registry — one breaker per tenant ──────────────────────────────────

_breakers: dict[str, GraphCircuitBreaker] = {}


def get_breaker(tenant_id: str) -> GraphCircuitBreaker:
    """Get or create a circuit breaker for a tenant."""
    if tenant_id not in _breakers:
        _breakers[tenant_id] = GraphCircuitBreaker()
    return _breakers[tenant_id]


def all_breaker_stats() -> dict[str, dict]:
    """Return circuit breaker stats for all tenants — used by /api/health."""
    return {tid: b.stats() for tid, b in _breakers.items()}
