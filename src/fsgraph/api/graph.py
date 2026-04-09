"""
Graph API routes — Cypher queries, node lookup, neighbor traversal.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.dgraphai.graph.client import GraphClient, get_graph_client

router = APIRouter(prefix="/api/graph", tags=["graph"])


# ── Request/response models ────────────────────────────────────────────────────

class CypherRequest(BaseModel):
    cypher: str
    params: dict[str, Any] = {}


class SearchRequest(BaseModel):
    term: str | None = None
    node_type: str | None = None
    filters: dict[str, Any] = {}
    limit: int = 50


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    client: GraphClient = Depends(get_graph_client),
) -> dict[str, int]:
    """Node and relationship counts for the dashboard overview."""
    return await client.stats()


@router.post("/query")
async def run_query(
    req: CypherRequest,
    client: GraphClient = Depends(get_graph_client),
) -> list[dict[str, Any]]:
    """
    Execute a raw Cypher query against the knowledge graph.
    Returns up to 500 rows.

    Example:
        MATCH (f:File) WHERE f.file_category = 'video' RETURN f.name, f.size_bytes LIMIT 20
    """
    try:
        results = await client.query(req.cypher, req.params)
        return results[:500]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/node/{node_id}")
async def get_node(
    node_id: str,
    client: GraphClient = Depends(get_graph_client),
) -> dict[str, Any]:
    """Fetch a single node by its id property."""
    node = await client.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id!r} not found")
    return node


@router.get("/node/{node_id}/neighbors")
async def get_neighbors(
    node_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    limit: int = Query(default=100, ge=1, le=500),
    client: GraphClient = Depends(get_graph_client),
) -> dict[str, Any]:
    """
    Return a subgraph centered on a node.
    Response format: {nodes: [...], edges: [...]} — ready for Cytoscape.
    """
    return await client.get_neighbors(node_id, depth=depth, limit=limit)


@router.post("/search")
async def search_nodes(
    req: SearchRequest,
    client: GraphClient = Depends(get_graph_client),
) -> list[dict[str, Any]]:
    """
    Search nodes by text, type, or property filters.
    Searches name, path, and summary fields.
    """
    return await client.search(
        term=req.term,
        node_type=req.node_type,
        filters=req.filters,
        limit=req.limit,
    )
