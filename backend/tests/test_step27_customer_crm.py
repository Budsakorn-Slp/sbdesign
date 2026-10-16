"""ทะเบียนลูกค้าจริง (SAP CRM customer-search) — กรองผลค้นแบบใกล้เคียงให้เหลือรายที่ใช่จริง

ข้อมูลในเทสเป็นของปลอมทั้งหมด หน้าตาเหมือนที่ API ตอบ (ET_SEARCHRESULT)
"""
import pytest

from app.core.config import get_settings
from app.integrations.sap import customer_crm, lookup_customer


def _row(partner, tel="", mob="", mob2="", email="", first="", last="", addr="", crdat="20250101", block=""):
    return {"PARTNER": partner, "TELEPHONE": tel, "MOBILE_TEL": mob, "MOBILE_TEL2": mob2, "E_MAIL": email,
            "FIRSTNAME": first, "LASTNAME": last, "ADDRESS": addr, "CRDAT": crdat, "CENTRALBLOCK": block,
            "CENTRALARCHIVINGFLAG": ""}


ROWS = [
    # คนที่ค้น: role ลูกค้า (11) + bill-to (17) + ship-to (18) — ต้องได้แค่ 11
    _row("1101946329", tel="02-445-3777", mob="098-256-5517", first="ทดสอบ", last="หนึ่ง",
         addr="99/1 ถ.ทดสอบ แขวงทดสอบ เขตทดสอบ กรุงเทพฯ 10260", email="one@test.local"),
    _row("1702292161", mob="0982565517"),
    _row("1802083302", mob="0982565517"),
    # ค้นแบบใกล้เคียงติดมา: ต่างกันหลักเดียว / เบอร์มั่ว
    _row("1101000001", mob="098-256-4517", first="คนอื่น"),
    _row("1101000002", tel="02-000-9000", first="เบอร์ปน"),
    # ถูกบล็อก
    _row("1101000003", mob="0982565517", first="บล็อก", block="X"),
]


@pytest.fixture
def crm(monkeypatch):
    monkeypatch.setattr(get_settings(), "sap_customer_url", "http://sap.test/v1/rfc/customer-search")
    sent = []

    def fake_post(url, params, timeout):
        sent.append(params)
        return {"data": {"ET_SEARCHRESULT": ROWS, "ET_RETURN": []}}

    monkeypatch.setattr(customer_crm, "_post", fake_post)
    return sent


def test_ค้นเบอร์_ได้เฉพาะลูกค้าเลข_11_ที่เบอร์ตรงเป๊ะ(crm):
    found = customer_crm.search("098-256-5517")
    assert [c.sap_customer_no for c in found] == ["1101946329"]
    c = found[0]
    assert c.name == "ทดสอบ หนึ่ง" and c.phone == "0982565517" and c.email == "one@test.local"
    assert c.address.endswith("10260") and c.postcode == "10260"
    assert crm[-1] == {"IV_TELEPHONE": "0982565517"}


def test_เบอร์รูปแบบ_66_ก็เจอ(crm):
    assert customer_crm.get_customer("+66 98 256 5517").sap_customer_no == "1101946329"


def test_ค้นอีเมล_และเลขลูกค้า(crm):
    assert customer_crm.get_customer("ONE@test.local").sap_customer_no == "1101946329"
    assert crm[-1] == {"IV_EMAIL": "ONE@test.local"}
    assert customer_crm.get_customer("1101946329").sap_customer_no == "1101946329"
    assert crm[-1] == {"IS_CENTRALDATA": {"PARTNER": "1101946329"}}


def test_ไม่ตรงเลย_ได้ว่าง_ไม่เดา(crm):
    assert customer_crm.get_customer("0811111111") is None
    n = len(crm)
    assert customer_crm.search("ชื่อคน") == [] and len(crm) == n, "ชื่อคนไม่ยิงค้น"


def test_ทางเดียวของทั้งระบบ_เปิดแล้วใช้ทะเบียนจริง(crm):
    assert lookup_customer("0982565517").sap_customer_no == "1101946329"


def test_ปิดอยู่_ใช้ข้อมูลจำลองเดิม(monkeypatch):
    monkeypatch.setattr(get_settings(), "sap_customer_url", "")
    called = []
    monkeypatch.setattr(customer_crm, "_post", lambda *a: called.append(a))
    c = lookup_customer("0949164600")  # ลูกค้าในข้อมูลจำลอง
    assert c and c.sap_customer_no == "1100440182" and not called


def test_สร้างเลขลูกค้า_ยังไม่พร้อม(monkeypatch):
    monkeypatch.setattr(get_settings(), "sap_customer_create_url", "")
    with pytest.raises(customer_crm.CustomerCreateNotReady):
        customer_crm.create_customer(customer_crm.NewCustomer(first_name="ก", last_name="ข", phone="0800000000"))


def _crm_with(monkeypatch, rows, owners=()):
    monkeypatch.setattr(get_settings(), "sap_customer_url", "http://sap.test/v1/rfc/customer-search")
    monkeypatch.setattr(customer_crm, "_post", lambda url, params, timeout: {"data": {
        "ET_SEARCHRESULT": rows, "ET_CUSTATTR": [{"PARTNER": p} for p in owners], "ET_RETURN": []}})


SHARED = [  # เบอร์ร้าน/เบอร์บ้านที่ผูกหลายลูกค้า
    _row("1100797241", tel="0860000000", first="ก", crdat="20161031"),
    _row("1101927575", tel="0860000000", first="ข", crdat="20260203"),
    _row("1100467950", tel="0860000000", mob="0860000000", first="เจ้าของ", crdat="20130103"),
]


def test_เบอร์ผูกหลายราย_ไม่มีตัวชี้เจ้าของ_ไม่เดา(monkeypatch):
    _crm_with(monkeypatch, SHARED)
    found = customer_crm.search("0860000000")
    assert len(found) == 3
    assert found[0].sap_customer_no == "1100467950", "เบอร์อยู่ในช่องมือถือของตัวเองขึ้นก่อน"
    assert customer_crm.get_customer("0860000000") is None, "แยกเจ้าของไม่ได้ = ไม่ผูกให้"


def test_เบอร์ผูกหลายราย_ET_CUSTATTR_ชี้เจ้าของ(monkeypatch):
    _crm_with(monkeypatch, SHARED, owners=["1100797241"])
    assert customer_crm.search("0860000000")[0].sap_customer_no == "1100797241"
    assert customer_crm.get_customer("0860000000").sap_customer_no == "1100797241"


def test_หน้าพนักงาน_ค้นเบอร์เห็นทุกราย_เบอร์ปิดบัง(client, monkeypatch):
    from tests.helpers import auth_headers, ensure_seed

    ensure_seed()
    _crm_with(monkeypatch, SHARED, owners=["1100467950"])
    h = auth_headers(client, "SA-104", "staff")
    rows = [r for r in client.get("/customers/search", params={"q": "0860000000"}, headers=h).json() if r["source"] == "sap"]
    assert [r["sap_customer_no"] for r in rows][:1] == ["1100467950"] and len(rows) == 3
    assert all("xxx" in (r["phone"] or "") for r in rows)
