"""พนักงานร่วมดูแลตะกร้า (ใส่รหัสเข้าร่วม)

Revision ID: b4d81e6c2a37
Revises: a7c3e9f15d22
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4d81e6c2a37"
down_revision: Union[str, None] = "a7c3e9f15d22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cart_handlers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cart_id", sa.String(36), sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cart_handlers_cart_id", "cart_handlers", ["cart_id"])
    op.create_index("ix_cart_handlers_user_id", "cart_handlers", ["user_id"])
    op.create_index("ux_cart_handlers_cart_user", "cart_handlers", ["cart_id", "user_id"], unique=True)


def downgrade() -> None:
    op.drop_table("cart_handlers")
