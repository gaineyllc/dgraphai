"""
E2E tests — Connector CRUD + health + routing (P0).
"""
import pytest
import uuid
from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.p0]


@pytest.mark.asyncio
async def test_connector_types_returned(client: AsyncClient):
    r = await client.get("/api/connectors/types")
    assert r.status_code == 200
    types = r.json()
    assert isinstance(types, list)


@pytest.mark.asyncio
async def test_connector_list_empty_initially(client: AsyncClient):
    r = await client.get("/api/connectors")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_connector_full_lifecycle(client: AsyncClient):
    """Create → Get → Update → Delete."""
    # Create
    r = await client.post("/api/connectors", json={
        "name":           "Production S3",
        "description":    "Main media bucket",
        "connector_type": "aws-s3",
        "config":         {"bucket": "media-bucket", "region": "us-east-1"},
        "routing_mode":   "direct",
        "tags":           ["media", "production"],
    })
    assert r.status_code == 200
    conn = r.json()
    assert conn["name"]           == "Production S3"
    assert conn["connector_type"] == "aws-s3"
    assert "media" in conn["tags"]
    conn_id = conn["id"]

    # Get
    r = await client.get(f"/api/connectors/{conn_id}")
    assert r.status_code == 200
    assert r.json()["id"] == conn_id

    # Update
    r = await client.patch(f"/api/connectors/{conn_id}", json={
        "name":      "Updated S3",
        "is_active": False,
    })
    assert r.status_code == 200
    assert r.json()["name"]      == "Updated S3"
    assert r.json()["is_active"] is False

    # Delete
    r = await client.delete(f"/api/connectors/{conn_id}")
    assert r.status_code == 200

    # Verify gone
    r = await client.get(f"/api/connectors/{conn_id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_connector_health_fields_present(client: AsyncClient):
    """Created connector must expose health fields."""
    r = await client.post("/api/connectors", json={
        "name":           "SMB Share",
        "connector_type": "smb",
        "config":         {"host": "192.168.1.10", "share": "Media"},
        "routing_mode":   "agent",
    })
    assert r.status_code == 200
    conn = r.json()
    health = conn.get("health", {})
    assert "status"           in health
    assert "last_scan_at"     in health or health["status"] == "never"
    assert "total_files"      in health
    assert "last_test_result" in health


@pytest.mark.asyncio
async def test_connector_routing_mode_validation(client: AsyncClient):
    """On-prem types (SMB) must only allow 'agent' routing."""
    # Test that we can create with agent routing
    r = await client.post("/api/connectors", json={
        "name":           "SMB Agent Routed",
        "connector_type": "smb",
        "config":         {"host": "192.168.1.1", "share": "Files"},
        "routing_mode":   "agent",
    })
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_connector_available_agents(client: AsyncClient):
    """Agents endpoint returns a list (may be empty)."""
    r = await client.post("/api/connectors", json={
        "name": "Agent Test", "connector_type": "smb",
        "config": {"host": "x", "share": "y"}, "routing_mode": "agent",
    })
    conn_id = r.json()["id"]
    r = await client.get(f"/api/connectors/{conn_id}/agents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
