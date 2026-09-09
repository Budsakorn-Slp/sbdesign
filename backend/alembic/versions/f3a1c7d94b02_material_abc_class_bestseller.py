"""material abc_class + is_bestseller (MAABC จาก SAP)

Revision ID: f3a1c7d94b02
Revises: e7b04c91a3d2
Create Date: 2026-09-09 10:12:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a1c7d94b02'
down_revision: Union[str, None] = 'e7b04c91a3d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('abc_class', sa.String(length=4), nullable=True))
        # server_default ต้องมี เพราะตารางมีของอยู่แล้ว ~25,000 แถว เติมคอลัมน์ NOT NULL เปล่าๆ ไม่ได้
        # ค่าเริ่มต้น 0 = ยังไม่ขายดี จนกว่า import_catalog รอบถัดไปจะเติมตาม MAABC
        batch_op.add_column(sa.Column('is_bestseller', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index(batch_op.f('ix_materials_is_bestseller'), ['is_bestseller'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('materials', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_materials_is_bestseller'))
        batch_op.drop_column('is_bestseller')
        batch_op.drop_column('abc_class')
