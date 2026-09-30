"""customer_sales_links / customer_sales_events — ลูกค้าคนนี้เป็นของพนักงานคนไหน

ลูกค้าที่เคยซื้อกับพนักงานคนหนึ่ง ครั้งหน้ากลับมาควรได้คนเดิมดูแล — คนเดิมรู้บริบท
และเป็นเรื่องค่าคอมมิชชันด้วย ถ้าไม่เก็บไว้ ใครหยิบก่อนได้ก่อน

Revision ID: d2f4a81c60b7
Revises: c7e5a03b91d4
Create Date: 2026-09-30 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2f4a81c60b7'
down_revision: Union[str, None] = 'c7e5a03b91d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_sales_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sales_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.String(16), nullable=True),
        sa.Column("attach_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sale_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_at", sa.DateTime(), nullable=False),
        sa.Column("last_at", sa.DateTime(), nullable=False),
        sa.Column("last_sale_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("customer_user_id", "sales_user_id", name="uq_customer_sales"),
    )
    op.create_index("ix_csl_customer", "customer_sales_links", ["customer_user_id"])
    op.create_index("ix_csl_sales", "customer_sales_links", ["sales_user_id"])
    op.create_index("ix_csl_last_at", "customer_sales_links", ["last_at"])
    op.create_index("ix_csl_last_sale_at", "customer_sales_links", ["last_sale_at"])

    op.create_table(
        "customer_sales_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sales_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("branch_id", sa.String(16), nullable=True),
        sa.Column("cart_id", sa.String(36), nullable=True),
        sa.Column("doc_no", sa.String(32), nullable=True),
        sa.Column("previous_sales_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cse_customer", "customer_sales_events", ["customer_user_id"])
    op.create_index("ix_cse_sales", "customer_sales_events", ["sales_user_id"])
    op.create_index("ix_cse_kind", "customer_sales_events", ["kind"])
    op.create_index("ix_cse_created", "customer_sales_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("customer_sales_events")
    op.drop_table("customer_sales_links")
