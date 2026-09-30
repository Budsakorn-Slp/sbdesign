import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.cart import CartItemHistory
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed, login


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _count(model, **where) -> int:
    with SessionLocal() as db:
        stmt = select(func.count()).select_from(model)
        for k, v in where.items():
            stmt = stmt.where(getattr(model, k) == v)
        return int(db.scalar(stmt) or 0)


def test_guest_cart_then_login_keeps_items(client: TestClient):
    r = client.get("/cart")
    assert r.status_code == 200 and r.json()["is_guest"] is True and r.json()["count"] == 0
    assert "sb_anon" in client.cookies
    r = client.post("/cart/items", json={"matnr": "10023841", "qty": 1})
    assert r.status_code == 201
    r = client.post("/cart/items", json={"matnr": "10031002", "qty": 2, "plant_code": "BKN", "supply_mode": "takeaway"})
    body = r.json()
    assert body["count"] == 3 and body["subtotal"] == "32080.00"  # guest = ราคาปกติ 24,900 + 3,590×2
    guest_cart_id = body["id"]
    # guest ชำระเงินไม่ได้
    assert client.post("/cart/checkout-check").status_code == 401
    # ล็อกอิน (cookie เดิมติดไปกับ request) → ของย้ายเข้าตะกร้าลูกค้า · ราคาเท่าเดิม (ไม่มีระดับสมาชิก)
    tok = login(client, "094-916-4600")
    h = {"Authorization": "Bearer " + tok["access_token"]}
    mine = client.get("/cart", headers=h).json()
    assert mine["id"] != guest_cart_id and mine["is_guest"] is False and mine["customer"]["points"] == 1250
    assert mine["count"] == 3
    sofa = next(it for it in mine["items"] if it["matnr"] == "10023841")
    assert sofa["price_tier"] == "standard" and float(sofa["unit_price"]) == 24900
    lamp = next(it for it in mine["items"] if it["matnr"] == "10031002")
    assert lamp["supply_mode"] == "takeaway" and lamp["plant_code"] == "BKN" and lamp["atp_date"] is not None
    assert client.post("/cart/checkout-check", headers=h).json()["ok"] is True
    # ตะกร้า guest เดิมปิดเป็น merged → เข้าถึงไม่ได้อีก
    assert client.post(f"/carts/{guest_cart_id}/merge", json={"source_cart_id": guest_cart_id}, headers=h).status_code == 403


def test_update_and_remove_write_history_and_audit(client: TestClient):
    h = auth_headers(client, "081-222-3333")
    cart = client.post("/cart/items", json={"matnr": "10052277", "qty": 1}, headers=h).json()
    item = cart["items"][0]
    hist_before = _count(CartItemHistory, cart_id=cart["id"])
    audit_before = _count(AuditLog, target_id=cart["id"])
    upd = client.patch(f"/cart/items/{item['id']}", json={"qty": 3}, headers=h).json()
    assert next(it for it in upd["items"] if it["id"] == item["id"])["qty"] == 3
    bad = client.patch(f"/cart/items/{item['id']}", json={"qty": 0}, headers=h)
    assert bad.status_code == 422
    rem = client.delete(f"/cart/items/{item['id']}", headers=h).json()
    assert all(it["id"] != item["id"] for it in rem["items"])
    assert _count(CartItemHistory, cart_id=cart["id"]) == hist_before + 2
    assert _count(AuditLog, target_id=cart["id"]) == audit_before + 2
    assert client.delete(f"/cart/items/{item['id']}", headers=h).status_code == 404


def test_customer_cannot_touch_other_customer_cart(client: TestClient):
    h_a = auth_headers(client, "094-916-4600")
    h_b = auth_headers(client, "081-222-3333")
    cart_a = client.post("/cart/items", json={"matnr": "10054010", "qty": 1}, headers=h_a).json()
    cart_b = client.get("/cart", headers=h_b).json()
    assert cart_a["id"] != cart_b["id"]
    r = client.post(f"/carts/{cart_b['id']}/merge", json={"source_cart_id": cart_a["id"]}, headers=h_b)
    assert r.status_code == 403  # B ไม่มีสิทธิ์ในตะกร้าของ A


def test_staff_must_use_sales_carts(client: TestClient):
    h = auth_headers(client, "SA-104", "staff")
    assert client.get("/cart", headers=h).status_code == 400
    assert client.post("/cart/checkout-check", headers=h).status_code == 403


def test_unknown_material_404(client: TestClient):
    h = auth_headers(client, "081-222-3333")
    assert client.post("/cart/items", json={"matnr": "00000000", "qty": 1}, headers=h).status_code == 404


def test_pickup_only_items_can_be_carted_but_not_paid_online(client: TestClient, monkeypatch):
    """ของตัวโชว์ (MATNR 20) / ฝากขาย (25) — ใส่ตะกร้าได้ แต่ชำระเงินออนไลน์ไม่ได้

    ข้อมูลทดสอบใช้รหัสขึ้นต้น 10 จึงตั้งค่าให้ 10 เป็นกลุ่มที่ถูกกันไว้ชั่วคราว
    (กฎจริงอ่านจาก config เหมือนกันทุกบรรทัด ไม่ได้ฮาร์ดโค้ดเลขไว้ในโค้ด)
    """
    from app.core.config import get_settings

    monkeypatch.setenv("CATALOG_MATNR_GROUPS", "display:10")
    monkeypatch.setenv("ONLINE_CHECKOUT_BLOCKED_GROUPS", "display")
    get_settings.cache_clear()
    try:
        h = {"Authorization": "Bearer " + login(client, "094-916-4600")["access_token"]}
        client.post("/cart/items", json={"matnr": "10023841", "qty": 1}, headers=h)

        # ใส่ตะกร้าได้ตามปกติ และตะกร้าบอกธงมาให้หน้าเว็บรู้ว่าต้องรับที่สาขา
        cart = client.get("/cart", headers=h).json()
        item = next(it for it in cart["items"] if it["matnr"] == "10023841")
        assert item["pickup_only"] is True and item["group"] == "display"

        # แต่กดชำระเงินไม่ได้ — กันที่เซิร์ฟเวอร์ ไม่ใช่แค่ปิดปุ่มในหน้าเว็บ
        r = client.post("/cart/checkout-check", headers=h)
        assert r.status_code == 409
        assert r.json()["detail"]["pickup_only"][0]["matnr"] == "10023841"
        # ออกใบสั่งซื้อออนไลน์เองก็ไม่ได้เหมือนกัน (กันคนยิง API ตรง)
        assert client.post("/checkout/quotation", json={"force": False}, headers=h).status_code == 409

        # ลูกค้าต้องเห็นว่ามีของที่สาขาไหนบ้าง (ของทั่วไปยังเห็นเฉพาะสาขาที่เลือกเหมือนเดิม)
        rows = client.get("/materials/10023841/stock", headers=h).json()["rows"]
        assert len(rows) > 0 and all("plant_name" in r for r in rows)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

    # อนาคตเปิดขายออนไลน์ได้ = เอาชื่อกลุ่มออกจาก config อย่างเดียว ไม่ต้องแก้โค้ด
    monkeypatch.setenv("CATALOG_MATNR_GROUPS", "display:10")
    monkeypatch.setenv("ONLINE_CHECKOUT_BLOCKED_GROUPS", "")
    get_settings.cache_clear()
    try:
        h = {"Authorization": "Bearer " + login(client, "094-916-4600")["access_token"]}
        assert client.post("/cart/checkout-check", headers=h).status_code == 200
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
