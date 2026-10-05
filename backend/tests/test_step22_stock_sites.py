"""สาขาที่มีของ — SAP เพิ่งเพิ่มฟิลด์ชื่อสาขา (NAME) ใน STOCK_ON_SITES

สินค้าตัวโชว์มีของชิ้นเดียวต่อสาขา ลูกค้าต้องรู้ว่าไปดูของจริงได้ที่ไหน
ไม่งั้นขับรถไปแล้วไม่เจอของ
"""
from datetime import date

import pytest

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
    c = HttpMaterialStockClient.__new__(HttpMaterialStockClient)
    c._post = lambda body, fresh: payload
    line = c.check(["20000158"], date(2026, 10, 5))["20000158"]
    assert line.available == 11
    # เก็บเฉพาะสาขาที่มีของ (9000 เป็น 0 จึงตัดออก) เรียงมากไปน้อย
    assert [(s.plant_code, s.name, s.available) for s in line.sites] == [("1000", "", 7), ("S318", "DS-พระราม 2", 1)]
