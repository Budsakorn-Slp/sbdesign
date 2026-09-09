import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.integrations.sap import get_sap_client
from app.models.catalog import StockCheck
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


def test_guest_sees_standard_price_only_customer_sees_member_price(client):
    guest = client.get("/materials/10023841").json()
    assert guest["price"] == "24900.00" and guest["member_price"] is None and guest["price_tier"] == "standard"
    gold = client.get("/materials/10023841", headers=auth_headers(client, "089-234-4471")).json()
    assert gold["price_tier"] == "Gold" and float(gold["price"]) < 24900
    assert gold["discount_percent"] == 24  # compare_at 32,900


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
    r = client.get("/materials/10023841/stock", headers=auth_headers(client, "089-234-4471")).json()
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


def test_only_configured_matnr_prefixes_show_on_web():
    """เว็บโชว์เฉพาะ MATNR ขึ้นต้นตามที่ตั้งไว้ (ตอนนี้ 19 = สินค้าขายปกติ)
    20 ตัวโชว์ · 25 ฝากวางขาย · 27 รวมห้อง · 59 ชุด ยังไม่เปิดขายบนเว็บ"""
    from app.services.catalog_service import is_web_visible

    assert is_web_visible("19248757") and is_web_visible("19205233")
    assert not is_web_visible("25030643")
    assert not is_web_visible("59064091")
    assert not is_web_visible("39019171")
    assert not is_web_visible("")
