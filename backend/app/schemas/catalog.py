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


class ProductStockOut(BaseModel):
    """ยอดของรวมทุกสาขาไว้โชว์บนการ์ดสินค้า — มาจาก cache อายุไม่เกิน TTL ไม่ใช่ยอดสด
    ตอนสั่งซื้อจริงระบบยิงเช็คใหม่ทั้งตะกร้าอยู่แล้ว เลขในนี้จึงเป็นแค่ตัวช่วยตัดสินใจ
    """

    ready_qty: int = 0  # มีของตอนนี้
    later_qty: int = 0  # จะเข้าเพิ่ม
    later_date: date | None = None
    made_to_order: bool = False  # สั่งทำ — สั่งได้เสมอ ไม่ต้องรอสต็อก
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
    compare_at_price: Decimal | None = None
    discount_percent: int | None = None
    requires_install: bool
    is_takeaway_ok: bool
    is_new: bool
    # ของที่ตั้งโชว์หน้าร้าน (MATNR กลุ่ม display) — หน้าเว็บเอาไปขึ้นป้าย ไม่ต้องรู้เลขนำหน้าเอง
    is_display: bool = False
    # ของตัวโชว์/ฝากขาย (กลุ่ม 20/25) — ซื้อได้ที่สาขาเท่านั้น และซื้อแล้วไม่รับเปลี่ยนคืน
    # หน้าเว็บอ่านธงนี้ ไม่ต้องรู้ว่ากลุ่มไหนบ้าง (กฎอยู่ที่ online_checkout_blocked_groups)
    pickup_only: bool = False
    tags: list[str] = []
    stock: ProductStockOut | None = None


class VariantOptionOut(BaseModel):
    """ตัวเลือกหนึ่งปุ่มบนหน้าสินค้า (ขนาด หรือ สี) — กดแล้วไปที่ MATNR ตัวนั้น"""

    label: str
    matnr: str
    image_url: str | None = None
    price: Decimal | None = None


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


class StockSiteOut(BaseModel):
    """สาขาที่มีของตัวนี้ — ชื่อมาจาก SAP ตรงๆ (ฟิลด์ NAME ของ STOCK_ON_SITES)"""

    plant_code: str
    name: str
    qty: int


class MaterialDetail(MaterialCard):
    barcode: str | None = None
    description: str | None = None            # SHORT_DESC — กล่อง "ข้อมูลสินค้า"
    description_long: str | None = None       # LONG_DESC — บล็อกยาวใต้หน้าสินค้า (HTML ล้างแล้ว)
    color: str | None = None
    style: str | None = None
    volume_m3: Decimal | None = None
    weight_kg: Decimal | None = None
    sold_qty: int = 0
    # ตัวเลือก 2 แกน — ว่างเมื่อรุ่นนั้นมีตัวเลือกเดียว (ดู variant_axes ใน api/catalog.py)
    # แกลเลอรีรูปจริงของสินค้าตัวนี้ เรียงตามลำดับของต้นทาง (ดู etl/import_product_gallery.py)
    images: list[str] = []
    sizes: list[VariantOptionOut] = []
    colors: list[VariantOptionOut] = []
    related_categories: list[CategoryRefOut] = []
    # สาขาที่มีของให้ไปดูได้จริง — ไม่รวมคลัง/ระดับบริษัท (ดู product_stock_service.sites_for)
    stock_sites: list[StockSiteOut] = []
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


class UnderstoodOut(BaseModel):
    """สิ่งที่ระบบตีความจากประโยคค้นหา — หน้าเว็บเอาไปโชว์เป็นชิปให้ผู้ใช้เห็นและกดถอดได้"""

    labels: list[str] = []          # "หมวด ตู้ข้างเตียง", "สีขาว", "ราคาไม่เกิน 20,000 บาท"
    dropped: list[str] = []         # เงื่อนไขที่ต้องยอมตัดถึงจะเจอของ (specs | color)
    category_id: str | None = None
    color: str | None = None
    min_price: float | None = None
    max_price: float | None = None


class SearchOut(BaseModel):
    items: list[MaterialCard]
    total: int
    q: str | None = None
    category: str | None = None
    facets: FacetsOut | None = None
    corrected: str | None = None            # ระบบแก้ตัวสะกดให้ถึงจะเจอ — โชว์ "แสดงผลของ ..." แทน
    understood: UnderstoodOut | None = None  # รอบนี้ใช้โหมดตีความประโยค
    relaxed: bool = False                    # ต้องผ่อนเป็น "เข้าคำใดคำหนึ่ง" ผลจึงไม่ตรงทั้งหมด


class SuggestItemOut(BaseModel):
    """หนึ่งบรรทัดในกล่องแนะนำใต้ช่องค้นหา"""

    kind: str                       # term | category | brand
    label: str
    href: str


class SuggestOut(BaseModel):
    q: str
    suggestions: list[SuggestItemOut] = []
    items: list[MaterialCard] = []   # สินค้าที่ตรงที่สุดไม่กี่ตัว โชว์พร้อมรูปในกล่องเดียวกัน


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


class InfoPageOut(BaseModel):
    """หน้าเนื้อหาคงที่ที่ยกมาจาก CMS ของเว็บจริง (ดู etl/sync_cms_pages.py)"""

    slug: str
    title: str
    body_html: str
    source_url: str | None = None
