"""
Tenant management API.
Tenant creation is handled by the platform admin (not self-service yet).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.fsgraph.db.models import Role, Tenant, User, RoleAssignment
from src.fsgraph.db.session import get_db
from src.fsgraph.auth.oidc import get_auth_context, AuthContext
from src.fsgraph.rbac.engine import BUILTIN_PERMISSIONS, require_permissions

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

BUILTIN_ROLES = ["admin", "analyst", "viewer", "agent"]


async def _create_builtin_roles(tenant_id: Any, db: AsyncSession) -> None:
    """Create the four built-in roles for a new tenant."""
    for role_type in BUILTIN_ROLES:
        role = Role(
            tenant_id   = tenant_id,
            name        = role_type,
            role_type   = role_type,
            description = f"Built-in {role_type} role",
            permissions = list(BUILTIN_PERMISSIONS.get(role_type, set())),
            is_system   = True,
        )
        db.add(role)


class CreateTenantRequest(BaseModel):
    slug:  str
    name:  str
    plan:  str = "starter"
    admin_email: str


@router.post("")
async def create_tenant(
    req: CreateTenantRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Create a new tenant. Platform-level operation.
    In production, protect with a platform admin API key.
    """
    # Check slug uniqueness
    existing = await db.execute(
        select(Tenant).where(Tenant.slug == req.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Slug {req.slug!r} already taken")

    tenant = Tenant(slug=req.slug, name=req.name, plan=req.plan)
    db.add(tenant)
    await db.flush()

    # Create built-in roles
    await _create_builtin_roles(tenant.id, db)
    await db.flush()

    return {
        "id":   str(tenant.id),
        "slug": tenant.slug,
        "name": tenant.name,
        "plan": tenant.plan,
        "status": "created",
        "next_steps": [
            f"Configure OIDC: POST /api/auth/oidc",
            f"Invite admin user: POST /api/tenants/{tenant.id}/users",
        ],
    }


@router.get("/me")
async def get_my_tenant(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the current tenant's details."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == auth.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "id":    str(tenant.id),
        "slug":  tenant.slug,
        "name":  tenant.name,
        "plan":  tenant.plan,
        "limits": {
            "max_users":      tenant.max_users,
            "max_connectors": tenant.max_connectors,
            "max_nodes":      tenant.max_nodes,
        },
    }


@router.get("/me/users")
async def list_users(
    auth: AuthContext = Depends(require_permissions("users:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all users in this tenant."""
    result = await db.execute(
        select(User).where(User.tenant_id == auth.tenant_id, User.is_active == True)  # noqa
    )
    users = result.scalars().all()
    return [
        {
            "id":           str(u.id),
            "email":        u.email,
            "display_name": u.display_name,
            "last_login":   u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


@router.get("/me/roles")
async def list_roles(
    auth: AuthContext = Depends(require_permissions("roles:write")),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all roles for this tenant."""
    result = await db.execute(
        select(Role).where(Role.tenant_id == auth.tenant_id)
    )
    roles = result.scalars().all()
    return [
        {
            "id":          str(r.id),
            "name":        r.name,
            "role_type":   r.role_type,
            "permissions": r.permissions,
            "is_system":   r.is_system,
        }
        for r in roles
    ]
