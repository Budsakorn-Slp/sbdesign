"""ความสัมพันธ์ "ลูกค้าคนนี้เป็นของพนักงานคนไหน"

ทำไมต้องเก็บ:
  ลูกค้าที่เคยซื้อกับพนักงานคนหนึ่งแล้ว ครั้งหน้ากลับมาควรได้คนเดิมดูแล — คนเดิมรู้ว่า
  บ้านลูกค้าเป็นยังไง เคยซื้ออะไรไป ตกลงอะไรกันไว้ และเป็นเรื่องของค่าคอมมิชชันด้วย
  ถ้าไม่เก็บไว้ ใครหยิบก่อนได้ก่อน ซึ่งทะเลาะกันแน่

เก็บสองระดับ คนละหน้าที่:
  CustomerSalesLink  สรุปว่า "ลูกค้า A กับพนักงาน B ผูกกันมากี่ครั้ง ซื้อจริงกี่ครั้ง ล่าสุดเมื่อไร"
                     ใช้ตอบคำถาม "ลูกค้าคนนี้ของใคร" ได้ด้วย query เดียว
  CustomerSalesEvent ทุกเหตุการณ์ทีละบรรทัด ไม่ลบไม่ทับ ใช้ตรวจย้อนหลังเวลามีข้อพิพาท
                     (audit_logs เก็บทุกอย่างปนกัน ค้นเรื่องนี้ทีต้องไล่ทั้งกอง)
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow, uuid_pk

# เหตุการณ์ที่ทำให้ความสัมพันธ์เปลี่ยน — เรียงตามน้ำหนักที่ใช้ตัดสินว่า "ใครเป็นเจ้าของ"
EVENT_KINDS = (
    "attach",      # พนักงานผูกลูกค้ากับตะกร้า
    "detach",      # ปลดลูกค้าออกจากตะกร้า
    "left_care",   # ลูกค้ากดออกจากการดูแลเอง
    "quotation",   # ออกใบเสนอราคาให้ลูกค้ารายนี้ — ถือว่า "ขายจริง"
    "handover",    # ส่งต่อให้พนักงานคนอื่น (ยังไม่มีหน้าจอ เตรียมไว้)
)


class CustomerSalesLink(Base):
    """สรุปความสัมพันธ์ลูกค้า-พนักงาน หนึ่งคู่หนึ่งแถว"""

    __tablename__ = "customer_sales_links"
    __table_args__ = (UniqueConstraint("customer_user_id", "sales_user_id", name="uq_customer_sales"),)

    id: Mapped[str] = uuid_pk()
    customer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    sales_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # สาขา ณ ตอนที่ผูกครั้งล่าสุด — พนักงานย้ายสาขาได้ ต้องรู้ว่าตอนนั้นอยู่ที่ไหน
    branch_id: Mapped[str | None] = mapped_column(String(16), nullable=True)

    attach_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # นับเฉพาะที่ออกใบเสนอราคาสำเร็จ = ขายได้จริง ไม่ใช่แค่เดินมาคุย
    sale_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    first_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    # เวลาที่ขายได้ครั้งล่าสุด — ตัวตัดสินหลักว่าใครควรได้ดูแลต่อ
    last_sale_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class CustomerSalesEvent(Base):
    """ประวัติรายเหตุการณ์ — เขียนอย่างเดียว ไม่แก้ไม่ลบ"""

    __tablename__ = "customer_sales_events"

    id: Mapped[str] = uuid_pk()
    customer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    sales_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cart_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    doc_no: Mapped[str | None] = mapped_column(String(32), nullable=True)  # เลขใบเสนอราคา ถ้ามี
    # พนักงานคนก่อนหน้า ณ ตอนนั้น — ไว้ดูว่าลูกค้าถูกแย่ง/ส่งต่อจากใคร
    previous_sales_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
