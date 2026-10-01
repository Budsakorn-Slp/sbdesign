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


def test_รหัสค่าบริการที่เลือกได้มาจากไฟล์กฎ(client):
    """เพิ่มรหัสใหม่ในไฟล์กฎแล้วต้องโผล่ในช่องเลือกเอง ไม่ต้องไปแก้หน้าเว็บตาม"""
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    r = client.get(f"/sales/carts/{cid}/shipping-charge", headers=h)
    assert r.status_code == 200, r.text
    codes = [o["matnr"] for o in r.json()["options"]]
    assert codes == ["A534", "A761", "A776"]          # tier เท่านั้น เรียงตามไฟล์
    assert "A533" not in codes                         # extra เปิดจากปุ่มเช็คค่าส่งพิเศษ ไม่ใช่ช่องนี้
    assert all(o["name"] for o in r.json()["options"])


def test_เปิดA776ได้และถูกนับเป็นบรรทัดค่าบริการไม่ใช่สินค้า(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    before = client.get(f"/sales/carts/{cid}", headers=h).json()["subtotal"]
    r = client.post(f"/sales/carts/{cid}/shipping-charge",
                    json={"matnr": "A776", "fee": "100", "remark": "ตกลงกับลูกค้าแล้ว"}, headers=h)
    assert r.status_code == 200, r.text
    line = next(i for i in r.json()["items"] if i["matnr"] == "A776")
    assert line["is_charge"] is True and line["charge_role"] == "tier"
    assert line["name"] == "ค่าบริการขนส่งพิเศษ-ออฟไลน์ #2"
    # ค่าบริการต้องไม่ไปโป่งยอดสินค้า ไม่งั้นบิลข้ามเทียร์เพราะค่าขนส่งของตัวเอง
    assert r.json()["subtotal"] == before
    # tier มีได้บรรทัดเดียว — เปลี่ยนไป A761 ต้องทับบรรทัดเดิม ไม่ใช่เพิ่มใบใหม่
    r2 = client.post(f"/sales/carts/{cid}/shipping-charge", json={"matnr": "A761", "fee": "100"}, headers=h)
    codes = [i["matnr"] for i in r2.json()["items"] if i["is_charge"]]
    assert codes == ["A761"]


def test_บล็อกค่าบริการแยกตามบทบาท(client):
    """หน้าเว็บวาดจากลิสต์นี้ ไม่ได้รู้จักรหัสเอง

    ตอนนี้เปิดใช้แค่ tier — flat (ค่าเหมา) กับ pack (ค่าแพ็ค) ทำโครงไว้แต่ปิดไว้ก่อน
    รอเงื่อนไขจากทีมขาย · extra ไม่โผล่เพราะเปิดจากเมนูจัดคิวส่ง ไม่ใช่กล่องนี้
    """
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    r = client.get(f"/sales/carts/{cid}/shipping-charge", headers=h).json()
    blocks = {b["role"]: b for b in r["roles"]}
    assert list(blocks) == ["tier"]
    assert [o["matnr"] for o in blocks["tier"]["options"]] == ["A534", "A761", "A776"]
    assert all(b["label"] for b in r["roles"])


def test_บทบาทที่ปิดไว้ไม่โผล่บนหน้าจอแต่โครงยังอยู่ครบ(client):
    """ปิดไว้ = ซ่อนจากกล่องเลือกเท่านั้น · เปลี่ยน enabled เป็น true ในไฟล์กฎแล้วใช้ได้ทันที"""
    from app.services import staff_shipping_service as svc

    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    shown = {b["role"] for b in client.get(f"/sales/carts/{cid}/shipping-charge", headers=h).json()["roles"]}
    assert {"flat", "pack"}.isdisjoint(shown)
    # กฎ ตัวเลข และการแยกบรรทัดยังอยู่ครบ ไม่ได้ถูกลบทิ้ง
    assert [o["matnr"] for o in svc.options("flat")] == ["A052"]
    assert [o["matnr"] for o in svc.options("pack")] == ["A617"]
    assert svc.options("flat")[0]["default_fee"] == "600"
    assert svc.options("pack")[0]["default_fee"] == "100"
    assert {"flat", "pack"} <= set(svc.known_roles())


def test_ค่าเหมากับค่าแพ็คบวกกับค่าตามยอดบิลได้ไม่ทับกัน(client):
    """เคสจริงในตาราง: ตัวโชว์ส่งต่างจังหวัด = A052 + A761 (+ A533 จากเมนูจัดคิวส่ง)

    ถ้า role ไหนไปทับ role อื่น บิลจะหายไปก้อนหนึ่งเงียบๆ ซึ่งจับได้ตอนลูกค้าทักแล้ว
    """
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    before = client.get(f"/sales/carts/{cid}", headers=h).json()["subtotal"]
    for matnr, fee in (("A761", "100"), ("A052", "600"), ("A617", "500")):
        r = client.post(f"/sales/carts/{cid}/shipping-charge", json={"matnr": matnr, "fee": fee}, headers=h)
        assert r.status_code == 200, r.text
    cart = r.json()
    charges = {i["matnr"]: i for i in cart["items"] if i["is_charge"]}
    assert set(charges) == {"A761", "A052", "A617"}
    assert charges["A052"]["charge_role"] == "flat"
    assert charges["A617"]["charge_role"] == "pack"
    assert cart["subtotal"] == before          # ค่าบริการไม่โป่งยอดสินค้า

    # ลบทีละบทบาท ต้องไม่ลากตัวอื่นไปด้วย
    r = client.request("DELETE", f"/sales/carts/{cid}/shipping-charge?role=pack", headers=h)
    assert r.status_code == 200, r.text
    assert {i["matnr"] for i in r.json()["items"] if i["is_charge"]} == {"A761", "A052"}


def test_บทบาทมั่วต้องไม่ผ่าน(client):
    h = auth_headers(client, "SA-104", "staff")
    cid = _cart_with(client, h)
    r = client.request("DELETE", f"/sales/carts/{cid}/shipping-charge?role=ไม่มีจริง", headers=h)
    assert r.status_code == 422, r.text


# ---------- ตรวจกฎทั้งตาราง "เงื่อนไขค่าส่ง 1" (MAT19) ทีละขอบ ----------
# ทดสอบตรงที่ฟังก์ชันคิดเทียร์ ไม่ต้องสร้างตะกร้าทุกบรรทัด — เช็คได้ครบทุกขอบในเทสเดียว
# ขอบเขตคือจุดที่พลาดง่ายที่สุด (109,999 กับ 110,000 คนละราคา) และเป็นเงินของลูกค้าจริง
@pytest.mark.parametrize("subtotal,matnr,fee", [
    ("0", "A534", 600),            # บิลเปล่า
    ("14999.99", "A534", 600),     # ขอบบนของชั้นแรก
    ("15000", "A761", 100),        # ขึ้นชั้นสอง
    ("109999.99", "A761", 100),
    ("110000", "A761", 200),
    ("209999.99", "A761", 200),
    ("210000", "A761", 300),
    ("309999.99", "A761", 300),
    ("310000", "A761", 400),
    ("409999.99", "A761", 400),
    ("410000", "A761", 500),
    ("5000000", "A761", 500),      # เพดาน — แพงแค่ไหนก็ไม่เกิน 500
])
def test_เทียร์ตรงตามตารางทุกขอบ(subtotal, matnr, fee):
    from decimal import Decimal

    from app.services import staff_shipping_service as svc

    t = svc._tier_for(Decimal(subtotal))
    assert (t["matnr"], Decimal(str(t["fee"]))) == (matnr, Decimal(fee)), f"ยอด {subtotal} คิดผิด"


def test_ปริมณฑลไม่มีค่าส่งพื้นที่ห่างไกล():
    """ตาราง: กรุงเทพฯ/นนทบุรี/ปทุมธานี/สมุทรปราการ/สมุทรสาคร ใช้เรทกรุงเทพ ไม่บวก A533"""
    from app.services import staff_shipping_service as svc

    for pv in ("กรุงเทพมหานคร", "นนทบุรี", "ปทุมธานี", "สมุทรปราการ", "สมุทรสาคร"):
        got = svc.district_fee(pv, "เมือง")
        assert got["fee"] == 0, f"{pv} ไม่ควรมีค่าส่งพื้นที่ห่างไกล (ได้ {got['fee']})"


def test_ต่างจังหวัดบวกA533ตามอำเภอ():
    """ตาราง: MAT19 ต่างจังหวัด = เทียร์เดิม + A533 ตามจังหวัด/อำเภอ"""
    from app.services import staff_shipping_service as svc

    # อำเภอเมืองของจังหวัดใหญ่หลายที่ค่าส่งเป็น 0 อยู่แล้ว — ต้องหยิบอำเภอที่มีค่าส่งจริงมาทดสอบ
    assert svc.district_fee("เชียงใหม่", "จอมทอง")["fee"] == 396
    assert svc.district_fee("เชียงใหม่", "อ.จอมทอง")["fee"] == 396   # ใส่ "อ." มาด้วยก็ต้องเจอ
    # เกาะ/ชายแดนใต้ค่าส่ง 10,000 เป็นของจริง ไม่ใช่ค่าพัง (ยืนยันกับทีมแล้ว)
    assert svc.district_fee("กระบี่", "เกาะลันตา")["fee"] == 10000

    # อำเภอที่สะกดไม่ตรง/ไม่มีในตาราง ต้องบอกว่าให้คนตรวจ ไม่ใช่เดาเป็น 0 แล้วส่งฟรี
    miss = svc.district_fee("เชียงใหม่", "อำเภอที่ไม่มีจริง")
    assert miss["in_table"] and not miss["found"]
