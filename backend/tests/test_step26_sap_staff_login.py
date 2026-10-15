"""login พนักงานสองทางคู่กัน: บัญชีในฐานเรา (บัญชีทดสอบ) + รหัสพนักงาน/PIN ของ SAP CRM"""
import random

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.sap import employee_auth
from app.models.user import User
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    from app.core.security import hash_password
    from app.models.catalog import Plant

    ensure_seed()
    with SessionLocal() as db:
        for code, name in (("S311", "DS-บางนา"), ("S316", "DS-เวสต์เกท")):
            if not db.get(Plant, code):
                db.add(Plant(plant_code=code, name=name, type="store"))
        if not db.scalar(select(User).where(User.staff_code == "4680012")):
            db.add(User(role="sales", name="รัตนากร", staff_code="4680012", password_hash=hash_password("1122"), is_guest=False))
        db.commit()


@pytest.fixture
def sap_on(monkeypatch):
    """เปิด SAP login แล้วแทนตัวยิง API ด้วยของปลอม — คืน dict ให้เทสตั้งผลที่ต้องการ"""
    monkeypatch.setattr(get_settings(), "sap_auth_url", "http://sap.test/v1/auth/login")
    st = {"calls": 0, "result": None}

    def fake(login_id, password):
        st["calls"] += 1
        r = st["result"]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(employee_auth, "login", fake)
    return st


def _pernr() -> str:
    return f"09{random.randint(100000, 999999)}"


def _emp(pernr, group="311", name="สุภาวดี ทดสอบ"):
    return employee_auth.SapEmployee(pernr=pernr, name=name, sales_office="SBDS", sales_group=group, distr_chan="18")


def _login(client, code, pin="1234"):
    return client.post("/auth/login", json={"identifier": code, "password": pin, "account_type": "staff"})


def test_พนักงานจริง_ล็อกอินด้วย_SAP_ครั้งแรกสร้างบัญชีให้(client, sap_on):
    p = _pernr()
    sap_on["result"] = _emp(p)
    r = _login(client, p)
    assert r.status_code == 200, r.text
    u = r.json()["user"]
    assert u["role"] == "sales" and u["auth_source"] == "sap"
    assert u["staff_code"] == p.lstrip("0"), "รหัสที่โชว์ตัดศูนย์หน้า"
    assert (u["sap_pernr"], u["sap_sales_office"], u["sap_sales_group"]) == (p, "SBDS", "311")
    assert u["branch_id"] == "S311", "กลุ่มขาย 311 = showroom S311"
    with SessionLocal() as db:
        row = db.scalar(select(User).where(User.sap_pernr == p))
        assert row.password_hash is None, "ห้ามเก็บ PIN"

    # ครั้งที่สอง พิมพ์แบบไม่มีศูนย์หน้า — ได้บัญชีเดิม และอัปเดตกลุ่มขายตาม SAP
    sap_on["result"] = _emp(p, group="316", name="สุภาวดี ย้ายสาขา")
    r2 = _login(client, p.lstrip("0"))
    assert r2.status_code == 200, r2.text
    u2 = r2.json()["user"]
    assert u2["id"] == u["id"] and u2["branch_id"] == "S316" and u2["name"] == "สุภาวดี ย้ายสาขา"


def test_role_ที่ตั้งในฐานเราไม่โดน_SAP_ทับ(client, sap_on):
    p = _pernr()
    sap_on["result"] = _emp(p)
    uid = _login(client, p).json()["user"]["id"]
    with SessionLocal() as db:
        db.get(User, uid).role = "manager"
        db.commit()
    assert _login(client, p).json()["user"]["role"] == "manager"


def test_PIN_ผิด_ได้ข้อความกลาง_และนับเป็นการลองผิด(client, sap_on):
    sap_on["result"] = employee_auth.SapLoginFailed()
    r = _login(client, _pernr())
    assert r.status_code == 401 and r.json()["detail"] == "บัญชีหรือรหัสผ่านไม่ถูกต้อง"


def test_SAP_ล็อก_ส่งต่อเป็น_429(client, sap_on):
    sap_on["result"] = employee_auth.SapLoginLocked(600)
    r = _login(client, _pernr())
    assert r.status_code == 429 and "10 นาที" in r.json()["detail"]


def test_SAP_ล่ม_ได้_503_ไม่ใช่รหัสผิด(client, sap_on):
    sap_on["result"] = employee_auth.SapAuthUnavailable("timeout")
    r = _login(client, _pernr())
    assert r.status_code == 503 and "SAP" in r.json()["detail"]


def test_บัญชีทดสอบในฐานเรา_ยังเข้าทางเดิม_ไม่ยิง_SAP(client, sap_on):
    sap_on["result"] = employee_auth.SapLoginFailed()
    h = auth_headers(client, "SA-104", "staff")
    me = client.get("/me", headers=h).json()
    assert me["staff_code"] == "SA-104" and me["auth_source"] == "local"
    assert sap_on["calls"] == 0


def test_ปิด_SAP_login_แล้วรหัสที่ไม่มีในฐานเข้าไม่ได้(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "sap_auth_url", "")
    called = []
    monkeypatch.setattr(employee_auth, "login", lambda *a: called.append(a))
    assert _login(client, _pernr()).status_code == 401
    assert not called


def test_โหมดทดสอบ_IT_ตั้งพนักงานขายสำหรับทดสอบได้(client):
    h = auth_headers(client, "4680012", "staff")
    r = client.put("/it-test/profile", json={"sap_pernr": "9570311", "sap_sales_office": "sbds", "sap_sales_group": "311"}, headers=h)
    assert r.status_code == 200, r.text
    assert (r.json()["sap_pernr"], r.json()["sap_sales_office"], r.json()["sap_sales_group"]) == ("09570311", "SBDS", "311")
    me = client.get("/me", headers=h).json()
    assert me["auth_source"] == "local", "ค่าที่ตั้งเองไม่ใช่ตัวตนที่ SAP ยืนยัน"
    # ล้างออก
    r = client.put("/it-test/profile", json={"sap_pernr": "", "sap_sales_office": "", "sap_sales_group": ""}, headers=h)
    assert r.json()["sap_pernr"] is None
    assert client.put("/it-test/profile", json={"sap_pernr": "12AB"}, headers=h).status_code == 422
