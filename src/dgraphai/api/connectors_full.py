"""
Full connector management API — CRUD + health + test + scanner routing.
Replaces the stub connectors.py.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.db.connector_models import Connector
from src.dgraphai.db.models import ScannerAgent
from src.dgraphai.db.session import get_db
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.connectors.sdk import list_connectors, get_connector

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


# ── Models ────────────────────────────────────────────────────────────────────

class CreateConnectorRequest(BaseModel):
    name:             str
    description:      str = ""
    connector_type:   str
    config:           dict[str, Any] = {}
    tags:             list[str] = []
    scanner_agent_id: str | None = None   # UUID of scanner agent to proxy through
    routing_mode:     str = "auto"         # direct | agent | auto


class UpdateConnectorRequest(BaseModel):
    name:             str | None = None
    description:      str | None = None
    config:           dict[str, Any] | None = None
    tags:             list[str] | None = None
    scanner_agent_id: str | None = None
    routing_mode:     str | None = None
    is_active:        bool | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/types")
async def list_connector_types(
    auth: AuthContext = Depends(get_auth_context),
) -> list[dict[str, Any]]:
    """List all available connector types with config schemas."""
    return [
        {
            "id":            m.id,
            "name":          m.name,
            "description":   m.description,
            "version":       m.version,
            "author":        m.author,
            "icon_url":      m.icon_url,
            "config_schema": m.config_schema,
            "capabilities":  m.capabilities,
            # Which routing modes make sense for this type
            "routing_modes": _routing_modes_for(m.id),
        }
        for m in list_connectors()
    ]


@router.get("")
async def list_tenant_connectors(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all configured connectors for this tenant with health metrics."""
    result = await db.execute(
        select(Connector).where(Connector.tenant_id == auth.tenant_id)
        .order_by(Connector.created_at.desc())
    )
    connectors = result.scalars().all()

    # Load scanner agent names
    agent_ids = {c.scanner_agent_id for c in connectors if c.scanner_agent_id}
    agents: dict[uuid.UUID, ScannerAgent] = {}
    if agent_ids:
        agent_result = await db.execute(
            select(ScannerAgent).where(ScannerAgent.id.in_(agent_ids))
        )
        agents = {a.id: a for a in agent_result.scalars().all()}

    return [_connector_dict(c, agents.get(c.scanner_agent_id)) for c in connectors]


@router.post("")
async def create_connector(
    req:  CreateConnectorRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new connector."""
    if "mounts:write" not in auth.permissions and "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Permission required: mounts:write")

    # Validate connector type exists
    cls = get_connector(req.connector_type)
    if not cls:
        raise HTTPException(status_code=400, detail=f"Unknown connector type: {req.connector_type!r}")

    # Validate scanner agent belongs to tenant if specified
    agent_uuid = None
    if req.scanner_agent_id:
        agent_uuid = uuid.UUID(req.scanner_agent_id)
        agent_result = await db.execute(
            select(ScannerAgent).where(
                ScannerAgent.id == agent_uuid,
                ScannerAgent.tenant_id == auth.tenant_id,
            )
        )
        if not agent_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Scanner agent not found")

    connector = Connector(
        tenant_id        = auth.tenant_id,
        name             = req.name,
        description      = req.description,
        connector_type   = req.connector_type,
        config           = req.config,  # TODO: encrypt sensitive fields
        tags             = req.tags,
        scanner_agent_id = agent_uuid,
        routing_mode     = req.routing_mode,
        created_by       = auth.user_id,
        last_scan_status = "never",
    )
    db.add(connector)
    await db.flush()
    return _connector_dict(connector, None)


@router.get("/{connector_id}")
async def get_connector_detail(
    connector_id: str,
    auth:         AuthContext = Depends(get_auth_context),
    db:           AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get full connector details including config schema and health history."""
    c = await _get_connector_or_404(connector_id, auth, db)
    agent = None
    if c.scanner_agent_id:
        r = await db.execute(select(ScannerAgent).where(ScannerAgent.id == c.scanner_agent_id))
        agent = r.scalar_one_or_none()

    d = _connector_dict(c, agent)
    # Add the config schema for the UI
    cls = get_connector(c.connector_type)
    if cls:
        d["config_schema"] = cls.manifest.config_schema
    return d


@router.patch("/{connector_id}")
async def update_connector(
    connector_id: str,
    req:          UpdateConnectorRequest,
    auth:         AuthContext = Depends(get_auth_context),
    db:           AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    c = await _get_connector_or_404(connector_id, auth, db)
    for field, value in req.model_dump(exclude_none=True).items():
        if field == "scanner_agent_id" and value:
            setattr(c, field, uuid.UUID(value))
        else:
            setattr(c, field, value)
    c.updated_at = datetime.now(timezone.utc)
    return _connector_dict(c, None)


@router.delete("/{connector_id}")
async def delete_connector(
    connector_id: str,
    auth:         AuthContext = Depends(get_auth_context),
    db:           AsyncSession = Depends(get_db),
) -> dict[str, str]:
    c = await _get_connector_or_404(connector_id, auth, db)
    await db.delete(c)
    return {"status": "deleted"}


@router.post("/{connector_id}/test")
async def test_connector(
    connector_id: str,
    auth:         AuthContext = Depends(get_auth_context),
    db:           AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Test connectivity for a saved connector."""
    c = await _get_connector_or_404(connector_id, auth, db)
    cls = get_connector(c.connector_type)
    if not cls:
        raise HTTPException(status_code=400, detail=f"Unknown type: {c.connector_type}")

    instance = cls(connector_id=str(c.id), config=c.config)
    result   = await instance.test_connection()

    c.last_test_at     = datetime.now(timezone.utc)
    c.last_test_result = result.get("success", False)
    c.last_test_msg    = result.get("message", "")

    return {
        "connector_id": connector_id,
        "success":      result.get("success", False),
        "message":      result.get("message", ""),
        "tested_at":    c.last_test_at.isoformat(),
    }


@router.get("/{connector_id}/agents")
async def available_agents_for_connector(
    connector_id: str,
    auth:         AuthContext = Depends(get_auth_context),
    db:           AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    List scanner agents available to proxy this connector.
    Returns agents that are online, with their routing scores to common regions.
    """
    await _get_connector_or_404(connector_id, auth, db)  # verify access

    result = await db.execute(
        select(ScannerAgent).where(
            ScannerAgent.tenant_id == auth.tenant_id,
            ScannerAgent.is_active == True,  # noqa
        )
    )
    agents = result.scalars().all()

    return [
        {
            "id":          str(a.id),
            "name":        a.name,
            "platform":    a.platform,
            "version":     a.version,
            "last_seen":   a.last_seen.isoformat() if a.last_seen else None,
            "health":      a.last_health or {},
            "is_online":   _is_online(a),
        }
        for a in agents
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_connector_or_404(
    connector_id: str, auth: AuthContext, db: AsyncSession
) -> Connector:
    result = await db.execute(
        select(Connector).where(
            Connector.id == uuid.UUID(connector_id),
            Connector.tenant_id == auth.tenant_id,
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Connector not found")
    return c


def _connector_dict(c: Connector, agent: ScannerAgent | None) -> dict[str, Any]:
    health_status, warnings, errors = _compute_health(c)
    return {
        "id":              str(c.id),
        "name":            c.name,
        "description":     c.description,
        "connector_type":  c.connector_type,
        "is_active":       c.is_active,
        "tags":            c.tags or [],
        "routing_mode":    c.routing_mode,
        "scanner_agent": {
            "id":       str(agent.id),
            "name":     agent.name,
            "platform": agent.platform,
            "is_online": _is_online(agent),
        } if agent else None,
        "health": {
            "status":        health_status,   # healthy | warning | error | unknown
            "warnings":      warnings,
            "errors":        errors,
            "last_scan_at":  c.last_scan_at.isoformat() if c.last_scan_at else None,
            "last_scan_status": c.last_scan_status,
            "last_scan_duration_secs": c.last_scan_duration_secs,
            "last_scan_files":   c.last_scan_files,
            "last_scan_errors":  c.last_scan_errors,
            "total_files":       c.total_files_indexed,
            "throughput_fps":    c.avg_throughput_fps,
            "last_test_result":  c.last_test_result,
            "last_test_at":      c.last_test_at.isoformat() if c.last_test_at else None,
            "last_test_msg":     c.last_test_msg,
        },
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _compute_health(c: Connector) -> tuple[str, list[str], list[str]]:
    warnings, errors = [], []

    if c.last_scan_status == "never" or not c.last_scan_at:
        return "unknown", [], []

    if c.last_scan_status == "error":
        errors.append(c.last_scan_error_msg or "Last scan failed")
        return "error", warnings, errors

    if c.last_scan_errors and c.last_scan_files:
        err_rate = c.last_scan_errors / max(c.last_scan_files, 1)
        if err_rate > 0.05:
            warnings.append(f"{c.last_scan_errors} errors in last scan ({err_rate*100:.1f}%)")

    if c.last_test_result is False:
        errors.append(c.last_test_msg or "Connection test failed")

    # Check staleness
    if c.last_scan_at:
        age_hours = (datetime.now(timezone.utc) - c.last_scan_at).total_seconds() / 3600
        if age_hours > 168:  # 7 days
            warnings.append(f"Last scan was {int(age_hours/24)} days ago")
        elif age_hours > 48:
            warnings.append(f"Last scan was {int(age_hours)} hours ago")

    if errors:    return "error", warnings, errors
    if warnings:  return "warning", warnings, errors
    return "healthy", warnings, errors


def _is_online(agent: ScannerAgent) -> bool:
    if not agent or not agent.last_seen:
        return False
    age = (datetime.now(timezone.utc) - agent.last_seen).total_seconds()
    return age < 300  # 5 minutes


def _routing_modes_for(connector_type: str) -> list[str]:
    """
    Determine which routing modes are applicable for a connector type.
    Cloud connectors can go direct from backend OR via agent.
    On-prem connectors MUST go via agent.
    """
    on_prem = {"smb", "nfs", "local"}
    cloud   = {"aws-s3", "azure-blob", "gcs", "sharepoint"}
    if connector_type in on_prem:
        return ["agent"]           # must use an agent
    if connector_type in cloud:
        return ["direct", "agent", "auto"]  # can go direct or via agent
    return ["direct", "agent", "auto"]
