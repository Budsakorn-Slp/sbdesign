"""ลูกค้าไม่มีระดับสมาชิก (Gold/Silver) แล้ว — เหลือเลขสมาชิก + แต้มสะสม

ระดับสมาชิกไม่มีอยู่จริงในธุรกิจ ราคาที่ลูกค้าเห็นจึงเท่ากับราคาปกติทุกคน
สิทธิประโยชน์ไปอยู่ที่แต้มสะสมแทน ซึ่ง SAP เป็นเจ้าของตัวเลข

Revision ID: b4e2f1a7c308
Revises: e7b3c5a10d92
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b4e2f1a7c308'
down_revision: Union[str, None] = 'e7b3c5a10d92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('points', sa.Integer(), nullable=False, server_default='0'))
        b.drop_column('tier')


def downgrade() -> None:
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('tier', sa.String(length=16), nullable=True))
        b.drop_column('points')
