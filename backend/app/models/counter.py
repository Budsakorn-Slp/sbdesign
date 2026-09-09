from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow


class DocCounter(Base):
    """ตัวนับเลขเอกสาร — เลขที่ออกไปแล้วต้องไม่ซ้ำและไม่ย้อน

    ของเดิมนับจาก COUNT(*) ของตาราง ซึ่งเลขจะเลื่อนเมื่อมีการลบแถว และสองคนกดพร้อมกัน
    ก็ได้เลขเดียวกัน ตัวนับจริงเก็บเป็นแถวเดียวต่อ key แล้วล็อกแถวตอนหยิบเลข
    (SELECT ... FOR UPDATE) เลขที่หยิบไปแล้วจึงไม่ถูกหยิบซ้ำแม้ transaction จะ rollback ทีหลัง

    key: "cart" · "PRE" · "QT" · "PAY"  (ดู services/counter_service.py)
    """

    __tablename__ = "doc_counters"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
