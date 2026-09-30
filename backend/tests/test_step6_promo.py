import pytest

from app.db.session import SessionLocal
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _sales_cart_with_customer(client, hs, items):
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    for matnr, qty in items:
        client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": matnr, "qty": qty}, headers=hs)
    r = client.post(f"/sales/carts/{cart['id']}/attach-customer", json={"customer_key": "1100440310"}, headers=hs)  # ลูกค้า Corporate ไม่มีตะกร้าออนไลน์
    assert r.status_code == 200, r.text
    return client.get(f"/sales/carts/{cart['id']}", headers=hs).json()


def test_evaluate_returns_eligible_and_ineligible_with_reasons(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart = _sales_cart_with_customer(client, hs, [("10023841", 1), ("10052277", 1)])  # โซฟา 24,900 + โต๊ะกลาง 8,900
    r = client.post("/promotions/evaluate", json={"cart_id": cart["id"]}, headers=hs)
    assert r.status_code == 200, r.text
    body = r.json()
    codes_ok = {o["code"]: o for o in body["eligible"]}
    codes_no = {o["code"]: o for o in body["ineligible"]}
    # ยอด 33,800 เข้าครบทุกขั้น · คูปองที่ต้องกรอกโค้ดต้องไม่โผล่ในลิสต์
    assert float(codes_ok["SAVE20"]["amount"]) == 6760  # 20% ของ 33,800
    assert float(codes_ok["SAVE10"]["amount"]) == 3380
    assert not ({"TESTCODE", "SBWELCOME"} & (set(codes_ok) | set(codes_no)))
    assert body["staff_discount_quota_percent"] == 3
    assert float(body["totals"]["subtotal"]) == 33800 and float(body["totals"]["discount_total"]) == 0


def test_apply_promo_and_staff_discount_totals_match_everywhere(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart = _sales_cart_with_customer(client, hs, [("10023841", 1), ("10052277", 1)])
    r = client.post(f"/cart/{cart['id']}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=hs)
    assert r.status_code == 201, r.text
    r = client.post(f"/cart/{cart['id']}/discounts", json={"kind": "staff_manual", "percent": 2}, headers=hs)
    assert r.status_code == 201, r.text
    t = r.json()["totals"]
    assert float(t["discount_total"]) == 6760 + 676  # 20% ของ 33,800 + 2% ของ 33,800
    assert float(t["net_total"]) == 33800 - 6760 - 676
    # ค่าเดียวกันทั้งใน /sales/carts/{id}, /promotions/evaluate และ (ลูกค้า) /cart
    via_sales = client.get(f"/sales/carts/{cart['id']}", headers=hs).json()["totals"]
    via_eval = client.post("/promotions/evaluate", json={"cart_id": cart["id"]}, headers=hs).json()["totals"]
    assert via_sales["net_total"] == t["net_total"] == via_eval["net_total"]
    # โปรที่ apply ไม่เข้าเงื่อนไขแล้ว (ลบโซฟา) → ส่วนลดเป็น 0 + warning
    items = client.get(f"/sales/carts/{cart['id']}", headers=hs).json()["items"]
    sofa = next(it for it in items if it["matnr"] == "10023841")
    after = client.delete(f"/sales/carts/{cart['id']}/items/{sofa['id']}", headers=hs).json()["totals"]
    # เหลือ 8,900 ต่ำกว่าขั้น 15,000 → SAVE20 หลุดเงื่อนไข เหลือแต่ส่วนลดพนักงาน 2%
    assert float(after["discount_total"]) == 178
    assert any("SAVE20" in w for w in after["warnings"])


def test_apply_ineligible_promo_400_and_discount_is_per_cart(client):
    hs = auth_headers(client, "SA-104", "staff")
    a = _sales_cart_with_customer(client, hs, [("10052277", 1)])   # 8,900 — ต่ำกว่าขั้น 15,000
    r = client.post(f"/cart/{a['id']}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=hs)
    assert r.status_code == 400 and "ยอดขาดอีก" in r.json()["detail"]
    b = client.post("/sales/carts", json={}, headers=hs).json()
    client.post(f"/sales/carts/{b['id']}/items", json={"matnr": "10054010", "qty": 1}, headers=hs)
    client.post(f"/cart/{a['id']}/discounts", json={"kind": "staff_manual", "percent": 3}, headers=hs)
    assert float(client.get(f"/sales/carts/{b['id']}", headers=hs).json()["totals"]["discount_total"]) == 0
    # ลูกค้าคนอื่น / เซลล์คนอื่น แตะส่วนลดตะกร้านี้ไม่ได้
    assert client.post(f"/cart/{a['id']}/discounts", json={"kind": "staff_manual", "percent": 1}, headers=auth_headers(client, "SA-105", "staff")).status_code == 403
    assert client.post(f"/cart/{a['id']}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=auth_headers(client, "081-222-3333")).status_code == 403


def test_over_quota_needs_manager_approval(client):
    hs = auth_headers(client, "SA-104", "staff")
    hm = auth_headers(client, "MG-001", "staff")
    cart = _sales_cart_with_customer(client, hs, [("10025117", 1)])  # 45,900
    r = client.post(f"/cart/{cart['id']}/discounts", json={"kind": "staff_manual", "percent": 5, "reason": "ลูกค้าโครงการ"}, headers=hs).json()
    line = r["totals"]["lines"][0]
    assert line["status"] == "pending_approval" and float(r["totals"]["discount_total"]) == 0
    # sales อนุมัติเองไม่ได้
    assert client.post(f"/discount-approvals/{line['id']}/approve", headers=hs).status_code == 403
    pend = client.get("/discount-approvals", headers=hm).json()
    assert any(p["id"] == line["id"] and p["sales_name"] == "สมชาย ก." for p in pend)
    ok = client.post(f"/discount-approvals/{line['id']}/approve", headers=hm).json()
    assert ok["status"] == "applied"
    t = client.get(f"/sales/carts/{cart['id']}", headers=hs).json()["totals"]
    assert float(t["discount_total"]) == 2295  # 5% ของ 45,900
    assert client.post(f"/discount-approvals/{line['id']}/approve", headers=hm).status_code == 404  # อนุมัติซ้ำไม่ได้


def test_customer_can_apply_eligible_promo_on_own_cart(client):
    hc = auth_headers(client, "081-222-3333")
    cart = client.post("/cart/items", json={"matnr": "10044290", "qty": 1}, headers=hc).json()  # ที่นอน 18,900
    ev = client.post("/promotions/evaluate", json={"cart_id": cart["id"]}, headers=hc).json()
    assert any(o["code"] == "SAVE20" for o in ev["eligible"])
    sub = float(ev["totals"]["subtotal"])
    r = client.post(f"/cart/{cart['id']}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=hc)
    assert r.status_code == 201 and float(r.json()["totals"]["discount_total"]) == round(sub * 0.20)
    # ลูกค้าให้ส่วนลดพนักงานเองไม่ได้
    assert client.post(f"/cart/{cart['id']}/discounts", json={"kind": "staff_manual", "percent": 1}, headers=hc).status_code == 403
