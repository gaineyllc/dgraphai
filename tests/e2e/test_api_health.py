"""
E2E tests — API health + core endpoints reachable (P0).
Spins up full FastAPI app with mocked dependencies.
"""
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.p0]


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    r = await client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_schema_endpoint(client: AsyncClient):
    r = await client.get("/api/schema")
    assert r.status_code == 200
    data = r.json()
    assert len(data["node_types"])         >= 15
    assert len(data["relationship_types"]) >= 20
    assert data["total_node_types"]        == len(data["node_types"])


@pytest.mark.asyncio
async def test_schema_node_types_endpoint(client: AsyncClient):
    r = await client.get("/api/schema/node-types")
    assert r.status_code == 200
    types = r.json()
    ids = [t["id"] for t in types]
    assert "File"          in ids
    assert "Person"        in ids
    assert "Vulnerability" in ids


@pytest.mark.asyncio
async def test_schema_properties_file(client: AsyncClient):
    r = await client.get("/api/schema/properties/File")
    assert r.status_code == 200
    data = r.json()
    assert data["node_type"] == "File"
    keys = [p["key"] for p in data["properties"]]
    assert "name"             in keys
    assert "path"             in keys
    assert "pii_detected"     in keys
    assert "contains_secrets" in keys
    assert "hdr_format"       in keys
    assert "summary"          in keys


@pytest.mark.asyncio
async def test_schema_properties_unknown_type(client: AsyncClient):
    r = await client.get("/api/schema/properties/NotARealType")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_schema_relationships_filter(client: AsyncClient):
    r = await client.get("/api/schema/relationships?from_type=File")
    assert r.status_code == 200
    rels = r.json()
    # All returned rels should have File in their 'from' list
    for rel in rels:
        assert "File" in rel["from"]


@pytest.mark.asyncio
async def test_inventory_list(client: AsyncClient):
    r = await client.get("/api/inventory")
    assert r.status_code == 200
    data = r.json()
    assert "groups" in data
    assert data["total_categories"] >= 10
    # Check group structure
    groups = data["groups"]
    assert isinstance(groups, dict)
    for group_name, cats in groups.items():
        assert isinstance(cats, list)
        for cat in cats:
            assert "id" in cat
            assert "name" in cat
            assert "color" in cat
            assert "has_children" in cat


@pytest.mark.asyncio
async def test_inventory_category_detail(client: AsyncClient):
    r = await client.get("/api/inventory/video")
    assert r.status_code == 200
    data = r.json()
    assert data["category"]["id"]   == "video"
    assert data["category"]["name"] == "Video"
    assert "subcategories" in data
    assert "pagination"    in data
    assert data["pagination"]["page"]      == 0
    assert data["pagination"]["page_size"] >= 1


@pytest.mark.asyncio
async def test_inventory_category_pagination(client: AsyncClient):
    r = await client.get("/api/inventory/video?page=0&page_size=5")
    assert r.status_code == 200
    data = r.json()
    assert data["pagination"]["page_size"] == 5


@pytest.mark.asyncio
async def test_inventory_unknown_category(client: AsyncClient):
    r = await client.get("/api/inventory/definitely-not-real")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_usage_rates(client: AsyncClient):
    r = await client.get("/api/usage/rates")
    assert r.status_code == 200
    data = r.json()
    assert "tiers" in data
    assert len(data["tiers"]) == 5
    tier_ids = [t["id"] for t in data["tiers"]]
    assert "standard"    in tier_ids
    assert "enrichable"  in tier_ids
    assert "ai_enriched" in tier_ids
    assert "identity"    in tier_ids
    assert "graph_edges" in tier_ids
    assert "free_relationships" in data
    assert "CHILD_OF" in data["free_relationships"]


@pytest.mark.asyncio
async def test_usage_plans(client: AsyncClient):
    r = await client.get("/api/usage/plans")
    assert r.status_code == 200
    plans = r.json()
    ids = [p["id"] for p in plans]
    assert "starter"    in ids
    assert "pro"        in ids
    assert "business"   in ids
    assert "enterprise" in ids


@pytest.mark.asyncio
async def test_usage_plan_detail(client: AsyncClient):
    r = await client.get("/api/usage/plans/pro")
    assert r.status_code == 200
    plan = r.json()
    assert plan["id"]   == "pro"
    assert plan["base_monthly_fee"] == 299.0
    assert plan["features"]["ai_enrichment"] is True


@pytest.mark.asyncio
async def test_usage_limits(client: AsyncClient):
    r = await client.get("/api/usage/limits")
    assert r.status_code == 200
    data = r.json()
    assert "nodes"      in data
    assert "connectors" in data
    assert "plan"       in data


@pytest.mark.asyncio
async def test_connectors_types(client: AsyncClient):
    r = await client.get("/api/connectors/types")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_connectors_list(client: AsyncClient):
    r = await client.get("/api/connectors")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
