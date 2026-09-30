"""ลูกค้าคนนี้เป็นของพนักงานคนไหน

กติกา: ลูกค้าที่เคยซื้อกับพนักงานคนหนึ่ง ครั้งหน้ากลับมาให้คนเดิมดูแลต่อ
       "เคยขายได้" หนักกว่า "เคยคุย" เสมอ

ชื่อไฟล์ขึ้นต้น zz ให้รันท้ายสุด — เทสชุดนี้ยึดตะกร้าของลูกค้าตัวอย่างไปผูกกับพนักงาน
ถ้ารันก่อนไฟล์อื่นจะไปกวนสถานะที่ไฟล์นั้นคาดไว้ (ฐานเทสใช้ร่วมกันทั้ง session)
"""
import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed

CUST = "1100440182"          # ณภัทร พงษ์ศรี
CUST_PHONE = "094-916-4600"


def _wipe_links():
    """ล้างความสัมพันธ์ของลูกค้าตัวอย่างให้สะอาด

    ต้องล้างทั้ง "ก่อน" และ "หลัง" — ไฟล์เทสอื่นที่รันก่อนหน้าก็ผูกลูกค้าคนนี้กับ SA-104
    เหมือนกัน ถ้าล้างแต่ตอนจบ เทสตัวแรกของไฟล์นี้จะนับครั้งต่อจากของเดิม
    """
    with SessionLocal() as db:
        from app.models.relationship import CustomerSalesEvent, CustomerSalesLink
        from app.models.user import User
        u = db.scalar(select(User).where(User.sap_customer_no == CUST))
        if u:
            for t in (CustomerSalesEvent, CustomerSalesLink):
                for r in db.scalars(select(t).where(t.customer_user_id == u.id)).all():
                    db.delete(r)
        db.commit()


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)
    _wipe_links()
    yield
    _wipe_links()
    with SessionLocal() as db:
        from app.models.cart import Cart
        from app.models.user import User
        u = db.scalar(select(User).where(User.sap_customer_no == CUST))
        if u:
            for c in db.scalars(select(Cart).where(Cart.customer_user_id == u.id)).all():
                c.status, c.owner_sales_id, c.expires_at = "abandoned", None, None
        db.commit()


def _cart_with_customer(client, h, matnr="10061050", qty=1):
    cart = client.post("/sales/carts", json={}, headers=h).json()
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": matnr, "qty": qty}, headers=h)
    r = client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": CUST}, headers=h)
    assert r.status_code == 200, r.text
    return cart["id"]


def _customer_id(client, hs):
    return client.get("/sales/carts", headers=hs).json() and _uid()


def _uid():
    with SessionLocal() as db:
        from app.models.user import User
        return db.scalar(select(User.id).where(User.sap_customer_no == CUST))


def test_ผูกลูกค้าแล้วจดว่าใครดูแล(client):
    h = auth_headers(client, "SA-104", "staff")
    _cart_with_customer(client, h)
    r = client.get(f"/sales/customers/{_uid()}/owner", headers=h).json()
    assert r["owner"]["staff_code"] == "SA-104"
    assert r["attach_count"] == 1 and r["sale_count"] == 0
    assert r["history"][0]["kind"] == "attach"


def test_คนที่ขายได้ชนะคนที่แค่คุย(client):
    """SA-105 ผูกทีหลัง แต่ SA-104 เป็นคนออกใบเสนอราคา — เจ้าของต้องเป็น SA-104"""
    h4 = auth_headers(client, "SA-104", "staff")
    h5 = auth_headers(client, "SA-105", "staff")
    uid = _uid()

    cid = _cart_with_customer(client, h4)
    client.post(f"/sales/carts/{cid}/availability", headers=h4)
    client.post("/promotions/evaluate", json={"cart_id": cid}, headers=h4)
    q = client.post("/delivery/quote", json={"cart_id": cid, "postcode": "10110"}, headers=h4).json()
    slot = next(s for s in q["slots"] if s["remaining"] > 0)
    client.post(f"/delivery/slots/{slot['id']}/hold", json={"cart_id": cid}, headers=h4)
    p = client.post("/presos", json={"cart_id": cid}, headers=h4)
    assert p.status_code == 201, p.text
    issued = client.post(f"/presos/{p.json()['preso_no']}/quotation", json={"force": True}, headers=h4)
    assert issued.status_code == 201, issued.text
    assert client.get(f"/sales/customers/{uid}/owner", headers=h4).json()["owner"]["staff_code"] == "SA-104"

    # SA-105 มาผูกทีหลัง — ขยับ last_at ของตัวเอง แต่ยังไม่เคยขายได้
    _cart_with_customer(client, h5)
    r = client.get(f"/sales/customers/{uid}/owner", headers=h5).json()
    assert r["owner"]["staff_code"] == "SA-104", "คนที่ขายได้ต้องชนะคนที่แค่มาผูกทีหลัง"


def test_บอกว่าไปรับช่วงต่อจากใคร(client):
    """ลูกค้ากลับมาวันหลังแล้วเจอพนักงานคนอื่น — ต้องจดไว้ว่ารับช่วงต่อจากใคร

    (ระหว่างที่ใบเก่ายังเปิดอยู่ ระบบกันไม่ให้คนอื่นผูกซ้ำอยู่แล้ว — 409
     เคสนี้คือใบเก่าปิดไปแล้ว ลูกค้าเดินกลับมาใหม่)
    """
    h4 = auth_headers(client, "SA-104", "staff")
    h5 = auth_headers(client, "SA-105", "staff")
    first = _cart_with_customer(client, h4)
    client.delete(f"/sales/carts/{first}", headers=h4)          # จบงานของคนแรก
    cart = client.post("/sales/carts", json={}, headers=h5).json()
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10061050", "qty": 1}, headers=h5)
    r = client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": CUST}, headers=h5)
    assert r.status_code == 200, r.text
    hist = client.get(f"/sales/customers/{_uid()}/owner", headers=h5).json()["history"]
    took = next(e for e in hist if e["note"] and "รับช่วงต่อ" in e["note"])
    assert took["sales"]["staff_code"] == "SA-105"


def test_ลูกค้าใหม่ยังไม่มีเจ้าของ(client):
    """ใช้ id ที่ไม่เคยมีความสัมพันธ์เลย — ลูกค้าใน seed ถูกไฟล์เทสอื่นผูกไปแล้ว
    การยืนยันว่า "ไม่มีเจ้าของ" จึงต้องใช้ id ที่สะอาดจริง ไม่งั้นเทสขึ้นกับลำดับการรัน"""
    h = auth_headers(client, "SA-104", "staff")
    r = client.get("/sales/customers/00000000-0000-0000-0000-000000000000/owner", headers=h).json()
    assert r["owner"] is None and r["attach_count"] == 0 and r["history"] == []


def test_ลูกค้าในมือของพนักงาน(client):
    h = auth_headers(client, "SA-104", "staff")
    _cart_with_customer(client, h)
    rows = client.get("/sales/my-customers", headers=h).json()
    mine = [x for x in rows if x["customer"]["id"] == _uid()]
    assert mine and mine[0]["still_mine"] is True


def test_ลูกค้ากดออกเองก็ยังเก็บประวัติไว้(client):
    hs = auth_headers(client, "SA-104", "staff")
    hc = auth_headers(client, CUST_PHONE)
    cid = _cart_with_customer(client, hs)
    assert client.request("DELETE", f"/cart/{cid}/sales-owner", headers=hc).status_code == 200
    r = client.get(f"/sales/customers/{_uid()}/owner", headers=hs).json()
    assert r["owner"]["staff_code"] == "SA-104", "ออกจากการดูแลไม่ได้ลบประวัติทิ้ง"
    assert any(e["kind"] == "left_care" for e in r["history"])
