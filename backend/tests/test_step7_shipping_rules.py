"""ค่าส่งจากตารางของเราเอง (ship_rules + ship_rates) แทนค่าส่งตามโซนของ SAP

ชุดกฎในเทสต์จำลองของจริงที่ ETL มาจาก Amasty: ส่งฟรีเมื่อครบยอด · SB Care ส่งฟรี ·
เรตเดียว 399 เมื่อยังไม่ครบยอดและมีของธรรมดาอยู่ในตะกร้า · ที่เหลือคิดตามตารางน้ำหนักแยกเขต

ตารางในเทสต์ตั้งใจไม่มีแถวปลายเปิด เพื่อให้ทดสอบเคส "หนักเกินตาราง → รอเจ้าหน้าที่ประเมิน" ได้
"""
from decimal import Decimal

import pytest
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models.cart import Cart
from app.models.shipping import ShipArea, ShipAreaPostcode, ShipProductAttr, ShipRate, ShipRule
from app.seed import seed_catalog
from app.services import shipping_engine
from tests.helpers import auth_headers, ensure_seed

# sku ที่ติดธง flatpack_not_seller = คิดค่าส่งตามตารางน้ำหนัก
FLAGGED = {"DIN-CHR-OAK": 6, "BKC-GRD-5": 30}
RATES = {  # area_id -> [(from, to, fee)] ครึ่งเปิด [from, to)
    1: [(0, 10, 100), (10, 20, 200), (20, 30, 300)],
    2: [(0, 10, 150), (10, 20, 250), (20, 30, 350)],
}


@pytest.fixture(autouse=True)
def _shipping_tables():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)
        for t in (ShipRate, ShipRule, ShipProductAttr, ShipAreaPostcode, ShipArea):
            db.execute(delete(t))
        db.add_all([
            ShipArea(id=1, code="bkk_metro", name="กรุงเทพฯ และปริมณฑล", is_default=False),
            ShipArea(id=2, code="upcountry", name="ต่างจังหวัด", is_default=True),
        ])
        db.flush()
        db.add_all([ShipAreaPostcode(prefix=p, area_id=1) for p in ("10", "11", "12")])
        db.add_all([
            ShipRate(area_id=a, weight_from=Decimal(lo), weight_to=Decimal(hi), fee=Decimal(fee))
            for a, bands in RATES.items()
            for lo, hi, fee in bands
        ])
        db.add_all([
            ShipRule(code="free-6000", name="ส่งฟรีเมื่อครบ 6,000", kind="free", priority=0, stop_on_match=True,
                     fee=Decimal(0), conditions={"min_subtotal": 6000}),
            ShipRule(code="sbcare-free", name="SB Care ส่งฟรี", kind="free", priority=0, stop_on_match=True,
                     fee=Decimal(0), conditions={"any_sku": ["LGT-ARC-BRS"]}),
            ShipRule(code="flat-399", name="เรตเดียว 399", kind="flat", priority=1, stop_on_match=True,
                     fee=Decimal(399), conditions={"max_subtotal": 5999,
                                                   "require_item_all_of": [{"attr": "flatpack_not_seller", "op": "==", "value": "0"}]}),
            ShipRule(code="weight-table", name="ตารางน้ำหนัก", kind="table", priority=3, stop_on_match=True,
                     fee=Decimal(0), conditions={"weight_attr": "flatpack_not_seller"}),
        ])
        db.add_all([ShipProductAttr(sku=sku, weight_kg=Decimal(w), flatpack_not_seller=True) for sku, w in FLAGGED.items()])
        db.commit()
    yield
    with SessionLocal() as db:
        for t in (ShipRate, ShipRule, ShipProductAttr, ShipAreaPostcode, ShipArea):
            db.execute(delete(t))
        db.commit()


def _cart(client, hs, items):
    cart = client.post("/sales/carts", json={}, headers=hs).json()
    for matnr, qty, mode in items:
        client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": matnr, "qty": qty, "supply_mode": mode}, headers=hs)
    return cart


def _quote(client, hs, items, postcode="10110"):
    cart = _cart(client, hs, items)
    r = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": postcode}, headers=hs)
    assert r.status_code == 200, r.text
    return cart, r.json()


def test_free_over_6000_beats_zone_fee(client):
    """โซน A ของ SAP คิด 800 แต่กฎเราส่งฟรีเมื่อครบ 6,000 — ค่าส่งที่ออกต้องมาจากกฎเรา"""
    hs = auth_headers(client, "SA-104", "staff")
    cart, q = _quote(client, hs, [("10023841", 1, "ship")])  # 24,900
    assert float(q["base_fee"]) == 0 and q["ship_source"] == "free-6000" and q["ship_needs_review"] is False
    assert q["ship_area"] == "กรุงเทพฯ และปริมณฑล"
    t = client.get(f"/sales/carts/{cart['id']}", headers=hs).json()["totals"]
    assert float(t["shipping_fee"]) == 0
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)


def test_flat_399_for_ordinary_cart_under_threshold(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart, q = _quote(client, hs, [("10031110", 1, "ship")])  # LGT-PND-OAK 2,490 ของธรรมดา
    assert float(q["base_fee"]) == 399 and q["ship_source"] == "flat-399"
    t = client.get(f"/sales/carts/{cart['id']}", headers=hs).json()["totals"]
    assert float(t["shipping_fee"]) == 399 and float(t["grand_total"]) == float(t["net_total"]) + 399
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)


def test_sbcare_sku_ships_free(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart, q = _quote(client, hs, [("10031002", 1, "ship")])  # LGT-ARC-BRS 3,590 อยู่ในลิสต์ SB Care
    assert float(q["base_fee"]) == 0 and q["ship_source"] == "sbcare-free"
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)


def test_weight_table_by_area(client):
    """ตะกร้าที่มีแต่ของติดธง → ตกมาถึงตารางน้ำหนัก และค่าส่งต่างกันตามเขต"""
    hs = auth_headers(client, "SA-104", "staff")
    cart, q = _quote(client, hs, [("10061050", 2, "ship")])  # DIN-CHR-OAK 6 kg × 2 = 12 kg
    assert float(q["base_fee"]) == 200 and q["ship_source"] == "weight-table"
    assert float(q["ship_weight_kg"]) == 12 and q["ship_area"] == "กรุงเทพฯ และปริมณฑล"
    # ต่างจังหวัด (ไม่เข้า prefix ไหน → เขตปริยาย) แพงกว่า
    up = client.post("/delivery/quote", json={"cart_id": cart["id"], "postcode": "50000"}, headers=hs).json()
    assert float(up["base_fee"]) == 250 and up["ship_area"] == "ต่างจังหวัด"
    # หนึ่งตัว 6 kg ตกช่วงแรก
    cart2, q2 = _quote(client, hs, [("10061050", 1, "ship")])
    assert float(q2["base_fee"]) == 100
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)
    client.delete(f"/sales/carts/{cart2['id']}", headers=hs)


def test_mixed_cart_uses_flat_rate_not_table(client):
    """ของติดธงปนของธรรมดา = ต้นทางเข้ากฎเรตเดียว (Product\\Found value=1 aggregator=all)

    เงื่อนไขคือ "มีอย่างน้อยหนึ่งรายการที่ผ่านครบทุกข้อ" ไม่ใช่ "ทุกรายการต้องผ่าน"
    ตารางน้ำหนักจึงทำงานเฉพาะตะกร้าที่เป็นของติดธงล้วน
    """
    hs = auth_headers(client, "SA-104", "staff")
    cart, q = _quote(client, hs, [("10061050", 1, "ship"), ("10031110", 1, "ship")])  # 1,890 + 2,490
    assert float(q["base_fee"]) == 399 and q["ship_source"] == "flat-399"
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)


def test_overweight_needs_review_not_silent_fallback(client):
    """หนักเกินตาราง → ไม่เดาราคาให้ ต้องบอกว่ารอเจ้าหน้าที่ประเมิน"""
    hs = auth_headers(client, "SA-104", "staff")
    cart, q = _quote(client, hs, [("10054010", 1, "ship")])  # BKC-GRD-5 30 kg พ้นแถวสุดท้าย
    assert float(q["base_fee"]) == 0 and q["ship_needs_review"] is True
    assert q["ship_warnings"] and "ประเมิน" in q["ship_warnings"][0]
    assert any(s["rule"] == "weight-table" and s["matched"] is False for s in q["ship_trace"])
    t = client.get(f"/sales/carts/{cart['id']}", headers=hs).json()["totals"]
    assert float(t["shipping_fee"]) == 0
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)


def test_takeaway_only_cart_has_no_shipping(client):
    hs = auth_headers(client, "SA-104", "staff")
    cart, q = _quote(client, hs, [("10031110", 1, "takeaway")])
    assert float(q["base_fee"]) == 0 and q["ship_source"] == "no_ship" and q["ship_needs_review"] is False
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)


def test_half_open_band_boundary_and_postcode_prefix(client):
    """น้ำหนักที่ตกขอบพอดีต้องมีเจ้าของแถวเดียว — 10.000 kg เป็นของช่วง [10, 20)"""
    with SessionLocal() as db:
        assert float(shipping_engine._rate_for(db, 1, Decimal("9.999")).fee) == 100
        assert float(shipping_engine._rate_for(db, 1, Decimal("10")).fee) == 200
        assert float(shipping_engine._rate_for(db, 1, Decimal("20")).fee) == 300
        assert shipping_engine._rate_for(db, 1, Decimal("30")) is None
        assert shipping_engine.area_for_postcode(db, "12120").id == 1
        assert shipping_engine.area_for_postcode(db, "90110").id == 2  # ไม่เข้า prefix ไหน → ปริยาย
        assert shipping_engine.area_for_postcode(db, None).id == 2


def test_falls_back_to_sap_zone_when_no_rules(client):
    """ยังไม่ได้ ETL (ตาราง ship_rules ว่าง) → ใช้ค่าส่งตามโซนของ SAP เหมือนเดิม"""
    hs = auth_headers(client, "SA-104", "staff")
    with SessionLocal() as db:
        db.execute(delete(ShipRule))
        db.commit()
    cart, q = _quote(client, hs, [("10023841", 1, "ship")])
    assert float(q["base_fee"]) == 800 and q["ship_source"] == "sap_zone"
    client.delete(f"/sales/carts/{cart['id']}", headers=hs)
