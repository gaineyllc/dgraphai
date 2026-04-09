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
from src.dgraphai.auth.local         import router as local_auth_router
from src.dgraphai.api.users          import router as users_router
from src.dgraphai.auth.audit         import audit_router
from src.dgraphai.auth.scim          import router as scim_router, mgmt_router as scim_mgmt_router
from src.dgraphai.auth.saml          import router as saml_router, mgmt_router as saml_mgmt_router
from src.dgraphai.api.settings       import router as settings_router
from src.dgraphai.api.search           import router as search_router
from src.dgraphai.api.graph_intelligence import router as intel_router
from src.dgraphai.tasks.reenrichment     import admin_router as reenrich_router
from src.dgraphai.api.scan_schedule      import router as scan_schedule_router
from src.dgraphai.api.notifications      import router as notifications_router
from src.dgraphai.webhooks.outbound  import webhook_router
from src.dgraphai.observability.metrics import setup_metrics
from src.dgraphai.api.inventory       import router as inventory_router
from src.dgraphai.api.inventory_search import router as inv_search_router
from src.dgraphai.api.schema          import router as schema_router
from src.dgraphai.api.usage           import router as usage_router
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


# Observability setup (before routes)
from src.dgraphai.observability.metrics import setup_metrics as _setup_metrics

# Validate critical env vars at startup
import os as _os
_jwt_secret = _os.getenv("JWT_SECRET", "")
if not _jwt_secret or _jwt_secret in ("dev-jwt-secret-change-in-production", "your-secret-here"):
    import logging as _logging
    if _os.getenv("DGRAPHAI_ENABLE_DOCS"):  # dev mode — warn
        _logging.getLogger("dgraphai").warning(
            "JWT_SECRET is not set or is using the default dev value. "
            "Set JWT_SECRET to a secure random string in production. "
            "Generate one: openssl rand -hex 32"
        )
    else:  # production — fail fast
        raise RuntimeError(
            "JWT_SECRET environment variable is not set or is using a default value. "
            "Generate a secure secret: openssl rand -hex 32"
        )

# Validate ENCRYPTION_KEY
_enc_key = _os.getenv("ENCRYPTION_KEY", "")
if not _enc_key and not _os.getenv("DGRAPHAI_ENABLE_DOCS"):
    import logging as _logging
    _logging.getLogger("dgraphai").warning(
        "ENCRYPTION_KEY is not set — credentials stored in plaintext. "
        "Set ENCRYPTION_KEY to a base64-encoded 32-byte key."
    )

app = FastAPI(
    title="dgraphai",
    version="0.2.0",
    description="Filesystem knowledge graph platform — multi-tenant",
    lifespan=lifespan,
    # Disable docs in production — set dgraphai_ENABLE_DOCS=true for dev
    docs_url="/api/docs"  if __import__("os").getenv("dgraphai_ENABLE_DOCS") else None,
    redoc_url="/api/redoc" if __import__("os").getenv("dgraphai_ENABLE_DOCS") else None,
)

# Redis-backed rate limiting (works across all API replicas)
from src.dgraphai.middleware.rate_limit import rate_limit_middleware
app.middleware("http")(rate_limit_middleware)

# Build CORS origins: APP_URL is always allowed; add comma-separated extras
_app_url_origin = __import__("os").getenv("APP_URL", "").rstrip("/")
_extra_origins   = __import__("os").getenv("DGRAPHAI_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:7474")
_all_origins     = list(filter(None, [_app_url_origin] + _extra_origins.split(",")))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_all_origins or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes (no auth required)
app.include_router(auth_router)
app.include_router(local_auth_router)
app.include_router(users_router)
app.include_router(audit_router)
app.include_router(scim_router)
app.include_router(scim_mgmt_router)
app.include_router(saml_router)
app.include_router(saml_mgmt_router)
app.include_router(settings_router)
app.include_router(webhook_router)
app.include_router(search_router)
app.include_router(intel_router)
app.include_router(reenrich_router)
app.include_router(scan_schedule_router)
app.include_router(notifications_router)

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
app.include_router(inv_search_router)
app.include_router(schema_router)
app.include_router(usage_router)
app.include_router(mounts_router)
app.include_router(indexer_router)
app.include_router(actions_router)
app.include_router(tenants_router)


# GraphQL endpoint — context injects tenant + graph backend
# GraphQL query depth validation middleware
from fastapi import Request as _GQLRequest
from fastapi.responses import JSONResponse as _JSONResponse

@app.middleware("http")
async def graphql_depth_limit(request: _GQLRequest, call_next):
    """Block GraphQL queries with excessive depth."""
    if request.url.path.startswith("/graphql") and request.method == "POST":
        try:
            body = await request.body()
            import json as _json
            data = _json.loads(body)
            query = data.get("query", "")
            # Count nesting depth by brace count as fast heuristic
            depth = 0; max_depth = 0
            for ch in query:
                if ch == '{': depth += 1; max_depth = max(max_depth, depth)
                elif ch == '}': depth -= 1
            if max_depth > 8:
                return _JSONResponse(
                    status_code=400,
                    content={"errors": [{"message": f"Query depth {max_depth} exceeds maximum allowed depth of 8"}]}
                )
        except Exception:
            pass  # fail open on parse error
    return await call_next(request)

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


# Attach Prometheus + OTLP after all routes registered
_setup_metrics(app)


@app.get("/api/health")
async def health() -> dict:
    from src.dgraphai.graph.circuit_breaker import all_breaker_stats
    breakers = all_breaker_stats()
    any_open = any(b["state"] == "open" for b in breakers.values())
    return {
        "status":  "degraded" if any_open else "ok",
        "version": "0.2.0",
        "graph_circuit_breakers": breakers,
    }


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
