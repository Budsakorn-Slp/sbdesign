"""รายการชำระ: บันทึกเงินที่รับซ้ำ รอคืน (refund_due / refund_note / refunded_at)

Revision ID: d8a2f4c6e913
Revises: c71e5a9b3f40
Create Date: 2026-10-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8a2f4c6e913"
down_revision: Union[str, None] = "c71e5a9b3f40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as b:
        b.add_column(sa.Column("refund_due", sa.Numeric(12, 2), nullable=True))
        b.add_column(sa.Column("refund_note", sa.Text(), nullable=True))
        b.add_column(sa.Column("refunded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payments") as b:
        b.drop_column("refunded_at")
        b.drop_column("refund_note")
        b.drop_column("refund_due")
