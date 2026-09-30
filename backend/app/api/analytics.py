from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.catalog import to_card
from app.api.deps import get_current_user, get_current_user_optional, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import DailyJobOut, OrderOut, TrackIn, WishlistOut
from app.schemas.catalog import MaterialCard
from app.services import analytics_service, cart_service, catalog_service, product_stock_service

router = APIRouter(tags=["history"])


def _anon(request: Request) -> str | None:
    return cart_service.anon_token_from(request)


def _cards(db: Session, materials, user: User | None) -> list[MaterialCard]:
    stock = product_stock_service.summary_for(db, [m.matnr for m in materials])
    return [to_card(m, user, stock.get(m.matnr)) for m in materials]


@router.post("/events", status_code=202)
def track_event(body: TrackIn, request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    if body.event not in analytics_service.EVENTS:
        raise HTTPException(status_code=422, detail="event ไม่รู้จัก")
    analytics_service.track(db, user, _anon(request), body.event, body.matnr, body.query, body.source, body.payload, body.purpose, body.path)
    db.commit()
    return {"ok": True}


@router.get("/best-sellers", response_model=list[MaterialCard])
def best_sellers(limit: int = Query(default=8, ge=1, le=40), db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    return _cards(db, analytics_service.best_sellers(db, limit), user)


@router.get("/me/recently-viewed", response_model=list[MaterialCard])
def recently_viewed(request: Request, limit: int = Query(default=12, ge=1, le=40), db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    return _cards(db, analytics_service.recently_viewed(db, user, _anon(request), limit), user)


@router.get("/me/wishlist", response_model=list[MaterialCard])
def my_wishlist(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _cards(db, analytics_service.wishlist(db, user), user)


@router.post("/me/wishlist/{matnr}", response_model=WishlistOut)
def toggle_wishlist(matnr: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not catalog_service.get_material(db, matnr):
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    added = analytics_service.wishlist_toggle(db, user, matnr)
    return WishlistOut(in_wishlist=added, items=_cards(db, analytics_service.wishlist(db, user), user))


@router.get("/me/orders", response_model=list[OrderOut])
def my_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return analytics_service.list_orders(db, user)


@router.get("/me/orders/{so_no}", response_model=OrderOut)
def my_order(so_no: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o = analytics_service.get_order(db, user, so_no)
    if not o:
        raise HTTPException(status_code=404, detail="ไม่พบออร์เดอร์นี้")
    return o


@router.get("/me/bought-again", response_model=list[MaterialCard])
def bought_again(limit: int = Query(default=8, ge=1, le=40), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    analytics_service.sync_order_history(db, user)
    return _cards(db, analytics_service.bought_again(db, user, limit), user)


@router.post("/admin/jobs/daily-stats", response_model=DailyJobOut)
def run_daily_stats(days: int = Query(default=30, ge=1, le=180), db: Session = Depends(get_db), _: User = Depends(require_role("manager", "admin"))):
    """ปกติรันด้วย cron รายวัน — เปิดเป็น endpoint ไว้ให้ trigger เองได้"""
    return analytics_service.run_daily_job(db, days)


@router.get("/admin/analytics/overview")
def analytics_overview(days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db), _: User = Depends(require_role("manager", "admin"))):
    """ภาพรวมพฤติกรรมผู้ใช้ — คนเข้าเว็บ · หน้ายอดนิยม · สินค้าที่ดู/กด/ใส่ตะกร้าเยอะสุด
    · คำค้นยอดฮิตพร้อมจำนวนคลิก · คำค้นที่ได้ผลลัพธ์ศูนย์"""
    return analytics_service.overview(db, days)


@router.get("/admin/top-searches")
def top_searches(days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db), _: User = Depends(require_role("manager", "admin"))):
    return analytics_service.top_searches(db, days)


@router.get("/admin/wishlist-report")
def wishlist_report(
    limit: int = Query(default=50, ge=1, le=200),
    days: int | None = Query(default=None, ge=1, le=365, description="ดูเฉพาะ N วันล่าสุด · ไม่ใส่ = ตั้งแต่เริ่มเก็บ"),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("manager", "admin")),
):
    """สินค้าที่ลูกค้ากดหัวใจมากที่สุด — เอาไว้ดูว่าของอะไรมีคนสนใจแต่ยังไม่ซื้อ

    saved_now = ตอนนี้มีกี่คนเก็บไว้ · ever/users = เคยถูกกดกี่ครั้งจากกี่คน
    removed = กดแล้วเปลี่ยนใจเอาออกกี่ครั้ง
    """
    return analytics_service.wishlist_report(db, limit=limit, days=days)
