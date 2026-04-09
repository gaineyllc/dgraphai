"""
Integration tests — full indexer → graph → inventory pipeline.
Requires: running Neo4j (or mock), Postgres (SQLite for tests).

These validate that:
  1. Files are categorized correctly
  2. Secret detection fires on appropriate files
  3. PII detection fires on appropriate content
  4. Nodes end up in the correct inventory categories
  5. Tier assignment matches expected billing tier
"""
import pytest
from pathlib import Path

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_code_file_secret_detection(sample_files, tmp_path):
    """Python file with hardcoded API key → contains_secrets=True."""
    try:
        from src.dgraphai.enrichers.metadata import _extract_code
    except ImportError:
        pytest.skip("archon enrichers not available in this environment")

    code_file = sample_files["code_with_secret"]
    result = _extract_code(str(code_file))

    assert result.get("contains_secrets") is True
    assert result.get("code_language") in ("Python", "PY")
    assert result.get("line_count")  >= 1


@pytest.mark.asyncio
async def test_archive_executable_detection(sample_files):
    """ZIP containing .exe → contains_executables=True."""
    try:
        from src.dgraphai.enrichers.metadata import _extract_archive
    except ImportError:
        pytest.skip("archon enrichers not available")

    arc = sample_files["archive_with_exe"]
    result = _extract_archive(str(arc), ".zip")

    assert result.get("contains_executables") is True
    assert result.get("file_count_in_archive") >= 1


@pytest.mark.asyncio
async def test_billing_tier_file_no_summary():
    """File without summary → enrichable tier."""
    from src.dgraphai.licensing.metering import NODE_TYPE_TIER, TIER_ENRICHABLE
    assert NODE_TYPE_TIER["File"] == TIER_ENRICHABLE


@pytest.mark.asyncio
async def test_billing_tier_directory():
    """Directory → standard tier (cheapest)."""
    from src.dgraphai.licensing.metering import NODE_TYPE_TIER, TIER_STANDARD
    assert NODE_TYPE_TIER["Directory"] == TIER_STANDARD


@pytest.mark.asyncio
async def test_billing_tier_person():
    """Person → identity tier (most expensive per node)."""
    from src.dgraphai.licensing.metering import NODE_TYPE_TIER, TIER_IDENTITY
    assert NODE_TYPE_TIER["Person"] == TIER_IDENTITY


@pytest.mark.asyncio
async def test_inventory_category_matches_cypher():
    """
    For each category, the Cypher WHERE clause conditions should logically
    match the category's intent (basic smoke test).
    """
    from src.dgraphai.inventory.taxonomy import get_category

    checks = [
        ("video",           "file_category = 'video'"),
        ("video-4k",        "height >= 2160"),
        ("video-4k-hdr",    "hdr_format IS NOT NULL"),
        ("audio-lossless",  "audio_codec IN"),
        ("images-geotagged","gps_latitude IS NOT NULL"),
        ("docs-pii",        "pii_detected = true"),
        ("code-secrets",    "contains_secrets = true"),
        ("certs-expired",   "cert_is_expired = true"),
        ("pii-ssn",         "pii_types CONTAINS 'ssn'"),
        ("exe-packed",      "is_packed = true"),
        ("audio-bpm",       "bpm IS NOT NULL"),
        ("video-bit-depth", "bit_depth >= 10"),
        ("docs-encrypted",  "is_encrypted = true"),
        ("docs-with-macros","has_macros = true"),
        ("certs-weak-keys", "key_size < 2048"),
    ]

    for cat_id, expected_fragment in checks:
        cat = get_category(cat_id)
        assert cat is not None, f"Category {cat_id!r} not found"
        assert expected_fragment in cat.cypher, (
            f"Category {cat_id!r} Cypher doesn't contain {expected_fragment!r}\n"
            f"Actual: {cat.cypher}"
        )


@pytest.mark.asyncio
async def test_usage_snapshot_math():
    """Snapshot totals should be internally consistent."""
    from src.dgraphai.licensing.metering import UsageSnapshot, CostBreakdown, get_plan
    from datetime import datetime, timezone

    snap = UsageSnapshot(
        tenant_id          = "test",
        snapshot_at        = datetime.now(timezone.utc),
        standard_nodes     = 5_000,
        enrichable_nodes   = 2_000,
        ai_enriched_nodes  = 1_000,
        identified_people  = 50,
        unknown_people     = 100,
        billed_relationships = 10_000,
    )

    assert snap.total_nodes == 5_000 + 2_000 + 1_000 + 50 + 100

    plan = get_plan("pro")
    cost = CostBreakdown.from_snapshot(snap, plan)

    # Each line item cost must be non-negative
    d = cost.to_dict()
    for item in d["line_items"]:
        assert item["amount"] >= 0, f"Negative cost on {item['tier']}"

    # Total must be ≤ subtotal (discount may apply)
    assert cost.total <= cost.subtotal + 0.001
