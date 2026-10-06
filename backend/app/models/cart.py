from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
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
    # เลขตะกร้าจริง เรียงตามลำดับที่เปิด: seq = 1, 2, 3 ... · no = "001", "002" (เลขที่โชว์)
    # ออกจาก doc_counters ผ่าน counter_service.cart_no() — ไม่ได้นับจาก COUNT(*) แล้ว
    seq: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    no: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
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
    # ด่านก่อนบันทึกใบ PRE — rev เดินขึ้นทุกครั้งที่ของในตะกร้าเปลี่ยน
    # เช็คสต็อก/เช็คโปรฯ จะจำไว้ว่าเช็คตอน rev ไหน ถ้าเลขไม่ตรง rev ปัจจุบัน = ของเปลี่ยนหลังเช็ค
    # ต้องเช็คใหม่ (ตรงกับผังงาน: แก้ตะกร้าแล้ววนกลับไป Check Stock ครั้งที่ 1 เสมอ)
    rev: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stock_ok_rev: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promo_rev: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # เลขรุ่นเดินเพราะอะไร — ด่านที่หมดอายุจะได้บอกเหตุผลจริง ไม่ใช่ "ตะกร้าเปลี่ยน" เฉยๆ
    # เซลล์เจอผลเช็คหายไปโดยไม่รู้ว่าเพราะอะไรแล้วคิดว่าระบบพัง (เคสที่เจอ: ผูกลูกค้า
    # ทีหลังแล้วของในตะกร้าออนไลน์ของลูกค้าไหลเข้ามา)
    rev_note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # หมายเหตุหลักระดับทั้งตะกร้า — คนละช่องกับหมายเหตุรายสินค้า (cart_items.note)
    # ห้ามใช้ช่องเดียวกัน: อันหนึ่งเป็นคำสั่งถึงคนจัดส่ง อีกอันเป็นสเปกของชิ้นนั้น
    overall_remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan", order_by="CartItem.added_at")
    customer = relationship("User", foreign_keys=[customer_user_id])
    owner_sales = relationship("User", foreign_keys=[owner_sales_id])

    @property
    def is_open(self) -> bool:
        return self.status == "open" and (self.expires_at is None or self.expires_at > utcnow())

    @property
    def selected_items(self) -> list["CartItem"]:
        """เฉพาะรายการที่ลูกค้าติ๊กไว้ — ใช้กับทุกอย่างที่เป็นเงิน (ยอดรวม ส่วนลด ค่าส่ง ใบเสนอราคา)
        ของที่ไม่ติ๊กยังอยู่ในตะกร้าเหมือนเดิม แค่ไม่ถูกคิดเงินรอบนี้

        หน้าขายก็มีช่องติ๊กเหมือนกัน (เพิ่มทีหลัง) — ของที่พนักงานใส่ให้ติ๊กมาให้แล้ว
        และของที่ยกมาจากตะกร้าลูกค้าก็ถูกติ๊กให้ตอนผูกลูกค้า จะได้ไม่มีของตกหล่นจากบิลเงียบๆ
        """
        return [it for it in self.items if it.selected]


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
    selected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # ติ๊กในหน้าตะกร้า = คิดเงินรอบนี้
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


# รหัสบทบาทพนักงานในบิล — ตรงกับ partner function ฝั่ง SAP
STAFF_ROLES = {
    "Z1": "Designer 1 (วัดพื้นที่)",
    "Z2": "Designer 2 (ออกแบบ)",
    "Z3": "Sales Employee 1 (พนักงานขาย)",
    "Z4": "Sales Employee 2 (พนักงานขายร่วม)",
    "ZK": "Cat Manager 1 (ส่งต่องาน)",
}


class CartStaff(Base):
    """พนักงานที่เกี่ยวข้องกับบิลนี้ แยกตามบทบาท Z1/Z2/Z3/Z4/ZK — บทบาทละหนึ่งคน

    ชื่อกับรหัสคัดลอกมาจากทะเบียนพนักงานตอนเลือก ไม่ได้ให้พิมพ์เอง · เก็บซ้ำไว้ (ไม่ join)
    เพราะชื่อพนักงานเปลี่ยนได้ แต่บิลที่ออกไปแล้วต้องบอกชื่อ ณ วันนั้น
    """

    __tablename__ = "cart_staff"
    # บทบาทละหนึ่งคนต่อบิล — กันที่ฐานด้วย ไม่ใช่เชื่อโค้ดอย่างเดียว
    __table_args__ = (Index("ux_cart_staff_cart_role", "cart_id", "role_code", unique=True),)

    id: Mapped[str] = uuid_pk()
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True, nullable=False)
    role_code: Mapped[str] = mapped_column(String(4), nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    employee_code: Mapped[str] = mapped_column(String(32), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(120), nullable=False)
    assigned_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

