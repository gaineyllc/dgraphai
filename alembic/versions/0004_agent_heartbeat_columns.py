"""Add agent heartbeat columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-09

Idempotent — uses IF NOT EXISTS for all column additions.
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def _add_if_not_exists(table: str, column: str, ddl: str) -> None:
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


def upgrade():
    _add_if_not_exists('scanner_agents', 'os',                 'os VARCHAR(64)')
    _add_if_not_exists('scanner_agents', 'hostname',           'hostname VARCHAR(256)')
    _add_if_not_exists('scanner_agents', 'last_seen_at',       'last_seen_at TIMESTAMPTZ')
    _add_if_not_exists('scanner_agents', 'files_indexed',      'files_indexed INTEGER DEFAULT 0')
    _add_if_not_exists('scanner_agents', 'files_pending',      'files_pending INTEGER DEFAULT 0')
    _add_if_not_exists('scanner_agents', 'last_error',         'last_error TEXT')
    _add_if_not_exists('scanner_agents', 'connector_statuses', 'connector_statuses JSONB')
    _add_if_not_exists('scanner_agents', 'created_at',         'created_at TIMESTAMPTZ')
    _add_if_not_exists('scanner_agents', 'created_by',         'created_by UUID')


def downgrade():
    with op.batch_alter_table('scanner_agents') as batch_op:
        for col in ['os', 'hostname', 'last_seen_at', 'files_indexed', 'files_pending',
                    'last_error', 'connector_statuses', 'created_at', 'created_by']:
            try:
                batch_op.drop_column(col)
            except Exception:
                pass
