"""
fsgraph configuration.
All settings load from environment variables with sensible defaults.
"""
from __future__ import annotations

import os
from pathlib import Path


# ── Data directory ────────────────────────────────────────────────────────────

def data_dir() -> Path:
    d = Path(os.getenv("FSGRAPH_DATA_DIR", str(Path.home() / ".fsgraph")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Neo4j ─────────────────────────────────────────────────────────────────────

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "fsgraph-local")


# ── Server ────────────────────────────────────────────────────────────────────

API_HOST = os.getenv("FSGRAPH_HOST", "0.0.0.0")
API_PORT = int(os.getenv("FSGRAPH_PORT", "7474"))  # 7474 mirrors Neo4j browser — memorable


# ── Indexer ───────────────────────────────────────────────────────────────────

INDEXER_IO_WORKERS   = int(os.getenv("FSGRAPH_IO_WORKERS",  "8"))
INDEXER_LLM_WORKERS  = int(os.getenv("FSGRAPH_LLM_WORKERS", "2"))
INDEXER_FACE_WORKERS = int(os.getenv("FSGRAPH_FACE_WORKERS","1"))

OLLAMA_BASE_URL     = os.getenv("OLLAMA_BASE_URL",    "http://localhost:11434")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL","llava")
OLLAMA_TEXT_MODEL   = os.getenv("OLLAMA_TEXT_MODEL",  "llama3.2")
