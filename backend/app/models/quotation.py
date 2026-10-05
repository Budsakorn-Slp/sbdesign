from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, utcnow, uuid_pk


class Preso(Base, TimestampMixin):
    """ใบร่างที่ Save ไว้ — ดึงกลับมาทำต่อได้ (ลูกค้ากลับมาวันหลัง)"""

    __tablename__ = "presos"

    id: Mapped[str] = uuid_pk()
    preso_no: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)  # PRE-260907-0042
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"), index=True, nullable=False)
    sales_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)  # None = ลูกค้าสั่งเอง
    customer_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # รายการ + ราคา + โปร + คิวส่ง ณ วันนั้น
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)  # draft | quoted | expired | cancelled
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    cart = relationship("Cart")
    sales = relationship("User", foreign_keys=[sales_user_id])
    customer = relationship("User", foreign_keys=[customer_user_id])


class Quotation(Base):
    """จุดส่งต่อไป SAP — issued แล้วห้ามแก้ (cancel แล้วออกใหม่)"""

    __tablename__ = "quotations"

    id: Mapped[str] = uuid_pk()
    quotation_no: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)  # QT-260907-0055
    preso_id: Mapped[str] = mapped_column(ForeignKey("presos.id"), index=True, nullable=False)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"), index=True, nullable=False)
    customer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    sales_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    channel: Mapped[str] = mapped_column(String(24), default="in_store_assisted", nullable=False)  # online | in_store_assisted
    customer_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    shipping_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    install_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    shipping_discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)  # VAT 7% ที่รวมอยู่ในยอด
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)  # มัดจำ 20%
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ship_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_postcode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ship_zone: Mapped[str | None] = mapped_column(String(8), nullable=True)
    slot_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    slot_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    slot_period: Mapped[str | None] = mapped_column(String(4), nullable=True)
    stock_warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sap_so_no: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    sap_sync_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending | ok | failed
    sap_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="issued", nullable=False, index=True)  # issued | paid | converted | expired | cancelled
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    lines: Mapped[list["QuotationLine"]] = relationship(back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationLine.sort")
    preso = relationship("Preso")
    customer = relationship("User", foreign_keys=[customer_user_id])
    sales = relationship("User", foreign_keys=[sales_user_id])


class QuotationLine(Base):
    __tablename__ = "quotation_lines"

    id: Mapped[str] = uuid_pk()
    quotation_id: Mapped[str] = mapped_column(ForeignKey("quotations.id", ondelete="CASCADE"), index=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matnr: Mapped[str] = mapped_column(String(18), nullable=False)
    sku: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    variant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)   # ราคาที่ลูกค้าจ่ายจริงต่อหน่วย
    # ราคาตั้ง (ป้าย) ณ วันออกใบ — ต้องเก็บไว้ ไม่ใช่ไปถามแคตตาล็อกตอนพิมพ์เอกสาร
    # เพราะราคาตั้งเปลี่ยนได้ทุกวันจาก ETL แล้วใบเก่าจะโชว์ส่วนลดที่ไม่ตรงกับที่ตกลงกันไว้
    list_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    supply_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    plant_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    atp_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    added_by: Mapped[str] = mapped_column(String(16), nullable=False)  # ดูว่าเซลล์ช่วยขายได้เท่าไร
    requires_install: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    quotation: Mapped[Quotation] = relationship(back_populates="lines")
