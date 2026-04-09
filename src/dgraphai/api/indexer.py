"""
Indexer API — trigger scans, stream progress via WebSocket.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/indexer", tags=["indexer"])

# Active indexing jobs: {job_id: {status, progress, ...}}
_jobs: dict[str, dict[str, Any]] = {}
# WebSocket subscribers: {job_id: [ws, ...]}
_subscribers: dict[str, list[WebSocket]] = {}


class IndexRequest(BaseModel):
    mount_id: str
    enrich_llm: bool = True
    enrich_vision: bool = True
    enrich_faces: bool = True
    dry_run: bool = False


@router.get("/jobs")
async def list_jobs() -> list[dict[str, Any]]:
    """List all indexing jobs (active and recent)."""
    return list(_jobs.values())


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    """Get status of a specific indexing job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job


@router.post("/start")
async def start_index(req: IndexRequest) -> dict[str, Any]:
    """
    Start indexing a mounted filesystem source.
    Returns job_id — subscribe to /ws/indexer/{job_id} for live progress.
    """
    from src.dgraphai.mounts.manager import MountManager
    import uuid

    manager = MountManager()
    mount = manager.get_mount(req.mount_id)
    if not mount:
        raise HTTPException(status_code=404, detail=f"Mount {req.mount_id!r} not found")

    job_id = str(uuid.uuid4())
    job: dict[str, Any] = {
        "id":            job_id,
        "mount_id":      req.mount_id,
        "mount_name":    mount["name"],
        "source":        mount["uri"],
        "status":        "running",
        "files_scanned": 0,
        "files_indexed": 0,
        "files_skipped": 0,
        "errors":        0,
        "current_file":  "",
        "dry_run":       req.dry_run,
        "started_at":    asyncio.get_event_loop().time(),
    }
    _jobs[job_id] = job
    _subscribers[job_id] = []

    # Run in background
    asyncio.create_task(_run_index(job_id, mount["uri"], req))

    return {"job_id": job_id, "status": "running"}


@router.websocket("/ws/{job_id}")
async def index_progress_ws(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket endpoint for real-time indexing progress.
    Streams {event, data} messages until the job completes.
    """
    await websocket.accept()
    _subscribers.setdefault(job_id, []).append(websocket)

    # Send current state immediately
    job = _jobs.get(job_id)
    if job:
        await websocket.send_text(json.dumps({"event": "state", "data": job}))

    try:
        # Keep alive until disconnect
        while True:
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"event": "ping"}))
    except WebSocketDisconnect:
        pass
    finally:
        subs = _subscribers.get(job_id, [])
        if websocket in subs:
            subs.remove(websocket)


async def _broadcast(job_id: str, event: str, data: Any) -> None:
    """Send an event to all WebSocket subscribers of a job."""
    message = json.dumps({"event": event, "data": data})
    for ws in list(_subscribers.get(job_id, [])):
        try:
            await ws.send_text(message)
        except Exception:
            pass


async def _run_index(job_id: str, source: str, req: IndexRequest) -> None:
    """Run the indexing pipeline and stream progress updates."""
    job = _jobs[job_id]
    try:
        from src.dgraphai.graph.client import get_graph_client
        from src.dgraphai.mounts.manager import MountManager

        # Import archon's indexer (reused as library)
        # This keeps dgraphai thin — archon owns the indexing logic
        from archon.src.pipeline.indexer import ArchonIndexer

        def on_progress(result: Any) -> None:
            job["files_indexed" if result.success else "errors"] += 1
            job["current_file"] = result.path
            asyncio.create_task(_broadcast(job_id, "progress", {
                "files_indexed": job["files_indexed"],
                "files_scanned": job["files_scanned"],
                "errors":        job["errors"],
                "current_file":  result.path,
            }))

        indexer = ArchonIndexer(
            enrich_llm=req.enrich_llm,
            enrich_vision=req.enrich_vision,
            enrich_faces=req.enrich_faces,
            dry_run=req.dry_run,
            on_progress=on_progress,
        )
        stats = indexer.index(source)

        job.update({
            "status":        "complete",
            "files_scanned": stats["files_scanned"],
            "files_indexed": stats["files_indexed"],
            "files_skipped": stats.get("files_skipped", 0),
            "errors":        stats["errors"],
            "duration_secs": stats["duration_secs"],
        })

        MountManager().update_index_status(
            req.mount_id, "complete", stats["files_indexed"]
        )
        await _broadcast(job_id, "complete", job)

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        await _broadcast(job_id, "error", {"message": str(e)})
