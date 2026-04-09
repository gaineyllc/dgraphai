"""
OIDC/JWT authentication.

Supports any compliant OIDC provider (Okta, Azure AD, Google, Keycloak, Auth0).
Each tenant configures their own IdP — tenant_id is extracted from the JWT
audience or a custom claim, then the correct OIDC config is loaded.

Flow:
  1. Frontend redirects user to IdP authorization endpoint
  2. IdP returns JWT access token
  3. Frontend sends token in Authorization: Bearer header
  4. This middleware validates the token and extracts the user context

Token validation:
  - Fetches JWKS from IdP discovery endpoint
  - Verifies signature, expiry, audience
  - Extracts email, display_name, tenant_id via claim mapping
  - Creates/updates User record on first login
  - Injects AuthContext into request state
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.fsgraph.db.models import OIDCConfig, Tenant, User
from src.fsgraph.db.session import get_db

_bearer = HTTPBearer(auto_error=False)

# JWKS cache: {issuer_url: {keys: [...], fetched_at: float}}
_jwks_cache: dict[str, dict[str, Any]] = {}
_JWKS_TTL = 3600  # 1 hour


@dataclass
class AuthContext:
    """Injected into every authenticated request."""
    user_id:   UUID
    tenant_id: UUID
    email:     str
    roles:     list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)


async def _get_jwks(issuer_url: str) -> list[dict]:
    """Fetch and cache JWKS from the OIDC discovery endpoint."""
    cached = _jwks_cache.get(issuer_url)
    if cached and time.time() - cached["fetched_at"] < _JWKS_TTL:
        return cached["keys"]

    discovery_url = issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10) as client:
        disc = await client.get(discovery_url)
        disc.raise_for_status()
        jwks_uri = disc.json()["jwks_uri"]
        keys_resp = await client.get(jwks_uri)
        keys_resp.raise_for_status()
        keys = keys_resp.json()["keys"]

    _jwks_cache[issuer_url] = {"keys": keys, "fetched_at": time.time()}
    return keys


async def _validate_token(
    token: str, oidc_config: OIDCConfig
) -> dict[str, Any]:
    """Validate a JWT token against the tenant's OIDC config."""
    keys = await _get_jwks(oidc_config.issuer_url)

    # Try each key until one validates
    last_error: Exception | None = None
    for key_data in keys:
        try:
            public_key = jwk.construct(key_data)
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256", "ES256", "RS384", "RS512"],
                audience=oidc_config.client_id,
                options={"verify_at_hash": False},
            )
            return claims
        except JWTError as e:
            last_error = e
            continue

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Token validation failed: {last_error}",
    )


def _extract_claim(claims: dict, mapping: dict, field: str, default: str = "") -> str:
    """Extract a claim using the tenant's claim mapping configuration."""
    claim_key = mapping.get(field, field)
    return str(claims.get(claim_key, default))


async def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """
    FastAPI dependency — validates the Bearer token and returns AuthContext.
    Raises 401 if token is missing or invalid.
    Raises 403 if tenant is not active.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Decode without verification first to extract issuer and determine tenant
    try:
        unverified = jwt.get_unverified_claims(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    issuer = unverified.get("iss", "")
    if not issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing issuer claim")

    # Find matching OIDC config by issuer URL
    result = await db.execute(
        select(OIDCConfig)
        .join(Tenant)
        .where(
            OIDCConfig.issuer_url == issuer,
            OIDCConfig.is_active == True,  # noqa: E712
            Tenant.is_active == True,       # noqa: E712
        )
        .limit(1)
    )
    oidc_config = result.scalar_one_or_none()
    if not oidc_config:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active tenant configured for this identity provider",
        )

    # Validate the full token
    claims = await _validate_token(token, oidc_config)

    # Extract user attributes via claim mapping
    mapping = oidc_config.claim_mapping or {}
    email        = _extract_claim(claims, mapping, "email")
    display_name = _extract_claim(claims, mapping, "name", email)
    external_id  = claims.get("sub", "")

    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email claim missing")

    # Upsert user record
    result = await db.execute(
        select(User).where(
            User.tenant_id  == oidc_config.tenant_id,
            User.external_id == external_id,
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        # First login — create user
        user = User(
            tenant_id    = oidc_config.tenant_id,
            email        = email,
            display_name = display_name,
            external_id  = external_id,
            idp_provider = oidc_config.provider_name,
        )
        db.add(user)
        await db.flush()
    else:
        from datetime import datetime, timezone
        user.last_login = datetime.now(timezone.utc)
        if display_name:
            user.display_name = display_name

    # Load roles and permissions
    from src.fsgraph.rbac.engine import load_user_permissions
    roles, permissions = await load_user_permissions(user.id, oidc_config.tenant_id, db)

    return AuthContext(
        user_id   = user.id,
        tenant_id = oidc_config.tenant_id,
        email     = email,
        roles     = roles,
        permissions = permissions,
    )


# Convenience dependency aliases
RequireAuth = Depends(get_auth_context)
