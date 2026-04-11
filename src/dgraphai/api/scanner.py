"""
Scanner Agent API — backend endpoints called by on-prem scanner agents.

Authentication: X-Scanner-Key header (not OIDC — agents use API keys).
All endpoints validate the key against the registered ScannerAgent record
and extract tenant_id from the registration.

Endpoints:
  POST /api/scanner/register       Register a new agent (one-time, with OIDC user auth)
  GET  /api/scanner/jobs           Poll for pending scan jobs
  POST /api/scanner/sync           Submit a GraphDelta chunk
  POST /api/scanner/heartbeat      Update agent health/last-seen
  POST /api/scanner/rotate-key     Rotate API key
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.db.models import ScannerAgent, Tenant
from src.dgraphai.db.session import get_db
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.rbac.engine import require_permissions
from src.dgraphai.scanner.protocol import GraphDelta, ScanJob

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


# ── Scanner authentication ─────────────────────────────────────────────────────

async def _get_scanner(
    x_scanner_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ScannerAgent:
    """Authenticate a scanner agent by API key."""
    if not x_scanner_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Scanner-Key header required",
        )

    # Hash the provided key and look it up
    key_hash = hashlib.sha256(x_scanner_key.encode()).hexdigest()
    result = await db.execute(
        select(ScannerAgent).where(
            ScannerAgent.api_key_hash == key_hash,
            ScannerAgent.is_active == True,  # noqa: E712
        )
    )
    scanner = result.scalar_one_or_none()
    if not scanner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive scanner key",
        )

    # Update last_seen
    scanner.last_seen = datetime.now(timezone.utc)
    return scanner


# ── Registration ───────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name:        str
    description: str = ""
    platform:    str = "kubernetes"  # kubernetes | docker | bare-metal
    version:     str = "unknown"


class RegisterResponse(BaseModel):
    scanner_id: str
    api_key:    str   # shown ONCE — store securely as K8s secret
    message:    str


@router.post("/register", response_model=RegisterResponse)
async def register_scanner(
    req: RegisterRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """
    Register a new scanner agent. Requires OIDC auth with scanners:register permission.
    Returns an API key shown exactly once — store it as a K8s secret immediately.
    """
    # Generate a secure API key
    raw_key  = f"dg_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    # Enforce permission inline
    if "scanners:register" not in auth.permissions and "admin:*" not in auth.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission required: scanners:register")

    scanner = ScannerAgent(
        tenant_id     = auth.tenant_id,
        name          = req.name,
        description   = req.description,
        api_key_hash  = key_hash,
        platform      = req.platform,
        version       = req.version,
        registered_by = auth.user_id,
    )
    db.add(scanner)
    await db.flush()

    return RegisterResponse(
        scanner_id = str(scanner.id),
        api_key    = raw_key,
        message    = (
            "Store this API key as a Kubernetes secret immediately. "
            "It will not be shown again."
        ),
    )


@router.post("/rotate-key")
async def rotate_key(
    scanner: ScannerAgent = Depends(_get_scanner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Rotate the scanner's API key. Old key immediately invalidated."""
    raw_key          = f"dg_{secrets.token_urlsafe(32)}"
    scanner.api_key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return {
        "api_key": raw_key,
        "message": "Update your K8s secret with this new key immediately.",
    }


# ── Job polling ────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def poll_jobs(
    scanner: ScannerAgent = Depends(_get_scanner),
) -> list[dict[str, Any]]:
    """
    Poll for pending scan jobs assigned to this scanner.
    Scanner calls this on its polling interval (default: every 60s).
    Returns empty list when no jobs are pending.
    """
    # TODO: implement job queue (Redis / Postgres-based)
    # For now returns empty — jobs triggered manually via /api/indexer/start
    return []


# ── Delta sync ─────────────────────────────────────────────────────────────────

class DeltaChunk(BaseModel):
    scanner_id:  str
    tenant_id:   str
    scan_job_id: str
    chunk_index: int
    is_final:    bool
    scanned_at:  str
    stats:       dict[str, int]
    nodes:       list[dict[str, Any]]
    edges:       list[dict[str, Any]]


@router.post("/sync")
async def sync_delta(
    chunk: DeltaChunk,
    scanner: ScannerAgent = Depends(_get_scanner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Accept a GraphDelta chunk from the scanner and merge it into the tenant graph.

    The scanner sends data in chunks (default 500 nodes per chunk).
    Each chunk is idempotent — safe to retry on network failure.
    The backend merges nodes/edges into the tenant-scoped graph.
    """
    # Validate scanner belongs to the claimed tenant
    if str(scanner.tenant_id) != chunk.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_id mismatch",
        )

    from src.dgraphai.graph.backends.factory import get_backend_for_tenant
    import uuid as _uuid

    # Get tenant's graph backend
    result = await db.execute(
        select(__import__("src.dgraphai.db.models", fromlist=["Tenant"]).Tenant)
        .where(__import__("src.dgraphai.db.models", fromlist=["Tenant"]).Tenant.id == scanner.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    backend = get_backend_for_tenant(
        tenant.graph_backend or "neo4j",
        tenant.graph_config or {},
    )

    nodes_merged = 0
    edges_merged = 0
    errors = 0

    # Use deduplication for File nodes (sha256-based merge with paths[] array)
    from src.dgraphai.graph.dedup import bulk_upsert_query
    from src.dgraphai.graph.client import get_graph_client
    gclient = get_graph_client()

    file_nodes = [n for n in chunk.nodes if n.get("type") == "File" or (n.get("labels") or [None])[0] == "File"]
    other_nodes = [n for n in chunk.nodes if n not in file_nodes]
    agent_id_str = str(scanner.id)

    # Batch upsert File nodes with deduplication
    if file_nodes:
        try:
            node_props_list = [n.get("props", n) for n in file_nodes]
            cypher, params = bulk_upsert_query(node_props_list, agent_id_str, chunk.tenant_id)
            rows = await gclient.query(cypher, params)
            nodes_merged += rows[0].get("merged", 0) if rows else 0
        except Exception as e:
            errors += len(file_nodes)

    # Non-File nodes use standard upsert
    async with backend:
        tenant_uuid = _uuid.UUID(chunk.tenant_id)

        for node in other_nodes:
            try:
                if node["op"] == "upsert":
                    await backend.upsert_node(
                        node_type = node["type"],
                        node_id   = node["id"],
                        props     = node.get("props", {}),
                        tenant_id = tenant_uuid,
                    )
                    nodes_merged += 1
            except Exception:
                errors += 1

        for edge in chunk.edges:
            try:
                if edge["op"] == "upsert":
                    await backend.upsert_rel(
                        rel_type  = edge["type"],
                        from_id   = edge["from"],
                        to_id     = edge["to"],
                        props     = edge.get("props", {}),
                        tenant_id = tenant_uuid,
                    )
                    edges_merged += 1
            except Exception:
                errors += 1

    # Update scanner stats on final chunk
    if chunk.is_final:
        scanner.last_health = {
            "last_sync":    chunk.scanned_at,
            "files_indexed": chunk.stats.get("total_files", 0),
            "errors":        errors,
        }

    return {
        "status":        "accepted",
        "chunk_index":   chunk.chunk_index,
        "nodes_merged":  nodes_merged,
        "edges_merged":  edges_merged,
        "errors":        errors,
        "is_final":      chunk.is_final,
    }


# ── Heartbeat ──────────────────────────────────────────────────────────────────

class HeartbeatPayload(BaseModel):
    version:       str
    platform:      str
    uptime_secs:   int
    files_indexed: int
    errors:        int
    connectors:    int
    scanning:      bool
    # Network topology for source routing
    region:          str = "unknown"       # e.g. 'us-east-1', 'eu-west-1', 'on-prem'
    datacenter:      str = "unknown"       # human-readable location
    latency_matrix:  dict[str, float] = {} # {region: avg_rtt_ms}
    bandwidth_mbps:  float = 100.0         # measured upload bandwidth
    indexed_connectors: list[str] = []     # connector IDs indexed by this agent


@router.post("/heartbeat")
async def heartbeat(
    payload: HeartbeatPayload,
    scanner: ScannerAgent = Depends(_get_scanner),
) -> dict[str, str]:
    """
    Regular health update from scanner agent.
    Scanner posts every 60 seconds when healthy.
    Backend marks scanner 'offline' if no heartbeat for 5 minutes.
    """
    scanner.version     = payload.version
    scanner.platform    = payload.platform

    # Update routing topology
    from src.dgraphai.streaming.router import AgentTopology, get_stream_router
    topo = AgentTopology(
        agent_id            = str(scanner.id),
        region              = payload.region,
        datacenter          = payload.datacenter,
        latency_matrix      = payload.latency_matrix,
        bandwidth_mbps      = payload.bandwidth_mbps,
        is_online           = True,
        indexed_connectors  = payload.indexed_connectors,
    )
    get_stream_router().register_agent(topo)

    scanner.last_health = {
        "uptime_secs":   payload.uptime_secs,
        "files_indexed": payload.files_indexed,
        "errors":        payload.errors,
        "connectors":    payload.connectors,
        "scanning":      payload.scanning,
        "reported_at":   datetime.now(timezone.utc).isoformat(),
    }
    return {"status": "ok"}
