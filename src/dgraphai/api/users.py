"""
User management API — invitations, profile, team management.
"""
from __future__ import annotations
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.models import User, Tenant
from src.dgraphai.db.session import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


class InviteRequest(BaseModel):
    email: EmailStr
    role:  str = "analyst"
    name:  str | None = None


class AcceptInviteRequest(BaseModel):
    token:    str
    password: str
    name:     str


class UpdateProfileRequest(BaseModel):
    name:  str | None = None
    email: EmailStr | None = None


# ── Invite ─────────────────────────────────────────────────────────────────────

@router.post("/invite", status_code=201)
async def invite_user(
    req:  InviteRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Invite a user to join the tenant.
    Sends an email with a sign-up link. The invite expires in 7 days.
    Admin only.
    """
    if "admin:*" not in auth.permissions and "users:write" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Admin permission required")

    # Check not already a member
    existing = await db.execute(
        select(User).where(User.email == req.email, User.tenant_id == auth.tenant_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already a member of this tenant")

    # Get inviter info
    inviter = await db.execute(select(User).where(User.id == auth.user_id))
    inviter_user = inviter.scalar_one_or_none()
    inviter_name = (inviter_user.display_name or inviter_user.email) if inviter_user else "Someone"

    # Get tenant info
    tenant_r = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant   = tenant_r.scalar_one_or_none()

    # Create invite token
    token    = secrets.token_urlsafe(48)
    tok_hash = hashlib.sha256(token.encode()).hexdigest()

    # Store as a pending UserInvite record
    from src.dgraphai.db.models import UserInvite
    invite = UserInvite(
        tenant_id   = auth.tenant_id,
        invited_by  = auth.user_id,
        email       = req.email,
        role        = req.role,
        token_hash  = tok_hash,
        expires_at  = datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    await db.flush()

    # Send invite email
    from src.dgraphai.auth.email import send_invitation_email
    try:
        await send_invitation_email(
            req.email, inviter_name,
            tenant.name if tenant else "dgraph.ai",
            token, req.role,
        )
    except Exception:
        pass

    return {
        "status":  "invited",
        "email":   req.email,
        "role":    req.role,
        "expires": invite.expires_at.isoformat(),
    }


@router.post("/accept-invite")
async def accept_invite(
    req: AcceptInviteRequest,
    db:  AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Accept an invitation, create an account, and return a JWT."""
    from src.dgraphai.db.models import UserInvite
    from src.dgraphai.auth.local import pwd_ctx, _issue_jwt, _validate_password

    tok_hash = hashlib.sha256(req.token.encode()).hexdigest()
    invite_r = await db.execute(
        select(UserInvite).where(
            UserInvite.token_hash == tok_hash,
            UserInvite.used_at    == None,
        )
    )
    invite = invite_r.scalar_one_or_none()
    if not invite or invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")

    _validate_password(req.password)

    # Create user
    from src.dgraphai.db.models import LocalCredential
    user = User(
        tenant_id    = invite.tenant_id,
        email        = invite.email,
        display_name = req.name,
        name         = req.name,
        is_active    = True,
        email_verified = True,  # invite = verified email
    )
    db.add(user)
    await db.flush()

    cred = LocalCredential(user_id=user.id, password_hash=pwd_ctx.hash(req.password))
    db.add(cred)

    # Assign invited role
    from src.dgraphai.rbac.engine import assign_builtin_role
    await assign_builtin_role(user.id, invite.tenant_id, invite.role, db)

    invite.used_at = datetime.now(timezone.utc)

    tenant_r = await db.execute(select(Tenant).where(Tenant.id == invite.tenant_id))
    tenant   = tenant_r.scalar_one_or_none()

    return {
        "token": _issue_jwt(user, tenant),
        "user":  {"id": str(user.id), "email": user.email, "name": user.display_name},
    }


# ── Team management ─────────────────────────────────────────────────────────────

@router.get("")
async def list_users(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all users in this tenant."""
    result = await db.execute(
        select(User).where(User.tenant_id == auth.tenant_id, User.is_active == True)
        .order_by(User.created_at)
    )
    users = result.scalars().all()
    return [
        {
            "id":             str(u.id),
            "email":          u.email,
            "name":           u.display_name or u.name,
            "email_verified": u.email_verified,
            "role":           u.role,
            "last_login":     u.last_login.isoformat() if u.last_login else None,
            "created_at":     u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.get("/me")
async def get_profile(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the current user's profile."""
    result = await db.execute(select(User).where(User.id == auth.user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check MFA status
    from src.dgraphai.db.models import MFAConfig
    mfa_r = await db.execute(
        select(MFAConfig).where(MFAConfig.user_id == auth.user_id, MFAConfig.is_active == True)
    )
    has_mfa = mfa_r.scalar_one_or_none() is not None

    # Get tenant
    tenant_r = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant   = tenant_r.scalar_one_or_none()

    return {
        "id":             str(user.id),
        "email":          user.email,
        "name":           user.display_name or user.name,
        "email_verified": user.email_verified,
        "role":           user.role,
        "mfa_enabled":    has_mfa,
        "tenant": {
            "id":   str(tenant.id),
            "name": tenant.name,
            "slug": tenant.slug,
            "plan": tenant.plan,
        } if tenant else None,
    }


@router.patch("/me")
async def update_profile(
    req:  UpdateProfileRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update current user's profile."""
    result = await db.execute(select(User).where(User.id == auth.user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.name:
        user.display_name = req.name
        user.name = req.name
    if req.email and req.email != user.email:
        # Require re-verification on email change
        user.email          = req.email
        user.email_verified = False

    return {"status": "updated"}


@router.delete("/{user_id}")
async def remove_user(
    user_id: str,
    auth:    AuthContext = Depends(get_auth_context),
    db:      AsyncSession = Depends(get_db),
) -> dict:
    """Remove a user from the tenant (admin only)."""
    if "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Admin required")
    if str(auth.user_id) == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    await db.execute(
        update(User).where(
            User.id == uuid.UUID(user_id),
            User.tenant_id == auth.tenant_id,
        ).values(is_active=False)
    )
    return {"status": "removed"}
