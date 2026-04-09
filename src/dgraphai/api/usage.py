"""
Usage and billing API.

Snapshots live usage from the graph and computes estimated monthly costs
broken down by tier (standard / enrichable / AI-enriched / identity / graph edges).

Endpoints:
  GET /api/usage/snapshot     — current live usage snapshot + cost estimate
  GET /api/usage/history      — daily snapshots for the billing period
  GET /api/usage/limits       — current limits vs usage (for dashboards/alerts)
  GET /api/usage/plans        — all available plans with pricing
  GET /api/usage/plans/{id}   — single plan detail
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.models import Tenant
from src.dgraphai.db.session import get_db
from src.dgraphai.graph.backends.factory import get_backend_for_tenant
from src.dgraphai.licensing.metering import (
    UsageSnapshot, CostBreakdown, PLANS, get_plan,
    NODE_TYPE_TIER, BILLED_RELATIONSHIP_TYPES,
    TIER_RATES, TIER_STANDARD, TIER_ENRICHABLE, TIER_AI_ENRICHED,
    TIER_IDENTITY, TIER_GRAPH_EDGES,
)

router = APIRouter(prefix="/api/usage", tags=["usage"])


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/snapshot")
async def get_usage_snapshot(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Live usage snapshot with cost breakdown.
    Queries the graph directly — may take a few seconds on large tenants.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return {}

    snap = await _build_snapshot(tenant, auth)
    plan = get_plan(tenant.plan or "starter")
    cost = CostBreakdown.from_snapshot(snap, plan)

    return {
        "snapshot":  _snap_dict(snap),
        "cost":      cost.to_dict(),
        "plan":      _plan_dict(plan),
        "limits":    _limits_dict(tenant, snap),
    }


@router.get("/limits")
async def get_usage_limits(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Usage vs limits — used by header quota bar, alert banners, etc.
    Returns percentage utilization for each limit dimension.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    plan   = get_plan(tenant.plan or "starter")

    # Quick counts — just totals, not full breakdown
    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})
    tid = str(auth.tenant_id)

    try:
        async with backend:
            rows = await backend.query(
                "MATCH (n) WHERE n.tenant_id = $tid RETURN count(n) AS total",
                {"tid": tid}, auth.tenant_id
            )
            total_nodes = rows[0]["total"] if rows else 0
    except Exception:
        total_nodes = 0

    # Connector count from Postgres
    from src.dgraphai.db.connector_models import Connector
    conn_result = await db.execute(
        select(Connector).where(Connector.tenant_id == auth.tenant_id)
    )
    connector_count = len(conn_result.scalars().all())

    # User count
    from src.dgraphai.db.models import User
    user_result = await db.execute(
        select(User).where(User.tenant_id == auth.tenant_id)
    )
    user_count = len(user_result.scalars().all())

    def pct(used: int, limit: int) -> float | None:
        if limit <= 0: return None  # unlimited
        return round(min(100.0, used / limit * 100), 1)

    included_nodes = (
        plan.included_standard_nodes +
        plan.included_enrichable_nodes +
        plan.included_ai_enriched_nodes
    )

    return {
        "nodes": {
            "used": total_nodes,
            "included": included_nodes if included_nodes > 0 else None,
            "pct": pct(total_nodes, included_nodes) if included_nodes > 0 else None,
        },
        "connectors": {
            "used":  connector_count,
            "limit": plan.features.get("scanner_agents", 1),
            "pct":   pct(connector_count, plan.features.get("scanner_agents", 1))
                     if isinstance(plan.features.get("scanner_agents"), int) and plan.features.get("scanner_agents") > 0 else None,
        },
        "users": {
            "used":  user_count,
            "limit": None,  # not hard-limited at plan level yet
            "pct":   None,
        },
        "plan": tenant.plan or "starter",
    }


@router.get("/plans")
async def list_plans(
    auth: AuthContext = Depends(get_auth_context),
) -> list[dict[str, Any]]:
    """All available plans with pricing details."""
    return [_plan_dict(p) for p in PLANS.values()]


@router.get("/plans/{plan_id}")
async def get_plan_detail(
    plan_id: str,
    auth:    AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    """Single plan detail with full pricing breakdown."""
    from fastapi import HTTPException
    plan = PLANS.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id!r} not found")
    return _plan_dict(plan, detailed=True)


@router.get("/rates")
async def get_tier_rates(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    """Current billing tier rates — shown in pricing UI."""
    return {
        "tiers": [
            {
                "id":          TIER_STANDARD,
                "name":        "Standard nodes",
                "description": "Directories, tags, collections, topics, vendors — structural metadata only",
                "examples":    ["Directory", "Tag", "Collection", "Event", "Vendor", "License", "Topic", "Location", "Organization"],
                "rate_per_1k": TIER_RATES[TIER_STANDARD],
                "currency":    "USD",
            },
            {
                "id":          TIER_ENRICHABLE,
                "name":        "Enrichable nodes",
                "description": "Files and applications with metadata extracted — AI enrichment not yet run",
                "examples":    ["File (raw)", "Application", "Dependency", "Certificate", "FaceCluster (unidentified)"],
                "rate_per_1k": TIER_RATES[TIER_ENRICHABLE],
                "currency":    "USD",
            },
            {
                "id":          TIER_AI_ENRICHED,
                "name":        "AI-enriched nodes",
                "description": "Files with AI summary, vision analysis, code review, or binary risk assessment",
                "examples":    ["File (with summary)", "File (vision analyzed)", "File (code reviewed)", "File (binary assessed)"],
                "rate_per_1k": TIER_RATES[TIER_AI_ENRICHED],
                "currency":    "USD",
            },
            {
                "id":          TIER_IDENTITY,
                "name":        "Identified people",
                "description": "Person nodes confirmed by face recognition with a known identity",
                "examples":    ["Person (known=true)"],
                "rate_per_1k": TIER_RATES[TIER_IDENTITY],
                "currency":    "USD",
            },
            {
                "id":          TIER_GRAPH_EDGES,
                "name":        "Graph relationships",
                "description": "AI-computed relationships: SIMILAR_TO, MENTIONS, CONTAINS_FACE, MATCHED_TO, DEPICTS",
                "examples":    ["SIMILAR_TO", "MENTIONS", "CONTAINS_FACE", "SAME_PERSON_AS", "MATCHED_TO", "DEPICTS"],
                "rate_per_1k": TIER_RATES[TIER_GRAPH_EDGES],
                "currency":    "USD",
                "unit":        "per 1,000 relationships",
            },
        ],
        "free_relationships": sorted(
            ["CHILD_OF", "DUPLICATE_OF", "PART_OF", "REFERENCES", "TAGGED_WITH",
             "LOCATED_AT", "IS_APPLICATION", "IS_BINARY", "MADE_BY", "DEPENDS_ON",
             "LICENSED_UNDER", "HAS_VULNERABILITY", "SIGNED_BY", "HAS_VERSION", "SUPERSEDES", "WITHIN"]
        ),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _build_snapshot(tenant: Tenant, auth: AuthContext) -> UsageSnapshot:
    """Query the graph to build a UsageSnapshot."""
    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})
    tid     = str(auth.tenant_id)

    async def q(cypher: str) -> int:
        try:
            async with backend:
                rows = await backend.query(cypher, {"tid": tid}, auth.tenant_id)
                return rows[0].get("c", 0) if rows else 0
        except Exception:
            return 0

    # Parallel queries
    results = await asyncio.gather(
        # Standard tier
        q("MATCH (n) WHERE n.tenant_id = $tid AND (n:Directory OR n:Tag OR n:Collection OR n:Event OR n:Vendor OR n:License OR n:Topic OR n:Organization OR n:Location OR n:Version OR n:Product) RETURN count(n) AS c"),
        # Enrichable: Files NOT yet enriched
        q("MATCH (f:File) WHERE f.tenant_id = $tid AND f.summary IS NULL RETURN count(f) AS c"),
        # AI Enriched: Files WITH summary
        q("MATCH (f:File) WHERE f.tenant_id = $tid AND f.summary IS NOT NULL RETURN count(f) AS c"),
        # Other enrichable (non-File)
        q("MATCH (n) WHERE n.tenant_id = $tid AND (n:Application OR n:Dependency OR n:Certificate OR n:Binary OR n:MediaItem OR n:Vulnerability) RETURN count(n) AS c"),
        # Identified people
        q("MATCH (p:Person) WHERE p.tenant_id = $tid AND p.known = true RETURN count(p) AS c"),
        # Unknown face clusters
        q("MATCH (n:FaceCluster) WHERE n.tenant_id = $tid RETURN count(n) AS c"),
        # Billed relationships
        q("MATCH ()-[r:SIMILAR_TO|MENTIONS|CONTAINS_FACE|SAME_PERSON_AS|MATCHED_TO|DEPICTS|OCCURRED_DURING]->() WHERE r.tenant_id IS NULL RETURN count(r) AS c"),
        # Enrichment breakdown
        q("MATCH (f:File) WHERE f.tenant_id = $tid AND f.scene_type IS NOT NULL RETURN count(f) AS c"),
        q("MATCH (f:File) WHERE f.tenant_id = $tid AND f.code_quality IS NOT NULL RETURN count(f) AS c"),
        q("MATCH (f:File) WHERE f.tenant_id = $tid AND f.risk_assessment IS NOT NULL RETURN count(f) AS c"),
    )

    (standard, files_raw, files_enriched, other_enrichable,
     identified_people, unknown_clusters, billed_rels,
     files_vision, files_code, files_binary) = results

    return UsageSnapshot(
        tenant_id          = str(auth.tenant_id),
        snapshot_at        = datetime.now(timezone.utc),
        standard_nodes     = standard,
        enrichable_nodes   = files_raw + other_enrichable,
        ai_enriched_nodes  = files_enriched,
        identified_people  = identified_people,
        unknown_people     = unknown_clusters,
        billed_relationships = billed_rels,
        files_raw          = files_raw,
        files_enriched     = files_enriched,
        files_vision       = files_vision,
        files_code         = files_code,
        files_binary       = files_binary,
    )


def _snap_dict(snap: UsageSnapshot) -> dict[str, Any]:
    return {
        "snapshot_at":         snap.snapshot_at.isoformat(),
        "total_nodes":         snap.total_nodes,
        "standard_nodes":      snap.standard_nodes,
        "enrichable_nodes":    snap.enrichable_nodes,
        "ai_enriched_nodes":   snap.ai_enriched_nodes,
        "identified_people":   snap.identified_people,
        "unknown_people":      snap.unknown_people,
        "billed_relationships":snap.billed_relationships,
        "enrichment_detail": {
            "files_raw":       snap.files_raw,
            "files_enriched":  snap.files_enriched,
            "files_vision":    snap.files_vision,
            "files_code":      snap.files_code,
            "files_binary":    snap.files_binary,
        },
    }


def _plan_dict(plan, detailed: bool = False) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id":               plan.id,
        "name":             plan.name,
        "base_monthly_fee": plan.base_monthly_fee,
        "included": {
            "standard_nodes":    plan.included_standard_nodes,
            "enrichable_nodes":  plan.included_enrichable_nodes,
            "ai_enriched_nodes": plan.included_ai_enriched_nodes,
            "relationships":     plan.included_relationships,
        },
        "volume_discounts": [
            {"from_nodes": t, "discount_pct": d}
            for t, d in plan.volume_discount_tiers
        ],
        "features":         plan.features,
    }
    return d


def _limits_dict(tenant: Tenant, snap: UsageSnapshot) -> dict[str, Any]:
    plan = get_plan(tenant.plan or "starter")
    included = (plan.included_standard_nodes +
                plan.included_enrichable_nodes +
                plan.included_ai_enriched_nodes)

    def status(used: int, limit: int) -> str:
        if limit <= 0: return "ok"
        pct = used / limit
        if pct >= 1.0:  return "exceeded"
        if pct >= 0.9:  return "critical"
        if pct >= 0.75: return "warning"
        return "ok"

    return {
        "nodes": {
            "used":    snap.total_nodes,
            "limit":   included if included > 0 else -1,
            "status":  status(snap.total_nodes, included),
        },
    }
