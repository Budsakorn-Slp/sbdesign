"""เก็บ path ของหน้าใน user_events — ใช้นับคนเข้าเว็บและหาหน้ายอดนิยม

event ชนิดใหม่ (page_view / click_product) ไม่ต้อง migrate เพราะคอลัมน์ event เป็น String อยู่แล้ว
มีแค่ path ที่ต้องเพิ่ม — แยกเป็นคอลัมน์ไม่ยัดใน payload เพราะต้อง GROUP BY หาหน้ายอดนิยม

Revision ID: d9a4c21e7f55
Revises: c7d31e58ab40
"""
import sqlalchemy as sa
from alembic import op

revision = "d9a4c21e7f55"
down_revision = "c7d31e58ab40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_events", sa.Column("path", sa.String(200), nullable=True))
    # หน้ายอดนิยมถามด้วย "event + ช่วงเวลา" เสมอ — index คู่นี้ทำให้ไม่ต้องสแกนทั้งตาราง
    op.create_index("ix_user_events_event_created", "user_events", ["event", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_events_event_created", table_name="user_events")
    op.drop_column("user_events", "path")
