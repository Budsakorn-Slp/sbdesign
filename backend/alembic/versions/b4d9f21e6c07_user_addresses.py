"""user_addresses — สมุดที่อยู่จัดส่งของลูกค้า (เก็บได้หลายที่อยู่)

ของเดิมเก็บได้ช่องเดียวที่ users.default_address ลูกค้าที่สลับที่อยู่ประจำ
(บ้าน/ที่ทำงาน/ส่งให้คนอื่น) ต้องพิมพ์ใหม่ทุกครั้ง และค่าส่งคิดจากรหัสไปรษณีย์
การพิมพ์ผิดจึงทำให้ค่าส่งผิดเขต ไม่ใช่แค่ความรำคาญ

Revision ID: b4d9f21e6c07
Revises: a1c8e73b5d29
Create Date: 2026-09-17 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4d9f21e6c07'
down_revision: Union[str, None] = 'a1c8e73b5d29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_addresses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(40), nullable=True),
        sa.Column("receiver", sa.String(120), nullable=False, server_default=""),
        sa.Column("phone", sa.String(32), nullable=False, server_default=""),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("sub", sa.String(120), nullable=True),
        sa.Column("district", sa.String(120), nullable=True),
        sa.Column("province", sa.String(120), nullable=True),
        sa.Column("postcode", sa.String(8), nullable=False, server_default=""),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_addresses_user_id", "user_addresses", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_addresses_user_id", table_name="user_addresses")
    op.drop_table("user_addresses")
