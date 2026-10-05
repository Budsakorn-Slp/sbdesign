"""สาขาที่มีของ — SAP เพิ่งเพิ่มฟิลด์ชื่อสาขา (NAME) ใน STOCK_ON_SITES

สินค้าตัวโชว์มีของชิ้นเดียวต่อสาขา ลูกค้าต้องรู้ว่าไปดูของจริงได้ที่ไหน
ไม่งั้นขับรถไปแล้วไม่เจอของ
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Material, ProductStockSite
from app.models.common import utcnow
from app.seed import seed_catalog
from app.services import product_stock_service
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)
    yield
    # ฐานเทสใช้ร่วมกันทั้ง session — ตะกร้าที่เทสนี้เปิดไว้ต้องปิดทิ้ง ไม่งั้นเทสไฟล์หลัง
    # ที่ล็อกอินด้วยสมาชิกคนเดียวกันจะเจอตะกร้าค้างแล้วนับของไม่ตรง
    from app.models.cart import Cart

    with SessionLocal() as db:
        for c in db.scalars(select(Cart).where(Cart.status == "open")).all():
            c.status = "closed"
        db.commit()


SITES = [
    ("1000", "", 7),                      # คลัง — ไม่มีชื่อ
    ("9000", "บริษัท เอสบี ดีไซน์สแควร์ จำ", 61),  # ระดับบริษัท
    ("S108", "SB-บางแค", 2),
    ("S304", "DS-ภูเก็ต", 1),
]


def _with_sites(matnr: str):
    with SessionLocal() as db:
        db.query(ProductStockSite).filter(ProductStockSite.matnr == matnr).delete()
        for code, name, qty in SITES:
            db.add(ProductStockSite(matnr=matnr, plant_code=code, name=name, available_qty=qty, fetched_at=utcnow()))
        db.commit()


def _any_matnr():
    with SessionLocal() as db:
        return db.scalars(__import__("sqlalchemy").select(Material.matnr).where(Material.is_public.is_(True))).first()


def test_หน้าสินค้าบอกว่ามีของที่สาขาไหน(client):
    m = _any_matnr()
    _with_sites(m)
    got = client.get(f"/materials/{m}").json()
    names = [s["name"] for s in got["stock_sites"]]
    assert "SB-บางแค" in names and "DS-ภูเก็ต" in names
    # เรียงจากมีเยอะไปน้อย
    assert [s["qty"] for s in got["stock_sites"]] == sorted((s["qty"] for s in got["stock_sites"]), reverse=True)


def test_คลังกับระดับบริษัทต้องไม่โผล่เป็นสาขา(client):
    """ลูกค้าเดินเข้าคลังไปดูของไม่ได้ · PLANT 9000 ชื่อเป็นชื่อบริษัท ไม่ใช่โชว์รูม"""
    m = _any_matnr()
    _with_sites(m)
    got = client.get(f"/materials/{m}").json()
    codes = [s["plant_code"] for s in got["stock_sites"]]
    assert "1000" not in codes and "9000" not in codes
    assert all(s["name"] for s in got["stock_sites"]), "ไม่ควรมีสาขาชื่อว่าง"


def test_ไม่มีข้อมูลสาขาก็ไม่พัง(client):
    m = _any_matnr()
    with SessionLocal() as db:
        db.query(ProductStockSite).filter(ProductStockSite.matnr == m).delete()
        db.commit()
    assert client.get(f"/materials/{m}").json()["stock_sites"] == []


def test_ของย้ายสาขาแล้วแถวเก่าต้องหายไป(client):
    """upsert ทับอย่างเดียวไม่พอ — สาขาที่ของหมดแล้วจะค้างบอกว่ายังมีของตลอดไป"""
    from app.integrations.sap.material_stock import SiteStock

    m = _any_matnr()
    _with_sites(m)
    with SessionLocal() as db:
        product_stock_service._write_sites(db, m, [SiteStock(plant_code="S304", name="DS-ภูเก็ต", available=3)], utcnow())
        db.commit()
    got = client.get(f"/materials/{m}").json()["stock_sites"]
    assert [(s["plant_code"], s["qty"]) for s in got] == [("S304", 3)]


def test_อ่านชื่อสาขาจากคำตอบ_sap_ได้ถูกต้อง():
    """payload บันทึกจากของจริง — ฟิลด์ NAME เพิ่งถูกเพิ่มเข้ามา"""
    from app.integrations.sap.material_stock import HttpMaterialStockClient

    payload = {"data": {"MESSAGES": [], "STOCK_REQUIREMENTS": [
        {"MATERIAL": "000000000020000158", "AVAILABLE_QTY": 11.0, "AVAILABLE_DATE": "20261005",
         "COMMITTED_QTY": 0.0, "COMMITTED_DATE": ""}], "STOCK_ON_SITES": [
        {"MATERIAL": "000000000020000158", "PLANT": "9000", "NAME": "บริษัท เอสบี  ดีไซนด์สแควร์ จำ", "AVAILABLE_QTY": 0.0},
        {"MATERIAL": "000000000020000158", "PLANT": "S318", "NAME": "DS-พระราม 2", "AVAILABLE_QTY": 1.0},
        {"MATERIAL": "000000000020000158", "PLANT": "1000", "NAME": "", "AVAILABLE_QTY": 7.0},
    ]}}
    # 1000 = S.B. Furniture (บริษัทผลิต) SAP ส่งชื่อว่างมา เราเติมให้เอง
    c = HttpMaterialStockClient.__new__(HttpMaterialStockClient)
    c._post = lambda body, fresh: payload
    line = c.check(["20000158"], date(2026, 10, 5))["20000158"]
    assert line.available == 11
    # เก็บเฉพาะสาขาที่มีของ (9000 เป็น 0 จึงตัดออก) เรียงมากไปน้อย
    assert [(s.plant_code, s.name, s.available) for s in line.sites] == [
        ("1000", "S.B. Furniture", 7), ("S318", "DS-พระราม 2", 1)]


def test_ระดับบริษัทไม่โผล่ให้ลูกค้าถึงจะมีชื่อแล้ว(client):
    """เติมชื่อให้ 1000 แล้วก็ยังต้องไม่อยู่ในรายการ "มีของที่สาขา" — เป็นบริษัทผลิต
    ไม่ใช่หน้าร้านที่ลูกค้าเดินเข้าไปดูของได้"""
    m = _any_matnr()
    with SessionLocal() as db:
        db.query(ProductStockSite).filter(ProductStockSite.matnr == m).delete()
        db.add(ProductStockSite(matnr=m, plant_code="1000", name="S.B. Furniture", available_qty=404, fetched_at=utcnow()))
        db.add(ProductStockSite(matnr=m, plant_code="S319", name="DS-บางแค", available_qty=2, fetched_at=utcnow()))
        db.commit()
    got = client.get(f"/materials/{m}").json()["stock_sites"]
    assert [(x["plant_code"], x["qty"]) for x in got] == [("S319", 2)]


def test_ตัวโชว์ในตะกร้าบอกสาขาที่ไปดูของจริงได้(client):
    """ของตัวโชว์มีชิ้นเดียวต่อสาขาและต้องไปรับเอง — ตะกร้าต้องบอกว่าไปดูที่ไหนได้
    ไม่ใช่ให้ลูกค้ากดหาเองทีหลัง"""
    from sqlalchemy import select

    from app.services import catalog_service

    # สร้างสินค้าตัวโชว์ขึ้นมาเอง — ข้ามเทสเวลาไม่มีข้อมูลเท่ากับไม่ได้ทดสอบอะไรเลย
    # (รหัสขึ้นต้น 20 = กลุ่ม display ซึ่ง pickup_only จะเป็น True)
    display = "20009999"
    with SessionLocal() as db:
        src = db.scalars(select(Material).where(Material.is_public.is_(True))).first()
        if not db.get(Material, display):
            m = Material(matnr=display, sku=f"SKU-{display}", name_th="ตู้โชว์ตัวอย่างหน้าร้าน",
                         is_public=True, synced_at=src.synced_at, brand_id=src.brand_id, category_id=src.category_id)
            db.add(m)
            db.commit()
    assert catalog_service.pickup_only(display)

    with SessionLocal() as db:
        db.query(ProductStockSite).filter(ProductStockSite.matnr == display).delete()
        db.add(ProductStockSite(matnr=display, plant_code="S319", name="DS-บางแค", available_qty=1, fetched_at=utcnow()))
        db.add(ProductStockSite(matnr=display, plant_code="1000", name="S.B. Furniture", available_qty=9, fetched_at=utcnow()))
        db.commit()

    hs = auth_headers(client, "0949164600")
    cart = client.post("/cart/items", json={"matnr": display, "qty": 1}, headers=hs).json()
    line = next(i for i in cart["items"] if i["matnr"] == display)
    assert [(s["plant_code"], s["name"]) for s in line["show_at_sites"]] == [("S319", "DS-บางแค")], \
        "ต้องบอกเฉพาะโชว์รูม ไม่ใช่โรงงาน"


def test_ของทั่วไปไม่ต้องรกด้วยรายชื่อสาขา(client):
    """ของทั่วไปส่งถึงบ้าน รู้ว่าสาขาไหนมีก็ไม่ช่วยอะไร"""
    from sqlalchemy import select

    from app.services import catalog_service

    with SessionLocal() as db:
        normal = db.scalars(
            select(Material.matnr).where(Material.is_public.is_(True), Material.matnr.like("10%"))
        ).first()
    if not normal or catalog_service.pickup_only(normal):
        pytest.skip("ชุดข้อมูลทดสอบไม่มีสินค้าทั่วไป")
    with SessionLocal() as db:   # เทสก่อนหน้าอาจใส่แถวนี้ไว้แล้ว — ล้างก่อนเสมอ
        db.query(ProductStockSite).filter(ProductStockSite.matnr == normal).delete()
        db.add(ProductStockSite(matnr=normal, plant_code="S319", name="DS-บางแค", available_qty=5, fetched_at=utcnow()))
        db.commit()
    hs = auth_headers(client, "0949164600")
    cart = client.post("/cart/items", json={"matnr": normal, "qty": 1}, headers=hs).json()
    line = next(i for i in cart["items"] if i["matnr"] == normal)
    assert line["show_at_sites"] == []


def _display(matnr: str, name: str) -> str:
    """สร้างสินค้าตัวโชว์ (รหัสขึ้นต้น 20 = กลุ่ม display ที่ต้องรับที่สาขา)"""
    with SessionLocal() as db:
        if not db.get(Material, matnr):
            src = db.scalars(select(Material).where(Material.is_public.is_(True))).first()
            db.add(Material(matnr=matnr, sku=f"SKU-{matnr}", name_th=name, is_public=True,
                            synced_at=src.synced_at, brand_id=src.brand_id, category_id=src.category_id))
            db.commit()
    return matnr


def test_เลือกสาขาแล้วเห็นตัวโชว์เฉพาะสาขานั้น(client):
    """ของตัวโชว์ต้องไปดูของจริงที่สาขา เลือกสาขาแล้วจึงควรเหลือเฉพาะที่สาขานั้นมี"""
    a = _display("20008801", "ตู้โชว์ A")
    b = _display("20008802", "ตู้โชว์ B")
    with SessionLocal() as db:
        db.query(ProductStockSite).filter(ProductStockSite.matnr.in_([a, b])).delete(synchronize_session=False)
        db.add(ProductStockSite(matnr=a, plant_code="S319", name="DS-บางแค", available_qty=1, fetched_at=utcnow()))
        db.add(ProductStockSite(matnr=b, plant_code="S304", name="DS-ภูเก็ต", available_qty=1, fetched_at=utcnow()))
        db.commit()
    # ตัวโชว์โผล่เฉพาะตอนขอหมวดนี้ตรงๆ (ไม่งั้นจะไปปนอยู่ในหน้ารวมสินค้าทั่วไป)
    codes = [m["matnr"] for m in client.get(
        "/materials/search", params={"group": "display", "plant": "S319", "limit": 100}).json()["items"]]
    assert a in codes and b not in codes


def test_เลือกสาขาแล้วรายการรวมต้องเท่าเดิมเป๊ะ(client):
    """สาขาใช้เฉพาะตอนเปิดหมวดตัวโชว์ — ของทั่วไปส่งจากคลัง สาขาไม่เกี่ยวกับการเลือกซื้อ
    เคยกรองทั้งเว็บแล้วของหายไปโดยที่ลูกค้าไม่ได้ขอ ซึ่งอธิบายให้คนใช้เข้าใจไม่ได้"""
    plain = client.get("/materials/search", params={"limit": 1}).json()["total"]
    with_plant = client.get("/materials/search", params={"plant": "S319", "limit": 1}).json()["total"]
    assert with_plant == plain, "เลือกสาขาแล้วรายการรวมต้องไม่เปลี่ยน"


def test_สาขาที่เลือกได้ต้องเป็นของจริงจาก_sap(client):
    """ตาราง plants เคยเป็นสาขาสมมติ 4 แห่งจาก seed — ลูกค้าเห็นสาขาที่ไม่มีอยู่จริง"""
    from app.etl.sync_plants import sync

    with SessionLocal() as db:
        db.add(ProductStockSite(matnr="20009998", plant_code="S399", name="DS-ทดสอบ", available_qty=1, fetched_at=utcnow()))
        db.commit()
        res = sync(db)
    assert "S399" in res["added"] or "S399" in res["updated"]
    rows = client.get("/plants").json()
    codes = {p["plant_code"] for p in rows}
    assert "S399" in codes
    assert not (codes & {"BKN", "RIT", "CNX", "BPL"}), "สาขาสมมติต้องถูกลบทิ้ง"
    # โรงงาน/ระดับบริษัทต้องไม่เป็น store ไม่งั้นโผล่ในตัวเลือกของลูกค้า
    # (มีในฐานหรือไม่ขึ้นกับว่าเทสก่อนหน้าใส่ไว้ไหม — ตรวจเฉพาะตัวที่มีจริง)
    assert all(p["type"] == "warehouse" for p in rows if p["plant_code"] in ("1000", "9000"))
    assert all(p["type"] == "store" for p in rows if p["plant_code"].startswith("S"))
