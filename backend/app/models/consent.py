from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow, uuid_pk

KINDS = ("marketing",)  # ความยินยอมเก็บพฤติกรรมเพื่อการตลาด — แยกจากการใช้งานทั่วไป (ไม่ต้องขอ)


class Consent(Base):
    """ประวัติการให้/ถอนความยินยอม — เก็บทุกครั้ง ไม่ทับของเดิม (ต้องพิสูจน์ย้อนหลังได้)"""

    __tablename__ = "consents"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="web", nullable=False)  # web | sales_app | admin
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class DataRequest(Base):
    """คำขอตามสิทธิ์เจ้าของข้อมูล (PDPA): ขอสำเนา / ขอลบ"""

    __tablename__ = "data_requests"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # export | delete
    status: Mapped[str] = mapped_column(String(16), default="done", nullable=False)  # done | pending | rejected
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # สรุปว่าลบ/ลบตัวตนอะไรไปบ้าง
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
