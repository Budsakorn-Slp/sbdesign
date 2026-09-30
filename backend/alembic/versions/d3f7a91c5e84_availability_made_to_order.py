"""availability_cache.made_to_order — สินค้าสั่งทำ (SAP ตอบ 999 = ไม่คุมสต็อก)

ready_qty เป็น 0 เหมือนของหมด แต่ความหมายตรงข้าม: สั่งได้เสมอ
ต้องแยกธงไว้ ไม่งั้นตัวกรองจะซ่อนสินค้าสั่งทำทั้งหมดออกจากหน้ารายการ

Revision ID: d3f7a91c5e84
Revises: c7d5e8b1f423
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd3f7a91c5e84'
down_revision: Union[str, None] = 'c7d5e8b1f423'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('availability_cache') as b:
        b.add_column(sa.Column('made_to_order', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('availability_cache') as b:
        b.drop_column('made_to_order')
