"""ตัวนับเลขเอกสารกลาง — หยิบเลขถัดไปแบบเรียงจริง ไม่ซ้ำ ไม่ย้อน

ใช้แถวเดียวต่อ key ใน doc_counters แล้วล็อกแถวตอนหยิบ ดังนั้นสองคนกดพร้อมกัน
ก็ได้คนละเลข (SQLite เขียนทีละ transaction อยู่แล้ว · MySQL/Postgres ใช้ FOR UPDATE)
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.counter import DocCounter

CART = "cart"


def next_value(db: Session, key: str, *, start: int = 1) -> int:
    """คืนเลขถัดไปแล้วเลื่อนตัวนับ — ต้องอยู่ใน transaction เดียวกับคนเรียก

    ไม่ commit ให้เอง: ถ้าคนเรียก rollback เลขนี้จะถูกทิ้งไปเฉย ๆ (เว้นช่องว่าง)
    ซึ่งดีกว่าเอาเลขมาใช้ซ้ำ
    """
    row = db.scalar(select(DocCounter).where(DocCounter.key == key).with_for_update())
    if row is None:
        row = DocCounter(key=key, next_value=start)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:  # อีก request สร้างแถวนี้ไปก่อนเสี้ยววินาที
            db.rollback()
            row = db.scalar(select(DocCounter).where(DocCounter.key == key).with_for_update())
    n = row.next_value
    row.next_value = n + 1
    db.flush()
    return n


def cart_no(db: Session) -> tuple[int, str]:
    """เลขตะกร้าถัดไป — 001, 002, ... เรียงตามลำดับที่เปิดจริง

    เก็บทั้งเลขดิบ (seq) ไว้เรียง/นับ และเลขที่โชว์ (no) ที่เติมศูนย์หน้าให้อ่านง่าย
    เกิน 999 แล้วก็ยาวขึ้นเองเป็น 1000 ไม่ต้องเปลี่ยนรูปแบบ
    """
    n = next_value(db, CART)
    return n, f"{n:03d}"
