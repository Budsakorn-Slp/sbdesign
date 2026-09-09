"""cart_items.selected — ติ๊กเลือกรายการที่จะคิดเงิน

Revision ID: a5c81f2ed310
Revises: f3a1c7d94b02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a5c81f2ed310'
down_revision: Union[str, None] = 'f3a1c7d94b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ของเดิมในตะกร้าถือว่าติ๊กไว้หมด (server_default=true) พฤติกรรมเดิมจึงไม่เปลี่ยน
    op.add_column('cart_items', sa.Column('selected', sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    op.drop_column('cart_items', 'selected')
