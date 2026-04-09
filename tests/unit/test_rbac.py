"""
Unit tests — RBAC engine (P0 auth).
Tests permission logic using the actual BUILTIN_PERMISSIONS sets.
"""
import pytest
from src.dgraphai.rbac.engine import BUILTIN_PERMISSIONS, load_user_permissions

pytestmark = pytest.mark.unit


def perms(role: str) -> set[str]:
    return BUILTIN_PERMISSIONS.get(role, set())


def has(permissions: set[str], required: str) -> bool:
    """Check if a permission set grants the required permission."""
    if "admin:*" in permissions:
        return True
    if required in permissions:
        return True
    # Namespace wildcard: queries:* covers queries:read
    ns = required.split(":")[0]
    return f"{ns}:*" in permissions


class TestBuiltinRoles:
    def test_admin_has_wildcard(self):
        assert "admin:*" in perms("admin")

    def test_admin_can_do_anything(self):
        admin_perms = perms("admin")
        for action in ["graph:read", "graph:query", "mounts:write",
                        "users:write", "roles:write", "actions:execute"]:
            assert has(admin_perms, action), f"Admin missing {action}"

    def test_analyst_cannot_write_users(self):
        assert not has(perms("analyst"), "users:write")

    def test_analyst_cannot_approve_actions(self):
        assert not has(perms("analyst"), "actions:approve")

    def test_analyst_can_propose_actions(self):
        assert has(perms("analyst"), "actions:propose")

    def test_viewer_read_only(self):
        viewer = perms("viewer")
        assert has(viewer,  "graph:read")
        assert not has(viewer, "graph:query")
        assert not has(viewer, "mounts:write")
        assert not has(viewer, "actions:propose")

    def test_agent_can_register(self):
        assert has(perms("agent"), "scanners:register")

    def test_agent_cannot_write_users(self):
        assert not has(perms("agent"), "users:write")

    def test_unknown_role_empty(self):
        assert perms("nonexistent") == set()


class TestPermissionInheritance:
    def test_admin_superset_of_analyst(self):
        """Admin must have at least all analyst permissions."""
        admin_perms  = perms("admin")
        analyst_perms = perms("analyst")
        for perm in analyst_perms:
            assert has(admin_perms, perm), f"Admin missing analyst perm: {perm}"

    def test_analyst_superset_of_viewer(self):
        analyst_perms = perms("analyst")
        viewer_perms  = perms("viewer")
        for perm in viewer_perms:
            assert has(analyst_perms, perm), f"Analyst missing viewer perm: {perm}"

    def test_no_role_has_empty_permissions(self):
        for role, ps in BUILTIN_PERMISSIONS.items():
            assert len(ps) > 0, f"Role {role!r} has no permissions"


class TestPermissionFormat:
    def test_all_permissions_have_colon(self):
        all_perms = set()
        for ps in BUILTIN_PERMISSIONS.values():
            all_perms.update(ps)
        for p in all_perms:
            assert ":" in p or p == "admin:*", f"Permission {p!r} not in resource:action format"

    def test_permission_resources_known(self):
        known_resources = {
            "admin", "graph", "mounts", "actions",
            "users", "roles", "scanners",
        }
        all_perms = set()
        for ps in BUILTIN_PERMISSIONS.values():
            all_perms.update(ps)
        for p in all_perms:
            ns = p.split(":")[0]
            assert ns in known_resources, f"Unknown resource namespace: {ns!r} in {p!r}"
