from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class CategoryOut(BaseModel):
    id: str
    name_th: str
    name_en: str | None = None
    room: str | None = None
    icon: str | None = None
    children: list["CategoryOut"] = []


class BrandOut(BaseModel):
    id: str
    name: str


class PlantOut(BaseModel):
    plant_code: str
    name: str
    type: str
    address: str | None = None

    model_config = {"from_attributes": True}


class StockSummaryOut(BaseModel):
    available_total: int = 0
    store_available: int = 0
    warehouse_available: int = 0
    fetched_at: datetime | None = None


class MaterialCard(BaseModel):
    matnr: str
    sku: str
    name_th: str
    name_en: str | None = None
    variant: str | None = None
    spec: str | None = None
    category_id: str | None = None
    category_name: str | None = None
    brand_id: str | None = None
    brand_name: str | None = None
    room: str | None = None
    image_url: str | None = None
    price: Decimal
    price_tier: str
    standard_price: Decimal
    member_price: Decimal | None = None  # ราคาสมาชิก (เห็นเมื่อล็อกอิน)
    compare_at_price: Decimal | None = None
    discount_percent: int | None = None
    requires_install: bool
    is_takeaway_ok: bool
    is_new: bool
    tags: list[str] = []
    stock: StockSummaryOut | None = None


class ColorOptionOut(BaseModel):
    """สีอื่นของรุ่นเดียวกัน — คนละ MATNR กัน จึงเป็นลิงก์ไปอีกสินค้า ไม่ใช่ตัวเลือกในตัวเดียว"""

    matnr: str
    color: str | None = None
    name_th: str
    image_url: str | None = None
    price: Decimal


class CategoryRefOut(BaseModel):
    """หมวดที่กดสลับได้ในแถบ "สินค้าที่เกี่ยวข้อง" — เอาแค่ id กับชื่อ ไม่ต้องพ่วงลูกมาทั้งกิ่ง"""

    id: str
    name_th: str


class MaterialDetail(MaterialCard):
    barcode: str | None = None
    description: str | None = None
    color: str | None = None
    style: str | None = None
    volume_m3: Decimal | None = None
    weight_kg: Decimal | None = None
    sold_qty: int = 0
    colors: list[ColorOptionOut] = []
    related_categories: list[CategoryRefOut] = []
    synced_at: datetime


class BrandFacetOut(BaseModel):
    id: str
    name: str
    count: int


class FacetsOut(BaseModel):
    """ตัวเลือกที่ยังกดได้จริงของผลค้นหาชุดนี้ — หน้าเว็บเอาไปวาดแถบตัวกรอง"""

    brands: list[BrandFacetOut] = []
    price_min: float | None = None
    price_max: float | None = None


class SearchOut(BaseModel):
    items: list[MaterialCard]
    total: int
    q: str | None = None
    category: str | None = None
    facets: FacetsOut | None = None


class StockRowOut(BaseModel):
    plant_code: str
    plant_name: str
    plant_type: str
    on_hand: int
    reserved: int
    available: int
    atp_date: date | None = None
    note: str | None = None


class StockOut(BaseModel):
    """พนักงานเห็นครบทุกสาขา · ลูกค้าเห็นแค่สรุป (ไม่เห็นสต็อกข้ามสาขา)"""

    matnr: str
    source: str
    stale: bool
    fetched_at: datetime
    stale_minutes: int
    available: bool
    earliest_atp: date | None = None
    rows: list[StockRowOut] = []
    error: str | None = None
