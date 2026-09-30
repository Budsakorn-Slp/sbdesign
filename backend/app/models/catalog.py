"""Group B: mirror/cache จาก SAP (sync เป็นรอบ) + stock_checks (Group A log ของเราเอง)"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
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
    # มาจากไหน: sap = ตามที่ฝ่ายสินค้าแบ่งใน SAP · web = ยกมาจากเว็บจริง (ดู etl/sync_web_categories)
    # ห้องไหนมีชุด web แล้วให้ใช้ชุดนั้นแทน sap — ตัดสินจากคอลัมน์นี้ ไม่ใช่เดาจากหน้าตาของ id
    # (เคยเดาจาก id ขึ้นต้น w- แล้วพังทันทีที่เปลี่ยน id เป็นชื่อที่อ่านรู้เรื่อง)
    source: Mapped[str] = mapped_column(String(8), default="sap", nullable=False)


class MaterialCategory(Base):
    """สินค้าอยู่ในหมวดไหนบ้าง — หลายหมวดต่อหนึ่งสินค้าได้

    ทำไมต้องมีตารางนี้ทั้งที่ materials.category_id มีอยู่แล้ว: หมวดชุดที่ยกมาจากเว็บจริง
    (Magento) ผูกสินค้าหนึ่งตัวไว้เฉลี่ย 3.1 หมวด เช่นเตียงตัวเดียวอยู่ทั้ง "ห้องนอน" และ
    "เตียงนอน" ถ้าฝืนเก็บหมวดเดียวจะหายไป 2 ใน 3 กดหมวดแล้วของไม่ครบ

    category_id เดิมยังอยู่ ใช้เป็นหมวดหลักของสินค้า (มาจาก SAP) และเป็นตัวสำรอง
    ให้สินค้าที่เว็บจริงไม่ได้จัดหมวดไว้
    """

    __tablename__ = "material_categories"

    matnr: Mapped[str] = mapped_column(ForeignKey("materials.matnr", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True, index=True)


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
    # SHORT_DESC จากฐานเว็บ — ประโยคเดียวสั้นๆ ใช้ในกล่อง "ข้อมูลสินค้า"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LONG_DESC — คำบรรยายเต็ม เอาไปวางเป็นบล็อกยาวใต้หน้าสินค้า
    # แยกคอลัมน์เพราะเป็นคนละที่แสดงผล ของเดิมยัดรวมช่องเดียว (long or short) เลยเลือกไม่ได้ว่าจะโชว์อันไหนตรงไหน
    description_long: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), index=True, nullable=True)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    room: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)  # "สีไม้อ่อน"
    # สองตัวนี้คือ "แกน" ของตัวเลือกบนหน้าสินค้า มาจาก SAP ตรงๆ (MVGR5T/MVGR6T)
    # size_label  = ขนาดในชุดเดียวกัน ("เตียง 5'" / "ตู้เสื้อผ้าบานเปิดขนาด 100")
    # color_code  = รหัสสีจริง ("SNOW WHITE" / "CANYON OAK") ใช้จับกลุ่มแทน color ภาษาไทย
    #               ซึ่งเขียนไม่เป็นมาตรฐาน (ขาว/สีขาว, สีไม้อ่อน/สีโอ๊คอ่อน = สีเดียวกัน)
    size_label: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    color_code: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
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


class MaterialImage(Base):
    """รูปสินค้าหลายใบต่อหนึ่งรหัส — ต้นทางคือ sb_products_image บนฐานเว็บ

    materials.image_url เก็บได้ใบเดียว (ใบหลัก) หน้าสินค้าจึงเคยเอารูปของ "สีอื่นในรุ่นเดียวกัน"
    มาวางเป็นแถวรูปย่อยแทน ซึ่งไม่ใช่รูปของสินค้าตัวนั้นจริงๆ ตารางนี้เก็บแกลเลอรีจริง
    เรียงตาม position ของต้นทาง
    """

    __tablename__ = "material_images"
    __table_args__ = (UniqueConstraint("matnr", "url", name="uq_material_image"),)

    id: Mapped[str] = uuid_pk()
    matnr: Mapped[str] = mapped_column(ForeignKey("materials.matnr", ondelete="CASCADE"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(400), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)


class MaterialPrice(Base):
    __tablename__ = "material_prices"

    id: Mapped[str] = uuid_pk()
    matnr: Mapped[str] = mapped_column(ForeignKey("materials.matnr", ondelete="CASCADE"), index=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)  # standard | compare_at
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


class ProductStock(Base):
    """ยอดของรวมทุกสาขา ไว้โชว์ในหน้ารายการสินค้า — มาจาก ZAIBAPI_MATERIAL_STOCK

    อย่าสับสนกับอีกสองตัวที่ชื่อคล้ายกัน:
      stock_cache          = ยอดรายสาขา (on_hand/reserved) ของ ZAIBAPI ตัวเก่า ใช้ในหน้าสินค้าเดี่ยว
      availability_service = ZAIBAPI_MATERIAL_AVAILABILITY ถามว่า "ลูกค้ารายนี้รับได้กี่ชิ้นวันนั้น"
                             ยิงสดตอนขายจริง ตัดเลขตามจำนวนที่ขอ และหักของที่บรรทัดก่อนจองไปแล้ว
      ตารางนี้             = "ของทั้งบริษัทมีเท่าไหร่" ใส่แค่รหัสสินค้า ไว้โชว์เฉยๆ

    เลขในนี้เก่าได้ถึง TTL และไม่ได้หักของที่คนอื่นกำลังจะซื้อ ห้ามใช้ตัดสินตอนขาย
    """

    __tablename__ = "product_stock"

    matnr: Mapped[str] = mapped_column(String(18), primary_key=True)
    ready_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # AVAILABLE_QUAN
    later_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # COMMITTED_QUAN
    later_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # SAP ไม่รู้จักรหัสนี้ (ตอบแถวเปล่า) — จำไว้จะได้ไม่เอาไปปนในชุดถัดไป เพราะรหัสเสียตัวเดียว
    # ทำให้ทั้งบิลตอบว่าง แล้วโค้ดต้องถอยไปไล่ยิงทีละรายการ
    sap_known: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # SAP ตอบ 999 ทุกสาขา = ไม่คุมสต็อก สั่งได้เสมอ (เจอในหมวดสั่งทำแบบ 100%)
    # ไม่ใช่ "ของหมด" ทั้งที่ ready_qty เป็น 0 — หน้าเว็บโชว์เป็นพรีออเดอร์และต้องไม่ถูกซ่อน
    made_to_order: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


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
