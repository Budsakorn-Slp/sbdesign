"""บิลรวม (Big Bill) — รวมใบเสนอราคาหลายใบของลูกค้าคนเดียว จ่ายครั้งเดียว

แต่ละใบยังเป็น SO แยกใน SAP เหมือนเดิม (ยอดขายยังนับให้พนักงานที่ออกใบนั้น)
ส่วนลดระดับบิล (โค้ดที่คิดจากยอดรวม) กระจายลงแต่ละใบตามสัดส่วนยอด ตอนจ่ายสำเร็จ
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import utcnow, uuid_pk


class BigBill(Base):
    __tablename__ = "big_bills"

    id: Mapped[str] = uuid_pk()
    bill_no: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)   # BB-261012-0001
    customer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)   # open | paid | cancelled
    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    promo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)     # รวมยอดสุทธิของทุกใบ
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["BigBillItem"]] = relationship(back_populates="bill", cascade="all, delete-orphan", lazy="selectin")
    customer = relationship("User", foreign_keys=[customer_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class BigBillItem(Base):
    __tablename__ = "big_bill_items"

    id: Mapped[str] = uuid_pk()
    bill_id: Mapped[str] = mapped_column(ForeignKey("big_bills.id", ondelete="CASCADE"), index=True, nullable=False)
    quotation_id: Mapped[str] = mapped_column(ForeignKey("quotations.id"), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)          # ยอดใบ ณ ตอนรวมบิล
    discount_share: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    bill: Mapped[BigBill] = relationship(back_populates="items")
    quotation = relationship("Quotation", lazy="selectin")
