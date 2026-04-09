"""
Scanner sync client — sends GraphDelta chunks to the dgraph.ai backend.
Handles chunking, retry with backoff, and offline queuing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("dgraphai.scanner.sync")

BACKEND_URL  = os.environ.get("DGRAPHAI_BACKEND_URL", "")
API_KEY      = os.environ.get("DGRAPHAI_AGENT_API_KEY", "")
SCANNER_ID   = os.environ.get("DGRAPHAI_SCANNER_ID", "")
TENANT_ID    = os.environ.get("DGRAPHAI_TENANT_ID", "")
CHUNK_SIZE   = int(os.environ.get("DGRAPHAI_CHUNK_SIZE", "500"))

# Offline queue — persisted to disk if backend unreachable
_QUEUE_DIR = Path(os.environ.get("DGRAPHAI_DATA_DIR", "/data")) / "sync_queue"


class SyncClient:
    """
    Sends GraphDelta chunks to the backend.
    Retries with exponential backoff.
    Persists unsent chunks to disk for offline resilience.
    """

    def __init__(
        self,
        backend_url: str = BACKEND_URL,
        api_key:     str = API_KEY,
        scanner_id:  str = SCANNER_ID,
        tenant_id:   str = TENANT_ID,
        chunk_size:  int = CHUNK_SIZE,
    ) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.api_key     = api_key
        self.scanner_id  = scanner_id
        self.tenant_id   = tenant_id
        self.chunk_size  = chunk_size
        _QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Scanner-Key": self.api_key,
            "Content-Type":  "application/json",
            "User-Agent":    f"dgraphai-scanner/{os.environ.get('DGRAPHAI_VERSION', '0.1.0')}",
        }

    async def send_delta(
        self,
        job_id:     str,
        nodes:      list[dict[str, Any]],
        edges:      list[dict[str, Any]],
        total_files: int = 0,
        total_nodes: int = 0,
        errors:      int = 0,
    ) -> dict[str, Any]:
        """
        Send a full GraphDelta to the backend, chunked automatically.
        Returns aggregate result stats.
        """
        # Split into chunks
        node_chunks = _chunks(nodes, self.chunk_size)
        edge_chunks = _chunks(edges, self.chunk_size)
        total_chunks = max(len(node_chunks), len(edge_chunks), 1)

        # Align: pad shorter list with empty chunks
        while len(node_chunks) < total_chunks:
            node_chunks.append([])
        while len(edge_chunks) < total_chunks:
            edge_chunks.append([])

        results = {
            "chunks_sent":  0,
            "nodes_merged": 0,
            "edges_merged": 0,
            "errors":       0,
        }

        for i, (nc, ec) in enumerate(zip(node_chunks, edge_chunks)):
            is_final = (i == total_chunks - 1)
            payload = {
                "scanner_id":  self.scanner_id,
                "tenant_id":   self.tenant_id,
                "scan_job_id": job_id,
                "chunk_index": i,
                "is_final":    is_final,
                "scanned_at":  datetime.now(timezone.utc).isoformat(),
                "stats": {
                    "total_files": total_files,
                    "total_nodes": total_nodes,
                    "errors":      errors,
                },
                "nodes": nc,
                "edges": ec,
            }

            result = await self._send_chunk_with_retry(payload)
            if result:
                results["chunks_sent"]  += 1
                results["nodes_merged"] += result.get("nodes_merged", 0)
                results["edges_merged"] += result.get("edges_merged", 0)
                results["errors"]       += result.get("errors", 0)
            else:
                # Queue for later if all retries failed
                await self._enqueue_chunk(payload)
                results["errors"] += len(nc) + len(ec)

        return results

    async def _send_chunk_with_retry(
        self, payload: dict[str, Any], max_retries: int = 5
    ) -> dict[str, Any] | None:
        """Send a chunk with exponential backoff. Returns None if all retries fail."""
        delay = 2.0
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0, connect=5.0)
                ) as client:
                    resp = await client.post(
                        f"{self.backend_url}/api/scanner/sync",
                        headers=self._headers(),
                        json=payload,
                    )
                    if resp.status_code == 200:
                        return resp.json()
                    if resp.status_code in (400, 403, 422):
                        # Don't retry client errors
                        log.error(f"Sync rejected ({resp.status_code}): {resp.text[:200]}")
                        return None
                    log.warning(f"Sync attempt {attempt+1} got {resp.status_code}, retrying...")
            except httpx.RequestError as e:
                log.warning(f"Sync attempt {attempt+1} network error: {e}, retrying in {delay}s...")

            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

        log.error(f"All {max_retries} sync retries failed for chunk {payload['chunk_index']}")
        return None

    async def _enqueue_chunk(self, payload: dict[str, Any]) -> None:
        """Persist a failed chunk to disk for later retry."""
        fname = _QUEUE_DIR / f"{payload['scan_job_id']}_{payload['chunk_index']}_{int(time.time())}.json"
        fname.write_text(json.dumps(payload))
        log.info(f"Queued chunk to disk: {fname.name}")

    async def flush_queue(self) -> int:
        """Retry all queued chunks. Returns number successfully sent."""
        sent = 0
        for f in sorted(_QUEUE_DIR.glob("*.json")):
            try:
                payload = json.loads(f.read_text())
                result = await self._send_chunk_with_retry(payload, max_retries=3)
                if result:
                    f.unlink()
                    sent += 1
            except Exception as e:
                log.warning(f"Queue flush failed for {f.name}: {e}")
        return sent

    async def heartbeat(self, health: dict[str, Any]) -> bool:
        """Send a heartbeat to the backend. Returns True on success."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.backend_url}/api/scanner/heartbeat",
                    headers=self._headers(),
                    json=health,
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def poll_jobs(self) -> list[dict[str, Any]]:
        """Poll for pending scan jobs from the backend."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.backend_url}/api/scanner/jobs",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return []


def _chunks(lst: list, size: int) -> list[list]:
    """Split a list into chunks of at most `size` items."""
    return [lst[i:i + size] for i in range(0, max(len(lst), 1), size)] if lst else [[]]
