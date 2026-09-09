"""เช็คสต็อก (ZAIBAPI_MATERIAL_AVAILABILITY) — ยิงทั้งตะกร้าครั้งเดียว

เทสวิ่งบน MockAvailabilityClient (ไม่มี SAP_AVAIL_URL/SAP_API_KEY) จะได้ไม่ต้องต่อ SAP จริง
ส่วนการอ่านคำตอบของ gateway เทสด้วย payload ที่บันทึกจากของจริง
"""
from datetime import date

import pytest

from app.db.session import SessionLocal
from app.integrations.sap.availability import AvailAsk, HttpAvailabilityClient, MockAvailabilityClient
from app.integrations.sap.base import SapError
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed

REQ = date(2026, 9, 16)

# บันทึกจาก http://<gateway>/v1/rfc/material-availability ของจริง (ตัดฟิลด์ที่ไม่ได้ใช้ออก)
ROW_OK = {
    "ORDER_ITEM": "000020", "MATERIAL": "000000000019248757", "DESCRIPTION": "MICKEY/CONSOLE CS/DK-100/WH",
    "QUANTITY": 1.0, "SALES_UNIT": "KIT", "UNIT_PRICE": 3360.0, "DISCOUNT": -510.0, "PERCENTAGE": 15.18,
    "AMOUNT": 2850.0, "CURRENCY_UNIT": "THB", "DELIVERY_DATE": "20260916",
    "AVAILABLE_QUAN": 15.0, "AVAILABLE_DATE": "20260916", "COMMITTED_QUAN": 0.0, "COMMITTED_DATE": "",
    "LAENG": 40.0, "BREIT": 100.0, "HOEHE": 75.0,
}
ROW_SPLIT = {
    "ORDER_ITEM": "000020", "MATERIAL": "000000000019214858", "DESCRIPTION": "GALAR/โต๊ะแป้งDT150/SMขาว/VOLAKAS/MN****",
    "QUANTITY": 15.0, "SALES_UNIT": "KIT", "UNIT_PRICE": 37000.0, "DISCOUNT": -27750.0, "PERCENTAGE": 5.0,
    "AMOUNT": 527250.0, "CURRENCY_UNIT": "THB", "DELIVERY_DATE": "20260916",
    "AVAILABLE_QUAN": 1.0, "AVAILABLE_DATE": "20260916", "COMMITTED_QUAN": 4.0, "COMMITTED_DATE": "20261007",
    "LAENG": 47.5, "BREIT": 147.5, "HOEHE": 78.0,
}


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _client(rows_by_call):
    """HttpAvailabilityClient ที่ไม่ยิงเน็ตจริง — ป้อน AI_RETURN_ITEMS ทีละ call"""
    from app.core.config import get_settings

    c = HttpAvailabilityClient("http://sap.test/v1/rfc/material-availability", "k", get_settings())
    calls = list(rows_by_call)
    c._post = lambda asks, cust, req: calls.pop(0)  # type: ignore[method-assign]
    return c


# ---------- อ่านคำตอบของ gateway ----------


def test_parses_real_payload():
    line = _client([[ROW_OK]]).check([AvailAsk("19248757", 1)], "1100467950", REQ)[0]
    assert line is not None
    assert line.matnr == "19248757"  # 18 หลักเติมศูนย์หน้า ต้องถูกตัดทิ้ง
    assert line.description == "MICKEY/CONSOLE CS/DK-100/WH"
    assert float(line.unit_price) == 3360.0 and float(line.amount) == 2850.0
    assert float(line.discount) == 510.0 and line.discount_percent == 15.18  # SAP ส่งลบ เราเก็บบวก
    assert line.available_qty == 15 and line.available_date == date(2026, 9, 16)
    assert line.committed_qty == 0 and line.committed_date is None  # "" ไม่ใช่วันที่


def test_bad_material_blanks_the_bill_then_probes_one_by_one():
    """รหัสผิดตัวเดียว SAP ทิ้งทั้งบิล — client ต้องไล่ทีละบรรทัดเพื่อชี้ตัวที่พัง"""
    c = _client([[], [], [ROW_OK]])  # บิลรวมว่าง → ยิงเดี่ยว: ตัวผิดว่าง, ตัวถูกได้ผล
    out = c.check([AvailAsk("00000000", 1), AvailAsk("19248757", 1)], "1100467950", REQ)
    assert out[0] is None
    assert out[1] is not None and out[1].matnr == "19248757"


def test_http_error_becomes_sap_error():
    c = _client([])
    c._post = lambda *a: (_ for _ in ()).throw(SapError("gateway 500"))  # type: ignore[method-assign]
    with pytest.raises(SapError):
        c.check([AvailAsk("19248757", 1)], "1100467950", REQ)


# ---------- ตีความตัวเลขเป็นสถานะ ----------


def test_available_is_capped_at_requested_qty():
    """ขอ 1 ตอบ AVAILABLE_QUAN 15 — ส่งได้ 1 ตามที่ขอ ห้ามโชว์ว่าจะส่ง 15"""
    from app.services.availability_service import _classify

    line = _client([[ROW_OK]]).check([AvailAsk("19248757", 1)], "1100467950", REQ)[0]
    res = _classify(1, line, "19248757", "x", None)
    assert res.status == "full" and res.ready_qty == 1 and res.short_qty == 0


def test_split_delivery_when_part_must_wait():
    from app.services.availability_service import _classify

    line = _client([[ROW_SPLIT]]).check([AvailAsk("19214858", 5)], "1100467950", REQ)[0]
    res = _classify(5, line, "19214858", "x", None)
    # ได้ 1 ชิ้นวันที่ขอ + อีก 4 ชิ้นรอถึง 7 ต.ค. = ครบ 5 แต่ต้องแบ่งส่ง
    assert res.status == "split"
    assert (res.ready_qty, res.later_qty, res.short_qty) == (1, 4, 0)
    assert res.later_date == date(2026, 10, 7)


def test_short_when_confirmed_less_than_requested():
    from app.services.availability_service import _classify

    line = _client([[ROW_SPLIT]]).check([AvailAsk("19214858", 15)], "1100467950", REQ)[0]
    res = _classify(15, line, "19214858", "x", None)
    assert res.status == "short" and (res.ready_qty, res.later_qty, res.short_qty) == (1, 4, 10)


def test_unknown_material_is_not_silently_available():
    from app.services.availability_service import _classify

    res = _classify(2, None, "99999999", "x", None)
    assert res.status == "unknown" and res.short_qty == 2 and res.ready_qty == 0


# ---------- ของซ้ำในบิลเดียวกัน ----------


def test_same_material_twice_does_not_double_count():
    """หัวใจของการยิงทีเดียว: บรรทัดแรกจองของไปแล้ว บรรทัดหลังต้องเห็นน้อยลง"""
    c = MockAvailabilityClient()
    a, b = c.check([AvailAsk("10025230", 3), AvailAsk("10025230", 3)], "1100467950", REQ)
    assert a and b
    assert a.available_qty + b.available_qty <= 4  # mock stock ของตัวนี้เหลือ 4 ชิ้น
    assert a.available_qty == 3 and b.available_qty == 1


# ---------- API ----------


def _cart_with(client, h, items):
    cart = client.post("/sales/carts", json={"label": "เช็คของ"}, headers=h).json()
    for matnr, qty in items:
        r = client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": matnr, "qty": qty}, headers=h)
        assert r.status_code == 201, r.text
    return cart


def test_endpoint_checks_every_item_in_one_go(client):
    h = auth_headers(client, "SA-104", "staff")
    cart = _cart_with(client, h, [("10023841", 1), ("10031002", 2)])
    r = client.post(f"/sales/carts/{cart['id']}/availability", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 2 and body["all_ok"] is True
    assert {i["matnr"] for i in body["items"]} == {"10023841", "10031002"}
    assert body["source"] == "mock"
    assert body["req_date"] > body["checked_at"][:10]  # REQ_DATE = วันนี้ + 7


def test_walkin_customer_used_when_cart_has_no_customer(client):
    h = auth_headers(client, "SA-104", "staff")
    cart = _cart_with(client, h, [("10023841", 1)])
    body = client.post(f"/sales/carts/{cart['id']}/availability", headers=h).json()
    assert body["is_walkin"] is True and body["customer_no"] == "1100467950"


def test_short_item_blocks_all_ok(client):
    h = auth_headers(client, "SA-104", "staff")
    cart = _cart_with(client, h, [("10025230", 99)])  # mock มีแค่ 4 ชิ้น
    body = client.post(f"/sales/carts/{cart['id']}/availability", headers=h).json()
    assert body["all_ok"] is False
    it = body["items"][0]
    assert it["status"] in ("short", "none") and it["short_qty"] == 95


def test_empty_cart_is_not_ok_but_not_an_error(client):
    h = auth_headers(client, "SA-104", "staff")
    cart = client.post("/sales/carts", json={"label": "ว่าง"}, headers=h).json()
    body = client.post(f"/sales/carts/{cart['id']}/availability", headers=h).json()
    assert body["items"] == [] and body["all_ok"] is False


def test_single_material_check_before_adding(client):
    h = auth_headers(client, "SA-104", "staff")
    r = client.post("/sales/availability", json={"matnr": "10023841", "qty": 1}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "full"
    assert client.post("/sales/availability", json={"matnr": "NOPE", "qty": 1}, headers=h).status_code == 404


def test_customer_cannot_check_sales_cart(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart = _cart_with(client, hs, [("10023841", 1)])
    hc = auth_headers(client, "081-222-3333")
    assert client.post(f"/sales/carts/{cart['id']}/availability", headers=hc).status_code == 403
    assert client.post("/sales/availability", json={"matnr": "10023841"}, headers=hc).status_code == 403


def test_kit_components_are_dropped_before_matching():
    """สินค้าชุดตอบแม่ 1 แถว + ลูกอีกหลายแถว ถ้าไม่ตัดลูกออก จำนวนแถวจะไม่ตรงกับที่ขอ
    แล้วโค้ดจะหลุดไปไล่ทีละบรรทัด = แต่ละบรรทัดเห็นของเต็มเหมือนกันหมด (ขายเกิน)
    ตัวเลขชุดนี้ยกมาจากที่ยิง SAP จริงด้วย 59064091 (GO/Bedroom)"""
    from app.integrations.sap.availability import top_level_rows

    rows = [
        {"ORDER_ITEM": "000020", "HIGH_LEVEL": "000000", "MATERIAL": "59064091", "AVAILABLE_QUAN": 7.0},
        {"ORDER_ITEM": "000040", "HIGH_LEVEL": "000020", "MATERIAL": "19224282", "AVAILABLE_QUAN": 7.0},
        {"ORDER_ITEM": "000080", "HIGH_LEVEL": "000020", "MATERIAL": "19226511", "AVAILABLE_QUAN": 8.0},
        {"ORDER_ITEM": "000120", "HIGH_LEVEL": "000020", "MATERIAL": "19231493", "AVAILABLE_QUAN": 36.0},
        {"ORDER_ITEM": "000200", "HIGH_LEVEL": "000000", "MATERIAL": "19205233", "AVAILABLE_QUAN": 4.0},
    ]
    kept = top_level_rows(rows)
    assert [r["MATERIAL"] for r in kept] == ["59064091", "19205233"]
    # ฟิลด์หายหรือว่าง = ถือว่าเป็นแถวแม่ ไม่ใช่ตัดทิ้ง
    assert len(top_level_rows([{"MATERIAL": "x"}, {"MATERIAL": "y", "HIGH_LEVEL": ""}])) == 2
