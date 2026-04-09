"""
Graph backend factory.
Selects the correct backend based on tenant configuration.
"""
from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from .base import GraphBackend


def get_backend_for_tenant(
    backend_type: str,
    config: dict[str, Any],
) -> GraphBackend:
    """
    Instantiate the correct graph backend for a tenant.

    backend_type: "neo4j" | "auradb" | "neptune"
    config: decrypted connection parameters
    """
    if backend_type in ("neo4j", "auradb"):
        from .neo4j import Neo4jBackend
        return Neo4jBackend(
            uri      = config.get("uri",      os.getenv("NEO4J_URI",      "bolt://localhost:7687")),
            user     = config.get("user",     os.getenv("NEO4J_USER",     "neo4j")),
            password = config.get("password", os.getenv("NEO4J_PASSWORD", "fsgraph-local")),
        )

    if backend_type == "neptune":
        from .neptune import NeptuneBackend
        return NeptuneBackend(
            endpoint = config.get("endpoint", os.getenv("NEPTUNE_ENDPOINT", "")),
            region   = config.get("region",   os.getenv("AWS_REGION", "us-east-1")),
            use_iam  = config.get("use_iam",  True),
        )

    raise ValueError(f"Unknown graph backend: {backend_type!r}. Use: neo4j, auradb, neptune")


def get_default_backend() -> GraphBackend:
    """Return the default backend from environment config."""
    backend_type = os.getenv("GRAPH_BACKEND", "neo4j")
    return get_backend_for_tenant(backend_type, {})
