"""materials.size_label / color_code — แกนตัวเลือกบนหน้าสินค้า (MVGR5T/MVGR6T)

Revision ID: e3a7c05d9b12
Revises: d8f1b93c2e47
Create Date: 2026-09-16 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3a7c05d9b12'
down_revision: Union[str, None] = 'd8f1b93c2e47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('size_label', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('color_code', sa.String(length=60), nullable=True))
        batch_op.create_index('ix_materials_size_label', ['size_label'])
        batch_op.create_index('ix_materials_color_code', ['color_code'])


def downgrade() -> None:
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.drop_index('ix_materials_color_code')
        batch_op.drop_index('ix_materials_size_label')
        batch_op.drop_column('color_code')
        batch_op.drop_column('size_label')
