"""
Filesystem actions API — move, delete, rename with full audit log.
Every action is logged before execution. Destructive actions require confirmation.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.dgraphai.core.config import data_dir

router = APIRouter(prefix="/api/actions", tags=["actions"])


# ── Audit log ──────────────────────────────────────────────────────────────────

def _audit_file() -> Path:
    return data_dir() / "audit.jsonl"


def _log_action(action: dict[str, Any]) -> None:
    """Append an action to the audit log (append-only JSONL)."""
    with open(_audit_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(action) + "\n")


# ── Models ────────────────────────────────────────────────────────────────────

class MoveRequest(BaseModel):
    source: str       # Source URI (local path or smb://...)
    destination: str  # Destination URI
    dry_run: bool = True  # Safe default: always dry_run unless explicitly False


class DeleteRequest(BaseModel):
    path: str
    dry_run: bool = True


class RenameRequest(BaseModel):
    path: str
    new_name: str
    dry_run: bool = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit_log(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent audit log entries (most recent first)."""
    f = _audit_file()
    if not f.exists():
        return []
    lines = f.read_text(encoding="utf-8").strip().split("\n")
    entries = []
    for line in reversed(lines[-1000:]):
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries[:limit]


@router.post("/move")
async def move_file(req: MoveRequest) -> dict[str, Any]:
    """
    Move a file from source to destination.
    dry_run=True (default) previews without executing.
    """
    action = {
        "id":          str(uuid.uuid4()),
        "type":        "move",
        "source":      req.source,
        "destination": req.destination,
        "dry_run":     req.dry_run,
        "timestamp":   datetime.utcnow().isoformat(),
        "status":      "dry_run" if req.dry_run else "pending",
    }
    _log_action(action)

    if req.dry_run:
        return {**action, "status": "dry_run",
                "message": "Set dry_run=false to execute"}

    try:
        from archon.src.agents.nas_cataloger.protocols.factory import protocol_factory
        src_proto, src_path = protocol_factory(req.source)
        dst_proto, dst_path = protocol_factory(req.destination)
        with src_proto:
            src_proto.move(src_path, dst_path)
        action["status"] = "complete"
        _log_action({**action, "status": "complete"})
        return action
    except Exception as e:
        action["status"] = "error"
        action["error"] = str(e)
        _log_action(action)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete")
async def delete_file(req: DeleteRequest) -> dict[str, Any]:
    """
    Delete a file. Will NOT delete directories.
    dry_run=True (default) previews without executing.
    """
    action = {
        "id":        str(uuid.uuid4()),
        "type":      "delete",
        "path":      req.path,
        "dry_run":   req.dry_run,
        "timestamp": datetime.utcnow().isoformat(),
        "status":    "dry_run" if req.dry_run else "pending",
    }
    _log_action(action)

    if req.dry_run:
        return {**action, "status": "dry_run",
                "message": "Set dry_run=false to execute"}

    try:
        from archon.src.agents.nas_cataloger.protocols.factory import protocol_factory
        proto, path = protocol_factory(req.path)
        with proto:
            proto.delete(path)
        action["status"] = "complete"
        _log_action({**action, "status": "complete"})
        return action
    except Exception as e:
        action["status"] = "error"
        action["error"] = str(e)
        _log_action(action)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rename")
async def rename_file(req: RenameRequest) -> dict[str, Any]:
    """Rename a file in place."""
    parent = str(Path(req.path).parent)
    new_path = str(Path(parent) / req.new_name)

    move_req = MoveRequest(
        source=req.path,
        destination=new_path,
        dry_run=req.dry_run,
    )
    return await move_file(move_req)
