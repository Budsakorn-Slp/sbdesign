"""users.onboarded_at — เคยผ่านขั้นตั้งค่าบัญชีหลังล็อกอินครั้งแรกแล้วหรือยัง

ก่อนหน้านี้หน้า "เชื่อมบัญชีสมาชิก" ใช้เงื่อนไข "ยังไม่มี sap_customer_no" ซึ่งเป็นจริง
ตลอดไปสำหรับคนที่ไม่มีบัตรสมาชิก — เขาจึงเจอหน้าเดิมทุกครั้งที่ล็อกอิน ถึงจะกดข้ามไปแล้ว
ก็ตาม · เก็บเป็นคอลัมน์แทนเพราะต้องจำข้ามอุปกรณ์ (localStorage จำไม่ได้เมื่อเปลี่ยนเครื่อง)

Revision ID: e1c9b7a45d20
Revises: d9a4c21e7f55
"""
import sqlalchemy as sa
from alembic import op

revision = "e1c9b7a45d20"
down_revision = "d9a4c21e7f55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarded_at", sa.DateTime(), nullable=True))
    # บัญชีที่มีอยู่แล้วถือว่าผ่านขั้นนี้ไปแล้ว — ไม่งั้นลูกค้าเก่าทุกคนจะโดนถามข้อมูลใหม่
    # ครั้งแรกที่ล็อกอินหลังอัปเดต ทั้งที่เคยกรอกไปแล้ว
    op.execute("UPDATE users SET onboarded_at = created_at WHERE onboarded_at IS NULL")


def downgrade() -> None:
    op.drop_column("users", "onboarded_at")
