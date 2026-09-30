"""STEP 15 — เก็บ log พฤติกรรมผู้ใช้ไว้วิเคราะห์

ของเดิมเก็บอยู่แล้ว 3 อย่าง (ค้นหา · ดูสินค้า · ใส่ตะกร้า) ชุดนี้คุมของที่เพิ่มเข้ามา:
จำนวนคนเข้าเว็บ · หน้าที่เปิด · การกดสินค้า · และการเชื่อม "ค้นแล้วกดอะไรต่อ"
"""
import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.analytics import SearchQuery, UserEvent
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed

MATNR = "10023841"


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)
        db.execute(delete(UserEvent))
        db.execute(delete(SearchQuery))
        db.commit()


def _overview(client, days: int = 30) -> dict:
    r = client.get("/admin/analytics/overview", params={"days": days}, headers=auth_headers(client, "MG-001", "staff"))
    assert r.status_code == 200, r.text
    return r.json()


def test_page_view_is_recorded_with_its_path(client):
    assert client.post("/events", json={"event": "page_view", "path": "/search?q=โซฟา"}).status_code == 202
    with SessionLocal() as db:
        row = db.scalar(select(UserEvent).where(UserEvent.event == "page_view"))
        assert row is not None and row.path == "/search?q=โซฟา"


def test_unknown_event_is_rejected(client):
    assert client.post("/events", json={"event": "ไม่รู้จัก", "path": "/"}).status_code == 422


def test_overview_counts_people_not_page_views(client):
    """คนเดิมเปิดหลายหน้า = 1 คน หลาย page view — ไม่งั้นตัวเลข "คนเข้าเว็บ" จะเฟ้อ"""
    h = auth_headers(client, "094-916-4600")
    for path in ("/", "/search", "/p/10023841"):
        client.post("/events", json={"event": "page_view", "path": path}, headers=h)
    body = _overview(client)
    assert body["page_views"] == 3
    assert body["visitors"] == 1 and body["members"] == 1


def test_overview_lists_top_pages_and_products(client):
    h = auth_headers(client, "094-916-4600")
    client.post("/events", json={"event": "page_view", "path": "/"}, headers=h)
    client.post("/events", json={"event": "page_view", "path": "/"}, headers=h)
    client.post("/events", json={"event": "page_view", "path": "/cart"}, headers=h)
    client.post("/events", json={"event": "click_product", "matnr": MATNR, "payload": {"from": "home"}}, headers=h)
    body = _overview(client)
    assert body["top_pages"][0] == {"key": "/", "count": 2}
    assert body["top_clicked"][0] == {"key": MATNR, "count": 1}
    assert body["product_clicks"] == 1


def test_clicking_a_search_result_links_back_to_the_search_term(client):
    """คำที่ค้นเยอะแต่ไม่มีใครกดเลย = ผลลัพธ์ยังไม่ตรง — ต้องวัดได้"""
    h = auth_headers(client, "094-916-4600")
    client.get("/materials/search", params={"q": "โซฟา"}, headers=h)
    client.post("/events", json={"event": "click_product", "matnr": MATNR, "payload": {"from": "search", "q": "โซฟา"}}, headers=h)
    with SessionLocal() as db:
        row = db.scalar(select(SearchQuery).where(SearchQuery.q == "โซฟา"))
        assert row is not None and row.clicked_matnr == MATNR
    body = _overview(client)
    hit = next(t for t in body["top_searches"] if t["q"] == "โซฟา")
    assert hit["count"] >= 1 and hit["clicks"] == 1


def test_overview_surfaces_searches_that_found_nothing(client):
    client.get("/materials/search", params={"q": "ไม่มีสินค้าแบบนี้แน่นอน"})
    body = _overview(client)
    assert any(z["q"] == "ไม่มีสินค้าแบบนี้แน่นอน" for z in body["zero_result_searches"])


def test_guest_and_member_are_both_counted(client):
    client.post("/events", json={"event": "page_view", "path": "/"})  # guest (anon cookie)
    client.post("/events", json={"event": "page_view", "path": "/"}, headers=auth_headers(client, "094-916-4600"))
    body = _overview(client)
    assert body["members"] == 1 and body["visitors"] >= 1
    assert body["guests"] == body["visitors"] - body["members"]


def test_overview_is_manager_only(client):
    assert client.get("/admin/analytics/overview").status_code in (401, 403)
    assert client.get("/admin/analytics/overview", headers=auth_headers(client, "094-916-4600")).status_code == 403
    assert client.get("/admin/analytics/overview", headers=auth_headers(client, "SA-104", "staff")).status_code == 403
