"""กดหัวใจ — เก็บทั้ง "สถานะตอนนี้" และ "ประวัติ" ไว้ทำรีพอร์ต

หัวใจของชุดนี้: ลูกค้ากดเอาออกแล้ว รีพอร์ตต้องยังรู้ว่าเคยมีคนสนใจ
ของเดิมลบแถวทิ้งอย่างเดียว พอเอาออกก็เหมือนไม่เคยเกิดขึ้น
"""
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.analytics import UserEvent, Wishlist
from app.seed import seed_catalog
from tests.helpers import auth_headers, ensure_seed

MATNR = "10023841"


def setup_function():
    ensure_seed()
    with SessionLocal() as db:
        seed_catalog(db)


def _clean(matnr=MATNR):
    with SessionLocal() as db:
        db.query(Wishlist).filter(Wishlist.matnr == matnr).delete()
        db.query(UserEvent).filter(UserEvent.matnr == matnr).delete()
        db.commit()


def test_toggle_saves_and_removes(client):
    _clean()
    h = auth_headers(client, "0812223333")
    on = client.post(f"/me/wishlist/{MATNR}", headers=h).json()
    assert on["in_wishlist"] is True
    assert MATNR in [i["matnr"] for i in client.get("/me/wishlist", headers=h).json()]

    off = client.post(f"/me/wishlist/{MATNR}", headers=h).json()
    assert off["in_wishlist"] is False
    assert MATNR not in [i["matnr"] for i in client.get("/me/wishlist", headers=h).json()]


def test_history_survives_after_customer_unhearts(client):
    """เอาออกแล้วรายการโปรดต้องหาย แต่ประวัติต้องอยู่ ไม่งั้นทำรีพอร์ตย้อนหลังไม่ได้"""
    _clean()
    h = auth_headers(client, "0812223333")
    client.post(f"/me/wishlist/{MATNR}", headers=h)
    client.post(f"/me/wishlist/{MATNR}", headers=h)  # กดเอาออก

    with SessionLocal() as db:
        assert db.scalar(select(Wishlist).where(Wishlist.matnr == MATNR)) is None
        events = db.scalars(select(UserEvent).where(UserEvent.matnr == MATNR)).all()
    kinds = sorted(e.event for e in events)
    assert kinds == ["wishlist_add", "wishlist_remove"]
    # ต้องรู้ว่าใครกด ไม่ใช่นับรวมแบบไม่มีตัวตน — รีพอร์ตต้องตอบได้ว่ามีกี่คน
    assert all(e.user_id for e in events)


def test_unhearting_is_not_counted_as_a_product_view(client):
    """ของเดิมบันทึกการกดหัวใจเป็น view_material ทำให้ยอดวิวเฟ้อโดยไม่มีใครเปิดดูจริง"""
    _clean()
    h = auth_headers(client, "0812223333")
    client.post(f"/me/wishlist/{MATNR}", headers=h)
    with SessionLocal() as db:
        views = db.scalars(select(UserEvent).where(UserEvent.matnr == MATNR, UserEvent.event == "view_material")).all()
    assert views == []


def test_report_counts_current_and_all_time(client):
    """คนหนึ่งกดค้างไว้ อีกคนกดแล้วเอาออก — รีพอร์ตต้องแยกสองอย่างนี้ออกจากกัน"""
    _clean()
    keep = auth_headers(client, "0812223333")
    gone = auth_headers(client, "0949164600")
    client.post(f"/me/wishlist/{MATNR}", headers=keep)
    client.post(f"/me/wishlist/{MATNR}", headers=gone)
    client.post(f"/me/wishlist/{MATNR}", headers=gone)  # คนที่สองเปลี่ยนใจ

    admin = auth_headers(client, "ADM-001", "staff")
    rows = client.get("/admin/wishlist-report?limit=100", headers=admin).json()
    row = next(r for r in rows if r["matnr"] == MATNR)
    assert row["saved_now"] == 1      # เหลือคนเดียวที่ยังเก็บไว้
    assert row["ever"] == 2           # แต่เคยถูกกดสองครั้ง
    assert row["users"] == 2          # จากสองคน
    assert row["removed"] == 1        # เปลี่ยนใจไปหนึ่ง
    assert row["name_th"]


def test_report_is_staff_only(client):
    assert client.get("/admin/wishlist-report").status_code in (401, 403)
    hc = auth_headers(client, "0812223333")
    assert client.get("/admin/wishlist-report", headers=hc).status_code == 403
