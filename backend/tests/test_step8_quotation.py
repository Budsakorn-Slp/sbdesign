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


def _ready_cart(client, hs, customer_key="1100440310", items=(("10023841", 1, "ship", None), ("10031002", 2, "takeaway", "BKN"))):
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    for matnr, qty, mode, plant in items:
        client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": matnr, "qty": qty, "supply_mode": mode, "plant_code": plant}, headers=hs)
    r = client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": customer_key}, headers=hs)
    assert r.status_code == 200, r.text
    q = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10310", "address": "999 อาคารทรัพย์ทวี ถ.พระราม 9"}, headers=hs).json()
    slot = next(s for s in q["slots"] if s["remaining"] > 0)
    client.post(f"/delivery/slots/{slot['id']}/hold", json={"cart_id": cart["id"]}, headers=hs)
    client.post(f"/cart/{cart['id']}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=hs)
    # กดเช็คโปรฯ 1 รอบ — ของบางชุดไม่เข้าเงื่อนไขโปรฯ ข้างบน การกดดูรายการโปรฯ คือสิ่งที่ผ่านด่านนี้
    client.post("/promotions/evaluate", json={"cart_id": cart["id"]}, headers=hs)
    # ด่านสุดท้ายก่อน Save PRE: เช็คสต็อกทั้งตะกร้า (ต้องทำหลังแก้ของครั้งสุดท้าย)
    client.post(f"/sales/carts/{cart['id']}/availability", headers=hs)
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
    assert len(q["lines"]) == 2 and any(d["code"] == "SAVE20" for d in q["discounts"])
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
    # ของไม่พอ → ร่าง PRE ยังบันทึกได้ (เซลล์เก็บงานไว้ก่อน) แต่ออกใบเสนอราคาไม่ได้
    saved = client.post("/presos", json={"cart_id": cart["id"]}, headers=hs)
    assert saved.status_code == 201, saved.text
    p = saved.json()
    # ออกใบเสนอราคาแล้วโดนตีกลับพร้อมบอกว่าขาดตัวไหนกี่ชิ้น
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["shortages"][0]["matnr"] == "10081001" and detail["shortages"][0]["need"] == 5 and detail["shortages"][0]["available"] == 3
    forced = client.post(f"/presos/{p['preso_no']}/quotation", json={"force": True}, headers=hs)
    assert forced.status_code == 201 and forced.json()["stock_warnings"][0]["matnr"] == "10081001"


def test_preso_blocked_until_every_step_done(client):
    """ผังงานหน้าร้าน: ลูกค้า → ข้อมูลลูกค้า → เช็คสต็อก → เช็คโปรฯ → คิวจัดส่ง

    Preso เป็น "ร่าง" บันทึกค้างไว้ได้ตลอดแม้ยังทำไม่ครบ (ลูกค้าเดินไปดูของต่อ
    พนักงานต้องเก็บงานที่ทำมาไว้ได้) ส่วนด่านทั้งห้าไปบังคับที่ตอนออกใบเสนอราคาแทน
    """
    hs = auth_headers(client, "SA-104", "staff")
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10052277", "qty": 1}, headers=hs)

    def save():
        return client.post("/presos", json={"cart_id": cart["id"]}, headers=hs)

    def steps():
        return {s["key"]: s["ok"] for s in client.get(f"/sales/carts/{cart['id']}", headers=hs).json()["preso"]["steps"]}

    # 1 ยังไม่ผูกลูกค้า — บันทึกร่างได้ แต่ด่านยังไม่ผ่าน
    assert save().status_code == 201
    assert steps() == {"customer": False, "profile": False, "stock": False, "promo": False, "delivery": False}
    client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "1100440310"}, headers=hs)
    assert steps()["customer"] is True

    # 2 ยังไม่มีที่อยู่จัดส่ง
    client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=hs)
    assert steps()["profile"] is True

    # 3 ยังไม่ได้เช็คสต็อก
    client.post(f"/sales/carts/{cart['id']}/availability", headers=hs)
    assert steps()["stock"] is True

    # 4 ยังไม่ได้เช็คโปรฯ — ไม่มีโปรฯ ให้ใช้ก็ยังต้องกดดู 1 รอบ
    client.post("/promotions/evaluate", json={"cart_id": cart["id"]}, headers=hs)
    assert steps()["promo"] is True

    # 5 ยังไม่ได้จองคิวส่ง — ตรงนี้ลองออกใบเสนอราคาดู ต้องโดนตีกลับเพราะยังไม่ครบ
    draft = save().json()
    blocked_q = client.post(f"/presos/{draft['preso_no']}/quotation", json={}, headers=hs)
    assert blocked_q.status_code == 400 and "ยังทำไม่ครบ" in blocked_q.json()["detail"]
    q = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=hs).json()
    slot = next(s for s in q["slots"] if s["remaining"] > 0)
    client.post(f"/delivery/slots/{slot['id']}/hold", json={"cart_id": cart["id"]}, headers=hs)

    ready = client.get(f"/sales/carts/{cart['id']}", headers=hs).json()["preso"]
    assert ready["ready"] is True and all(s["ok"] for s in ready["steps"])
    r = save()
    assert r.status_code == 201, r.text
    p = r.json()

    # แก้ตะกร้าหลังเช็ค → ผลเช็คสต็อก/โปรฯ หมดอายุ ต้องวนกลับไปเช็คใหม่ตามผังงาน
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10023841", "qty": 1}, headers=hs)
    after = steps()
    assert after["stock"] is False and after["promo"] is False and after["delivery"] is True
    assert save().status_code == 201          # ร่างยังบันทึกทับได้
    # แต่ออกใบเสนอราคาไม่ได้จนกว่าจะเช็คใหม่ครบ
    assert client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs).status_code == 400

    # เช็คใหม่ครบแล้วบันทึกทับใบเดิมได้
    client.post(f"/sales/carts/{cart['id']}/availability", headers=hs)
    client.post("/promotions/evaluate", json={"cart_id": cart["id"]}, headers=hs)
    again = save()
    assert again.status_code == 201 and again.json()["preso_no"] == p["preso_no"]

    # SAP ล่มตอนเช็คสต็อกของใบเสนอราคา → fallback cache ยังออกใบได้
    get_sap_client().fail_next(2)
    assert client.post(f"/presos/{p['preso_no']}/quotation", json={}, headers=hs).status_code == 201
