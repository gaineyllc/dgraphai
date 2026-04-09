"""
Agent management API — config delivery, heartbeat, status.

dgraph-agent polls these endpoints using its API key:
  GET  /api/agent/config          → what connectors to scan + settings
  POST /api/agent/heartbeat       → liveness ping + metrics update
  GET  /api/agent/token           → (wizard) generate + return a new agent token
  GET  /api/agents                → (UI) list all agents for this tenant
  GET  /api/agents/{id}           → (UI) single agent detail
  DELETE /api/agents/{id}         → (UI) revoke agent
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
    connector_statuses: dict[str, str] = {}  # connector_id → "scanning|idle|error"


class HeartbeatResponse(BaseModel):
    ok: bool = True
    commands: list[dict] = []


class AgentTokenResponse(BaseModel):
    agent_id: str
    api_key: str          # shown ONCE — store immediately
    install_linux: str    # ready-to-run curl command
    install_docker: str   # ready-to-run docker run command
    install_helm: str     # ready-to-run helm command


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

def _get_agent_from_key(x_scanner_key: str | None, db: Session) -> ScannerAgent:
    """Authenticate an agent by X-Scanner-Key header."""
    if not x_scanner_key:
        raise HTTPException(status_code=401, detail="Missing X-Scanner-Key header")
    key_hash = hashlib.sha256(x_scanner_key.encode()).hexdigest()
    agent = db.query(ScannerAgent).filter(
        ScannerAgent.api_key_hash == key_hash,
        ScannerAgent.is_active == True,
    ).first()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or revoked agent key")
    return agent


# ── Agent-facing endpoints ────────────────────────────────────────────────────

@router.get("/api/agent/config", response_model=AgentConfig)
def get_agent_config(
    x_scanner_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Called by dgraph-agent on startup and periodically.
    Returns the full connector config the agent should scan.
    """
    agent = _get_agent_from_key(x_scanner_key, db)

    # Get all connectors assigned to this agent
    connectors = db.query(Connector).filter(
        Connector.tenant_id == agent.tenant_id,
        Connector.scanner_agent_id == agent.id,
        Connector.is_active == True,
    ).all()

    connector_configs = []
    for c in connectors:
        connector_configs.append(ConnectorConfig(
            id=str(c.id),
            name=c.name,
            connector_type=c.connector_type,
            config=c.config or {},
            scan_interval_minutes=_interval_minutes(c.scan_schedule),
            enabled=c.is_active,
        ))

    cloud_url = os.getenv("APP_URL", "https://api.dgraph.ai")

    return AgentConfig(
        agent_id=str(agent.id),
        tenant_id=str(agent.tenant_id),
        cloud_url=cloud_url,
        connectors=connector_configs,
        enrichment_enabled=True,
        log_level="info",
        max_concurrent_scans=2,
        version_check_url=f"https://api.github.com/repos/gaineyllc/dgraphai/releases/latest",
    )


@router.post("/api/agent/heartbeat", response_model=HeartbeatResponse)
def agent_heartbeat(
    body: HeartbeatRequest,
    x_scanner_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Called by dgraph-agent every 30 seconds.
    Updates last_seen, file counts, and connector statuses.
    """
    agent = _get_agent_from_key(x_scanner_key, db)

    # Update agent record
    agent.last_seen_at    = datetime.now(timezone.utc)
    agent.files_indexed   = body.files_indexed
    agent.files_pending   = body.files_pending
    agent.version         = body.version
    agent.os              = body.os
    agent.hostname        = body.hostname or agent.hostname
    agent.last_error      = body.last_error
    agent.connector_statuses = body.connector_statuses

    db.commit()

    # Pull any pending commands (reindex requests, config changes)
    commands = _get_pending_commands(agent, db)

    return HeartbeatResponse(ok=True, commands=commands)


# ── UI-facing endpoints ───────────────────────────────────────────────────────

@router.post("/api/agent/token", response_model=AgentTokenResponse)
def generate_agent_token(
    name: str = "default",
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a new agent API key for the current tenant.
    The API key is shown ONCE and never stored in plaintext.
    Called by the first-run wizard to generate the install command.
    """
    raw_key  = "dga_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    agent = ScannerAgent(
        tenant_id   = current_user.tenant_id,
        name        = name,
        api_key_hash= key_hash,
        is_active   = True,
        created_by  = current_user.id,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    cloud_url = os.getenv("APP_URL", "https://api.dgraph.ai")

    install_linux = (
        f"curl -L {cloud_url}/install.sh | "
        f"DGRAPH_AGENT_API_KEY={raw_key} DGRAPH_CLOUD_URL={cloud_url} bash"
    )

    install_docker = (
        f"docker run -d --name dgraph-agent \\\n"
        f"  -e DGRAPH_AGENT_API_KEY={raw_key} \\\n"
        f"  -e DGRAPH_CLOUD_URL={cloud_url} \\\n"
        f"  -v /:/host:ro \\\n"
        f"  ghcr.io/gaineyllc/dgraph-agent:latest"
    )

    install_helm = (
        f"helm install dgraph-agent oci://ghcr.io/gaineyllc/charts/dgraph-agent \\\n"
        f"  --set credentials.apiKey={raw_key} \\\n"
        f"  --set config.cloudUrl={cloud_url}"
    )

    return AgentTokenResponse(
        agent_id      = str(agent.id),
        api_key       = raw_key,
        install_linux = install_linux,
        install_docker= install_docker,
        install_helm  = install_helm,
    )


@router.get("/api/agents", response_model=list[AgentStatus])
def list_agents(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all agents registered to this tenant."""
    agents = db.query(ScannerAgent).filter(
        ScannerAgent.tenant_id == current_user.tenant_id,
        ScannerAgent.is_active == True,
    ).order_by(ScannerAgent.created_at.desc()).all()

    return [_agent_status(a) for a in agents]


@router.get("/api/agents/{agent_id}", response_model=AgentStatus)
def get_agent(
    agent_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(ScannerAgent).filter(
        ScannerAgent.id        == agent_id,
        ScannerAgent.tenant_id == current_user.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_status(agent)


@router.delete("/api/agents/{agent_id}", status_code=204)
def revoke_agent(
    agent_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke an agent's API key. The agent will be unable to connect."""
    agent = db.query(ScannerAgent).filter(
        ScannerAgent.id        == agent_id,
        ScannerAgent.tenant_id == current_user.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_active = False
    db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _agent_status(agent: ScannerAgent) -> AgentStatus:
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    last_seen = agent.last_seen_at
    is_online = (
        last_seen is not None and
        (now - last_seen.replace(tzinfo=timezone.utc if last_seen.tzinfo is None else last_seen.tzinfo)) < timedelta(seconds=90)
    )
    return AgentStatus(
        id                  = str(agent.id),
        name                = agent.name,
        version             = getattr(agent, "version", "unknown"),
        os                  = getattr(agent, "os", "unknown"),
        hostname            = getattr(agent, "hostname", ""),
        last_seen_at        = agent.last_seen_at,
        files_indexed       = getattr(agent, "files_indexed", 0) or 0,
        connector_statuses  = getattr(agent, "connector_statuses", {}) or {},
        is_online           = is_online,
    )


def _interval_minutes(schedule: str | None) -> int:
    mapping = {
        "1h": 60, "6h": 360, "12h": 720,
        "24h": 1440, "48h": 2880, "weekly": 10080,
    }
    return mapping.get(schedule or "6h", 360)


def _get_pending_commands(agent: ScannerAgent, db: Session) -> list[dict]:
    """Return any pending commands queued for this agent (reindex, etc.)."""
    # TODO: implement AgentCommand table
    return []
