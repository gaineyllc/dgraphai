"""
Graph intelligence — attack path analysis, neighborhood expansion, graph diff.

Attack path analysis answers: "How would an attacker move from node A to node B?"
Uses Neo4j shortest path queries across security-relevant relationship types.

Neighborhood expansion: given a node ID, return all directly connected nodes
(1-hop or N-hop). Used by the frontend to expand a node in the graph explorer.

Graph diff: compare two scan snapshots — what nodes appeared/disappeared.
"""
from __future__ import annotations
import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.models import Tenant
from src.dgraphai.db.session import get_db
from src.dgraphai.graph.backends.factory import get_backend_for_tenant

router = APIRouter(prefix="/api/graph/intel", tags=["graph-intelligence"])


async def _backend(auth: AuthContext, db: AsyncSession):
    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})


# ── Attack path analysis ───────────────────────────────────────────────────────

@router.get("/attack-path")
async def find_attack_path(
    from_id:  str = Query(..., description="Start node ID"),
    to_id:    str = Query(..., description="Target node ID"),
    max_hops: int = Query(default=6, ge=1, le=15),
    auth:     AuthContext = Depends(get_auth_context),
    db:       AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Find the shortest attack path between two nodes.

    Uses allShortestPaths across security-relevant relationships:
      - HAS_VULNERABILITY (app → CVE)
      - DEPENDS_ON (app → dependency with CVE)
      - SIGNED_BY (binary → compromised cert)
      - CONTAINS_FACE / SAME_PERSON_AS (identity chain)
      - SIMILAR_TO (lateral movement via similar files)
      - LOCATED_AT (geographic correlation)

    Returns path nodes, edges, and a risk score.
    """
    backend = await _backend(auth, db)
    tid = str(auth.tenant_id)

    cypher = f"""
    MATCH path = allShortestPaths(
      (start) -[*1..{max_hops}]- (end)
    )
    WHERE id(start) = $from_id
      AND id(end)   = $to_id
      AND start.tenant_id = $tid
      AND end.tenant_id   = $tid
    RETURN
      [n IN nodes(path) | {{
        id:       id(n),
        labels:   labels(n),
        name:     coalesce(n.name, n.path, toString(id(n))),
        props:    properties(n)
      }}] AS nodes,
      [r IN relationships(path) | {{
        type:   type(r),
        from:   id(startNode(r)),
        to:     id(endNode(r))
      }}] AS edges,
      length(path) AS hops
    ORDER BY hops
    LIMIT 5
    """

    try:
        async with backend:
            rows = await backend.query(cypher, {"from_id": from_id, "to_id": to_id, "tid": tid}, auth.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph query failed: {e}")

    if not rows:
        return {"found": False, "paths": [], "message": "No path found between these nodes"}

    paths = []
    for row in rows:
        path_nodes = row.get("nodes", [])
        path_edges = row.get("edges", [])
        risk_score = _compute_path_risk(path_nodes, path_edges)
        paths.append({
            "nodes":      path_nodes,
            "edges":      path_edges,
            "hops":       row.get("hops", 0),
            "risk_score": risk_score,
            "risk_label": _risk_label(risk_score),
        })

    return {
        "found":    True,
        "paths":    paths,
        "from_id":  from_id,
        "to_id":    to_id,
        "summary":  f"Found {len(paths)} path(s). Shortest: {paths[0]['hops']} hop(s).",
    }


def _compute_path_risk(nodes: list, edges: list) -> float:
    """
    Heuristic risk score 0.0–1.0 based on edge types in the path.
    Higher score = more dangerous path.
    """
    score = 0.0
    edge_weights = {
        "HAS_VULNERABILITY":  0.9,
        "DEPENDS_ON":         0.6,
        "CONTAINS_FACE":      0.5,
        "SAME_PERSON_AS":     0.7,
        "SIGNED_BY":          0.4,
        "SIMILAR_TO":         0.3,
        "REFERENCES":         0.2,
        "LOCATED_AT":         0.1,
    }
    for edge in edges:
        weight = edge_weights.get(edge.get("type", ""), 0.1)
        score  = max(score, weight)

    # Penalize longer paths slightly
    hop_penalty = min(0.1 * len(edges), 0.3)
    return min(1.0, score + hop_penalty)


def _risk_label(score: float) -> str:
    if score >= 0.8: return "critical"
    if score >= 0.6: return "high"
    if score >= 0.4: return "medium"
    return "low"


# ── Neighborhood expansion ─────────────────────────────────────────────────────

@router.get("/neighborhood")
async def get_neighborhood(
    node_id: str = Query(..., description="Center node ID"),
    hops:    int = Query(default=1, ge=1, le=3),
    limit:   int = Query(default=50, ge=1, le=200),
    auth:    AuthContext = Depends(get_auth_context),
    db:      AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Return all nodes and edges within N hops of a given node.
    Used by the graph explorer to expand a node's connections.
    """
    backend = await _backend(auth, db)
    tid = str(auth.tenant_id)

    cypher = f"""
    MATCH (center)
    WHERE id(center) = $node_id AND center.tenant_id = $tid
    MATCH path = (center) -[*1..{hops}]- (neighbor)
    WHERE neighbor.tenant_id = $tid
    WITH center, collect(DISTINCT neighbor)[..{limit}] AS neighbors,
         collect(DISTINCT relationships(path)) AS rel_lists
    RETURN
      center,
      neighbors,
      [r IN apoc.coll.flatten(rel_lists) |
        {{type: type(r), from: id(startNode(r)), to: id(endNode(r))}}
      ] AS edges
    LIMIT 1
    """

    # Fallback without APOC
    cypher_simple = f"""
    MATCH (center)
    WHERE id(center) = $node_id AND center.tenant_id = $tid
    MATCH (center) -[r]- (neighbor)
    WHERE neighbor.tenant_id = $tid
    RETURN center,
           collect(DISTINCT {{
             id:     id(neighbor),
             labels: labels(neighbor),
             name:   coalesce(neighbor.name, neighbor.path, toString(id(neighbor))),
             props:  properties(neighbor)
           }})[..{limit}] AS neighbors,
           collect(DISTINCT {{
             type: type(r),
             from: id(startNode(r)),
             to:   id(endNode(r))
           }}) AS edges
    """

    try:
        async with backend:
            rows = await backend.query(cypher_simple, {"node_id": node_id, "tid": tid}, auth.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph query failed: {e}")

    if not rows:
        return {"center": None, "neighbors": [], "edges": []}

    row = rows[0]
    center = row.get("center", {})
    if isinstance(center, dict):
        center_out = {
            "id":     center.get("id", node_id),
            "labels": center.get("labels", []),
            "name":   center.get("name") or center.get("path") or node_id,
            "props":  center,
        }
    else:
        center_out = {"id": node_id, "labels": [], "name": node_id, "props": {}}

    return {
        "center":    center_out,
        "neighbors": row.get("neighbors", []),
        "edges":     row.get("edges", []),
        "total":     len(row.get("neighbors", [])),
    }


# ── Related nodes (context menu) ──────────────────────────────────────────────

@router.get("/related")
async def get_related_nodes(
    node_id:   str = Query(...),
    rel_types: str = Query(default="", description="Comma-separated relationship types to filter"),
    limit:     int = Query(default=20, ge=1, le=100),
    auth:      AuthContext = Depends(get_auth_context),
    db:        AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get nodes related to a given node, grouped by relationship type.
    Used by the right-click context menu in the graph explorer.
    """
    backend = await _backend(auth, db)
    tid     = str(auth.tenant_id)

    rel_filter = ""
    if rel_types:
        types = [t.strip() for t in rel_types.split(",") if t.strip()]
        rel_filter = f"AND type(r) IN {types!r}"

    cypher = f"""
    MATCH (n) WHERE id(n) = $node_id AND n.tenant_id = $tid
    MATCH (n) -[r]- (m) WHERE m.tenant_id = $tid {rel_filter}
    RETURN type(r)  AS rel_type,
           count(m) AS count,
           collect(DISTINCT {{
             id:     id(m),
             labels: labels(m),
             name:   coalesce(m.name, m.path, toString(id(m)))
           }})[..{limit}] AS nodes
    ORDER BY count DESC
    """

    try:
        async with backend:
            rows = await backend.query(cypher, {"node_id": node_id, "tid": tid}, auth.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph query failed: {e}")

    grouped = {}
    for row in rows:
        grouped[row["rel_type"]] = {
            "count": row["count"],
            "nodes": row.get("nodes", []),
        }

    return {
        "node_id":  node_id,
        "related":  grouped,
        "rel_count":sum(v["count"] for v in grouped.values()),
    }


# ── Graph diff (snapshot comparison) ─────────────────────────────────────────

@router.get("/diff")
async def graph_diff(
    since_hours: int = Query(default=24, ge=1, le=720),
    limit:       int = Query(default=100, ge=1, le=500),
    auth:        AuthContext = Depends(get_auth_context),
    db:          AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns nodes that appeared or were modified in the last N hours.
    Surfaces what changed since the last scan — new findings, new files, etc.
    """
    backend = await _backend(auth, db)
    tid = str(auth.tenant_id)

    cutoff_query = f"""
    MATCH (n) WHERE n.tenant_id = $tid
      AND n.indexed_at IS NOT NULL
      AND n.indexed_at > datetime() - duration('PT{since_hours}H')
    RETURN labels(n)[0] AS node_type,
           count(n)     AS count,
           collect(DISTINCT {{
             id:          id(n),
             labels:      labels(n),
             name:        coalesce(n.name, n.path, toString(id(n))),
             indexed_at:  n.indexed_at,
             file_category: n.file_category
           }})[..{limit}] AS nodes
    ORDER BY count DESC
    """

    try:
        async with backend:
            rows = await backend.query(cutoff_query, {"tid": tid}, auth.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph query failed: {e}")

    new_findings: list[dict] = []
    by_type: dict[str, int] = {}

    for row in rows:
        nt    = row.get("node_type", "Unknown")
        count = row.get("count", 0)
        by_type[nt] = count
        new_findings.extend(row.get("nodes", []))

    # Sort by indexed_at descending
    new_findings.sort(
        key=lambda n: n.get("indexed_at", "") or "",
        reverse=True,
    )

    return {
        "since_hours":   since_hours,
        "total_new":     sum(by_type.values()),
        "by_type":       by_type,
        "recent_nodes":  new_findings[:limit],
    }


# ── Exposure scoring ───────────────────────────────────────────────────────────

@router.get("/exposure-score/{node_id}")
async def node_exposure_score(
    node_id: str,
    auth:    AuthContext = Depends(get_auth_context),
    db:      AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Compute a composite exposure/risk score for a single node.
    Aggregates: CVE count, secret presence, PII status, EOL status,
    connectivity (how many nodes can reach this one).
    """
    backend = await _backend(auth, db)
    tid = str(auth.tenant_id)

    cypher = """
    MATCH (n) WHERE id(n) = $node_id AND n.tenant_id = $tid
    OPTIONAL MATCH (n) -[:HAS_VULNERABILITY]-> (v:Vulnerability)
    OPTIONAL MATCH (n) <-[in_rels]- ()
    RETURN
      n.contains_secrets   AS has_secrets,
      n.pii_detected       AS has_pii,
      n.sensitivity_level  AS sensitivity,
      n.eol_status         AS eol_status,
      n.signed             AS signed,
      n.risk_assessment    AS ai_risk,
      count(DISTINCT v)    AS cve_count,
      count(DISTINCT in_rels) AS in_degree,
      coalesce(n.name, n.path, toString(id(n))) AS name
    """

    try:
        async with backend:
            rows = await backend.query(cypher, {"node_id": node_id, "tid": tid}, auth.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph query failed: {e}")

    if not rows:
        raise HTTPException(status_code=404, detail="Node not found")

    row    = rows[0]
    score  = 0.0
    factors = []

    if row.get("has_secrets"):
        score += 30
        factors.append({"factor": "Contains secrets", "weight": 30, "severity": "critical"})
    if row.get("cve_count", 0) > 0:
        cve_w = min(25, row["cve_count"] * 5)
        score += cve_w
        factors.append({"factor": f"{row['cve_count']} CVE(s)", "weight": cve_w, "severity": "high"})
    if row.get("has_pii"):
        pii_w = 20 if row.get("sensitivity") == "high" else 10
        score += pii_w
        factors.append({"factor": "Contains PII", "weight": pii_w, "severity": "high" if pii_w == 20 else "medium"})
    if row.get("eol_status") == "eol":
        score += 15
        factors.append({"factor": "End-of-life software", "weight": 15, "severity": "high"})
    if row.get("signed") is False:
        score += 10
        factors.append({"factor": "Unsigned binary", "weight": 10, "severity": "medium"})
    if row.get("ai_risk") == "high":
        score += 15
        factors.append({"factor": "AI-flagged high risk", "weight": 15, "severity": "high"})

    # Connectivity adds exposure (highly connected nodes = blast radius)
    in_degree = row.get("in_degree", 0) or 0
    if in_degree > 100:
        score += 10
        factors.append({"factor": f"High connectivity ({in_degree} references)", "weight": 10, "severity": "medium"})
    elif in_degree > 20:
        score += 5

    score = min(100, score)

    return {
        "node_id":    node_id,
        "name":       row.get("name", node_id),
        "score":      round(score),
        "label":      _risk_label(score / 100),
        "factors":    sorted(factors, key=lambda f: f["weight"], reverse=True),
        "in_degree":  in_degree,
        "cve_count":  row.get("cve_count", 0),
    }
