"""product_stock_sites — ของรหัสนี้อยู่ที่สาขาไหนบ้าง

มาจาก STOCK_ON_SITES ของ ZAIBAPI_MATERIAL_STOCK ซึ่งเพิ่งเพิ่มฟิลด์ NAME (ชื่อสาขา) มาให้
เก็บเฉพาะสาขาที่มีของจริง — SAP ตอบ 32 แถวต่อรหัสเสมอ เก็บหมดจะได้เกือบล้านแถว
เพื่อบอกว่าส่วนใหญ่เป็นศูนย์

Revision ID: d8a2f06c91b7
Revises: c3f1a7b24e05
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8a2f06c91b7"
down_revision: Union[str, None] = "c3f1a7b24e05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_stock_sites",
        sa.Column("matnr", sa.String(length=18), nullable=False),
        sa.Column("plant_code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("available_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("matnr", "plant_code"),
    )


def downgrade() -> None:
    op.drop_table("product_stock_sites")
