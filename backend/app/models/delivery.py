from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow, uuid_pk


class DeliveryZone(Base):
    """mirror จาก SAP: รหัสไปรษณีย์ → เขต + ค่าขนส่งฐาน + ค่าติดตั้ง"""

    __tablename__ = "delivery_zones"

    postcode: Mapped[str] = mapped_column(String(8), primary_key=True)
    zone: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    zone_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    base_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    install_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    lead_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DeliverySlot(Base):
    """คิวจัดส่ง: วัน + รอบ (am/pm) + โซน · quota จาก SAP · booked นับรวม hold ที่ยังไม่หมดอายุ"""

    __tablename__ = "delivery_slots"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # A-2026-09-15-am
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    period: Mapped[str] = mapped_column(String(4), nullable=False)  # am | pm
    zone: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    quota: Mapped[int] = mapped_column(Integer, nullable=False)
    booked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def remaining(self) -> int:
        return max(0, self.quota - self.booked)


class SlotHold(Base):
    """จองคิวชั่วคราว 15 นาที (ปล่อยอัตโนมัติเมื่อหมดอายุ) · confirmed=True เมื่อออกใบเสนอราคาแล้ว"""

    __tablename__ = "slot_holds"

    id: Mapped[str] = uuid_pk()
    slot_id: Mapped[str] = mapped_column(ForeignKey("delivery_slots.id"), index=True, nullable=False)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    released: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
