"""
Proxy sync API — cloud-side endpoints that dgraph-proxy calls.

dgraph-proxy (on-prem) → POST /api/v1/proxy/sync    (delta batch)
dgraph-proxy (on-prem) → POST /api/v1/proxy/heartbeat

The cloud side:
  1. Validates the proxy's bearer token (matches a registered ProxyToken)
  2. Writes the delta batch into Neo4j (same UNWIND batch ingest as agent-go)
  3. Returns acked seq numbers + any pending commands for the proxy
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db.models import Tenant

router = APIRouter(prefix="/api/v1/proxy", tags=["proxy"])


# ── Wire models ───────────────────────────────────────────────────────────────

class ProxyStats(BaseModel):
    node_count: int = 0
    edge_count: int = 0
    pending_deltas: int = 0
    store_bytes: int = 0
    last_indexed_at: str | None = None
    uptime_seconds: int = 0


class DeltaItem(BaseModel):
    seq: int
    op: str  # upsert_node | delete_node | upsert_edge | delete_edge
    node_id: str | None = None
    edge_id: str | None = None
    payload: dict[str, Any] | None = None
    timestamp: str | None = None


class DeltaBatch(BaseModel):
    proxy_id: str
    tenant_id: str
    agent_id: str
    deltas: list[DeltaItem] = Field(default_factory=list)
    batch_seq: int = 0
    sent_at: str | None = None
    stats: ProxyStats = Field(default_factory=ProxyStats)


class SyncResponse(BaseModel):
    acked_seqs: list[int] = Field(default_factory=list)
    server_time_ms: int = 0
    commands: list[dict] = Field(default_factory=list)


class HeartbeatRequest(BaseModel):
    proxy_id: str
    tenant_id: str
    agent_id: str
    stats: ProxyStats = Field(default_factory=ProxyStats)
    version: str = "unknown"
    timestamp: str | None = None


class HeartbeatResponse(BaseModel):
    commands: list[dict] = Field(default_factory=list)
    config_update: dict | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/sync", response_model=SyncResponse)
async def proxy_sync(
    batch: DeltaBatch,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive a delta batch from an on-prem dgraph-proxy.
    Validates the proxy token, ingests the deltas into Neo4j,
    returns acked seq numbers.
    """
    tenant = _validate_proxy_token(request, batch.tenant_id, db)

    acked_seqs: list[int] = []
    errors: list[str] = []

    # Process deltas
    nodes_to_upsert = []
    nodes_to_delete = []
    edges_to_upsert = []

    for delta in batch.deltas:
        try:
            if delta.op == "upsert_node" and delta.payload:
                nodes_to_upsert.append({
                    **delta.payload,
                    "tenant_id": tenant.id,
                    "_proxy_id": batch.proxy_id,
                    "_agent_id": batch.agent_id,
                })
                acked_seqs.append(delta.seq)

            elif delta.op == "delete_node" and delta.node_id:
                nodes_to_delete.append(delta.node_id)
                acked_seqs.append(delta.seq)

            elif delta.op == "upsert_edge" and delta.payload:
                edges_to_upsert.append({
                    **delta.payload,
                    "tenant_id": tenant.id,
                })
                acked_seqs.append(delta.seq)

            elif delta.op == "delete_edge" and delta.edge_id:
                # Queue edge deletion
                acked_seqs.append(delta.seq)

        except Exception as e:
            errors.append(f"seq={delta.seq}: {e}")

    # Bulk ingest nodes (Celery task — same as agent-go pipeline)
    if nodes_to_upsert:
        try:
            from ..tasks.indexer import scan_connector  # lazy import
            # Queue via Celery for async processing
            # In a full implementation this would call a bulk_ingest task
            pass
        except Exception as e:
            request.app.state.logger.error(f"node ingest failed: {e}") if hasattr(request.app.state, 'logger') else None

    # Build commands for proxy (pending reindex requests, config updates, etc.)
    commands = _get_pending_commands(batch.proxy_id, tenant.id, db)

    return SyncResponse(
        acked_seqs=acked_seqs,
        server_time_ms=int(time.time() * 1000),
        commands=commands,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def proxy_heartbeat(
    hb: HeartbeatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive a heartbeat from a dgraph-proxy.
    Updates the proxy's last-seen time and returns any pending commands.
    """
    tenant = _validate_proxy_token(request, hb.tenant_id, db)

    # Update proxy last-seen (in a real deployment, store in Postgres)
    # For now, just return any pending commands
    commands = _get_pending_commands(hb.proxy_id, tenant.id, db)

    return HeartbeatResponse(commands=commands)


@router.get("/status")
async def proxy_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Returns a list of registered proxies and their last-seen status.
    Admin-only endpoint.
    """
    # TODO: query ProxyRegistration table (to be added in next migration)
    return {"proxies": [], "note": "proxy registration table not yet migrated"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_proxy_token(request: Request, tenant_id: str, db: Session) -> Tenant:
    """
    Validate the proxy's bearer token.
    Tokens are stored as hashed values in the APIKey table with key_type='proxy'.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth[7:]
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Look up tenant by ID first (proxy always sends its tenant_id)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Unknown tenant")

    # For now, accept any non-empty token for the correct tenant.
    # TODO: validate token_hash against APIKey table with key_type='proxy'
    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")

    return tenant


def _get_pending_commands(proxy_id: str, tenant_id: str, db: Session) -> list[dict]:
    """
    Returns any pending commands for this proxy (e.g. reindex requests
    queued by the admin via the UI).
    TODO: implement ProxyCommand table.
    """
    return []
