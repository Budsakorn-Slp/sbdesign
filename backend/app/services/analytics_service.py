"""ประวัติ + สินค้าขายดี
- เก็บ event ดิบใน user_events แล้ว job รายวันย่อยเป็น material_daily_stats → best_sellers
  (ไม่จัดอันดับจาก event ดิบตอน request เพราะตารางโตเร็ว)
- order_history mirror จาก SAP: อ่านอย่างเดียว ระบบเราไม่แก้
"""
import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.integrations.sap import SapError, get_sap_client
from app.models.analytics import BestSeller, MaterialDailyStat, OrderHistory, OrderHistoryLine, RecentlyViewed, SearchQuery, UserEvent, Wishlist
from app.models.catalog import Material
from app.models.common import utcnow
from app.models.user import User

log = logging.getLogger("sb.analytics")

EVENTS = ("view_material", "search", "add_to_cart", "remove_from_cart", "begin_checkout", "purchase")
RECENT_LIMIT = 20
# น้ำหนักคะแนนขายดี: ยอดขายสำคัญสุด ตามด้วยการหยิบใส่ตะกร้า แล้วค่อยยอดวิว
W_QTY, W_CART, W_VIEW = Decimal(10), Decimal(2), Decimal("0.2")


def owner_key(user: User | None, anon: str | None) -> str | None:
    return f"u:{user.id}" if user else (f"a:{anon}" if anon else None)


def track(db: Session, user: User | None, anon: str | None, event: str, matnr: str | None = None, query: str | None = None, source: str = "web", payload: dict | None = None, purpose: str = "service") -> None:
    """เก็บ event — ไม่ commit เอง ยกเว้นถูกเรียกจาก endpoint /events

    purpose="service" = จำเป็นต่อการให้บริการ (ดูล่าสุด/ตะกร้า/ประวัติ) เก็บได้ตามปกติ
    purpose="marketing" = เก็บเพื่อการตลาด ต้องมี consent · ไม่มี consent → ยังนับเป็นสถิติรวมได้
    แต่ต้องตัดตัวตนทิ้งตั้งแต่ตอนเขียน
    """
    from app.services import pdpa_service  # import ตรงนี้กัน circular import

    if event not in EVENTS:
        return
    purpose = purpose if purpose in ("service", "marketing") else "service"
    identify = purpose == "service" or pdpa_service.marketing_allowed(user)
    uid = user.id if (user and identify) else None
    tok = None if user else (anon if identify else None)
    db.add(UserEvent(user_id=uid, anon_token=tok, event=event, matnr=matnr, query=query, source=source, payload=payload, purpose=purpose))
    if event == "view_material" and matnr:
        _touch_recent(db, user, anon, matnr)
    if event == "search" and query:
        db.add(SearchQuery(user_id=uid, anon_token=tok, q=query[:200], result_count=int((payload or {}).get("result_count") or 0)))


def _touch_recent(db: Session, user: User | None, anon: str | None, matnr: str) -> None:
    key = owner_key(user, anon)
    if not key:
        return
    row = db.scalar(select(RecentlyViewed).where(RecentlyViewed.owner_key == key, RecentlyViewed.matnr == matnr))
    if row:
        row.views += 1
        row.viewed_at = utcnow()
    else:
        db.add(RecentlyViewed(owner_key=key, user_id=user.id if user else None, matnr=matnr, viewed_at=utcnow()))


def recently_viewed(db: Session, user: User | None, anon: str | None, limit: int = 12) -> list[Material]:
    key = owner_key(user, anon)
    if not key:
        return []
    rows = db.scalars(select(RecentlyViewed).where(RecentlyViewed.owner_key == key).order_by(RecentlyViewed.viewed_at.desc()).limit(limit)).all()
    return _materials_in_order(db, [r.matnr for r in rows])


def merge_owner(db: Session, anon: str, user: User) -> None:
    """ตอน guest ล็อกอิน: ย้ายของที่ดูไว้มาเป็นของบัญชี"""
    for row in db.scalars(select(RecentlyViewed).where(RecentlyViewed.owner_key == f"a:{anon}")).all():
        mine = db.scalar(select(RecentlyViewed).where(RecentlyViewed.owner_key == f"u:{user.id}", RecentlyViewed.matnr == row.matnr))
        if mine:
            mine.views += row.views
            mine.viewed_at = max(mine.viewed_at, row.viewed_at)
            db.delete(row)
        else:
            row.owner_key, row.user_id = f"u:{user.id}", user.id
    db.execute(UserEvent.__table__.update().where(UserEvent.anon_token == anon).values(user_id=user.id, anon_token=None))


def _materials_in_order(db: Session, matnrs: list[str]) -> list[Material]:
    if not matnrs:
        return []
    # แถวพวกนี้ (ดูล่าสุด/รายการโปรด/ซื้อซ้ำ/ขายดี) เคยไม่กรอง is_public เลย
    # ของที่ถอดออกจากเว็บแล้วจึงยังโผล่กลับมาทางนี้ได้
    found = {m.matnr: m for m in db.scalars(select(Material).where(Material.matnr.in_(matnrs), Material.is_public.is_(True))).all()}
    return [found[m] for m in matnrs if m in found]


# ---------- wishlist ----------
def wishlist(db: Session, user: User) -> list[Material]:
    rows = db.scalars(select(Wishlist).where(Wishlist.user_id == user.id).order_by(Wishlist.created_at.desc())).all()
    return _materials_in_order(db, [r.matnr for r in rows])


def wishlist_toggle(db: Session, user: User, matnr: str) -> bool:
    row = db.scalar(select(Wishlist).where(Wishlist.user_id == user.id, Wishlist.matnr == matnr))
    if row:
        db.delete(row)
        db.commit()
        return False
    db.add(Wishlist(user_id=user.id, matnr=matnr))
    track(db, user, None, "view_material", matnr, payload={"wishlist": True})
    db.commit()
    return True


def wishlist_matnrs(db: Session, user: User | None) -> set[str]:
    if not user:
        return set()
    return set(db.scalars(select(Wishlist.matnr).where(Wishlist.user_id == user.id)).all())


# ---------- order history (mirror จาก SAP) ----------
def sync_order_history(db: Session, user: User) -> int:
    if not user.sap_customer_no:
        return 0
    try:
        orders = get_sap_client().get_order_history(user.sap_customer_no)
    except SapError as e:
        log.warning("ดึงประวัติสั่งซื้อจาก SAP ไม่ได้ (%s): %s", user.sap_customer_no, e)
        return 0
    n = 0
    for o in orders:
        row = db.scalar(select(OrderHistory).where(OrderHistory.so_no == o.so_no))
        if not row:
            row = OrderHistory(so_no=o.so_no, sap_customer_no=o.sap_customer_no)
            db.add(row)
            n += 1
        row.customer_user_id = user.id
        row.order_date, row.status, row.channel, row.branch = o.order_date, o.status, o.channel, o.branch
        row.grand_total, row.delivery_date, row.synced_at = o.grand_total, o.delivery_date, utcnow()
        db.flush()
        db.execute(delete(OrderHistoryLine).where(OrderHistoryLine.order_id == row.id))
        for l in o.lines:
            db.add(OrderHistoryLine(order_id=row.id, matnr=l.matnr, name=l.name, qty=l.qty, unit_price=l.unit_price, line_total=l.line_total))
    db.commit()
    return n


def list_orders(db: Session, user: User, refresh: bool = True) -> list[OrderHistory]:
    if refresh:
        sync_order_history(db, user)
    return list(db.scalars(select(OrderHistory).options(selectinload(OrderHistory.lines)).where(OrderHistory.customer_user_id == user.id).order_by(OrderHistory.order_date.desc())).all())


def get_order(db: Session, user: User, so_no: str) -> OrderHistory | None:
    o = db.scalar(select(OrderHistory).options(selectinload(OrderHistory.lines)).where(OrderHistory.so_no == so_no))
    if not o:
        return None
    if o.customer_user_id != user.id and not user.is_staff:
        return None
    return o


def bought_again(db: Session, user: User, limit: int = 8) -> list[Material]:
    """สินค้าที่เคยซื้อ — ไว้ทำแถบ 'ซื้อซ้ำ'"""
    rows = db.execute(
        select(OrderHistoryLine.matnr, func.max(OrderHistory.order_date))
        .join(OrderHistory, OrderHistory.id == OrderHistoryLine.order_id)
        .where(OrderHistory.customer_user_id == user.id)
        .group_by(OrderHistoryLine.matnr)
        .order_by(func.max(OrderHistory.order_date).desc())
        .limit(limit)
    ).all()
    return _materials_in_order(db, [r[0] for r in rows])


# ---------- job รายวัน ----------
def build_daily_stats(db: Session, day: date) -> int:
    """ย่อย user_events + order_history ของวันนั้นลง material_daily_stats"""
    start, end = day, day + timedelta(days=1)
    agg: dict[str, dict] = {}

    ev = db.execute(
        select(UserEvent.matnr, UserEvent.event, func.count())
        .where(UserEvent.matnr.is_not(None), UserEvent.created_at >= start, UserEvent.created_at < end)
        .group_by(UserEvent.matnr, UserEvent.event)
    ).all()
    for matnr, event, n in ev:
        a = agg.setdefault(matnr, {"views": 0, "add_to_cart": 0, "orders": 0, "qty_sold": 0, "revenue": Decimal(0)})
        if event == "view_material":
            a["views"] += n
        elif event == "add_to_cart":
            a["add_to_cart"] += n

    sold = db.execute(
        select(OrderHistoryLine.matnr, func.count(), func.sum(OrderHistoryLine.qty), func.sum(OrderHistoryLine.line_total))
        .join(OrderHistory, OrderHistory.id == OrderHistoryLine.order_id)
        .where(OrderHistory.order_date == day, OrderHistory.status != "cancelled")
        .group_by(OrderHistoryLine.matnr)
    ).all()
    for matnr, orders, qty, revenue in sold:
        a = agg.setdefault(matnr, {"views": 0, "add_to_cart": 0, "orders": 0, "qty_sold": 0, "revenue": Decimal(0)})
        a["orders"] += int(orders or 0)
        a["qty_sold"] += int(qty or 0)
        a["revenue"] += Decimal(revenue or 0)

    for matnr, a in agg.items():
        row = db.scalar(select(MaterialDailyStat).where(MaterialDailyStat.stat_date == day, MaterialDailyStat.matnr == matnr))
        if not row:
            row = MaterialDailyStat(stat_date=day, matnr=matnr)
            db.add(row)
        row.views, row.add_to_cart, row.orders, row.qty_sold, row.revenue = a["views"], a["add_to_cart"], a["orders"], a["qty_sold"], a["revenue"]
    db.commit()
    return len(agg)


def refresh_best_sellers(db: Session, window_days: int = 30, limit: int = 20) -> list[BestSeller]:
    since = date.today() - timedelta(days=window_days)
    rows = db.execute(
        select(MaterialDailyStat.matnr, func.sum(MaterialDailyStat.qty_sold), func.sum(MaterialDailyStat.add_to_cart), func.sum(MaterialDailyStat.views))
        .where(MaterialDailyStat.stat_date >= since)
        .group_by(MaterialDailyStat.matnr)
    ).all()
    scored = sorted(
        ((m, Decimal(int(q or 0)) * W_QTY + Decimal(int(c or 0)) * W_CART + Decimal(int(v or 0)) * W_VIEW, int(q or 0)) for m, q, c, v in rows),
        key=lambda x: (-x[1], x[0]),
    )[:limit]
    db.execute(delete(BestSeller))
    now = utcnow()
    out = [BestSeller(matnr=m, rank=i + 1, score=score, qty_sold=qty, window_days=window_days, computed_at=now) for i, (m, score, qty) in enumerate(scored)]
    db.add_all(out)
    db.commit()
    return out


def run_daily_job(db: Session, days: int = 30, window_days: int = 30) -> dict:
    """cron รายวัน (หรือปุ่มในหน้า admin): ย้อนหลัง N วัน แล้ว refresh อันดับขายดี"""
    today = date.today()
    rows = sum(build_daily_stats(db, today - timedelta(days=i)) for i in range(days))
    best = refresh_best_sellers(db, window_days)
    return {"days": days, "stat_rows": rows, "best_sellers": len(best), "top": [b.matnr for b in best[:5]]}


def best_sellers(db: Session, limit: int = 8) -> list[Material]:
    rows = db.scalars(select(BestSeller).order_by(BestSeller.rank).limit(limit)).all()
    return _materials_in_order(db, [r.matnr for r in rows])


def top_searches(db: Session, days: int = 30, limit: int = 8) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    rows = db.execute(
        select(SearchQuery.q, func.count()).where(SearchQuery.created_at >= since).group_by(SearchQuery.q).order_by(func.count().desc()).limit(limit)
    ).all()
    return [{"q": q, "count": int(n)} for q, n in rows]
