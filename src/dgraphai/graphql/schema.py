"""
GraphQL schema for dgraph.ai.
Every piece of platform state is queryable via GraphQL.
The frontend encodes the active GraphQL query in the URL —
so every view is shareable, bookmarkable, and replayable.
"""
from __future__ import annotations
import strawberry
from strawberry.fastapi import GraphQLRouter
from strawberry.scalars import JSON
from strawberry.types import Info
from typing import Optional, Annotated
import urllib.parse


# ── Types ─────────────────────────────────────────────────────────────────────

@strawberry.type
class FileNode:
    id:              str
    name:            str
    path:            str
    size:            Optional[int]   = None
    file_category:   Optional[str]   = None
    mime_type:       Optional[str]   = None
    sha256:          Optional[str]   = None
    pii_detected:    Optional[bool]  = None
    sensitivity_level: Optional[str] = None
    contains_secrets:  Optional[bool] = None
    eol_status:      Optional[str]   = None
    resolution:      Optional[str]   = None
    modified_at:     Optional[str]   = None
    source_connector: Optional[str]  = None


@strawberry.type
class InventoryCategory:
    id:          str
    name:        str
    description: str
    group:       str
    icon:        str
    color:       str
    count:       Optional[int]
    cypher:      str
    query_url:   str


@strawberry.type
class InventoryGroup:
    name:       str
    categories: list[InventoryCategory]


@strawberry.type
class GraphQueryResult:
    nodes: list[JSON]
    edges: list[JSON]
    count: int
    cypher: str
    query_url: str    # deep-link back to QueryWorkspace with this exact query


@strawberry.type
class ConnectorType:
    id:          str
    name:        str
    description: str
    icon:        str
    color:       str


@strawberry.type
class ScannerAgentInfo:
    id:        str
    name:      str
    platform:  str
    is_online: bool
    last_seen: Optional[str]


@strawberry.type
class TenantStats:
    total_files:     int
    total_nodes:     int
    total_edges:     int
    total_size_bytes: Optional[int]
    connector_count: int
    last_indexed_at: Optional[str]


# ── Query ─────────────────────────────────────────────────────────────────────

@strawberry.type
class Query:

    @strawberry.field(description="Run a raw Cypher query against the knowledge graph. Returns nodes, edges, and a deep-link URL.")
    async def graph_query(
        self,
        info: Info,
        cypher:   str,
        params:   Optional[JSON] = None,
        format:   str = "nodes",   # nodes | raw
    ) -> GraphQueryResult:
        ctx     = info.context
        backend = ctx["graph_backend"]
        tid     = ctx["tenant_id"]
        result  = await backend.query(cypher, params or {}, tid)
        nodes, edges = _split_result(result)
        url = "/query?q=" + urllib.parse.quote(cypher)
        return GraphQueryResult(nodes=nodes, edges=edges, count=len(result), cypher=cypher, query_url=url)

    @strawberry.field(description="List all inventory categories with live counts.")
    async def inventory(self, info: Info) -> list[InventoryGroup]:
        from src.dgraphai.inventory.taxonomy import get_by_group
        groups = get_by_group()
        return [
            InventoryGroup(name=g, categories=[
                InventoryCategory(
                    id=c.id, name=c.name, description=c.description,
                    group=c.group, icon=c.icon, color=c.color,
                    count=None,  # counts loaded separately via REST for perf
                    cypher=c.cypher,
                    query_url=f"/query?q={urllib.parse.quote(c.cypher)}&category={c.id}",
                )
                for c in cats
            ])
            for g, cats in groups.items()
        ]

    @strawberry.field(description="Get files matching a named inventory category.")
    async def inventory_category(
        self, info: Info, category_id: str, limit: int = 100
    ) -> GraphQueryResult:
        from src.dgraphai.inventory.taxonomy import get_category
        ctx     = info.context
        backend = ctx["graph_backend"]
        tid     = ctx["tenant_id"]
        cat     = get_category(category_id)
        if not cat:
            raise ValueError(f"Unknown category: {category_id}")
        cypher  = cat.cypher + f" LIMIT {limit}"
        result  = await backend.query(cypher, {"tid": str(tid)}, tid)
        nodes, edges = _split_result(result)
        url = f"/query?q={urllib.parse.quote(cypher)}&category={category_id}"
        return GraphQueryResult(nodes=nodes, edges=edges, count=len(result), cypher=cypher, query_url=url)

    @strawberry.field(description="List available connector types.")
    def connector_types(self, info: Info) -> list[ConnectorType]:
        from src.dgraphai.connectors.sdk import list_connectors
        colors = {"aws-s3": "#f97316", "azure-blob": "#0ea5e9", "gcs": "#3b82f6",
                  "sharepoint": "#10b981", "smb": "#8b5cf6", "nfs": "#6366f1", "local": "#6b7280"}
        icons  = {"aws-s3": "🪣", "azure-blob": "☁️", "gcs": "🔵",
                  "sharepoint": "📁", "smb": "🗄️", "nfs": "📡", "local": "💻"}
        return [
            ConnectorType(id=m.id, name=m.name, description=m.description,
                          icon=icons.get(m.id, "🔌"), color=colors.get(m.id, "#6b7280"))
            for m in list_connectors()
        ]

    @strawberry.field(description="Tenant-level stats: total nodes, files, connectors.")
    async def stats(self, info: Info) -> TenantStats:
        ctx     = info.context
        backend = ctx["graph_backend"]
        tid     = ctx["tenant_id"]
        try:
            rows = await backend.query(
                "MATCH (n) WHERE n.tenant_id = $tid RETURN count(n) AS nodes",
                {"tid": str(tid)}, tid
            )
            total_nodes = rows[0]["nodes"] if rows else 0
            rows2 = await backend.query(
                "MATCH (f:File) WHERE f.tenant_id = $tid RETURN count(f) AS files, sum(f.size) AS sz",
                {"tid": str(tid)}, tid
            )
            total_files = rows2[0]["files"] if rows2 else 0
            total_size  = rows2[0]["sz"]    if rows2 else None
        except Exception:
            total_nodes, total_files, total_size = 0, 0, None
        return TenantStats(
            total_files=total_files, total_nodes=total_nodes,
            total_edges=0, total_size_bytes=total_size,
            connector_count=0, last_indexed_at=None,
        )


# ── Schema + router ───────────────────────────────────────────────────────────

schema = strawberry.Schema(query=Query)


def make_graphql_router(get_context) -> GraphQLRouter:
    """
    Returns a GraphQL router. get_context is an async callable that
    receives the FastAPI Request and returns the strawberry context dict.
    """
    return GraphQLRouter(
        schema,
        context_getter=get_context,
        graphiql=True,   # enable GraphiQL IDE at /graphql
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_result(rows: list[dict]) -> tuple[list, list]:
    """Separate node records from relationship records."""
    nodes, edges = [], []
    for row in rows:
        for v in row.values():
            if isinstance(v, dict):
                if "start" in v and "end" in v:
                    edges.append(v)
                else:
                    nodes.append(v)
    return nodes, edges
