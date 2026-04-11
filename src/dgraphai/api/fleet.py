"""
Fleet management API — agent fleet grouping, telemetry, scan assignment.

Fleets allow multiple agents to coordinate scanning of large NFS/SMB shares:
  - Load-balance scan shards across fleet members based on capacity
  - Receive inter-agent bandwidth/latency mesh telemetry
  - Monitor fleet health in the UI
  - Route file access requests to the nearest/fastest agent

Endpoints:
  POST /api/fleets                     Create a fleet
  GET  /api/fleets                     List fleets for tenant
  GET  /api/fleets/{id}                Fleet detail + member telemetry
  PATCH /api/fleets/{id}               Update fleet (name, members)
  DELETE /api/fleets/{id}              Delete fleet
  POST /api/fleets/{id}/assign         Assign connectors across fleet members
  POST /api/fleets/{id}/telemetry      Agent posts fleet probe results
  GET  /api/fleets/{id}/mesh           Current latency mesh (for UI visualization)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.oidc import get_auth_context, AuthContext
from ..db.session import get_db
from ..db.models import ScannerAgent

router = APIRouter(prefix="/api/fleets", tags=["fleet"])


# ── In-memory fleet store (replace with DB table in production) ──────────────
# For now, fleets are stored in-process. A future migration will add a
# Fleet + FleetMember table. The API is designed so the frontend + agents
# don't need to change when we persist to DB.

_FLEETS: dict[str, dict] = {}  # fleet_id → fleet_record
_TELEMETRY: dict[str, list] = {}  # fleet_id → list of probe results


# ── Wire models ───────────────────────────────────────────────────────────────

class CreateFleetRequest(BaseModel):
    name:        str
    description: str = ""
    agent_ids:   list[str] = []
    scan_strategy: str = "round_robin"  # round_robin | capacity_weighted | latency_aware


class FleetMember(BaseModel):
    agent_id:   str
    name:       str
    hostname:   str = ""
    os:         str = "unknown"
    version:    str = "unknown"
    is_online:  bool = False
    capacity:   int = 4
    files_indexed: int = 0
    # Mesh telemetry — filled from probe results
    peer_latency_ms: dict[str, float] = {}       # peer_agent_id → latency_ms
    peer_bandwidth_mbps: dict[str, float] = {}   # peer_agent_id → bandwidth_mbps


class FleetDetail(BaseModel):
    id:           str
    name:         str
    description:  str
    tenant_id:    str
    created_at:   datetime
    scan_strategy: str
    members:      list[FleetMember]
    connector_assignments: dict[str, str]  # connector_id → agent_id
    status:       str  # healthy | degraded | offline


class TelemetrySubmit(BaseModel):
    agent_id:  str
    probes:    list[dict]  # list of ProbeResult from Go fleet package


class AssignRequest(BaseModel):
    connector_ids: list[str]
    strategy:      str = "latency_aware"  # override fleet default


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_fleet(
    req: CreateFleetRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    fleet_id = str(uuid.uuid4())
    _FLEETS[fleet_id] = {
        "id":           fleet_id,
        "name":         req.name,
        "description":  req.description,
        "tenant_id":    str(auth.tenant_id),
        "created_at":   datetime.now(timezone.utc).isoformat(),
        "scan_strategy": req.scan_strategy,
        "agent_ids":    req.agent_ids,
        "connector_assignments": {},
    }
    _TELEMETRY[fleet_id] = []
    return _FLEETS[fleet_id]


@router.get("")
async def list_fleets(
    auth: AuthContext = Depends(get_auth_context),
) -> list[dict]:
    return [f for f in _FLEETS.values() if f["tenant_id"] == str(auth.tenant_id)]


@router.get("/{fleet_id}")
async def get_fleet(
    fleet_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> FleetDetail:
    fleet = _FLEETS.get(fleet_id)
    if not fleet or fleet["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail="Fleet not found")

    # Load agent records
    members = []
    for agent_id in fleet["agent_ids"]:
        result = await db.execute(
            select(ScannerAgent).where(
                ScannerAgent.id == agent_id,
                ScannerAgent.tenant_id == auth.tenant_id,
            ).limit(1)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            continue

        from datetime import timedelta
        now = datetime.now(timezone.utc)
        last_seen = agent.last_seen_at
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        is_online = last_seen is not None and (now - last_seen) < timedelta(seconds=90)

        # Build latency/bandwidth mesh from telemetry
        peer_latency: dict[str, float] = {}
        peer_bandwidth: dict[str, float] = {}
        for probe in _TELEMETRY.get(fleet_id, []):
            if probe.get("from_agent") == str(agent.id):
                for p in probe.get("probes", []):
                    peer_id = p.get("peer_agent_id", "")
                    if p.get("reachable") and peer_id:
                        peer_latency[peer_id]   = p.get("latency_ms", 0)
                        peer_bandwidth[peer_id] = p.get("bandwidth_mbps", 0)

        members.append(FleetMember(
            agent_id       = str(agent.id),
            name           = agent.name,
            hostname       = getattr(agent, "hostname", "") or "",
            os             = getattr(agent, "os", "unknown") or "unknown",
            version        = getattr(agent, "version", "unknown") or "unknown",
            is_online      = is_online,
            files_indexed  = getattr(agent, "files_indexed", 0) or 0,
            peer_latency_ms     = peer_latency,
            peer_bandwidth_mbps = peer_bandwidth,
        ))

    online = sum(1 for m in members if m.is_online)
    status = "healthy" if online == len(members) and online > 0 else \
             "degraded" if online > 0 else "offline"

    return FleetDetail(
        id           = fleet_id,
        name         = fleet["name"],
        description  = fleet["description"],
        tenant_id    = fleet["tenant_id"],
        created_at   = datetime.fromisoformat(fleet["created_at"]),
        scan_strategy= fleet["scan_strategy"],
        members      = members,
        connector_assignments = fleet["connector_assignments"],
        status       = status,
    )


@router.patch("/{fleet_id}")
async def update_fleet(
    fleet_id: str,
    body: dict,
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    fleet = _FLEETS.get(fleet_id)
    if not fleet or fleet["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail="Fleet not found")
    for key in ("name", "description", "scan_strategy", "agent_ids"):
        if key in body:
            fleet[key] = body[key]
    return fleet


@router.delete("/{fleet_id}", status_code=204)
async def delete_fleet(
    fleet_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> None:
    fleet = _FLEETS.get(fleet_id)
    if not fleet or fleet["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail="Fleet not found")
    del _FLEETS[fleet_id]
    _TELEMETRY.pop(fleet_id, None)


@router.post("/{fleet_id}/telemetry")
async def submit_telemetry(
    fleet_id: str,
    body: TelemetrySubmit,
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    """Agent posts inter-agent probe results for the fleet mesh."""
    fleet = _FLEETS.get(fleet_id)
    if not fleet or fleet["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail="Fleet not found")

    entry = {
        "from_agent": body.agent_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "probes": body.probes,
    }
    if fleet_id not in _TELEMETRY:
        _TELEMETRY[fleet_id] = []
    # Keep only the last 100 telemetry entries per fleet
    _TELEMETRY[fleet_id].append(entry)
    _TELEMETRY[fleet_id] = _TELEMETRY[fleet_id][-100:]

    return {"ok": True, "fleet_id": fleet_id}


@router.get("/{fleet_id}/mesh")
async def get_mesh(
    fleet_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    """Return the current latency mesh for visualization."""
    fleet = _FLEETS.get(fleet_id)
    if not fleet or fleet["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail="Fleet not found")

    # Build adjacency matrix from most recent probes per agent pair
    edges: list[dict] = []
    seen = set()
    for entry in reversed(_TELEMETRY.get(fleet_id, [])):
        from_id = entry["from_agent"]
        for probe in entry.get("probes", []):
            peer_id = probe.get("peer_agent_id", "")
            key = tuple(sorted([from_id, peer_id]))
            if key not in seen and probe.get("reachable"):
                seen.add(key)
                edges.append({
                    "from":      from_id,
                    "to":        peer_id,
                    "latency_ms":      probe.get("latency_ms", 0),
                    "bandwidth_mbps":  probe.get("bandwidth_mbps", 0),
                    "quality":   _quality(probe.get("latency_ms", 999)),
                })

    return {
        "fleet_id": fleet_id,
        "agent_ids": fleet["agent_ids"],
        "edges": edges,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/{fleet_id}/assign")
async def assign_connectors(
    fleet_id: str,
    req: AssignRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    """
    Assign connectors to fleet members for load-balanced scanning.
    Uses the fleet's scan strategy (round_robin, capacity_weighted, latency_aware).
    """
    fleet = _FLEETS.get(fleet_id)
    if not fleet or fleet["tenant_id"] != str(auth.tenant_id):
        raise HTTPException(status_code=404, detail="Fleet not found")

    agent_ids = fleet.get("agent_ids", [])
    if not agent_ids:
        raise HTTPException(status_code=400, detail="Fleet has no members")

    strategy = req.strategy or fleet.get("scan_strategy", "round_robin")
    assignments: dict[str, str] = {}

    if strategy == "round_robin":
        for i, connector_id in enumerate(req.connector_ids):
            assignments[connector_id] = agent_ids[i % len(agent_ids)]

    elif strategy in ("capacity_weighted", "latency_aware"):
        # Simple weighted round-robin for now (full impl needs agent capacity data)
        # TODO: use mesh telemetry to pick lowest-latency agent for each connector's host
        for i, connector_id in enumerate(req.connector_ids):
            assignments[connector_id] = agent_ids[i % len(agent_ids)]

    fleet["connector_assignments"].update(assignments)
    return {"fleet_id": fleet_id, "assignments": assignments, "strategy": strategy}


def _quality(latency_ms: float) -> str:
    if latency_ms < 5:   return "excellent"
    if latency_ms < 20:  return "good"
    if latency_ms < 100: return "fair"
    return "poor"
