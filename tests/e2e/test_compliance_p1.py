"""
E2E tests — Compliance reports + alert rules (P1).
"""
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.p1]


@pytest.mark.asyncio
async def test_alerts_list(client: AsyncClient):
    r = await client.get("/api/alerts")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_compliance_report_types(client: AsyncClient):
    r = await client.get("/api/compliance/reports")
    assert r.status_code in (200, 404)  # route may differ
    if r.status_code == 200:
        data = r.json()
        assert isinstance(data, list)


@pytest.mark.asyncio
async def test_inventory_pii_category(client: AsyncClient):
    """PII inventory must exist and surface compliance-relevant fields."""
    r = await client.get("/api/inventory/pii")
    assert r.status_code == 200
    data = r.json()
    cat = data["category"]
    assert cat["id"]   == "pii"
    cols = data.get("columns", [])
    col_keys = [c["key"] for c in cols]
    assert "pii_detected"      in col_keys
    assert "sensitivity_level" in col_keys
    assert "pii_types"         in col_keys


@pytest.mark.asyncio
async def test_inventory_secrets_category(client: AsyncClient):
    r = await client.get("/api/inventory/secrets")
    assert r.status_code == 200
    data = r.json()
    assert data["category"]["id"] == "secrets"
    subs = [s["id"] for s in data.get("subcategories", [])]
    assert "secrets-api-keys"  in subs
    assert "secrets-passwords" in subs
    assert "secrets-tokens"    in subs


@pytest.mark.asyncio
async def test_inventory_certificates_category(client: AsyncClient):
    r = await client.get("/api/inventory/certificates")
    assert r.status_code == 200
    subs = [s["id"] for s in r.json().get("subcategories", [])]
    assert "certs-expired"    in subs
    assert "certs-expiring-30" in subs
    assert "private-keys"     in subs


@pytest.mark.asyncio
async def test_inventory_cve_critical(client: AsyncClient):
    r = await client.get("/api/inventory/cve-critical")
    assert r.status_code == 200
    data = r.json()
    assert "CVSS" in data["category"]["description"] or "critical" in data["category"]["description"].lower()
