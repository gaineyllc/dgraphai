"""
Unit tests — inventory taxonomy completeness and correctness.
"""
import re
import pytest

from src.dgraphai.inventory.taxonomy import (
    ALL_CATEGORIES, INVENTORY, CATEGORY_INDEX, get_category, get_by_group,
    Category, Column,
)

pytestmark = pytest.mark.unit


# ── Structure ──────────────────────────────────────────────────────────────────

def test_minimum_category_count():
    """We should have at least 100 categories."""
    assert len(ALL_CATEGORIES) >= 100, f"Only {len(ALL_CATEGORIES)} categories"


def test_no_duplicate_ids():
    ids = [c.id for c in ALL_CATEGORIES]
    dupes = [i for i in ids if ids.count(i) > 1]
    assert not dupes, f"Duplicate category IDs: {set(dupes)}"


def test_all_categories_have_required_fields():
    for cat in ALL_CATEGORIES:
        assert cat.id,          f"{cat.id}: missing id"
        assert cat.name,        f"{cat.id}: missing name"
        assert cat.description, f"{cat.id}: missing description"
        assert cat.group,       f"{cat.id}: missing group"
        assert cat.icon,        f"{cat.id}: missing icon"
        assert cat.color,       f"{cat.id}: missing color"
        assert cat.cypher,      f"{cat.id}: missing cypher"


def test_cypher_contains_tenant_scope():
    """Every Cypher query must scope by tenant_id for multi-tenant isolation."""
    for cat in ALL_CATEGORIES:
        assert "$tid" in cat.cypher or "tenant_id" in cat.cypher, (
            f"{cat.id}: Cypher missing tenant_id scope: {cat.cypher[:80]}"
        )


def test_cypher_has_return():
    """Every Cypher query must have a RETURN clause."""
    for cat in ALL_CATEGORIES:
        assert re.search(r'\bRETURN\b', cat.cypher, re.IGNORECASE), (
            f"{cat.id}: Cypher missing RETURN: {cat.cypher[:80]}"
        )


def test_valid_hex_colors():
    for cat in ALL_CATEGORIES:
        assert re.match(r'^#[0-9a-fA-F]{6}$', cat.color), (
            f"{cat.id}: invalid color {cat.color!r}"
        )


def test_parent_ids_resolve():
    """Every parent_id must point to an existing category."""
    for cat in ALL_CATEGORIES:
        if cat.parent_id:
            assert cat.parent_id in CATEGORY_INDEX, (
                f"{cat.id}: parent_id {cat.parent_id!r} not found"
            )


def test_subcategories_have_parent_id():
    """Categories listed as subcategories must have parent_id set."""
    def check(cats, parent=None):
        for cat in cats:
            if parent:
                assert cat.parent_id == parent.id, (
                    f"{cat.id}: subcategory of {parent.id} but parent_id={cat.parent_id!r}"
                )
            check(cat.subcategories, cat)
    check(INVENTORY)


def test_get_category_lookup():
    for cat in ALL_CATEGORIES[:10]:
        found = get_category(cat.id)
        assert found is not None
        assert found.id == cat.id


def test_get_category_missing_returns_none():
    assert get_category("does-not-exist-abc123") is None


def test_get_by_group_returns_only_top_level():
    groups = get_by_group()
    for group, cats in groups.items():
        for cat in cats:
            assert cat.parent_id is None, (
                f"get_by_group returned {cat.id} (parent_id={cat.parent_id!r}) in group {group!r}"
            )


# ── Column schema ──────────────────────────────────────────────────────────────

def test_column_kinds_valid():
    valid_kinds = {"text", "size", "date", "badge", "bool", "path", "num", "mono"}
    for cat in ALL_CATEGORIES:
        for col in cat.columns:
            assert col.kind in valid_kinds, (
                f"{cat.id}.{col.key}: unknown column kind {col.kind!r}"
            )


def test_columns_have_labels():
    for cat in ALL_CATEGORIES:
        for col in cat.columns:
            assert col.label, f"{cat.id}.{col.key}: column missing label"


# ── Coverage checks ────────────────────────────────────────────────────────────

def test_all_relationship_types_surfaced():
    """
    AI-computed and semantically-interesting relationship types must appear
    in at least one inventory Cypher query.
    Structural/free rels (CHILD_OF, TAGGED_WITH, etc.) are defined in the schema
    but don't drive inventory categories — they're surfaced in the graph explorer.
    """
    all_cypher = " ".join(c.cypher for c in ALL_CATEGORIES)
    # These must appear in inventory Cypher (they drive category browsing)
    must_have_in_inventory = [
        "DUPLICATE_OF", "SIMILAR_TO", "PART_OF", "REFERENCES",
        "MENTIONS", "LOCATED_AT", "OCCURRED_DURING",
        "DEPICTS", "CONTAINS_FACE", "MATCHED_TO",
        "IS_APPLICATION", "IS_BINARY", "MADE_BY",
        "DEPENDS_ON", "LICENSED_UNDER", "HAS_VULNERABILITY", "SIGNED_BY",
        "SAME_PERSON_AS",
    ]
    for rel in must_have_in_inventory:
        assert rel in all_cypher, f"Relationship {rel!r} not in any inventory category Cypher"

    # Structural rels that appear in schema but don't drive category browsing
    # (they're used in graph explorer/query builder, not inventory drill-down)
    from src.dgraphai.api.schema import RELATIONSHIP_TYPES
    all_schema_rels = {r["id"] for r in RELATIONSHIP_TYPES}
    for rel in ["CHILD_OF", "TAGGED_WITH", "WITHIN", "OWNS", "HAS_VERSION", "SUPERSEDES"]:
        assert rel in all_schema_rels, f"Structural rel {rel!r} missing from schema"


def test_security_categories_exist():
    """Key security categories must exist."""
    security_cats = [
        "pii", "secrets", "certificates", "certs-expired",
        "vulnerabilities", "cve-critical",
    ]
    for cid in security_cats:
        assert get_category(cid) is not None, f"Security category {cid!r} missing"


def test_ai_categories_exist():
    """AI analysis categories must exist."""
    for cid in ["ai-enriched", "ai-negative-sentiment", "ai-action-items"]:
        assert get_category(cid) is not None, f"AI category {cid!r} missing"


def test_media_hierarchy():
    """Video → 4K → 4K+HDR hierarchy must exist."""
    assert get_category("video")    is not None
    assert get_category("video-4k") is not None
    assert get_category("video-4k-hdr") is not None
    assert get_category("video-4k").parent_id == "video"
    assert get_category("video-4k-hdr").parent_id == "video-4k"
