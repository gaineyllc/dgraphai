"""
Unit tests — licensing & metering (P0).
No I/O. No DB. Pure logic.
"""
import pytest
from datetime import datetime, timezone, timedelta

from src.dgraphai.licensing.metering import (
    UsageSnapshot, CostBreakdown, BillingPlan, PLANS, get_plan,
    TIER_STANDARD, TIER_ENRICHABLE, TIER_AI_ENRICHED, TIER_IDENTITY, TIER_GRAPH_EDGES,
    TIER_RATES, NODE_TYPE_TIER, BILLED_RELATIONSHIP_TYPES, FREE_RELATIONSHIP_TYPES,
)
from src.dgraphai.licensing.license import (
    License, LicenseType, LicenseFeatures, LicenseLimits,
    _developer_license, LicenseError,
)

pytestmark = pytest.mark.unit


# ── Tier rate sanity ───────────────────────────────────────────────────────────

def test_tier_rates_ascending():
    """AI enriched must cost more than enrichable, which costs more than standard."""
    assert TIER_RATES[TIER_STANDARD]    < TIER_RATES[TIER_ENRICHABLE]
    assert TIER_RATES[TIER_ENRICHABLE]  < TIER_RATES[TIER_AI_ENRICHED]
    assert TIER_RATES[TIER_AI_ENRICHED] < TIER_RATES[TIER_IDENTITY]


def test_all_node_types_have_tier():
    expected_types = {
        "Directory","Tag","Collection","Event","Vendor","License","Topic","Organization",
        "File","Application","Dependency","Certificate","FaceCluster","Binary","MediaItem",
        "Version","Product","Person","Vulnerability","Location",
    }
    for nt in expected_types:
        assert nt in NODE_TYPE_TIER, f"Node type {nt!r} missing from NODE_TYPE_TIER"


def test_relationship_sets_disjoint():
    overlap = BILLED_RELATIONSHIP_TYPES & FREE_RELATIONSHIP_TYPES
    assert not overlap, f"Relationships in both billed and free: {overlap}"


# ── UsageSnapshot ──────────────────────────────────────────────────────────────

def make_snapshot(**kwargs) -> UsageSnapshot:
    defaults = dict(
        tenant_id         = "test-tenant",
        snapshot_at       = datetime.now(timezone.utc),
        standard_nodes    = 1_000,
        enrichable_nodes  = 500,
        ai_enriched_nodes = 200,
        identified_people = 10,
        billed_relationships = 5_000,
    )
    defaults.update(kwargs)
    return UsageSnapshot(**defaults)


def test_total_nodes():
    snap = make_snapshot(
        standard_nodes=1000, enrichable_nodes=500,
        ai_enriched_nodes=200, identified_people=10, unknown_people=5,
    )
    assert snap.total_nodes == 1715


def test_zero_snapshot_zero_cost():
    snap = UsageSnapshot(tenant_id="x", snapshot_at=datetime.now(timezone.utc))
    plan = get_plan("starter")
    cost = CostBreakdown.from_snapshot(snap, plan)
    assert cost.total == 0.0


def test_cost_components_add_up():
    snap = make_snapshot(
        standard_nodes=10_000, enrichable_nodes=5_000,
        ai_enriched_nodes=2_000, identified_people=100,
        billed_relationships=50_000,
    )
    plan = get_plan("pro")
    cost = CostBreakdown.from_snapshot(snap, plan)

    expected_standard    = (10_000 / 1_000) * TIER_RATES[TIER_STANDARD]
    expected_enrichable  = (5_000  / 1_000) * TIER_RATES[TIER_ENRICHABLE]
    expected_ai          = (2_000  / 1_000) * TIER_RATES[TIER_AI_ENRICHED]
    expected_identity    = (100    / 1_000) * TIER_RATES[TIER_IDENTITY]
    expected_edges       = (50_000 / 1_000) * TIER_RATES[TIER_GRAPH_EDGES]

    assert abs(cost.standard_cost    - expected_standard)   < 0.001
    assert abs(cost.enrichable_cost  - expected_enrichable) < 0.001
    assert abs(cost.ai_enriched_cost - expected_ai)         < 0.001
    assert abs(cost.identity_cost    - expected_identity)   < 0.001
    assert abs(cost.graph_edge_cost  - expected_edges)      < 0.001


def test_volume_discount_applies():
    # Pro plan: 10% discount over 1M nodes
    snap = make_snapshot(
        standard_nodes    = 800_000,
        enrichable_nodes  = 200_000,
        ai_enriched_nodes = 100_000,
    )
    plan = get_plan("pro")
    cost = CostBreakdown.from_snapshot(snap, plan)
    assert cost.discount_pct == 10.0
    assert cost.total < cost.subtotal


def test_no_discount_under_threshold():
    snap = make_snapshot(standard_nodes=100, enrichable_nodes=100)
    plan = get_plan("pro")
    cost = CostBreakdown.from_snapshot(snap, plan)
    assert cost.discount_pct == 0.0
    assert cost.total == cost.subtotal


def test_cost_breakdown_to_dict():
    snap = make_snapshot()
    cost = CostBreakdown.from_snapshot(snap, get_plan("starter"))
    d = cost.to_dict()
    assert "line_items" in d
    assert "total" in d
    assert isinstance(d["total"], float)
    tiers = {item["tier"] for item in d["line_items"]}
    assert TIER_STANDARD    in tiers
    assert TIER_ENRICHABLE  in tiers
    assert TIER_AI_ENRICHED in tiers


# ── Plans ──────────────────────────────────────────────────────────────────────

def test_all_plans_exist():
    for plan_id in ["starter", "pro", "business", "enterprise"]:
        assert plan_id in PLANS
        plan = get_plan(plan_id)
        assert plan.id == plan_id
        assert isinstance(plan.base_monthly_fee, float)


def test_starter_is_free():
    assert get_plan("starter").base_monthly_fee == 0.0


def test_enterprise_has_unlimited_nodes():
    plan = get_plan("enterprise")
    assert plan.included_standard_nodes == -1
    assert plan.included_ai_enriched_nodes == -1


def test_plan_features_escalate():
    """Higher plans have more features enabled."""
    starter    = get_plan("starter")
    pro        = get_plan("pro")
    business   = get_plan("business")
    enterprise = get_plan("enterprise")

    assert not starter.features.get("ai_enrichment")
    assert     pro.features.get("ai_enrichment")
    assert not starter.features.get("sso_oidc")
    assert     business.features.get("sso_oidc")
    assert not business.features.get("ai_training_export")
    assert     enterprise.features.get("ai_training_export")


def test_unknown_plan_returns_starter():
    plan = get_plan("nonexistent-plan")
    assert plan.id == "starter"


# ── License ────────────────────────────────────────────────────────────────────

def test_developer_license_valid():
    lic = _developer_license()
    assert lic.is_valid
    assert not lic.is_expired
    assert lic.license_type == LicenseType.DEVELOPER
    assert lic.features.api_access is True


def test_expired_license_invalid():
    lic = _developer_license()
    lic.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    lic.grace_period_days = 0
    assert lic.is_expired
    assert not lic.is_valid


def test_license_in_grace_period():
    lic = _developer_license()
    lic.expires_at = datetime.now(timezone.utc) - timedelta(days=3)
    lic.grace_period_days = 14
    assert lic.is_expired
    assert lic.is_in_grace_period
    assert lic.is_valid   # grace period keeps it valid


def test_days_until_expiry_perpetual():
    lic = _developer_license()
    lic.expires_at = None
    assert lic.days_until_expiry() is None


def test_days_until_expiry_future():
    lic = _developer_license()
    lic.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    days = lic.days_until_expiry()
    assert 28 <= days <= 31


def test_feature_check():
    lic = _developer_license()
    lic.features.api_access = True
    lic.features.sso_oidc   = False
    assert lic.check_feature("api_access") is True
    assert lic.check_feature("sso_oidc")   is False
    assert lic.check_feature("nonexistent") is False
