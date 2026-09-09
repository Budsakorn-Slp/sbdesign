"""Group B: mirror/cache จาก SAP (sync เป็นรอบ) + stock_checks (Group A log ของเราเอง)"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import utcnow, uuid_pk


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # slug เช่น sofa
    name_th: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    room: Mapped[str | None] = mapped_column(String(40), nullable=True)  # bedroom / living / dining / office ...
    icon: Mapped[str | None] = mapped_column(String(40), nullable=True)  # material symbol
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class Material(Base):
    __tablename__ = "materials"

    matnr: Mapped[str] = mapped_column(String(18), primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    name_th: Mapped[str] = mapped_column(String(200), nullable=False)  # ชื่อที่ลูกค้าเห็น (display_name จากฐานเว็บ)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # ชื่อดิบจาก SAP "SELECTOR/กระจกแขวนM080/เวงเก้" — ลูกค้าไม่เห็น แต่เซลล์ค้นด้วยรหัสรุ่นแบบนี้
    name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variant: Mapped[str | None] = mapped_column(String(200), nullable=True)  # "ผ้ากันเปื้อน, สีเทาอ่อน"
    spec: Mapped[str | None] = mapped_column(String(200), nullable=True)  # "กว้าง 210 ซม."
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), index=True, nullable=True)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    room: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)  # "สีไม้อ่อน"
    style: Mapped[str | None] = mapped_column(String(100), nullable=True)  # "โมเดิร์น"
    image_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # ข้อมูลครบพอโชว์ลูกค้าไหม — ฐานเว็บตัดสินมาแล้วตอน rebuild (มีรูป+ราคา+ชื่อที่อ่านรู้เรื่อง)
    # ลูกค้าเห็นเฉพาะ True · เซลล์/แอดมินเห็นทั้งหมด เพราะต้องค้นเช็คสต็อกของที่ยังไม่ขึ้นเว็บ
    # default=True เพราะของที่ใส่มือ (seed/เทส) คือของที่ตั้งใจให้เห็นอยู่แล้ว
    # ตัวที่มาจาก ETL ไม่พึ่ง default — import_catalog เซ็ตค่าตาม is_public ของฐานเว็บทุกแถว
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    requires_install: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_takeaway_ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_new: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    volume_m3: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # สองตัวนี้มาจาก sync_product_signals (Magento) ไม่ใช่ SAP — ใช้จัดอันดับ "มาใหม่" / "ขายดี"
    created_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)  # วันที่ขึ้นเว็บ
    sold_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)  # ยอดขายในช่วงที่ ETL นับ
    # ชั้นสินค้า MAABC ของ SAP (A B C E G M N P R T V Z) — ฝ่ายสินค้าเป็นคนจัด
    abc_class: Mapped[str | None] = mapped_column(String(4), nullable=True)
    # ขายดีจริงตามที่บริษัทจัดชั้น = MAABC 'Z' · เชื่อถือได้กว่า sold_qty ซึ่งนับเฉพาะยอดบนเว็บ
    # (วัดกับ sb_product_signals: ชั้น Z เฉลี่ย 3.5 ชิ้น/ตัว · ชั้นอื่นไม่เกิน 1.1)
    is_bestseller: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    category: Mapped[Category | None] = relationship()
    brand: Mapped[Brand | None] = relationship()
    prices: Mapped[list["MaterialPrice"]] = relationship(back_populates="material", cascade="all, delete-orphan")


class MaterialPrice(Base):
    __tablename__ = "material_prices"

    id: Mapped[str] = uuid_pk()
    matnr: Mapped[str] = mapped_column(ForeignKey("materials.matnr", ondelete="CASCADE"), index=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)  # standard | Gold | Silver | compare_at
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    material: Mapped[Material] = relationship(back_populates="prices")


class Plant(Base):
    __tablename__ = "plants"

    plant_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # store | warehouse
    zone_codes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)


class StockCache(Base):
    """cache ระยะสั้น — SAP เป็นเจ้าของสต็อกจริงเสมอ ใช้แค่โชว์ในผลค้นหา + fallback ตอน SAP ล่ม"""

    __tablename__ = "stock_cache"

    matnr: Mapped[str] = mapped_column(String(18), primary_key=True)
    plant_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    atp_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class StockCheck(Base):
    """log ทุกครั้งที่กดเช็คสต็อก — ใช้อ้างอิงเมื่อลูกค้าเคลม 'ตอนนั้นบอกว่ามีของ'"""

    __tablename__ = "stock_checks"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    matnr: Mapped[str] = mapped_column(String(18), index=True, nullable=False)
    plant_code: Mapped[str] = mapped_column(String(8), nullable=False)
    qty_returned: Mapped[int] = mapped_column(Integer, nullable=False)
    atp_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(8), nullable=False)  # sap | cache
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
