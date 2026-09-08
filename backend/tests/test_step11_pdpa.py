"""STEP 11 — consent การตลาด + สิทธิ์ขอสำเนา/ขอลบข้อมูล (PDPA)"""
import uuid

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.analytics import UserEvent
from app.models.user import User
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed

CUSTOMER = "4400205"
MATNR = "10023841"


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _register(client) -> tuple[dict, str]:
    """สมัครลูกค้าใหม่สำหรับเทสต์ลบข้อมูล (จะได้ไม่กระทบ user ที่ test อื่นใช้)"""
    phone = "09" + uuid.uuid4().hex[:8]
    r = client.post("/auth/register", json={"phone": phone, "password": "1234", "name": "ทดสอบ PDPA"})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}, phone


def _events_of(user_id: str) -> list[UserEvent]:
    with SessionLocal() as db:
        return list(db.scalars(select(UserEvent).where(UserEvent.user_id == user_id)).all())


def test_marketing_consent_toggle_and_history(client):
    h = auth_headers(client, CUSTOMER)
    before = client.get("/me/privacy", headers=h).json()
    assert before["consent_marketing"] is False  # ค่าเริ่มต้นต้องเป็น "ไม่ยินยอม"

    on = client.post("/me/consents", json={"marketing": True}, headers=h)
    assert on.status_code == 200 and on.json()["consent_marketing"] is True

    off = client.post("/me/consents", json={"marketing": False}, headers=h).json()
    assert off["consent_marketing"] is False
    # เก็บประวัติทุกครั้ง ไม่ทับของเดิม
    assert [c["granted"] for c in off["history"]][:2] == [False, True]


def test_marketing_events_need_consent(client):
    h = auth_headers(client, CUSTOMER)
    uid = client.get("/me", headers=h).json()["id"]
    client.get("/materials/10023841", headers=h)  # event เพื่อการใช้งาน (service) — ไม่ต้องขอความยินยอม

    # ไม่ยินยอม → เก็บเป็นสถิติได้ แต่ต้องไม่ผูกกับตัวบุคคล
    client.post("/me/consents", json={"marketing": False}, headers=h)
    client.post("/events", json={"event": "view_material", "matnr": "10023841", "purpose": "marketing"}, headers=h)
    assert not [e for e in _events_of(uid) if e.purpose == "marketing"]

    # ยินยอมแล้ว → ผูกกับบัญชีได้
    client.post("/me/consents", json={"marketing": True}, headers=h)
    client.post("/events", json={"event": "view_material", "matnr": "10023841", "purpose": "marketing"}, headers=h)
    assert [e for e in _events_of(uid) if e.purpose == "marketing"]

    # ถอนความยินยอม → ของเก่าต้องถูกลบตัวตนย้อนหลังทันที
    client.post("/me/consents", json={"marketing": False}, headers=h)
    assert not [e for e in _events_of(uid) if e.purpose == "marketing"]
    # ส่วน event ที่จำเป็นต่อการใช้งาน (service) ไม่ถูกแตะ
    assert [e for e in _events_of(uid) if e.purpose == "service"]


def test_export_returns_my_data(client):
    h = auth_headers(client, CUSTOMER)
    if not client.post("/me/wishlist/10023841", headers=h).json()["in_wishlist"]:
        client.post("/me/wishlist/10023841", headers=h)  # toggle — test อื่นอาจใส่ไว้ก่อนแล้ว
    data = client.get("/me/data/export", headers=h).json()
    assert data["profile"]["sap_customer_no"] == CUSTOMER
    assert "10023841" in data["wishlist"]
    assert {"consents", "recently_viewed", "searches", "events", "orders", "quotations"} <= set(data)


def test_delete_request_anonymizes_everything(client):
    h, phone = _register(client)
    uid = client.get("/me", headers=h).json()["id"]

    client.get("/materials/10023841", headers=h)  # สร้างรอยเท้าไว้ก่อน
    client.post("/cart/items", json={"matnr": "10023841", "qty": 1}, headers=h)
    client.post("/me/wishlist/10023841", headers=h)
    assert _events_of(uid)

    assert client.post("/me/data/delete", json={}, headers=h).status_code == 400  # ต้องยืนยันก่อน
    done = client.post("/me/data/delete", json={"confirm": True, "note": "ลูกค้าขอลบ"}, headers=h)
    assert done.status_code == 200, done.text

    # events ต้องระบุตัวบุคคลไม่ได้อีก + โปรไฟล์ถูกล้าง + เข้าระบบด้วยของเดิมไม่ได้
    assert not _events_of(uid)
    with SessionLocal() as db:
        u = db.get(User, uid)
        assert u.phone is None and u.email is None and u.password_hash is None and u.anonymized_at is not None
        assert not db.scalars(select(UserEvent).where(UserEvent.anon_token.is_not(None), UserEvent.user_id == uid)).all()
    assert client.post("/auth/login", json={"identifier": phone, "password": "1234"}).status_code == 401
    assert client.get("/me", headers=h).status_code == 401  # session ถูกเพิกถอนแล้ว


def test_admin_sees_audit_and_data_requests(client):
    admin = auth_headers(client, "ADM-001", "staff")
    reqs = client.get("/admin/data-requests", headers=admin)
    assert reqs.status_code == 200 and any(r["kind"] == "delete" for r in reqs.json())

    logs = client.get("/admin/audit-logs?action=pdpa", headers=admin)
    assert logs.status_code == 200 and {l["action"] for l in logs.json()} & {"pdpa.consent", "pdpa.anonymize", "pdpa.export"}
