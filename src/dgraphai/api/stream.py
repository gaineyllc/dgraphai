"""
Data Streaming API — serve graph query results to AI training pipelines.

RBAC-gated: requires graph:query permission + ai_training_export license feature.

Endpoints:
  GET /api/stream/{query_id}              Stream saved query results
  GET /api/stream/{query_id}/schema       Arrow schema for the dataset
  POST /api/stream/adhoc                  Stream ad-hoc Cypher query results
  GET /api/stream/sources                 List available data sources + routing info

Format negotiation via Accept header or ?format= query param:
  application/x-arrow-stream  → Arrow IPC stream (PyTorch/JAX native)
  application/x-parquet       → Parquet row groups
  application/x-webdataset    → WebDataset tar shards
  application/x-ndjson        → JSONL (Hugging Face fine-tuning)
  text/csv                    → CSV

Source routing via X-Requester-Region header:
  Client sets X-Requester-Region: us-east-1 (or auto-detected from IP)
  Server routes to nearest scanner agent with the requested data.

Hugging Face compatibility:
  GET /api/hf/{query_id}/data/{split}-{shard_index:05d}-of-{total:05d}.parquet
  → Returns a Parquet shard compatible with HF datasets library
  ds = load_dataset("dgraphai/tenant-slug/query-name", streaming=True)
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.api.license import gate_feature
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.query_models import SavedQuery
from src.dgraphai.db.session import get_db
from src.dgraphai.streaming.formats import (
    stream_arrow, stream_csv, stream_jsonl, stream_parquet, stream_webdataset
)
from src.dgraphai.streaming.router import AgentTopology, get_stream_router

router = APIRouter(prefix="/api/stream", tags=["streaming"])

# Format → (content-type, streamer)
FORMATS = {
    "arrow":      ("application/x-arrow-stream",  stream_arrow),
    "parquet":    ("application/x-parquet",        stream_parquet),
    "webdataset": ("application/x-webdataset",     stream_webdataset),
    "jsonl":      ("application/x-ndjson",         stream_jsonl),
    "csv":        ("text/csv",                     stream_csv),
}

ACCEPT_MAP = {
    "application/x-arrow-stream": "arrow",
    "application/x-parquet":      "parquet",
    "application/x-webdataset":   "webdataset",
    "application/x-ndjson":       "jsonl",
    "application/jsonl":          "jsonl",
    "text/csv":                   "csv",
}


def _resolve_format(accept: str | None, fmt_param: str | None) -> str:
    """Resolve output format from Accept header or ?format= param."""
    if fmt_param and fmt_param in FORMATS:
        return fmt_param
    if accept:
        for mime, fmt in ACCEPT_MAP.items():
            if mime in accept:
                return fmt
    return "jsonl"  # safe default


@router.get("/sources")
async def list_sources(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    """
    List available data sources and their routing information.
    Shows scanner agents, their regions, and estimated bandwidth.
    Used by training jobs to choose the closest source explicitly.
    """
    router_inst = get_stream_router()
    topology    = router_inst._topology

    return {
        "sources": [
            {
                "agent_id":    t.agent_id,
                "region":      t.region,
                "datacenter":  t.datacenter,
                "is_online":   t.is_online,
                "bandwidth_mbps": t.bandwidth_mbps,
                "connectors":  t.indexed_connectors,
                # Never expose internal IPs or auth details
            }
            for t in topology.values()
            if t.is_online
        ],
        "routing_hint": (
            "Set X-Requester-Region header to your cloud region "
            "(e.g. us-east-1) for optimal source routing."
        ),
    }


@router.get("/{query_id}/schema")
async def get_stream_schema(
    query_id: str,
    auth:     AuthContext = Depends(get_auth_context),
    db:       AsyncSession = Depends(get_db),
    _:        None = Depends(gate_feature("ai_training_export")),
) -> dict[str, Any]:
    """
    Return the Arrow schema for a saved query's output.
    Clients use this to set up DataLoaders before streaming.
    """
    query = await _get_query(query_id, auth, db)

    # Run a 1-row sample to infer schema
    rows = await _execute_query(query, auth, limit=1)
    if not rows:
        return {"schema": [], "row_count_estimate": 0}

    import pyarrow as pa
    table = pa.Table.from_pylist(rows)
    schema = [
        {"name": field.name, "type": str(field.type)}
        for field in table.schema
    ]
    return {"schema": schema, "sample_row": rows[0]}


@router.get("/{query_id}")
async def stream_query(
    query_id:         str,
    request:          Request,
    format:           str | None = Query(default=None),
    batch_size:       int = Query(default=1000, ge=1, le=100_000),
    limit:            int = Query(default=-1, ge=-1),   # -1 = all
    x_requester_region: str | None = Header(default=None),
    auth:             AuthContext = Depends(get_auth_context),
    db:               AsyncSession = Depends(get_db),
    _:                None = Depends(gate_feature("ai_training_export")),
) -> StreamingResponse:
    """
    Stream a saved query's results as a training dataset.

    Supports format negotiation via Accept header or ?format= param.
    Uses source routing to select the nearest scanner agent with the data.

    Usage examples:

    PyTorch / PyArrow:
      import pyarrow as pa
      import httpx
      with httpx.stream("GET", url, headers={"Accept": "application/x-arrow-stream"}) as r:
          reader = pa.ipc.open_stream(r)
          for batch in reader:
              process(batch)

    Hugging Face datasets:
      from datasets import load_dataset
      ds = load_dataset("dgraphai/...", streaming=True)

    pandas:
      import pandas as pd
      df = pd.read_json(url + "?format=jsonl", lines=True)
    """
    if "graph:query" not in auth.permissions and "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Permission required: graph:query")

    query = await _get_query(query_id, auth, db)

    accept     = request.headers.get("Accept")
    fmt        = _resolve_format(accept, format)
    content_type, streamer = FORMATS[fmt]

    # Source routing
    requester_region = x_requester_region or "unknown"
    stream_router    = get_stream_router()
    source = stream_router.select_source(
        connector_ids    = [],  # will be derived from query metadata
        requester_region = requester_region,
    )

    async def row_generator() -> AsyncIterator[dict[str, Any]]:
        rows = await _execute_query(query, auth, limit=limit if limit > 0 else 100_000)
        for row in rows:
            yield row

    return StreamingResponse(
        streamer(row_generator(), batch_size=batch_size)
        if fmt in ("arrow", "parquet", "webdataset")
        else streamer(row_generator()),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{query.name}.{fmt}"',
            "X-Source-Agent":      source.agent_id if source else "direct",
            "X-Source-Region":     source.region   if source else "direct",
            "X-Query-Name":        query.name,
            "X-Tenant-Id":         str(auth.tenant_id),
            "Cache-Control":       "no-store",
        },
    )


class AdhocStreamRequest(BaseModel):
    cypher:          str
    params:          dict[str, Any] = {}
    format:          str = "jsonl"
    limit:           int = 10_000
    requester_region: str = "unknown"


@router.post("/adhoc")
async def stream_adhoc(
    req:  AdhocStreamRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
    _:    None = Depends(gate_feature("ai_training_export")),
) -> StreamingResponse:
    """
    Stream ad-hoc Cypher query results as a training dataset.
    Same format support as saved query streaming.
    Results are not persisted.
    """
    if "graph:query" not in auth.permissions and "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Permission required: graph:query")

    if req.format not in FORMATS:
        raise HTTPException(status_code=400, detail=f"Unknown format: {req.format}")

    from src.dgraphai.db.models import Tenant
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant
    import uuid as _uuid

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})

    async def row_gen() -> AsyncIterator[dict[str, Any]]:
        async with backend:
            rows = await backend.query(req.cypher, req.params, auth.tenant_id)
            for row in rows[:req.limit]:
                yield row

    content_type, streamer = FORMATS[req.format]
    return StreamingResponse(
        streamer(row_gen()),
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


# ── Hugging Face compatible endpoint ──────────────────────────────────────────

hf_router = APIRouter(prefix="/api/hf", tags=["huggingface"])


@hf_router.get("/{tenant_slug}/{query_name}/data/{filename}")
async def hf_parquet_shard(
    tenant_slug: str,
    query_name:  str,
    filename:    str,
    auth:        AuthContext = Depends(get_auth_context),
    db:          AsyncSession = Depends(get_db),
    _:           None = Depends(gate_feature("ai_training_export")),
) -> StreamingResponse:
    """
    Hugging Face datasets-compatible Parquet shard endpoint.
    Allows: load_dataset("dgraphai/tenant/query-name", streaming=True)

    Filename format: {split}-{shard:05d}-of-{total:05d}.parquet
    Currently returns all data as a single shard (shard 0 of 1).
    """
    result = await db.execute(
        select(SavedQuery).where(
            SavedQuery.tenant_id == auth.tenant_id,
            SavedQuery.name == query_name,
        )
    )
    query = result.scalar_one_or_none()
    if not query:
        raise HTTPException(status_code=404, detail="Dataset not found")

    from src.dgraphai.db.models import Tenant
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})

    async def row_gen() -> AsyncIterator[dict[str, Any]]:
        async with backend:
            rows = await backend.query(query.cypher, query.params or {}, auth.tenant_id)
            for row in rows:
                yield row

    return StreamingResponse(
        stream_parquet(row_gen()),
        media_type="application/x-parquet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "public, max-age=3600",
        },
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_query(query_id: str, auth: AuthContext, db: AsyncSession) -> SavedQuery:
    import uuid as _uuid
    result = await db.execute(
        select(SavedQuery).where(
            SavedQuery.id        == _uuid.UUID(query_id),
            SavedQuery.tenant_id == auth.tenant_id,
        )
    )
    query = result.scalar_one_or_none()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    return query


async def _execute_query(
    query: SavedQuery,
    auth: AuthContext,
    limit: int = 100_000,
) -> list[dict[str, Any]]:
    from sqlalchemy import select as _select
    from src.dgraphai.db.models import Tenant
    from src.dgraphai.db.session import AsyncSessionLocal
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant

    async with AsyncSessionLocal() as db:
        result = await db.execute(_select(Tenant).where(Tenant.id == auth.tenant_id))
        tenant = result.scalar_one_or_none()

    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})
    async with backend:
        rows = await backend.query(query.cypher, query.params or {}, auth.tenant_id)
    return rows[:limit] if limit > 0 else rows
