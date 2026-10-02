"""ผูกลูกค้าทีหลังแล้วผลเช็คสต็อกต้องไม่หายไปเฉยๆ

เคสจริงที่เจอ: เซลล์ใส่ของ → กดเช็คสต็อก → กดเช็คโปรฯ → แล้วค่อยใส่เบอร์ผูกลูกค้า
ปรากฏว่าด่านเช็คสต็อกกับโปรฯ กลับไปเป็นยังไม่ทำ ต้องกดใหม่ทั้งคู่ เพราะการผูกลูกค้า
ยกของจากตะกร้าออนไลน์ของลูกค้าเข้ามา + คิดราคาใหม่ตามสิทธิสมาชิก = ตะกร้าเปลี่ยน

ของที่เปลี่ยนจริงต้องเช็คใหม่จริง ไม่ปล่อยผ่านให้ฟรี — แต่ "เช็คสต็อก" เป็นคำถามที่ระบบ
ถามเองได้ จึงยิงซ้ำให้อัตโนมัติ ส่วน "เช็คโปรฯ" เป็นด่านให้คนดู (ราคาเพิ่งเปลี่ยน อาจมี
โปรฯ สมาชิกใหม่ที่เข้าเงื่อนไข) จึงยังต้องกดเอง แต่ต้องบอกเหตุผลให้ชัดว่าทำไมหลุด
"""
import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.integrations.sap.base import SapError
from app.models.cart import Cart
from app.seed import seed_catalog
from app.services import availability_service
from tests.helpers import auth_headers, ensure_seed, login

MEMBER = "0949164600"


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)
    yield
    # ฐานเทสใช้ร่วมกันทั้ง session — ตะกร้าที่เทสนี้เปิดไว้ต้องปิดทิ้ง ไม่งั้นเทสไฟล์หลัง
    # ที่ล็อกอินด้วยสมาชิกคนเดียวกันจะเจอตะกร้าค้างแล้วนับของไม่ตรง
    with SessionLocal() as db:
        for c in db.scalars(select(Cart).where(Cart.status == "open")).all():
            c.status = "closed"
        db.commit()


def _online_cart(client, matnr="10031002"):
    """ลูกค้าเคยเล่นเว็บเองแล้วมีของค้างในตะกร้าออนไลน์"""
    hs = {"Authorization": "Bearer " + login(client, MEMBER)["access_token"]}
    client.post("/cart/items", json={"matnr": matnr, "qty": 1}, headers=hs)


def _steps(client, cid, hs):
    return {s["key"]: s for s in client.get(f"/sales/carts/{cid}", headers=hs).json()["preso"]["steps"]}


def _checked_cart(client, hs, promo=True):
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10023841", "qty": 1, "supply_mode": "ship"}, headers=hs)
    client.post(f"/sales/carts/{cart['id']}/availability", headers=hs)
    if promo:
        client.post("/promotions/evaluate", json={"cart_id": cart["id"]}, headers=hs)
    st = _steps(client, cart["id"], hs)
    assert st["stock"]["ok"] and (not promo or st["promo"]["ok"])
    return cart["id"]


def test_ผูกลูกค้าที่มีของค้างในตะกร้าออนไลน์_ด่านสต็อกต้องไม่หาย(client):
    hs = auth_headers(client, "SA-104", "staff")
    _online_cart(client)
    cid = _checked_cart(client, hs)
    client.post(f"/sales/carts/{cid}/attach-customer", json={"customer_key": MEMBER}, headers=hs)
    st = _steps(client, cid, hs)
    assert st["stock"]["ok"], st["stock"]["note"]          # ยิงซ้ำให้เองแล้ว
    assert not st["promo"]["ok"]                            # ยังต้องกดดูโปรฯ เอง
    assert "ยกของจากตะกร้าลูกค้า" in st["promo"]["note"]   # แต่บอกเหตุผลให้ชัด


def test_ผูกลูกค้าที่ไม่มีของค้าง_ก็ยังต้องเช็คโปรฯใหม่เพราะราคาเปลี่ยน(client):
    """ไม่มีของยกเข้ามาก็ยังต้องเดินเลขรุ่น — ราคาคิดใหม่ตามสิทธิสมาชิก ผลเช็คโปรฯ
    รอบก่อนคิดจากราคาที่ไม่ใช่ราคาของลูกค้าคนนี้ (เดิมปล่อยผ่านเงียบๆ)"""
    hs = auth_headers(client, "SA-104", "staff")
    cid = _checked_cart(client, hs)
    client.post(f"/sales/carts/{cid}/attach-customer", json={"customer_key": MEMBER}, headers=hs)
    st = _steps(client, cid, hs)
    assert st["stock"]["ok"], st["stock"]["note"]
    assert not st["promo"]["ok"] and "ราคาคิดใหม่ตามสิทธิสมาชิก" in st["promo"]["note"]


def test_ยังไม่เคยกดเช็คสต็อก_ห้ามยิงSAPให้เอง(client, monkeypatch):
    """คนยังไม่ได้ขอ อย่าไปกวน SAP แทนเขา — ด่านต้องยังเป็น "กดเช็คสต็อกก่อน" """
    hs = auth_headers(client, "SA-104", "staff")
    cid = _checked_cart(client, hs, promo=False)
    with SessionLocal() as db:                 # ล้างผลเช็คให้เหมือนยังไม่เคยกด
        c = db.get(Cart, cid)
        c.stock_ok_rev = None
        db.commit()
    calls = []

    class _นับ:
        def check(self, asks, customer_no, req_date):
            calls.append(asks)
            return [None for _ in asks]

    monkeypatch.setattr(availability_service, "get_availability_client", lambda: _นับ())
    client.post(f"/sales/carts/{cid}/attach-customer", json={"customer_key": MEMBER}, headers=hs)
    assert not calls, "ตะกร้าที่ยังไม่เคยเช็คต้องไม่ถูกยิงให้เอง"
    assert _steps(client, cid, hs)["stock"]["note"] == "กดเช็คสต็อกก่อน"


def test_ของที่ยกเข้ามาไม่มีสต็อก_ด่านต้องแดงไม่ใช่เขียวฟรี(client, monkeypatch):
    hs = auth_headers(client, "SA-104", "staff")
    _online_cart(client)
    cid = _checked_cart(client, hs)

    class _ไม่มีของ:
        def check(self, asks, customer_no, req_date):
            from app.integrations.sap.availability import AvailLine
            return [AvailLine(matnr=a.matnr, qty=a.qty, description=None, sales_unit="KIT",
                              unit_price=0, amount=0, available_qty=0, available_date=None) for a in asks]

    monkeypatch.setattr(availability_service, "get_availability_client", lambda: _ไม่มีของ())
    client.post(f"/sales/carts/{cid}/attach-customer", json={"customer_key": MEMBER}, headers=hs)
    st = _steps(client, cid, hs)
    assert not st["stock"]["ok"], "ยิงซ้ำแล้วของไม่พอ ต้องแดง"


def test_SAP_ล่มตอนยิงซ้ำ_ผูกลูกค้าต้องไม่พัง(client, monkeypatch):
    hs = auth_headers(client, "SA-104", "staff")
    _online_cart(client)
    cid = _checked_cart(client, hs)

    class _ล่ม:
        def check(self, asks, customer_no, req_date):
            raise SapError("gateway timeout")

    monkeypatch.setattr(availability_service, "get_availability_client", lambda: _ล่ม())
    r = client.post(f"/sales/carts/{cid}/attach-customer", json={"customer_key": MEMBER}, headers=hs)
    assert r.status_code == 200, r.text
    assert not _steps(client, cid, hs)["stock"]["ok"]


def test_ถอดลูกค้าออกก็บอกเหตุผลว่าทำไมต้องเช็คใหม่(client):
    hs = auth_headers(client, "SA-104", "staff")
    cid = _checked_cart(client, hs)
    client.post(f"/sales/carts/{cid}/attach-customer", json={"customer_key": MEMBER}, headers=hs)
    client.post("/promotions/evaluate", json={"cart_id": cid}, headers=hs)
    assert _steps(client, cid, hs)["promo"]["ok"]
    client.delete(f"/sales/carts/{cid}/attach-customer", headers=hs)
    st = _steps(client, cid, hs)
    assert not st["promo"]["ok"] and "ราคากลับเป็นราคาปกติ" in st["promo"]["note"]
