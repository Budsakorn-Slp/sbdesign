"""สิทธิ์ส่วนลดตามว่า "ใครถือตะกร้า"

ชื่อไฟล์ขึ้นต้น zz ให้รันท้ายสุดโดยตั้งใจ — ฐานเทสใช้ร่วมกันทั้ง session และเทสชุดนี้
ยึดตะกร้าของลูกค้าตัวอย่างไปผูกกับพนักงาน ถ้ารันก่อนไฟล์อื่นจะไปกวนสถานะที่ไฟล์นั้นคาดไว้

  ลูกค้าออนไลน์ (ไม่มีพนักงานดูแล)  -> กรอกโค้ดเองได้
  ลูกค้าที่พนักงานดูแลอยู่           -> แตะส่วนลดไม่ได้เลย ดูได้อย่างเดียว
  ลูกค้ากด "ออกจากการดูแล"          -> ส่วนลดหน้าร้านถูกถอดหมด ของยังอยู่ครบ
"""
import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed

CUSTOMER = "094-916-4600"


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)
    yield
    # ฐานเทสใช้ร่วมกันทั้ง session และไฟล์นี้เรียงมาก่อน test_step3/4/9
    # ถ้าทิ้งตะกร้าของลูกค้าคนนี้ค้างไว้ ไฟล์หลังจะหยิบใบเดิมไปใช้แล้วเจอของที่ไม่ได้ใส่เอง
    with SessionLocal() as db:
        from app.models.cart import Cart
        from app.models.user import User
        # ปิดใบทิ้งพอ ไม่ลบ — ประวัติ/ส่วนลด/audit อ้างถึง cart_id อยู่ ลบแล้ว FK พัง
        u = db.scalar(select(User).where(User.phone == CUSTOMER))
        for c in db.scalars(select(Cart).where(Cart.customer_user_id == (u.id if u else None))).all():
            c.status = "abandoned"
            c.owner_sales_id = None
            c.expires_at = None
        db.commit()


def _online_cart(client, hc):
    return client.post("/cart/items", json={"matnr": "10061050", "qty": 1}, headers=hc).json()


def _staff_cart_for_customer(client, hs, hc):
    """เซลล์เปิดใบ ใส่ของ แล้วผูกลูกค้า — ได้ตะกร้าที่พนักงานดูแล"""
    cart = client.post("/sales/carts", json={"label": "ดูแลลูกค้า"}, headers=hs).json()
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10061050", "qty": 9}, headers=hs)
    r = client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": CUSTOMER}, headers=hs)
    assert r.status_code == 200, r.text
    return cart["id"]


def test_ลูกค้าออนไลน์กรอกโค้ดเองได้(client):
    hc = auth_headers(client, CUSTOMER)
    cart = _online_cart(client, hc)
    r = client.post(f"/cart/{cart['id']}/discounts", json={"kind": "promotion", "promo_code": "TESTCODE"}, headers=hc)
    assert r.status_code == 201, r.text
    assert float(r.json()["totals"]["discount_total"]) == 50.0


def test_พนักงานดูแลอยู่_ลูกค้าแตะส่วนลดไม่ได้(client):
    hs = auth_headers(client, "SA-104", "staff")
    hc = auth_headers(client, CUSTOMER)
    cid = _staff_cart_for_customer(client, hs, hc)
    r = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "TESTCODE"}, headers=hc)
    assert r.status_code == 403 and "พนักงาน" in r.json()["detail"]


def test_พนักงานยังใส่ส่วนลดให้ได้ตามปกติ(client):
    hs = auth_headers(client, "SA-104", "staff")
    hc = auth_headers(client, CUSTOMER)
    cid = _staff_cart_for_customer(client, hs, hc)
    assert client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=hs).status_code == 201


def test_ออกจากการดูแล_ถอดส่วนลดแต่ของยังอยู่(client):
    hs = auth_headers(client, "SA-104", "staff")
    hc = auth_headers(client, CUSTOMER)
    cid = _staff_cart_for_customer(client, hs, hc)
    client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=hs)
    before = client.get("/cart", headers=hc).json()
    assert float(before["totals"]["discount_total"]) > 0

    r = client.request("DELETE", f"/cart/{cid}/sales-owner", headers=hc)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["owner_sales"] is None                      # ไม่มีพนักงานดูแลแล้ว
    assert float(after["totals"]["discount_total"]) == 0     # สิทธิ์หน้าร้านถูกถอด
    assert len(after["items"]) == len(before["items"])       # ของไม่หาย

    # ออกมาแล้วกรอกโค้ดออนไลน์เองได้
    assert client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "TESTCODE"}, headers=hc).status_code == 201


def test_พนักงานกดปุ่มของลูกค้าไม่ได้(client):
    hs = auth_headers(client, "SA-104", "staff")
    hc = auth_headers(client, CUSTOMER)
    cid = _staff_cart_for_customer(client, hs, hc)
    assert client.request("DELETE", f"/cart/{cid}/sales-owner", headers=hs).status_code == 403


def test_กดออกซ้ำไม่ได้(client):
    """ตะกร้าที่ไม่มีพนักงานดูแลแล้ว กดออกอีกครั้งต้องบอกว่าไม่มีให้ออก ไม่ใช่เงียบๆ ผ่าน"""
    hs = auth_headers(client, "SA-104", "staff")
    hc = auth_headers(client, CUSTOMER)
    cid = _staff_cart_for_customer(client, hs, hc)
    assert client.request("DELETE", f"/cart/{cid}/sales-owner", headers=hc).status_code == 200
    assert client.request("DELETE", f"/cart/{cid}/sales-owner", headers=hc).status_code == 409
