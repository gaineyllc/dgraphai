"""
Inventory API — normalized data/technology taxonomy.
Returns category counts and generates shareable query URLs.
"""
from __future__ import annotations
import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.models import Tenant
from src.dgraphai.db.session import get_db
from src.dgraphai.graph.backends.factory import get_backend_for_tenant
from src.dgraphai.inventory.taxonomy import INVENTORY, get_by_group, get_category

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("")
async def list_inventory(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Return inventory categories with live counts.
    Each category includes a query_url that deep-links to QueryWorkspace.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})

    # Get counts for all categories concurrently
    import asyncio

    async def count_category(cat):
        count_cypher = (
            f"MATCH ({cat.count_field}:File) WHERE {cat.count_field}.tenant_id = $tid "
            f"RETURN count({cat.count_field}) AS c"
            if "WHERE" not in cat.cypher
            else cat.cypher.replace("RETURN f", f"RETURN count({cat.count_field}) AS c")
                           .replace("RETURN DISTINCT a AS f", "RETURN count(DISTINCT a) AS c")
                           .replace("RETURN p AS f", "RETURN count(p) AS c")
                           .replace("RETURN fc AS f", "RETURN count(fc) AS c")
                           .replace("UNWIND files AS f RETURN f", "UNWIND files AS f RETURN count(f) AS c")
        )
        try:
            async with backend:
                rows = await backend.query(count_cypher, {"tid": str(auth.tenant_id)}, auth.tenant_id)
                return rows[0]["c"] if rows else 0
        except Exception:
            return None  # None = unknown (not 0)

    counts = await asyncio.gather(*[count_category(cat) for cat in INVENTORY])

    groups = get_by_group()
    result_groups = {}

    count_map = {cat.id: cnt for cat, cnt in zip(INVENTORY, counts)}

    for group_name, cats in groups.items():
        result_groups[group_name] = [
            {
                "id":          cat.id,
                "name":        cat.name,
                "description": cat.description,
                "icon":        cat.icon,
                "color":       cat.color,
                "count":       count_map.get(cat.id),
                "tags":        cat.tags,
                # Deep-link URL that opens QueryWorkspace with this query
                "query_url":   f"/query?q={urllib.parse.quote(cat.cypher)}&category={cat.id}",
                "cypher":      cat.cypher,
            }
            for cat in cats
        ]

    return {
        "groups":     result_groups,
        "total_categories": len(INVENTORY),
    }


@router.get("/{category_id}")
async def get_category_detail(
    category_id: str,
    auth:        AuthContext = Depends(get_auth_context),
    db:          AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific category with its Cypher query and count."""
    cat = get_category(category_id)
    if not cat:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Category {category_id!r} not found")

    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})

    try:
        async with backend:
            rows = await backend.query(cat.cypher, {"tid": str(auth.tenant_id)}, auth.tenant_id)
            count = len(rows)
    except Exception:
        rows = []
        count = None

    return {
        "id":        cat.id,
        "name":      cat.name,
        "description": cat.description,
        "icon":      cat.icon,
        "color":     cat.color,
        "count":     count,
        "cypher":    cat.cypher,
        "query_url": f"/query?q={urllib.parse.quote(cat.cypher)}&category={cat.id}",
        "sample":    rows[:10],
    }
