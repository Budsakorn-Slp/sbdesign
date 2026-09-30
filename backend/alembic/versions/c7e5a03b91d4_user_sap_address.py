"""users.sap_address / sap_postcode — ที่อยู่ในทะเบียนสมาชิกฝั่ง SAP

แยกจากสมุดที่อยู่จัดส่ง (user_addresses) คนละความหมายกัน
  sap_address     = ที่อยู่ที่ลูกค้าให้ไว้ตอนสมัครสมาชิกที่สาขา · SAP เป็นเจ้าของ แก้บนเว็บไม่ได้
  user_addresses  = ปลายทางที่จะให้ไปส่งของ · ลูกค้าเพิ่ม/แก้/ลบเองได้ มีได้หลายที่

ของเดิมยัดรวมกันที่ users.default_address ช่องเดียว พอลูกค้าแก้ที่อยู่จัดส่งก็ทับที่อยู่
ทะเบียนไปเลย แล้วดูไม่ออกว่าอันไหนมาจากไหน

Revision ID: c7e5a03b91d4
Revises: b4d9f21e6c07
Create Date: 2026-09-17 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7e5a03b91d4'
down_revision: Union[str, None] = 'b4d9f21e6c07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("sap_address", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("sap_postcode", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "sap_postcode")
    op.drop_column("users", "sap_address")
