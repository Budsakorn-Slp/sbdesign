"""ค่าขนส่งฝั่งพนักงาน — เปิด Mat A534/A761 ตามยอดบิล (หน้า /sales เท่านั้น)

กฎที่ทีมขายให้มา:
    ต่ำกว่า 15,000        -> A534 = 600
    15,000 - 109,999      -> A761 = 100
    110,000 - 209,999     -> A761 = 200  (ทุก 100,000 เพิ่ม 100)
    410,000 ขึ้นไป        -> A761 = 500  (เพดาน)
"""
import pytest

from app.db.session import SessionLocal
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


# ตั้งใจใช้ของถูก (1,777) เป็นค่าตั้งต้น เพื่อให้ตะกร้าใบเล็กอยู่ใต้ 15,000 จริง
def _cart_with(client, h, matnr="10061050", qty=1):
    cart = client.post("/sales/carts", json={"label": "ทดสอบค่าขนส่ง"}, headers=h).json()
    r = client.post(f"/sales/carts/{cart['id']}/items", json={"matnr": matnr, "qty": qty}, headers=h)
    assert r.status_code == 201, r.text
    return cart["id"]


def test_บิลเล็กเสนอ_A534_600บาท(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    r = client.get(f"/sales/carts/{cid}/shipping-charge", headers=h)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["matnr"] == "A534" and s["fee"] == "600"
    assert s["current"] is None          # ยังไม่ได้เปิดเข้าบิล แค่เสนอ
    assert "15,000" in s["tier_label"]


def test_บิลใหญ่ขยับเทียร์เอง(client):
    """ยอดขยับข้ามเทียร์แล้วข้อเสนอต้องเปลี่ยนตาม ไม่ค้างของเดิม"""
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h, qty=1)
    small = client.get(f"/sales/carts/{cid}/shipping-charge", headers=h).json()
    item = client.get(f"/sales/carts/{cid}", headers=h).json()["items"][0]
    # อัดจำนวนจนยอดทะลุ 15,000
    need = int(15000 // float(item["unit_price"])) + 1
    client.patch(f"/sales/carts/{cid}/items/{item['id']}", json={"qty": need}, headers=h)
    big = client.get(f"/sales/carts/{cid}/shipping-charge", headers=h).json()
    assert small["matnr"] == "A534"
    assert big["matnr"] == "A761" and float(big["fee"]) >= 100


def test_เปิด_Mat_เข้าบิลแล้วไม่ถูกนับเป็นยอดสินค้า(client):
    """บรรทัดค่าขนส่งต้องไม่ดันยอดสินค้าจนเปลี่ยนเทียร์ตัวเอง — ไม่งั้นวนไม่จบ"""
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    before = client.get(f"/sales/carts/{cid}/shipping-charge", headers=h).json()["goods_subtotal"]

    r = client.post(f"/sales/carts/{cid}/shipping-charge", json={"matnr": "A534", "fee": "600"}, headers=h)
    assert r.status_code == 200, r.text

    after = client.get(f"/sales/carts/{cid}/shipping-charge", headers=h).json()
    assert after["goods_subtotal"] == before          # ยอดสินค้าเท่าเดิม
    assert after["current"]["fee"] == "600.00"
    assert after["current"]["matches_rule"] is True
    assert any(it["matnr"] == "A534" for it in r.json()["items"])


def test_แก้ราคาเองได้_และจำได้ว่าไม่ตรงกฎ(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    client.post(f"/sales/carts/{cid}/shipping-charge",
                json={"matnr": "A534", "fee": "1250", "remark": "ของชิ้นใหญ่ ส่งกระบี่"}, headers=h)
    cur = client.get(f"/sales/carts/{cid}/shipping-charge", headers=h).json()["current"]
    assert cur["fee"] == "1250.00"
    assert cur["matches_rule"] is False               # ธงไว้ให้หัวหน้าไล่ดูย้อนหลัง
    assert cur["remark"] == "ของชิ้นใหญ่ ส่งกระบี่"


def test_เปิดซ้ำไม่ได้สองบรรทัด(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    client.post(f"/sales/carts/{cid}/shipping-charge", json={"matnr": "A534", "fee": "600"}, headers=h)
    r = client.post(f"/sales/carts/{cid}/shipping-charge", json={"matnr": "A761", "fee": "100"}, headers=h)
    lines = [it for it in r.json()["items"] if it["matnr"] in ("A534", "A761")]
    assert len(lines) == 1 and lines[0]["matnr"] == "A761"


def test_เอาออกจากบิลได้(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    client.post(f"/sales/carts/{cid}/shipping-charge", json={"matnr": "A534", "fee": "600"}, headers=h)
    r = client.delete(f"/sales/carts/{cid}/shipping-charge", headers=h)
    assert r.status_code == 200, r.text
    assert not [it for it in r.json()["items"] if it["matnr"] in ("A534", "A761")]
    assert client.get(f"/sales/carts/{cid}/shipping-charge", headers=h).json()["current"] is None


def test_รหัสนอกรายการไม่รับ(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    r = client.post(f"/sales/carts/{cid}/shipping-charge", json={"matnr": "19218579", "fee": "600"}, headers=h)
    assert r.status_code == 422


def test_ลูกค้าเรียกไม่ได้(client):
    """หน้านี้ของพนักงานเท่านั้น — ลูกค้าต้องแตะค่าขนส่งตัวเองไม่ได้"""
    hs = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, hs)
    hc = auth_headers(client, "094-916-4600")
    assert client.get(f"/sales/carts/{cid}/shipping-charge", headers=hc).status_code == 403
    assert client.post(f"/sales/carts/{cid}/shipping-charge",
                       json={"matnr": "A534", "fee": "1"}, headers=hc).status_code == 403


def test_ไม่คิดค่าส่งสองต่อ_และแยกช่องให้ถูก(client):
    """เปิด Mat แล้วกรอกที่อยู่ด้วย ต้องไม่โดนทั้งค่า Mat และค่าส่งตามกฎ Amasty"""
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    goods = float(client.get(f"/sales/carts/{cid}", headers=h).json()["subtotal"])

    client.post(f"/sales/carts/{cid}/shipping-charge", json={"matnr": "A534", "fee": "600"}, headers=h)
    # กรอกปลายทางหลังเปิด Mat — จุดที่เคยเสี่ยงคิดซ้ำ
    client.post(f"/sales/carts/{cid}/delivery/quote", json={"postcode": "80240"}, headers=h)

    t = client.get(f"/sales/carts/{cid}", headers=h).json()
    assert float(t["subtotal"]) == goods                      # ยอดสินค้าไม่มีค่าขนส่งปน
    assert float(t["totals"]["shipping_fee"]) == 600.0        # ค่าขนส่งมาจาก Mat ที่เปิดไว้
    assert float(t["totals"]["grand_total"]) == goods + 600   # รวมครั้งเดียว ไม่ใช่สองต่อ
