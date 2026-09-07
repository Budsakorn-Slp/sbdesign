from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, utcnow, uuid_pk


class Payment(Base, TimestampMixin):
    """เจตนาชำระเงิน 1 ครั้ง — ไม่มีช่องทางเงินสด (เซลล์ห้ามรับเงิน)"""

    __tablename__ = "payments"

    id: Mapped[str] = uuid_pk()
    payment_no: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)  # PAY-260907-0007
    quotation_id: Mapped[str] = mapped_column(ForeignKey("quotations.id"), index=True, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)  # qr_promptpay | card | installment | link
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # full | deposit
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)  # pending | paid | failed | expired | cancelled
    provider_ref: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    qr_payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # mock EMVCo payload สำหรับวาด QR
    pay_url: Mapped[str | None] = mapped_column(String(300), nullable=True)  # ลิงก์จ่ายที่ส่งเข้ามือถือลูกค้า
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # payload ดิบจาก webhook

    quotation = relationship("Quotation")


class SapSyncJob(Base, TimestampMixin):
    """คิว retry ตอน SAP ล่ม — จ่ายเงินสำเร็จแล้วต้องได้ SO ให้ได้"""

    __tablename__ = "sap_sync_jobs"

    id: Mapped[str] = uuid_pk()
    quotation_id: Mapped[str] = mapped_column(ForeignKey("quotations.id"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)  # pending | ok | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    quotation = relationship("Quotation")
