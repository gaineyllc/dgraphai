"""
Unit tests — graph schema API definitions.
"""
import pytest

from src.dgraphai.api.schema import NODE_TYPES, RELATIONSHIP_TYPES, _group_props

pytestmark = pytest.mark.unit


def test_node_type_count():
    assert len(NODE_TYPES) >= 15, "Expected at least 15 node types"


def test_relationship_type_count():
    assert len(RELATIONSHIP_TYPES) >= 20, "Expected at least 20 relationship types"


def test_all_node_types_have_required_fields():
    for nt in NODE_TYPES:
        assert nt.get("id"),    f"Node type missing 'id': {nt}"
        assert nt.get("label"), f"Node type missing 'label': {nt}"
        assert nt.get("icon"),  f"Node type missing 'icon': {nt}"
        assert nt.get("color"), f"Node type missing 'color': {nt}"


def test_file_node_has_all_property_groups():
    file_nt = next(n for n in NODE_TYPES if n["id"] == "File")
    props = file_nt.get("properties", [])
    groups = {p["group"] for p in props}
    required_groups = {"Identity", "Storage", "AI", "Video", "Image", "Security", "Code", "Document"}
    missing = required_groups - groups
    assert not missing, f"File node type missing property groups: {missing}"


def test_file_node_property_count():
    file_nt = next(n for n in NODE_TYPES if n["id"] == "File")
    assert len(file_nt["properties"]) >= 60


def test_all_properties_have_type():
    valid_types = {"string", "integer", "float", "boolean", "datetime"}
    for nt in NODE_TYPES:
        for prop in nt.get("properties", []):
            assert prop.get("type") in valid_types, (
                f"{nt['id']}.{prop.get('key')}: invalid type {prop.get('type')!r}"
            )


def test_relationship_types_have_from_to():
    for rel in RELATIONSHIP_TYPES:
        assert rel.get("from"), f"Rel {rel.get('id')!r} missing 'from'"
        assert rel.get("to"),   f"Rel {rel.get('id')!r} missing 'to'"
        assert isinstance(rel["from"], list)
        assert isinstance(rel["to"],   list)


def test_all_relationships_have_description():
    for rel in RELATIONSHIP_TYPES:
        assert rel.get("description"), f"Rel {rel.get('id')!r} missing description"


def test_group_props_groups_correctly():
    props = [
        {"key": "name",  "label": "Name",  "type": "string", "group": "Identity"},
        {"key": "size",  "label": "Size",  "type": "integer","group": "Storage"},
        {"key": "color", "label": "Color", "type": "string", "group": "Identity"},
    ]
    grouped = _group_props(props)
    assert "Identity" in grouped
    assert "Storage"  in grouped
    assert len(grouped["Identity"]) == 2
    assert len(grouped["Storage"])  == 1


def test_no_duplicate_node_type_ids():
    ids = [n["id"] for n in NODE_TYPES]
    assert len(ids) == len(set(ids)), "Duplicate node type IDs"


def test_no_duplicate_rel_type_ids():
    ids = [r["id"] for r in RELATIONSHIP_TYPES]
    assert len(ids) == len(set(ids)), "Duplicate relationship type IDs"


def test_vulnerability_node_has_cvss_fields():
    vuln = next(n for n in NODE_TYPES if n["id"] == "Vulnerability")
    keys = {p["key"] for p in vuln.get("properties", [])}
    assert "cvss_score"    in keys
    assert "cvss_severity" in keys
    assert "exploit_available"  in keys
    assert "actively_exploited" in keys


def test_certificate_node_has_expiry_fields():
    cert = next(n for n in NODE_TYPES if n["id"] == "Certificate")
    keys = {p["key"] for p in cert.get("properties", [])}
    assert "is_expired"        in keys
    assert "days_until_expiry" in keys
    assert "is_ca"             in keys
    assert "key_size"          in keys
