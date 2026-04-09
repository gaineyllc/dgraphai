"""
In-app notification API.
Surfaces alert firings, security findings, and system events
as a feed for the notification center bell icon.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.models import AuditLog
from src.dgraphai.db.session import get_db

router = APIRouter(prefix="/api/alerts", tags=["notifications"])


@router.get("/notifications")
async def list_notifications(
    limit: int = 30,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns recent notifications for the current user.
    Synthesized from:
      - Audit log entries (auth events, security findings)
      - Alert firings (from alerts engine)
      - System events (scan complete, CVE sync, etc.)
    """
    # Pull recent audit log entries as notifications
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == auth.tenant_id,
            AuditLog.created_at >= cutoff,
            AuditLog.action.in_([
                "alert.fired", "connector.scan.failed", "connector.scan.complete",
                "finding.created", "user.provisioned", "user.deprovisioned",
                "gdpr.erasure.complete", "indexing.complete", "indexing.failed",
                "auth.login.failed", "auth.mfa.enrolled",
            ])
        )
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
    )
    entries = result.scalars().all()

    notifications = [_audit_to_notification(e) for e in entries]
    unread = sum(1 for n in notifications if not n.get("read_at"))

    return {
        "notifications": notifications,
        "unread":        unread,
        "total":         len(notifications),
    }


@router.post("/notifications/read")
async def mark_notifications_read(
    body: dict,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """Mark specific notifications as read (by audit log IDs)."""
    ids = body.get("ids", [])
    if ids:
        await db.execute(
            update(AuditLog)
            .where(
                AuditLog.tenant_id == auth.tenant_id,
                AuditLog.id.in_([uuid.UUID(i) for i in ids if i]),
            )
            .values(details={"read": True})  # piggyback on details JSON
        )
    return {"status": "ok"}


@router.post("/notifications/read-all")
async def mark_all_read(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """Mark all notifications as read."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    await db.execute(
        update(AuditLog)
        .where(
            AuditLog.tenant_id == auth.tenant_id,
            AuditLog.created_at >= cutoff,
        )
        .values(details={"read": True})
    )
    return {"status": "ok"}


def _audit_to_notification(entry: AuditLog) -> dict:
    action = entry.action or ""
    details = entry.details or {}
    is_read = details.get("read", False)

    # Map action to severity + title
    severity_map = {
        "alert.fired":              ("high",     "Alert fired"),
        "connector.scan.failed":    ("medium",   "Scan failed"),
        "connector.scan.complete":  ("info",     "Scan complete"),
        "finding.created":          ("high",     "New finding"),
        "auth.login.failed":        ("medium",   "Failed login attempt"),
        "gdpr.erasure.complete":    ("info",     "Data erasure complete"),
        "indexing.failed":          ("medium",   "Indexing failed"),
        "indexing.complete":        ("info",     "Indexing complete"),
        "user.provisioned":         ("info",     "User provisioned"),
        "user.deprovisioned":       ("info",     "User deprovisioned"),
        "auth.mfa.enrolled":        ("info",     "MFA enrolled"),
    }
    severity, title = severity_map.get(action, ("info", action.replace(".", " ").title()))

    # Build a helpful message from details
    message = details.get("message") or details.get("connector_name") or ""
    if not message and action == "auth.login.failed":
        message = f"IP: {entry.ip_address or 'unknown'}"

    # Build a deep-link URL
    link = None
    if "scan" in action or "indexing" in action:
        link = "/indexer"
    elif "alert" in action or "finding" in action:
        link = "/security"
    elif "user" in action:
        link = "/settings"
    elif "erasure" in action:
        link = "/audit"

    return {
        "id":         str(entry.id),
        "action":     action,
        "title":      title,
        "message":    message,
        "severity":   severity,
        "link":       link,
        "read_at":    entry.created_at.isoformat() if is_read else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }
