"""โปรโมชั่นขั้นบันไดตามยอดบิล + โปรโมโค้ด

  ยอด ≥ 5,000  -> ลด 10%   (SAVE10)
  ยอด ≥ 10,000 -> ลด 15%   (SAVE15)
  ยอด ≥ 15,000 -> ลด 20%   (SAVE20)
ทั้งสามขั้นเลือกใช้ได้ทีละอัน ห้ามซ้อนกัน · ส่วนโปรโมโค้ดต้องกรอกโค้ดเท่านั้น ไม่โผล่ในลิสต์
"""
from decimal import Decimal

import pytest

from app.db.session import SessionLocal
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _cart(client, h, qty):
    c = client.post("/sales/carts", json={"label": "ทดสอบโปร"}, headers=h).json()
    r = client.post(f"/sales/carts/{c['id']}/items", json={"matnr": "10061050", "qty": qty}, headers=h)
    assert r.status_code == 201, r.text
    return c["id"]


def _eval(client, h, cid):
    r = client.post("/promotions/evaluate", json={"cart_id": cid}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_ขั้นบันไดโผล่ตามยอด(client):
    h = auth_headers(client, "SA-104", "staff")
    # 1,777 x 3 = 5,331 -> เข้าแค่ขั้นแรก
    ok = {o["code"] for o in _eval(client, h, _cart(client, h, 3))["eligible"]}
    assert "SAVE10" in ok and "SAVE15" not in ok and "SAVE20" not in ok

    # 1,777 x 9 = 15,993 -> เข้าครบทั้งสามขั้น ให้พนักงานเลือกเอง
    ok = {o["code"] for o in _eval(client, h, _cart(client, h, 9))["eligible"]}
    assert {"SAVE10", "SAVE15", "SAVE20"} <= ok


def test_ลดตามเปอร์เซ็นต์จริง(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart(client, h, 9)
    d = _eval(client, h, cid)
    # อิงยอดจริงจากการประเมิน ไม่ฮาร์ดโค้ด — ราคาที่คิดขึ้นกับ tier ราคาของลูกค้า
    sub = float(d["totals"]["subtotal"])
    offers = {o["code"]: o for o in d["eligible"]}
    assert float(offers["SAVE10"]["amount"]) == pytest.approx(sub * 0.10, abs=1)
    assert float(offers["SAVE20"]["amount"]) == pytest.approx(sub * 0.20, abs=1)


def test_เลือกได้ทีละขั้นห้ามซ้อน(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart(client, h, 9)
    assert client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=h).status_code == 201
    r = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE10"}, headers=h)
    assert r.status_code == 409, r.text


def test_โปรฯที่ซ้อนได้ก็ยังโดนกันถ้าของเดิมห้ามซ้อน(client):
    """ด่านต้องกันสองทาง — ใส่ตัวห้ามซ้อนไว้ก่อน แล้วตามด้วยตัวซ้อนได้ ต้องไม่ผ่าน"""
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart(client, h, 9)
    client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=h)
    r = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "TESTCODE"}, headers=h)
    assert r.status_code == 409, r.text


def test_TESTCODE_ลด50_ไม่มียอดขั้นต่ำ(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart(client, h, 1)                       # 1,777 — ต่ำกว่าทุกขั้น
    r = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "TESTCODE"}, headers=h)
    assert r.status_code == 201, r.text
    line = next(l for l in r.json()["totals"]["lines"] if "50" in l["amount"])
    assert float(line["amount"]) == 50.0


def test_โค้ดไม่โผล่ในลิสต์(client):
    """คูปองใช้ได้ทางเดียวคือกรอกโค้ด — โชว์ในลิสต์เท่ากับแจกให้ทุกคนเห็น"""
    h = auth_headers(client, "SA-104", "staff")
    d = _eval(client, h, _cart(client, h, 9))
    shown = {o["code"] for o in (*d["eligible"], *d["ineligible"])}
    assert not shown & {"TESTCODE", "SBWELCOME", "SEP10", "STAFF300"}
    assert "SAVE20" in shown          # ส่วนโปรฯ อัตโนมัติต้องโผล่


def test_ONTOP_ใช้ทับโปรโมชั่นได้(client):
    """ON TOP อยู่นอกกลุ่ม tier จึงบวกทับขั้นบันไดได้ — ต่างจาก TESTCODE ที่ห้ามซ้อน"""
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart(client, h, 9)
    r1 = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=h)
    assert r1.status_code == 201, r1.text
    r2 = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "ONTOP"}, headers=h)
    assert r2.status_code == 201, r2.text
    codes = {l["title"] for l in r2.json()["totals"]["lines"]}
    assert len(codes) == 2
    sub = float(client.get(f"/sales/carts/{cid}", headers=h).json()["totals"]["subtotal"])
    assert float(r2.json()["totals"]["discount_total"]) == round(sub * 0.20) + 50


def test_TESTCODE_ห้ามซ้อนกับโปรโมชั่น(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart(client, h, 9)
    client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=h)
    r = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "TESTCODE"}, headers=h)
    assert r.status_code == 409, r.text


def test_ขั้นบันไดยังเลือกได้ทีละขั้น(client):
    """เปลี่ยน stackable เป็น True แล้ว ขั้นบันไดต้องยังกันกันเองด้วย exclusive_group"""
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart(client, h, 9)
    client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=h)
    r = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE10"}, headers=h)
    assert r.status_code == 409 and "ทีละขั้น" in r.json()["detail"]["message"]


def test_โค้ดที่ชนกันต้องบอกมูลค่าของตัวใหม่มาด้วย(client):
    """ลูกค้าต้องเทียบได้ว่าสลับไปใช้ตัวใหม่แล้วคุ้มกว่าไหม ก่อนตัดสินใจทิ้งของเดิม"""
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart(client, h, 9)
    client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=h)
    r = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "TESTCODE"}, headers=h)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "TESTCODE"
    assert Decimal(d["amount"]) == Decimal("50")
    assert d["title"]


def test_มูลค่าที่ส่งมาตอนชนต้องเป็นยอดจริงของโค้ดใหม่ไม่ใช่ศูนย์(client):
    """โปรฯ เปอร์เซ็นต์ต้องส่งยอดที่คำนวณแล้วมา ไม่งั้นลูกค้าเห็น 'ลด 0 บาท' แล้วไม่กล้าสลับ"""
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart(client, h, 9)
    client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE10"}, headers=h)
    r = client.post(f"/cart/{cid}/discounts", json={"kind": "promotion", "promo_code": "SAVE20"}, headers=h)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "SAVE20"
    assert Decimal(d["amount"]) > 0
