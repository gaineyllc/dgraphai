"""SMB/CIFS connector — wraps smbprotocol."""
from __future__ import annotations

import os
from pathlib import PureWindowsPath
from typing import AsyncIterator
from urllib.parse import urlparse, unquote

from .base import BaseConnector, FileRecord


class SMBConnector(BaseConnector):
    """
    Scans an SMB share.
    URI: smb://user:pass@host/share/subpath
    Credentials can also come from options dict (avoids embedding in URI).
    """

    def _parse(self) -> tuple[str, str, str, str, str]:
        parsed = urlparse(self.uri)
        host   = parsed.hostname or ""
        share  = parsed.path.lstrip("/").split("/")[0]
        subpath = "/".join(parsed.path.lstrip("/").split("/")[1:])
        user   = self.options.get("username") or unquote(parsed.username or "")
        pw     = self.options.get("password") or unquote(parsed.password or "")
        return host, share, subpath, user, pw

    async def walk(self) -> AsyncIterator[FileRecord]:
        try:
            import smbclient
        except ImportError:
            raise RuntimeError("smbprotocol not installed: uv add smbprotocol")

        host, share, subpath, user, pw = self._parse()
        domain = self.options.get("domain", "")

        smbclient.register_session(
            host,
            username=f"{domain}\\{user}" if domain else user,
            password=pw,
        )

        unc_root = f"\\\\{host}\\{share}"
        if subpath:
            unc_root = unc_root + "\\" + subpath.replace("/", "\\")

        try:
            yield from self._walk_smb(smbclient, unc_root, host, share)
        finally:
            try:
                smbclient.delete_session(host)
            except Exception:
                pass

    def _walk_smb(self, smbclient, unc_path: str, host: str, share: str):
        try:
            for entry in smbclient.scandir(unc_path):
                try:
                    stat = entry.stat()
                    full = str(PureWindowsPath(unc_path, entry.name))
                    yield FileRecord(
                        path=full, name=entry.name,
                        size_bytes=stat.st_size if entry.is_file() else 0,
                        modified=stat.st_mtime,
                        sha256=None,
                        suffix=PureWindowsPath(entry.name).suffix.lower() if entry.is_file() else "",
                        is_dir=entry.is_dir(),
                        host=host, share=share,
                    )
                    if entry.is_dir():
                        yield from self._walk_smb(smbclient, full, host, share)
                except (PermissionError, OSError):
                    pass
        except Exception:
            pass
