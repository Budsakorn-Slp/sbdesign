"""เส้นที่ K-Payment Gateway จะเรียกกลับมา — เปิดรับไว้แล้วแต่ยังไม่ตัดสถานะ

ยังไม่มีสเปกชื่อฟิลด์กับวิธีเซ็นข้อความ เดาเองไม่ได้เพราะผิดแล้วจะรู้ตอนเงินไม่เข้า
สิ่งที่ทำได้ตอนนี้คือบันทึก payload ดิบไว้ พอเริ่มทดสอบ sandbox จะเห็นชื่อฟิลด์จริงทันที
"""
import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.audit import AuditLog
from app.seed import seed_catalog
from tests.helpers import ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _last(action: str) -> AuditLog | None:
    with SessionLocal() as db:
        return db.scalars(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at.desc())).first()


@pytest.mark.parametrize("path,action", [
    ("/payment/card/notify", "kbank.card_notify"),
    ("/payment/qr/notify", "kbank.qr_notify"),
])
def test_notify_บันทึกของดิบไว้แล้วขอให้ส่งซ้ำ(client, path, action):
    body = {"transactionId": "T123", "amount": "1000.00", "status": "SUCCESS"}
    r = client.post(path, json=body, headers={"x-kbank-signature": "abc123"})
    # ตอบ 503 ไม่ใช่ 200 — gateway ส่วนใหญ่ยิงซ้ำเมื่อไม่ได้ 2xx
    # ตอบ 200 ทิ้งไปเฉยๆ รายการจ่ายจริงจะหายโดยไม่มีใครรู้
    assert r.status_code == 503
    row = _last(action)
    assert row and "transactionId" in row.payload["body"]
    assert row.payload["headers"].get("x-kbank-signature") == "abc123", "ต้องเก็บลายเซ็นไว้ดูด้วย"


def test_notify_ต้องไม่ตัดสถานะว่าจ่ายแล้ว(client):
    """จุดสำคัญ: ยิงอะไรเข้ามาก็ต้องไม่ทำให้ใบกลายเป็นจ่ายแล้ว จนกว่าจะยืนยันลายเซ็นได้"""
    from tests.test_step9_payment import _quotation
    from tests.helpers import auth_headers

    hs = auth_headers(client, "SA-104", "staff")
    q = _quotation(client, hs)
    pay = client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "card", "kind": "full"}, headers=hs).json()
    client.post("/payment/card/notify", json={"payment_no": pay["payment_no"], "status": "SUCCESS"})
    assert client.get(f"/payments/{pay['payment_no']}", headers=hs).json()["status"] == "pending"
    assert client.get(f"/quotations/{q['quotation_no']}", headers=hs).json()["status"] == "issued"


def test_callback_พาลูกค้าไปหน้าผล_ไม่โชว์_json(client):
    """ตรงนี้คือสายตาลูกค้า เจอ JSON ดิบแล้วนึกว่าเว็บพัง"""
    r = client.get("/payment/card/callback", params={"orderId": "QT-260101-0001"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/pay/QT-260101-0001/result"


def test_callback_ไม่รู้เลขอ้างอิง_ก็ยังพาไปที่ที่ใช้ได้(client):
    r = client.get("/payment/card/callback", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/account/pending"
    assert _last("kbank.card_callback") is not None


def test_หน้าเช็คสถานะความพร้อม(client):
    s = client.get("/payment/kbank/status").json()
    assert s["ready"] is False and s["blocked_by"]
    assert set(s["endpoints"]) == {"/payment/card/notify", "/payment/qr/notify", "/payment/card/callback"}


def test_ยังไม่ตั้ง_provider_เป็น_kbank_ก็เรียก_charge_ไม่ได้(client):
    from tests.helpers import auth_headers
    from tests.test_step9_payment import _quotation

    hs = auth_headers(client, "SA-104", "staff")
    q = _quotation(client, hs)
    pay = client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "card", "kind": "full"}, headers=hs).json()
    r = client.post(f"/payments/{pay['payment_no']}/kbank/charge", json={"token": "tok_x"}, headers=hs)
    assert r.status_code == 400


def test_ตั้ง_kbank_แต่ไม่มีคีย์_ต้องบอกว่าขาดอะไร(client, monkeypatch):
    from app.core.config import get_settings
    from tests.helpers import auth_headers
    from tests.test_step9_payment import _quotation

    hs = auth_headers(client, "SA-104", "staff")
    q = _quotation(client, hs)
    pay = client.post(f"/quotations/{q['quotation_no']}/payment-intent", json={"method": "card", "kind": "full"}, headers=hs).json()
    monkeypatch.setattr(get_settings(), "payment_provider", "kbank")
    r = client.post(f"/payments/{pay['payment_no']}/kbank/charge", json={"token": "tok_x"}, headers=hs)
    assert r.status_code == 503 and "KBANK_BASE_URL" in r.json()["detail"]


def test_public_config_ไม่ส่ง_secret_key_ออกไปหน้าเว็บ(client, monkeypatch):
    """คีย์ฝั่งเซิร์ฟเวอร์หลุดไปหน้าเว็บ = ใครก็สร้างรายการเก็บเงินในนามร้านเราได้"""
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "kbank_public_key", "pkey_ok")
    monkeypatch.setattr(s, "kbank_secret_key", "skey_ความลับ")
    cfg = client.get("/public-config").json()
    assert cfg["kbank_public_key"] == "pkey_ok"
    assert "skey_ความลับ" not in str(cfg)
    assert not any("secret" in k for k in cfg)
