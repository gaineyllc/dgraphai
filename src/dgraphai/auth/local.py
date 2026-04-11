"""
Local authentication — email/password with bcrypt hashing.
Supports:
  - Signup with email verification
  - Login returning a signed JWT
  - Password reset via email token
  - MFA (TOTP) enrollment and verification
  - Account lockout after N failed attempts
  - Session management (list + revoke)
"""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
import bcrypt as _bcrypt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from src.dgraphai.db.models import (
    Tenant, User, LocalCredential, EmailVerificationToken,
    PasswordResetToken, MFAConfig, UserSession, APIKey,
)
from src.dgraphai.db.session import get_db
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.auth.email import send_verification_email, send_password_reset_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Password hashing — bcrypt direct (passlib 1.7.4 incompatible with bcrypt 4.x+)
class _PwdCtx:
    """Drop-in passlib.hash() / .verify() using bcrypt directly."""
    def hash(self, password: str) -> str:
        return _bcrypt.hashpw(password.encode()[:72], _bcrypt.gensalt(rounds=12)).decode()
    def verify(self, password: str, hashed: str) -> bool:
        try:
            return _bcrypt.checkpw(password.encode()[:72], hashed.encode())
        except Exception:
            return False

pwd_ctx = _PwdCtx()

# JWT config
JWT_SECRET   = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGO     = "HS256"
JWT_EXPIRY_H = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

# Account lockout
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES     = 15


# ── Pydantic models ────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email:     EmailStr
    password:  str
    name:      str
    company:   str | None = None
    plan:      str = "starter"

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str
    mfa_code: str | None = None  # TOTP code if MFA enrolled

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token:        str
    new_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str

class MFAEnrollResponse(BaseModel):
    secret:      str
    qr_url:      str
    backup_codes: list[str]

class MFAVerifyRequest(BaseModel):
    code: str

class CreateAPIKeyRequest(BaseModel):
    name:       str
    expires_days: int | None = None  # None = no expiry


# ── Signup ─────────────────────────────────────────────────────────────────────

@router.post("/signup", status_code=201)
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Create a new tenant + admin user.
    Sends email verification. Account usable immediately (email verification
    is soft — shows a banner but doesn't block access).
    """
    # Validate password strength
    _validate_password(req.password)

    # Check email not already registered globally
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Create tenant
    slug = _slugify(req.company or req.email.split("@")[0])
    slug = await _unique_slug(slug, db)
    tenant = Tenant(name=req.company or req.name, slug=slug, plan=req.plan)
    db.add(tenant)
    await db.flush()

    # Create admin user
    user = User(
        tenant_id    = tenant.id,
        email        = req.email,
        display_name = req.name,
        is_active    = True,
        email_verified = False,
    )
    db.add(user)
    await db.flush()

    # Create local credential
    cred = LocalCredential(
        user_id       = user.id,
        password_hash = pwd_ctx.hash(req.password),
    )
    db.add(cred)

    # Create admin role assignment
    from src.dgraphai.rbac.engine import assign_builtin_role
    await assign_builtin_role(user.id, tenant.id, "admin", db)

    # Email verification token
    token = _generate_token()
    ev = EmailVerificationToken(
        user_id    = user.id,
        token_hash = _hash_token(token),
        expires_at = datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db.add(ev)
    await db.flush()

    # Send verification email (non-blocking)
    try:
        await send_verification_email(req.email, req.name, token)
    except Exception:
        pass  # Don't fail signup if email fails

    # Queue onboarding email sequence
    try:
        from src.dgraphai.tasks.onboarding import queue_onboarding_sequence
        queue_onboarding_sequence(str(user.id), str(tenant.id), req.email, req.name)
    except Exception:
        pass  # Non-critical

    return {
        "user_id":    str(user.id),
        "tenant_id":  str(tenant.id),
        "email":      req.email,
        "message":    "Account created. Check your email to verify your address.",
        "token":      _issue_jwt(user, tenant),
    }


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(
    req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Email + password login.
    Returns JWT on success.
    If MFA is enrolled, requires mfa_code in the same request.
    """
    # Find user
    result = await db.execute(select(User).where(User.email == req.email, User.is_active == True))
    user = result.scalar_one_or_none()

    # Get credential
    cred = None
    if user:
        cr = await db.execute(select(LocalCredential).where(LocalCredential.user_id == user.id))
        cred = cr.scalar_one_or_none()

    # Constant-time invalid check (prevent timing attacks)
    if not user or not cred:
        await _constant_time_hash()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check lockout
    if cred.locked_until and cred.locked_until > datetime.now(timezone.utc):
        remaining = int((cred.locked_until - datetime.now(timezone.utc)).total_seconds() / 60)
        raise HTTPException(
            status_code=429,
            detail=f"Account temporarily locked. Try again in {remaining} minutes."
        )

    # Verify password
    if not pwd_ctx.verify(req.password, cred.password_hash):
        cred.failed_attempts  = (cred.failed_attempts or 0) + 1
        cred.last_failed_at   = datetime.now(timezone.utc)
        if cred.failed_attempts >= MAX_FAILED_ATTEMPTS:
            cred.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Reset failed attempts on success
    cred.failed_attempts = 0
    cred.locked_until    = None
    cred.last_login_at   = datetime.now(timezone.utc)

    # Check MFA
    mfa_result = await db.execute(
        select(MFAConfig).where(MFAConfig.user_id == user.id, MFAConfig.is_active == True)
    )
    mfa = mfa_result.scalar_one_or_none()
    if mfa:
        if not req.mfa_code:
            raise HTTPException(
                status_code=401,
                detail="MFA required",
                headers={"X-MFA-Required": "true"},
            )
        if not _verify_totp(mfa.secret, req.mfa_code):
            # Check backup codes
            if not _use_backup_code(mfa, req.mfa_code):
                raise HTTPException(status_code=401, detail="Invalid MFA code")

    # Get tenant
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    # Create session record
    session = UserSession(
        user_id    = user.id,
        tenant_id  = user.tenant_id,
        ip_address = request.client.host if request.client else None,
        user_agent = request.headers.get("user-agent", "")[:512],
        expires_at = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_H),
    )
    db.add(session)
    await db.flush()

    token = _issue_jwt(user, tenant, session_id=str(session.id))
    return {
        "token":      token,
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRY_H * 3600,
        "user": {
            "id":             str(user.id),
            "email":          user.email,
            "name":           user.display_name,
            "email_verified": user.email_verified,
            "tenant_id":      str(user.tenant_id),
            "plan":           tenant.plan if tenant else "starter",
        },
    }


# ── Email verification ─────────────────────────────────────────────────────────

@router.post("/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Verify email address using the token from the verification email."""
    token_hash = _hash_token(token)
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.used_at    == None,
        )
    )
    ev = result.scalar_one_or_none()
    if not ev or ev.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    ev.used_at = datetime.now(timezone.utc)
    await db.execute(update(User).where(User.id == ev.user_id).values(email_verified=True))
    return {"status": "verified", "message": "Email address verified successfully"}


@router.post("/resend-verification")
async def resend_verification(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """Resend email verification for the current user."""
    result = await db.execute(select(User).where(User.id == auth.user_id))
    user   = result.scalar_one_or_none()
    if not user or user.email_verified:
        return {"status": "ok"}

    token = _generate_token()
    ev = EmailVerificationToken(
        user_id    = user.id,
        token_hash = _hash_token(token),
        expires_at = datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db.add(ev)
    await db.flush()
    await send_verification_email(user.email, user.display_name or "", token)
    return {"status": "sent"}


# ── Password reset ─────────────────────────────────────────────────────────────

@router.post("/forgot-password")
async def forgot_password(req: PasswordResetRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Send password reset email. Always returns success to prevent enumeration."""
    result = await db.execute(select(User).where(User.email == req.email))
    user   = result.scalar_one_or_none()

    if user:
        token = _generate_token()
        pr = PasswordResetToken(
            user_id    = user.id,
            token_hash = _hash_token(token),
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(pr)
        await db.flush()
        try:
            await send_password_reset_email(user.email, user.display_name or "", token)
        except Exception:
            pass

    return {"status": "ok", "message": "If an account exists for that email, a reset link was sent"}


@router.post("/reset-password")
async def reset_password(req: PasswordResetConfirm, db: AsyncSession = Depends(get_db)) -> dict:
    """Reset password using token from email."""
    token_hash = _hash_token(req.token)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at    == None,
        )
    )
    pr = result.scalar_one_or_none()
    if not pr or pr.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    _validate_password(req.new_password)

    pr.used_at = datetime.now(timezone.utc)
    cr = await db.execute(select(LocalCredential).where(LocalCredential.user_id == pr.user_id))
    cred = cr.scalar_one_or_none()
    if cred:
        cred.password_hash  = pwd_ctx.hash(req.new_password)
        cred.failed_attempts = 0
        cred.locked_until   = None

    # Invalidate all existing sessions
    await db.execute(
        update(UserSession).where(
            UserSession.user_id == pr.user_id,
            UserSession.revoked_at == None,
        ).values(revoked_at=datetime.now(timezone.utc))
    )
    return {"status": "ok", "message": "Password reset successfully. Please log in again."}


# ── MFA ────────────────────────────────────────────────────────────────────────

@router.post("/mfa/enroll")
async def enroll_mfa(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """Begin MFA enrollment. Returns a TOTP secret and QR code URL."""
    import pyotp, qrcode, io, base64

    result = await db.execute(select(User).where(User.id == auth.user_id))
    user   = result.scalar_one()

    # Generate TOTP secret
    secret = pyotp.random_base32()
    totp   = pyotp.TOTP(secret)
    uri    = totp.provisioning_uri(name=user.email, issuer_name="dgraph.ai")

    # Generate QR code as base64 PNG
    qr  = qrcode.make(uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    # Generate backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]

    # Store pending enrollment (not active until verified)
    existing = await db.execute(select(MFAConfig).where(MFAConfig.user_id == auth.user_id))
    mfa = existing.scalar_one_or_none()
    if mfa:
        mfa.secret        = secret
        mfa.backup_codes  = backup_codes
        mfa.is_active     = False
    else:
        mfa = MFAConfig(
            user_id      = auth.user_id,
            secret       = secret,
            backup_codes = backup_codes,
            is_active    = False,
        )
        db.add(mfa)
    await db.flush()

    return {
        "secret":       secret,
        "qr_code_png":  qr_b64,
        "backup_codes": backup_codes,
        "uri":          uri,
    }


@router.post("/mfa/verify-enrollment")
async def verify_mfa_enrollment(
    req:  MFAVerifyRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """Verify a TOTP code to complete MFA enrollment."""
    result = await db.execute(
        select(MFAConfig).where(MFAConfig.user_id == auth.user_id)
    )
    mfa = result.scalar_one_or_none()
    if not mfa:
        raise HTTPException(status_code=404, detail="No pending MFA enrollment")

    if not _verify_totp(mfa.secret, req.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    mfa.is_active   = True
    mfa.enrolled_at = datetime.now(timezone.utc)
    return {"status": "enrolled", "message": "MFA enabled successfully. Save your backup codes."}


@router.delete("/mfa")
async def disable_mfa(
    req:  MFAVerifyRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """Disable MFA (requires current TOTP code to confirm)."""
    result = await db.execute(
        select(MFAConfig).where(MFAConfig.user_id == auth.user_id, MFAConfig.is_active == True)
    )
    mfa = result.scalar_one_or_none()
    if not mfa:
        raise HTTPException(status_code=404, detail="MFA not enabled")

    if not _verify_totp(mfa.secret, req.code) and not _use_backup_code(mfa, req.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    mfa.is_active    = False
    mfa.disabled_at  = datetime.now(timezone.utc)
    return {"status": "disabled"}


# ── Sessions ───────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[dict]:
    """List active sessions for the current user."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id    == auth.user_id,
            UserSession.revoked_at == None,
            UserSession.expires_at >  datetime.now(timezone.utc),
        ).order_by(UserSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "id":         str(s.id),
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        }
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    auth:       AuthContext = Depends(get_auth_context),
    db:         AsyncSession = Depends(get_db),
) -> dict:
    """Revoke a specific session (sign out that device)."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.id      == uuid.UUID(session_id),
            UserSession.user_id == auth.user_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.revoked_at = datetime.now(timezone.utc)
    return {"status": "revoked"}


@router.delete("/sessions")
async def revoke_all_sessions(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """Sign out of all devices."""
    await db.execute(
        update(UserSession).where(
            UserSession.user_id   == auth.user_id,
            UserSession.revoked_at == None,
        ).values(revoked_at=datetime.now(timezone.utc))
    )
    return {"status": "ok", "message": "All sessions revoked"}


# ── API keys ───────────────────────────────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[dict]:
    """List API keys for the current user (secrets never returned)."""
    result = await db.execute(
        select(APIKey).where(APIKey.user_id == auth.user_id, APIKey.revoked_at == None)
        .order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        {
            "id":           str(k.id),
            "name":         k.name,
            "prefix":       k.key_prefix,
            "created_at":   k.created_at.isoformat() if k.created_at else None,
            "expires_at":   k.expires_at.isoformat() if k.expires_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in keys
    ]


@router.post("/api-keys", status_code=201)
async def create_api_key(
    req:  CreateAPIKeyRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """
    Create a new API key.
    The full key is returned ONCE and never stored in plaintext.
    """
    raw_key  = f"dg_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix   = raw_key[:12]

    expires_at = None
    if req.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_days)

    key = APIKey(
        user_id    = auth.user_id,
        tenant_id  = auth.tenant_id,
        name       = req.name,
        key_hash   = key_hash,
        key_prefix = prefix,
        expires_at = expires_at,
    )
    db.add(key)
    await db.flush()

    return {
        "id":         str(key.id),
        "name":       req.name,
        "key":        raw_key,   # ONLY time full key is returned
        "prefix":     prefix,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "warning":    "Save this key now. It will never be shown again.",
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    auth:   AuthContext = Depends(get_auth_context),
    db:     AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(APIKey).where(APIKey.id == uuid.UUID(key_id), APIKey.user_id == auth.user_id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = datetime.now(timezone.utc)
    return {"status": "revoked"}


# ── GDPR right to erasure ──────────────────────────────────────────────────────

@router.post("/erase-my-data")
async def erase_my_data(
    req:  MFAVerifyRequest,  # reuse — requires TOTP or password confirmation
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """
    GDPR Article 17 — Right to Erasure.
    Permanently deletes all personal data for the current user.
    For account owners, also deletes the tenant and all graph data.
    Requires current password (passed as 'code') for confirmation.
    """
    result = await db.execute(select(User).where(User.id == auth.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify password before erasure
    cr = await db.execute(select(LocalCredential).where(LocalCredential.user_id == auth.user_id))
    cred = cr.scalar_one_or_none()
    if cred and not pwd_ctx.verify(req.code, cred.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")

    # Queue async erasure job (graph data + Postgres records)
    from src.dgraphai.tasks.gdpr import queue_erasure_job
    job_id = await queue_erasure_job(str(auth.user_id), str(auth.tenant_id))

    return {
        "status":  "queued",
        "job_id":  job_id,
        "message": "Erasure request received. All personal data will be deleted within 72 hours.",
    }


# ── Change password ────────────────────────────────────────────────────────────

@router.post("/change-password")
async def change_password(
    req:  ChangePasswordRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    cr = await db.execute(select(LocalCredential).where(LocalCredential.user_id == auth.user_id))
    cred = cr.scalar_one_or_none()
    if not cred or not pwd_ctx.verify(req.current_password, cred.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    _validate_password(req.new_password)
    cred.password_hash = pwd_ctx.hash(req.new_password)
    cred.updated_at    = datetime.now(timezone.utc)

    # Invalidate all other sessions
    await db.execute(
        update(UserSession).where(
            UserSession.user_id   == auth.user_id,
            UserSession.revoked_at == None,
        ).values(revoked_at=datetime.now(timezone.utc))
    )
    return {"status": "ok", "message": "Password changed. Please log in again on other devices."}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _issue_jwt(user: User, tenant: Tenant | None, session_id: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    app_url = os.getenv("APP_URL", "https://app.dgraph.ai")
    payload = {
        "iss":       app_url,          # issuer — required by get_auth_context
        "sub":       str(user.id),
        "email":     user.email,
        "tenant_id": str(user.tenant_id),
        "plan":      tenant.plan if tenant else "starter",
        "auth_type": "local",           # distinguish from OIDC tokens
        "iat":       int(now.timestamp()),
        "exp":       int((now + timedelta(hours=JWT_EXPIRY_H)).timestamp()),
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    if not any(c.isupper() for c in password):
        raise HTTPException(status_code=422, detail="Password must contain an uppercase letter")
    if not any(c.isdigit() for c in password):
        raise HTTPException(status_code=422, detail="Password must contain a number")


def _generate_token() -> str:
    return secrets.token_urlsafe(48)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _verify_totp(secret: str, code: str) -> bool:
    import pyotp
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def _use_backup_code(mfa: MFAConfig, code: str) -> bool:
    code = code.upper().replace("-", "").replace(" ", "")
    codes = list(mfa.backup_codes or [])
    if code in codes:
        codes.remove(code)
        mfa.backup_codes = codes
        return True
    return False


async def _constant_time_hash():
    """Waste time equivalent to bcrypt verify to prevent timing attacks."""
    import asyncio
    pwd_ctx.hash("dummy_constant_time_filler")


def _slugify(s: str) -> str:
    import re
    return re.sub(r'[^a-z0-9-]', '-', s.lower())[:32].strip('-')


async def _unique_slug(slug: str, db: AsyncSession) -> str:
    base = slug
    for i in range(1, 100):
        r = await db.execute(select(Tenant).where(Tenant.slug == slug))
        if not r.scalar_one_or_none():
            return slug
        slug = f"{base}-{i}"
    return f"{base}-{secrets.token_hex(3)}"
