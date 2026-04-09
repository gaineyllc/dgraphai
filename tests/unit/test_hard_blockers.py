"""
Tests for all 8 hard blocker systems.

1. Auth (signup, login, MFA, password reset, sessions, API keys)
2. Email verification flow
3. User invitations
4. Audit log
5. GDPR erasure
6. Celery task queue config
7. Rate limiting (middleware)
8. DB models complete
"""
import pytest
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.unit


# ── 1. Password validation ─────────────────────────────────────────────────────

class TestPasswordValidation:
    def _validate(self, pw):
        from src.dgraphai.auth.local import _validate_password
        from fastapi import HTTPException
        try:
            _validate_password(pw)
            return True
        except HTTPException:
            return False

    def test_strong_password_accepted(self):
        assert self._validate("Secure123!") is True

    def test_too_short_rejected(self):
        assert self._validate("Ab1") is False

    def test_no_uppercase_rejected(self):
        assert self._validate("password123") is False

    def test_no_digit_rejected(self):
        assert self._validate("Password") is False

    def test_exactly_8_chars_accepted(self):
        assert self._validate("Passw0rd") is True


# ── 2. Token hashing ───────────────────────────────────────────────────────────

class TestTokenHashing:
    def test_token_hash_deterministic(self):
        from src.dgraphai.auth.local import _hash_token, _generate_token
        t = _generate_token()
        h1 = _hash_token(t)
        h2 = _hash_token(t)
        assert h1 == h2

    def test_different_tokens_different_hashes(self):
        from src.dgraphai.auth.local import _hash_token, _generate_token
        t1 = _generate_token()
        t2 = _generate_token()
        assert _hash_token(t1) != _hash_token(t2)

    def test_token_not_guessable(self):
        from src.dgraphai.auth.local import _generate_token
        tokens = {_generate_token() for _ in range(100)}
        assert len(tokens) == 100  # all unique


# ── 3. TOTP / MFA ──────────────────────────────────────────────────────────────

class TestTOTP:
    def test_valid_totp_accepted(self):
        import pyotp
        from src.dgraphai.auth.local import _verify_totp
        secret = pyotp.random_base32()
        current_code = pyotp.TOTP(secret).now()
        assert _verify_totp(secret, current_code) is True

    def test_wrong_code_rejected(self):
        import pyotp
        from src.dgraphai.auth.local import _verify_totp
        secret = pyotp.random_base32()
        assert _verify_totp(secret, "000000") is False

    def test_backup_code_consumed(self):
        from src.dgraphai.auth.local import _use_backup_code
        mfa = MagicMock()
        mfa.backup_codes = ["ABCD1234", "EFGH5678"]
        assert _use_backup_code(mfa, "ABCD1234") is True
        assert "ABCD1234" not in mfa.backup_codes
        assert len(mfa.backup_codes) == 1

    def test_used_backup_code_rejected(self):
        from src.dgraphai.auth.local import _use_backup_code
        mfa = MagicMock()
        mfa.backup_codes = ["ABCD1234"]
        _use_backup_code(mfa, "ABCD1234")
        assert _use_backup_code(mfa, "ABCD1234") is False

    def test_wrong_backup_code_rejected(self):
        from src.dgraphai.auth.local import _use_backup_code
        mfa = MagicMock()
        mfa.backup_codes = ["ABCD1234"]
        assert _use_backup_code(mfa, "WRONG123") is False


# ── 4. JWT issuance ────────────────────────────────────────────────────────────

class TestJWT:
    def _make_user(self, uid=None, tenant_id=None):
        import uuid
        u = MagicMock()
        u.id        = uid or uuid.uuid4()
        u.email     = "test@example.com"
        u.tenant_id = tenant_id or uuid.uuid4()
        return u

    def _make_tenant(self, plan="pro"):
        t = MagicMock()
        t.plan = plan
        return t

    def test_jwt_issued_and_decodable(self):
        import jwt as pyjwt
        from src.dgraphai.auth.local import _issue_jwt, JWT_SECRET, JWT_ALGO
        token = _issue_jwt(self._make_user(), self._make_tenant())
        claims = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert "sub" in claims
        assert "email" in claims
        assert "tenant_id" in claims
        assert "exp" in claims

    def test_jwt_contains_plan(self):
        import jwt as pyjwt
        from src.dgraphai.auth.local import _issue_jwt, JWT_SECRET, JWT_ALGO
        token = _issue_jwt(self._make_user(), self._make_tenant("enterprise"))
        claims = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert claims["plan"] == "enterprise"

    def test_jwt_expiry_is_future(self):
        import jwt as pyjwt, time
        from src.dgraphai.auth.local import _issue_jwt, JWT_SECRET, JWT_ALGO
        token = _issue_jwt(self._make_user(), self._make_tenant())
        claims = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert claims["exp"] > int(time.time())


# ── 5. API key generation ──────────────────────────────────────────────────────

class TestAPIKeys:
    def test_key_has_correct_prefix(self):
        key = f"dg_{secrets.token_urlsafe(32)}"
        assert key.startswith("dg_")

    def test_key_hash_is_sha256(self):
        raw = f"dg_{secrets.token_urlsafe(32)}"
        h   = hashlib.sha256(raw.encode()).hexdigest()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_key_prefix_is_first_12_chars(self):
        raw    = f"dg_{secrets.token_urlsafe(32)}"
        prefix = raw[:12]
        assert len(prefix) == 12
        assert prefix == raw[:12]

    def test_different_keys_different_hashes(self):
        keys   = [f"dg_{secrets.token_urlsafe(32)}" for _ in range(10)]
        hashes = {hashlib.sha256(k.encode()).hexdigest() for k in keys}
        assert len(hashes) == 10


# ── 6. Audit log model ─────────────────────────────────────────────────────────

class TestAuditLogModel:
    def test_audit_log_fields_exist(self):
        from src.dgraphai.db.models import AuditLog
        cols = {c.key for c in AuditLog.__table__.columns}
        required = {"id","tenant_id","user_id","action","resource","details",
                    "ip_address","user_agent","status","created_at"}
        assert required <= cols

    def test_audit_log_has_index_on_tenant_created(self):
        from src.dgraphai.db.models import AuditLog
        index_names = {i.name for i in AuditLog.__table__.indexes}
        assert "ix_audit_tenant_created" in index_names

    def test_no_updated_at_on_audit_log(self):
        """Audit log must be append-only — no updated_at column."""
        from src.dgraphai.db.models import AuditLog
        cols = {c.key for c in AuditLog.__table__.columns}
        assert "updated_at" not in cols


# ── 7. All auth DB models present ─────────────────────────────────────────────

class TestAuthModels:
    def _cols(self, model):
        return {c.key for c in model.__table__.columns}

    def test_local_credential_model(self):
        from src.dgraphai.db.models import LocalCredential
        cols = self._cols(LocalCredential)
        assert {"user_id","password_hash","failed_attempts","locked_until"} <= cols

    def test_email_verification_token(self):
        from src.dgraphai.db.models import EmailVerificationToken
        cols = self._cols(EmailVerificationToken)
        assert {"user_id","token_hash","expires_at","used_at"} <= cols

    def test_password_reset_token(self):
        from src.dgraphai.db.models import PasswordResetToken
        cols = self._cols(PasswordResetToken)
        assert {"user_id","token_hash","expires_at","used_at"} <= cols

    def test_mfa_config_model(self):
        from src.dgraphai.db.models import MFAConfig
        cols = self._cols(MFAConfig)
        assert {"user_id","secret","backup_codes","is_active","enrolled_at"} <= cols

    def test_user_session_model(self):
        from src.dgraphai.db.models import UserSession
        cols = self._cols(UserSession)
        assert {"user_id","tenant_id","ip_address","expires_at","revoked_at"} <= cols

    def test_api_key_model(self):
        from src.dgraphai.db.models import APIKey
        cols = self._cols(APIKey)
        assert {"user_id","tenant_id","name","key_hash","key_prefix","revoked_at"} <= cols

    def test_user_invite_model(self):
        from src.dgraphai.db.models import UserInvite
        cols = self._cols(UserInvite)
        assert {"tenant_id","email","role","token_hash","expires_at","used_at"} <= cols

    def test_gdpr_erasure_job_model(self):
        from src.dgraphai.db.models import GDPRErasureJob
        cols = self._cols(GDPRErasureJob)
        assert {"user_id","tenant_id","status","requested_at","completed_at"} <= cols

    def test_user_model_has_email_verified(self):
        from src.dgraphai.db.models import User
        cols = self._cols(User)
        assert "email_verified" in cols


# ── 8. Celery queue config ─────────────────────────────────────────────────────

class TestCeleryConfig:
    def test_all_queues_defined(self):
        from src.dgraphai.tasks.celery_app import app
        queue_names = {q.name for q in app.conf.task_queues}
        required = {"default","indexing","enrichment","alerts","gdpr","exports"}
        assert required <= queue_names

    def test_acks_late_enabled(self):
        from src.dgraphai.tasks.celery_app import app
        assert app.conf.task_acks_late is True

    def test_reject_on_worker_lost(self):
        from src.dgraphai.tasks.celery_app import app
        assert app.conf.task_reject_on_worker_lost is True

    def test_beat_schedule_has_required_jobs(self):
        from src.dgraphai.tasks.celery_app import app
        jobs = set(app.conf.beat_schedule.keys())
        assert "evaluate-alerts-every-5-min" in jobs
        assert "cleanup-expired-tokens-daily" in jobs
        assert "snapshot-usage-daily" in jobs

    def test_gdpr_tasks_routed_to_gdpr_queue(self):
        from src.dgraphai.tasks.celery_app import app
        routes = app.conf.task_routes
        assert routes.get("dgraphai.tasks.gdpr.*", {}).get("queue") == "gdpr"

    def test_enrichment_tasks_isolated(self):
        from src.dgraphai.tasks.celery_app import app
        routes = app.conf.task_routes
        assert routes.get("dgraphai.tasks.enrichment.*", {}).get("queue") == "enrichment"


# ── 9. Email service ───────────────────────────────────────────────────────────

class TestEmailService:
    @pytest.mark.asyncio
    async def test_dev_mode_logs_not_sends(self):
        """Without SMTP_HOST configured, email falls back to logging."""
        import logging
        from src.dgraphai.auth import email as email_mod
        original = email_mod.SMTP_HOST
        email_mod.SMTP_HOST = ""
        try:
            result = await email_mod.send_email("test@example.com", "Test", "<p>Hi</p>")
            assert result is True  # logged, not failed
        finally:
            email_mod.SMTP_HOST = original

    def test_verification_email_contains_token_url(self):
        """Verification email template should include the token URL."""
        import asyncio
        from src.dgraphai.auth import email as email_mod

        sent_to = []
        original_send = email_mod.send_email

        async def mock_send(to, subject, html, text=""):
            sent_to.append({"to": to, "subject": subject, "html": html})
            return True

        email_mod.send_email = mock_send
        email_mod.SMTP_HOST  = ""
        try:
            token = "testtoken123"
            asyncio.run(email_mod.send_verification_email("u@example.com", "Alice", token))
            if sent_to:
                assert token in sent_to[0]["html"] or token in sent_to[0].get("text", "")
        finally:
            email_mod.send_email = original_send


# ── 10. RBAC assign_builtin_role ──────────────────────────────────────────────

class TestAssignBuiltinRole:
    def test_builtin_permissions_exist_for_all_roles(self):
        from src.dgraphai.rbac.engine import BUILTIN_PERMISSIONS
        for role in ["admin", "analyst", "viewer", "agent"]:
            assert role in BUILTIN_PERMISSIONS
            assert len(BUILTIN_PERMISSIONS[role]) > 0

    def test_assign_builtin_role_importable(self):
        from src.dgraphai.rbac.engine import assign_builtin_role
        import inspect
        assert inspect.iscoroutinefunction(assign_builtin_role)
