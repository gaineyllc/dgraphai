"""
Neo4j graph client for dgraphai.
Provides typed query interface over the knowledge graph.
All methods return clean Python dicts — no Neo4j driver objects leak out.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver

from src.dgraphai.core.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


class GraphClient:
    """Async Neo4j client. Use as async context manager or call connect/close."""

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def __aenter__(self) -> "GraphClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    @staticmethod
    def _serialize(val: Any) -> Any:
        """Recursively convert Neo4j types to plain Python types."""
        from neo4j.graph import Node, Relationship, Path
        if isinstance(val, Node):
            return {"id": val.element_id, "labels": list(val.labels), **dict(val)}
        if isinstance(val, Relationship):
            return {"id": val.element_id, "type": val.type, **dict(val)}
        if isinstance(val, Path):
            return {"nodes": [GraphClient._serialize(n) for n in val.nodes],
                    "edges": [GraphClient._serialize(r) for r in val.relationships]}
        if isinstance(val, dict):
            return {k: GraphClient._serialize(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [GraphClient._serialize(v) for v in val]
        return val

    async def query(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results as plain Python dicts."""
        async with self._driver.session() as session:
            result = await session.run(cypher, params or {})
            rows = []
            async for record in result:
                row = {k: self._serialize(v) for k, v in record.items()}
                rows.append(row)
            return rows

    async def query_one(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Execute a Cypher query and return the first result, or None."""
        rows = await self.query(cypher, params)
        return rows[0] if rows else None

    # ── Graph statistics ───────────────────────────────────────────────────────

    async def stats(self, tenant_id: str | None = None) -> dict[str, int]:
        """Return node/relationship counts for the dashboard.
        Uses dynamic label discovery so new node types appear automatically.
        Filters by tenant_id when provided.
        """
        counts: dict[str, int] = {}
        try:
            # Dynamic: count all labels actually present in the graph
            if tenant_id:
                rows = await self.query(
                    "MATCH (n) WHERE n.tenant_id = $tid "
                    "RETURN labels(n)[0] AS label, count(n) AS c",
                    {"tid": tenant_id}
                )
            else:
                rows = await self.query(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS c"
                )
            for row in rows:
                if row.get("label"):
                    counts[row["label"]] = row["c"]
        except Exception:
            pass

        try:
            if tenant_id:
                row = await self.query_one(
                    "MATCH (a)-[r]->(b) WHERE a.tenant_id = $tid RETURN count(r) AS c",
                    {"tid": tenant_id}
                )
            else:
                row = await self.query_one("MATCH ()-[r]->() RETURN count(r) AS c")
            counts["relationships"] = row["c"] if row else 0
        except Exception:
            counts["relationships"] = 0

        return counts

    # ── Node queries ───────────────────────────────────────────────────────────

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Fetch a single node by its id property."""
        return await self.query_one(
            "MATCH (n {id: $id}) RETURN n, labels(n) AS labels",
            {"id": node_id},
        )

    async def get_neighbors(
        self, node_id: str, depth: int = 1, limit: int = 100
    ) -> dict[str, Any]:
        """
        Return a subgraph centered on node_id up to `depth` hops.
        Returns {nodes: [...], edges: [...]} ready for Cytoscape.
        """
        cypher = f"""
            MATCH path = (n {{id: $id}})-[*1..{depth}]-(neighbor)
            WITH nodes(path) AS ns, relationships(path) AS rels
            UNWIND ns AS node
            WITH collect(DISTINCT {{
                id:     node.id,
                label:  labels(node)[0],
                name:   coalesce(node.name, node.title, node.path, node.id),
                props:  properties(node)
            }}) AS nodes, rels
            UNWIND rels AS rel
            WITH nodes, collect(DISTINCT {{
                id:     id(rel),
                source: startNode(rel).id,
                target: endNode(rel).id,
                type:   type(rel)
            }}) AS edges
            RETURN nodes, edges
            LIMIT {limit}
        """
        row = await self.query_one(cypher, {"id": node_id})
        if not row:
            return {"nodes": [], "edges": []}
        return {"nodes": row["nodes"], "edges": row["edges"]}

    # ── Search ─────────────────────────────────────────────────────────────────

    async def search(
        self,
        term: str | None = None,
        node_type: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Flexible node search.
        - term: full-text search across name/path/summary
        - node_type: filter to a specific label
        - filters: {property: value} equality filters
        """
        conditions = []
        params: dict[str, Any] = {}

        label_clause = f":{node_type}" if node_type else ""

        if term:
            conditions.append(
                "(toLower(n.name) CONTAINS toLower($term) OR "
                "toLower(n.path) CONTAINS toLower($term) OR "
                "toLower(n.summary) CONTAINS toLower($term))"
            )
            params["term"] = term

        if filters:
            for k, v in filters.items():
                conditions.append(f"n.{k} = ${k}")
                params[k] = v

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cypher = f"""
            MATCH (n{label_clause})
            {where}
            RETURN n.id AS id, labels(n)[0] AS label,
                   coalesce(n.name, n.path, n.id) AS name,
                   n.summary AS summary,
                   n.file_category AS category,
                   n.size_bytes AS size_bytes
            ORDER BY name
            LIMIT {limit}
        """
        return await self.query(cypher, params)


# ── Singleton ─────────────────────────────────────────────────────────────────

_client: GraphClient | None = None


def get_graph_client() -> GraphClient:
    """Return the application-level graph client (FastAPI dependency)."""
    global _client
    if _client is None:
        _client = GraphClient()
    return _client
