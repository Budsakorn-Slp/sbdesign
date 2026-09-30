import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.analytics import BestSeller, OrderHistory, UserEvent
from app.models.common import utcnow
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed, login


@pytest.fixture(autouse=True)
def _seed():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _hs(client, ident="1100440205"):
    return {"Authorization": "Bearer " + login(client, ident)["access_token"]}


def test_view_and_add_to_cart_write_user_events(client):
    hs = _hs(client)
    assert client.get("/materials/10023841", headers=hs).status_code == 200
    assert client.post("/cart/items", json={"matnr": "10023841", "qty": 2, "supply_mode": "ship"}, headers=hs).status_code == 201
    client.get("/materials/search", params={"q": "โซฟา"}, headers=hs)

    with SessionLocal() as db:
        events = {e.event for e in db.scalars(select(UserEvent).where(UserEvent.matnr == "10023841")).all()}
        assert {"view_material", "add_to_cart"} <= events
        assert db.scalar(select(func.count()).select_from(UserEvent).where(UserEvent.event == "search")) >= 1

    recent = client.get("/me/recently-viewed", headers=hs).json()
    assert recent and recent[0]["matnr"] == "10023841"


def test_guest_events_merge_into_account_on_login(client):
    client.cookies.clear()
    client.get("/materials/10031002")  # guest ได้ anon cookie จาก /cart
    client.post("/cart/items", json={"matnr": "10031002", "qty": 1, "supply_mode": "ship"})
    client.get("/materials/10031002")
    assert client.get("/me/recently-viewed").json()[0]["matnr"] == "10031002"

    hs = _hs(client)  # ล็อกอินแล้วของที่ดูไว้ต้องตามมา
    assert "10031002" in [m["matnr"] for m in client.get("/me/recently-viewed", headers=hs).json()]


def test_wishlist_toggle(client):
    hs = _hs(client)
    r = client.post("/me/wishlist/10023841", headers=hs)
    assert r.status_code == 200 and r.json()["in_wishlist"] is True
    assert [m["matnr"] for m in client.get("/me/wishlist", headers=hs).json()] == ["10023841"]
    assert client.post("/me/wishlist/10023841", headers=hs).json()["in_wishlist"] is False
    assert client.get("/me/wishlist", headers=hs).json() == []
    assert client.post("/me/wishlist/NOPE", headers=hs).status_code == 404
    client.cookies.clear()
    assert client.get("/me/wishlist").status_code == 401


def test_order_history_mirrors_sap(client):
    hs = _hs(client)
    orders = client.get("/me/orders", headers=hs).json()
    assert orders and all(o["so_no"] and o["lines"] for o in orders)
    assert orders == sorted(orders, key=lambda o: o["order_date"], reverse=True)
    one = client.get(f"/me/orders/{orders[0]['so_no']}", headers=hs).json()
    assert one["so_no"] == orders[0]["so_no"]
    assert float(one["grand_total"]) == pytest.approx(sum(float(l["line_total"]) for l in one["lines"]))
    # sync ซ้ำไม่สร้างซ้ำ
    before = len(orders)
    assert len(client.get("/me/orders", headers=hs).json()) == before
    # คนอื่นเปิดใบเราไม่ได้
    other = _hs(client, "1100440182")
    assert client.get(f"/me/orders/{orders[0]['so_no']}", headers=other).status_code == 404


def test_daily_job_reranks_best_sellers(client):
    hs = _hs(client)
    client.get("/me/orders", headers=hs)  # ดึงประวัติเข้ามาก่อน job จะได้มียอดขาย
    mg = auth_headers(client, "MG-001", "staff")
    assert client.post("/admin/jobs/daily-stats", headers=hs).status_code == 403
    res = client.post("/admin/jobs/daily-stats", params={"days": 180}, headers=mg).json()
    assert res["best_sellers"] > 0
    first = [m["matnr"] for m in client.get("/best-sellers", headers=hs).json()]
    assert first

    # ยิงวิว/ใส่ตะกร้าให้สินค้าอันดับท้าย แล้วรัน job ใหม่ → อันดับต้องขยับ
    target = first[-1]
    with SessionLocal() as db:
        for _ in range(500):
            db.add(UserEvent(event="add_to_cart", matnr=target, source="web", created_at=utcnow()))
        db.commit()
    client.post("/admin/jobs/daily-stats", headers=mg)
    after = [m["matnr"] for m in client.get("/best-sellers", headers=hs).json()]
    assert after[0] == target and after != first

    with SessionLocal() as db:
        top = db.scalar(select(BestSeller).order_by(BestSeller.rank))
        assert top.matnr == target and top.rank == 1
        assert db.scalar(select(func.count()).select_from(OrderHistory)) > 0
