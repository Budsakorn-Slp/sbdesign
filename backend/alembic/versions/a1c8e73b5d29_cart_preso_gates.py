"""carts.rev / stock_ok_rev / promo_rev — ด่านก่อนบันทึกใบ PRE

ใบ PRE จะบันทึกได้ต่อเมื่อ เช็คสต็อกผ่าน + เช็คโปรฯ แล้ว + จองคิวส่งแล้ว
ปัญหาคือ "เช็คแล้ว" ต้องหมายถึงเช็คกับของชุดปัจจุบัน ไม่ใช่ของเมื่อ 10 นาทีก่อน
เลยนับรุ่นของตะกร้าไว้ (rev) ทุกครั้งที่ของในตะกร้าเปลี่ยน แล้วจำว่าเช็คตอน rev ไหน
ถ้าเลขไม่ตรงกัน = ของเปลี่ยนหลังเช็ค ต้องเช็คใหม่

Revision ID: a1c8e73b5d29
Revises: f9b2d461ac83
Create Date: 2026-09-17 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c8e73b5d29'
down_revision: Union[str, None] = 'f9b2d461ac83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("carts", sa.Column("rev", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("carts", sa.Column("stock_ok_rev", sa.Integer(), nullable=True))
    op.add_column("carts", sa.Column("promo_rev", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("carts", "promo_rev")
    op.drop_column("carts", "stock_ok_rev")
    op.drop_column("carts", "rev")
