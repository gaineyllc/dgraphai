"""Initial schema — all tables from models.py

Revision ID: 0001
Revises:
Create Date: 2026-04-09
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tenants ────────────────────────────────────────────────────────────────
    op.create_table('tenants',
        sa.Column('id',                 UUID(as_uuid=True), primary_key=True),
        sa.Column('slug',               sa.String(64),  nullable=False, unique=True),
        sa.Column('name',               sa.String(256), nullable=False),
        sa.Column('plan',               sa.String(32),  default='starter'),
        sa.Column('is_active',          sa.Boolean(),   nullable=False, default=True),
        sa.Column('max_users',          sa.String()),
        sa.Column('max_connectors',     sa.String()),
        sa.Column('max_nodes',          sa.String()),
        sa.Column('stripe_customer_id', sa.String(64)),
        sa.Column('subscription_status',sa.String(32), default='none'),
        sa.Column('current_period_end', sa.Integer()),
        sa.Column('cancel_at_period_end', sa.Boolean(), default=False),
        sa.Column('timezone',           sa.String(64),  default='UTC'),
        sa.Column('logo_url',           sa.String(512)),
        sa.Column('notification_config',JSON(),         default=dict),
        sa.Column('graph_backend',      sa.String(32),  default='neo4j'),
        sa.Column('graph_config',       JSON(),         default=dict),
        sa.Column('created_at',         sa.DateTime(timezone=True)),
        sa.Column('updated_at',         sa.DateTime(timezone=True)),
    )

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table('users',
        sa.Column('id',             UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',      UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email',          sa.String(256), nullable=False),
        sa.Column('display_name',   sa.String(256)),
        sa.Column('name',           sa.String(256)),
        sa.Column('role',           sa.String(32),  default='member'),
        sa.Column('external_id',    sa.String(512)),
        sa.Column('idp_provider',   sa.String(64)),
        sa.Column('is_active',      sa.Boolean(), default=True),
        sa.Column('email_verified', sa.Boolean(), default=False),
        sa.Column('last_login',     sa.DateTime(timezone=True)),
        sa.Column('created_at',     sa.DateTime(timezone=True)),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_tenant_email'),
    )
    op.create_index('ix_users_tenant_external', 'users', ['tenant_id', 'external_id'])

    # ── local_credentials ─────────────────────────────────────────────────────
    op.create_table('local_credentials',
        sa.Column('id',              UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id',         UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('password_hash',   sa.String(256), nullable=False),
        sa.Column('failed_attempts', sa.Integer(), default=0),
        sa.Column('locked_until',    sa.DateTime(timezone=True)),
        sa.Column('last_failed_at',  sa.DateTime(timezone=True)),
        sa.Column('last_login_at',   sa.DateTime(timezone=True)),
        sa.Column('updated_at',      sa.DateTime(timezone=True)),
    )

    # ── email_verification_tokens ─────────────────────────────────────────────
    op.create_table('email_verification_tokens',
        sa.Column('id',         UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id',    UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(256), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at',    sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )

    # ── password_reset_tokens ─────────────────────────────────────────────────
    op.create_table('password_reset_tokens',
        sa.Column('id',         UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id',    UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(256), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at',    sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )

    # ── mfa_configs ────────────────────────────────────────────────────────────
    op.create_table('mfa_configs',
        sa.Column('id',          UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id',     UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('secret',      sa.String(256), nullable=False),
        sa.Column('backup_codes',JSON()),
        sa.Column('is_active',   sa.Boolean(), default=False),
        sa.Column('enrolled_at', sa.DateTime(timezone=True)),
        sa.Column('disabled_at', sa.DateTime(timezone=True)),
        sa.Column('created_at',  sa.DateTime(timezone=True)),
    )

    # ── user_sessions ──────────────────────────────────────────────────────────
    op.create_table('user_sessions',
        sa.Column('id',         UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id',    UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id',  UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.String(512)),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_user_sessions_user', 'user_sessions', ['user_id', 'revoked_at'])

    # ── api_keys ───────────────────────────────────────────────────────────────
    op.create_table('api_keys',
        sa.Column('id',           UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id',      UUID(as_uuid=True), sa.ForeignKey('users.id',   ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id',    UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',         sa.String(256), nullable=False),
        sa.Column('key_hash',     sa.String(256), nullable=False, unique=True),
        sa.Column('key_prefix',   sa.String(16),  nullable=False),
        sa.Column('expires_at',   sa.DateTime(timezone=True)),
        sa.Column('revoked_at',   sa.DateTime(timezone=True)),
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.Column('created_at',   sa.DateTime(timezone=True)),
    )
    op.create_index('ix_api_keys_hash', 'api_keys', ['key_hash'])

    # ── audit_logs ─────────────────────────────────────────────────────────────
    op.create_table('audit_logs',
        sa.Column('id',         UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',  UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id',    UUID(as_uuid=True), nullable=True),
        sa.Column('action',     sa.String(128), nullable=False),
        sa.Column('resource',   sa.String(128)),
        sa.Column('details',    JSON(), default=dict),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.String(512)),
        sa.Column('status',     sa.String(16), default='success'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_audit_tenant_created', 'audit_logs', ['tenant_id', 'created_at'])
    op.create_index('ix_audit_user',           'audit_logs', ['user_id',   'created_at'])

    # ── webhook_endpoints ──────────────────────────────────────────────────────
    op.create_table('webhook_endpoints',
        sa.Column('id',                   UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',            UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url',                  sa.String(512), nullable=False),
        sa.Column('secret',               sa.String(256)),
        sa.Column('event_types',          JSON(), default=list),
        sa.Column('description',          sa.String(256)),
        sa.Column('is_active',            sa.Boolean(), default=True),
        sa.Column('last_delivery_at',     sa.DateTime(timezone=True)),
        sa.Column('last_delivery_status', sa.String(16)),
        sa.Column('failure_count',        sa.Integer(), default=0),
        sa.Column('created_by',           UUID(as_uuid=True)),
        sa.Column('created_at',           sa.DateTime(timezone=True)),
    )

    # ── webhook_deliveries ─────────────────────────────────────────────────────
    op.create_table('webhook_deliveries',
        sa.Column('id',           UUID(as_uuid=True), primary_key=True),
        sa.Column('endpoint_id',  UUID(as_uuid=True), sa.ForeignKey('webhook_endpoints.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id',    UUID(as_uuid=True), nullable=False),
        sa.Column('event_type',   sa.String(128), nullable=False),
        sa.Column('event_id',     sa.String(64),  nullable=False),
        sa.Column('attempts',     sa.Integer(), default=1),
        sa.Column('delivered',    sa.Boolean(), default=False),
        sa.Column('status',       sa.String(32), default='pending'),
        sa.Column('last_error',   sa.Text()),
        sa.Column('delivered_at', sa.DateTime(timezone=True)),
        sa.Column('created_at',   sa.DateTime(timezone=True)),
    )
    op.create_index('ix_webhook_deliveries_tenant', 'webhook_deliveries', ['tenant_id', 'created_at'])

    # ── scim_configs ───────────────────────────────────────────────────────────
    op.create_table('scim_configs',
        sa.Column('id',           UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',    UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash',   sa.String(256), nullable=False),
        sa.Column('is_active',    sa.Boolean(), default=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.Column('created_by',   UUID(as_uuid=True)),
        sa.Column('created_at',   sa.DateTime(timezone=True)),
    )

    # ── saml_configs ───────────────────────────────────────────────────────────
    op.create_table('saml_configs',
        sa.Column('id',               UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',        UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('idp_entity_id',    sa.String(512), nullable=False),
        sa.Column('idp_sso_url',      sa.String(512), nullable=False),
        sa.Column('idp_certificate',  sa.Text(), nullable=False),
        sa.Column('email_attribute',  sa.String(128), default='emailaddress'),
        sa.Column('name_attribute',   sa.String(128), default='displayname'),
        sa.Column('groups_attribute', sa.String(128), default='groups'),
        sa.Column('role_mappings',    JSON(), default=dict),
        sa.Column('is_active',        sa.Boolean(), default=True),
        sa.Column('created_by',       UUID(as_uuid=True)),
        sa.Column('created_at',       sa.DateTime(timezone=True)),
    )

    # ── user_invites ───────────────────────────────────────────────────────────
    op.create_table('user_invites',
        sa.Column('id',          UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',   UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('invited_by',  UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('email',       sa.String(256), nullable=False),
        sa.Column('role',        sa.String(32),  default='analyst'),
        sa.Column('token_hash',  sa.String(256), nullable=False, unique=True),
        sa.Column('expires_at',  sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at',     sa.DateTime(timezone=True)),
        sa.Column('created_at',  sa.DateTime(timezone=True)),
    )

    # ── gdpr_erasure_jobs ──────────────────────────────────────────────────────
    op.create_table('gdpr_erasure_jobs',
        sa.Column('id',           UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id',      sa.String(256), nullable=False),
        sa.Column('tenant_id',    sa.String(256), nullable=False),
        sa.Column('status',       sa.String(32),  default='pending'),
        sa.Column('requested_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('error',        sa.Text()),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    for table in [
        'gdpr_erasure_jobs', 'user_invites', 'saml_configs', 'scim_configs',
        'webhook_deliveries', 'webhook_endpoints', 'audit_logs', 'api_keys',
        'user_sessions', 'mfa_configs', 'password_reset_tokens',
        'email_verification_tokens', 'local_credentials',
        'users', 'tenants',
    ]:
        op.drop_table(table)
