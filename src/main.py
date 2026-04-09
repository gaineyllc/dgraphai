"""
fsgraph API server.
Serves both the REST/WebSocket API and the React frontend.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.fsgraph.api.graph import router as graph_router
from src.fsgraph.api.mounts import router as mounts_router
from src.fsgraph.api.indexer import router as indexer_router
from src.fsgraph.api.actions import router as actions_router
from src.fsgraph.graph.client import get_graph_client
from src.fsgraph.core.config import API_HOST, API_PORT

log = logging.getLogger("fsgraph")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Neo4j on startup, disconnect on shutdown."""
    client = get_graph_client()
    try:
        await client.connect()
        log.info("Connected to Neo4j")
    except Exception as e:
        log.warning(f"Neo4j unavailable at startup: {e} — graph features disabled")
    yield
    await client.close()


app = FastAPI(
    title="fsgraph",
    version="0.1.0",
    description="Filesystem knowledge graph platform",
    lifespan=lifespan,
)

# Allow the Vite dev server to call the API during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:7474"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(graph_router)
app.include_router(mounts_router)
app.include_router(indexer_router)
app.include_router(actions_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# Serve the React frontend in production (after `npm run build`)
_web_dist = Path(__file__).parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )
