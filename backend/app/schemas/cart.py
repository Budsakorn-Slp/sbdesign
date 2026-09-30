from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.catalog import ProductStockOut
from app.schemas.promo import TotalsOut


class CartItemOut(BaseModel):
    id: str
    matnr: str
    sku: str
    name: str
    variant: str | None = None
    spec: str | None = None
    image_url: str | None = None
    category_id: str | None = None
    qty: int
    unit_price: Decimal
    price_tier: str
    line_total: Decimal
    added_by: str
    added_by_name: str | None = None
    added_by_code: str | None = None
    added_at: datetime
    pending_ack: bool
    supply_mode: str
    plant_code: str | None = None
    atp_date: date | None = None
    requires_install: bool
    note: str | None = None
    selected: bool = True
    # ยอดของจาก cache (อายุไม่เกิน TTL) ไว้โชว์ป้ายสต็อกในตะกร้าเหมือนการ์ดสินค้า
    # ไม่ใช่ยอดสด — ตอนสั่งซื้อจริงระบบยิงเช็คทั้งตะกร้าอีกรอบอยู่แล้ว
    stock: ProductStockOut | None = None
    group: str | None = None      # regular | display | consign (จากตัวขึ้นต้น MATNR)
    pickup_only: bool = False     # ใส่ตะกร้าได้ แต่ยังชำระเงินออนไลน์ไม่ได้ ต้องรับที่สาขา


class CartPersonOut(BaseModel):
    id: str
    name: str
    points: int = 0
    sap_customer_no: str | None = None
    staff_code: str | None = None
    phone: str | None = None
    branch_id: str | None = None
    email: str | None = None
    default_address: str | None = None
    default_postcode: str | None = None


class DeliveryInfoOut(BaseModel):
    postcode: str | None = None
    address: str | None = None
    zone: str | None = None
    zone_name: str | None = None
    shipping_fee: Decimal | None = None
    install_fee: Decimal | None = None
    slot_id: str | None = None
    slot_date: date | None = None
    slot_period: str | None = None
    quoted_at: datetime | None = None


class PresoStepOut(BaseModel):
    """หนึ่งด่านก่อนบันทึกใบ PRE — หน้าเซลล์เอาไปทำเป็นเช็คลิสต์"""

    key: str
    title: str
    ok: bool
    note: str
    blocked: bool = False  # ติดอยู่ที่ด่านก่อนหน้า ยังไม่ถึงคิวทำอันนี้


class PresoReadyOut(BaseModel):
    ready: bool
    next: str | None = None
    message: str
    steps: list[PresoStepOut] = []


class CartOut(BaseModel):
    id: str
    no: str
    label: str | None = None
    status: str
    customer: CartPersonOut | None = None
    owner_sales: CartPersonOut | None = None
    is_guest: bool
    items: list[CartItemOut]
    count: int          # จำนวนชิ้นที่ติ๊กไว้ (= ที่คิดเงิน)
    subtotal: Decimal   # ยอดเฉพาะที่ติ๊กไว้
    pending_count: int
    all_count: int = 0       # จำนวนชิ้นทั้งตะกร้า (ป้ายบนหัวเว็บ)
    item_count: int = 0      # จำนวนบรรทัดทั้งหมดในตะกร้า
    selected_count: int = 0  # จำนวนบรรทัดที่ติ๊กไว้
    expires_at: datetime | None = None
    updated_at: datetime
    totals: TotalsOut | None = None
    delivery: DeliveryInfoOut | None = None
    preso: PresoReadyOut | None = None  # เฉพาะตะกร้าที่เซลล์ถือ — ด่านก่อนบันทึกใบ PRE


class AddItemIn(BaseModel):
    matnr: str = Field(min_length=1)
    qty: int = Field(default=1, ge=1, le=999)
    supply_mode: str | None = Field(default=None, pattern="^(takeaway|ship|install|pickup)$")
    plant_code: str | None = None
    note: str | None = None


class UpdateItemIn(BaseModel):
    qty: int | None = Field(default=None, ge=1, le=999)
    supply_mode: str | None = Field(default=None, pattern="^(takeaway|ship|install|pickup)$")
    plant_code: str | None = None
    note: str | None = None


class SelectIn(BaseModel):
    """ติ๊ก/เอาติ๊กออก — item_ids = None คือทั้งตะกร้า"""

    item_ids: list[str] | None = None
    selected: bool = True


class ShipToIn(BaseModel):
    """ปลายทางคร่าวๆ ของตะกร้า — ว่าง = ยังไม่เลือก (หน้าตะกร้าจะไม่โชว์ค่าส่ง)"""

    postcode: str | None = None


class MergeIn(BaseModel):
    source_cart_id: str
