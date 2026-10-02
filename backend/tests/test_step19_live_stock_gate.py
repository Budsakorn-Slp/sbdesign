"""ด่านเช็คสต็อกสดตอนออกใบเสนอราคา — ต้องถาม SAP จริง ไม่ใช่ตอบ "ครบ" ไปเรื่อยๆ

เดิมด่านนี้เรียก stock_service ซึ่งวิ่งไปหา SAP client อีกตัวที่ยังเป็น mock อยู่ จึงปล่อย
ผ่านทุกครั้งโดยไม่ได้ถามใครจริง — มีด่านแต่ไม่กันอะไรเลย เทสนี้ยัดคำตอบ "ของไม่พอ" ใส่
client ตัวที่ด่านใช้ ถ้าใบยังออกได้แปลว่าด่านไม่ได้ฟังคำตอบนั้น
"""
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.integrations.sap.availability import AvailLine
from app.integrations.sap.base import SapError
from app.models.cart import CartItem
from app.seed import seed_catalog
from app.services import availability_service
from tests.helpers import auth_headers, ensure_seed

REQ = date(2026, 9, 16)


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


class _Stub:
    """ตอบตามที่สั่ง และนับจำนวนครั้งที่ถูกยิง (ด่านต้องยิงครั้งเดียวทั้งใบ)"""

    def __init__(self, reply):
        self.reply = reply
        self.calls: list[list[tuple[str, int]]] = []
        self.customers: list[str] = []

    def check(self, asks, customer_no, req_date):
        self.calls.append([(a.matnr, a.qty) for a in asks])
        self.customers.append(customer_no)
        if isinstance(self.reply, Exception):
            raise self.reply
        return [self.reply(a) for a in asks]


def _use(monkeypatch, stub):
    monkeypatch.setattr(availability_service, "get_availability_client", lambda: stub)
    return stub


def _line(qty, ready, later=0, later_date=None):
    return AvailLine(
        matnr="x", qty=qty, description=None, sales_unit="KIT", unit_price=0, amount=0,
        available_qty=ready, available_date=REQ if ready else None,
        committed_qty=later, committed_date=later_date,
    )


def _preso(client, hs):
    """ตะกร้าพร้อมออกใบ — ด่านอื่นผ่านครบแล้ว เหลือด่านสต็อกให้เทสตัวนี้"""
    from tests.test_step8_quotation import _ready_cart

    cart, _ = _ready_cart(client, hs)
    return client.post("/presos", json={"cart_id": cart["id"]}, headers=hs).json(), cart


def test_ของไม่พอต้องออกใบไม่ได้(client, monkeypatch):
    p, _ = _preso(client, auth_headers(client, "SA-104", "staff"))
    hs = auth_headers(client, "SA-104", "staff")
    stub = _use(monkeypatch, _Stub(lambda a: _line(a.qty, 0)))  # ไม่มีของเลยทุกบรรทัด
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["shortages"] and all(s["available"] == 0 for s in d["shortages"])
    assert {s["status"] for s in d["shortages"]} == {"none"}
    # ยิงครั้งเดียวทั้งใบ — วนยิงทีละบรรทัดจะเห็นของชิ้นเดียวซ้ำทุกบรรทัดแล้วขายเกิน
    assert len(stub.calls) == 1 and len(stub.calls[0]) == 2


def test_ของครบออกใบได้_และไม่ขึ้นคำเตือน(client, monkeypatch):
    hs = auth_headers(client, "SA-104", "staff")
    p, _ = _preso(client, hs)
    _use(monkeypatch, _Stub(lambda a: _line(a.qty, a.qty)))
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 201, r.text
    assert r.json()["stock_warnings"] is None


def test_แบ่งส่งไม่ใช่ของขาด_และจดวันของครบไว้(client, monkeypatch):
    """ready 0 + committed ครบ = ได้ของครบแต่ต้องรอ → ออกใบได้ และ atp_date ต้องเป็นวันรอบหลัง"""
    hs = auth_headers(client, "SA-104", "staff")
    p, cart = _preso(client, hs)
    later = date(2026, 10, 7)
    _use(monkeypatch, _Stub(lambda a: _line(a.qty, 0, later=a.qty, later_date=later)))
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        ship = [i for i in db.query(CartItem).filter_by(cart_id=cart["id"]).all() if i.supply_mode in ("ship", "install")]
        assert ship and all(i.atp_date == later for i in ship)


def test_SAP_ล่มต้องไม่นับว่าของพอ(client, monkeypatch):
    """ไม่รู้ ≠ พอ · ติด 409 บอกเหตุผลจริง แต่ force ได้ ไม่ใช่ปิดร้านทั้งวันตอน SAP ล่ม"""
    hs = auth_headers(client, "SA-104", "staff")
    p, _ = _preso(client, hs)
    _use(monkeypatch, _Stub(SapError("gateway timeout")))
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert "ไม่สำเร็จ" in d["message"] and d["shortages"][0]["sap_error"] == "gateway timeout"
    r2 = client.post(f"/presos/{p['preso_no']}/quotation", json={"force": True}, headers=hs)
    assert r2.status_code == 201, r2.text
    assert r2.json()["stock_warnings"][0]["sap_error"] == "gateway timeout"


def test_force_ออกใบได้_แต่คำเตือนต้องติดอยู่ในใบ(client, monkeypatch):
    hs = auth_headers(client, "SA-104", "staff")
    p, _ = _preso(client, hs)
    _use(monkeypatch, _Stub(lambda a: _line(a.qty, 0)))
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={"force": True}, headers=hs)
    assert r.status_code == 201, r.text
    w = r.json()["stock_warnings"]
    assert w and len(w) == 2 and all(x["need"] > x["available"] for x in w)


def test_ถามด้วยเลขลูกค้าเดียวกับปุ่มเช็คสต็อกของเซลล์(client, monkeypatch):
    """สองทางถามด้วยเลขต่างกัน = ATP ไม่เท่ากัน เซลล์เห็นของครบแต่กดออกใบไม่ได้"""
    hs = auth_headers(client, "SA-104", "staff")
    p, cart = _preso(client, hs)
    stub = _use(monkeypatch, _Stub(lambda a: _line(a.qty, a.qty)))
    client.post(f"/sales/carts/{cart['id']}/availability", headers=hs)
    from_button = stub.customers[-1]
    client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert stub.customers[-1] == from_button
