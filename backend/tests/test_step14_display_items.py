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


def run_sync(monkeypatch, table, *, zd06=None, **kw):
    """zd06 = รหัสที่มีส่วนลดตัวโชว์ใน SAP · None = ทุกตัวที่ถูกถามสต็อกถือว่ามี

    ต้องแทน snapshot ราคาเสมอ ไม่งั้นเทสจะไปอ่านไฟล์จริงบนเครื่อง dev
    ซึ่งไม่มีรหัสสมมุติของเทสอยู่ ทำให้ทุกตัวถูกซ่อนหมด
    """
    fake = FakeStock(table)
    monkeypatch.setattr(product_stock_service, "get_material_stock_client", lambda: fake)
    codes = table.keys() if zd06 is None else zd06
    monkeypatch.setattr(sync_display_items, "load_price_snapshot",
                        lambda: {c: {"sellable": True} for c in codes})
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
    # ชื่อต้องบอกว่าเป็นตัวโชว์ เพราะชื่อคือตัวเดียวที่ติดไปถึงตะกร้า/ใบเสนอราคา
    # "ขายตามสภาพ" ต้องอยู่ในชื่อ ไม่ใช่ซ่อนในหน้ารายละเอียด — ลูกค้าต้องเห็นตั้งแต่ในผลค้นหา
    assert d.name_th == "โซฟาทดสอบ 0 (สินค้าตัวโชว์ ขายตามสภาพ)" and d.image_url == "x.jpg"
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


def test_card_is_flagged_as_a_display_item(client, monkeypatch, parents):
    """หน้าเว็บต้องรู้จากธง ไม่ใช่ไปเดาเลขนำหน้ารหัสเอง"""
    run_sync(monkeypatch, in_stock_table({"20000001": 4}))
    got = client.get("/materials/search?group=display&limit=100").json()
    card = next(i for i in got["items"] if i["matnr"] == "20000001")
    assert card["is_display"] is True
    normal = client.get("/materials/search?q=โซฟาทดสอบ&limit=100").json()
    assert all(i["is_display"] is False for i in normal["items"])


def test_staff_can_still_find_a_display_code(client, monkeypatch, parents):
    """เซลล์ต้องค้นเจอทุกตัวเสมอ ไว้เช็คของให้ลูกค้าหน้าร้าน แม้ของหมดจนถูกซ่อนจากลูกค้า"""
    run_sync(monkeypatch, in_stock_table({"20000001": 4}))
    h = auth_headers(client, "SA-104", "staff")
    got = client.get("/materials/search?q=20000001&limit=20", headers=h).json()
    assert "20000001" in [i["matnr"] for i in got["items"]]


def test_มีของแต่ไม่มีส่วนลดตัวโชว์ต้องซ่อน(monkeypatch, parents):
    """กติกาใหม่: ขึ้นเว็บได้ต้อง "มีของ" และ "มี ZD06" ครบทั้งสองอย่าง

    ของที่ตั้งโชว์อยู่หน้าร้านแต่ยังไม่ตั้งส่วนลดใน SAP ถือว่ายังไม่พร้อมขาย
    """
    _, (_, shown, hidden) = run_sync(
        monkeypatch, in_stock_table({"20000001": 4, "20000002": 4}), zd06=["20000001"])
    assert (shown, hidden) == (1, 2)
    with SessionLocal() as db:
        rows = {m.matnr: m for m in db.scalars(select(Material).where(Material.matnr.like("200000%"))).all()}
    assert rows["20000001"].is_public is True     # มีของ + มี ZD06
    assert rows["20000002"].is_public is False    # มีของ แต่ไม่มี ZD06


def test_ยังไม่เคยรันงานราคาต้องไม่เผลอเปิดทั้งชุด(monkeypatch, parents):
    """ไม่มี snapshot = ไม่รู้ว่าตัวไหนมีส่วนลด ต้องซ่อนไว้ก่อน ไม่ใช่เปิดหมด"""
    _, (_, shown, hidden) = run_sync(monkeypatch, in_stock_table({"20000001": 4}), zd06=[])
    assert shown == 0 and hidden == 3


def test_ราคาตัวโชว์มาจากsnapshotไม่ใช่ก๊อปราคาตัวปกติ(monkeypatch, parents):
    """ราคาตัวปกติที่เก็บไว้คือราคาหลังลดของตัวปกติ ซึ่งคนละตัวกับส่วนลดตัวโชว์"""
    fake = FakeStock(in_stock_table({"20000001": 4}))
    monkeypatch.setattr(product_stock_service, "get_material_stock_client", lambda: fake)
    monkeypatch.setattr(sync_display_items, "load_price_snapshot", lambda: {
        "20000001": {"sellable": True, "list": "3200.00", "net": "2240.00"}})
    with SessionLocal() as db:
        sync_display_items.sync(db, refresh_all=True, limit=None, mock=False)
    with SessionLocal() as db:
        got = {p.tier: p.price for p in db.scalars(
            select(MaterialPrice).where(MaterialPrice.matnr == "20000001"))}
    assert got["standard"] == Decimal("2240.00")      # ราคาป้าย 3,200 ลบ ZD06 30%
    assert got["compare_at"] == Decimal("3200.00")


def test_หมวดตัวโชว์กรองเหมือนกันทั้งลูกค้าและพนักงาน(client, monkeypatch, parents):
    """เปิดดูทั้งหมวด = เห็นเฉพาะที่พร้อมขาย · ค้นหา = พนักงานเจอทุกตัวรวมที่ซ่อน

    เหตุผล: หมวดตัวโชว์มี 3,400 ตัว ส่วนใหญ่ยังไม่มีส่วนลดให้ขาย
    โหลดมาทั้งหมดทำให้หน้าพนักงานช้าโดยไม่ได้อะไร
    """
    from tests.helpers import auth_headers

    run_sync(monkeypatch, in_stock_table({"20000001": 4, "20000002": 4}), zd06=["20000001"])
    hs = auth_headers(client, "SA-104", "staff")

    def codes(params, headers=None):
        r = client.get("/materials/search", params=params, headers=headers or {})
        assert r.status_code == 200, r.text
        return {i["matnr"] for i in r.json()["items"]}

    # เปิดดูหมวด — ทั้งลูกค้าและพนักงานเห็นเฉพาะตัวที่พร้อมขาย
    assert "20000002" not in codes({"group": "display", "limit": 100})
    assert "20000002" not in codes({"group": "display", "limit": 100}, hs)
    assert "20000001" in codes({"group": "display", "limit": 100}, hs)

    # ค้นหาด้วยรหัส — พนักงานต้องเจอตัวที่ซ่อน ไม่งั้นเช็คของให้ลูกค้าหน้าร้านไม่ได้
    assert "20000002" in codes({"q": "20000002", "limit": 100}, hs)
