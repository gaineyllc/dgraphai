"""
Scanner ↔ Backend sync protocol.

The scanner agent runs on-prem and communicates with the backend
over HTTPS (outbound only — no inbound ports required).

Protocol:
  1. Agent authenticates with API key (rotatable, per-tenant)
  2. Agent polls /api/scanner/jobs for pending scan jobs
  3. Agent scans filesystem, produces GraphDelta
  4. Agent POSTs delta to /api/scanner/sync in chunks
  5. Backend merges delta into the tenant graph
  6. Agent reports completion

GraphDelta format:
  - Only sends what changed since last scan (SHA-256 + mtime comparison)
  - Never sends raw file content — only metadata + enriched attributes
  - Nodes and edges in upsert/delete batches
  - Chunked for large filesystems (configurable batch size)

Security:
  - API key in X-Scanner-Key header (not Authorization — keeps OIDC separate)
  - TLS required in production
  - Delta contains no file content, no credentials, no key material
  - Backend validates tenant_id matches scanner registration
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DeltaOp(str, Enum):
    UPSERT = "upsert"
    DELETE = "delete"


@dataclass
class NodeDelta:
    op:         DeltaOp
    node_type:  str
    node_id:    str
    props:      dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeDelta:
    op:        DeltaOp
    rel_type:  str
    from_id:   str
    to_id:     str
    props:     dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphDelta:
    """
    A batch of graph changes from one scan run.
    Chunked and streamed to the backend — never the whole graph at once.
    """
    scanner_id:    str
    tenant_id:     str
    scan_job_id:   str
    chunk_index:   int
    is_final:      bool
    scanned_at:    str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    nodes: list[NodeDelta] = field(default_factory=list)
    edges: list[EdgeDelta] = field(default_factory=list)

    # Stats for progress reporting
    total_files:   int = 0
    total_nodes:   int = 0
    errors:        int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanner_id":  self.scanner_id,
            "tenant_id":   self.tenant_id,
            "scan_job_id": self.scan_job_id,
            "chunk_index": self.chunk_index,
            "is_final":    self.is_final,
            "scanned_at":  self.scanned_at,
            "stats": {
                "total_files": self.total_files,
                "total_nodes": self.total_nodes,
                "errors":      self.errors,
            },
            "nodes": [
                {"op": n.op, "type": n.node_type, "id": n.node_id, "props": n.props}
                for n in self.nodes
            ],
            "edges": [
                {"op": e.op, "type": e.rel_type, "from": e.from_id, "to": e.to_id, "props": e.props}
                for e in self.edges
            ],
        }


@dataclass
class ScanJob:
    """Job dispatched from backend to scanner agent."""
    job_id:       str
    connector_id: str
    source_uri:   str        # smb://... or /path or nfs://...
    scan_type:    str        # "full" | "incremental"
    options:      dict[str, Any] = field(default_factory=dict)
    # options: enrich_llm, enrich_vision, enrich_faces, min_file_size_bytes, etc.
