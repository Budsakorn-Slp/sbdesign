import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.models.catalog import Brand, Category, Material, Plant
from app.models.user import User
from app.schemas.catalog import BrandOut, CategoryOut, MaterialCard, MaterialDetail, PlantOut, SearchOut, StockOut, StockRowOut, StockSummaryOut
from app.services import analytics_service, cart_service, catalog_service, stock_service

router = APIRouter(tags=["catalog"])
CONTENT_DIR = Path(__file__).resolve().parents[2] / "seed" / "content"


def to_card(m: Material, user: User | None, stock: dict | None = None) -> MaterialCard:
    prices = catalog_service.prices_of(m)
    price, tier = catalog_service.unit_price_for(m, user)
    standard = prices.get("standard", price)
    compare = prices.get("compare_at")
    member = None
    if user:  # guest ไม่เห็นราคาสมาชิก
        member = prices.get(catalog_service.price_tier_for(user)) or prices.get("Gold")
    pct = int(round((1 - float(standard) / float(compare)) * 100)) if compare and compare > standard else None
    return MaterialCard(
        matnr=m.matnr, sku=m.sku, name_th=m.name_th, name_en=m.name_en, variant=m.variant, spec=m.spec, category_id=m.category_id,
        category_name=m.category.name_th if m.category else None, brand_id=m.brand_id, brand_name=m.brand.name if m.brand else None, room=m.room,
        image_url=m.image_url, price=price, price_tier=tier, standard_price=standard, member_price=member, compare_at_price=compare, discount_percent=pct,
        requires_install=m.requires_install, is_takeaway_ok=m.is_takeaway_ok, is_new=m.is_new, tags=list(m.tags or []),
        stock=StockSummaryOut(**stock) if stock else None,
    )


def to_detail(m: Material, user: User | None, stock: dict | None) -> MaterialDetail:
    card = to_card(m, user, stock)
    return MaterialDetail(**card.model_dump(), barcode=m.barcode, description=m.description, volume_m3=m.volume_m3, weight_kg=m.weight_kg, synced_at=m.synced_at)


def category_tree(db: Session) -> list[CategoryOut]:
    cats = db.scalars(select(Category).order_by(Category.sort, Category.name_th)).all()
    by_parent: dict[str | None, list[Category]] = {}
    for c in cats:
        by_parent.setdefault(c.parent_id, []).append(c)
    return [CategoryOut(id=c.id, name_th=c.name_th, name_en=c.name_en, room=c.room, icon=c.icon, children=[CategoryOut(id=ch.id, name_th=ch.name_th, room=ch.room) for ch in by_parent.get(c.id, [])]) for c in by_parent.get(None, [])]


@router.get("/categories", response_model=list[CategoryOut])
def categories(db: Session = Depends(get_db)):
    return category_tree(db)


@router.get("/brands", response_model=list[BrandOut])
def brands(db: Session = Depends(get_db)):
    return [BrandOut(id=b.id, name=b.name) for b in db.scalars(select(Brand)).all()]


@router.get("/plants", response_model=list[PlantOut])
def plants(db: Session = Depends(get_db)):
    return db.scalars(select(Plant).order_by(Plant.type.desc(), Plant.name)).all()


@router.get("/materials/search", response_model=SearchOut)
def search(
    q: str | None = Query(default=None),
    category: str | None = None,
    room: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    rows, total = catalog_service.search(db, q, category, room, tag, limit, offset)
    stock = catalog_service.stock_summary(db, [m.matnr for m in rows])
    if q and offset == 0:
        analytics_service.track(db, user, cart_service.anon_token_from(request), "search", query=q, payload={"result_count": total})
        db.commit()
    return SearchOut(items=[to_card(m, user, stock.get(m.matnr)) for m in rows], total=total, q=q, category=category)


@router.get("/materials/{matnr}", response_model=MaterialDetail)
def material_detail(matnr: str, request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    m = catalog_service.get_material(db, matnr)
    if not m:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    stock = catalog_service.stock_summary(db, [matnr]).get(matnr)
    analytics_service.track(db, user, cart_service.anon_token_from(request), "view_material", matnr)
    db.commit()
    return to_detail(m, user, stock)


@router.get("/materials/{matnr}/stock", response_model=StockOut)
def material_stock(matnr: str, plant: str | None = None, db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    """ยิง SAP สด + log stock_checks ทุกครั้ง · พนักงานเห็นทุกสาขา · ลูกค้าเห็นแค่สาขาที่เลือก/สรุป"""
    if not db.get(Material, matnr):
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    res = stock_service.check_stock(db, user, matnr)
    rows = res.rows
    is_staff = bool(user and user.is_staff)
    if not is_staff:
        rows = [r for r in rows if plant and r.plant_code == plant]
    return StockOut(
        matnr=matnr, source=res.source, stale=res.stale, fetched_at=res.fetched_at, stale_minutes=stock_service.stale_minutes(res.fetched_at),
        available=any(r.available > 0 for r in res.rows), earliest_atp=stock_service.earliest_atp(res.rows),
        rows=[StockRowOut(plant_code=r.plant_code, plant_name=r.plant_name, plant_type=r.plant_type, on_hand=r.on_hand, reserved=r.reserved, available=r.available, atp_date=r.atp_date, note=r.note) for r in rows],
        error=res.error,
    )


@router.get("/home")
def home(db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    with open(CONTENT_DIR / "home.json", encoding="utf-8") as f:
        content = json.load(f)
    new_rows, _ = catalog_service.search(db, None, None, None, "new", limit=8)
    deal_rows, _ = catalog_service.search(db, None, None, None, "deal", limit=8)
    best_rows, _ = catalog_service.search(db, None, None, None, "bestseller", limit=8)
    all_m = new_rows + deal_rows + best_rows
    stock = catalog_service.stock_summary(db, [m.matnr for m in all_m])
    content["categories"] = [c.model_dump() for c in category_tree(db)]
    content["new_products"] = [to_card(m, user, stock.get(m.matnr)).model_dump() for m in new_rows]
    content["deals"] = [to_card(m, user, stock.get(m.matnr)).model_dump() for m in deal_rows]
    content["bestsellers"] = [to_card(m, user, stock.get(m.matnr)).model_dump() for m in best_rows]
    content["brands"] = [BrandOut(id=b.id, name=b.name).model_dump() for b in db.scalars(select(Brand)).all()]
    return content
