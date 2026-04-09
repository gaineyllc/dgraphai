"""
Database models — Postgres via SQLAlchemy async.
Stores: tenants, users, OIDC configs, roles, permissions, scanner registrations.
Graph data lives in Neo4j/Neptune, scoped per tenant.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ── Tenants ────────────────────────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug        = Column(String(64), unique=True, nullable=False, index=True)
    name        = Column(String(256), nullable=False)
    plan        = Column(String(32), default="starter")  # starter / pro / enterprise
    is_active   = Column(Boolean, default=True, nullable=False)
    created_at  = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at  = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    # Graph DB config per tenant (overrides global default)
    graph_backend   = Column(String(32), default="neo4j")  # neo4j | neptune | auradb
    graph_config    = Column(JSON, default=dict)            # encrypted connection params

    # Limits
    max_users       = Column(String, default="10")
    max_connectors  = Column(String, default="5")
    max_nodes       = Column(String, default="1000000")

    # Stripe billing
    stripe_customer_id   = Column(String(64))
    subscription_status  = Column(String(32), default="none")
    current_period_end   = Column(Integer)   # Unix timestamp
    cancel_at_period_end = Column(Boolean, default=False)

    # Settings
    timezone             = Column(String(64), default="UTC")
    logo_url             = Column(String(512))
    notification_config  = Column(JSON, default=dict)

    users           = relationship("User",         back_populates="tenant", cascade="all, delete")
    oidc_configs    = relationship("OIDCConfig",   back_populates="tenant", cascade="all, delete")
    roles           = relationship("Role",         back_populates="tenant", cascade="all, delete")
    scanners        = relationship("ScannerAgent", back_populates="tenant", cascade="all, delete")


# ── OIDC / Identity Provider configuration ────────────────────────────────────

class OIDCConfig(Base):
    """
    Per-tenant OIDC provider configuration.
    Supports: Okta, Azure AD, Google Workspace, Keycloak, Auth0, any compliant IdP.
    """
    __tablename__ = "oidc_configs"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id       = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    provider_name   = Column(String(64), nullable=False)       # e.g. "Okta", "Azure AD"
    issuer_url      = Column(String(512), nullable=False)      # OIDC discovery URL base
    client_id       = Column(String(256), nullable=False)
    client_secret   = Column(Text, nullable=False)             # encrypted at rest
    scopes          = Column(JSON, default=lambda: ["openid", "email", "profile"])
    claim_mapping   = Column(JSON, default=dict)               # map IdP claims → dgraphai attrs
    # e.g. {"email": "email", "name": "name", "groups": "groups"}
    is_default      = Column(Boolean, default=True)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime(timezone=True), default=now_utc)

    tenant          = relationship("Tenant", back_populates="oidc_configs")

    __table_args__ = (
        UniqueConstraint("tenant_id", "client_id", name="uq_tenant_client"),
    )


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id       = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email           = Column(String(256), nullable=False)
    display_name    = Column(String(256))
    external_id     = Column(String(512))       # subject from IdP JWT
    idp_provider    = Column(String(64))        # which OIDCConfig authenticated them
    is_active       = Column(Boolean, default=True)
    last_login      = Column(DateTime(timezone=True))
    email_verified  = Column(Boolean, default=False)
    role            = Column(String(32), default="member")   # quick access role label
    name            = Column(String(256))                    # alias for display_name
    created_at      = Column(DateTime(timezone=True), default=now_utc)

    tenant          = relationship("Tenant", back_populates="users")
    role_assignments = relationship("RoleAssignment", back_populates="user", cascade="all, delete")

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_tenant_email"),
        Index("ix_users_tenant_external", "tenant_id", "external_id"),
    )


# ── RBAC ──────────────────────────────────────────────────────────────────────

ROLE_TYPES = ("admin", "analyst", "viewer", "agent", "custom")

class Role(Base):
    """
    Tenant-scoped role definition.
    Built-in roles: admin, analyst, viewer, agent.
    Custom roles can be created by tenant admins.
    """
    __tablename__ = "roles"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id       = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name            = Column(String(64), nullable=False)
    role_type       = Column(Enum(*ROLE_TYPES, name="role_type"), default="custom")
    description     = Column(Text)
    permissions     = Column(JSON, default=list)
    # e.g. ["graph:read", "mounts:read", "actions:propose", "actions:approve"]
    is_system       = Column(Boolean, default=False)  # True = cannot be deleted
    created_at      = Column(DateTime(timezone=True), default=now_utc)

    tenant          = relationship("Tenant", back_populates="roles")
    assignments     = relationship("RoleAssignment", back_populates="role", cascade="all, delete")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_role_name"),
    )


class RoleAssignment(Base):
    """
    Assigns a role to a user with an optional resource scope.

    Scope examples:
      scope_type=None              → global within tenant
      scope_type="connector"       → scoped to specific connector IDs
      scope_type="tag"             → scoped to nodes with matching tags
      scope_type="attribute"       → scoped to nodes matching attribute filter
    """
    __tablename__ = "role_assignments"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id       = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id",   ondelete="CASCADE"), nullable=False)
    role_id         = Column(UUID(as_uuid=True), ForeignKey("roles.id",   ondelete="CASCADE"), nullable=False)
    scope_type      = Column(String(32))            # None | connector | tag | attribute
    scope_value     = Column(JSON)                  # depends on scope_type
    # connector: {"connector_ids": ["abc", "def"]}
    # tag:       {"tags": ["env:production", "owner:engineering"]}
    # attribute: {"filters": {"file_category": "document", "sensitivity_level": "confidential"}}
    granted_by      = Column(UUID(as_uuid=True))    # user_id who granted this
    created_at      = Column(DateTime(timezone=True), default=now_utc)
    expires_at      = Column(DateTime(timezone=True))  # optional time-bounded access

    user            = relationship("User", back_populates="role_assignments")
    role            = relationship("Role", back_populates="assignments")

    __table_args__ = (
        Index("ix_role_assignments_user", "user_id", "tenant_id"),
    )


# ── Scanner Agents ────────────────────────────────────────────────────────────

class ScannerAgent(Base):
    """
    Registered on-prem scanner agent instances.
    Each agent has a unique API key for authentication.
    """
    __tablename__ = "scanner_agents"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id       = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name            = Column(String(256), nullable=False)
    description     = Column(Text)
    api_key_hash    = Column(String(256), nullable=False)  # bcrypt hash of API key
    version         = Column(String(32))
    platform        = Column(String(32))                   # kubernetes | docker | bare-metal
    is_active       = Column(Boolean, default=True)
    last_seen       = Column(DateTime(timezone=True))
    last_health     = Column(JSON, default=dict)           # latest health report
    registered_at   = Column(DateTime(timezone=True), default=now_utc)
    registered_by   = Column(UUID(as_uuid=True))           # user_id

    tenant          = relationship("Tenant", back_populates="scanners")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_scanner_name"),
    )


# ── Local auth models ────────────────────────────────────────────────────────────────

class LocalCredential(Base):
    """Email/password credential for local auth (alternative to OIDC)."""
    __tablename__ = "local_credentials"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id          = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    password_hash    = Column(String(256), nullable=False)
    failed_attempts  = Column(Integer, default=0)
    locked_until     = Column(DateTime(timezone=True))
    last_failed_at   = Column(DateTime(timezone=True))
    last_login_at    = Column(DateTime(timezone=True))
    updated_at       = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(256), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at    = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=now_utc)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(256), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at    = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=now_utc)


class MFAConfig(Base):
    """TOTP MFA configuration per user."""
    __tablename__ = "mfa_configs"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    secret       = Column(String(256), nullable=False)    # base32 TOTP secret (encrypted at rest)
    backup_codes = Column(JSON, default=list)             # hashed 8-char codes
    is_active    = Column(Boolean, default=False)
    enrolled_at  = Column(DateTime(timezone=True))
    disabled_at  = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), default=now_utc)


class UserSession(Base):
    """Active user sessions for session management and revocation."""
    __tablename__ = "user_sessions"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id  = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    ip_address = Column(String(45))
    user_agent = Column(String(512))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (Index("ix_user_sessions_user", "user_id", "revoked_at"),)


class APIKey(Base):
    """Personal access tokens for programmatic API access."""
    __tablename__ = "api_keys"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id",   ondelete="CASCADE"), nullable=False)
    tenant_id   = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name        = Column(String(256), nullable=False)
    key_hash    = Column(String(256), nullable=False, unique=True)  # SHA-256, never store plaintext
    key_prefix  = Column(String(16),  nullable=False)               # first 12 chars for display
    expires_at  = Column(DateTime(timezone=True))
    revoked_at  = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    created_at  = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (Index("ix_api_keys_hash", "key_hash"),)


class AuditLog(Base):
    """
    Immutable audit log — every significant action recorded here.
    Written append-only; no updates or deletes allowed via ORM.
    For SOC 2 Type II compliance.
    """
    __tablename__ = "audit_logs"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id   = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id     = Column(UUID(as_uuid=True), nullable=True)    # None for system events
    action      = Column(String(128), nullable=False)          # e.g. "user.login", "query.run"
    resource    = Column(String(128))                          # e.g. "connector:abc123"
    details     = Column(JSON, default=dict)                   # action-specific context
    ip_address  = Column(String(45))
    user_agent  = Column(String(512))
    status      = Column(String(16), default="success")       # success | failure | error
    created_at  = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    __table_args__ = (
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_user",           "user_id",   "created_at"),
    )


class UserInvite(Base):
    """Pending user invitations."""
    __tablename__ = "user_invites"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id   = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    invited_by  = Column(UUID(as_uuid=True), ForeignKey("users.id",   ondelete="SET NULL"))
    email       = Column(String(256), nullable=False)
    role        = Column(String(32), default="analyst")
    token_hash  = Column(String(256), nullable=False, unique=True)
    expires_at  = Column(DateTime(timezone=True), nullable=False)
    used_at     = Column(DateTime(timezone=True))
    created_at  = Column(DateTime(timezone=True), default=now_utc)


class SCIMConfig(Base):
    """SCIM provisioning token per tenant."""
    __tablename__ = "scim_configs"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    token_hash   = Column(String(256), nullable=False)
    is_active    = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True))
    created_by   = Column(UUID(as_uuid=True))
    created_at   = Column(DateTime(timezone=True), default=now_utc)


class SAMLConfig(Base):
    """SAML 2.0 IdP configuration per tenant."""
    __tablename__ = "saml_configs"
    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id        = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    idp_entity_id    = Column(String(512), nullable=False)
    idp_sso_url      = Column(String(512), nullable=False)
    idp_certificate  = Column(Text, nullable=False)
    email_attribute  = Column(String(128), default="emailaddress")
    name_attribute   = Column(String(128), default="displayname")
    groups_attribute = Column(String(128), default="groups")
    role_mappings    = Column(JSON, default=dict)
    is_active        = Column(Boolean, default=True)
    created_by       = Column(UUID(as_uuid=True))
    created_at       = Column(DateTime(timezone=True), default=now_utc)


class WebhookEndpoint(Base):
    """Registered outbound webhook endpoints."""
    __tablename__ = "webhook_endpoints"
    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id            = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    url                  = Column(String(512), nullable=False)
    secret               = Column(String(256))  # HMAC signing secret
    event_types          = Column(JSON, default=list)
    description          = Column(String(256))
    is_active            = Column(Boolean, default=True)
    last_delivery_at     = Column(DateTime(timezone=True))
    last_delivery_status = Column(String(16))
    failure_count        = Column(Integer, default=0)
    created_by           = Column(UUID(as_uuid=True))
    created_at           = Column(DateTime(timezone=True), default=now_utc)


class WebhookDelivery(Base):
    """Log of webhook delivery attempts."""
    __tablename__ = "webhook_deliveries"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id  = Column(UUID(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False)
    tenant_id    = Column(UUID(as_uuid=True), nullable=False)
    event_type   = Column(String(128), nullable=False)
    event_id     = Column(String(64), nullable=False)
    attempts     = Column(Integer, default=1)
    delivered    = Column(Boolean, default=False)
    status       = Column(String(32), default="pending")
    last_error   = Column(Text)
    delivered_at = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (Index("ix_webhook_deliveries_tenant", "tenant_id", "created_at"),)


class GDPRErasureJob(Base):
    """Tracks GDPR right-to-erasure requests."""
    __tablename__ = "gdpr_erasure_jobs"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(String(256), nullable=False)    # keep as string (user may be deleted)
    tenant_id   = Column(String(256), nullable=False)
    status      = Column(String(32), default="pending")  # pending | running | complete | failed
    requested_at = Column(DateTime(timezone=True), default=now_utc)
    completed_at = Column(DateTime(timezone=True))
    error        = Column(Text)
