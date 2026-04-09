"""
RBAC + ABAC enforcement engine.

Permission format: "{resource}:{action}"
  graph:read          read graph nodes/edges
  graph:query         run Cypher queries
  mounts:read         list connectors
  mounts:write        add/remove connectors
  mounts:index        trigger indexing
  actions:propose     propose filesystem actions (creates approval request)
  actions:approve     approve/reject pending actions
  actions:execute     execute approved actions directly (elevated)
  users:read          list users
  users:write         manage users and role assignments
  roles:write         manage roles
  scanners:register   register scanner agents
  scanners:read       view scanner health
  admin:*             all permissions (tenant admin)

Built-in roles:
  admin    → admin:* (all)
  analyst  → graph:read, graph:query, mounts:read, actions:propose, scanners:read
  viewer   → graph:read, mounts:read, scanners:read
  agent    → scanners:register, scanners:read (for scanner agent API keys)
"""
from __future__ import annotations

from functools import wraps
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.fsgraph.db.models import Role, RoleAssignment
from src.fsgraph.db.session import get_db

# ── Built-in role permission sets ─────────────────────────────────────────────

BUILTIN_PERMISSIONS: dict[str, set[str]] = {
    "admin":   {"admin:*"},
    "analyst": {
        "graph:read", "graph:query",
        "mounts:read", "mounts:index",
        "actions:propose",
        "scanners:read",
        "users:read",
    },
    "viewer": {
        "graph:read",
        "mounts:read",
        "scanners:read",
    },
    "agent": {
        "scanners:register",
        "scanners:read",
        "graph:read",  # needed for delta sync
    },
}


def _expand_permissions(permissions: set[str]) -> set[str]:
    """Expand wildcard permissions like 'admin:*' into all known permissions."""
    if "admin:*" in permissions:
        # Admin gets everything
        all_perms = set()
        for p in BUILTIN_PERMISSIONS.values():
            all_perms.update(p)
        # Plus all explicit permissions
        all_perms.update(permissions)
        return all_perms
    return permissions


async def load_user_permissions(
    user_id: UUID,
    tenant_id: UUID,
    db: AsyncSession,
) -> tuple[list[str], set[str]]:
    """
    Load all roles and permissions for a user within a tenant.
    Returns (role_names, permission_set).
    """
    result = await db.execute(
        select(RoleAssignment, Role)
        .join(Role, RoleAssignment.role_id == Role.id)
        .where(
            RoleAssignment.user_id  == user_id,
            RoleAssignment.tenant_id == tenant_id,
        )
    )
    rows = result.all()

    role_names:  list[str] = []
    permissions: set[str]  = set()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    for assignment, role in rows:
        # Skip expired assignments
        if assignment.expires_at and assignment.expires_at < now:
            continue

        role_names.append(role.name)

        # Built-in role permissions
        builtin = BUILTIN_PERMISSIONS.get(role.role_type, set())
        permissions.update(builtin)

        # Custom role permissions (stored in DB)
        if role.permissions:
            permissions.update(role.permissions)

    return role_names, _expand_permissions(permissions)


def has_permission(permission: str) -> Any:
    """
    FastAPI dependency factory — requires a specific permission.

    Usage:
        @router.get("/sensitive", dependencies=[Depends(has_permission("graph:query"))])
    """
    from src.fsgraph.auth.oidc import get_auth_context, AuthContext

    async def _check(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not _is_allowed(auth.permissions, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return auth

    return Depends(_check)


def require_permissions(*permissions: str) -> Any:
    """Require ALL of the listed permissions."""
    from src.fsgraph.auth.oidc import get_auth_context, AuthContext

    async def _check(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        missing = [p for p in permissions if not _is_allowed(auth.permissions, p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissions required: {', '.join(missing)}",
            )
        return auth

    return Depends(_check)


def _is_allowed(user_perms: set[str], required: str) -> bool:
    """
    Check if required permission is satisfied.
    Supports wildcard matching: 'admin:*' satisfies any 'admin:x'.
    """
    if required in user_perms:
        return True
    # Check wildcard: 'graph:*' satisfies 'graph:read'
    prefix = required.split(":")[0]
    return f"{prefix}:*" in user_perms or "admin:*" in user_perms


# ── Scope enforcement ──────────────────────────────────────────────────────────

def build_scope_filter(assignments: list[Any], resource_type: str) -> dict[str, Any] | None:
    """
    Build a graph query filter from a user's scoped role assignments.
    Returns None if user has unscoped (global) access.
    Returns a filter dict if access is scoped.

    The filter is applied to Cypher queries via WHERE clause injection.
    """
    scoped = [a for a in assignments if a.scope_type is not None]
    if not scoped:
        return None  # Global access, no filter needed

    filters: list[dict] = []
    for assignment in scoped:
        if assignment.scope_type == "connector":
            filters.append({
                "type":  "connector",
                "ids":   assignment.scope_value.get("connector_ids", []),
            })
        elif assignment.scope_type == "tag":
            filters.append({
                "type": "tag",
                "tags": assignment.scope_value.get("tags", []),
            })
        elif assignment.scope_type == "attribute":
            filters.append({
                "type":    "attribute",
                "filters": assignment.scope_value.get("filters", {}),
            })

    return {"operator": "OR", "conditions": filters} if filters else None


def scope_filter_to_cypher(scope_filter: dict | None) -> str:
    """
    Convert a scope filter to a Cypher WHERE clause fragment.
    Returns "" (no restriction) if scope_filter is None.
    """
    if not scope_filter:
        return ""

    clauses: list[str] = []
    for cond in scope_filter.get("conditions", []):
        if cond["type"] == "connector":
            ids = ", ".join(f'"{i}"' for i in cond["ids"])
            clauses.append(f"n.connector_id IN [{ids}]")
        elif cond["type"] == "tag":
            for tag in cond["tags"]:
                clauses.append(f"'{tag}' IN n.tags")
        elif cond["type"] == "attribute":
            for k, v in cond["filters"].items():
                clauses.append(f"n.{k} = '{v}'")

    if not clauses:
        return ""

    op = scope_filter.get("operator", "OR")
    return f"({f' {op} '.join(clauses)})"
