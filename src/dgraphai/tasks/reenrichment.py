"""
Re-enrichment queue — queue stale or failed nodes for re-processing.

Nodes are considered stale if:
  - enrichment_status = 'error' (previous attempt failed)
  - enrichment_status = 'pending' and indexed_at > 7 days ago (stuck)
  - summary IS NULL and indexed_at > 1 day ago (never enriched)
  - AI model version has changed (future: version tracking)

The queue is managed via Celery. Workers pull nodes from the queue
and re-run the enrichment pipeline on them.

Admin can also manually queue specific nodes via POST /api/admin/reenrich.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from src.dgraphai.tasks.celery_app import app

log = logging.getLogger("dgraphai.tasks.reenrichment")


@app.task(
    name="dgraphai.tasks.reenrichment.queue_stale_nodes",
    queue="default",
    max_retries=2,
)
def queue_stale_nodes(tenant_id: str | None = None, limit: int = 1000):
    """
    Find stale/failed nodes and queue them for re-enrichment.
    If tenant_id is None, scans all active tenants.
    """
    asyncio.run(_queue_stale_async(tenant_id, limit))


async def _queue_stale_async(tenant_id: str | None, limit: int):
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.models import Tenant
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant
    from sqlalchemy import select

    async with async_session() as db:
        q = select(Tenant).where(Tenant.is_active == True)
        if tenant_id:
            import uuid
            q = q.where(Tenant.id == uuid.UUID(tenant_id))
        result = await db.execute(q)
        tenants = result.scalars().all()

    for tenant in tenants:
        await _queue_tenant_stale(tenant, limit)


async def _queue_tenant_stale(tenant, limit: int):
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant

    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})
    tid = str(tenant.id)

    # Find nodes that need re-enrichment
    find_stale = """
    MATCH (f:File)
    WHERE f.tenant_id = $tid
      AND f.file_category IN ['document', 'code', 'image', 'video', 'audio', 'executable']
      AND (
        f.enrichment_status = 'error'
        OR (f.enrichment_status = 'pending' AND f.indexed_at < datetime() - duration('P7D'))
        OR (f.summary IS NULL AND f.indexed_at < datetime() - duration('P1D'))
      )
    RETURN f.id AS id, f.path AS path, f.file_category AS category
    LIMIT $limit
    """

    try:
        async with backend:
            rows = await backend.query(find_stale, {"tid": tid, "limit": limit}, tenant.id)
    except Exception as e:
        log.error(f"Failed to find stale nodes for tenant {tid}: {e}")
        return

    if not rows:
        log.info(f"Tenant {tid}: no stale nodes found")
        return

    log.info(f"Tenant {tid}: queuing {len(rows)} stale nodes for re-enrichment")

    for row in rows:
        reenrich_node.apply_async(
            args=[str(tenant.id), row.get("id"), row.get("path"), row.get("category")],
            queue="enrichment",
        )


@app.task(
    name="dgraphai.tasks.reenrichment.reenrich_node",
    queue="enrichment",
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=120,
    time_limit=180,
)
def reenrich_node(tenant_id: str, node_id: str, path: str, category: str):
    """
    Re-run AI enrichment on a single file node.
    Marks the node as 'processing' before starting, 'done' or 'error' after.
    """
    asyncio.run(_reenrich_node_async(tenant_id, node_id, path, category))


async def _reenrich_node_async(tenant_id: str, node_id: str, path: str, category: str):
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.models import Tenant
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            return

    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})

    # Mark as processing
    try:
        async with backend:
            await backend.query(
                "MATCH (f:File) WHERE f.id = $id AND f.tenant_id = $tid "
                "SET f.enrichment_status = 'processing'",
                {"id": node_id, "tid": tenant_id}, tenant.id,
            )
    except Exception:
        pass

    success = False
    try:
        # Run category-specific enrichment
        # This is a stub — in production, call the actual enrichment pipeline
        enriched_props = await _run_enrichment(path, category, tenant_id)

        if enriched_props:
            set_clauses = ", ".join(f"f.{k} = ${k}" for k in enriched_props)
            params = {"id": node_id, "tid": tenant_id, **enriched_props}
            async with backend:
                await backend.query(
                    f"MATCH (f:File) WHERE f.id = $id AND f.tenant_id = $tid "
                    f"SET {set_clauses}, f.enrichment_status = 'done'",
                    params, tenant.id,
                )
            success = True

    except Exception as e:
        log.error(f"Re-enrichment failed for node {node_id}: {e}")
        try:
            async with backend:
                await backend.query(
                    "MATCH (f:File) WHERE f.id = $id AND f.tenant_id = $tid "
                    "SET f.enrichment_status = 'error', f.enrichment_error = $err",
                    {"id": node_id, "tid": tenant_id, "err": str(e)[:200]}, tenant.id,
                )
        except Exception:
            pass
        raise

    log.info(f"Re-enriched node {node_id} (category={category}, success={success})")


async def _run_enrichment(path: str, category: str, tenant_id: str) -> dict[str, Any] | None:
    """
    Stub for enrichment pipeline invocation.
    In production, this calls the actual LLM/vision/code enrichers.
    Returns property dict to merge into the node, or None if not applicable.
    """
    # TODO: invoke actual enrichment pipeline
    # This is where we'd call: enrich_document(), enrich_image_vision(), enrich_code()
    # For now return None (no-op) — avoids querying Ollama without a running instance
    return None


# ── Admin API for manual re-enrichment ────────────────────────────────────────

from fastapi import APIRouter, Depends
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


@admin_router.post("/reenrich")
async def trigger_reenrichment(
    body: dict,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """Manually trigger re-enrichment for this tenant."""
    if "admin:*" not in auth.permissions:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin required")

    limit = body.get("limit", 500)
    queue_stale_nodes.apply_async(
        args=[str(auth.tenant_id), limit],
        queue="default",
    )
    return {"status": "queued", "message": f"Re-enrichment queued for up to {limit} stale nodes"}


@admin_router.post("/sync/cve")
async def trigger_cve_sync(
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    """Manually trigger CVE sync from NVD."""
    if "admin:*" not in auth.permissions:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin required")

    from src.dgraphai.tasks.cve_sync import sync_nvd_cves
    sync_nvd_cves.apply_async(args=[14], queue="default")
    return {"status": "queued", "message": "CVE sync queued (last 14 days from NVD)"}
