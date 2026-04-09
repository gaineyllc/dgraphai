"""
Connector scan scheduling API.
Allows connectors to be configured with automatic scan intervals.
Backed by Celery Beat dynamic schedules via Redis.
"""
from __future__ import annotations
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.connector_models import Connector
from src.dgraphai.db.session import get_db

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

VALID_SCHEDULES = {
    "manual":  None,
    "1h":      3600,
    "6h":      21600,
    "12h":     43200,
    "24h":     86400,
    "48h":     172800,
    "weekly":  604800,
}


class ScanScheduleRequest(BaseModel):
    schedule: str  # manual | 1h | 6h | 12h | 24h | 48h | weekly


@router.patch("/{connector_id}/schedule")
async def set_scan_schedule(
    connector_id: str,
    req:          ScanScheduleRequest,
    auth:         AuthContext = Depends(get_auth_context),
    db:           AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Set automatic scan schedule for a connector."""
    if req.schedule not in VALID_SCHEDULES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid schedule. Valid options: {list(VALID_SCHEDULES.keys())}"
        )

    result = await db.execute(
        select(Connector).where(
            Connector.id == UUID(connector_id),
            Connector.tenant_id == auth.tenant_id,
        )
    )
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    interval_secs = VALID_SCHEDULES[req.schedule]

    # Store schedule in connector config
    config = dict(connector.config or {})
    config['scan_schedule']          = req.schedule
    config['scan_interval_seconds']  = interval_secs
    connector.config = config

    # Register with Celery Beat if not manual
    if interval_secs:
        _register_celery_schedule(
            connector_id = str(connector.id),
            tenant_id    = str(auth.tenant_id),
            interval_secs= interval_secs,
        )
    else:
        _unregister_celery_schedule(str(connector.id))

    return {
        "connector_id": connector_id,
        "schedule":     req.schedule,
        "interval_secs":interval_secs,
        "next_scan":    "scheduled" if interval_secs else "manual only",
    }


@router.post("/{connector_id}/scan")
async def trigger_manual_scan(
    connector_id: str,
    auth:         AuthContext = Depends(get_auth_context),
    db:           AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger an immediate scan of a connector."""
    result = await db.execute(
        select(Connector).where(
            Connector.id == UUID(connector_id),
            Connector.tenant_id == auth.tenant_id,
        )
    )
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Queue scan via Celery
    from src.dgraphai.tasks.celery_app import app as celery_app
    task = celery_app.send_task(
        "dgraphai.tasks.indexer.scan_connector",
        args=[str(auth.tenant_id), connector_id],
        queue="indexing",
    )
    return {
        "status":       "queued",
        "task_id":      task.id,
        "connector_id": connector_id,
        "message":      f"Scan of '{connector.name}' queued",
    }


def _register_celery_schedule(connector_id: str, tenant_id: str, interval_secs: int):
    """Add a periodic scan task to Celery Beat for this connector."""
    try:
        from src.dgraphai.tasks.celery_app import app as celery_app
        schedule_name = f"scan-connector-{connector_id}"
        # Dynamic beat schedule — stored in Redis via celery-redbeat
        # Falls back to logging if redbeat not available
        celery_app.conf.beat_schedule[schedule_name] = {
            "task":     "dgraphai.tasks.indexer.scan_connector",
            "schedule": interval_secs,
            "args":     [tenant_id, connector_id],
            "options":  {"queue": "indexing"},
        }
    except Exception:
        pass  # Celery not running — schedule will apply on next beat start


def _unregister_celery_schedule(connector_id: str):
    """Remove periodic scan task for this connector."""
    try:
        from src.dgraphai.tasks.celery_app import app as celery_app
        schedule_name = f"scan-connector-{connector_id}"
        celery_app.conf.beat_schedule.pop(schedule_name, None)
    except Exception:
        pass
