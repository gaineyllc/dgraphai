"""
Inventory API — hierarchical data taxonomy with paginated node browsing.
"""
from __future__ import annotations
import asyncio
import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.models import Tenant
from src.dgraphai.db.session import get_db
from src.dgraphai.graph.backends.factory import get_backend_for_tenant
from src.dgraphai.inventory.taxonomy import (
    INVENTORY, CATEGORY_INDEX, get_by_group, get_category, Column
)

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

PAGE_SIZE = 25


# ── Attribute filter helpers ──────────────────────────────────────────────────

def _apply_attribute_filters(cypher: str, filters: list[dict]) -> str:
    """
    Inject attribute WHERE clauses into a category Cypher query.
    filters: [{field, op, value}]
    Returns the modified Cypher and a human-readable description.
    """
    import re
    if not filters:
        return cypher

    clauses = []
    alias = "f"  # all category Cypherrs use 'f' as the node alias

    for f in filters:
        field = re.sub(r'[^\w]', '', f.get("field", ""))
        op    = f.get("op", "=")
        val   = f.get("value", "")

        if not field:
            continue
        if op in ("IS NULL", "IS NOT NULL"):
            clauses.append(f"{alias}.{field} {op}")
        elif op in ("CONTAINS", "STARTS WITH", "ENDS WITH"):
            safe_val = str(val).replace("'", "\\'")
            clauses.append(f"{alias}.{field} {op} '{safe_val}'")
        elif str(val).lower() in ("true", "false"):
            clauses.append(f"{alias}.{field} {op} {str(val).lower()}")
        else:
            try:
                float(val)
                clauses.append(f"{alias}.{field} {op} {val}")
            except (ValueError, TypeError):
                safe_val = str(val).replace("'", "\\'")
                clauses.append(f"{alias}.{field} {op} '{safe_val}'")

    if not clauses:
        return cypher

    extra = " AND ".join(clauses)
    # Inject into existing WHERE clause or add one before RETURN
    if re.search(r'\bWHERE\b', cypher, re.IGNORECASE):
        cypher = re.sub(
            r'(\bRETURN\b)',
            f'AND {extra} \\1',
            cypher, count=1, flags=re.IGNORECASE
        )
    else:
        cypher = re.sub(
            r'(\bRETURN\b)',
            f'WHERE {extra} \\1',
            cypher, count=1, flags=re.IGNORECASE
        )
    return cypher


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_backend(tenant_id, db):
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})


def _cypher_with_pagination(cypher: str, skip: int, limit: int) -> str:
    """Inject SKIP/LIMIT into a category Cypher query."""
    # Remove any existing LIMIT
    import re
    cypher = re.sub(r'\s+LIMIT\s+\d+', '', cypher, flags=re.IGNORECASE)
    return cypher + f" SKIP {skip} LIMIT {limit}"


def _count_cypher(cypher: str) -> str:
    """Convert a RETURN f query into a COUNT query."""
    import re
    # Strip SKIP/LIMIT
    c = re.sub(r'\s+SKIP\s+\d+', '', cypher, flags=re.IGNORECASE)
    c = re.sub(r'\s+LIMIT\s+\d+', '', c, flags=re.IGNORECASE)
    # Replace RETURN clause
    c = re.sub(r'RETURN\s+DISTINCT\s+\w+\s+AS\s+f', 'RETURN count(DISTINCT f) AS total', c, flags=re.IGNORECASE)
    c = re.sub(r'RETURN\s+\w+\s+AS\s+f', 'RETURN count(f) AS total', c, flags=re.IGNORECASE)
    c = re.sub(r'RETURN\s+f\b', 'RETURN count(f) AS total', c, flags=re.IGNORECASE)
    # Handle duplicate file pattern
    c = re.sub(r'UNWIND files AS f RETURN count\(f\) AS total',
               'UNWIND files AS f RETURN count(f) AS total', c, flags=re.IGNORECASE)
    return c


def _col_dict(col: Column) -> dict:
    return {"key": col.key, "label": col.label, "width": col.width, "kind": col.kind}


def _cat_summary(cat, count=None) -> dict:
    return {
        "id":            cat.id,
        "name":          cat.name,
        "description":   cat.description,
        "icon":          cat.icon,
        "color":         cat.color,
        "tags":          cat.tags,
        "count":         count,
        "has_children":  len(cat.subcategories) > 0,
        "parent_id":     cat.parent_id,
        "query_url":     f"/query?q={urllib.parse.quote(cat.cypher)}&category={cat.id}",
        "columns":       [_col_dict(c) for c in cat.columns],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def list_inventory(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Top-level inventory groups with live counts on every category.
    Returns only top-level items; subcategories are loaded on drill-down.
    """
    backend = await _get_backend(auth.tenant_id, db)
    groups  = get_by_group()

    async def count_cat(cat):
        try:
            cq   = _count_cypher(cat.cypher)
            async with backend:
                rows = await backend.query(cq, {"tid": str(auth.tenant_id)}, auth.tenant_id)
                return rows[0].get("total", 0) if rows else 0
        except Exception:
            return None

    # Flatten all top-level cats across groups for parallel counting
    top_cats = [cat for cats in groups.values() for cat in cats]
    counts   = await asyncio.gather(*[count_cat(c) for c in top_cats])
    count_map = {cat.id: cnt for cat, cnt in zip(top_cats, counts)}

    return {
        "groups": {
            group: [_cat_summary(cat, count_map.get(cat.id)) for cat in cats]
            for group, cats in groups.items()
        },
        "total_categories": len(top_cats),
    }


@router.get("/{category_id}/filterable-attributes")
async def get_filterable_attributes(
    category_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns the attribute fields that make sense to filter on for this
    category, with suggested values sampled from the live graph.
    Used to populate the inline attribute filter panel.
    """
    cat = get_category(category_id)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Category {category_id!r} not found")

    # Return column schema from taxonomy + common ops per type
    filter_fields = []
    for col in cat.columns:
        if col.key in ("name", "path", "source_connector", "modified_at"):
            continue  # skip structural columns — not useful as filters
        ops = _ops_for_kind(col.kind)
        filter_fields.append({
            "key":   col.key,
            "label": col.label,
            "kind":  col.kind,
            "ops":   ops,
        })

    return {"category_id": category_id, "fields": filter_fields}


def _ops_for_kind(kind: str) -> list[str]:
    if kind == "bool":      return ["= true", "= false"]
    if kind == "num":       return ["=", ">", ">=", "<", "<=", "IS NOT NULL", "IS NULL"]
    if kind == "size":      return [">", ">=", "<", "<="]
    if kind == "date":      return [">", ">=", "<", "<=", "IS NOT NULL", "IS NULL"]
    if kind == "badge":     return ["=", "<>", "IS NOT NULL", "IS NULL", "CONTAINS"]
    return ["=", "<>", "CONTAINS", "STARTS WITH", "IS NOT NULL", "IS NULL"]


@router.post("/{category_id}/filtered")
async def get_filtered_nodes(
    category_id: str,
    body:        dict,
    page:        int = Query(default=0, ge=0),
    page_size:   int = Query(default=PAGE_SIZE, ge=1, le=200),
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Run a category query with attribute filters applied.
    body: { filters: [{field, op, value}] }
    Returns filtered nodes + the Cypher query used (for 'View in Graph').
    """
    cat = get_category(category_id)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Category {category_id!r} not found")

    filters   = body.get("filters", [])
    base_cypher = _apply_attribute_filters(cat.cypher, filters)
    tid         = str(auth.tenant_id)
    skip        = page * page_size
    backend     = await _get_backend(auth.tenant_id, db)

    import asyncio as _asyncio
    async def get_count():
        try:
            async with backend:
                rows = await backend.query(_count_cypher(base_cypher), {"tid": tid}, auth.tenant_id)
                return rows[0].get("total", 0) if rows else 0
        except Exception: return None

    async def get_nodes():
        try:
            pq = _cypher_with_pagination(base_cypher, skip, page_size)
            async with backend:
                rows = await backend.query(pq, {"tid": tid}, auth.tenant_id)
                return [_extract_node(r) for r in rows]
        except Exception: return []

    total, nodes = await _asyncio.gather(get_count(), get_nodes())

    return {
        "nodes":     nodes,
        "cypher":    base_cypher,
        "query_url": f"/query?q={urllib.parse.quote(base_cypher)}",
        "pagination": {
            "page":      page,
            "page_size": page_size,
            "total":     total,
            "has_more":  total is not None and (skip + page_size) < total,
        },
        "active_filters": filters,
    }


@router.get("/{category_id}")
async def get_category_detail(
    category_id: str,
    page:        int = Query(default=0, ge=0),
    page_size:   int = Query(default=PAGE_SIZE, ge=1, le=200),
    auth:        AuthContext = Depends(get_auth_context),
    db:          AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Drill into a category:
      - subcategory summaries with counts
      - paginated node list
      - column schema for the table
    """
    cat = get_category(category_id)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Category {category_id!r} not found")

    backend = await _get_backend(auth.tenant_id, db)
    tid     = str(auth.tenant_id)
    skip    = page * page_size

    # Run: total count + page of nodes + subcategory counts — all in parallel
    async def get_total():
        try:
            cq = _count_cypher(cat.cypher)
            async with backend:
                rows = await backend.query(cq, {"tid": tid}, auth.tenant_id)
                return rows[0].get("total", 0) if rows else 0
        except Exception:
            return None

    async def get_nodes():
        try:
            pq = _cypher_with_pagination(cat.cypher, skip, page_size)
            async with backend:
                rows = await backend.query(pq, {"tid": tid}, auth.tenant_id)
                # Extract the node from result row (keyed as 'f' or first value)
                return [_extract_node(r) for r in rows]
        except Exception:
            return []

    async def count_subcat(sc):
        try:
            cq = _count_cypher(sc.cypher)
            async with backend:
                rows = await backend.query(cq, {"tid": tid}, auth.tenant_id)
                return sc.id, rows[0].get("total", 0) if rows else 0
        except Exception:
            return sc.id, None

    tasks = [get_total(), get_nodes()]
    sub_tasks = [count_subcat(sc) for sc in cat.subcategories]

    results    = await asyncio.gather(*tasks)
    sub_counts_list = await asyncio.gather(*sub_tasks)
    sub_counts = dict(sub_counts_list)

    total, nodes = results

    # Build breadcrumb trail
    breadcrumb = _build_breadcrumb(cat)

    return {
        "category":     _cat_summary(cat, total),
        "breadcrumb":   breadcrumb,
        "subcategories": [_cat_summary(sc, sub_counts.get(sc.id)) for sc in cat.subcategories],
        "columns":      [_col_dict(c) for c in cat.columns],
        "nodes":        nodes,
        "pagination": {
            "page":       page,
            "page_size":  page_size,
            "total":      total,
            "has_more":   total is not None and (skip + page_size) < total,
        },
        "query_url":    f"/query?q={urllib.parse.quote(cat.cypher)}&category={cat.id}",
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_node(row: dict) -> dict:
    """Pull the node properties from a result row."""
    # Neo4j returns nodes as dicts; the alias is usually 'f'
    for key in ("f", "a", "p", "fc", "n"):
        if key in row:
            val = row[key]
            if isinstance(val, dict):
                return val
    # Fallback: return flattened row
    return {k: v for k, v in row.items() if not isinstance(v, (dict, list))}


def _build_breadcrumb(cat) -> list[dict]:
    """Walk up the parent chain to build a breadcrumb."""
    from src.dgraphai.inventory.taxonomy import CATEGORY_INDEX
    crumb = []
    current = cat
    while current:
        crumb.insert(0, {"id": current.id, "name": current.name, "icon": current.icon})
        if current.parent_id:
            current = CATEGORY_INDEX.get(current.parent_id)
        else:
            break
    # Prepend root
    crumb.insert(0, {"id": None, "name": "Data Inventory", "icon": "🗄️"})
    return crumb
