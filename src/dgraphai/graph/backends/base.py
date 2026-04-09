"""
Graph backend abstraction.
Every backend must implement this interface.
Tenant isolation is enforced at this layer — queries are always scoped.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class GraphBackend(ABC):
    """Abstract graph database backend."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def query(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        tenant_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a Cypher query.
        tenant_id is used to enforce row-level isolation where the backend
        supports it (e.g. Neptune uses named graphs per tenant).
        """
        ...

    @abstractmethod
    async def upsert_node(
        self,
        node_type: str,
        node_id: str,
        props: dict[str, Any],
        tenant_id: UUID,
    ) -> None: ...

    @abstractmethod
    async def upsert_rel(
        self,
        rel_type: str,
        from_id: str,
        to_id: str,
        props: dict[str, Any],
        tenant_id: UUID,
    ) -> None: ...

    @abstractmethod
    async def stats(self, tenant_id: UUID) -> dict[str, int]: ...

    async def __aenter__(self) -> "GraphBackend":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
