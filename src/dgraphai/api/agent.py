"""
Agent management API — config delivery, heartbeat, status.

dgraph-agent polls these endpoints using its API key:
  GET  /api/agent/config          → connectors to scan + settings
  POST /api/agent/heartbeat       → liveness ping + metrics update

UI endpoints (JWT auth):
  POST /api/agent/token           → generate + return a new agent API key
  GET  /api/agents                → list all agents for this tenant
  GET  /api/agents/{id}           → single agent detail + is_online
  DELETE /api/agents/{id}         → revoke agent
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db
from ..db.connector_models import Connector
from ..db.models import ScannerAgent
from ..auth.oidc import get_auth_context as get_current_user

router = APIRouter(tags=["agent"])


# ── Wire models ───────────────────────────────────────────────────────────────

class ConnectorConfig(BaseModel):
    id: str
    name: str
    connector_type: str
    config: dict
    scan_interval_minutes: int = 360
    enabled: bool = True


class AgentConfig(BaseModel):
    agent_id: str
    tenant_id: str
    cloud_url: str
    connectors: list[ConnectorConfig]
    enrichment_enabled: bool = True
    log_level: str = "info"
    max_concurrent_scans: int = 2
    version_check_url: str


class HeartbeatRequest(BaseModel):
    agent_id: str
    version: str = "unknown"
    os: str = "unknown"
    hostname: str = ""
    files_indexed: int = 0
    files_pending: int = 0
    last_error: str | None = None
    connector_statuses: dict[str, str] = {}


class HeartbeatResponse(BaseModel):
    ok: bool = True
    commands: list[dict] = []


class AgentTokenResponse(BaseModel):
    agent_id: str
    api_key: str
    install_linux: str
    install_docker: str
    install_helm: str


class AgentStatus(BaseModel):
    id: str
    name: str
    version: str
    os: str
    hostname: str
    last_seen_at: datetime | None
    files_indexed: int
    connector_statuses: dict[str, str]
    is_online: bool


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _get_agent_from_key(x_scanner_key: str | None, db: AsyncSession) -> ScannerAgent:
    if not x_scanner_key:
        raise HTTPException(status_code=401, detail="Missing X-Scanner-Key header")
    key_hash = hashlib.sha256(x_scanner_key.encode()).hexdigest()
    result = await db.execute(
        select(ScannerAgent).where(
            ScannerAgent.api_key_hash == key_hash,
            ScannerAgent.is_active == True,
        ).limit(1)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or revoked agent key")
    return agent


# ── Agent-facing endpoints (X-Scanner-Key auth) ───────────────────────────────

@router.get("/api/agent/config", response_model=AgentConfig)
async def get_agent_config(
    x_scanner_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Called by dgraph-agent on startup and periodically. Returns connector list."""
    agent = await _get_agent_from_key(x_scanner_key, db)

    result = await db.execute(
        select(Connector).where(
            Connector.tenant_id == agent.tenant_id,
            Connector.scanner_agent_id == agent.id,
            Connector.is_active == True,
        )
    )
    connectors = result.scalars().all()

    cloud_url = os.getenv("APP_URL", "https://api.dgraph.ai")

    return AgentConfig(
        agent_id    = str(agent.id),
        tenant_id   = str(agent.tenant_id),
        cloud_url   = cloud_url,
        connectors  = [
            ConnectorConfig(
                id                    = str(c.id),
                name                  = c.name,
                connector_type        = c.connector_type,
                config                = c.config or {},
                scan_interval_minutes = 360,  # default 6h — scan_schedule field not yet in model
                enabled               = c.is_active,
            )
            for c in connectors
        ],
        enrichment_enabled  = True,
        log_level           = "info",
        max_concurrent_scans= 2,
        version_check_url   = "https://api.github.com/repos/gaineyllc/dgraphai/releases/latest",
    )


@router.post("/api/agent/heartbeat", response_model=HeartbeatResponse)
async def agent_heartbeat(
    body: HeartbeatRequest,
    x_scanner_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Called by dgraph-agent every 30s. Updates last_seen + stats."""
    agent = await _get_agent_from_key(x_scanner_key, db)

    agent.last_seen_at       = datetime.now(timezone.utc)
    agent.files_indexed      = body.files_indexed
    agent.files_pending      = body.files_pending
    agent.version            = body.version
    agent.os                 = body.os
    agent.hostname           = body.hostname or agent.hostname
    agent.last_error         = body.last_error
    agent.connector_statuses = body.connector_statuses

    await db.commit()
    return HeartbeatResponse(ok=True, commands=[])


# ── UI-facing endpoints (JWT auth) ────────────────────────────────────────────

@router.post("/api/agent/token", response_model=AgentTokenResponse)
async def generate_agent_token(
    name: str = "default",
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a new agent API key for the current tenant.
    The API key is shown ONCE — store it immediately.
    """
    raw_key  = "dga_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    agent = ScannerAgent(
        tenant_id    = current_user.tenant_id,
        name         = name,
        api_key_hash = key_hash,
        is_active    = True,
        created_by   = current_user.user_id,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    cloud_url = os.getenv("APP_URL", "https://api.dgraph.ai")

    # Windows PowerShell install command
    install_windows = (
        f"$env:DGRAPH_AGENT_API_KEY='{raw_key}'; "
        f"$env:DGRAPH_AGENT_API_ENDPOINT='{cloud_url}'; "
        f".\\dgraph-agent.exe"
    )

    install_linux = (
        f"DGRAPH_AGENT_API_KEY={raw_key} "
        f"DGRAPH_AGENT_API_ENDPOINT={cloud_url} "
        f"./dgraph-agent"
    )

    install_docker = (
        f"docker run -d --name dgraph-agent \\\n"
        f"  -e DGRAPH_AGENT_API_KEY={raw_key} \\\n"
        f"  -e DGRAPH_AGENT_API_ENDPOINT={cloud_url} \\\n"
        f"  -v /:/host:ro \\\n"
        f"  ghcr.io/gaineyllc/dgraph-agent:latest"
    )

    install_helm = (
        f"helm install dgraph-agent oci://ghcr.io/gaineyllc/charts/dgraph-agent \\\n"
        f"  --set credentials.apiKey={raw_key} \\\n"
        f"  --set config.cloudUrl={cloud_url}"
    )

    return AgentTokenResponse(
        agent_id       = str(agent.id),
        api_key        = raw_key,
        install_linux  = install_linux,
        install_docker = install_docker,
        install_helm   = install_helm,
    )


@router.get("/api/agents", response_model=list[AgentStatus])
async def list_agents(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScannerAgent).where(
            ScannerAgent.tenant_id == current_user.tenant_id,
            ScannerAgent.is_active == True,
        ).order_by(ScannerAgent.created_at.desc())
    )
    agents = result.scalars().all()
    return [_agent_status(a) for a in agents]


@router.get("/api/agents/{agent_id}", response_model=AgentStatus)
async def get_agent(
    agent_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScannerAgent).where(
            ScannerAgent.id        == agent_id,
            ScannerAgent.tenant_id == current_user.tenant_id,
        ).limit(1)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_status(agent)


@router.delete("/api/agents/{agent_id}", status_code=204)
async def revoke_agent(
    agent_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScannerAgent).where(
            ScannerAgent.id        == agent_id,
            ScannerAgent.tenant_id == current_user.tenant_id,
        ).limit(1)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_active = False
    await db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _agent_status(agent: ScannerAgent) -> AgentStatus:
    now = datetime.now(timezone.utc)
    last_seen = agent.last_seen_at
    if last_seen and last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    is_online = (
        last_seen is not None and
        (now - last_seen) < timedelta(seconds=90)
    )
    return AgentStatus(
        id                  = str(agent.id),
        name                = agent.name,
        version             = getattr(agent, "version", "unknown") or "unknown",
        os                  = getattr(agent, "os", "unknown") or "unknown",
        hostname            = getattr(agent, "hostname", "") or "",
        last_seen_at        = agent.last_seen_at,
        files_indexed       = getattr(agent, "files_indexed", 0) or 0,
        connector_statuses  = getattr(agent, "connector_statuses", {}) or {},
        is_online           = is_online,
    )


def _interval_minutes(schedule: str | None) -> int:
    return {"1h": 60, "6h": 360, "12h": 720, "24h": 1440,
            "48h": 2880, "weekly": 10080}.get(schedule or "6h", 360)
