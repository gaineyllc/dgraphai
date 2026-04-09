"""
Mounts API — add, remove, list filesystem sources.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.dgraphai.mounts.manager import MountManager

router = APIRouter(prefix="/api/mounts", tags=["mounts"])
_manager = MountManager()


class AddMountRequest(BaseModel):
    name: str
    uri: str
    auto_index: bool = True


@router.get("")
async def list_mounts() -> list[dict[str, Any]]:
    """List all configured filesystem sources with reachability status."""
    return _manager.list_mounts()


@router.post("")
async def add_mount(req: AddMountRequest) -> dict[str, Any]:
    """
    Add a filesystem source.
    URI formats:
      - Local:  C:\\path\\to\\dir  or  /mnt/nas
      - SMB:    smb://user:pass@host/share
      - NFS:    nfs://host/export/path
    """
    try:
        return _manager.add_mount(
            name=req.name,
            uri=req.uri,
            auto_index=req.auto_index,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{mount_id}")
async def remove_mount(mount_id: str) -> dict[str, str]:
    """Remove a filesystem source by ID."""
    if not _manager.remove_mount(mount_id):
        raise HTTPException(status_code=404, detail=f"Mount {mount_id!r} not found")
    return {"status": "removed", "id": mount_id}


@router.get("/{mount_id}")
async def get_mount(mount_id: str) -> dict[str, Any]:
    """Get a specific mount's configuration and status."""
    mount = _manager.get_mount(mount_id)
    if not mount:
        raise HTTPException(status_code=404, detail=f"Mount {mount_id!r} not found")
    return mount
