"""users.branch_name — ชื่อสาขาที่พิมพ์บนเอกสาร

ใบเสนอราคาต้องบอกว่าออกจากสาขาไหน (ใบรับคำสั่งซื้อของระบบเดิมมี "319-DS. บางแค")
รหัสเก็บใน branch_id ที่มีอยู่แล้ว ส่วนชื่อเก็บคู่กันเพราะยังไม่มีทะเบียนสาขาฝั่ง SAP
ในฐานเรา — product_stock_sites มีชื่อก็จริงแต่โผล่เฉพาะสาขาที่บังเอิญมีของอยู่ตอนนั้น

Revision ID: e5b73c1d80a4
Revises: d8a2f06c91b7
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b73c1d80a4"
down_revision: Union[str, None] = "d8a2f06c91b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as b:
        b.add_column(sa.Column("branch_name", sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as b:
        b.drop_column("branch_name")
