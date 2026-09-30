import pytest

from tests.helpers import auth_headers, ensure_seed, login


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()


def test_login_all_four_roles(client):
    assert login(client, "094-916-4600")["user"]["role"] == "customer"
    assert login(client, "SA-104", account_type="staff")["user"]["role"] == "sales"
    assert login(client, "MG-001", account_type="staff")["user"]["role"] == "manager"
    assert login(client, "ADM-001", account_type="staff")["user"]["role"] == "admin"


def test_customer_can_login_with_email_or_member_no(client):
    assert login(client, "napat@email.com")["user"]["sap_customer_no"] == "1100440182"
    assert login(client, "1100440182")["user"]["name"] == "ณภัทร พงษ์ศรี"


def test_wrong_password_401(client):
    r = client.post("/auth/login", json={"identifier": "SA-104", "password": "nope", "account_type": "staff"})
    assert r.status_code == 401


def test_me_and_role_guard(client):
    h = auth_headers(client, "SA-104", "staff")
    assert client.get("/me", headers=h).json()["staff_code"] == "SA-104"
    assert client.get("/me").status_code == 401
    # sales ห้ามเข้า admin endpoint -> 403
    assert client.get("/admin/users", headers=h).status_code == 403
    assert client.get("/admin/users", headers=auth_headers(client, "ADM-001", "staff")).status_code == 200


def test_refresh_rotates_and_old_token_dies(client):
    tok = login(client, "094-916-4600")
    r1 = client.post("/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r1.status_code == 200
    r2 = client.post("/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r2.status_code == 401


def test_register_and_duplicate(client):
    body = {"phone": "0855550001", "password": "abcd", "name": "ทดสอบ"}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409


def test_otp_flow_creates_customer(client):
    r = client.post("/auth/otp/request", json={"phone": "0866660002"})
    code = r.json()["debug_code"]
    bad = client.post("/auth/otp/verify", json={"phone": "0866660002", "code": "000000"})
    assert bad.status_code == 400
    ok = client.post("/auth/otp/verify", json={"phone": "0866660002", "code": code, "name": "ลูกค้า OTP"})
    assert ok.status_code == 200
    assert ok.json()["user"]["role"] == "customer"


def test_name_editable_only_until_member_card_is_linked(client):
    """ชื่อเป็นของ SAP เมื่อผูกบัตรสมาชิกแล้ว — ล็อกที่หลังบ้าน ไม่ใช่แค่ซ่อนช่องกรอก"""
    # ลูกค้าที่สมัครเอง ยังไม่มีเลขสมาชิก -> แก้ชื่อได้
    phone = "0877770003"
    tok = client.post("/auth/register", json={"phone": phone, "password": "abcd", "name": "ชื่อเดิม"}).json()
    h = {"Authorization": "Bearer " + tok["access_token"]}
    r = client.patch("/me", json={"name": "ชื่อใหม่"}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "ชื่อใหม่"

    # ลูกค้าที่ผูกบัตรสมาชิกแล้ว (seed มี sap_customer_no) -> แก้ไม่ได้
    hm = auth_headers(client, "094-916-4600")
    before = client.get("/me", headers=hm).json()
    assert before["sap_customer_no"]
    blocked = client.patch("/me", json={"name": "เปลี่ยนชื่อ"}, headers=hm)
    assert blocked.status_code == 409
    assert client.get("/me", headers=hm).json()["name"] == before["name"]

    # ส่งชื่อเดิมกลับมา (ฟอร์มส่งทุกฟิลด์) ต้องไม่โดนบล็อก ไม่งั้นแก้อีเมลไม่ได้เลย
    ok = client.patch("/me", json={"name": before["name"], "email": before["email"]}, headers=hm)
    assert ok.status_code == 200


def test_โทเคนหมดอายุต้องได้401ไม่ใช่โดนมองเป็นguest(client):
    """เคสจริง: ลูกค้าเปิดหน้าตะกร้าค้างไว้จนโทเคนหมดอายุ แล้วกดใช้โค้ดส่วนลด

    ของเดิม get_current_user_optional คืน None เงียบๆ = ถูกมองเป็น guest
    แล้วด่านตะกร้าตอบ 403 "ไม่มีสิทธิ์เข้าถึงตะกร้านี้" ทั้งที่เป็นตะกร้าของตัวเอง
    หน้าเว็บไม่เคยเห็น 401 เลยไม่รู้ว่าต้องไปต่ออายุโทเคน ลูกค้าติดตายอยู่ตรงนั้น
    """
    from datetime import timedelta

    import jwt

    from app.core.config import get_settings
    from app.models.common import utcnow

    tok = login(client, "094-916-4600")
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    cart_id = client.get("/cart", headers=h).json()["id"]

    dead = jwt.encode(
        {"sub": tok["user"]["id"], "role": "customer", "type": "access",
         "iat": utcnow() - timedelta(hours=2), "exp": utcnow() - timedelta(hours=1)},
        get_settings().jwt_secret, algorithm="HS256",
    )
    dead_h = {"Authorization": f"Bearer {dead}"}

    r = client.post(f"/cart/{cart_id}/discounts", json={"kind": "promotion", "promo_code": "ONTOP"}, headers=dead_h)
    assert r.status_code == 401, r.text

    # endpoint ที่ guest ใช้ได้จริงๆ ก็ต้องไม่ปล่อยโทเคนเสียผ่านไปเป็น guest เงียบๆ
    assert client.get("/cart", headers=dead_h).status_code == 401
    # ไม่ส่งโทเคนมาเลย = guest จริง ต้องยังใช้ได้เหมือนเดิม
    assert client.get("/cart").status_code == 200
