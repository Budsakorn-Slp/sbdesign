"""material_categories — สินค้าอยู่ได้หลายหมวด (หมวดชุดที่ยกมาจากเว็บจริง)

Revision ID: a7c3e91d5b48
Revises: e5b8c2d740a1
Create Date: 2026-09-15 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c3e91d5b48'
down_revision: Union[str, None] = 'e5b8c2d740a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'material_categories',
        sa.Column('matnr', sa.String(length=18), nullable=False),
        sa.Column('category_id', sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(['matnr'], ['materials.matnr'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('matnr', 'category_id'),
    )
    # กดหมวดแล้วต้องได้รายชื่อสินค้าเร็ว — ค้นจากฝั่ง category เป็นหลัก
    op.create_index('ix_material_categories_category_id', 'material_categories', ['category_id'])


def downgrade() -> None:
    op.drop_index('ix_material_categories_category_id', table_name='material_categories')
    op.drop_table('material_categories')
