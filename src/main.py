"""
dgraphai API server — multi-tenant, RBAC-enforced.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.dgraphai.api.graph   import router as graph_router
from src.dgraphai.api.mounts  import router as mounts_router
from src.dgraphai.api.indexer import router as indexer_router
from src.dgraphai.api.actions import router as actions_router
from src.dgraphai.api.tenants import router as tenants_router
from src.dgraphai.api.auth    import router as auth_router
from src.dgraphai.api.scanner   import router as scanner_router
from src.dgraphai.api.queries   import router as queries_router
from src.dgraphai.api.workflows import router as workflows_router
from src.dgraphai.api.license   import router as license_router
from src.dgraphai.api.stream      import router as stream_router, hf_router
from src.dgraphai.api.alerts      import router as alerts_router
from src.dgraphai.api.compliance  import router as compliance_router
from src.dgraphai.api.connectors_full import router as connectors_router
from src.dgraphai.api.inventory       import router as inventory_router
from src.dgraphai.api.schema          import router as schema_router
from src.dgraphai.graphql.schema      import make_graphql_router
from src.dgraphai.db.session    import create_tables
from src.dgraphai.core.config import API_HOST, API_PORT

log = logging.getLogger("dgraphai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create Postgres tables on startup (idempotent)
    await create_tables()
    log.info("Database tables ready")
    yield


app = FastAPI(
    title="dgraphai",
    version="0.2.0",
    description="Filesystem knowledge graph platform — multi-tenant",
    lifespan=lifespan,
    # Disable docs in production — set dgraphai_ENABLE_DOCS=true for dev
    docs_url="/api/docs"  if __import__("os").getenv("dgraphai_ENABLE_DOCS") else None,
    redoc_url="/api/redoc" if __import__("os").getenv("dgraphai_ENABLE_DOCS") else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=__import__("os").getenv(
        "dgraphai_ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:7474"
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes (no auth required)
app.include_router(auth_router)

# Protected API routes
app.include_router(graph_router)
app.include_router(scanner_router)
app.include_router(queries_router)
app.include_router(workflows_router)
app.include_router(license_router)
app.include_router(stream_router)
app.include_router(hf_router)
app.include_router(alerts_router)
app.include_router(compliance_router)
app.include_router(connectors_router)
app.include_router(inventory_router)
app.include_router(schema_router)
app.include_router(mounts_router)
app.include_router(indexer_router)
app.include_router(actions_router)
app.include_router(tenants_router)


# GraphQL endpoint — context injects tenant + graph backend
async def _gql_context(request: __import__('fastapi').Request):
    from src.dgraphai.auth.oidc import get_auth_context
    from src.dgraphai.db.session import async_session
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant
    from src.dgraphai.db.models import Tenant
    from sqlalchemy import select
    async with async_session() as db:
        auth = await get_auth_context(request, db)
        result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
        tenant = result.scalar_one_or_none()
        backend = get_backend_for_tenant(tenant.graph_backend or 'neo4j', tenant.graph_config or {})
        return {"tenant_id": auth.tenant_id, "graph_backend": backend, "user": auth}

graphql_app = make_graphql_router(_gql_context)
app.include_router(graphql_app, prefix="/graphql")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


# Serve React frontend in production
_web_dist = Path(__file__).parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=bool(__import__("os").getenv("dgraphai_ENABLE_DOCS")),
        log_level="info",
    )
