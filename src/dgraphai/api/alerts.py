"""Alert rules and fired alert management API."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.dgraphai.db.alert_models import Alert, AlertRule
from src.dgraphai.alerts.engine import BUILTIN_RULES
from src.dgraphai.db.session import get_db
from src.dgraphai.auth.oidc import get_auth_context, AuthContext

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class CreateRuleRequest(BaseModel):
    name:             str
    description:      str = ""
    severity:         str = "medium"
    cypher:           str
    cypher_params:    dict = {}
    threshold_count:  int = 1
    eval_schedule:    str = "0 * * * *"
    cooldown_minutes: int = 60
    channels:         list[dict] = []
    message_template: str = ""


@router.get("/rules")
async def list_rules(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    result = await db.execute(select(AlertRule).where(AlertRule.tenant_id == auth.tenant_id))
    return [_rule_dict(r) for r in result.scalars().all()]


@router.post("/rules")
async def create_rule(
    req:  CreateRuleRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rule = AlertRule(
        tenant_id        = auth.tenant_id,
        name             = req.name,
        description      = req.description,
        severity         = req.severity,
        cypher           = req.cypher,
        cypher_params    = req.cypher_params,
        threshold_count  = req.threshold_count,
        eval_schedule    = req.eval_schedule,
        cooldown_minutes = req.cooldown_minutes,
        channels         = req.channels,
        message_template = req.message_template,
    )
    db.add(rule)
    await db.flush()
    return _rule_dict(rule)


@router.post("/rules/install-defaults")
async def install_default_rules(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Install the built-in alert rule templates for this tenant."""
    if "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Admin required")
    installed = []
    for defn in BUILTIN_RULES:
        exists = await db.execute(
            select(AlertRule).where(
                AlertRule.tenant_id == auth.tenant_id,
                AlertRule.name == defn["name"],
            )
        )
        if exists.scalar_one_or_none():
            continue
        rule = AlertRule(tenant_id=auth.tenant_id, **defn)
        db.add(rule)
        installed.append(defn["name"])
    await db.flush()
    return {"installed": installed, "count": len(installed)}


@router.get("")
async def list_alerts(
    status:   str | None = None,
    severity: str | None = None,
    auth:     AuthContext = Depends(get_auth_context),
    db:       AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(Alert).where(Alert.tenant_id == auth.tenant_id)
    if status:   stmt = stmt.where(Alert.status   == status)
    if severity: stmt = stmt.where(Alert.severity == severity)
    result = await db.execute(stmt.order_by(Alert.fired_at.desc()).limit(200))
    return [_alert_dict(a) for a in result.scalars().all()]


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    auth:     AuthContext = Depends(get_auth_context),
    db:       AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(Alert).where(Alert.id == uuid.UUID(alert_id), Alert.tenant_id == auth.tenant_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status          = "acknowledged"
    alert.acknowledged_by = auth.user_id
    alert.acknowledged_at = datetime.now(timezone.utc)
    return _alert_dict(alert)


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    auth:     AuthContext = Depends(get_auth_context),
    db:       AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(Alert).where(Alert.id == uuid.UUID(alert_id), Alert.tenant_id == auth.tenant_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status      = "resolved"
    alert.resolved_at = datetime.now(timezone.utc)
    return _alert_dict(alert)


def _rule_dict(r: AlertRule) -> dict:
    return {"id": str(r.id), "name": r.name, "severity": r.severity,
            "is_active": r.is_active, "eval_schedule": r.eval_schedule,
            "last_fired_at": r.last_fired_at.isoformat() if r.last_fired_at else None,
            "channels": r.channels}

def _alert_dict(a: Alert) -> dict:
    return {"id": str(a.id), "title": a.title, "severity": a.severity,
            "status": a.status, "message": a.message, "row_count": a.row_count,
            "fired_at": a.fired_at.isoformat() if a.fired_at else None,
            "context": a.context}
