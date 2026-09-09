import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.etl import import_catalog
from app.models.catalog import Brand, Category, Material, Plant
from app.models.content import HomeMedia
from app.models.user import User
from app.schemas.catalog import BrandOut, CategoryOut, CategoryRefOut, ColorOptionOut, FacetsOut, MaterialCard, MaterialDetail, PlantOut, SearchOut, StockOut, StockRowOut, StockSummaryOut
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


def color_options(db: Session, m: Material) -> list[Material]:
    """สีอื่นของรุ่นเดียวกัน — ต้นทางแยกทุกสีเป็นคนละ MATNR ("รุ่น Adorn สีขาว" / "สีไม้เข้ม")

    จับคู่ด้วย ซีรีส์ + แบรนด์ + หมวด เพราะสามอย่างนี้มาจากฐานเว็บชุดเดียวกัน ตรงกันคือของรุ่นเดียวกันจริง
    (ถ้าจับด้วยชื่อจะพลาด เพราะชื่อมีสีต่อท้ายอยู่แล้ว) · ไม่มีซีรีส์/สี ก็แค่ไม่มีตัวเลือกให้เลือก
    """
    if not m.variant or not m.color:
        return []
    rows = db.scalars(
        select(Material)
        .where(
            Material.is_public.is_(True),
            Material.variant == m.variant,
            Material.brand_id == m.brand_id,
            Material.category_id == m.category_id,
            Material.color.is_not(None),
        )
        .order_by(Material.color, Material.matnr)
        .limit(24)
    ).all()
    seen: dict[str, Material] = {}
    for r in rows:  # หนึ่งสีหนึ่งปุ่ม — รุ่นเดียวกันสีเดียวกันแต่คนละขนาดมีอยู่ เอาตัวแรกพอ
        seen.setdefault(r.color or "", r if r.matnr != m.matnr else m)
    return list(seen.values()) if len(seen) > 1 else []


def related_categories(db: Session, m: Material) -> list[Category]:
    """หมวดของสินค้าตัวนี้ + หมวดพี่น้องใต้หมวดแม่เดียวกัน — ดูเตียงแล้วกดดูชุดเตียง/หัวเตียงต่อได้

    หมวดตัวเองมาก่อนเสมอ (เป็นชิปที่เลือกอยู่) ตามด้วยพี่น้องที่ยังมีของขายจริงเท่านั้น
    หมวดที่ไม่มีของกดไปก็เจอหน้าเปล่า · นับของในหมวดลูกด้วย เพราะบางกิ่งของอยู่ชั้นล่างสุด
    """
    cat = m.category
    if not cat or not cat.parent_id:
        return [cat] if cat else []
    sibs = db.scalars(
        select(Category).where(Category.parent_id == cat.parent_id, Category.id != cat.id).order_by(Category.sort, Category.name_th)
    ).all()
    if not sibs:
        return [cat]
    kids = db.scalars(select(Category).where(Category.parent_id.in_([c.id for c in sibs]))).all()
    under: dict[str, list[str]] = {c.id: [c.id] for c in sibs}
    for k in kids:
        under[k.parent_id].append(k.id)
    ids = [i for v in under.values() for i in v]
    counts = dict(
        db.execute(
            select(Material.category_id, func.count())
            .where(Material.is_public.is_(True), Material.category_id.in_(ids))
            .group_by(Material.category_id)
        ).all()
    )
    return [cat] + [c for c in sibs if sum(counts.get(i, 0) for i in under[c.id]) > 0][:11]


def to_detail(m: Material, user: User | None, stock: dict | None, colors: list[Material] | None = None,
              cats: list[Category] | None = None) -> MaterialDetail:
    card = to_card(m, user, stock)
    return MaterialDetail(
        **card.model_dump(), barcode=m.barcode, description=m.description, color=m.color, style=m.style,
        volume_m3=m.volume_m3, weight_kg=m.weight_kg, sold_qty=m.sold_qty, synced_at=m.synced_at,
        related_categories=[CategoryRefOut(id=c.id, name_th=c.name_th) for c in (cats or [])],
        colors=[
            ColorOptionOut(matnr=c.matnr, color=c.color, name_th=c.name_th, image_url=c.image_url,
                           price=catalog_service.unit_price_for(c, user)[0])
            for c in (colors or [])
        ],
    )


def category_tree(db: Session) -> list[CategoryOut]:
    """ต้นไม้หมวดสำหรับหน้าลูกค้า — ตัดกิ่งที่ไม่มีสินค้าให้ลูกค้าเห็นสักตัวออก

    ต้นทางส่งหมวดมาตามที่ฝ่ายจัดหมวดแบ่งไว้ ซึ่งมีทั้งของที่ไม่ใช่สินค้า ("ค่าบริการ")
    และหมวดที่ยังไม่มีของขึ้นเว็บ ("Prop") โผล่ในตัวกรองแล้วกดไปก็เจอหน้าว่าง
    นับจากของจริงแทนที่จะไล่ลิสต์ชื่อไว้ — วันหลังมีของขึ้นหมวดไหน หมวดนั้นก็โผล่มาเอง
    """
    cats = db.scalars(select(Category).order_by(Category.sort, Category.name_th)).all()
    by_parent: dict[str | None, list[Category]] = {}
    for c in cats:
        by_parent.setdefault(c.parent_id, []).append(c)

    counts = dict(
        db.execute(
            select(Material.category_id, func.count())
            .where(Material.is_public.is_(True), Material.category_id.is_not(None))
            .group_by(Material.category_id)
        ).all()
    )

    def n_public(cid: str) -> int:
        return counts.get(cid, 0) + sum(n_public(ch.id) for ch in by_parent.get(cid, []))

    return [
        CategoryOut(
            id=c.id, name_th=c.name_th, name_en=c.name_en, room=c.room, icon=c.icon,
            children=[CategoryOut(id=ch.id, name_th=ch.name_th, room=ch.room)
                      for ch in by_parent.get(c.id, []) if n_public(ch.id)],
        )
        for c in by_parent.get(None, [])
        if n_public(c.id)
    ]


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
    brand: list[str] = Query(default=[], description="เลือกได้หลายแบรนด์ — ส่ง brand ซ้ำหลายตัว"),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    discount_only: bool = False,
    in_stock: bool = False,
    has_image: bool = False,
    sort: str = Query(default="relevance"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    facets: bool = Query(default=False, description="ขอ facet มาด้วย (หน้าถัดๆ ไปไม่ต้องขอซ้ำ)"),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    f = catalog_service.SearchFilters(
        q=q, category=category, room=room, tag=tag, brands=brand, min_price=min_price, max_price=max_price,
        discount_only=discount_only, in_stock=in_stock, has_image=has_image, sort=sort,
        include_hidden=bool(user and user.is_staff),
    )
    rows, total = catalog_service.search(db, f, limit, offset)
    stock = catalog_service.stock_summary(db, [m.matnr for m in rows])
    if q and offset == 0:
        analytics_service.track(db, user, cart_service.anon_token_from(request), "search", query=q, payload={"result_count": total})
        db.commit()
    return SearchOut(
        items=[to_card(m, user, stock.get(m.matnr)) for m in rows], total=total, q=q, category=category,
        facets=FacetsOut(**catalog_service.facets(db, f)) if facets else None,
    )


@router.get("/materials/{matnr}", response_model=MaterialDetail)
def material_detail(matnr: str, request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    m = catalog_service.get_material(db, matnr)
    # ของที่ข้อมูลไม่ครบไม่โผล่ในผลค้นหาอยู่แล้ว ปิดทางเดาลิงก์ตรงด้วย — แต่พนักงานยังเปิดดูได้
    if not m or (not m.is_public and not (user and user.is_staff)):
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    stock = catalog_service.stock_summary(db, [matnr]).get(matnr)
    analytics_service.track(db, user, cart_service.anon_token_from(request), "view_material", matnr)
    db.commit()
    return to_detail(m, user, stock, color_options(db, m), related_categories(db, m))


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
    # เดิมกรองด้วย tag ของ seed (new/deal/bestseller) ซึ่งข้อมูลจริงแทบไม่มี — ใช้สัญญาณจริงแทน
    new_rows = strip(db, sort="new")
    deal_rows = strip(db, sort="discount", discount_only=True)
    best_rows = strip(db, sort="bestseller")
    groups = room_groups(db)
    all_m = new_rows + deal_rows + best_rows + [m for _, rows in groups for m in rows]
    stock = catalog_service.stock_summary(db, [m.matnr for m in all_m])
    content["categories"] = [c.model_dump() for c in category_tree(db)]
    content["new_products"] = [to_card(m, user, stock.get(m.matnr)).model_dump() for m in new_rows]
    content["deals"] = [to_card(m, user, stock.get(m.matnr)).model_dump() for m in deal_rows]
    content["bestsellers"] = [to_card(m, user, stock.get(m.matnr)).model_dump() for m in best_rows]
    content["brands"] = [BrandOut(id=b.id, name=b.name).model_dump() for b in db.scalars(select(Brand)).all()]
    content["room_rows"] = [
        {"label": g.name_th, "room": g.id, "href": f"/search?category={g.id}",
         "items": [to_card(m, user, stock.get(m.matnr)).model_dump() for m in rows]}
        for g, rows in groups
    ] or content.get("room_rows", [])
    content.update(home_media(db))
    content["main_nav"] = main_nav(db, content["categories"])
    return content


# เมนูตัวโชว์ยังไม่มีข้อมูลต้นทาง — ทั้ง sb_products และ Magento ไม่มีฟิลด์ไหนบอกว่าเป็นตัวโชว์
# ระหว่างรอ ชี้ไปที่ของลดราคา ซึ่งใกล้เคียงที่สุด (ใส่ in_stock ไม่ได้ stock_cache ยังมีแค่ 20 ตัว)
DISPLAY_HREF = "/search?discount_only=1&has_image=1&sort=discount"


def main_nav(db: Session, cats: list[dict]) -> list[dict]:
    """แถบเมนูมาจากต้นไม้หมวดจริง ไม่ใช่รายการตายตัวใน home.json

    หมวดกลุ่ม (ดู GROUPS ใน etl/import_catalog.py) = 1 เมนู · ลูกของมัน = รายการในเมนู
    """
    out = [
        {"label": c["name_th"], "href": f"/search?category={c['id']}",
         "items": [{"label": ch["name_th"], "href": f"/search?category={ch['id']}"} for ch in c["children"]]}
        for c in cats if c["id"] in import_catalog.GROUPS
    ]
    out.append({"label": "สินค้าตัวโชว์", "href": DISPLAY_HREF, "items": []})
    return out


def room_groups(db: Session) -> list[tuple[Category, list[Material]]]:
    """แถว "ช้อปตามหมวดสินค้า" — กลุ่มละ 1 แถว แต่ละแถวเป็นการ์ดสินค้าจริงในกลุ่มนั้น

    ของเดิมใน seed เป็นช่องหมวดที่ใช้ slug ซึ่งไม่มีอยู่จริง (bed, wardrobe, ...) กดแล้วไม่เจอสินค้า
    ตอนนี้ดึงสินค้าขายดีที่มีรูปของกลุ่ม (ค้นลงทั้งกิ่ง) มาแสดงเป็นการ์ดเหมือนแถวสินค้าอื่น

    เอาเฉพาะกลุ่มที่เป็น "ห้อง" (room ไม่ว่าง) — "สินค้าพิเศษ" กับ "ของตกแต่ง" เป็นถุงรวมของ
    ที่ไม่เข้าห้องไหน ของในแถวเลยกระโดดกันมั่ว (โต๊ะ ปนของแต่ง ปนไฟ) ไม่ช่วยให้เลือกของง่ายขึ้น
    ยังกดเข้าไปดูจากเมนู/ตัวกรองได้ตามปกติ แค่ไม่ตั้งเป็นแถวบนหน้าแรก
    """
    groups = [c for c in db.scalars(select(Category).where(Category.parent_id.is_(None)).order_by(Category.sort, Category.name_th))
              if c.id in import_catalog.GROUPS and c.room]
    out = []
    for g in groups:
        rows = strip(db, limit=12, category=g.id, sort="bestseller")
        if rows:
            out.append((g, rows))
    return out


def strip(db: Session, limit: int = 8, **kw):
    """แถวสินค้าบนหน้าแรก/หน้าค้นหา — เอาเฉพาะตัวที่มีรูปก่อน กล่องเปล่าเรียงกันดูไม่ได้

    ถ้ากรองรูปแล้วไม่เหลืออะไร (ฐาน seed ยังไม่มีรูปสักตัว) ค่อยยอมเอาแบบไม่มีรูป
    ดีกว่าปล่อยแถวว่าง
    """
    f = catalog_service.SearchFilters(has_image=True, **kw)
    rows, _ = catalog_service.search(db, f, limit=limit)
    if rows:
        return rows
    f.has_image = False
    return catalog_service.search(db, f, limit=limit)[0]


def home_media(db: Session) -> dict:
    """ภาพจริงจาก Magento CMS (ตาราง home_media) — section ไหนยังไม่มีข้อมูล ก็ปล่อยให้ home.json ทำงานไป

    หน้าเว็บจึงไม่พังถ้ายังไม่ได้รัน sync_home_media แค่กลับไปเป็นกล่อง placeholder เหมือนเดิม
    """
    rows = db.scalars(
        select(HomeMedia).where(HomeMedia.is_active.is_(True)).order_by(HomeMedia.section, HomeMedia.position)
    ).all()
    def tile(r: HomeMedia) -> dict:
        return {"id": f"{r.section}-{r.slug}", "label": r.label, "alt": r.alt, "image": r.image_url,
                "image_mb": r.image_mb_url, "href": r.href or "/search"}

    out: dict[str, list[dict]] = {}
    for key, section in (("hero_slides", "hero"), ("top_categories", "top_category"), ("inspirations", "inspiration"), ("brand_tiles", "brand")):
        got = [r for r in rows if r.section == section]
        if got:
            out[key] = [tile(r) for r in got]
    # FIND YOUR INSPIRATION — แบ่งเป็นแท็บตาม group_key เรียงตามลำดับที่ ETL เก็บมา
    tabs: dict[str, dict] = {}
    for r in rows:
        if r.section != "inspire_tab" or not r.group_key:
            continue
        tab = tabs.setdefault(r.group_key, {"key": r.group_key, "label": r.group_label or r.group_key, "items": []})
        tab["items"].append(tile(r))
    if tabs:
        out["inspire_tabs"] = [tabs[k] for k in sorted(tabs)]
    return out
