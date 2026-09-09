"""เลขตะกร้าจริง — เรียง 001, 002, ... ไม่ซ้ำ ไม่ย้อน และผูกกับเจ้าของตะกร้า

เทสต์อื่นเปิดตะกร้าไว้ก่อนหน้าในฐานเดียวกัน เลยเช็ค "เดินหน้าทีละ 1" แทนการฟิกซ์ตัวเลข
ส่วนกฎ "เริ่มที่ 001" เช็คจากตัวนับตรง ๆ ด้วย key ใหม่ที่ยังไม่เคยใช้
"""

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.cart import Cart
from app.models.counter import DocCounter
from app.models.user import User
from app.services import cart_service, counter_service
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()


def _open(db, **kw) -> Cart:
    c = cart_service.new_cart(db, **kw)
    db.commit()
    return c


def test_counter_starts_at_one():
    with SessionLocal() as db:
        assert counter_service.next_value(db, "test-fresh-key") == 1
        assert counter_service.next_value(db, "test-fresh-key") == 2
        db.execute(delete(DocCounter).where(DocCounter.key == "test-fresh-key"))
        db.commit()


def test_numbers_run_in_order_and_are_padded():
    with SessionLocal() as db:
        carts = [_open(db, anon_token=f"tok-{i}", label="guest") for i in range(3)]
        seqs = [c.seq for c in carts]
        assert seqs == [seqs[0], seqs[0] + 1, seqs[0] + 2]
        assert [c.no for c in carts] == [f"{s:03d}" for s in seqs]


def test_deleting_a_cart_does_not_reuse_its_number():
    """ของเดิมนับจาก COUNT(*) — ลบตะกร้าแล้วใบถัดไปได้เลขซ้ำ ตัวนับจริงต้องเดินหน้าอย่างเดียว"""
    with SessionLocal() as db:
        first = _open(db, anon_token="tok-a")
        gone = first.seq
        db.execute(delete(Cart).where(Cart.id == first.id))
        db.commit()
        assert _open(db, anon_token="tok-b").seq == gone + 1


def test_number_keeps_going_past_999():
    with SessionLocal() as db:
        row = db.scalar(select(DocCounter).where(DocCounter.key == counter_service.CART))
        before = row.next_value
        row.next_value = 1000
        db.commit()
        assert _open(db, anon_token="tok-k").no == "1000"  # ไม่ตัดหลัก ไม่วนกลับ
        row = db.scalar(select(DocCounter).where(DocCounter.key == counter_service.CART))
        row.next_value = max(before, 1001)
        db.commit()


def test_cart_is_linked_to_the_user_row(client):
    """เปิดตะกร้าผ่าน API แล้วต้องมีแถวจริงในตาราง ผูกกับ user id ของคนที่ล็อกอิน"""
    h = auth_headers(client, "napat@email.com")
    r = client.get("/cart", headers=h)
    assert r.status_code == 200, r.text
    cart = r.json()
    with SessionLocal() as db:
        me = db.scalar(select(User).where(User.email == "napat@email.com"))
        row = db.scalar(select(Cart).where(Cart.id == cart["id"]))
        assert row.customer_user_id == me.id
        assert row.no == cart["no"] and row.seq is not None
