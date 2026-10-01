import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.integrations.sap import get_sap_client
from app.models.catalog import ProductStock, Material, StockCache, StockCheck
from app.models.common import utcnow
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _stock_check_count(source: str | None = None) -> int:
    with SessionLocal() as db:
        stmt = select(func.count()).select_from(StockCheck)
        if source:
            stmt = stmt.where(StockCheck.source == source)
        return int(db.scalar(stmt) or 0)


def test_search_by_name_matnr_barcode(client):
    by_name = client.get("/materials/search", params={"q": "โซฟา"}).json()
    assert by_name["total"] >= 3
    assert all("โซฟา" in it["name_th"] for it in by_name["items"])
    by_mat = client.get("/materials/search", params={"q": "10023841"}).json()
    assert by_mat["total"] == 1 and by_mat["items"][0]["sku"] == "SOF-NRD-3S-GY"
    by_barcode = client.get("/materials/search", params={"q": "8850100442904"}).json()
    assert by_barcode["items"][0]["matnr"] == "10044290"
    by_cat = client.get("/materials/search", params={"category": "sofa"}).json()
    assert by_cat["total"] >= 4  # รวมลูกหมวด sofa-3 / sofa-l / recliner


def test_everyone_sees_the_same_price(client):
    """ลูกค้าไม่มีระดับสมาชิกแล้ว — guest / ลูกค้า / พนักงาน เห็นราคาเดียวกันหมด"""
    guest = client.get("/materials/10023841").json()
    assert guest["price"] == "24900.00" and guest["price_tier"] == "standard"
    assert guest["discount_percent"] == 24  # compare_at 32,900
    member = client.get("/materials/10023841", headers=auth_headers(client, "094-916-4600")).json()
    staff = client.get("/materials/10023841", headers=auth_headers(client, "SA-104", "staff")).json()
    assert member["price"] == staff["price"] == guest["price"]
    assert member["price_tier"] == staff["price_tier"] == "standard"


def test_sales_stock_check_returns_all_plants_with_atp_and_logs(client):
    before = _stock_check_count("sap")
    r = client.get("/materials/10023841/stock", headers=auth_headers(client, "SA-104", "staff"))
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "sap" and body["stale"] is False
    assert len(body["rows"]) == 4
    codes = {row["plant_code"] for row in body["rows"]}
    assert codes == {"BKN", "BPL", "RIT", "CNX"}
    bpl = next(row for row in body["rows"] if row["plant_code"] == "BPL")
    assert bpl["atp_date"] is not None and bpl["available"] == 18
    assert _stock_check_count("sap") == before + 4


def test_customer_cannot_see_cross_branch_stock(client):
    r = client.get("/materials/10023841/stock", headers=auth_headers(client, "094-916-4600")).json()
    assert r["rows"] == [] and r["available"] is True
    r2 = client.get("/materials/10023841/stock", params={"plant": "BKN"}).json()
    assert [row["plant_code"] for row in r2["rows"]] == ["BKN"]


def test_stock_fallback_to_cache_when_sap_down(client):
    sap = get_sap_client()
    h = auth_headers(client, "SA-104", "staff")
    client.get("/materials/10031002/stock", headers=h)  # เติม cache ก่อน
    before = _stock_check_count("cache")
    sap.fail_next(2)  # ล้มทั้ง call แรกและ retry
    r = client.get("/materials/10031002/stock", headers=h).json()
    assert r["source"] == "cache" and r["stale"] is True
    assert len(r["rows"]) == 4 and r["error"]
    assert _stock_check_count("cache") == before + 4


def test_unknown_material_404(client):
    assert client.get("/materials/99999999").status_code == 404
    assert client.get("/materials/99999999/stock").status_code == 404


def test_home_payload(client):
    body = client.get("/home").json()
    assert len(body["hero_slides"]) == 5 and len(body["promo_cards"]) == 4
    # ต้นไม้หมวดตัดกิ่งที่ยังไม่มีสินค้าให้ลูกค้าเห็นออก — seed มีหมวดลูกใต้ ห้องนอน 6 หมวด
    # แต่มีของจริงแค่ 3 (เตียงนอน/ตู้เสื้อผ้า/โต๊ะเครื่องแป้ง) อีก 3 จึงไม่โผล่ในตัวกรอง
    kids = body["categories"][0]["children"]
    assert body["categories"][0]["id"] == "bedroom"
    assert [c["id"] for c in kids] == ["bed", "wardrobe", "dresser"]
    assert len(body["new_products"]) >= 3 and len(body["deals"]) >= 3


def _set_availability(matnr: str, ready: int, later: int = 0, mto: bool = False) -> None:
    with SessionLocal() as db:
        row = db.get(ProductStock, matnr) or ProductStock(matnr=matnr)
        row.ready_qty, row.later_qty, row.sap_known, row.fetched_at = ready, later, True, utcnow()
        row.made_to_order = mto
        db.add(row)
        db.commit()


def test_made_to_order_is_not_hidden_even_with_no_stock(client):
    """สินค้าสั่งทำ (SAP ตอบ 999 = ไม่คุมสต็อก) มี ready 0 เหมือนของหมด แต่สั่งได้เสมอ

    ถ้าไม่แยกธงไว้ ตัวกรอง "ซ่อนของหมด" จะกลืนสินค้าสั่งทำหายไปทั้งหมวด
    """
    matnr = "10023841"
    _set_availability(matnr, ready=0, later=0, mto=True)

    browse = client.get("/materials/search", params={"category": "sofa", "limit": 100}).json()
    hit = next(it for it in browse["items"] if it["matnr"] == matnr)
    assert hit["stock"]["made_to_order"] is True and hit["stock"]["ready_qty"] == 0

    # ตัดธงออก = กลายเป็นหมดสนิท ต้องหายจากหน้ารายการ
    _set_availability(matnr, ready=0, later=0, mto=False)
    after = client.get("/materials/search", params={"category": "sofa", "limit": 100}).json()
    assert matnr not in [it["matnr"] for it in after["items"]]


def test_preorder_stays_visible_when_more_stock_is_coming(client):
    """ของหมดตอนนี้แต่มีรอบเข้า = พรีออเดอร์ ยังสั่งได้ ต้องไม่ถูกซ่อนเหมือนของหมดสนิท"""
    matnr = "10023841"
    _set_availability(matnr, ready=0, later=5)

    browse = client.get("/materials/search", params={"category": "sofa", "limit": 100}).json()
    hit = next(it for it in browse["items"] if it["matnr"] == matnr)
    assert hit["stock"]["ready_qty"] == 0 and hit["stock"]["later_qty"] == 5

    # หมดสนิท (ไม่มีรอบเข้า) ถึงจะหายไปจากหน้ารายการ
    _set_availability(matnr, ready=0, later=0)
    browse2 = client.get("/materials/search", params={"category": "sofa", "limit": 100}).json()
    assert matnr not in [it["matnr"] for it in browse2["items"]]


def test_sold_out_hidden_from_browsing_but_found_by_product_code(client):
    """ของหมดไม่โผล่ตอนเดินดูทั่วไป — แต่พิมพ์รหัสมาตรงๆ ต้องเจอ จะได้รู้ว่า "มีรุ่นนี้แต่หมด"""
    matnr = "10023841"
    _set_availability(matnr, ready=0)

    # เดินดูตามหมวด: ต้องไม่เห็น
    browse = client.get("/materials/search", params={"category": "sofa", "limit": 100}).json()
    assert matnr not in [it["matnr"] for it in browse["items"]]

    # ค้นด้วยรหัสสินค้า: ต้องเจอ พร้อมบอกว่าของหมด (ready_qty = 0) ให้หน้าเว็บทำการ์ดทึบ
    by_code = client.get("/materials/search", params={"q": matnr}).json()
    assert by_code["total"] == 1
    assert by_code["items"][0]["stock"]["ready_qty"] == 0

    staff = client.get("/materials/search", params={"q": matnr}, headers=auth_headers(client, "SA-104", "staff")).json()
    assert staff["total"] == 1


def test_in_stock_material_shows_quantity_and_stays_in_browsing(client):
    matnr = "10023841"
    _set_availability(matnr, ready=7)

    browse = client.get("/materials/search", params={"category": "sofa", "limit": 100}).json()
    hit = next(it for it in browse["items"] if it["matnr"] == matnr)
    assert hit["stock"]["ready_qty"] == 7


def test_customer_still_sees_material_never_checked_with_sap(client):
    """ยังไม่เคยเช็คกับ SAP เลย (ไม่มีแถวใน availability_cache) ถือว่ายังไม่รู้ ไม่ซ่อนจากลูกค้า"""
    matnr = "10099999"
    with SessionLocal() as db:
        if not db.get(Material, matnr):
            db.add(Material(matnr=matnr, sku="TEST-NO-STOCK-ROW", name_th="ทดสอบยังไม่เคยเช็คสต็อก", is_public=True))
            db.commit()
        assert db.get(ProductStock, matnr) is None

    guest = client.get("/materials/search", params={"q": matnr}).json()
    assert guest["total"] == 1
    assert guest["items"][0]["stock"] is None  # ไม่รู้ = ไม่ต้องโชว์ตัวเลขอะไร


def test_only_configured_matnr_prefixes_show_on_web():
    """เว็บโชว์เฉพาะ MATNR ขึ้นต้นตามที่ตั้งไว้ (ตอนนี้ 19 ขายปกติ · 20 ตัวโชว์ · 25 ฝากวางขาย)
    27 รวมห้อง · 59 ชุด ยังไม่เปิดขายบนเว็บ"""
    from app.services.catalog_service import is_web_visible

    assert is_web_visible("19248757") and is_web_visible("19205233")
    assert is_web_visible("20030643") and is_web_visible("25030643")
    assert not is_web_visible("59064091")
    assert not is_web_visible("39019171")
    assert not is_web_visible("27019171")
    assert not is_web_visible("")


# ---------- คุณภาพการค้นหา (STEP 13.2) ----------

def _matnrs(body: dict) -> set[str]:
    return {it["matnr"] for it in body["items"]}


def test_search_splits_thai_words_that_are_written_together(client):
    """ภาษาไทยไม่เว้นวรรค — "ที่นอนสปริง" ไม่มีอยู่ในชื่อสินค้าตัวไหนเลย

    ของจริงชื่อ "ที่นอนพ็อกเก็ตสปริง 6 ฟุต" ค้นด้วย LIKE ทั้งก้อนจะได้ศูนย์
    ต้องตัดเป็น "ที่นอน" + "สปริง" ก่อนถึงจะเจอ
    """
    body = client.get("/materials/search", params={"q": "ที่นอนสปริง"}).json()
    assert {"10044290", "10044310"} <= _matnrs(body)


def test_search_understands_english_and_thai_words_for_the_same_thing(client):
    """พิมพ์ sofa ต้องได้โซฟา — ชื่อสินค้าเป็นภาษาไทยล้วน คนต่างชาติ/คนพิมพ์อังกฤษก็ต้องเจอ"""
    en = client.get("/materials/search", params={"q": "sofa"}).json()
    th = client.get("/materials/search", params={"q": "โซฟา"}).json()
    assert _matnrs(th) <= _matnrs(en) and th["total"] >= 3


def test_short_category_word_returns_everything_of_that_kind(client):
    """พิมพ์คำเดียวสั้นๆ ต้องได้ครบทุกตัวของประเภทนั้น ไม่ใช่โดนตีความจนเหลือหยิบมือ"""
    body = client.get("/materials/search", params={"q": "โต๊ะ"}).json()
    assert {"10052277", "10052300", "10071001", "10046220"} <= _matnrs(body)


def test_search_finds_material_by_partial_and_zero_padded_code(client):
    """SAP เก็บ MATNR 18 หลักเติมศูนย์ ใบเสร็จใช้แบบตัดศูนย์ เซลล์ก๊อปมาได้ทั้งสองแบบ"""
    padded = client.get("/materials/search", params={"q": "000000000010023841"}).json()
    assert padded["items"][0]["matnr"] == "10023841"
    partial = client.get("/materials/search", params={"q": "023841"}).json()
    assert partial["items"][0]["matnr"] == "10023841"


def test_exact_code_outranks_everything_else(client):
    """รหัสตรงเป๊ะต้องมาที่หนึ่งเสมอ ต่อให้ตัวอื่นมีรหัสนี้อยู่ข้างในหรือขายดีกว่า"""
    body = client.get("/materials/search", params={"q": "10023841"}).json()
    assert body["items"][0]["matnr"] == "10023841"


def test_smart_mode_turns_a_budget_phrase_into_a_price_filter(client):
    """"ไม่เกิน 7000" ต้องกลายเป็นตัวกรองราคา ไม่ใช่คำที่เอาไปไล่จับตัวอักษร"""
    body = client.get("/materials/search", params={"q": "โต๊ะกลาง ไม่เกิน 7000", "mode": "smart"}).json()
    assert body["understood"] and body["understood"]["max_price"] == 7000
    assert "10052300" in _matnrs(body)      # LOFT 6,290
    assert "10052277" not in _matnrs(body)  # OAK 120 ราคา 8,900 เกินงบ


def test_keyword_mode_never_interprets(client):
    """โหมดจับคำต้องไม่แปลงประโยคเป็นตัวกรอง — เซลล์ที่อยากได้ผลแบบเดิมเป๊ะๆ ใช้โหมดนี้"""
    body = client.get("/materials/search", params={"q": "โต๊ะกลาง ไม่เกิน 7000", "mode": "keyword"}).json()
    assert body["understood"] is None


def test_search_recovers_from_a_misspelled_model_name(client):
    """พิมพ์ชื่อรุ่นผิดตัวเดียวแล้วเจอศูนย์คือพังที่สุด — เดาคำให้แล้วบอกว่าเดาเป็นอะไร"""
    body = client.get("/materials/search", params={"q": "nordik"}).json()
    assert body["total"] >= 1 and body["corrected"] == "nordic"


def test_suggest_returns_matching_products_without_logging_a_search(client):
    from app.models.analytics import SearchQuery

    with SessionLocal() as db:
        before = int(db.scalar(select(func.count()).select_from(SearchQuery)) or 0)
    body = client.get("/materials/suggest", params={"q": "โซฟา"}).json()
    assert len(body["items"]) >= 1
    assert all("โซฟา" in it["name_th"] or "โซฟา" in (it["category_name"] or "") for it in body["items"])
    with SessionLocal() as db:
        assert int(db.scalar(select(func.count()).select_from(SearchQuery)) or 0) == before


# ---------- แคชหน้าแรก ----------
def test_หน้าแรกใช้แคชแต่ของเปลี่ยนแล้วต้องสดเอง(client):
    """หน้าแรกประกอบจาก 8 ส่วน ~0.9 วิ ถ้าคิดใหม่ทุก request ทุกคนต้องรอทุกครั้ง

    แคชได้เพราะหน้าแรกไม่ขึ้นกับว่าใครเปิด — ถ้าวันหลังมีราคาเฉพาะกลุ่ม เทสนี้จะยังผ่าน
    แต่พฤติกรรมจะผิด ต้องกลับมาเลิกแคชรวมเอง (ดูหมายเหตุที่ catalog.home)
    """
    from app.api import catalog as cat
    from app.db.session import SessionLocal
    from app.models.catalog import Material
    from app.models.common import utcnow

    cat._home_cache.update(key=None, at=0.0, data=None)
    first = client.get("/home")
    assert first.status_code == 200
    assert cat._home_cache["data"] is not None, "ครั้งแรกต้องเก็บผลไว้"

    # ครั้งที่สองต้องได้ของจากแคชตัวเดิม ไม่ใช่คำนวณใหม่
    cached = cat._home_cache["data"]
    assert client.get("/home").json()["categories"] == first.json()["categories"]
    assert cat._home_cache["data"] is cached

    # ETL แตะสินค้า -> ลายเซ็นข้อมูลเปลี่ยน -> ต้องคิดใหม่ ไม่ต้องรอหมดอายุ
    with SessionLocal() as db:
        m = db.query(Material).first()
        m.synced_at = utcnow()
        db.commit()
    assert client.get("/home").status_code == 200
    assert cat._home_cache["data"] is not cached, "ข้อมูลเปลี่ยนแล้วต้องไม่ใช้ของเก่า"
