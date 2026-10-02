"""member link events

ประวัติการผูก/ถอดเลขสมาชิกเข้ากับบัญชีเว็บ รวมครั้งที่ไม่ผ่าน

หมายเหตุ: autogenerate เสนอให้เปลี่ยนชื่อ index ของ customer_sales_* และลบ index
ของ user_events มาด้วย ซึ่งเป็นแค่ชื่อที่ต่างกันระหว่างโมเดลกับฐานที่สร้างไปแล้ว
ไม่เกี่ยวกับงานนี้และไม่ได้ทำให้เร็วขึ้น — ตัดออก migration นี้สร้างตารางใหม่อย่างเดียว

Revision ID: 3e7995d9d5f6
Revises: d2f4a81c60b7
Create Date: 2026-10-02 10:04:12.002843
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3e7995d9d5f6"
down_revision: Union[str, None] = "d2f4a81c60b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "member_link_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("sap_customer_no", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("via", sa.String(length=16), nullable=True),
        sa.Column("phone_masked", sa.String(length=32), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("device", sa.String(length=200), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("member_link_events", schema=None) as b:
        b.create_index(b.f("ix_member_link_events_created_at"), ["created_at"], unique=False)
        # ค้นด้วยเลขสมาชิกเรียงตามเวลา = คำถามหลักเวลามีข้อพิพาท ("ใครแตะเลขนี้บ้าง")
        b.create_index("ix_member_link_events_cust", ["sap_customer_no", "created_at"], unique=False)
        b.create_index(b.f("ix_member_link_events_kind"), ["kind"], unique=False)
        b.create_index(b.f("ix_member_link_events_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("member_link_events", schema=None) as b:
        b.drop_index(b.f("ix_member_link_events_user_id"))
        b.drop_index(b.f("ix_member_link_events_kind"))
        b.drop_index("ix_member_link_events_cust")
        b.drop_index(b.f("ix_member_link_events_created_at"))
    op.drop_table("member_link_events")
