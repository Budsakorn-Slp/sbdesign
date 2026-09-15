"""สินค้าตัวโชว์ — รหัส 19 แปลงเป็น 20 แล้วถามสต็อกจาก SAP · มีของโชว์ ไม่มีของซ่อน

ไม่ยิง SAP จริง: สวม client ปลอมเข้าไปที่ product_stock_service เพื่อกำหนดผลลัพธ์เองทีละรหัส
(conftest เคลียร์ SAP_API_KEY ไว้แล้ว ตัวจริงจะตกไปใช้ mock อยู่แล้ว แต่ mock สุ่มจากรหัส
ซึ่งเทสคุมค่าไม่ได้ จึงต้องสวมของตัวเอง)
"""
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.etl import sync_display_items
from app.integrations.sap.material_stock import StockLine
from app.models.catalog import Material, MaterialPrice, ProductStock
from app.services import product_stock_service
from tests.helpers import auth_headers, ensure_seed

MEE = "19000001"  # มีของ -> ต้องโชว์
MOD = "19000002"  # ของหมด -> ต้องซ่อน
NOK = "19000003"  # SAP ไม่รู้จักรหัสตัวโชว์ -> ต้องซ่อน


@pytest.fixture
def parents():
    """สินค้าขายปกติ 3 ตัวสำหรับเทสนี้ — ลบทิ้งทุกครั้งกันค้างข้ามเทส"""
    codes = [MEE, MOD, NOK]
    disp = [sync_display_items.display_matnr(c) for c in codes]
    ensure_seed()
    with SessionLocal() as db:
        _clean(db, codes + disp)
        for i, c in enumerate(codes):
            db.add(Material(matnr=c, sku=c, name_th=f"โซฟาทดสอบ {i}", is_public=True, image_url="x.jpg"))
            db.add(MaterialPrice(matnr=c, tier="standard", price=Decimal("1000.00")))
        db.commit()
    yield codes
    with SessionLocal() as db:
        _clean(db, codes + disp)
        db.commit()


def _clean(db, codes):
    db.execute(delete(MaterialPrice).where(MaterialPrice.matnr.in_(codes)))
    db.execute(delete(Material).where(Material.matnr.in_(codes)))
    db.execute(delete(ProductStock).where(ProductStock.matnr.in_(codes)))


class FakeStock:
    """คืนค่าตามที่เทสสั่ง · รหัสที่ไม่ได้ใส่ไว้ = SAP ไม่รู้จัก (ไม่มี key)"""

    def __init__(self, table):
        self.table = table
        self.asked = []

    def check(self, matnrs, req_date, fresh=False):
        self.asked.extend(matnrs)
        return {m: self.table[m] for m in matnrs if m in self.table}


def run_sync(monkeypatch, table, **kw):
    fake = FakeStock(table)
    monkeypatch.setattr(product_stock_service, "get_material_stock_client", lambda: fake)
    with SessionLocal() as db:
        res = sync_display_items.sync(db, refresh_all=kw.get("refresh_all", True), limit=None, mock=False)
    return fake, res


def in_stock_table(qty_by_code):
    return {c: StockLine(matnr=c, available=q, committed=0, committed_date=None) for c, q in qty_by_code.items()}


# ---------- กติกาการแปลงรหัส ----------


def test_19_becomes_20_keeping_the_tail():
    assert sync_display_items.display_matnr("19248757") == "20248757"
    assert sync_display_items.display_matnr("19000001") == "20000001"


# ---------- การสร้างแถวและธงโชว์/ซ่อน ----------


def test_only_items_with_stock_are_shown(monkeypatch, parents):
    """หัวใจของชุดนี้: มีของ = is_public True · ของหมด/SAP ไม่รู้จัก = False"""
    fake, (asked, shown, hidden) = run_sync(monkeypatch, in_stock_table({"20000001": 4, "20000002": 0}))
    # ถาม SAP ด้วยรหัส 20 เท่านั้น ไม่ใช่ 19
    assert all(m.startswith("20") for m in fake.asked)
    assert (shown, hidden) == (1, 2)
    with SessionLocal() as db:
        rows = {m.matnr: m for m in db.scalars(select(Material).where(Material.matnr.like("200000%"))).all()}
    assert rows["20000001"].is_public is True
    assert rows["20000002"].is_public is False
    assert rows["20000003"].is_public is False  # SAP ไม่รู้จัก


def test_display_row_copies_name_image_and_price(monkeypatch, parents):
    run_sync(monkeypatch, in_stock_table({"20000001": 4}))
    with SessionLocal() as db:
        d = db.get(Material, "20000001")
        price = db.scalar(select(MaterialPrice.price).where(MaterialPrice.matnr == "20000001", MaterialPrice.tier == "standard"))
    assert d.name_th == "โซฟาทดสอบ 0" and d.image_url == "x.jpg"
    assert price == Decimal("1000.00")  # ราคาก๊อปจากตัวปกติ (ยังไม่มีราคาตัวโชว์จริง)
    # สัญญาณการขายของตัวปกติต้องไม่ติดมา ไม่งั้นตัวโชว์จะไปแย่งอันดับหน้า "มาใหม่/ขายดี"
    assert d.is_new is False and d.is_bestseller is False and d.sold_qty == 0


def test_stock_running_out_hides_it_on_the_next_run(monkeypatch, parents):
    """ของขายหมดระหว่างวัน รอบถัดไปต้องซ่อนเอง ไม่ใช่ค้างโชว์อยู่"""
    run_sync(monkeypatch, in_stock_table({"20000001": 2}))
    with SessionLocal() as db:
        assert db.get(Material, "20000001").is_public is True
    run_sync(monkeypatch, in_stock_table({"20000001": 0}))
    with SessionLocal() as db:
        assert db.get(Material, "20000001").is_public is False


def test_second_run_reuses_cache_and_does_not_ask_sap_again(monkeypatch, parents):
    """TTL 1 ชม. — รันซ้ำติดๆ กันต้องไม่ยิง SAP ใหม่ ไม่งั้น job รายชั่วโมงจะถล่ม SAP"""
    run_sync(monkeypatch, in_stock_table({"20000001": 2}))
    fake, _ = run_sync(monkeypatch, in_stock_table({"20000001": 2}), refresh_all=False)
    assert fake.asked == []


# ---------- หน้าเว็บ ----------


def test_display_group_shows_them_but_normal_search_does_not(client, monkeypatch, parents):
    """ตัวโชว์กับตัวปกติเป็นของรุ่นเดียวกัน ถ้าขึ้นในผลค้นหาทั่วไปด้วยลูกค้าจะเห็นซ้ำสองใบ"""
    run_sync(monkeypatch, in_stock_table({"20000001": 4}))

    got = client.get("/materials/search?group=display&limit=100").json()
    assert "20000001" in [i["matnr"] for i in got["items"]]

    normal = client.get("/materials/search?q=โซฟาทดสอบ&limit=100").json()
    codes = [i["matnr"] for i in normal["items"]]
    assert "19000001" in codes and not [c for c in codes if c.startswith("20")]


def test_staff_can_still_find_a_display_code(client, monkeypatch, parents):
    """เซลล์ต้องค้นเจอทุกตัวเสมอ ไว้เช็คของให้ลูกค้าหน้าร้าน แม้ของหมดจนถูกซ่อนจากลูกค้า"""
    run_sync(monkeypatch, in_stock_table({"20000001": 4}))
    h = auth_headers(client, "SA-104", "staff")
    got = client.get("/materials/search?q=20000001&limit=20", headers=h).json()
    assert "20000001" in [i["matnr"] for i in got["items"]]
