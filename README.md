# dgraph.ai

Filesystem knowledge graph platform. Index any filesystem (local, SMB, NFS) into a Neo4j graph, visualize and query it interactively.

## Stack

| Layer | Technology |
|---|---|
| Graph DB | Neo4j |
| Backend | FastAPI + Python 3.14 |
| Frontend | React + TypeScript + Vite |
| Graph viz | Cytoscape.js + fcose layout |
| State | TanStack Query + Zustand |
| Indexing engine | archon (subproject) |

## Quickstart

```bash
# 1. Install Python deps
uv sync

# 2. Install frontend deps
cd web && npm install && cd ..

# 3. Start Neo4j
docker compose up -d  # (from archon/ — shares the same Neo4j instance)

# 4. Start backend
uv run python -m src.main

# 5. Start frontend (dev)
cd web && npm run dev
```

Backend: http://localhost:7474  
Frontend (dev): http://localhost:5173  
Neo4j browser: http://localhost:7474 (Neo4j default)

## Architecture

See [archon/docs/architecture.md](../archon/docs/) for the indexing pipeline.
The fsgraph backend is a thin API layer over the same Neo4j graph archon builds.
