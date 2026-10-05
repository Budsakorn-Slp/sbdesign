"""quotation_lines.list_price — ราคาตั้ง (ป้าย) ณ วันออกใบ

ใบเสนอราคาต้องโชว์ว่าของชิ้นนี้ลดมาจากราคาเท่าไร · ไปถามแคตตาล็อกตอนพิมพ์เอกสารไม่ได้
เพราะ ETL อัปเดตราคาทุกวัน แล้วใบเก่าจะโชว์ส่วนลดที่ไม่ตรงกับที่ตกลงกับลูกค้าไว้

แถวเดิมเติมด้วย unit_price (= ไม่มีส่วนลด) ซึ่งตรงกับที่เอกสารเคยแสดง

Revision ID: c3f1a7b24e05
Revises: b7c9e2a14d38
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3f1a7b24e05"
down_revision: Union[str, None] = "b7c9e2a14d38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("quotation_lines", schema=None) as b:
        b.add_column(sa.Column("list_price", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.execute("UPDATE quotation_lines SET list_price = unit_price WHERE list_price = 0")
    with op.batch_alter_table("quotation_lines", schema=None) as b:
        b.alter_column("list_price", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("quotation_lines", schema=None) as b:
        b.drop_column("list_price")
