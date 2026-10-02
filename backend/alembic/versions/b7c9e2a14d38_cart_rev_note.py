"""carts.rev_note — เหตุผลที่ผลเช็คสต็อก/โปรฯ หมดอายุ

เดิมด่านที่หมดอายุขึ้นแค่ "ตะกร้าเปลี่ยนหลังเช็คครั้งล่าสุด" ซึ่งไม่ได้บอกว่าเปลี่ยนเพราะอะไร
เซลล์ที่เพิ่งผูกลูกค้าแล้วเห็นผลเช็คหายไปจึงคิดว่าระบบพัง (ของจริงคือของในตะกร้าออนไลน์
ของลูกค้าไหลเข้ามา + ราคาคิดใหม่ตามสิทธิสมาชิก)

Revision ID: b7c9e2a14d38
Revises: a4b81c3f5e92
Create Date: 2026-10-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c9e2a14d38"
down_revision: Union[str, None] = "a4b81c3f5e92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("carts", schema=None) as b:
        b.add_column(sa.Column("rev_note", sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("carts", schema=None) as b:
        b.drop_column("rev_note")
