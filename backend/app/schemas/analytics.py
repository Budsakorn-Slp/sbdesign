from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, Field

from app.schemas.catalog import MaterialCard


class TrackIn(BaseModel):
    # หน้าที่เกิด event — page_view ใช้บอกว่าเปิดหน้าไหน
    path: str | None = Field(default=None, max_length=200)
    event: str
    matnr: str | None = None
    query: str | None = None
    source: str = "web"
    payload: dict | None = None
    purpose: str = "service"  # marketing = ต้องมี consent ไม่งั้นเก็บแบบไม่ระบุตัวตน


class OrderLineOut(BaseModel):
    matnr: str
    name: str
    qty: int
    unit_price: Decimal
    line_total: Decimal
    variant: str | None = None
    image_url: str | None = None
    linkable: bool = False        # มีหน้าสินค้าในเว็บ กดเข้าไปดูได้
    supply: str | None = None     # ยกกลับ / จัดส่ง / ส่ง+ติดตั้ง
    remark: str | None = None

    model_config = {"from_attributes": True}


class OrderStepOut(BaseModel):
    key: str
    label: str
    done: bool
    at: datetime | date | None = None


class OrderOut(BaseModel):
    so_no: str
    order_date: date
    status: str
    channel: str
    branch: str | None = None
    grand_total: Decimal
    delivery_date: date | None = None
    synced_at: datetime | None = None
    lines: list[OrderLineOut] = Field(default_factory=list)
    # ---- รายละเอียดแบบหน้าคำสั่งซื้อ (Shopee) ----
    key: str = ""                       # ใช้เปิดหน้ารายละเอียด /account/orders/{key}
    order_no: str | None = None         # เลขคำสั่งซื้อ (SO ใน SAP) · ยังไม่มี = รอยืนยัน
    quotation_no: str | None = None     # ใบที่จ่ายผ่านเว็บ
    source: str = "sap"                 # web = จ่ายผ่านเว็บ · sap = ประวัติจาก SAP (หน้าร้าน)
    status_text: str = ""
    ordered_at: datetime | None = None
    paid_at: datetime | None = None
    payment_method: str | None = None
    sales_name: str | None = None
    receiver: str | None = None
    phone: str | None = None
    ship_address: str | None = None
    subtotal: Decimal | None = None
    discount_total: Decimal | None = None
    shipping_fee: Decimal | None = None
    vat: Decimal | None = None
    steps: list[OrderStepOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class WishlistOut(BaseModel):
    in_wishlist: bool
    items: list[MaterialCard] = Field(default_factory=list)


class DailyJobOut(BaseModel):
    days: int
    stat_rows: int
    best_sellers: int
    top: list[str]
