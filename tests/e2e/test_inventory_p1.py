"""
E2E tests — Data Inventory drill-down (P1).
Tests: category listing, breadcrumb, subcategory counts, pagination.
"""
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.p1]


@pytest.mark.asyncio
async def test_inventory_groups_structure(client: AsyncClient):
    r = await client.get("/api/inventory")
    assert r.status_code == 200
    data   = r.json()
    groups = data["groups"]

    expected_groups = ["Media", "Documents & Text", "Code & Config", "Security"]
    for g in expected_groups:
        assert g in groups, f"Group {g!r} missing from inventory"


@pytest.mark.asyncio
async def test_inventory_category_has_columns(client: AsyncClient):
    r = await client.get("/api/inventory/video")
    assert r.status_code == 200
    data = r.json()
    cols = data.get("columns", [])
    assert len(cols) > 0, "Video category must have table columns"
    col_keys = [c["key"] for c in cols]
    assert "name" in col_keys


@pytest.mark.asyncio
async def test_inventory_breadcrumb(client: AsyncClient):
    """Leaf category should have full breadcrumb trail."""
    r = await client.get("/api/inventory/video-4k-hdr")
    assert r.status_code == 200
    breadcrumb = r.json().get("breadcrumb", [])
    # Should be: Data Inventory > Video > 4K/UHD > 4K+HDR
    assert len(breadcrumb) >= 3
    names = [b["name"] for b in breadcrumb]
    assert "Data Inventory" in names


@pytest.mark.asyncio
async def test_inventory_subcategories_listed(client: AsyncClient):
    r = await client.get("/api/inventory/video")
    assert r.status_code == 200
    subs = r.json().get("subcategories", [])
    sub_ids = [s["id"] for s in subs]
    assert "video-4k" in sub_ids
    assert "video-hdr" in sub_ids


@pytest.mark.asyncio
async def test_inventory_leaf_has_no_subcats(client: AsyncClient):
    r = await client.get("/api/inventory/video-4k-hdr")
    assert r.status_code == 200
    subs = r.json().get("subcategories", [])
    assert subs == [], "video-4k-hdr is a leaf — should have no subcategories"


@pytest.mark.asyncio
async def test_inventory_page_size_respected(client: AsyncClient):
    r = await client.get("/api/inventory/video?page=0&page_size=3")
    assert r.status_code == 200
    data = r.json()
    assert data["pagination"]["page_size"] == 3
    assert len(data.get("nodes", [])) <= 3


@pytest.mark.asyncio
async def test_inventory_query_url_present(client: AsyncClient):
    r = await client.get("/api/inventory/pii")
    assert r.status_code == 200
    data = r.json()
    assert "query_url" in data
    assert "/query" in data["query_url"]


@pytest.mark.asyncio
async def test_inventory_security_categories(client: AsyncClient):
    """All major security categories must be navigable."""
    security_cats = ["secrets", "pii", "certificates", "vulnerabilities"]
    for cid in security_cats:
        r = await client.get(f"/api/inventory/{cid}")
        assert r.status_code == 200, f"Category {cid!r} returned {r.status_code}"
        data = r.json()
        assert data["category"]["id"] == cid


@pytest.mark.asyncio
async def test_inventory_ai_categories(client: AsyncClient):
    ai_cats = ["ai-enriched", "ai-action-items"]
    for cid in ai_cats:
        r = await client.get(f"/api/inventory/{cid}")
        assert r.status_code == 200
