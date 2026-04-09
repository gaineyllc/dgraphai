"""
Shared pytest fixtures for dgraph.ai test suite.

Fixture hierarchy:
  db_engine     — in-memory SQLite engine (unit/e2e)
  db_session    — async session per test
  app           — FastAPI test app with overridden dependencies
  client        — AsyncClient bound to test app
  tenant        — a seeded Tenant row
  admin_user    — admin User for the test tenant
  member_user   — member User for the test tenant
  auth_headers  — Authorization headers for admin
  graph_backend — MockGraphBackend stub
"""
from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from faker import Faker
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker
)
from sqlalchemy.pool import StaticPool

from src.dgraphai.db.models import Base, Tenant, User, Role
from src.dgraphai.db.session import get_db
from src.main import app as _app

fake = Faker()


# ── Event loop ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── In-memory SQLite DB ────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# ── Test tenant + users ────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def tenant(db_session: AsyncSession) -> Tenant:
    t = Tenant(
        id       = uuid.uuid4(),
        slug     = fake.slug(),
        name     = fake.company(),
        plan     = "pro",
        is_active= True,
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, tenant: Tenant) -> User:
    u = User(
        id        = uuid.uuid4(),
        tenant_id = tenant.id,
        email     = fake.email(),
        name      = fake.name(),
        role      = "admin",
        is_active = True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def member_user(db_session: AsyncSession, tenant: Tenant) -> User:
    u = User(
        id        = uuid.uuid4(),
        tenant_id = tenant.id,
        email     = fake.email(),
        name      = fake.name(),
        role      = "member",
        is_active = True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


# ── Auth context mock ──────────────────────────────────────────────────────────

@pytest.fixture
def make_auth_context(tenant: Tenant, admin_user: User):
    """Factory: returns an AuthContext-like object for a given user."""
    from src.dgraphai.auth.oidc import AuthContext

    def _make(user: User = None, permissions: list[str] = None) -> AuthContext:
        u = user or admin_user
        return AuthContext(
            tenant_id   = tenant.id,
            user_id     = u.id,
            email       = u.email,
            name        = u.name,
            role        = u.role,
            permissions = permissions or ["admin:*"],
        )
    return _make


@pytest.fixture
def auth_headers(admin_user: User, tenant: Tenant) -> dict[str, str]:
    """JWT headers for the test admin user — token is mocked."""
    import jwt, time
    token = jwt.encode({
        "sub":       str(admin_user.id),
        "email":     admin_user.email,
        "tenant_id": str(tenant.id),
        "role":      "admin",
        "exp":       int(time.time()) + 3600,
    }, "test-secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ── Mock graph backend ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_graph(tenant: Tenant):
    """Stub graph backend with pre-seeded nodes."""
    tid = str(tenant.id)

    _nodes = [
        {"id": f"{tid}-f1", "name": "movie.mkv",    "file_category": "video",    "height": 2160, "hdr_format": "HDR10", "tenant_id": tid, "summary": "A great film"},
        {"id": f"{tid}-f2", "name": "secret.py",    "file_category": "code",     "contains_secrets": True, "tenant_id": tid, "code_language": "Python"},
        {"id": f"{tid}-f3", "name": "invoice.pdf",  "file_category": "document", "pii_detected": True, "sensitivity_level": "high", "tenant_id": tid, "document_type": "invoice", "summary": "Invoice from ACME"},
        {"id": f"{tid}-f4", "name": "app.exe",      "file_category": "executable","signed": False, "tenant_id": tid, "eol_status": "eol"},
        {"id": f"{tid}-f5", "name": "photo.jpg",    "file_category": "image",    "face_count": 2, "gps_latitude": 37.7749, "tenant_id": tid, "summary": "Portrait photo"},
        {"id": f"{tid}-f6", "name": "report.docx",  "file_category": "document", "document_type": "report", "sentiment": "positive", "tenant_id": tid, "summary": "Q3 Report"},
        {"id": f"{tid}-p1", "name": "Alice Smith",                               "known": True,  "tenant_id": tid, "face_count": 5},
        {"id": f"{tid}-p2", "name": "Unknown-001",                               "known": False, "tenant_id": tid, "face_count": 2},
    ]

    backend = MagicMock()
    backend.__aenter__ = AsyncMock(return_value=backend)
    backend.__aexit__  = AsyncMock(return_value=False)

    async def _query(cypher: str, params: dict, tenant_id) -> list[dict]:
        # Route common query patterns to test data
        if "count" in cypher.lower():
            return [{"c": len(_nodes), "total": len(_nodes)}]
        if "File" in cypher and "video" in cypher:
            return [{"f": n} for n in _nodes if n.get("file_category") == "video"]
        if "File" in cypher and "pii_detected" in cypher:
            return [{"f": n} for n in _nodes if n.get("pii_detected")]
        if "Person" in cypher:
            return [{"f": n} for n in _nodes if "face_count" in n]
        return [{"f": n} for n in _nodes[:3]]

    backend.query = AsyncMock(side_effect=_query)
    return backend


# ── FastAPI test client ────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_session: AsyncSession, tenant: Tenant, admin_user: User, mock_graph) -> AsyncGenerator[AsyncClient, None]:
    """
    Full test client with:
      - DB dependency overridden to test session
      - Graph backend overridden to mock
      - Auth overridden to test admin context
    """
    from src.dgraphai.auth.oidc import get_auth_context, AuthContext

    async def override_db():
        yield db_session

    async def override_auth():
        return AuthContext(
            tenant_id   = tenant.id,
            user_id     = admin_user.id,
            email       = admin_user.email,
            name        = admin_user.name,
            role        = "admin",
            permissions = ["admin:*"],
        )

    _app.dependency_overrides[get_db]            = override_db
    _app.dependency_overrides[get_auth_context]  = override_auth

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c

    _app.dependency_overrides.clear()


# ── File fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_files(tmp_path):
    """Create a small set of sample files for connector/indexer tests."""
    files = {}

    video = tmp_path / "sample.mkv"
    video.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 100)  # MKV magic bytes
    files["video"] = video

    pdf = tmp_path / "document.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    files["pdf"] = pdf

    code = tmp_path / "app.py"
    code.write_text("api_key = 'sk-1234567890abcdef'\nprint('hello')\n")
    files["code_with_secret"] = code

    image = tmp_path / "photo.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # JPEG magic
    files["image"] = image

    archive = tmp_path / "bundle.zip"
    import zipfile, io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "hello")
        z.writestr("payload.exe", b"\x4d\x5a".decode("latin1"))
    archive.write_bytes(buf.getvalue())
    files["archive_with_exe"] = archive

    return files
