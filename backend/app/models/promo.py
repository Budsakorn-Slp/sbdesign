from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow, uuid_pk


class Promotion(Base):
    """mirror จาก SAP (sync รายวัน) — ใช้โชว์/อ้างอิง ส่วนการประเมินเงื่อนไขเรียกผ่าน SapClient.evaluate_promotions"""

    __tablename__ = "promotions"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    condition_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    discount_type: Mapped[str] = mapped_column(String(16), nullable=False)  # percent | amount | gift
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    stackable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AppliedDiscount(Base):
    """ใครให้ส่วนลด ใครอนุมัติ — ผูกรายตะกร้า (ไม่ใช่ global) และคัดลอกไป quotation ตอนออกเอกสาร"""

    __tablename__ = "applied_discounts"

    id: Mapped[str] = uuid_pk()
    cart_id: Mapped[str | None] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True, nullable=True)
    quotation_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # promotion | member_price | staff_manual
    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)  # staff_manual
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)  # snapshot ล่าสุด (คำนวณใหม่ทุกครั้งที่ตะกร้าเปลี่ยน)
    status: Mapped[str] = mapped_column(String(20), default="applied", nullable=False, index=True)  # applied | pending_approval | rejected | removed
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # เหตุผลขอส่วนลดเกินโควตา
    applied_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
