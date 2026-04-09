"""Add agent heartbeat columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to scanner_agents
    op.add_column('scanner_agents', sa.Column('os',                 sa.String(64),  nullable=True))
    op.add_column('scanner_agents', sa.Column('hostname',           sa.String(256), nullable=True))
    op.add_column('scanner_agents', sa.Column('last_seen_at',       sa.DateTime(timezone=True), nullable=True))
    op.add_column('scanner_agents', sa.Column('files_indexed',      sa.Integer(),   nullable=True, server_default='0'))
    op.add_column('scanner_agents', sa.Column('files_pending',      sa.Integer(),   nullable=True, server_default='0'))
    op.add_column('scanner_agents', sa.Column('last_error',         sa.Text(),      nullable=True))
    op.add_column('scanner_agents', sa.Column('connector_statuses', sa.JSON(),      nullable=True))
    op.add_column('scanner_agents', sa.Column('created_at',         sa.DateTime(timezone=True), nullable=True))
    op.add_column('scanner_agents', sa.Column('created_by',         sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column('scanner_agents', 'os')
    op.drop_column('scanner_agents', 'hostname')
    op.drop_column('scanner_agents', 'last_seen_at')
    op.drop_column('scanner_agents', 'files_indexed')
    op.drop_column('scanner_agents', 'files_pending')
    op.drop_column('scanner_agents', 'last_error')
    op.drop_column('scanner_agents', 'connector_statuses')
    op.drop_column('scanner_agents', 'created_at')
    op.drop_column('scanner_agents', 'created_by')
