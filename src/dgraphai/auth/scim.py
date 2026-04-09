"""
SCIM 2.0 provisioning endpoint.

Allows enterprise IdPs (Okta, Azure AD, OneLogin, etc.) to automatically:
  - Create user accounts when employees join
  - Deprovision accounts when employees leave
  - Sync group memberships → role assignments
  - Update profile attributes

SCIM is stateless from the IdP side — they call our API to manage users.
Each tenant gets a unique SCIM base URL and bearer token.

Endpoint: /api/scim/v2/{tenant_id}/...
Auth: Bearer <scim_token> (per-tenant, stored as SCIMConfig)

Implemented:
  GET  /Users            — list users (with filter support)
  GET  /Users/{id}       — get single user
  POST /Users            — provision new user
  PUT  /Users/{id}       — replace user (full update)
  PATCH /Users/{id}      — update user (partial, Operations format)
  DELETE /Users/{id}     — deprovision user
  GET  /Groups           — list groups (mapped to roles)
  POST /Groups           — create group → role
  PATCH /Groups/{id}     — update group members → role assignments
  GET  /ServiceProviderConfig — SCIM capabilities
  GET  /Schemas          — user/group schema definitions
"""
from __future__ import annotations
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.db.models import User, Tenant, SCIMConfig
from src.dgraphai.db.session import get_db

router = APIRouter(prefix="/api/scim/v2", tags=["scim"])

SCIM_CONTENT_TYPE = "application/scim+json"


# ── SCIM auth ──────────────────────────────────────────────────────────────────

async def get_scim_tenant(
    tenant_id: str,
    request:   Request,
    db:        AsyncSession = Depends(get_db),
) -> Tenant:
    """Validate SCIM bearer token and return the tenant."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token     = auth_header[7:]
    tok_hash  = hashlib.sha256(token.encode()).hexdigest()

    result = await db.execute(
        select(SCIMConfig).where(
            SCIMConfig.tenant_id  == uuid.UUID(tenant_id),
            SCIMConfig.token_hash == tok_hash,
            SCIMConfig.is_active  == True,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=401, detail="Invalid SCIM token")

    tenant_r = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant   = tenant_r.scalar_one_or_none()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Update last used timestamp
    config.last_used_at = datetime.now(timezone.utc)
    return tenant


# ── User endpoints ─────────────────────────────────────────────────────────────

@router.get("/{tenant_id}/Users")
async def list_scim_users(
    tenant_id: str,
    request:   Request,
    startIndex: int = 1,
    count:      int = 100,
    filter:     str | None = None,
    db:         AsyncSession = Depends(get_db),
):
    tenant = await get_scim_tenant(tenant_id, request, db)
    q = select(User).where(User.tenant_id == tenant.id, User.is_active == True)

    # SCIM filter: userName eq "alice@example.com"
    if filter and "userName eq" in filter.lower():
        email = filter.split('"')[1]
        q = q.where(User.email == email)

    result  = await db.execute(q)
    users   = result.scalars().all()
    total   = len(users)
    paged   = users[startIndex - 1 : startIndex - 1 + count]

    return JSONResponse(content={
        "schemas":      ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": total,
        "startIndex":   startIndex,
        "itemsPerPage": len(paged),
        "Resources":    [_user_to_scim(u, tenant_id) for u in paged],
    }, media_type=SCIM_CONTENT_TYPE)


@router.get("/{tenant_id}/Users/{user_id}")
async def get_scim_user(
    tenant_id: str, user_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    tenant = await get_scim_tenant(tenant_id, request, db)
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return JSONResponse(content=_user_to_scim(user, tenant_id), media_type=SCIM_CONTENT_TYPE)


@router.post("/{tenant_id}/Users", status_code=201)
async def create_scim_user(
    tenant_id: str, body: dict, request: Request, db: AsyncSession = Depends(get_db)
):
    """Provision a new user from IdP."""
    tenant = await get_scim_tenant(tenant_id, request, db)

    email    = _extract_email(body)
    name     = _extract_name(body)
    ext_id   = body.get("externalId", "")

    if not email:
        raise HTTPException(status_code=400, detail="userName (email) required")

    # Idempotent: return existing if already provisioned
    existing = await db.execute(
        select(User).where(User.email == email, User.tenant_id == tenant.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already exists")

    # Determine role from SCIM groups
    role = _extract_role(body)

    user = User(
        tenant_id      = tenant.id,
        email          = email,
        display_name   = name,
        name           = name,
        external_id    = ext_id,
        idp_provider   = "scim",
        is_active      = body.get("active", True),
        email_verified = True,   # IdP-provisioned = trusted
        role           = role,
    )
    db.add(user)
    await db.flush()

    # Assign role
    from src.dgraphai.rbac.engine import assign_builtin_role
    await assign_builtin_role(user.id, tenant.id, role, db)

    return JSONResponse(
        status_code=201,
        content=_user_to_scim(user, tenant_id),
        media_type=SCIM_CONTENT_TYPE,
    )


@router.put("/{tenant_id}/Users/{user_id}")
async def replace_scim_user(
    tenant_id: str, user_id: str, body: dict,
    request: Request, db: AsyncSession = Depends(get_db)
):
    """Full user replace (IdP sends complete user object)."""
    tenant = await get_scim_tenant(tenant_id, request, db)
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email        = _extract_email(body) or user.email
    user.display_name = _extract_name(body)  or user.display_name
    user.name         = user.display_name
    user.is_active    = body.get("active", True)
    user.external_id  = body.get("externalId", user.external_id)
    return JSONResponse(content=_user_to_scim(user, tenant_id), media_type=SCIM_CONTENT_TYPE)


@router.patch("/{tenant_id}/Users/{user_id}")
async def patch_scim_user(
    tenant_id: str, user_id: str, body: dict,
    request: Request, db: AsyncSession = Depends(get_db)
):
    """Partial update via SCIM Operations (handles deprovisioning)."""
    tenant = await get_scim_tenant(tenant_id, request, db)
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for op in body.get("Operations", []):
        path  = op.get("path", "")
        value = op.get("value")
        if path == "active" or (not path and isinstance(value, dict) and "active" in value):
            active = value if isinstance(value, bool) else (value or {}).get("active", True)
            user.is_active = active
            if not active:
                # Deprovision: revoke all sessions and API keys
                from src.dgraphai.db.models import UserSession, APIKey
                await db.execute(
                    update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at == None)
                    .values(revoked_at=datetime.now(timezone.utc))
                )
                await db.execute(
                    update(APIKey).where(APIKey.user_id == user.id, APIKey.revoked_at == None)
                    .values(revoked_at=datetime.now(timezone.utc))
                )
        elif path in ("userName", "emails[type eq \"work\"].value"):
            user.email = str(value)
        elif path.startswith("name"):
            user.display_name = str(value)
            user.name = user.display_name

    return JSONResponse(content=_user_to_scim(user, tenant_id), media_type=SCIM_CONTENT_TYPE)


@router.delete("/{tenant_id}/Users/{user_id}", status_code=204)
async def delete_scim_user(
    tenant_id: str, user_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    """Hard deprovision — marks user inactive."""
    tenant = await get_scim_tenant(tenant_id, request, db)
    await db.execute(
        update(User).where(
            User.id == uuid.UUID(user_id), User.tenant_id == tenant.id
        ).values(is_active=False)
    )


# ── Group endpoints (maps to roles) ───────────────────────────────────────────

@router.get("/{tenant_id}/Groups")
async def list_scim_groups(
    tenant_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    tenant = await get_scim_tenant(tenant_id, request, db)
    from src.dgraphai.db.models import Role
    result = await db.execute(select(Role).where(Role.tenant_id == tenant.id))
    roles  = result.scalars().all()
    return JSONResponse(content={
        "schemas":      ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(roles),
        "startIndex":   1,
        "itemsPerPage": len(roles),
        "Resources":    [_role_to_scim_group(r, tenant_id) for r in roles],
    }, media_type=SCIM_CONTENT_TYPE)


@router.patch("/{tenant_id}/Groups/{group_id}")
async def patch_scim_group(
    tenant_id: str, group_id: str, body: dict,
    request: Request, db: AsyncSession = Depends(get_db)
):
    """Sync group members → role assignments."""
    tenant = await get_scim_tenant(tenant_id, request, db)
    from src.dgraphai.db.models import Role, RoleAssignment
    from src.dgraphai.rbac.engine import assign_builtin_role

    role_r = await db.execute(
        select(Role).where(Role.id == uuid.UUID(group_id), Role.tenant_id == tenant.id)
    )
    role = role_r.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Group/role not found")

    for op in body.get("Operations", []):
        if op.get("op", "").lower() == "add":
            for member in op.get("value", []):
                uid_str = member.get("value", "")
                if uid_str:
                    await assign_builtin_role(uuid.UUID(uid_str), tenant.id, role.name, db)
        elif op.get("op", "").lower() == "remove":
            for member in op.get("value", []):
                uid_str = member.get("value", "")
                if uid_str:
                    await db.execute(
                        delete(RoleAssignment).where(
                            RoleAssignment.user_id == uuid.UUID(uid_str),
                            RoleAssignment.role_id == role.id,
                        )
                    )
    return JSONResponse(content=_role_to_scim_group(role, tenant_id), media_type=SCIM_CONTENT_TYPE)


# ── Discovery ──────────────────────────────────────────────────────────────────

@router.get("/{tenant_id}/ServiceProviderConfig")
async def service_provider_config(tenant_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await get_scim_tenant(tenant_id, request, db)
    return JSONResponse(content={
        "schemas":  ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch":    {"supported": True},
        "bulk":     {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter":   {"supported": True, "maxResults": 500},
        "changePassword": {"supported": False},
        "sort":     {"supported": False},
        "etag":     {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "OAuth Bearer Token"}],
    }, media_type=SCIM_CONTENT_TYPE)


# ── SCIM token management (admin API) ──────────────────────────────────────────

from src.dgraphai.auth.oidc import get_auth_context, AuthContext

mgmt_router = APIRouter(prefix="/api/admin/scim", tags=["scim"])


@mgmt_router.post("/token")
async def create_scim_token(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate a SCIM provisioning token for this tenant (admin only)."""
    if "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Admin required")

    raw_token = secrets.token_urlsafe(48)
    tok_hash  = hashlib.sha256(raw_token.encode()).hexdigest()

    # Revoke existing token if any
    await db.execute(
        update(SCIMConfig).where(SCIMConfig.tenant_id == auth.tenant_id)
        .values(is_active=False)
    )

    config = SCIMConfig(
        tenant_id  = auth.tenant_id,
        token_hash = tok_hash,
        is_active  = True,
        created_by = auth.user_id,
    )
    db.add(config)
    await db.flush()

    base_url_env = __import__("os").getenv("APP_URL", "https://app.dgraph.ai")
    return {
        "token":    raw_token,
        "base_url": f"{base_url_env}/api/scim/v2/{auth.tenant_id}",
        "warning":  "Save this token. It will not be shown again.",
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _user_to_scim(user: User, tenant_id: str) -> dict:
    return {
        "schemas":    ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id":         str(user.id),
        "externalId": user.external_id or "",
        "userName":   user.email,
        "name":       {"formatted": user.display_name or user.name or ""},
        "emails":     [{"value": user.email, "type": "work", "primary": True}],
        "active":     user.is_active,
        "meta": {
            "resourceType": "User",
            "location":     f"/api/scim/v2/{tenant_id}/Users/{user.id}",
        },
    }


def _role_to_scim_group(role, tenant_id: str) -> dict:
    return {
        "schemas":     ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id":          str(role.id),
        "displayName": role.name,
        "meta": {
            "resourceType": "Group",
            "location":     f"/api/scim/v2/{tenant_id}/Groups/{role.id}",
        },
    }


def _extract_email(body: dict) -> str:
    # SCIM userName is typically email
    un = body.get("userName", "")
    if un:
        return un
    emails = body.get("emails", [])
    if emails:
        return emails[0].get("value", "")
    return ""


def _extract_name(body: dict) -> str:
    name = body.get("name", {})
    if isinstance(name, dict):
        return name.get("formatted") or f"{name.get('givenName','')} {name.get('familyName','')}".strip()
    return str(name)


def _extract_role(body: dict) -> str:
    groups = body.get("groups", [])
    if groups:
        display = groups[0].get("display", "").lower()
        if display in ("admin", "analyst", "viewer"):
            return display
    return "analyst"
