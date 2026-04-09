"""
Global search API.

Falls back gracefully based on what's available:
  1. Meilisearch (if MEILISEARCH_URL configured) — sub-10ms full-text
  2. OpenSearch/Elasticsearch (if OPENSEARCH_URL configured)
  3. Neo4j graph query (always available) — uses CONTAINS which is slow at scale
     but works for <1M nodes without a dedicated search index

Results are returned in a unified format regardless of backend.
Install Meilisearch for production: https://docs.meilisearch.com/learn/getting_started/installation.html
"""
from __future__ import annotations
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.session import get_db

router = APIRouter(prefix="/api/search", tags=["search"])

MEILISEARCH_URL = os.getenv("MEILISEARCH_URL", "")
MEILISEARCH_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "")
OPENSEARCH_URL  = os.getenv("OPENSEARCH_URL", "")


@router.get("")
async def global_search(
    q:     str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=20, le=100),
    types: str = Query(default="",  description="Comma-separated node types to filter"),
    auth:  AuthContext = Depends(get_auth_context),
    db:    AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Search across all node types.
    Returns unified results with highlights for display.
    """
    node_types = [t.strip() for t in types.split(",") if t.strip()] or None

    if MEILISEARCH_URL:
        results = await _search_meilisearch(q, str(auth.tenant_id), limit, node_types)
    elif OPENSEARCH_URL:
        results = await _search_opensearch(q, str(auth.tenant_id), limit, node_types)
    else:
        results = await _search_graph(q, str(auth.tenant_id), limit, node_types, auth, db)

    return {
        "query":   q,
        "results": results,
        "total":   len(results),
        "backend": "meilisearch" if MEILISEARCH_URL else ("opensearch" if OPENSEARCH_URL else "graph"),
    }


async def _search_graph(
    q: str, tenant_id: str, limit: int,
    node_types: list[str] | None,
    auth: AuthContext, db: AsyncSession,
) -> list[dict]:
    """Fallback: graph full-text search via CONTAINS on name/path/summary."""
    from sqlalchemy import select
    from src.dgraphai.db.models import Tenant
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant

    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return []

    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})

    # Sanitize query
    safe_q = re.sub(r"['\"\\\n\r;]", "", q)[:100]

    search_types = node_types or ["File", "Person", "Application", "Vulnerability"]
    all_results  = []

    import asyncio

    async def search_type(node_type: str) -> list[dict]:
        type_limit = max(5, limit // len(search_types))
        cypher = f"""
        MATCH (n:{node_type})
        WHERE n.tenant_id = $tid AND (
          toLower(n.name) CONTAINS toLower($q)
          OR toLower(coalesce(n.path, '')) CONTAINS toLower($q)
          OR toLower(coalesce(n.summary, '')) CONTAINS toLower($q)
          OR toLower(coalesce(n.email, '')) CONTAINS toLower($q)
        )
        RETURN n LIMIT {type_limit}
        """
        try:
            async with backend:
                rows = await backend.query(cypher, {"tid": tenant_id, "q": safe_q}, auth.tenant_id)
                out = []
                for row in rows:
                    node = row.get("n") or next(iter(row.values()), {})
                    if not isinstance(node, dict):
                        continue
                    name = node.get("name") or node.get("email") or node.get("id", "")
                    out.append({
                        "id":        node.get("id", ""),
                        "node_type": node_type,
                        "name":      name,
                        "path":      node.get("path"),
                        "summary":   node.get("summary"),
                        "highlight": _highlight(name, q),
                        "score":     1.0,
                    })
                return out
        except Exception:
            return []

    results_nested = await asyncio.gather(*[search_type(t) for t in search_types])
    for r in results_nested:
        all_results.extend(r)

    # Sort by name match quality (exact > starts with > contains)
    def rank(item):
        n = item["name"].lower()
        q_lower = q.lower()
        if n == q_lower:           return 0
        if n.startswith(q_lower):  return 1
        return 2

    all_results.sort(key=rank)
    return all_results[:limit]


async def _search_meilisearch(q: str, tenant_id: str, limit: int, types: list[str] | None) -> list[dict]:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{MEILISEARCH_URL}/multi-search",
                headers={"Authorization": f"Bearer {MEILISEARCH_KEY}"},
                json={
                    "queries": [
                        {
                            "indexUid":       f"dgraphai_{tenant_id}",
                            "q":              q,
                            "limit":          limit,
                            "attributesToHighlight": ["name", "path", "summary"],
                            "highlightPreTag":  "<em>",
                            "highlightPostTag": "</em>",
                            "filter":         f"node_type IN [{','.join(types)}]" if types else None,
                        }
                    ]
                }
            )
            data = resp.json()
            hits = data.get("results", [{}])[0].get("hits", [])
            return [
                {
                    "id":        h.get("id", ""),
                    "node_type": h.get("node_type", "File"),
                    "name":      h.get("name", ""),
                    "path":      h.get("path"),
                    "summary":   h.get("summary"),
                    "highlight": h.get("_formatted", {}).get("name", h.get("name", "")),
                    "score":     h.get("_rankingScore", 1.0),
                }
                for h in hits
            ]
    except Exception:
        return []


async def _search_opensearch(q: str, tenant_id: str, limit: int, types: list[str] | None) -> list[dict]:
    try:
        import httpx
        filters = [{"term": {"tenant_id": tenant_id}}]
        if types:
            filters.append({"terms": {"node_type": types}})

        body = {
            "size": limit,
            "query": {
                "bool": {
                    "must": {"multi_match": {"query": q, "fields": ["name^3", "path^2", "summary", "email^2"], "fuzziness": "AUTO"}},
                    "filter": filters,
                }
            },
            "highlight": {"fields": {"name": {}, "summary": {}}},
        }
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(f"{OPENSEARCH_URL}/dgraphai/_search", json=body)
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            return [
                {
                    "id":        h["_source"].get("id", h["_id"]),
                    "node_type": h["_source"].get("node_type", "File"),
                    "name":      h["_source"].get("name", ""),
                    "path":      h["_source"].get("path"),
                    "summary":   h["_source"].get("summary"),
                    "highlight": (h.get("highlight", {}).get("name", [h["_source"].get("name", "")])[0]),
                    "score":     h.get("_score", 1.0),
                }
                for h in hits
            ]
    except Exception:
        return []


def _highlight(text: str, query: str) -> str:
    """Wrap query matches in <em> tags for display highlighting."""
    if not text or not query:
        return text
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    return pattern.sub(lambda m: f"<em>{m.group()}</em>", text)
