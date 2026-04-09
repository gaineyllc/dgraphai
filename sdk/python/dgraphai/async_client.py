"""Async version of the dgraph.ai SDK (httpx AsyncClient)."""
from __future__ import annotations
import os
from typing import Any
import httpx


class AsyncDGraphAI:
    """Async SDK client for use with asyncio/FastAPI/aiohttp applications."""

    def __init__(
        self,
        api_key:   str | None = None,
        tenant_id: str | None = None,
        base_url:  str = "https://api.dgraph.ai",
        timeout:   float = 30.0,
    ):
        self.api_key   = api_key   or os.getenv("DGRAPHAI_API_KEY", "")
        self.tenant_id = tenant_id or os.getenv("DGRAPHAI_TENANT_ID", "")
        self.base_url  = base_url.rstrip("/")

        if not self.api_key:
            raise ValueError("api_key is required")

        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "X-Tenant-ID":   self.tenant_id,
                "User-Agent":    "dgraphai-python/0.1.0",
            },
            timeout=timeout,
        )

    async def close(self):
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def query(self, cypher: str, params: dict | None = None, limit: int = 100) -> list[dict]:
        r = await self._http.post("/api/graph/query", json={"cypher": cypher, "params": params or {}, "limit": limit})
        r.raise_for_status()
        return r.json().get("rows", [])

    async def search(self, q: str, limit: int = 20) -> list[dict]:
        r = await self._http.get("/api/search", params={"q": q, "limit": limit})
        r.raise_for_status()
        return r.json().get("results", [])

    async def inventory(self) -> dict:
        r = await self._http.get("/api/inventory")
        r.raise_for_status()
        return r.json()

    async def usage(self) -> dict:
        r = await self._http.get("/api/usage/snapshot")
        r.raise_for_status()
        return r.json()

    async def attack_path(self, from_id: str, to_id: str) -> dict:
        r = await self._http.get("/api/graph/intel/attack-path",
                                  params={"from_id": from_id, "to_id": to_id})
        r.raise_for_status()
        return r.json()
