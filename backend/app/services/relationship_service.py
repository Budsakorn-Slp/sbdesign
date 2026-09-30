"""ลูกค้าคนนี้เป็นของพนักงานคนไหน — บันทึก ค้นหา และเสนอคนเดิมให้ดูแลต่อ

กติกาที่ตกลงกัน:
  ลูกค้าที่เคยซื้อกับพนักงานคนหนึ่ง ครั้งหน้ากลับมาให้คนเดิมดูแลต่อ

"เคยซื้อ" หนักกว่า "เคยคุย" เสมอ — คนที่ปิดการขายได้คือคนที่ลงแรงจริง
ถ้ายังไม่มีใครขายได้เลย ค่อยดูว่าใครคุยล่าสุด

ตรงนี้ทำแค่ "รู้ว่าใครควรดูแล" เท่านั้น ยังไม่ได้บังคับหรือแจ้งเตือนใคร
การแจ้งเตือนพนักงาน (noti) รอสรุปวิธีส่งอีกที — ดู notify_owner() ท้ายไฟล์
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common import utcnow
from app.models.relationship import CustomerSalesEvent, CustomerSalesLink
from app.models.user import User


def _link(db: Session, customer_id: str, sales_id: str) -> CustomerSalesLink:
    row = db.scalar(select(CustomerSalesLink).where(
        CustomerSalesLink.customer_user_id == customer_id,
        CustomerSalesLink.sales_user_id == sales_id,
    ))
    if not row:
        row = CustomerSalesLink(customer_user_id=customer_id, sales_user_id=sales_id)
        db.add(row)
        db.flush()
    return row


def owner_of(db: Session, customer_id: str) -> CustomerSalesLink | None:
    """พนักงานที่ "ควร" ดูแลลูกค้ารายนี้ — คนที่ขายได้ล่าสุด ถ้าไม่มีใครขายได้ก็คนที่คุยล่าสุด

    คืน None ถ้าลูกค้ายังไม่เคยเจอพนักงานคนไหนเลย (ลูกค้าใหม่/ซื้อออนไลน์ล้วน)
    """
    rows = db.scalars(select(CustomerSalesLink).where(CustomerSalesLink.customer_user_id == customer_id)).all()
    if not rows:
        return None
    sold = [r for r in rows if r.sale_count > 0]
    pool = sold or rows
    key = (lambda r: r.last_sale_at or r.last_at) if sold else (lambda r: r.last_at)
    return max(pool, key=key)


def history_of(db: Session, customer_id: str, limit: int = 50) -> list[CustomerSalesEvent]:
    return list(db.scalars(
        select(CustomerSalesEvent)
        .where(CustomerSalesEvent.customer_user_id == customer_id)
        .order_by(CustomerSalesEvent.created_at.desc())
        .limit(limit)
    ).all())


def customers_of(db: Session, sales_id: str, limit: int = 200) -> list[CustomerSalesLink]:
    """ลูกค้าในมือของพนักงานคนนี้ — เรียงคนที่ขยับล่าสุดขึ้นก่อน"""
    return list(db.scalars(
        select(CustomerSalesLink)
        .where(CustomerSalesLink.sales_user_id == sales_id)
        .order_by(CustomerSalesLink.last_at.desc())
        .limit(limit)
    ).all())


def _event(db: Session, kind: str, customer_id: str, sales: User | None, *,
           cart_id: str | None = None, doc_no: str | None = None,
           previous_sales_id: str | None = None, note: str | None = None) -> None:
    db.add(CustomerSalesEvent(
        customer_user_id=customer_id,
        sales_user_id=sales.id if sales else None,
        kind=kind,
        branch_id=sales.branch_id if sales else None,
        cart_id=cart_id, doc_no=doc_no,
        previous_sales_user_id=previous_sales_id,
        note=note,
    ))


def record_attach(db: Session, customer_id: str, sales: User, cart_id: str | None = None) -> dict:
    """พนักงานผูกลูกค้ากับตะกร้า — นับครั้ง และบอกว่าไปทับของคนอื่นไหม

    คืนข้อมูลให้ผู้เรียกตัดสินใจต่อ (จะเตือนบนจอ/ส่ง noti หรือไม่) ไม่ได้ห้ามเอง
    เพราะหน้าร้านจริงลูกค้าเดินเข้ามาหาใครก็ได้ การบล็อกจะทำให้ขายไม่ได้
    """
    before = owner_of(db, customer_id)
    taken_over = bool(before and before.sales_user_id != sales.id)

    row = _link(db, customer_id, sales.id)
    row.attach_count += 1
    row.last_at = utcnow()
    row.branch_id = sales.branch_id
    _event(db, "attach", customer_id, sales, cart_id=cart_id,
           previous_sales_id=before.sales_user_id if taken_over else None,
           note="รับช่วงต่อจากพนักงานคนอื่น" if taken_over else None)
    db.flush()
    return {
        "taken_over": taken_over,
        "previous_sales_user_id": before.sales_user_id if taken_over else None,
        "attach_count": row.attach_count,
        "sale_count": row.sale_count,
    }


def record_sale(db: Session, customer_id: str, sales: User, *, cart_id: str | None = None,
                doc_no: str | None = None) -> None:
    """ออกใบเสนอราคาสำเร็จ = ขายได้จริง — น้ำหนักสูงสุดในการตัดสินว่าใครเป็นเจ้าของ"""
    now = utcnow()
    row = _link(db, customer_id, sales.id)
    row.sale_count += 1
    row.last_sale_at = now
    row.last_at = now
    row.branch_id = sales.branch_id
    _event(db, "quotation", customer_id, sales, cart_id=cart_id, doc_no=doc_no)
    db.flush()


def record_release(db: Session, customer_id: str, sales_id: str | None, kind: str,
                   cart_id: str | None = None, note: str | None = None) -> None:
    """ลูกค้าหลุดจากการดูแล (พนักงานปลดเอง / ลูกค้ากดออกเอง)

    ไม่ลบความสัมพันธ์ทิ้ง — ประวัติว่าเคยดูแลกันยังมีค่า ทั้งตอนลูกค้ากลับมาและตอนตรวจสอบ
    """
    sales = db.get(User, sales_id) if sales_id else None
    _event(db, kind, customer_id, sales, cart_id=cart_id, note=note)
    db.flush()


def notify_owner(db: Session, customer_id: str, sales_id: str, reason: str) -> None:
    """แจ้งพนักงานเจ้าของว่าลูกค้ากลับมา — ยังไม่ได้ต่อช่องทางส่งจริง

    รอสรุปว่าจะส่งทางไหน (ในแอป / LINE / SMS) ตอนนี้บันทึกเป็นเหตุการณ์ไว้ก่อน
    พอได้ข้อสรุปแล้วมาต่อที่ฟังก์ชันนี้ที่เดียว ผู้เรียกไม่ต้องแก้
    """
    _event(db, "attach", customer_id, db.get(User, sales_id), note=f"[รอส่ง noti] {reason}")
    db.flush()
