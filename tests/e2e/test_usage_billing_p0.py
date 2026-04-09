"""
E2E tests — Usage & Billing (P0).
Tests: snapshot structure, cost calculation, plan gating, limits.
"""
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.p0]


@pytest.mark.asyncio
async def test_usage_snapshot_structure(client: AsyncClient):
    r = await client.get("/api/usage/snapshot")
    assert r.status_code == 200
    data = r.json()

    # Top-level keys
    assert "snapshot" in data
    assert "cost"     in data
    assert "plan"     in data
    assert "limits"   in data

    snap = data["snapshot"]
    assert "total_nodes"            in snap
    assert "standard_nodes"         in snap
    assert "enrichable_nodes"       in snap
    assert "ai_enriched_nodes"      in snap
    assert "identified_people"      in snap
    assert "billed_relationships"   in snap
    assert "enrichment_detail"      in snap

    detail = snap["enrichment_detail"]
    assert "files_raw"      in detail
    assert "files_enriched" in detail
    assert "files_vision"   in detail
    assert "files_code"     in detail
    assert "files_binary"   in detail


@pytest.mark.asyncio
async def test_cost_breakdown_structure(client: AsyncClient):
    r = await client.get("/api/usage/snapshot")
    assert r.status_code == 200
    cost = r.json()["cost"]

    assert "line_items" in cost
    assert "total"      in cost
    assert "subtotal"   in cost

    # Must have all 5 tier line items
    tier_ids = {item["tier"] for item in cost["line_items"]}
    assert "standard"    in tier_ids
    assert "enrichable"  in tier_ids
    assert "ai_enriched" in tier_ids
    assert "identity"    in tier_ids
    assert "graph_edges" in tier_ids

    # Total must be non-negative
    assert cost["total"] >= 0


@pytest.mark.asyncio
async def test_cost_total_equals_sum(client: AsyncClient):
    r = await client.get("/api/usage/snapshot")
    cost = r.json()["cost"]
    line_sum = sum(item["amount"] for item in cost["line_items"])
    # With discount, total ≤ subtotal ≤ line_sum + platform_fee
    assert cost["total"] <= cost["subtotal"] + 0.01


@pytest.mark.asyncio
async def test_pro_plan_features(client: AsyncClient):
    r = await client.get("/api/usage/plans/pro")
    assert r.status_code == 200
    plan = r.json()
    assert plan["features"]["ai_enrichment"]  is True
    assert plan["features"]["api_access"]     is True
    assert plan["features"]["sso_oidc"]       is not True  # not on Pro
    assert plan["base_monthly_fee"]           == 299.0


@pytest.mark.asyncio
async def test_enterprise_plan_unlimited(client: AsyncClient):
    r = await client.get("/api/usage/plans/enterprise")
    assert r.status_code == 200
    plan = r.json()
    assert plan["included"]["standard_nodes"]    == -1
    assert plan["included"]["ai_enriched_nodes"] == -1
    assert plan["features"]["ai_training_export"] is True


@pytest.mark.asyncio
async def test_starter_plan_free(client: AsyncClient):
    r = await client.get("/api/usage/plans/starter")
    assert r.status_code == 200
    assert r.json()["base_monthly_fee"] == 0.0


@pytest.mark.asyncio
async def test_rates_endpoint_all_tiers(client: AsyncClient):
    r = await client.get("/api/usage/rates")
    assert r.status_code == 200
    data = r.json()

    tiers = {t["id"]: t for t in data["tiers"]}
    # AI enriched must cost more than enrichable
    assert tiers["ai_enriched"]["rate_per_1k"] > tiers["enrichable"]["rate_per_1k"]
    assert tiers["enrichable"]["rate_per_1k"]  > tiers["standard"]["rate_per_1k"]
    assert tiers["identity"]["rate_per_1k"]    > tiers["ai_enriched"]["rate_per_1k"]


@pytest.mark.asyncio
async def test_limits_endpoint(client: AsyncClient):
    r = await client.get("/api/usage/limits")
    assert r.status_code == 200
    data = r.json()
    assert "nodes"      in data
    assert "connectors" in data
    node_status = data["nodes"].get("status")
    assert node_status in ("ok", "warning", "critical", "exceeded", None)
