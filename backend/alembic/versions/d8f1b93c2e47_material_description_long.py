"""materials.description_long — คำบรรยายเต็มจาก LONG_DESC แยกจาก SHORT_DESC

Revision ID: d8f1b93c2e47
Revises: c5e2a83f14d6
Create Date: 2026-09-16 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8f1b93c2e47'
down_revision: Union[str, None] = 'c5e2a83f14d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description_long', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.drop_column('description_long')
