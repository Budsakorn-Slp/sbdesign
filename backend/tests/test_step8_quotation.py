from datetime import date, timedelta

import pytest

from app.db.session import SessionLocal
from app.integrations.sap import get_sap_client
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed, login


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _ready_cart(client, hs, customer_key="4400310", items=(("10023841", 1, "ship", None), ("10031002", 2, "takeaway", "BKN"))):
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    for matnr, qty, mode, plant in items:
        client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": matnr, "qty": qty, "supply_mode": mode, "plant_code": plant}, headers=hs)
    r = client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": customer_key}, headers=hs)
    assert r.status_code == 200, r.text
    q = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10310", "address": "999 อาคารทรัพย์ทวี ถ.พระราม 9"}, headers=hs).json()
    slot = next(s for s in q["slots"] if s["remaining"] > 0)
    client.post(f"/delivery/slots/{slot['id']}/hold", json={"cart_id": cart["id"]}, headers=hs)
    client.post(f"/cart/{cart['id']}/discounts", json={"kind": "promotion", "promo_code": "SEP-SOFA15"}, headers=hs)
    return client.get(f"/sales/carts/{cart['id']}", headers=hs).json(), slot


def test_save_preso_then_reopen_in_new_session(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart, _ = _ready_cart(client, hs)
    r = client.post("/presos", json={"cart_id": cart["id"], "note": "รอลูกค้าวัดห้อง"}, headers=hs)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["preso_no"].startswith("PRE-") and p["status"] == "draft" and p["item_count"] == 3
    assert p["snapshot"]["totals"]["grand_total"] == cart["totals"]["grand_total"]
    # save ซ้ำ = อัปเดตใบเดิม
    p2 = client.post("/presos", json={"cart_id": cart["id"]}, headers=hs).json()
    assert p2["preso_no"] == p["preso_no"] and p2["note"] == "รอลูกค้าวัดห้อง"
    # "ปิดเบราว์เซอร์": ปิดเซสชันตะกร้า แล้วล็อกอินใหม่
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)
    hs2 = {"Authorization": "Bearer " + login(client, "SA-104", account_type="staff")["access_token"]}
    mine = client.get("/presos", params={"status": "draft", "mine": "true"}, headers=hs2).json()
    assert any(x["preso_no"] == p["preso_no"] for x in mine)
    assert client.get(f"/presos/{p['preso_no']}", headers=hs2).json()["snapshot"]["items"][0]["matnr"] == "10023841"
    # ดึงกลับมาทำต่อ → ตะกร้ากลับเข้าเซสชัน
    back = client.post(f"/presos/{p['preso_no']}/reopen", headers=hs2)
    assert back.status_code == 200 and back.json()["id"] == cart["id"]
    assert any(c["id"] == cart["id"] for c in client.get("/sales/carts", headers=hs2).json())
    # เซลล์อื่นดู/เปิด Preso ของเราไม่ได้
    assert client.get(f"/presos/{p['preso_no']}", headers=auth_headers(client, "SA-105", "staff")).status_code == 403


def test_create_quotation_locks_totals_and_is_immutable(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart, slot = _ready_cart(client, hs)
    p = client.post("/presos", json={"cart_id": cart["id"]}, headers=hs).json()
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["quotation_no"].startswith("QT-") and q["status"] == "issued" and q["channel"] == "in_store_assisted"
    assert q["grand_total"] == cart["totals"]["grand_total"] and q["discount_total"] == cart["totals"]["discount_total"]
    assert len(q["lines"]) == 2 and any(d["code"] == "SEP-SOFA15" for d in q["discounts"])
    assert q["valid_until"] == (date.today() + timedelta(days=7)).isoformat()
    assert q["slot_date"] == slot["date"] and q["slot_period"] == slot["period"] and q["sales_code"] == "SA-104"
    assert float(q["deposit_amount"]) == round(float(q["grand_total"]) * 0.2)
    assert q["link_token"]  # พนักงานได้ token ไว้ส่งลิงก์
    # ตะกร้า converted → หลุดจากแท็บเซลล์ · Preso quoted
    assert all(c["id"] != cart["id"] for c in client.get("/sales/carts", headers=hs).json())
    assert client.get(f"/presos/{p['preso_no']}", headers=hs).json()["status"] == "quoted"
    assert client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs).status_code == 400
    # เอกสาร (mock PDF) เปิดได้
    doc = client.get(q["pdf_url"], headers=hs)
    assert doc.status_code == 200 and q["quotation_no"] in doc.text
    # ส่งลิงก์ (mock) → ลูกค้าเปิดด้วย token โดยไม่ล็อกอิน · token ผิด 403 · ไม่มี token 401
    sent = client.post(f"/quotations/{q['quotation_no']}/send", json={"channel": "sms"}, headers=hs).json()
    assert sent["sent"] and sent["link"].endswith(q["link_token"])
    client.cookies.clear()
    assert client.get(f"/quotations/{q['quotation_no']}", params={"t": q["link_token"]}).status_code == 200
    assert client.get(f"/quotations/{q['quotation_no']}", params={"t": "bad"}).status_code == 403
    assert client.get(f"/quotations/{q['quotation_no']}").status_code == 401
    # issued แล้วห้ามแก้ → cancel แล้วออกใหม่ได้เลขใหม่
    c = client.post(f"/quotations/{q['quotation_no']}/cancel", json={"reason": "ลูกค้าขอเปลี่ยนรุ่น"}, headers=hs).json()
    assert c["status"] == "cancelled"
    assert any(x["id"] == cart["id"] for x in client.get("/sales/carts", headers=hs).json())  # ตะกร้ากลับมาแก้ได้
    q2 = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs).json()
    assert q2["quotation_no"] != q["quotation_no"] and q2["status"] == "issued"
    assert client.get(f"/quotations/{q['quotation_no']}", headers=hs).json()["status"] == "cancelled"


def test_quotation_blocked_when_stock_short_unless_forced(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart, _ = _ready_cart(client, hs, items=(("10081001", 5, "install", None),))  # เคาน์เตอร์ครัว: คลังมี 3
    p = client.post("/presos", json={"cart_id": cart["id"]}, headers=hs).json()
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["shortages"][0]["matnr"] == "10081001" and detail["shortages"][0]["need"] == 5 and detail["shortages"][0]["available"] == 3
    forced = client.post(f"/presos/{p['preso_no']}/quotation", json={"force": True}, headers=hs)
    assert forced.status_code == 201 and forced.json()["stock_warnings"][0]["matnr"] == "10081001"


def test_quotation_requires_customer_and_delivery(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10052277", "qty": 1}, headers=hs)
    p = client.post("/presos", json={"cart_id": cart["id"]}, headers=hs).json()
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 400 and "ผูกลูกค้า" in r.json()["detail"]
    client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "4400310"}, headers=hs)
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 400 and "ค่าขนส่ง" in r.json()["detail"]
    # SAP ล่มตอนเช็คสต็อก → fallback cache ยังออกได้ (stale flag ใน shortages ถ้ามี)
    client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=hs)
    get_sap_client().fail_next(2)
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 201
