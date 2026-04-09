"""
Neo4j backend — works with local Neo4j Community/Enterprise and Neo4j AuraDB.
Tenant isolation: all nodes carry a `tenant_id` property.
Queries are automatically scoped by injecting a WHERE tenant_id = $tid clause.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from neo4j import AsyncGraphDatabase, AsyncDriver

from .base import GraphBackend


class Neo4jBackend(GraphBackend):
    """
    Neo4j / AuraDB backend.

    Connection string formats:
      Local:  bolt://localhost:7687
      AuraDB: neo4j+s://xxxxx.databases.neo4j.io
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri      = uri
        self._user     = user
        self._password = password
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def query(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        tenant_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        p = dict(params or {})
        if tenant_id:
            p["__tid"] = str(tenant_id)
            # Inject tenant scope if not already present
            if "__tid" not in cypher and "tenant_id" not in cypher:
                cypher = _inject_tenant_scope(cypher)

        async with self._driver.session() as session:
            result = await session.run(cypher, p)
            return [dict(record) async for record in result]

    async def upsert_node(
        self,
        node_type: str,
        node_id: str,
        props: dict[str, Any],
        tenant_id: UUID,
    ) -> None:
        all_props = {**props, "tenant_id": str(tenant_id)}
        async with self._driver.session() as session:
            await session.run(
                f"MERGE (n:{node_type} {{id: $id, tenant_id: $tenant_id}}) "
                f"SET n += $props",
                {"id": node_id, "tenant_id": str(tenant_id), "props": all_props},
            )

    async def upsert_rel(
        self,
        rel_type: str,
        from_id: str,
        to_id: str,
        props: dict[str, Any],
        tenant_id: UUID,
    ) -> None:
        tid = str(tenant_id)
        async with self._driver.session() as session:
            await session.run(
                f"MATCH (a {{id: $from_id, tenant_id: $tid}}) "
                f"MATCH (b {{id: $to_id,   tenant_id: $tid}}) "
                f"MERGE (a)-[r:{rel_type}]->(b) SET r += $props",
                {"from_id": from_id, "to_id": to_id, "tid": tid, "props": props},
            )

    async def stats(self, tenant_id: UUID) -> dict[str, int]:
        tid = str(tenant_id)
        node_types = [
            "File", "Directory", "Person", "FaceCluster", "Location",
            "Organization", "Topic", "Application", "Vendor",
            "Vulnerability", "Certificate",
        ]
        counts: dict[str, int] = {}
        async with self._driver.session() as session:
            for nt in node_types:
                result = await session.run(
                    f"MATCH (n:{nt} {{tenant_id: $tid}}) RETURN count(n) AS c",
                    {"tid": tid},
                )
                record = await result.single()
                counts[nt] = record["c"] if record else 0

            rel_result = await session.run(
                "MATCH (a {tenant_id: $tid})-[r]->(b {tenant_id: $tid}) "
                "RETURN count(r) AS c",
                {"tid": tid},
            )
            rel_record = await rel_result.single()
            counts["relationships"] = rel_record["c"] if rel_record else 0

        return counts


def _inject_tenant_scope(cypher: str) -> str:
    """
    Best-effort tenant scope injection.
    Adds WHERE n.tenant_id = $__tid to simple MATCH statements.
    Complex queries should include tenant scoping explicitly.
    """
    # Only inject for simple single-MATCH queries
    lines = cypher.strip().split("\n")
    result: list[str] = []
    injected = False
    for line in lines:
        stripped = line.strip().upper()
        if stripped.startswith("MATCH") and not injected:
            result.append(line)
            result.append("WHERE n.tenant_id = $__tid")
            injected = True
        else:
            result.append(line)
    return "\n".join(result)
