from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, utcnow, uuid_pk

CART_STATUSES = ("open", "merged", "converted", "abandoned")
SUPPLY_MODES = ("takeaway", "ship", "install", "pickup")


class Cart(Base, TimestampMixin):
    """1 เซลล์ถือได้หลายใบ · ลูกค้า/guest มีใบ open ได้ใบเดียว"""

    __tablename__ = "carts"

    id: Mapped[str] = uuid_pk()
    customer_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    owner_sales_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    anon_token: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    no: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)  # #8823
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    merged_into_cart_id: Mapped[str | None] = mapped_column(ForeignKey("carts.id"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # ตะกร้าที่เซลล์ถือหมดอายุอัตโนมัติ
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # จัดส่ง (STEP 7) - quote ล่าสุด
    ship_postcode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ship_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_zone: Mapped[str | None] = mapped_column(String(8), nullable=True)
    shipping_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    install_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    slot_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delivery_quoted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan", order_by="CartItem.added_at")
    customer = relationship("User", foreign_keys=[customer_user_id])
    owner_sales = relationship("User", foreign_keys=[owner_sales_id])

    @property
    def is_open(self) -> bool:
        return self.status == "open" and (self.expires_at is None or self.expires_at > utcnow())


class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[str] = uuid_pk()
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True, nullable=False)
    matnr: Mapped[str] = mapped_column(String(18), nullable=False)
    sku: Mapped[str] = mapped_column(String(40), nullable=False)
    name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    variant_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    spec_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    category_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    qty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_tier: Mapped[str] = mapped_column(String(16), default="standard", nullable=False)
    added_by: Mapped[str] = mapped_column(String(16), nullable=False)  # customer | sales
    added_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    pending_ack: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supply_mode: Mapped[str] = mapped_column(String(16), default="ship", nullable=False)
    plant_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    atp_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    requires_install: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    cart: Mapped[Cart] = relationship(back_populates="items")
    added_by_user = relationship("User", foreign_keys=[added_by_user_id])

    @property
    def line_total(self) -> Decimal:
        return self.unit_price_snapshot * self.qty


class CartItemHistory(Base):
    """ประวัติใส่/ลบ/แก้จำนวนของทุกตะกร้า — เก็บถาวร ใช้ตรวจย้อนหลัง"""

    __tablename__ = "cart_item_history"

    id: Mapped[str] = uuid_pk()
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"), index=True, nullable=False)
    matnr: Mapped[str] = mapped_column(String(18), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # add | update | remove | ack
    qty_before: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qty_after: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_by: Mapped[str] = mapped_column(String(16), nullable=False)  # role ของคนทำ: guest|customer|sales|manager
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
