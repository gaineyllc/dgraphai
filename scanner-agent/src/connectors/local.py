"""Local filesystem connector — Windows/Linux/macOS."""
from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncIterator

from .base import BaseConnector, FileRecord

SKIP_DIRS = {"/proc", "/sys", "/dev", "/run"}


class LocalConnector(BaseConnector):
    """Scans a local directory path."""

    async def walk(self) -> AsyncIterator[FileRecord]:
        root = Path(self.uri)
        if not root.exists():
            return

        for dirpath, dirnames, filenames in os.walk(str(root)):
            # Skip pseudo-filesystems
            dirnames[:] = [
                d for d in dirnames
                if os.path.join(dirpath, d) not in SKIP_DIRS
            ]

            # Yield directory node
            yield FileRecord(
                path=dirpath, name=Path(dirpath).name,
                size_bytes=0, modified=os.path.getmtime(dirpath),
                sha256=None, suffix="", is_dir=True, host="", share="",
            )

            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                try:
                    stat = os.stat(fpath)
                    yield FileRecord(
                        path=fpath, name=fname,
                        size_bytes=stat.st_size,
                        modified=stat.st_mtime,
                        sha256=None,  # hashed on-demand for dedup
                        suffix=Path(fname).suffix.lower(),
                        is_dir=False, host="", share="",
                    )
                except (PermissionError, OSError):
                    pass
