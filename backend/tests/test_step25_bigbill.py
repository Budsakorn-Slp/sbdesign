"""บิลรวม (Big Bill): ใบของพนักงานหลายคน ลูกค้าคนเดียว จ่ายครั้งเดียว"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.payment import Payment
from app.models.promo import AppliedDiscount
from app.models.quotation import Quotation
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed

CUST = "1100440310"


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _issue(client, hs):
    from tests.test_step8_quotation import _ready_cart

    cart, _ = _ready_cart(client, hs, customer_key=CUST)
    p = client.post("/presos", json={"cart_id": cart["id"]}, headers=hs).json()
    r = client.post(f"/presos/{p['preso_no']}/quotation", json={"force": True}, headers=hs)
    assert r.status_code == 201, r.text
    return r.json()


def test_รวมใบของพนักงานสองคน_ใช้โค้ด_จ่ายครั้งเดียว(client):
    a = auth_headers(client, "SA-104", "staff")
    b = auth_headers(client, "SA-105", "staff")
    q1, q2 = _issue(client, a), _issue(client, b)

    c = client.get("/sales/bigbill/candidates", params={"quotation_no": q1["quotation_no"]}, headers=a).json()
    rows = {r["quotation_no"]: r for r in c["quotations"]}
    assert rows[q1["quotation_no"]]["mine"] and not rows[q2["quotation_no"]]["mine"], "เห็นใบของพนักงานคนอื่นด้วย (ทาง ก)"

    total = Decimal(q1["grand_total"]) + Decimal(q2["grand_total"])
    promos = {p["code"]: p for p in client.get("/sales/bigbill/promos", params={"amount": str(total)}, headers=a).json()}
    assert promos["MC0626500B"]["eligible"]
    assert not promos["BB100K12000"]["eligible"] or total >= 100000

    r = client.post("/sales/bigbills", json={"quotation_nos": [q1["quotation_no"], q2["quotation_no"]], "promo_code": "MC0626500B"}, headers=a)
    assert r.status_code == 201, r.text
    bill = r.json()
    assert Decimal(bill["subtotal"]) == total and Decimal(bill["discount"]) == 500
    assert sum(Decimal(i["discount_share"]) for i in bill["items"]) == 500, "ส่วนลดกระจายครบพอดี"

    pay = client.post(f"/sales/bigbills/{bill['bill_no']}/pay", json={"method": "qr_promptpay"}, headers=a).json()
    assert pay["big_bill_no"] == bill["bill_no"] and Decimal(pay["amount"]) == total - 500
    # พนักงานคนที่สอง (ไม่ได้สร้างบิล) ก็เปิดดูรายการชำระได้
    assert client.get(f"/payments/{pay['payment_no']}", headers=b).status_code == 200
    # ใบในบิลไม่โผล่เป็น "มีรายการชำระรอ" รายใบ
    r = client.post(f"/payments/{pay['payment_no']}/mock-confirm", params={"outcome": "paid"}, headers=a)
    assert r.status_code == 200, r.text

    done = client.get(f"/sales/bigbills/{bill['bill_no']}", headers=a).json()
    assert done["status"] == "paid" and all(i["status"] in ("paid", "converted") for i in done["items"])
    assert all(i["sap_so_no"] for i in done["items"]), "แต่ละใบเป็น SO แยกใน SAP"
    # หลังจ่ายแล้วหาบิลเจอ: ในรายการบิลรวม (ทั้งคนสร้างและเจ้าของใบอีกคน) และป้ายบนแถว Preso
    for hs in (a, b):
        rows = client.get("/sales/bigbills", headers=hs).json()
        assert any(r["bill_no"] == bill["bill_no"] and r["status"] == "paid" and r["count"] == 2 for r in rows)
    row = next(p for p in client.get("/presos?mine=true", headers=b).json() if p["quotation_no"] == q2["quotation_no"])
    assert row["big_bill_no"] == bill["bill_no"] and row["big_bill_status"] == "paid"
    with SessionLocal() as db:
        for it in done["items"]:
            q = db.scalar(select(Quotation).where(Quotation.quotation_no == it["quotation_no"]))
            d = db.scalars(select(AppliedDiscount).where(AppliedDiscount.quotation_id == q.id, AppliedDiscount.title.like("ส่วนลดบิลรวม%"))).all()
            assert sum((Decimal(x.amount) for x in d), Decimal(0)) == Decimal(it["discount_share"])
        qs = db.scalars(select(Quotation).where(Quotation.quotation_no.in_([q1["quotation_no"], q2["quotation_no"]]))).all()
        assert sum((Decimal(q.grand_total) for q in qs), Decimal(0)) == total - 500, "ยอดใบรวมกันเท่าที่ลูกค้าจ่ายจริง"


def test_โค้ดยอดไม่ถึงใช้ไม่ได้_และลูกค้าต่างคนรวมไม่ได้(client):
    a = auth_headers(client, "SA-104", "staff")
    q1 = _issue(client, a)
    r = client.post("/sales/bigbills", json={"quotation_nos": [q1["quotation_no"]], "promo_code": "BB100K12000"}, headers=a)
    if Decimal(q1["grand_total"]) < 100000:
        assert r.status_code == 400 and "ขาดอีก" in r.text
    from tests.test_step8_quotation import _ready_cart

    cart, _ = _ready_cart(client, a, customer_key="1100440182")
    p = client.post("/presos", json={"cart_id": cart["id"]}, headers=a).json()
    other = client.post(f"/presos/{p['preso_no']}/quotation", json={"force": True}, headers=a).json()
    r = client.post("/sales/bigbills", json={"quotation_nos": [q1["quotation_no"], other["quotation_no"]]}, headers=a)
    assert r.status_code == 400 and "ลูกค้าคนเดียวกัน" in r.text


def test_รายการชำระบิลหมดเวลา_ไม่ยกเลิกใบ(client):
    from datetime import timedelta

    from app.models.common import utcnow

    a = auth_headers(client, "SA-104", "staff")
    q1 = _issue(client, a)
    bill = client.post("/sales/bigbills", json={"quotation_nos": [q1["quotation_no"]]}, headers=a).json()
    pay = client.post(f"/sales/bigbills/{bill['bill_no']}/pay", json={"method": "card"}, headers=a).json()
    with SessionLocal() as db:
        p = db.scalar(select(Payment).where(Payment.payment_no == pay["payment_no"]))
        p.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.get(f"/payments/{pay['payment_no']}", headers=a).json()["status"] == "expired"
    assert client.get(f"/quotations/{q1['quotation_no']}", headers=a).json()["status"] == "issued", "ใบยังอยู่ จ่ายใหม่ได้"


def test_ยกเลิกที่หน้าธนาคาร_หน้าบิลบอกผล_จ่ายใหม่ในบิลเดิมได้_และยกเลิกบิลได้(client):
    a = auth_headers(client, "SA-104", "staff")
    q1 = _issue(client, a)
    bill = client.post("/sales/bigbills", json={"quotation_nos": [q1["quotation_no"]]}, headers=a).json()
    p1 = client.post(f"/sales/bigbills/{bill['bill_no']}/pay", json={"method": "qr_promptpay"}, headers=a).json()
    client.post(f"/payments/{p1['payment_no']}/mock-confirm", params={"outcome": "cancelled"}, headers=a)
    v = client.get(f"/sales/bigbills/{bill['bill_no']}", headers=a).json()
    assert v["status"] == "open" and v["pending_payment"] is None
    assert v["attempts"][0]["status"] == "cancelled", "บอกว่ารอบล่าสุดถูกยกเลิก"

    # ใบยังรอชำระ และในแท็บ Preso ขึ้นป้ายว่าอยู่ในบิลรวม
    presos = client.get("/presos?mine=true", headers=a).json()
    row = next(p for p in presos if p["quotation_no"] == q1["quotation_no"])
    assert row["big_bill_no"] == bill["bill_no"]

    # จ่ายใหม่ในบิลเดิม — ไม่ต้องสร้างบิลใหม่ · ธนาคารปฏิเสธ → บอกเหตุผล
    p2 = client.post(f"/sales/bigbills/{bill['bill_no']}/pay", json={"method": "card"}, headers=a).json()
    client.post(f"/payments/{p2['payment_no']}/mock-confirm", params={"outcome": "failed"}, headers=a)
    v = client.get(f"/sales/bigbills/{bill['bill_no']}", headers=a).json()
    assert [x["status"] for x in v["attempts"]] == ["failed", "cancelled"] and v["attempts"][0]["failed_reason"]

    # ยกเลิกบิล → ใบกลับเป็นรอชำระปกติ ป้ายหาย
    v = client.post(f"/sales/bigbills/{bill['bill_no']}/cancel", headers=a).json()
    assert v["status"] == "cancelled"
    row = next(p for p in client.get("/presos?mine=true", headers=a).json() if p["quotation_no"] == q1["quotation_no"])
    assert row["big_bill_no"] is None and row["quotation_status"] == "issued"


# ---------- กันจ่ายซ้ำ ----------
def _confirm(client, hs, payment_no, outcome="paid"):
    r = client.post(f"/payments/{payment_no}/mock-confirm", params={"outcome": outcome}, headers=hs)
    assert r.status_code == 200, r.text
    return r.json()


def test_ข้อ1_บิลเปิดชำระค้าง_ใบในบิลเปิดชำระเดี่ยวไม่ได้_และ_QR_เดี่ยวที่ค้างถูกปิด(client):
    a = auth_headers(client, "SA-104", "staff")
    q1 = _issue(client, a)
    single = client.post(f"/quotations/{q1['quotation_no']}/payment-intent", json={"method": "qr_promptpay", "kind": "full"}, headers=a).json()
    bill = client.post("/sales/bigbills", json={"quotation_nos": [q1["quotation_no"]]}, headers=a).json()
    client.post(f"/sales/bigbills/{bill['bill_no']}/pay", json={"method": "qr_promptpay"}, headers=a)
    assert client.get(f"/payments/{single['payment_no']}", headers=a).json()["status"] == "cancelled", "QR เดี่ยวที่ค้างต้องถูกปิด"
    r = client.post(f"/quotations/{q1['quotation_no']}/payment-intent", json={"method": "card", "kind": "full"}, headers=a)
    assert r.status_code == 409 and bill["bill_no"] in r.text


def test_ข้อ2_จ่ายเดี่ยวสำเร็จ_บิลรวมที่มีใบนี้ถูกยกเลิก(client):
    a = auth_headers(client, "SA-104", "staff")
    q1, q2 = _issue(client, a), _issue(client, a)
    bill = client.post("/sales/bigbills", json={"quotation_nos": [q1["quotation_no"], q2["quotation_no"]]}, headers=a).json()
    single = client.post(f"/quotations/{q1['quotation_no']}/payment-intent", json={"method": "qr_promptpay", "kind": "full"}, headers=a).json()
    _confirm(client, a, single["payment_no"])
    assert client.get(f"/sales/bigbills/{bill['bill_no']}", headers=a).json()["status"] == "cancelled"
    assert client.get(f"/quotations/{q2['quotation_no']}", headers=a).json()["status"] == "issued", "ใบอื่นในบิลกลับไปรอชำระ"


def test_ข้อ3_4_เงินเข้าซ้ำหลังยกเลิกแล้ว_ไม่แตะใบ_ไม่สร้าง_SO_ซ้ำ_บันทึกรอคืน(client):
    from tests.helpers import auth_headers as ah

    a = auth_headers(client, "SA-104", "staff")
    q1, q2 = _issue(client, a), _issue(client, a)
    single = client.post(f"/quotations/{q1['quotation_no']}/payment-intent", json={"method": "qr_promptpay", "kind": "full"}, headers=a).json()
    bill = client.post("/sales/bigbills", json={"quotation_nos": [q1["quotation_no"], q2["quotation_no"]], "promo_code": "MC0626500B"}, headers=a).json()
    bp = client.post(f"/sales/bigbills/{bill['bill_no']}/pay", json={"method": "qr_promptpay"}, headers=a).json()
    _confirm(client, a, bp["payment_no"])
    so = client.get(f"/quotations/{q1['quotation_no']}", headers=a).json()["sap_so_no"]
    assert so

    # ธนาคารยังรับเงินจาก QR เดี่ยว (ที่เราปิดไปแล้ว) เข้ามา → รอคืน ใบไม่เปลี่ยน SO ไม่ซ้ำ
    r = _confirm(client, a, single["payment_no"])
    assert r["status"] == "refund_due"
    after = client.get(f"/quotations/{q1['quotation_no']}", headers=a).json()
    assert after["sap_so_no"] == so and after["status"] == "converted"

    mg = ah(client, "MG-001", "staff")
    rows = client.get("/admin/refunds", headers=mg).json()
    row = next(x for x in rows if x["payment_no"] == single["payment_no"])
    assert Decimal(row["refund_due"]) == Decimal(single["amount"]) and not row["refunded_at"]
    assert client.post(f"/admin/refunds/{single['payment_no']}/done", headers=mg).json()["refunded_at"]
    assert client.get("/admin/refunds", headers=a).status_code == 403, "พนักงานขายไม่เห็นหน้าคืนเงิน"


def test_บิลรวมจ่ายทีหลัง_ใบที่จ่ายไปแล้วถูกข้ามและยอดใบนั้นรอคืน(client):
    a = auth_headers(client, "SA-104", "staff")
    q1, q2 = _issue(client, a), _issue(client, a)
    bill = client.post("/sales/bigbills", json={"quotation_nos": [q1["quotation_no"], q2["quotation_no"]]}, headers=a).json()
    bp = client.post(f"/sales/bigbills/{bill['bill_no']}/pay", json={"method": "qr_promptpay"}, headers=a).json()
    # จำลองว่า q1 ถูกจ่ายทางอื่นไปก่อน (เช่นชำระที่แคชเชียร์ระบบเดิม) ระหว่างที่ QR บิลค้างอยู่
    with SessionLocal() as db:
        q = db.scalar(select(Quotation).where(Quotation.quotation_no == q1["quotation_no"]))
        q.status, q.sap_so_no = "converted", "2600000001"
        db.commit()
    _confirm(client, a, bp["payment_no"])
    assert client.get(f"/quotations/{q1['quotation_no']}", headers=a).json()["sap_so_no"] == "2600000001", "SO เดิมไม่ถูกทับ"
    assert client.get(f"/quotations/{q2['quotation_no']}", headers=a).json()["status"] in ("paid", "converted")
    with SessionLocal() as db:
        p = db.scalar(select(Payment).where(Payment.payment_no == bp["payment_no"]))
        assert p.status == "paid" and Decimal(p.refund_due) == Decimal(q1["grand_total"]) and q1["quotation_no"] in p.refund_note
