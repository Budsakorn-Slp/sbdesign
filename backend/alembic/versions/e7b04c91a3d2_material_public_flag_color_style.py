"""material: is_public + name_raw + color/style

Revision ID: e7b04c91a3d2
Revises: c41a7b9d2f10
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7b04c91a3d2'
down_revision: Union[str, None] = 'c41a7b9d2f10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name_raw', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('color', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('style', sa.String(length=100), nullable=True))
        # server_default '1' ไม่ใช่ '0': ของที่นำเข้ามาก่อนหน้านี้ผ่านเกณฑ์เดิม (มีราคา+รูป) อยู่แล้ว
        # ตั้งเป็น 0 จะทำให้เว็บไม่เหลือสินค้าสักตัวจนกว่าจะ import รอบใหม่
        batch_op.add_column(sa.Column('is_public', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.create_index(batch_op.f('ix_materials_is_public'), ['is_public'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_materials_is_public'))
        batch_op.drop_column('is_public')
        batch_op.drop_column('style')
        batch_op.drop_column('color')
        batch_op.drop_column('name_raw')
