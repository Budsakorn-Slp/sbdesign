"""availability_cache — จำนวนของจาก SAP ไว้โชว์ในหน้ารายการสินค้า

แยกจาก stock_cache เพราะคนละรูปทรง: stock_cache เป็นยอดรายสาขา (on_hand/reserved)
ส่วน availability ตอบเป็นรายบรรทัด (มีตอนนี้ / จะเข้าอีกเมื่อไหร่) ไม่บอกสาขา

Revision ID: c7d5e8b1f423
Revises: e1c9b7a45d20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c7d5e8b1f423'
down_revision: Union[str, None] = 'e1c9b7a45d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'availability_cache',
        sa.Column('matnr', sa.String(length=18), nullable=False),
        sa.Column('ready_qty', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('later_qty', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('later_date', sa.Date(), nullable=True),
        sa.Column('sap_known', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('matnr'),
    )
    op.create_index('ix_availability_cache_fetched_at', 'availability_cache', ['fetched_at'])


def downgrade() -> None:
    op.drop_index('ix_availability_cache_fetched_at', table_name='availability_cache')
    op.drop_table('availability_cache')
