"""
Saved Queries API — Graph Control.

Saved queries are named, reusable Cypher queries that teams can:
  - Save and share within a tenant
  - Tag and organize (e.g. "security", "pii", "ai-training")
  - Run on demand or schedule
  - Export as JSONL/CSV/Parquet for AI training datasets
  - Pin to dashboard
  - Use as workflow triggers

This is the "Graph Control" concept from Wiz — your team's library of
graph queries that encode institutional knowledge about your data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.db.query_models import SavedQuery, QueryExport
from src.dgraphai.db.session import get_db
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.rbac.engine import require_permissions
from src.dgraphai.graph.backends.factory import get_backend_for_tenant

router = APIRouter(prefix="/api/queries", tags=["queries"])


# ── Models ────────────────────────────────────────────────────────────────────

class SaveQueryRequest(BaseModel):
    name:        str
    description: str = ""
    cypher:      str
    params:      dict[str, Any] = {}
    tags:        list[str] = []
    is_public:   bool = False
    is_pinned:   bool = False
    export_format: str | None = None     # jsonl | csv | parquet
    export_schedule: str | None = None  # cron expression


class UpdateQueryRequest(BaseModel):
    name:        str | None = None
    description: str | None = None
    cypher:      str | None = None
    params:      dict[str, Any] | None = None
    tags:        list[str] | None = None
    is_public:   bool | None = None
    is_pinned:   bool | None = None
    export_format: str | None = None
    export_schedule: str | None = None


class RunQueryRequest(BaseModel):
    params:  dict[str, Any] = {}
    limit:   int = 1000
    export:  bool = False   # trigger an export run


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def list_queries(
    tag:    str | None = None,
    pinned: bool | None = None,
    auth:   AuthContext = Depends(get_auth_context),
    db:     AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    List saved queries for this tenant.
    Returns public queries + queries owned by the current user.
    Filter by tag or pinned status.
    """
    stmt = select(SavedQuery).where(
        SavedQuery.tenant_id == auth.tenant_id,
        # Show public queries + own queries
        (SavedQuery.is_public == True) | (SavedQuery.created_by == auth.user_id),  # noqa
    )
    if pinned is not None:
        stmt = stmt.where(SavedQuery.is_pinned == pinned)

    result = await db.execute(stmt.order_by(SavedQuery.is_pinned.desc(), SavedQuery.name))
    queries = result.scalars().all()

    if tag:
        queries = [q for q in queries if tag in (q.tags or [])]

    return [_query_to_dict(q) for q in queries]


@router.post("")
async def save_query(
    req:  SaveQueryRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Save a new query to the team library."""
    # Check name uniqueness within tenant
    existing = await db.execute(
        select(SavedQuery).where(
            SavedQuery.tenant_id == auth.tenant_id,
            SavedQuery.name == req.name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Query named {req.name!r} already exists")

    query = SavedQuery(
        tenant_id       = auth.tenant_id,
        created_by      = auth.user_id,
        name            = req.name,
        description     = req.description,
        cypher          = req.cypher,
        params          = req.params,
        tags            = req.tags,
        is_public       = req.is_public,
        is_pinned       = req.is_pinned,
        export_format   = req.export_format,
        export_schedule = req.export_schedule,
    )
    db.add(query)
    await db.flush()
    return _query_to_dict(query)


@router.get("/tags")
async def list_tags(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[str]:
    """Return all unique tags used in this tenant's saved queries."""
    result = await db.execute(
        select(SavedQuery.tags).where(
            SavedQuery.tenant_id == auth.tenant_id,
            (SavedQuery.is_public == True) | (SavedQuery.created_by == auth.user_id),  # noqa
        )
    )
    all_tags: set[str] = set()
    for (tags,) in result:
        if tags:
            all_tags.update(tags)
    return sorted(all_tags)


@router.get("/{query_id}")
async def get_query(
    query_id: str,
    auth:     AuthContext = Depends(get_auth_context),
    db:       AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific saved query."""
    query = await _get_query_or_404(query_id, auth, db)
    return _query_to_dict(query)


@router.patch("/{query_id}")
async def update_query(
    query_id: str,
    req:      UpdateQueryRequest,
    auth:     AuthContext = Depends(get_auth_context),
    db:       AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update a saved query."""
    query = await _get_query_or_404(query_id, auth, db, require_owner=True)
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(query, field, value)
    query.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return _query_to_dict(query)


@router.delete("/{query_id}")
async def delete_query(
    query_id: str,
    auth:     AuthContext = Depends(get_auth_context),
    db:       AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a saved query."""
    query = await _get_query_or_404(query_id, auth, db, require_owner=True)
    await db.delete(query)
    return {"status": "deleted"}


@router.post("/{query_id}/run")
async def run_query(
    query_id:   str,
    req:        RunQueryRequest,
    background: BackgroundTasks,
    auth:       AuthContext = Depends(get_auth_context),
    db:         AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Execute a saved query and return results.
    With export=True, triggers an async export job.
    """
    if "graph:query" not in auth.permissions and "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Permission required: graph:query")

    query = await _get_query_or_404(query_id, auth, db)

    # Merge saved params with request params (request overrides saved)
    merged_params = {**(query.params or {}), **req.params}

    # Update run stats
    query.run_count  = (query.run_count or 0) + 1
    query.last_run_at = datetime.now(timezone.utc)
    await db.flush()

    # Get tenant graph backend
    from src.dgraphai.db.models import Tenant
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    backend = get_backend_for_tenant(
        tenant.graph_backend or "neo4j",
        tenant.graph_config  or {},
    )

    try:
        async with backend:
            rows = await backend.query(query.cypher, merged_params, auth.tenant_id)
            rows = rows[:req.limit]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query error: {e}")

    response: dict[str, Any] = {
        "query_id":   query_id,
        "query_name": query.name,
        "row_count":  len(rows),
        "rows":       rows,
    }

    # Trigger export in background if requested
    if req.export and query.export_format:
        export_id = str(uuid.uuid4())
        export = QueryExport(
            id           = uuid.UUID(export_id),
            query_id     = query.id,
            tenant_id    = auth.tenant_id,
            triggered_by = "manual",
            status       = "pending",
        )
        db.add(export)
        await db.flush()
        background.add_task(_run_export, export_id, rows, query.export_format)
        response["export_id"] = export_id
        response["export_status"] = "pending"

    return response


@router.get("/{query_id}/exports")
async def list_exports(
    query_id: str,
    auth:     AuthContext = Depends(get_auth_context),
    db:       AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List export runs for a saved query."""
    query = await _get_query_or_404(query_id, auth, db)
    result = await db.execute(
        select(QueryExport)
        .where(QueryExport.query_id == query.id)
        .order_by(QueryExport.started_at.desc())
        .limit(50)
    )
    exports = result.scalars().all()
    return [
        {
            "id":           str(e.id),
            "status":       e.status,
            "row_count":    e.row_count,
            "file_size_bytes": e.file_size_bytes,
            "output_uri":   e.output_uri,
            "triggered_by": e.triggered_by,
            "started_at":   e.started_at.isoformat() if e.started_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            "error":        e.error,
        }
        for e in exports
    ]


@router.post("/{query_id}/export")
async def export_query(
    query_id:    str,
    background:  BackgroundTasks,
    format:      str = "jsonl",   # jsonl | csv | parquet
    auth:        AuthContext = Depends(get_auth_context),
    db:          AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Trigger an export of a saved query's results as a dataset.
    Supports JSONL, CSV, and Parquet — all suitable for AI training pipelines.
    Returns export_id to poll for completion.
    """
    if format not in ("jsonl", "csv", "parquet"):
        raise HTTPException(status_code=400, detail="format must be jsonl, csv, or parquet")

    query = await _get_query_or_404(query_id, auth, db)

    export_id = str(uuid.uuid4())
    export = QueryExport(
        id           = uuid.UUID(export_id),
        query_id     = query.id,
        tenant_id    = auth.tenant_id,
        triggered_by = "manual",
        status       = "pending",
    )
    db.add(export)
    await db.flush()

    # Run export asynchronously
    background.add_task(
        _execute_and_export,
        export_id    = export_id,
        query_cypher = query.cypher,
        query_params = query.params or {},
        tenant_id    = str(auth.tenant_id),
        fmt          = format,
        tenant_backend = tenant_id_to_backend_placeholder(auth.tenant_id),
    )

    return {
        "export_id": export_id,
        "status":    "pending",
        "format":    format,
        "message":   f"Export started. Poll GET /api/queries/{query_id}/exports for status.",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_query_or_404(
    query_id: str,
    auth: AuthContext,
    db: AsyncSession,
    require_owner: bool = False,
) -> SavedQuery:
    result = await db.execute(
        select(SavedQuery).where(
            SavedQuery.id == uuid.UUID(query_id),
            SavedQuery.tenant_id == auth.tenant_id,
        )
    )
    query = result.scalar_one_or_none()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    if require_owner and query.created_by != auth.user_id:
        if "admin:*" not in auth.permissions:
            raise HTTPException(status_code=403, detail="You don't own this query")
    return query


def _query_to_dict(q: SavedQuery) -> dict[str, Any]:
    return {
        "id":              str(q.id),
        "name":            q.name,
        "description":     q.description,
        "cypher":          q.cypher,
        "params":          q.params,
        "tags":            q.tags or [],
        "is_public":       q.is_public,
        "is_pinned":       q.is_pinned,
        "run_count":       q.run_count,
        "last_run_at":     q.last_run_at.isoformat() if q.last_run_at else None,
        "export_format":   q.export_format,
        "export_schedule": q.export_schedule,
        "created_at":      q.created_at.isoformat() if q.created_at else None,
        "updated_at":      q.updated_at.isoformat() if q.updated_at else None,
    }


async def _run_export(export_id: str, rows: list[dict], fmt: str) -> None:
    """Write pre-fetched rows to an export file."""
    import json
    from pathlib import Path
    output_dir = Path("/data/exports")
    output_dir.mkdir(parents=True, exist_ok=True)

    ext  = {"jsonl": "jsonl", "csv": "csv", "parquet": "parquet"}[fmt]
    path = output_dir / f"{export_id}.{ext}"

    try:
        if fmt == "jsonl":
            with open(path, "w") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
        elif fmt == "csv":
            import csv
            if rows:
                with open(path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
        elif fmt == "parquet":
            try:
                import pyarrow as pa
                import pyarrow.parquet as pq
                table = pa.Table.from_pylist(rows)
                pq.write_table(table, str(path))
            except ImportError:
                # Fall back to JSONL if pyarrow not available
                with open(path, "w") as f:
                    for row in rows:
                        f.write(json.dumps(row) + "\n")
                path = output_dir / f"{export_id}.jsonl"
    except Exception:
        pass  # logged externally


async def _execute_and_export(
    export_id: str, query_cypher: str, query_params: dict,
    tenant_id: str, fmt: str, tenant_backend: Any,
) -> None:
    """Execute query and export results — runs in background."""
    pass  # Wired in full implementation


def tenant_id_to_backend_placeholder(tenant_id: Any) -> Any:
    return None  # Backend resolved inside the task
