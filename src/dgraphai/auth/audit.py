"""
Audit log middleware + helper.

Every significant action is recorded to the audit_logs table.
Written append-only — the ORM has no update/delete for audit logs.
Forwarded to SIEM via webhook if configured.

Usage:
    from src.dgraphai.auth.audit import audit_log
    await audit_log(db, tenant_id, user_id, "connector.create",
                    resource=f"connector:{cid}", details={"name": "S3"})

FastAPI middleware automatically logs:
  - auth.login / auth.login.failed
  - auth.logout
  - Any 4xx/5xx on sensitive endpoints
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("dgraphai.audit")

# Audit log SIEM webhook (optional)
AUDIT_WEBHOOK_URL = os.getenv("AUDIT_WEBHOOK_URL", "")


async def audit_log(
    db:         AsyncSession,
    tenant_id:  UUID | str,
    user_id:    UUID | str | None,
    action:     str,
    resource:   str | None = None,
    details:    dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    status:     str = "success",
    request:    Request | None = None,
) -> None:
    """Write an immutable audit log entry."""
    from src.dgraphai.db.models import AuditLog

    if request:
        ip_address = ip_address or (request.client.host if request.client else None)
        user_agent = user_agent or request.headers.get("user-agent", "")[:512]

    entry = AuditLog(
        tenant_id  = UUID(str(tenant_id)),
        user_id    = UUID(str(user_id)) if user_id else None,
        action     = action,
        resource   = resource,
        details    = details or {},
        ip_address = ip_address,
        user_agent = user_agent,
        status     = status,
        created_at = datetime.now(timezone.utc),
    )
    db.add(entry)
    # Note: no flush here — caller controls transaction

    # Forward to SIEM webhook asynchronously (best-effort)
    if AUDIT_WEBHOOK_URL:
        import asyncio
        asyncio.create_task(_forward_to_siem({
            "tenant_id":  str(tenant_id),
            "user_id":    str(user_id) if user_id else None,
            "action":     action,
            "resource":   resource,
            "details":    details or {},
            "ip_address": ip_address,
            "status":     status,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
        }))


async def _forward_to_siem(payload: dict) -> None:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(AUDIT_WEBHOOK_URL, json=payload)
    except Exception as e:
        log.debug(f"SIEM forward failed (non-critical): {e}")


# ── Audit log API ──────────────────────────────────────────────────────────────

from fastapi import APIRouter, Depends, Query
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.session import get_db

audit_router = APIRouter(prefix="/api/audit", tags=["audit"])


@audit_router.get("")
async def list_audit_log(
    action:  str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit:   int        = Query(default=50, le=500),
    offset:  int        = Query(default=0,  ge=0),
    auth:    AuthContext = Depends(get_auth_context),
    db:      AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    List audit log entries for this tenant.
    Admin only — returns all actions across all users.
    Analysts — returns only their own actions.
    """
    from sqlalchemy import select, desc
    from src.dgraphai.db.models import AuditLog

    q = select(AuditLog).where(AuditLog.tenant_id == auth.tenant_id)

    # Non-admins see only their own entries
    if "admin:*" not in auth.permissions:
        q = q.where(AuditLog.user_id == auth.user_id)
    elif user_id:
        import uuid as _uuid
        q = q.where(AuditLog.user_id == _uuid.UUID(user_id))

    if action:
        q = q.where(AuditLog.action.contains(action))

    total_q = select(AuditLog).where(AuditLog.tenant_id == auth.tenant_id)
    total_r = await db.execute(total_q)

    q = q.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
    result = await db.execute(q)
    entries = result.scalars().all()

    return {
        "entries": [
            {
                "id":         str(e.id),
                "action":     e.action,
                "resource":   e.resource,
                "details":    e.details,
                "user_id":    str(e.user_id) if e.user_id else None,
                "ip_address": e.ip_address,
                "status":     e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
        "offset": offset,
        "limit":  limit,
    }
