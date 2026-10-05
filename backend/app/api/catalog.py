import json
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.etl import import_catalog
from app.models.catalog import Brand, Category, Material, MaterialCategory, MaterialImage, Plant
from app.models.content import HomeMedia, InfoPage
from app.models.user import User
from app.schemas.catalog import (
    ProductStockOut, BrandOut, CategoryOut, CategoryRefOut, ColorOptionOut, FacetsOut, MaterialCard,
    InfoPageOut, MaterialDetail, VariantOptionOut, PlantOut, ProductStockOut, SearchOut, StockOut, StockRowOut, SuggestItemOut, SuggestOut,
    StockSiteOut, UnderstoodOut,
)
from app.services import analytics_service, product_stock_service, cart_service, catalog_service, stock_service

router = APIRouter(tags=["catalog"])
CONTENT_DIR = Path(__file__).resolve().parents[2] / "seed" / "content"


def to_card(m: Material, user: User | None, stock: dict | None = None) -> MaterialCard:
    prices = catalog_service.prices_of(m)
    price, tier = catalog_service.unit_price_for(m, user)
    standard = prices.get("standard", price)
    compare = prices.get("compare_at")
    pct = int(round((1 - float(standard) / float(compare)) * 100)) if compare and compare > standard else None
    return MaterialCard(
        matnr=m.matnr, sku=m.sku, name_th=m.name_th, name_en=m.name_en, variant=m.variant, spec=m.spec, category_id=m.category_id,
        category_name=m.category.name_th if m.category else None, brand_id=m.brand_id, brand_name=m.brand.name if m.brand else None, room=m.room,
        image_url=m.image_url, price=price, price_tier=tier, standard_price=standard, compare_at_price=compare, discount_percent=pct,
        requires_install=m.requires_install, is_takeaway_ok=m.is_takeaway_ok, is_new=m.is_new,
        is_display=catalog_service.is_display_item(m.matnr), pickup_only=catalog_service.pickup_only(m.matnr), tags=list(m.tags or []),
        stock=ProductStockOut(**stock) if stock else None,
    )


def family_of(db: Session, m: Material) -> list[Material]:
    """สินค้าตัวอื่นในรุ่นเดียวกัน — ต่างกันแค่ขนาดหรือสี

    จับด้วย ซีรีส์ + แบรนด์ + หมวด เพราะสามอย่างนี้มาจากฐานเว็บชุดเดียวกัน
    ตรงกันคือของรุ่นเดียวกันจริง (จับด้วยชื่อไม่ได้ เพราะชื่อมีสี/ขนาดต่อท้ายอยู่แล้ว)
    """
    if not m.variant:
        return []
    return db.scalars(
        select(Material)
        .where(
            Material.is_public.is_(True),
            Material.variant == m.variant,
            Material.brand_id == m.brand_id,
            Material.category_id == m.category_id,
        )
        .order_by(Material.matnr)
        .limit(60)
    ).all()


def _color_key(m: Material) -> str:
    """คีย์จับกลุ่มสี — ใช้ชื่อไทยที่ตัดคำว่า "สี" นำหน้าออก ถ้าไม่มีค่อยใช้รหัสจาก SAP

    ทำไมไม่ใช้รหัส SAP อย่างเดียว: เตียงรุ่นเดียวกัน ขนาด 3.5 ฟุตใช้รหัส WHITE
    แต่ 5/6 ฟุตใช้ SNOW WHITE ทั้งที่ภาษาไทยเขียน "สีขาว" กับ "ขาว" — ลูกค้าเห็นเป็นสีขาวเหมือนกัน
    ถ้าแยกตามรหัสจะได้ปุ่มสองปุ่มชื่อเกือบเหมือนกัน ซึ่งงงกว่าเดิม
    ตัดแค่คำว่า "สี" นำหน้าเท่านั้น ไม่ได้เดาว่าสีไหนเหมือนสีไหน
    """
    th = (m.color or "").strip()
    if th:
        return th[2:].strip().lower() if th.startswith("สี") else th.lower()
    return (m.color_code or "").strip().lower()


def variant_axes(db: Session, m: Material, user: User | None) -> tuple[list, list]:
    """ตัวเลือก 2 แกนของหน้าสินค้า: ขนาด กับ สี

    ของเดิมยัดทุกตัวในรุ่นลงช่อง "สี" ช่องเดียว เตียงรุ่นเดียวที่มี 3 ขนาด × 2 สี
    เลยกลายเป็นปุ่มสี 6 ปุ่มที่ชื่อซ้ำกันเอง (ขาว/สีขาว/สีไม้อ่อน/สีโอ๊คอ่อน) เลือกขนาดไม่ได้เลย

    จับกลุ่มด้วย color_code (รหัสสีจาก SAP) ไม่ใช่ color ภาษาไทย เพราะฝั่งไทยเขียนไม่เป็น
    มาตรฐาน — "ขาว" กับ "สีขาว" คือสีเดียวกัน แต่เป็นคนละสตริง

    กดเลือกแกนหนึ่งแล้วพยายามคงอีกแกนไว้ (เลือกขนาด 6 ฟุต ตอนกำลังดูสีโอ๊ค ต้องได้ 6 ฟุตสีโอ๊ค
    ไม่ใช่เด้งไปสีขาว) ถ้าคู่นั้นไม่มีจริงค่อยตกไปตัวแรกที่เจอ
    """
    fam = family_of(db, m)
    if len(fam) < 2:
        return [], []

    def pick(cands: list[Material], keep_attr: str, keep_val) -> Material:
        return next((c for c in cands if getattr(c, keep_attr) == keep_val), cands[0])

    sizes, seen_s = [], set()
    for c in fam:
        key = (c.size_label or "").strip()
        if not key or key in seen_s:
            continue
        seen_s.add(key)
        same = [x for x in fam if (x.size_label or "").strip() == key]
        hit = pick(same, "color_code", m.color_code)
        sizes.append(VariantOptionOut(label=key, matnr=hit.matnr, image_url=hit.image_url,
                                      price=catalog_service.unit_price_for(hit, user)[0]))

    # จับกลุ่มสีสองชั้น เพราะ SAP ไม่นิ่งทั้งสองทาง:
    #   รหัสเดียวกันแต่ชื่อไทยต่างกัน (CANYON OAK = "สีไม้อ่อน" กับ "สีโอ๊คอ่อน")
    #   ชื่อไทยเดียวกันแต่รหัสต่างกัน (WHITE กับ SNOW WHITE = "สีขาว"/"ขาว")
    # ชั้นแรกรวมด้วยรหัส ชั้นสองรวมกลุ่มที่ชื่อไทย (ตัดคำว่า "สี" ออกแล้ว) ตรงกัน
    by_code: dict[str, list[Material]] = {}
    for c in fam:
        by_code.setdefault((c.color_code or "").strip().lower() or _color_key(c), []).append(c)
    merged: dict[str, list[Material]] = {}
    for items in by_code.values():
        merged.setdefault(_color_key(items[0]) or "?", []).extend(items)

    colors = []
    for same in merged.values():
        hit = pick(same, "size_label", m.size_label)
        colors.append(VariantOptionOut(label=(hit.color or "").strip() or "-", matnr=hit.matnr,
                                       image_url=hit.image_url,
                                       price=catalog_service.unit_price_for(hit, user)[0]))

    # แกนที่มีตัวเลือกเดียวไม่ต้องโชว์ — ปุ่มเดียวกดไปก็ไม่เปลี่ยนอะไร
    return (sizes if len(sizes) > 1 else []), (colors if len(colors) > 1 else [])


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


def gallery_of(db: Session, m: Material) -> list[str]:
    """รูปทั้งหมดของสินค้าตัวนี้ เรียงตามลำดับของต้นทาง — ใบหลักมาก่อนเสมอ

    ใบหลัก (materials.image_url) อาจไม่ได้อยู่ใน material_images เพราะมาคนละทาง
    ถ้าไม่ยัดไว้หัวแถว รูปแรกที่ลูกค้าเห็นตอนเปิดหน้าจะไม่ตรงกับรูปบนการ์ดที่เพิ่งกดมา
    """
    urls = list(db.scalars(
        select(MaterialImage.url).where(MaterialImage.matnr == m.matnr)
        .order_by(MaterialImage.position, MaterialImage.url)
    ))
    main = (m.image_url or "").strip()
    if main:
        urls = [main] + [u for u in urls if u != main]
    return urls[:24]


def to_detail(m: Material, user: User | None, stock: dict | None, sizes=None, colors=None,
              cats: list[Category] | None = None, images: list[str] | None = None,
              sites: list | None = None) -> MaterialDetail:
    card = to_card(m, user, stock)
    return MaterialDetail(
        **card.model_dump(), barcode=m.barcode, description=m.description, description_long=m.description_long,
        color=m.color, style=m.style,
        volume_m3=m.volume_m3, weight_kg=m.weight_kg, sold_qty=m.sold_qty, synced_at=m.synced_at,
        related_categories=[CategoryRefOut(id=c.id, name_th=c.name_th) for c in (cats or [])],
        images=images or [], sizes=sizes or [], colors=colors or [],
        stock_sites=[StockSiteOut(plant_code=x.plant_code, name=x.name, qty=x.available_qty) for x in (sites or [])],
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
    # หมวดชุดที่ยกมาจากเว็บจริงผูกสินค้าไว้ในตารางเชื่อม ไม่ได้อยู่ที่ materials.category_id
    # ถ้านับแค่ทางเดียว หมวดพวกนี้จะถูกตัดทิ้งหมดเพราะดูเหมือนไม่มีสินค้า
    for cid, n in db.execute(
        select(MaterialCategory.category_id, func.count())
        .join(Material, Material.matnr == MaterialCategory.matnr)
        .where(Material.is_public.is_(True))
        .group_by(MaterialCategory.category_id)
    ).all():
        counts[cid] = counts.get(cid, 0) + n

    def n_public(cid: str) -> int:
        return counts.get(cid, 0) + sum(n_public(ch.id) for ch in by_parent.get(cid, []))

    # ไล่ลงไปทุกชั้น ไม่ใช่แค่ชั้นเดียว — หมวดชุดที่ยกมาจากเว็บจริงลึก 3 ชั้น
    # (ห้องนอน > ที่นอน > ที่นอนสปริง) ถ้าส่งไปแค่ 2 ชั้น หน้าเว็บจะหาชื่อหมวดชั้นในไม่เจอ
    # แล้วไปโชว์รหัสดิบ (w-826) แทนชื่อบนป้ายตัวกรองกับ breadcrumb
    def children_of(cid: str) -> list[Category]:
        kids = [ch for ch in by_parent.get(cid, []) if n_public(ch.id)]
        # ห้องที่ยกหมวดมาจากเว็บจริงแล้ว ให้เหลือชุดเว็บอย่างเดียว ซ่อนชุดเก่าจาก SAP
        # ไม่งั้นลูกค้าเห็น "ที่นอน" สองอัน (w-955 กับ c3-13) ที่เนื้อหาทับกันแต่ของไม่เท่ากัน
        # ชุดเก่ายังอยู่ในฐานและยังค้นด้วย category เดิมได้ แค่ไม่โผล่ในเมนูลูกค้า
        web = [ch for ch in kids if ch.source == "web"]
        return web or kids

    def node(c: Category, depth: int = 0) -> CategoryOut:
        return CategoryOut(
            id=c.id, name_th=c.name_th, name_en=c.name_en, room=c.room, icon=c.icon,
            children=[node(ch, depth + 1) for ch in children_of(c.id)] if depth < 3 else [],
        )

    return [node(c) for c in by_parent.get(None, []) if n_public(c.id)]


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
    plant: str | None = Query(default=None, description="เฉพาะของที่มีอยู่ที่สาขานี้ (รหัสฝั่ง SAP เช่น S319)"),
    sold_out: bool = Query(default=False, description="เฉพาะของที่หมด — สำหรับพนักงานตามเช็คของที่ขายไม่ได้ (ลูกค้าไม่เห็นของพวกนี้อยู่แล้ว)"),
    has_image: bool = False,
    color: str | None = Query(default=None, description="ชื่อสีแบบไม่ต้องตรงเป๊ะ เช่น ขาว"),
    group: str | None = Query(default=None, description="กลุ่มสินค้าตามตัวขึ้นต้น MATNR — display = สินค้าตัวโชว์"),
    abc: str | None = Query(default=None, max_length=4, description="ชั้นสินค้าจาก SAP (MAABC) — N = ของเข้าใหม่, Z = ขายดี"),
    mode: str = Query(default="auto", description="auto = จับคำก่อนแล้วค่อยตีความ | keyword = จับคำอย่างเดียว | smart = ตีความประโยค"),
    sort: str = Query(default="relevance"),
    seed: int | None = Query(default=None, ge=1, le=2147483646, description="สลับลำดับสินค้าตอนเปิดดูเฉยๆ — ส่งเลขเดิมทุกหน้าของการเลื่อนครั้งเดียวกัน ไม่งั้นของจะซ้ำ/หายระหว่างหน้า"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    facets: bool = Query(default=False, description="ขอ facet มาด้วย (หน้าถัดๆ ไปไม่ต้องขอซ้ำ)"),
    background: BackgroundTasks = None,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    f = catalog_service.SearchFilters(
        q=q, category=category, room=room, tag=tag, brands=brand, min_price=min_price, max_price=max_price,
        discount_only=discount_only, in_stock=in_stock, sold_out=sold_out, plant=plant, has_image=has_image, sort=sort, color=color, mode=mode, group=group,
        seed=seed, abc=abc, include_hidden=bool(user and user.is_staff),
    )
    rows, total = catalog_service.search(db, f, limit, offset)
    matnrs = [m.matnr for m in rows]

    # จำนวนของอ่านจาก cache เท่านั้น — SAP ตอบช้าเป็นสิบวินาที ผูกกับการเลื่อนหน้าไม่ได้
    # ตัวที่หมดอายุให้ job รายชั่วโมงไปเติมเอง (etl/refresh_stock.py)
    stock = product_stock_service.summary_for(db, matnrs)
    # ตัวที่ข้อมูลเก่าเกิน TTL ค่อยไปรีเฟรชหลังส่งหน้านี้ออกไปแล้ว — หน้าเว็บไม่ต้องรอ SAP
    if background is not None and matnrs:
        background.add_task(product_stock_service.refresh_stale_bg, matnrs)
    if q and offset == 0:
        analytics_service.track(db, user, cart_service.anon_token_from(request), "search", query=q, payload={"result_count": total})
        db.commit()
    ip = f.understood
    return SearchOut(
        items=[to_card(m, user, stock.get(m.matnr)) for m in rows], total=total, q=q, category=category,
        facets=FacetsOut(**catalog_service.facets(db, f)) if facets else None,
        corrected=f.corrected, relaxed=f.loose,
        understood=UnderstoodOut(labels=ip.labels, dropped=ip.dropped, category_id=ip.category_id, color=ip.color,
                                 min_price=ip.min_price, max_price=ip.max_price) if ip else None,
    )


@router.get("/materials/suggest", response_model=SuggestOut)
def suggest(
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=6, ge=1, le=10),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """กล่องแนะนำใต้ช่องค้นหา — เรียกทุกครั้งที่พิมพ์ ต้องเบาและไม่เขียนอะไรลงฐาน

    ไม่บันทึกเป็น event ค้นหา เพราะยังไม่นับว่าลูกค้า "ค้น" จริง (นับตอนกด Enter/เข้าหน้าผลลัพธ์)
    ไม่งั้นสถิติคำค้นยอดฮิตจะเต็มไปด้วยคำที่พิมพ์ค้างไว้ครึ่งคำ
    """
    tips, rows = catalog_service.suggest(db, q, include_hidden=bool(user and user.is_staff), limit=limit)
    stock = product_stock_service.summary_for(db, [m.matnr for m in rows])
    return SuggestOut(q=q, suggestions=[SuggestItemOut(**t) for t in tips],
                      items=[to_card(m, user, stock.get(m.matnr)) for m in rows])


@router.get("/materials/{matnr}", response_model=MaterialDetail)
def material_detail(matnr: str, request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    m = catalog_service.get_material(db, matnr)
    # ของที่ข้อมูลไม่ครบไม่โผล่ในผลค้นหาอยู่แล้ว ปิดทางเดาลิงก์ตรงด้วย — แต่พนักงานยังเปิดดูได้
    if not m or (not m.is_public and not (user and user.is_staff)):
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    stock = product_stock_service.summary_for(db, [matnr]).get(matnr)
    analytics_service.track(db, user, cart_service.anon_token_from(request), "view_material", matnr)
    db.commit()
    sizes, colors = variant_axes(db, m, user)
    sites = product_stock_service.sites_for(db, [matnr]).get(matnr, [])
    return to_detail(m, user, stock, sizes, colors, related_categories(db, m), gallery_of(db, m), sites)


@router.get("/materials/{matnr}/stock", response_model=StockOut)
def material_stock(matnr: str, plant: str | None = None, db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    """ยิง SAP สด + log stock_checks ทุกครั้ง · พนักงานเห็นทุกสาขา · ลูกค้าเห็นแค่สาขาที่เลือก/สรุป"""
    if not db.get(Material, matnr):
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    res = stock_service.check_stock(db, user, matnr)
    rows = res.rows
    is_staff = bool(user and user.is_staff)
    # ของที่ต้องรับที่สาขา (ตัวโชว์/ฝากขาย) ลูกค้าต้องเห็นทุกสาขา — ไม่งั้นไม่รู้จะไปดูของที่ไหน
    # ของทั่วไปยังเห็นเฉพาะสาขาที่เลือกเหมือนเดิม (ยอดรายสาขาเป็นข้อมูลภายใน)
    if not is_staff and not catalog_service.pickup_only(matnr):
        rows = [r for r in rows if plant and r.plant_code == plant]
    return StockOut(
        matnr=matnr, source=res.source, stale=res.stale, fetched_at=res.fetched_at, stale_minutes=stock_service.stale_minutes(res.fetched_at),
        available=any(r.available > 0 for r in res.rows), earliest_atp=stock_service.earliest_atp(res.rows),
        rows=[StockRowOut(plant_code=r.plant_code, plant_name=r.plant_name, plant_type=r.plant_type, on_hand=r.on_hand, reserved=r.reserved, available=r.available, atp_date=r.atp_date, note=r.note) for r in rows],
        error=res.error,
    )


@router.get("/pages/{slug}", response_model=InfoPageOut)
def info_page(slug: str, db: Session = Depends(get_db)):
    """หน้าเนื้อหาคงที่ — วิธีสั่งซื้อ / การรับประกัน / นโยบาย ฯลฯ

    เนื้อหายกมาจาก CMS ของเว็บจริงและล้าง script ทิ้งแล้วตั้งแต่ตอน sync
    (ดู etl/sync_cms_pages.py) หน้าเว็บจึงเอาไปใส่ innerHTML ได้
    """
    row = db.get(InfoPage, slug)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบหน้านี้")
    return InfoPageOut(slug=row.slug, title=row.title, body_html=row.body_html, source_url=row.source_url)


# แคชหน้าแรก — ของชิ้นเดียวใช้ร่วมกันทุกคน
#
# ทำไมแคชได้: หน้าแรกไม่มีอะไรขึ้นกับว่าใครเปิด — ทุกคนเห็นราคาเดียวกัน
# (ดู catalog_service.unit_price_for) ถ้าวันหลังมีราคาเฉพาะกลุ่ม ต้องเลิกแคชรวมแบบนี้
#
# ทำไมต้องแคช: ประกอบจาก 8 ส่วน ยิงฐานใหม่ทุกครั้งที่มีคนเข้า รวม ~0.9 วินาที
# ซึ่งเป็นเวลาที่ทุกคนต้องนั่งมองคำว่า "กำลังโหลดหน้าแรก" ทุกครั้งที่เปิดเว็บ
#
# อายุ 1 วัน แต่ไม่ได้รอให้หมดอายุอย่างเดียว — คีย์ผูกกับ "ของเปลี่ยนหรือยัง" ด้วย
# (เวลา sync ล่าสุดของสินค้า + เวลาแก้ไฟล์เนื้อหา) พอ ETL กลางคืนรันเสร็จ คีย์เปลี่ยนเอง
# หน้าแรกจึงสดทันทีโดยไม่ต้องรอครบวันและไม่ต้องสั่งล้างแคชจากที่ไหน
_HOME_TTL = 24 * 60 * 60
_home_cache: dict[str, object] = {"key": None, "at": 0.0, "data": None}


def _home_stamp(db: Session) -> str:
    """ลายเซ็นของข้อมูลที่หน้าแรกใช้ — เปลี่ยนเมื่อไรแปลว่าต้องคำนวณใหม่"""
    synced = db.scalar(select(func.max(Material.synced_at)))
    try:
        mtime = (CONTENT_DIR / "home.json").stat().st_mtime
    except OSError:
        mtime = 0
    return f"{synced}|{mtime}"


@router.get("/home")
def home(db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    stamp = _home_stamp(db)
    if (_home_cache["data"] is not None and _home_cache["key"] == stamp
            and time.time() - float(_home_cache["at"]) < _HOME_TTL):
        return _home_cache["data"]

    with open(CONTENT_DIR / "home.json", encoding="utf-8") as f:
        content = json.load(f)
    # เดิมกรองด้วย tag ของ seed (new/deal/bestseller) ซึ่งข้อมูลจริงแทบไม่มี — ใช้สัญญาณจริงแทน
    # "ของเข้าใหม่" = ชั้น N ของ MAABC ที่ฝ่ายสินค้าจัดไว้ ชุดเดียวกับเมนูสินค้าใหม่ (?abc=N)
    # ไม่ใช่เรียงตามวันที่สร้างรหัส — รหัสเพิ่งถูกสร้างไม่ได้แปลว่าของเพิ่งเข้าร้าน
    # (เกณฑ์เดิมดันสินค้าสั่งทำ MTO ที่เพิ่งตั้งรหัสขึ้นหน้าแรกเป็นของใหม่ ซึ่งไม่ใช่)
    # ถ้ายังไม่มีใครถูกจัดชั้น N ค่อยถอยไปใช้วันที่ — ดีกว่าปล่อยแถวบนหน้าแรกว่าง
    new_rows = strip(db, abc="N", sort="new") or strip(db, sort="new")
    deal_rows = strip(db, sort="discount", discount_only=True)
    best_rows = strip(db, sort="bestseller")
    groups = room_groups(db)
    all_m = new_rows + deal_rows + best_rows + [m for _, rows in groups for m in rows]
    stock = product_stock_service.summary_for(db, [m.matnr for m in all_m])
    content["categories"] = [c.model_dump() for c in category_tree(db)]
    content["new_products"] = [to_card(m, user, stock.get(m.matnr)).model_dump() for m in new_rows]
    content["deals"] = [to_card(m, user, stock.get(m.matnr)).model_dump() for m in deal_rows]
    content["bestsellers"] = [to_card(m, user, stock.get(m.matnr)).model_dump() for m in best_rows]
    # แบรนด์บนหน้าแรก (MVGR1T จาก SAP) — เอาเฉพาะแบรนด์ที่มีสินค้าขายอยู่จริงตอนนี้
    # เดิมส่งทั้งตาราง 143 แบรนด์ ซึ่งส่วนใหญ่ไม่มีสินค้าขึ้นเว็บเลย กดเข้าไปเจอหน้าว่าง
    # นับด้วย facets() = เงื่อนไขชุดเดียวกับหน้าผลค้นหา เลขบนหน้าแรกจึงตรงกับที่เห็นตอนกดเข้าไป
    home_brands = catalog_service.facets(db, catalog_service.SearchFilters())["brands"]
    covers = catalog_service.brand_covers(db, [b["id"] for b in home_brands])
    content["brands"] = [{**b, **covers.get(b["id"], {"matnr": None, "image_url": None})} for b in home_brands]
    content["room_rows"] = [
        {"label": g.name_th, "room": g.id, "href": f"/search?category={g.id}",
         "items": [to_card(m, user, stock.get(m.matnr)).model_dump() for m in rows]}
        for g, rows in groups
    ] or content.get("room_rows", [])
    content.update(home_media(db))
    content["main_nav"] = main_nav(db, content["categories"])
    _home_cache.update(key=stamp, at=time.time(), data=content)
    return content


# สินค้าตัวโชว์ = MATNR ขึ้นต้นด้วย 20 (ดู catalog_matnr_groups) ไม่มีฟิลด์ไหนบอกนอกจากรหัส
# หน้าเว็บส่งชื่อกลุ่มมา ไม่ต้องรู้เลขนำหน้า — วันหลังเปลี่ยนเลขก็แก้ที่ config ที่เดียว
DISPLAY_HREF = "/search?group=display&sort=discount"


def web_nav_groups(db: Session, room: str) -> list[dict]:
    """เมนูของห้องที่ยกหมวดมาจากเว็บจริงแล้ว — คืนเป็นกลุ่ม แต่ละกลุ่มมีหมวดย่อยของตัวเอง

    ต่างจากเมนูห้องอื่นตรงที่มี 3 ชั้น (ห้องนอน > ที่นอน > ที่นอนสปริง) ตามเว็บจริง
    ลำดับใช้ sort ซึ่งคือ position ของเว็บ เมนูจึงเรียงเหมือนกันเป๊ะ
    (ดู etl/sync_web_categories.py)
    """
    rows = db.scalars(
        select(Category).where(Category.source == "web", Category.room == room).order_by(Category.sort, Category.name_th)
    ).all()
    kids: dict[str, list[Category]] = {}
    for c in rows:
        kids.setdefault(c.parent_id or "", []).append(c)

    # หมวดที่เรา "ไม่มีของ" ต้องไม่โผล่ในเมนู — เว็บ SB มีของแต่เราไม่ได้ขายทุกตัว
    # (ที่นอนพ็อคเก็ตสปริง ผ้าคาดเตียง หมอนทั้งหมวด ฯลฯ) กดเข้าไปแล้วเจอหน้าว่างเสียความรู้สึกกว่า
    # นับครั้งเดียวทั้งห้องด้วย query เดียว ไม่ไล่นับทีละหมวด เมนูอยู่บนทุกหน้าจะได้ไม่หน่วง
    have = {
        cid for (cid,) in db.execute(
            select(MaterialCategory.category_id)
            .join(Material, Material.matnr == MaterialCategory.matnr)
            .where(Material.is_public.is_(True), MaterialCategory.category_id.in_([c.id for c in rows]))
            .group_by(MaterialCategory.category_id)
        )
    }
    out = []
    # กลุ่มบนสุด = ตัวที่แขวนอยู่ใต้หมวดห้องเดิม (ดู sync_web_categories)
    # กลุ่มที่ไม่มีหมวดย่อยเลยก็ยังขึ้นได้ ถ้าตัวมันเองมีสินค้า (หมอน · แผ่นรองนอน)
    for g in kids.get(room, []):
        items = [{"label": ch.name_th, "label_en": ch.name_en, "href": f"/search?category={ch.id}"}
                 for ch in kids.get(g.id, []) if ch.id in have]
        if items or g.id in have:
            out.append({"label": g.name_th, "label_en": g.name_en, "href": f"/search?category={g.id}", "items": items})
    return out


def main_nav(db: Session, cats: list[dict]) -> list[dict]:
    """แถบเมนูมาจากต้นไม้หมวดจริง ไม่ใช่รายการตายตัวใน home.json

    หมวดกลุ่ม (ดู GROUPS ใน etl/import_catalog.py) = 1 เมนู · ลูกของมัน = รายการในเมนู

    ห้องที่ยกหมวดมาจากเว็บจริงแล้ว (มีหมวด w-) จะได้เมนูแบบ 3 ชั้นแทน — ใส่มาใน groups
    ส่วนห้องที่ยังไม่ได้ยกมายังใช้ items เหมือนเดิม หน้าเว็บรองรับทั้งสองแบบ
    """
    out = []
    for c in cats:
        if c["id"] not in import_catalog.GROUPS:
            continue
        groups = web_nav_groups(db, c["id"])
        if groups:
            # มีหมวดชุดเว็บแล้ว: หัวเมนูชี้ไปกลุ่มแรก (= หมวดห้องของเว็บจริง) ไม่ใช่หมวด SAP เดิม
            out.append({"label": c["name_th"], "label_en": c.get("name_en"),
                        "href": groups[0]["href"], "items": [], "groups": groups})
        else:
            out.append({"label": c["name_th"], "label_en": c.get("name_en"), "href": f"/search?category={c['id']}",
                        "items": [{"label": ch["name_th"], "label_en": ch.get("name_en"),
                                   "href": f"/search?category={ch['id']}"} for ch in c["children"]]})
    out.append({"label": "สินค้าตัวโชว์", "label_en": "Display Items", "href": DISPLAY_HREF, "items": []})
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
