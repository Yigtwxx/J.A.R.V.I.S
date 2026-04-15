"""add indexes on created_at and updated_at

Revision ID: e9a01b3c7f0c
Revises: 25fb8c4668db
Create Date: 2026-04-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e9a01b3c7f0c'
down_revision: Union[str, None] = '25fb8c4668db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.create_index('ix_profiles_created_at', ['created_at'])
        batch_op.create_index('ix_profiles_updated_at', ['updated_at'])


def downgrade() -> None:
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.drop_index('ix_profiles_updated_at')
        batch_op.drop_index('ix_profiles_created_at')
