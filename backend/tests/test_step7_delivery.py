import pytest

from app.db.session import SessionLocal
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _cart(client, hs, items):
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    for matnr, qty, mode, plant in items:
        client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": matnr, "qty": qty, "supply_mode": mode, "plant_code": plant}, headers=hs)
    return cart


def test_postcode_changes_fee_and_groups(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart = _cart(client, hs, [("10023841", 1, "ship", None), ("10031002", 2, "takeaway", "BKN"), ("10046100", 1, None, None)])  # ตู้เสื้อผ้าต้องติดตั้ง
    a = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=hs)
    assert a.status_code == 200, a.text
    a = a.json()
    assert a["zone"] == "A" and float(a["base_fee"]) == 800 and float(a["install_fee"]) == 1500
    modes = {g["mode"]: g for g in a["groups"]}
    assert set(modes) == {"takeaway", "ship", "install"}
    assert modes["takeaway"]["items"][0]["matnr"] == "10031002" and modes["takeaway"]["fee_note"] == "ฟรี"
    assert modes["install"]["items"][0]["matnr"] == "10046100"
    assert len(a["slots"]) == 14 and all(s["zone"] == "A" for s in a["slots"])
    # เปลี่ยนรหัสไปรษณีย์ → ค่าส่งเปลี่ยน
    d = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "50000"}, headers=hs).json()
    assert d["zone"] == "D" and float(d["base_fee"]) == 3500 and float(d["install_fee"]) == 2500
    # รหัสที่ไม่รู้จัก prefix → ใช้ prefix rule; รูปแบบผิด → 422
    assert client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "abc12"}, headers=hs).status_code == 422
    # ยอดรวมทั้งบิลใน cart รวมค่าส่ง
    t = client.get(f"/sales/carts/{cart['id']}", headers=hs).json()["totals"]
    assert float(t["shipping_fee"]) == 3500 and float(t["install_fee"]) == 2500
    assert float(t["grand_total"]) == float(t["net_total"]) + 3500 + 2500


def test_hold_slot_reduces_quota_and_full_slot_409(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart = _cart(client, hs, [("10052277", 1, "ship", None)])
    q = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=hs).json()
    open_slot = next(s for s in q["slots"] if s["remaining"] > 0)
    full_slot = next(s for s in q["slots"] if s["remaining"] == 0)
    r = client.post(f"/delivery/slots/{open_slot['id']}/hold", json={"cart_id": cart["id"]}, headers=hs)
    assert r.status_code == 200 and r.json()["remaining"] == open_slot["remaining"] - 1
    r = client.post(f"/delivery/slots/{full_slot['id']}/hold", json={"cart_id": cart["id"]}, headers=hs)
    assert r.status_code == 409
    q2 = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=hs).json()
    held = next(s for s in q2["slots"] if s["id"] == open_slot["id"])
    assert held["held_by_this_cart"] is True and held["remaining"] == open_slot["remaining"] - 1 and q2["held_slot_id"] == open_slot["id"]
    # ย้ายไปคิวอื่น → คิวเดิมคืนโควตา
    other = next(s for s in q2["slots"] if s["remaining"] > 0 and s["id"] != open_slot["id"])
    client.post(f"/delivery/slots/{other['id']}/hold", json={"cart_id": cart["id"]}, headers=hs)
    q3 = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=hs).json()
    assert next(s for s in q3["slots"] if s["id"] == open_slot["id"])["remaining"] == open_slot["remaining"]
    # เซลล์อื่นแตะตะกร้านี้ไม่ได้
    assert client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=auth_headers(client, "SA-105", "staff")).status_code == 403


def test_gold_free_shipping_discounts_fee(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart = _cart(client, hs, [("10025117", 1, "ship", None)])  # VERONA 45,900
    client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "4400182"}, headers=hs)  # Gold
    client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "10110"}, headers=hs)
    ev = client.post("/promotions/evaluate", json={"cart_id": cart["id"]}, headers=hs).json()
    assert any(o["code"] == "GOLD-FREESHIP" for o in ev["eligible"])
    r = client.post(f"/cart/{cart['id']}/discounts", json={"kind": "promotion", "promo_code": "GOLD-FREESHIP"}, headers=hs).json()
    t = r["totals"]
    assert float(t["shipping_fee"]) == 800 and float(t["shipping_discount"]) == 800
    assert float(t["grand_total"]) == float(t["net_total"]) + 800 - 800
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)
