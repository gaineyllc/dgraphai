"""Add oidc_configs, roles, role_assignments, scanner_agents

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-09
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # ── oidc_configs ───────────────────────────────────────────────────────────
    op.create_table('oidc_configs',
        sa.Column('id',            UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',     UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_name', sa.String(64),  nullable=False),
        sa.Column('issuer_url',    sa.String(512), nullable=False),
        sa.Column('client_id',     sa.String(256), nullable=False),
        sa.Column('client_secret', sa.Text(),      nullable=False),
        sa.Column('scopes',        JSON(), default=list),
        sa.Column('claim_mapping', JSON(), default=dict),
        sa.Column('is_default',    sa.Boolean(), default=True),
        sa.Column('is_active',     sa.Boolean(), default=True),
        sa.Column('created_at',    sa.DateTime(timezone=True)),
        sa.UniqueConstraint('tenant_id', 'client_id', name='uq_tenant_client'),
    )

    # ── roles ──────────────────────────────────────────────────────────────────
    op.create_table('roles',
        sa.Column('id',          UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',   UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',        sa.String(64),  nullable=False),
        sa.Column('role_type',   sa.String(32),  default='custom'),
        sa.Column('description', sa.Text()),
        sa.Column('permissions', JSON(), default=list),
        sa.Column('is_system',   sa.Boolean(), default=False),
        sa.Column('created_at',  sa.DateTime(timezone=True)),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_tenant_role_name'),
    )

    # ── role_assignments ───────────────────────────────────────────────────────
    op.create_table('role_assignments',
        sa.Column('id',          UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',   UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id',     UUID(as_uuid=True), sa.ForeignKey('users.id',   ondelete='CASCADE'), nullable=False),
        sa.Column('role_id',     UUID(as_uuid=True), sa.ForeignKey('roles.id',   ondelete='CASCADE'), nullable=False),
        sa.Column('scope_type',  sa.String(32)),
        sa.Column('scope_value', JSON()),
        sa.Column('granted_by',  UUID(as_uuid=True)),
        sa.Column('created_at',  sa.DateTime(timezone=True)),
        sa.Column('expires_at',  sa.DateTime(timezone=True)),
    )
    op.create_index('ix_role_assignments_user', 'role_assignments', ['user_id', 'tenant_id'])

    # ── scanner_agents ─────────────────────────────────────────────────────────
    op.create_table('scanner_agents',
        sa.Column('id',             UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',      UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',           sa.String(256), nullable=False),
        sa.Column('description',    sa.Text()),
        sa.Column('api_key_hash',   sa.String(256), nullable=False),
        sa.Column('version',        sa.String(32)),
        sa.Column('platform',       sa.String(32)),
        sa.Column('is_active',      sa.Boolean(), default=True),
        sa.Column('last_seen',      sa.DateTime(timezone=True)),
        sa.Column('last_health',    JSON(), default=dict),
        sa.Column('registered_at',  sa.DateTime(timezone=True)),
        sa.Column('registered_by',  UUID(as_uuid=True)),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_tenant_scanner_name'),
    )

    # Also add connector_models table if exists in codebase
    op.create_table('connectors',
        sa.Column('id',               UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id',        UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',             sa.String(256), nullable=False),
        sa.Column('description',      sa.Text()),
        sa.Column('connector_type',   sa.String(64),  nullable=False),
        sa.Column('is_active',        sa.Boolean(), default=True),
        sa.Column('config',           JSON(), default=dict),
        sa.Column('tags',             JSON(), default=list),
        sa.Column('scanner_agent_id', UUID(as_uuid=True), sa.ForeignKey('scanner_agents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('routing_mode',     sa.String(32), default='direct'),
        sa.Column('last_scan_at',     sa.DateTime(timezone=True)),
        sa.Column('last_scan_status', sa.String(32)),
        sa.Column('last_scan_duration_secs', sa.Float()),
        sa.Column('last_scan_files',  sa.Integer(), default=0),
        sa.Column('last_scan_errors', sa.Integer(), default=0),
        sa.Column('last_scan_error_msg', sa.Text()),
        sa.Column('total_files_indexed', sa.Integer(), default=0),
        sa.Column('avg_throughput_fps',  sa.Float()),
        sa.Column('last_test_at',     sa.DateTime(timezone=True)),
        sa.Column('last_test_result', sa.Boolean()),
        sa.Column('last_test_msg',    sa.Text()),
        sa.Column('created_at',       sa.DateTime(timezone=True)),
        sa.Column('updated_at',       sa.DateTime(timezone=True)),
        sa.Column('created_by',       UUID(as_uuid=True)),
    )


def downgrade() -> None:
    for table in ['connectors', 'scanner_agents', 'role_assignments', 'roles', 'oidc_configs']:
        op.drop_table(table)
