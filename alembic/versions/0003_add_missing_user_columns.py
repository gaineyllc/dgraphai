"""Add missing user columns (role, name, email_verified) + fix connector FK order

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-09
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add role, name, email_verified to users table (added in models.py but missed in 0001)
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('role',           sa.String(32),  nullable=True, server_default='member'))
        batch_op.add_column(sa.Column('name',           sa.String(256), nullable=True))
        batch_op.add_column(sa.Column('email_verified', sa.Boolean(),   nullable=True, server_default='false'))

    # Add stripe + settings fields to tenants table (added in models.py but missed in 0001)
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.add_column(sa.Column('stripe_customer_id',    sa.String(64),  nullable=True))
        batch_op.add_column(sa.Column('subscription_status',   sa.String(32),  nullable=True, server_default='none'))
        batch_op.add_column(sa.Column('current_period_end',    sa.Integer(),   nullable=True))
        batch_op.add_column(sa.Column('cancel_at_period_end',  sa.Boolean(),   nullable=True, server_default='false'))
        batch_op.add_column(sa.Column('timezone',              sa.String(64),  nullable=True, server_default='UTC'))
        batch_op.add_column(sa.Column('logo_url',              sa.String(512), nullable=True))
        batch_op.add_column(sa.Column('notification_config',   sa.JSON(),      nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('role')
        batch_op.drop_column('name')
        batch_op.drop_column('email_verified')

    with op.batch_alter_table('tenants') as batch_op:
        for col in ['stripe_customer_id','subscription_status','current_period_end',
                    'cancel_at_period_end','timezone','logo_url','notification_config']:
            batch_op.drop_column(col)
