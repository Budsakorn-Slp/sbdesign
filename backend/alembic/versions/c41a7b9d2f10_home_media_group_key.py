"""home_media group_key/group_label (แท็บของบล็อก FIND YOUR INSPIRATION)

Revision ID: c41a7b9d2f10
Revises: ad380c8e36a7
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c41a7b9d2f10'
down_revision: Union[str, None] = 'ad380c8e36a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('home_media', schema=None) as batch_op:
        batch_op.add_column(sa.Column('group_key', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('group_label', sa.String(length=160), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('home_media', schema=None) as batch_op:
        batch_op.drop_column('group_label')
        batch_op.drop_column('group_key')
