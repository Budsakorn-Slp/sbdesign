import json

import pytest

from app.db.session import SessionLocal
from app.integrations.sap import get_sap_client
from app.seed import seed_catalog
from app.services import payment_service
from tests.helpers import auth_headers, ensure_seed, login


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _quotation(client, hs):
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": "10023841", "qty": 1, "supply_mode": "ship"}, headers=hs)
    client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "4400310"}, headers=hs)
    q = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10310"}, headers=hs).json()
    slot = next(s for s in q["slots"] if s["remaining"] > 0)
    client.post(f"/delivery/slots/{slot['id']}/hold", json={"cart_id": cart["id"]}, headers=hs)
    p = client.post("/presos", json={"cart_id": cart["id"]}, headers=hs).json()
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={"force": True}, headers=hs)
    assert r.status_code == 201, r.text
    return r.json()


def _webhook(client, payment_no, event="payment.succeeded", reason=None):
    body = json.dumps({"event": event, "payment_no": payment_no, "reason": reason}).encode()
    return client.post("/webhooks/payment", content=body, headers={"X-Signature": payment_service.sign(body), "Content-Type": "application/json"})


def test_pay_full_then_sap_so_created(client):
    hs = auth_headers(client, "SA-104", "staff")
    q = _quotation(client, hs)
    r = client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "qr_promptpay", "kind": "full"}, headers=hs)
    assert r.status_code == 201, r.text
    pay = r.json()
    assert pay["payment_no"].startswith("PAY-") and pay["status"] == "pending" and pay["qr_payload"]
    assert pay["amount"] == q["grand_total"]
    # กดซ้ำได้ intent เดิม ไม่สร้างใบใหม่
    assert client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "qr_promptpay", "kind": "full"}, headers=hs).json()["payment_no"] == pay["payment_no"]

    # ลูกค้าจ่ายผ่านลิงก์โดยไม่ต้องล็อกอิน (ใช้ token)
    client.cookies.clear()
    got = client.get(f"/payments/{pay['payment_no']}", params={"t": q["link_token"]})
    assert got.status_code == 200 and got.json()["status"] == "pending"
    assert client.get(f"/payments/{pay['payment_no']}").status_code == 401

    assert _webhook(client, pay["payment_no"]).json()["sap_so_no"]
    done = client.get(f"/payments/{pay['payment_no']}", params={"t": q["link_token"]}).json()
    assert done["status"] == "paid" and done["quotation_status"] == "converted" and done["sap_sync_status"] == "ok"
    view = client.get(f"/quotations/{q['quotation_no']}", params={"t": q["link_token"]}).json()
    assert view["sap_so_no"] == done["sap_so_no"] and view["status"] == "converted" and view["paid_at"]
    # provider ยิงซ้ำ → idempotent ไม่สร้าง SO ใหม่
    dup = _webhook(client, pay["payment_no"]).json()
    assert dup["duplicate"] and dup["sap_so_no"] == done["sap_so_no"]


def test_deposit_20_percent_and_no_cash_channel(client):
    hs = auth_headers(client, "SA-104", "staff")
    q = _quotation(client, hs)
    assert client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "cash", "kind": "full"}, headers=hs).status_code == 400
    pay = client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "link", "kind": "deposit"}, headers=hs).json()
    assert float(pay["amount"]) == float(q["deposit_amount"]) == round(float(q["grand_total"]) * 0.2)
    _webhook(client, pay["payment_no"])
    view = client.get(f"/quotations/{q['quotation_no']}", headers=hs).json()
    assert view["status"] == "converted" and view["sap_so_no"]
    # ใบที่จ่ายแล้วเปิด intent ใหม่ไม่ได้
    assert client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "card", "kind": "full"}, headers=hs).status_code == 400
    # webhook ที่ลายเซ็นผิด = 401
    body = json.dumps({"event": "payment.succeeded", "payment_no": pay["payment_no"]}).encode()
    assert client.post("/webhooks/payment", content=body, headers={"X-Signature": "deadbeef"}).status_code == 401


def test_sap_down_queues_retry_and_manager_can_resync(client):
    hs = auth_headers(client, "SA-104", "staff")
    q = _quotation(client, hs)
    pay = client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "card", "kind": "full"}, headers=hs).json()
    get_sap_client().fail_next(1)  # SAP ล่มตอน create_sales_order
    res = _webhook(client, pay["payment_no"]).json()
    assert res["status"] == "paid" and res["sap_so_no"] is None and res["sap_sync_status"] == "failed"
    assert client.get(f"/quotations/{q['quotation_no']}", headers=hs).json()["status"] == "paid"  # เงินรับแล้ว ไม่หาย

    mg = auth_headers(client, "MG-001", "staff")
    assert client.get("/admin/sap-sync", params={"status": "pending"}, headers=hs).status_code == 403  # เซลล์ดูไม่ได้
    jobs = client.get("/admin/sap-sync", params={"status": "pending"}, headers=mg).json()
    job = next(j for j in jobs if j["quotation_no"] == q["quotation_no"])
    assert job["attempts"] == 1 and job["last_error"]

    r = client.post(f"/admin/sap-sync/{q['quotation_no']}/retry", headers=mg).json()
    assert r["status"] == "ok" and r["sap_so_no"] and r["attempts"] == 2
    assert client.get(f"/quotations/{q['quotation_no']}", headers=hs).json()["status"] == "converted"


def test_customer_online_checkout_then_pay(client):
    hs = {"Authorization": "Bearer " + login(client, "4400182")["access_token"]}
    client.post("/cart/items", json={"matnr": "10031002", "qty": 1, "supply_mode": "ship"}, headers=hs)
    cart = client.get("/cart", headers=hs).json()
    q = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=hs).json()
    client.post(f"/delivery/slots/{q['slots'][0]['id']}/hold", json={"cart_id": cart["id"]}, headers=hs)
    r = client.post("/checkout/quotation", json={"force": True}, headers=hs)
    assert r.status_code == 201, r.text
    quote = r.json()
    assert quote["channel"] == "online" and quote["sales_name"] is None and quote["link_token"] is None
    pay = client.post(f"/quotations/{quote['quotation_no']}/payment-intent", json={"method": "qr_promptpay", "kind": "deposit"}, headers=hs).json()
    assert _webhook(client, pay["payment_no"]).json()["sap_so_no"]
    assert client.get(f"/quotations/{quote['quotation_no']}", headers=hs).json()["status"] == "converted"


def test_failed_payment_keeps_quotation_issued(client):
    hs = auth_headers(client, "SA-104", "staff")
    q = _quotation(client, hs)
    pay = client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "installment", "kind": "full"}, headers=hs).json()
    assert _webhook(client, pay["payment_no"], event="payment.failed", reason="บัตรถูกปฏิเสธ").json()["status"] == "failed"
    assert client.get(f"/quotations/{q['quotation_no']}", headers=hs).json()["status"] == "issued"
    # เปิดใบใหม่แล้วจ่ายผ่าน mock-confirm (โหมด dev) ได้
    again = client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "qr_promptpay", "kind": "full"}, headers=hs).json()
    assert again["payment_no"] != pay["payment_no"]
    ok = client.post(f"/payments/{again['payment_no']}/mock-confirm", headers=hs).json()
    assert ok["status"] == "paid" and ok["sap_so_no"]
