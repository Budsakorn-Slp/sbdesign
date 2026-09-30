"""categories.source — หมวดมาจาก SAP หรือยกมาจากเว็บจริง

Revision ID: b2d4f60a9c17
Revises: a7c3e91d5b48
Create Date: 2026-09-15 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d4f60a9c17'
down_revision: Union[str, None] = 'a7c3e91d5b48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('categories', schema=None) as batch_op:
        # ตารางมีของอยู่แล้ว ต้องมี server_default — ของเดิมทั้งหมดมาจาก SAP
        batch_op.add_column(sa.Column('source', sa.String(length=8), nullable=False, server_default='sap'))


def downgrade() -> None:
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_column('source')
