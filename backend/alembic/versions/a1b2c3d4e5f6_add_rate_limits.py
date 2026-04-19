"""add rate limits table

Revision ID: a1b2c3d4e5f6
Revises: e9a01b3c7f0c
Create Date: 2026-04-18 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = 'e9a01b3c7f0c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'rate_limits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=False),
        sa.Column('timestamp', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rate_limits_id', 'rate_limits', ['id'], unique=False)
    op.create_index('ix_rate_limits_ip_address', 'rate_limits', ['ip_address'], unique=False)
    op.create_index('ix_rate_limits_timestamp', 'rate_limits', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_rate_limits_timestamp', table_name='rate_limits')
    op.drop_index('ix_rate_limits_ip_address', table_name='rate_limits')
    op.drop_index('ix_rate_limits_id', table_name='rate_limits')
    op.drop_table('rate_limits')
