"""Add missing user columns (role, name, email_verified) + fix connector FK order

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-09

Uses IF NOT EXISTS so this migration is idempotent — safe to run on a DB
that already has these columns from an earlier schema version.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def _add_column_if_not_exists(table: str, column: str, ddl: str) -> None:
    """Add a column only if it doesn't already exist (idempotent)."""
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='{table}' AND column_name='{column}'
            ) THEN
                ALTER TABLE {table} ADD COLUMN {ddl};
            END IF;
        END $$;
    """)


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────────
    _add_column_if_not_exists('users', 'role',           "role VARCHAR(32) DEFAULT 'member'")
    _add_column_if_not_exists('users', 'name',           "name VARCHAR(256)")
    _add_column_if_not_exists('users', 'email_verified', "email_verified BOOLEAN DEFAULT false")

    # ── tenants ────────────────────────────────────────────────────────────────
    _add_column_if_not_exists('tenants', 'stripe_customer_id',   "stripe_customer_id VARCHAR(64)")
    _add_column_if_not_exists('tenants', 'subscription_status',  "subscription_status VARCHAR(32) DEFAULT 'none'")
    _add_column_if_not_exists('tenants', 'current_period_end',   "current_period_end INTEGER")
    _add_column_if_not_exists('tenants', 'cancel_at_period_end', "cancel_at_period_end BOOLEAN DEFAULT false")
    _add_column_if_not_exists('tenants', 'timezone',             "timezone VARCHAR(64) DEFAULT 'UTC'")
    _add_column_if_not_exists('tenants', 'logo_url',             "logo_url VARCHAR(512)")
    _add_column_if_not_exists('tenants', 'notification_config',  "notification_config JSONB")


def downgrade() -> None:
    # Downgrade drops unconditionally — only run on a fresh DB
    with op.batch_alter_table('users') as batch_op:
        for col in ['role', 'name', 'email_verified']:
            try:
                batch_op.drop_column(col)
            except Exception:
                pass

    with op.batch_alter_table('tenants') as batch_op:
        for col in ['stripe_customer_id', 'subscription_status', 'current_period_end',
                    'cancel_at_period_end', 'timezone', 'logo_url', 'notification_config']:
            try:
                batch_op.drop_column(col)
            except Exception:
                pass
