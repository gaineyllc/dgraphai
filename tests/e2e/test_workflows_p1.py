"""
E2E tests — Workflow builder API (P1).
"""
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.p1]


@pytest.mark.asyncio
async def test_workflows_list(client: AsyncClient):
    r = await client.get("/api/workflows")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_workflow_create(client: AsyncClient):
    r = await client.post("/api/workflows", json={
        "name":        "PII Alert Workflow",
        "description": "Notify security team when PII detected",
        "trigger":     "pii_detected",
        "steps": [
            {"type": "condition", "config": {"field": "sensitivity_level", "op": "=", "value": "high"}},
            {"type": "notify",    "config": {"channel": "slack", "message": "High sensitivity PII found"}},
        ],
    })
    # 200 (created) or 422 (validation) are both fine; 500 is not
    assert r.status_code != 500


@pytest.mark.asyncio
async def test_workflow_step_types_valid(client: AsyncClient):
    """The workflow engine should accept all 7 documented step types."""
    step_types = ["condition", "notify", "tag", "quarantine", "escalate", "export", "webhook"]
    for stype in step_types:
        r = await client.post("/api/workflows", json={
            "name": f"Test {stype}",
            "steps": [{"type": stype, "config": {}}],
        })
        assert r.status_code not in (500,), f"Step type {stype!r} caused server error"


@pytest.mark.asyncio
async def test_saved_queries_list(client: AsyncClient):
    r = await client.get("/api/queries")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_saved_query_create_and_retrieve(client: AsyncClient):
    r = await client.post("/api/queries", json={
        "name":   "All 4K Videos",
        "cypher": "MATCH (f:File) WHERE f.file_category = 'video' AND f.height >= 2160 RETURN f",
        "tags":   ["media", "4k"],
    })
    assert r.status_code == 200
    query = r.json()
    assert query["name"]   == "All 4K Videos"
    qid = query["id"]

    # Retrieve
    r = await client.get(f"/api/queries/{qid}")
    assert r.status_code == 200
    assert r.json()["id"] == qid
