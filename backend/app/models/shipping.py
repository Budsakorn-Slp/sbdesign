"""ตารางค่าส่งของเราเอง — ยกมาจาก Amasty Shipping Rules บน Magento (10.9.12.67) แล้วคลีนแล้ว

ต้นทางเก็บทุกอย่างเป็น JSON ก้อนเดียวใน conditions_serialized ทำให้ 207 rule
ที่จริงเป็น "ตารางน้ำหนัก 2 คอลัมน์" ถูกเก็บเป็น rule 207 ตัว เวลาแก้ราคาต้องแก้ทีละตัว
ฝั่งเราแยกเป็น 2 ชนิดตามที่มันเป็นจริง:

  ship_rates  — ตารางอัตราตามน้ำหนัก (แถวละช่วง) แก้ราคาได้โดยไม่ต้องแตะ logic
  ship_rules  — กฎที่ไม่ใช่ตาราง (ส่งฟรีเมื่อครบยอด / เรตเดียว / ยกเว้นตาม SKU)

ช่วงน้ำหนักในตารางเราเป็นครึ่งเปิด [weight_from, weight_to) เสมอ
ต้นทางปนกันระหว่าง <= กับ < ทำให้ของที่หนัก 1.01 kg เป๊ะ ตกช่องว่างระหว่างแถว
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow, uuid_pk

# ชนิดของกฎใน ship_rules
RULE_KINDS = ("free", "flat", "table")


class ShipArea(Base):
    """เขตค่าส่ง — ต้นทางมี 2 เขต (กทม.+ปริมณฑล / ต่างจังหวัด) ตารางอัตราแยกตามนี้"""

    __tablename__ = "ship_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # 1 | 2 ตรงกับ Amasty
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)  # bkk_metro | upcountry
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # ใช้เมื่อไม่เข้า prefix ไหนเลย


class ShipAreaPostcode(Base):
    """รหัสไปรษณีย์ → เขต · เก็บเป็น prefix เพราะกฎจริงคุมทั้งจังหวัด

    ของเดิมใน Java แมปด้วย "ชื่อจังหวัด" ที่ hardcode ไว้ 6 จังหวัด ซึ่งพังทันทีที่
    ลูกค้าพิมพ์ชื่อจังหวัดต่างจากลิสต์ (เว้นวรรค/จ.นำหน้า) — ตะกร้าเรามีแต่รหัสไปรษณีย์อยู่แล้ว
    เลยแมปจากรหัสตรงๆ: 10=กทม.+สมุทรปราการ 11=นนทบุรี 12=ปทุมธานี 73=นครปฐม 74=สมุทรสาคร
    """

    __tablename__ = "ship_area_postcodes"

    prefix: Mapped[str] = mapped_column(String(5), primary_key=True)  # จับแบบยาวสุดชนะ
    area_id: Mapped[int] = mapped_column(ForeignKey("ship_areas.id"), index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ShipRate(Base):
    """หนึ่งแถว = หนึ่งช่วงน้ำหนักของหนึ่งเขต · [weight_from, weight_to) หน่วย kg"""

    __tablename__ = "ship_rates"
    __table_args__ = (UniqueConstraint("area_id", "weight_from", name="uq_ship_rate_area_from"),)

    id: Mapped[str] = uuid_pk()
    area_id: Mapped[int] = mapped_column(ForeignKey("ship_areas.id"), index=True, nullable=False)
    weight_from: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    weight_to: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)  # ไม่รวมค่านี้
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    source_rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # rule_id ฝั่ง Amasty ไว้ตามรอย
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)  # บันทึกตอน ETL คลีน เช่น "ปิดช่องว่าง"
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ShipRule(Base):
    """กฎที่ไม่ใช่ตารางอัตรา — เรียงตาม priority · stop_on_match=True แล้วหยุดหาต่อ

    conditions เป็น JSON คีย์ที่ engine รู้จัก (ไม่ใช่ JSON ดิบของ Amasty):
      min_subtotal / max_subtotal   ยอดสุทธิหลังหักส่วนลด
      any_sku            : [..]     ในตะกร้ามี SKU ตัวใดตัวหนึ่ง
      require_item_all_of: [..]     มีอย่างน้อย 1 รายการที่ผ่านครบทุกข้อ
                                    ข้อละ {attr, op, value} เช่น {"attr":"flat_pack","op":"==","value":"1"}
                                    (ตรงกับ Product\\Found value=1 aggregator=all ของ Amasty
                                     ซึ่งแปลว่า "มีอย่างน้อยหนึ่ง" ไม่ใช่ "ทุกรายการ")
      weight_attr        : ".."     เฉพาะ kind=table — นับน้ำหนักเฉพาะสินค้าที่ติดธงนี้
    """

    __tablename__ = "ship_rules"

    id: Mapped[str] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # free | flat | table
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    stop_on_match: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)  # ใช้เมื่อ kind=flat
    conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    source_rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ShipProductAttr(Base):
    """ธงค่าส่งรายสินค้า — 6 ตัวที่กฎจริงอ้างถึง

    mirror maison เดิมยกมาแค่ 4 ตัว ขาด flatpack_not_seller (ตัวที่ตารางอัตราทั้ง 207 แถวใช้กรอง)
    กับ flat_pack_bulky (ตัวกันของกฎเรตเดียว) — ขาดสองตัวนี้กฎเลยไม่เคยแมตช์เลยสักข้อ
    """

    __tablename__ = "ship_product_attrs"

    sku: Mapped[str] = mapped_column(String(40), primary_key=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    flat_pack: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flatpack_not_seller: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    flat_pack_bulky: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attr_19_rule: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attr_25_rule: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
