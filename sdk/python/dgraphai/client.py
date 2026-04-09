"""
dgraph.ai Python SDK — official client library.

Install: pip install dgraphai

Usage:
    from dgraphai import DGraphAI

    client = DGraphAI(api_key="dg_...", tenant_id="...")

    # Query the graph
    results = client.graph.query("MATCH (f:File) WHERE f.pii_detected = true RETURN f LIMIT 10")

    # Search
    results = client.search("4K videos with HDR")

    # Inventory
    categories = client.inventory.list()
    files = client.inventory.category("video-mkv").nodes(limit=100)

    # Usage
    usage = client.usage.snapshot()
    print(f"Total nodes: {usage.total_nodes}")
    print(f"Estimated cost: ${usage.cost.total:.2f}/mo")
"""
from __future__ import annotations
import os
from typing import Any

import httpx


class DGraphAI:
    """Main SDK client."""

    def __init__(
        self,
        api_key:    str | None = None,
        tenant_id:  str | None = None,
        base_url:   str = "https://api.dgraph.ai",
        timeout:    float = 30.0,
    ):
        self.api_key   = api_key   or os.getenv("DGRAPHAI_API_KEY", "")
        self.tenant_id = tenant_id or os.getenv("DGRAPHAI_TENANT_ID", "")
        self.base_url  = base_url.rstrip("/")

        if not self.api_key:
            raise ValueError("api_key is required (or set DGRAPHAI_API_KEY env var)")
        if not self.tenant_id:
            raise ValueError("tenant_id is required (or set DGRAPHAI_TENANT_ID env var)")

        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "X-Tenant-ID":   self.tenant_id,
                "User-Agent":    "dgraphai-python/0.1.0",
            },
            timeout=timeout,
        )

        # Sub-clients
        self.graph     = GraphClient(self._http)
        self.inventory = InventoryClient(self._http)
        self.search    = SearchClient(self._http)
        self.usage     = UsageClient(self._http)
        self.connectors= ConnectorsClient(self._http)
        self.audit     = AuditClient(self._http)

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class GraphClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def query(self, cypher: str, params: dict | None = None, limit: int = 100) -> list[dict]:
        """Run a Cypher query against the knowledge graph."""
        r = self._http.post("/api/graph/query", json={
            "cypher": cypher,
            "params": params or {},
            "limit":  limit,
        })
        r.raise_for_status()
        return r.json().get("rows", [])

    def attack_path(self, from_id: str, to_id: str, max_hops: int = 6) -> dict:
        """Find attack paths between two graph nodes."""
        r = self._http.get("/api/graph/intel/attack-path", params={
            "from_id": from_id, "to_id": to_id, "max_hops": max_hops,
        })
        r.raise_for_status()
        return r.json()

    def neighborhood(self, node_id: str, hops: int = 1) -> dict:
        """Get all nodes within N hops of a given node."""
        r = self._http.get("/api/graph/intel/neighborhood", params={
            "node_id": node_id, "hops": hops,
        })
        r.raise_for_status()
        return r.json()

    def exposure_score(self, node_id: str) -> dict:
        """Get the exposure/risk score for a node."""
        r = self._http.get(f"/api/graph/intel/exposure-score/{node_id}")
        r.raise_for_status()
        return r.json()

    def diff(self, since_hours: int = 24) -> dict:
        """Get nodes that changed in the last N hours."""
        r = self._http.get("/api/graph/intel/diff", params={"since_hours": since_hours})
        r.raise_for_status()
        return r.json()


class InventoryClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def list(self) -> dict:
        """List all inventory categories with node counts."""
        r = self._http.get("/api/inventory")
        r.raise_for_status()
        return r.json()

    def category(self, category_id: str) -> "CategoryClient":
        return CategoryClient(self._http, category_id)

    def search(self, query: str) -> dict:
        """Natural language search for a data category."""
        r = self._http.get("/api/inventory/search", params={"q": query})
        r.raise_for_status()
        return r.json()


class CategoryClient:
    def __init__(self, http: httpx.Client, category_id: str):
        self._http = http
        self._id   = category_id

    def info(self) -> dict:
        r = self._http.get(f"/api/inventory/{self._id}")
        r.raise_for_status()
        return r.json()

    def nodes(self, page: int = 0, limit: int = 25) -> list[dict]:
        r = self._http.get(f"/api/inventory/{self._id}", params={"page": page, "page_size": limit})
        r.raise_for_status()
        return r.json().get("nodes", [])

    def filtered_nodes(self, filters: list[dict], page: int = 0, limit: int = 25) -> dict:
        """Get nodes matching attribute filters. filters = [{field, op, value}]"""
        r = self._http.post(
            f"/api/inventory/{self._id}/filtered",
            json={"filters": filters},
            params={"page": page, "page_size": limit},
        )
        r.raise_for_status()
        return r.json()


class SearchClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def __call__(self, query: str, limit: int = 20, types: list[str] | None = None) -> list[dict]:
        """Search across all node types."""
        params: dict[str, Any] = {"q": query, "limit": limit}
        if types:
            params["types"] = ",".join(types)
        r = self._http.get("/api/search", params=params)
        r.raise_for_status()
        return r.json().get("results", [])


class UsageClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def snapshot(self) -> dict:
        """Current usage snapshot with cost breakdown."""
        r = self._http.get("/api/usage/snapshot")
        r.raise_for_status()
        return r.json()

    def limits(self) -> dict:
        """Current usage vs plan limits."""
        r = self._http.get("/api/usage/limits")
        r.raise_for_status()
        return r.json()


class ConnectorsClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def list(self) -> list[dict]:
        r = self._http.get("/api/connectors")
        r.raise_for_status()
        return r.json()

    def create(self, name: str, connector_type: str, config: dict,
               routing_mode: str = "auto", tags: list[str] | None = None) -> dict:
        r = self._http.post("/api/connectors", json={
            "name": name, "connector_type": connector_type,
            "config": config, "routing_mode": routing_mode,
            "tags": tags or [],
        })
        r.raise_for_status()
        return r.json()

    def test(self, connector_id: str) -> dict:
        r = self._http.post(f"/api/connectors/{connector_id}/test")
        r.raise_for_status()
        return r.json()

    def delete(self, connector_id: str) -> None:
        self._http.delete(f"/api/connectors/{connector_id}").raise_for_status()


class AuditClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def list(self, action: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
        r = self._http.get("/api/audit", params={"action": action, "limit": limit, "offset": offset})
        r.raise_for_status()
        return r.json().get("entries", [])
