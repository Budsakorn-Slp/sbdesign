"""เปลี่ยนชื่อ availability_cache -> product_stock ให้ตรงกับ FM ที่เรียกจริง

ตอนสร้างตารางนี้ยังเรียก ZAIBAPI_MATERIAL_AVAILABILITY อยู่ ภายหลังเปลี่ยนมาใช้
ZAIBAPI_MATERIAL_STOCK (ยอดรวมทุกสาขา) แต่ชื่อไม่ได้ตาม ทำให้สับสนกับ availability_service
ซึ่งยังเรียก AVAILABILITY จริงๆ อยู่สำหรับตอนขาย

Revision ID: e5b8c2d740a1
Revises: d3f7a91c5e84
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e5b8c2d740a1'
down_revision: Union[str, None] = 'd3f7a91c5e84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_availability_cache_fetched_at', table_name='availability_cache')
    op.rename_table('availability_cache', 'product_stock')
    op.create_index('ix_product_stock_fetched_at', 'product_stock', ['fetched_at'])


def downgrade() -> None:
    op.drop_index('ix_product_stock_fetched_at', table_name='product_stock')
    op.rename_table('product_stock', 'availability_cache')
    op.create_index('ix_availability_cache_fetched_at', 'availability_cache', ['fetched_at'])
