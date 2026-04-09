"""
Connector base class for the scanner agent.
Each connector knows how to walk a specific filesystem type
and produce NodeDelta / EdgeDelta objects.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from src.sync.client import SyncClient


class FileRecord:
    """Minimal file record produced by a connector scan."""
    __slots__ = ("path", "name", "size_bytes", "modified", "sha256",
                 "suffix", "is_dir", "host", "share")

    def __init__(self, **kw: Any) -> None:
        for k, v in kw.items():
            setattr(self, k, v)

    def to_node_dict(self, connector_id: str) -> dict[str, Any]:
        return {
            "op":   "upsert",
            "type": "Directory" if self.is_dir else "File",
            "id":   self._stable_id(),
            "props": {
                "path":         self.path,
                "name":         self.name,
                "size_bytes":   self.size_bytes if not self.is_dir else 0,
                "modified":     self.modified,
                "sha256":       self.sha256 or "",
                "extension":    self.suffix,
                "host":         self.host or "",
                "share":        self.share or "",
                "connector_id": connector_id,
            },
        }

    def _stable_id(self) -> str:
        key = f"{self.host}:{self.share}:{self.path}"
        return hashlib.sha256(key.encode()).hexdigest()[:24]

    def parent_edge(self) -> dict[str, Any] | None:
        """Edge from this file to its parent directory."""
        parent_path = str(Path(self.path).parent)
        if parent_path == self.path:
            return None
        parent_key = f"{self.host}:{self.share}:{parent_path}"
        parent_id  = hashlib.sha256(parent_key.encode()).hexdigest()[:24]
        return {
            "op":   "upsert",
            "type": "CHILD_OF",
            "from": self._stable_id(),
            "to":   parent_id,
            "props": {},
        }


class BaseConnector(ABC):
    """Abstract filesystem connector."""

    def __init__(self, connector_id: str, uri: str, options: dict[str, Any]) -> None:
        self.connector_id = connector_id
        self.uri          = uri
        self.options      = options

    @abstractmethod
    async def walk(self) -> AsyncIterator[FileRecord]:
        """Yield FileRecord objects for every file in the source."""
        ...

    async def scan_and_sync(
        self,
        sync_client: SyncClient,
        job_id: str,
        batch_size: int = 500,
    ) -> dict[str, Any]:
        """
        Walk the filesystem and stream delta chunks to the backend.
        Returns summary stats.
        """
        nodes:  list[dict[str, Any]] = []
        edges:  list[dict[str, Any]] = []
        total_files = 0
        total_errors = 0
        chunk_index = 0

        async for record in self.walk():
            try:
                nodes.append(record.to_node_dict(self.connector_id))
                edge = record.parent_edge()
                if edge:
                    edges.append(edge)
                total_files += 1

                # Flush batch when full
                if len(nodes) >= batch_size:
                    await sync_client.send_delta(
                        job_id=job_id,
                        nodes=nodes,
                        edges=edges,
                        total_files=total_files,
                    )
                    nodes = []
                    edges = []
                    chunk_index += 1

            except Exception as e:
                total_errors += 1

        # Send final batch
        if nodes or edges:
            await sync_client.send_delta(
                job_id=job_id,
                nodes=nodes,
                edges=edges,
                total_files=total_files,
                errors=total_errors,
            )

        return {
            "total_files":  total_files,
            "total_errors": total_errors,
            "chunks_sent":  chunk_index + 1,
        }
