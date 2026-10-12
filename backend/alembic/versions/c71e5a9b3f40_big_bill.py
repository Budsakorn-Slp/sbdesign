"""บิลรวม (Big Bill): รวมหลายใบเสนอราคาจ่ายครั้งเดียว

Revision ID: c71e5a9b3f40
Revises: b4d81e6c2a37
Create Date: 2026-10-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c71e5a9b3f40"
down_revision: Union[str, None] = "b4d81e6c2a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "big_bills",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bill_no", sa.String(24), nullable=False, unique=True),
        sa.Column("customer_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("promo_code", sa.String(32), nullable=True),
        sa.Column("promo_title", sa.String(200), nullable=True),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_big_bills_customer_user_id", "big_bills", ["customer_user_id"])
    op.create_table(
        "big_bill_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bill_id", sa.String(36), sa.ForeignKey("big_bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quotation_id", sa.String(36), sa.ForeignKey("quotations.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_share", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_big_bill_items_bill_id", "big_bill_items", ["bill_id"])
    op.create_index("ix_big_bill_items_quotation_id", "big_bill_items", ["quotation_id"])
    with op.batch_alter_table("payments") as b:
        b.add_column(sa.Column("big_bill_id", sa.String(36), nullable=True))
        b.create_index("ix_payments_big_bill_id", ["big_bill_id"])
        b.create_foreign_key("fk_payments_big_bill_id", "big_bills", ["big_bill_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("payments") as b:
        b.drop_constraint("fk_payments_big_bill_id", type_="foreignkey")
        b.drop_index("ix_payments_big_bill_id")
        b.drop_column("big_bill_id")
    op.drop_table("big_bill_items")
    op.drop_table("big_bills")
