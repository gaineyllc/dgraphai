"""
Mount manager — add, remove, list filesystem sources.
Persists mount configurations to ~/.fsgraph/mounts.json.
Supports: local paths, SMB (smb://), NFS (nfs://)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.fsgraph.core.config import data_dir


def _mounts_file() -> Path:
    return data_dir() / "mounts.json"


def _load() -> list[dict[str, Any]]:
    f = _mounts_file()
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text())
    except Exception:
        return []


def _save(mounts: list[dict[str, Any]]) -> None:
    _mounts_file().write_text(json.dumps(mounts, indent=2))


class MountManager:
    """
    Manages filesystem mount configurations.
    A "mount" is a named source URI that fsgraph can index.
    """

    def list_mounts(self) -> list[dict[str, Any]]:
        """Return all configured mounts with status."""
        mounts = _load()
        # Enrich with live reachability status
        for m in mounts:
            m["reachable"] = self._check_reachable(m["uri"])
        return mounts

    def add_mount(
        self,
        name: str,
        uri: str,
        credentials: dict[str, str] | None = None,
        auto_index: bool = True,
    ) -> dict[str, Any]:
        """
        Add a new mount source.

        Args:
            name:        Human-readable label
            uri:         Source URI — local path, smb://user:pass@host/share, nfs://host/export
            credentials: Optional {username, password} stored separately from URI
            auto_index:  Whether to include in scheduled indexing runs
        """
        mounts = _load()

        # Validate URI format
        parsed = self._parse_uri(uri)
        if not parsed["valid"]:
            raise ValueError(f"Invalid URI: {uri}. Expected local path, smb://, or nfs://")

        mount: dict[str, Any] = {
            "id":          str(uuid.uuid4()),
            "name":        name,
            "uri":         uri,
            "protocol":    parsed["protocol"],
            "host":        parsed.get("host", ""),
            "auto_index":  auto_index,
            "created_at":  datetime.utcnow().isoformat(),
            "last_indexed": None,
            "index_status": "never",
            "file_count":   0,
        }
        mounts.append(mount)
        _save(mounts)
        return mount

    def remove_mount(self, mount_id: str) -> bool:
        """Remove a mount by ID. Returns True if found and removed."""
        mounts = _load()
        before = len(mounts)
        mounts = [m for m in mounts if m["id"] != mount_id]
        if len(mounts) == before:
            return False
        _save(mounts)
        return True

    def get_mount(self, mount_id: str) -> dict[str, Any] | None:
        """Get a specific mount by ID."""
        return next((m for m in _load() if m["id"] == mount_id), None)

    def update_index_status(
        self, mount_id: str, status: str, file_count: int | None = None
    ) -> None:
        """Update indexing status for a mount after a scan."""
        mounts = _load()
        for m in mounts:
            if m["id"] == mount_id:
                m["index_status"] = status
                m["last_indexed"] = datetime.utcnow().isoformat()
                if file_count is not None:
                    m["file_count"] = file_count
                break
        _save(mounts)

    def _parse_uri(self, uri: str) -> dict[str, Any]:
        """Parse and validate a source URI."""
        from urllib.parse import urlparse
        import re

        # Windows drive letter (C:\, F:\)
        if re.match(r'^[A-Za-z]:[/\\]', uri):
            return {"valid": True, "protocol": "local"}

        # Unix absolute path
        if uri.startswith("/"):
            return {"valid": True, "protocol": "local"}

        parsed = urlparse(uri)
        scheme = parsed.scheme.lower()

        if scheme == "smb":
            return {
                "valid": True,
                "protocol": "smb",
                "host": parsed.hostname or "",
            }
        if scheme == "nfs":
            return {
                "valid": True,
                "protocol": "nfs",
                "host": parsed.hostname or "",
            }

        return {"valid": False, "protocol": "unknown"}

    def _check_reachable(self, uri: str) -> bool:
        """Quick reachability check for a mount URI."""
        try:
            parsed = self._parse_uri(uri)
            if parsed["protocol"] == "local":
                from pathlib import Path as P
                return P(uri).exists()
            elif parsed["protocol"] in ("smb", "nfs"):
                import socket
                port = 445 if parsed["protocol"] == "smb" else 2049
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                result = s.connect_ex((parsed.get("host", ""), port))
                s.close()
                return result == 0
        except Exception:
            pass
        return False
