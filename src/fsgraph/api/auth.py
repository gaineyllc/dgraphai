"""
Auth API — OIDC config management, token exchange info.
No actual token validation here — that's middleware in auth/oidc.py.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.fsgraph.db.models import OIDCConfig, Tenant
from src.fsgraph.db.session import get_db
from src.fsgraph.auth.oidc import get_auth_context, AuthContext
from src.fsgraph.rbac.engine import require_permissions

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
async def get_me(auth: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    """Return the authenticated user's context."""
    return {
        "user_id":    str(auth.user_id),
        "tenant_id":  str(auth.tenant_id),
        "email":      auth.email,
        "roles":      auth.roles,
        "permissions": sorted(auth.permissions),
    }


class OIDCConfigRequest(BaseModel):
    provider_name: str
    issuer_url:    str
    client_id:     str
    client_secret: str
    scopes:        list[str] = ["openid", "email", "profile"]
    claim_mapping: dict[str, str] = {}


@router.get("/oidc")
async def list_oidc_configs(
    auth: AuthContext = Depends(require_permissions("admin:*")),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List OIDC providers for this tenant (admin only)."""
    result = await db.execute(
        select(OIDCConfig).where(OIDCConfig.tenant_id == auth.tenant_id)
    )
    configs = result.scalars().all()
    return [
        {
            "id":            str(c.id),
            "provider_name": c.provider_name,
            "issuer_url":    c.issuer_url,
            "client_id":     c.client_id,
            # Never return client_secret
            "scopes":        c.scopes,
            "claim_mapping": c.claim_mapping,
            "is_default":    c.is_default,
            "is_active":     c.is_active,
        }
        for c in configs
    ]


@router.post("/oidc")
async def add_oidc_config(
    req: OIDCConfigRequest,
    auth: AuthContext = Depends(require_permissions("admin:*")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Configure a new OIDC identity provider for this tenant (admin only)."""
    # Encrypt client_secret before storing
    encrypted_secret = _encrypt_secret(req.client_secret)

    config = OIDCConfig(
        tenant_id     = auth.tenant_id,
        provider_name = req.provider_name,
        issuer_url    = req.issuer_url.rstrip("/"),
        client_id     = req.client_id,
        client_secret = encrypted_secret,
        scopes        = req.scopes,
        claim_mapping = req.claim_mapping,
    )
    db.add(config)
    await db.flush()

    return {"id": str(config.id), "status": "created", "provider": req.provider_name}


def _encrypt_secret(secret: str) -> str:
    """
    Encrypt a client secret using the application encryption key.
    Uses AES-256-GCM via the cryptography library.
    In production, replace with Vault or cloud KMS.
    """
    import base64
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key_b64 = os.getenv("ENCRYPTION_KEY", "")
    if not key_b64:
        # Development: store plaintext with warning
        return f"PLAINTEXT:{secret}"

    key   = base64.b64decode(key_b64)
    nonce = os.urandom(12)
    ct    = AESGCM(key).encrypt(nonce, secret.encode(), None)
    return base64.b64encode(nonce + ct).decode()
