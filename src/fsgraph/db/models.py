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
    JSON, String, Text, UniqueConstraint, Index
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
