import pytest

from tests.helpers import auth_headers, ensure_seed, login


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()


def test_login_all_four_roles(client):
    assert login(client, "089-234-4471")["user"]["role"] == "customer"
    assert login(client, "SA-104", account_type="staff")["user"]["role"] == "sales"
    assert login(client, "MG-001", account_type="staff")["user"]["role"] == "manager"
    assert login(client, "ADM-001", account_type="staff")["user"]["role"] == "admin"


def test_customer_can_login_with_email_or_member_no(client):
    assert login(client, "napat@email.com")["user"]["sap_customer_no"] == "4400182"
    assert login(client, "4400182")["user"]["name"] == "ณภัทร พงษ์ศรี"


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
    tok = login(client, "089-234-4471")
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
