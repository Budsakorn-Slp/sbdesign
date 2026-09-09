import re
from datetime import date
from decimal import Decimal

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.integrations.sap.base import MaterialDTO
from app.models.catalog import Brand, Category, Material, MaterialPrice, Plant, StockCache
from app.models.common import utcnow
from app.models.user import User


def web_matnr_prefixes() -> tuple[str, ...]:
    return tuple(p.strip() for p in get_settings().catalog_matnr_prefixes.split(",") if p.strip())


def is_web_visible(matnr: str) -> bool:
    """สินค้ากลุ่มไหนโชว์บนเว็บได้ — ดูจากตัวขึ้นต้นของ MATNR (ดู catalog_matnr_prefixes)

    ตัดสินที่นี่ที่เดียว แล้วเก็บผลลงธง is_public ตอน import ทุกหน้าที่เช็ค is_public
    อยู่แล้วจึงกรองตามไปเอง ไม่ต้องไล่เติม where ทีละ query (มีจุดที่หลุดง่ายหลายจุด)
    """
    pre = web_matnr_prefixes()
    return not pre or (matnr or "").startswith(pre)


def price_tier_for(user: User | None) -> str:
    """guest เห็นราคาปกติ · ลูกค้าเห็นราคาตาม tier · พนักงานเห็นราคาสมาชิก Gold เพื่อเสนอลูกค้า"""
    if not user:
        return "standard"
    if user.role == "customer":
        return user.tier or "standard"
    return "Gold"


def prices_of(m: Material) -> dict[str, Decimal]:
    today = date.today()
    out: dict[str, Decimal] = {}
    for p in m.prices:
        if (p.valid_from and today < p.valid_from) or (p.valid_to and today > p.valid_to):
            continue
        out[p.tier] = p.price
    return out


def unit_price_for(m: Material, user: User | None) -> tuple[Decimal, str]:
    prices = prices_of(m)
    tier = price_tier_for(user)
    if tier in prices:
        return prices[tier], tier
    return prices.get("standard", Decimal(0)), "standard"


def get_material(db: Session, matnr: str) -> Material | None:
    return db.scalar(select(Material).options(selectinload(Material.prices), selectinload(Material.category), selectinload(Material.brand)).where(Material.matnr == matnr))


def descendant_category_ids(db: Session, category_id: str) -> list[str]:
    """ไล่ลงทั้งกิ่ง ไม่ใช่แค่ชั้นเดียว — ต้นไม้หมวดลึก 3 ชั้นแล้ว (กลุ่มเมนู > c3 > c4)
    และสินค้าเกาะอยู่ที่ใบ ถ้าไล่แค่ชั้นเดียวหมวดกลุ่มจะค้นแล้วไม่เจออะไรเลย
    """
    ids = [category_id]
    frontier = [category_id]
    for _ in range(4):  # กันวนไม่รู้จบถ้าข้อมูลหมวดพันกันเอง
        if not frontier:
            break
        frontier = [c for c in db.scalars(select(Category.id).where(Category.parent_id.in_(frontier))) if c not in ids]
        ids += frontier
    return ids


SORTS = ("relevance", "price_asc", "price_desc", "discount", "new", "bestseller")

# ราคาปกติ/ราคาก่อนลด แยกเป็น subquery ไว้ join — เอาไว้ทั้งกรอง เรียง และหาช่วงราคา
_STD = select(MaterialPrice.matnr, MaterialPrice.price.label("price")).where(MaterialPrice.tier == "standard").subquery()
_CMP = select(MaterialPrice.matnr, MaterialPrice.price.label("compare_at")).where(MaterialPrice.tier == "compare_at").subquery()

# ตัวที่มีรูปขึ้นก่อน — ตอนนี้ต้นทาง Magento มีรูปแค่ ~22% ถ้าเรียงตามชื่อล้วน
# หน้าแรกจะเต็มไปด้วยกล่องเปล่า
_NO_IMAGE = case((or_(Material.image_url.is_(None), Material.image_url == ""), 1), else_=0)


def _tokens(q: str) -> list[str]:
    """ตัดคำค้นเป็นคำๆ — จำกัด 6 คำ กันคนวางทั้งย่อหน้ามาแล้วคิวรียาวเกินจำเป็น"""
    return [t for t in re.split(r"\s+", q.strip()) if t][:6]


def _haystack():
    """กองข้อความที่ให้ค้น — รวมชื่อ รหัส รุ่น สเปก แบรนด์ และชื่อหมวดไว้ก้อนเดียว

    ทำแบบนี้เพื่อให้พิมพ์ข้ามฟิลด์ได้ เช่น "koncept เตียง" (แบรนด์ + ชื่อ)
    หรือ "โซฟา 3 ที่นั่ง" ที่คำกระจายอยู่คนละช่อง
    """
    return func.concat_ws(
        " ", Material.name_th, func.coalesce(Material.name_en, ""), func.coalesce(Material.name_raw, ""),
        func.coalesce(Material.variant, ""),
        func.coalesce(Material.spec, ""), func.coalesce(Material.sku, ""), Material.matnr,
        func.coalesce(Material.color, ""), func.coalesce(Material.style, ""),
        func.coalesce(Brand.name, ""), func.coalesce(Category.name_th, ""),
    )


def _score(q: str):
    """คะแนนความตรง — ยิ่งตรงตัวยิ่งสูง ใช้เรียงผลตอนโหมด "แนะนำ"

    ลำดับความสำคัญ: รหัสตรงเป๊ะ > รหัสขึ้นต้นด้วย > ชื่อขึ้นต้นด้วย > ชื่อมีคำนี้ > แบรนด์/อย่างอื่น
    """
    pre, any_ = f"{q}%", f"%{q}%"
    return case(
        (or_(Material.matnr == q, Material.sku == q, Material.barcode == q), 100),
        (or_(Material.matnr.like(pre), func.coalesce(Material.sku, "").like(pre)), 90),
        (Material.name_th.ilike(pre), 80),
        (Material.name_th.ilike(any_), 65),
        (func.coalesce(Material.name_en, "").ilike(any_), 55),
        (func.coalesce(Material.variant, "").ilike(any_), 50),
        (func.coalesce(Brand.name, "").ilike(any_), 45),
        else_=20,
    )


def _filtered(db: Session, f: "SearchFilters"):
    """เงื่อนไขร่วมของทั้งผลค้นหาและ facet — join ราคาไว้เสมอ (สินค้า 1 ตัวมีราคาปกติแถวเดียว ไม่บานปลาย)"""
    stmt = (
        select(Material)
        .outerjoin(_STD, _STD.c.matnr == Material.matnr)
        .outerjoin(_CMP, _CMP.c.matnr == Material.matnr)
        .outerjoin(Brand, Brand.id == Material.brand_id)
        .outerjoin(Category, Category.id == Material.category_id)
    )
    # ของที่ข้อมูลไม่ครบ (ไม่มีรูป/ไม่มีราคา/ชื่อยังเป็นรหัสโรงงาน) ลูกค้าไม่ควรเห็น
    # แต่เซลล์/แอดมินต้องค้นเจอ ไม่งั้นเช็คสต็อกให้ลูกค้าหน้าร้านไม่ได้
    if not f.include_hidden:
        stmt = stmt.where(Material.is_public.is_(True))
    if f.q:
        q = f.q.strip()
        hay = _haystack()
        # รหัสตรงเป๊ะต้องเจอเสมอ ต่อให้คำอื่นไม่เข้าเงื่อนไข — คนสแกนบาร์โค้ด/พิมพ์ MATNR มาต้องได้ตัวนั้น
        exact = or_(Material.matnr == q, Material.sku == q, Material.barcode == q)
        parts = [hay.ilike(f"%{t}%") for t in _tokens(q)]
        if parts:
            # ปกติต้องเข้าครบทุกคำ (แคบแต่แม่น) — ถ้าไม่เจอเลย search() จะสั่งผ่อนเป็น "คำใดคำหนึ่ง" ให้เอง
            joined = or_(*parts) if f.loose else and_(*parts)
            stmt = stmt.where(or_(exact, joined))
        else:
            stmt = stmt.where(exact)
    if f.category:
        stmt = stmt.where(Material.category_id.in_(descendant_category_ids(db, f.category)))
    if f.room:
        stmt = stmt.where(Material.room == f.room)
    if f.tag == "new":
        stmt = stmt.where(Material.is_new.is_(True))
    elif f.tag:
        stmt = stmt.where(cast(Material.tags, String).like(f'%"{f.tag}"%'))  # JSON text match - พอสำหรับ seed 20 ตัว
    if f.min_price is not None:
        stmt = stmt.where(_STD.c.price >= f.min_price)
    if f.max_price is not None:
        stmt = stmt.where(_STD.c.price <= f.max_price)
    if f.discount_only:
        stmt = stmt.where(_CMP.c.compare_at > _STD.c.price)
    if f.has_image:
        stmt = stmt.where(Material.image_url.isnot(None), Material.image_url != "")
    if f.in_stock:
        # cache สรุปเป็นสาขา ต้องมีสาขาไหนสักสาขาที่เหลือของ
        avail = select(StockCache.matnr).where(StockCache.on_hand - StockCache.reserved > 0)
        stmt = stmt.where(Material.matnr.in_(avail))
    return stmt


class SearchFilters:
    """พารามิเตอร์ค้นหาชุดเดียว ส่งต่อระหว่าง API / ผลลัพธ์ / facet โดยไม่ต้องไล่ส่งทีละตัว"""

    __slots__ = ("q", "category", "room", "tag", "brands", "min_price", "max_price", "discount_only", "in_stock", "has_image", "sort", "loose", "include_hidden")

    def __init__(self, q=None, category=None, room=None, tag=None, brands=None, min_price=None, max_price=None, discount_only=False, in_stock=False, has_image=False, sort="relevance", include_hidden=False):
        self.q, self.category, self.room, self.tag = q, category, room, tag
        self.include_hidden = include_hidden  # เฉพาะพนักงาน — เห็นของที่ยังไม่พร้อมขายออนไลน์ด้วย
        self.brands = [b for b in (brands or []) if b]
        self.min_price, self.max_price = min_price, max_price
        self.discount_only, self.in_stock, self.has_image = discount_only, in_stock, has_image
        self.sort = sort if sort in SORTS else "relevance"
        self.loose = False  # ผ่อนเป็น "เข้าคำใดคำหนึ่ง" — search() เปิดให้เองเมื่อค้นแบบครบทุกคำแล้วไม่เจอ


def _ordered(stmt, sort: str, q: str | None = None):
    """matnr ต่อท้ายทุกแบบเพื่อให้ลำดับนิ่ง ไม่งั้นค่าซ้ำกันแล้วเลื่อนหน้าถัดไปสินค้าจะซ้ำ/หายเอง"""
    if sort == "relevance" and q and q.strip():
        # มีคำค้น = เรียงตามความตรงก่อน แล้วค่อยตัวมีรูป/ขายดี ไม่ใช่เรียงตามชื่อเฉยๆ
        return stmt.order_by(_score(q.strip()).desc(), _NO_IMAGE, Material.sold_qty.desc(), Material.matnr)
    if sort == "price_asc":
        return stmt.order_by(_STD.c.price.asc(), Material.matnr)
    if sort == "price_desc":
        return stmt.order_by(_STD.c.price.desc(), Material.matnr)
    if sort == "discount":
        return stmt.order_by((_CMP.c.compare_at - _STD.c.price).desc().nullslast(), Material.matnr)
    if sort == "new":
        return stmt.order_by(Material.created_at.desc().nullslast(), Material.matnr)
    if sort == "bestseller":
        # ชั้น Z (MAABC) ขึ้นก่อนเสมอ — เป็นการจัดชั้นจากยอดขายจริงทั้งบริษัท
        # sold_qty เป็นตัวรอง เพราะนับเฉพาะยอดที่สั่งผ่านเว็บ ของขายดีหน้าร้านจะได้ 0
        return stmt.order_by(Material.is_bestseller.desc(), Material.sold_qty.desc(), _NO_IMAGE, Material.matnr)
    return stmt.order_by(_NO_IMAGE, Material.name_th, Material.matnr)


def search(db: Session, f: SearchFilters, limit: int = 24, offset: int = 0) -> tuple[list[Material], int]:
    rows, total = _run(db, f, limit, offset)
    # พิมพ์หลายคำแล้วไม่เจอสักตัว มักเป็นเพราะมีคำเกินมาคำเดียว — ลองใหม่แบบเข้าคำใดคำหนึ่ง
    # (คะแนนความตรงจะดันตัวที่เข้าหลายคำขึ้นบนอยู่แล้ว) ดีกว่าโชว์ "ไม่พบสินค้า"
    if total == 0 and f.q and not f.loose and len(_tokens(f.q)) > 1:
        f.loose = True
        rows, total = _run(db, f, limit, offset)
    return rows, total


def _run(db: Session, f: SearchFilters, limit: int, offset: int) -> tuple[list[Material], int]:
    stmt = _filtered(db, f)
    if f.brands:
        stmt = stmt.where(Material.brand_id.in_(f.brands))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.options(selectinload(Material.prices), selectinload(Material.category), selectinload(Material.brand))
    rows = db.scalars(_ordered(stmt, f.sort, f.q).offset(offset).limit(limit)).all()
    return list(rows), int(total)


def facets(db: Session, f: SearchFilters, brand_limit: int = 60) -> dict:
    """ตัวเลือกที่ยังเลือกได้จริงของผลค้นหาชุดนี้ + จำนวนของแต่ละตัว

    นับแบรนด์โดย "ไม่" ใส่ตัวกรองแบรนด์เข้าไป ไม่งั้นพอเลือกแบรนด์หนึ่งแล้ว
    ตัวเลือกอื่นจะหายหมด กลับไปเลือกแบรนด์อื่นไม่ได้
    """
    base = _filtered(db, f).with_only_columns(Material.brand_id.label("brand_id"), _STD.c.price.label("price")).subquery()
    rows = db.execute(
        select(Brand.id, Brand.name, func.count()).select_from(base).join(Brand, Brand.id == base.c.brand_id).group_by(Brand.id, Brand.name).order_by(func.count().desc(), Brand.name)
    ).all()
    lo, hi = db.execute(select(func.min(base.c.price), func.max(base.c.price))).first() or (None, None)
    chosen = set(f.brands)
    # แบรนด์ที่ผู้ใช้เลือกไว้ต้องอยู่ในลิสต์เสมอ ไม่งั้นติ๊กออกไม่ได้เมื่อมันหลุด top N
    top = [r for r in rows[:brand_limit]] + [r for r in rows[brand_limit:] if r[0] in chosen]
    return {
        "brands": [{"id": bid, "name": name, "count": int(n)} for bid, name, n in top],
        "price_min": float(lo) if lo is not None else None,
        "price_max": float(hi) if hi is not None else None,
    }


def stock_summary(db: Session, matnrs: list[str]) -> dict[str, dict]:
    """สรุปจาก cache (โชว์ในผลค้นหาโดยไม่ยิง SAP ทุก keystroke)"""
    if not matnrs:
        return {}
    rows = db.scalars(select(StockCache).where(StockCache.matnr.in_(matnrs))).all()
    out: dict[str, dict] = {}
    for r in rows:
        d = out.setdefault(r.matnr, {"available_total": 0, "store_available": 0, "warehouse_available": 0, "fetched_at": None})
        avail = max(0, r.on_hand - r.reserved)
        d["available_total"] += avail
        d["fetched_at"] = r.fetched_at
    plants = {p.plant_code: p for p in db.scalars(select(Plant)).all()}
    for r in rows:
        if r.matnr in out:
            avail = max(0, r.on_hand - r.reserved)
            p = plants.get(r.plant_code)
            if p and p.type == "warehouse":
                out[r.matnr]["warehouse_available"] += avail
            else:
                out[r.matnr]["store_available"] += avail
    return out


# ---------- sync จาก SAP -> mirror (Group B) ----------
def upsert_materials(db: Session, items: list[MaterialDTO]) -> int:
    n = 0
    for dto in items:
        m = db.get(Material, dto.matnr)
        if not m:
            m = Material(matnr=dto.matnr, sku=dto.sku, name_th=dto.name_th)
            db.add(m)
            n += 1
        m.sku = dto.sku
        m.barcode = dto.barcode
        m.name_th = dto.name_th
        m.name_en = dto.name_en
        m.variant = dto.variant
        m.spec = dto.spec
        m.description = dto.description
        m.category_id = dto.category_id
        m.brand_id = dto.brand_id
        m.room = dto.room
        m.image_url = dto.image_url
        m.requires_install = dto.requires_install
        m.is_takeaway_ok = dto.is_takeaway_ok
        m.is_new = dto.is_new
        m.volume_m3 = Decimal(str(dto.volume_m3)) if dto.volume_m3 is not None else None
        m.weight_kg = Decimal(str(dto.weight_kg)) if dto.weight_kg is not None else None
        m.tags = dto.tags
        m.synced_at = utcnow()
        db.flush()
        existing = {p.tier: p for p in db.scalars(select(MaterialPrice).where(MaterialPrice.matnr == m.matnr)).all()}
        for tier, price in dto.prices.items():
            if tier in existing:
                existing[tier].price = Decimal(str(price))
            else:
                db.add(MaterialPrice(matnr=m.matnr, tier=tier, price=Decimal(str(price))))
    db.commit()
    return n


def upsert_taxonomy(db: Session, categories: list[dict], brands: list[dict]) -> None:
    for c in categories:
        if not db.get(Category, c["id"]):
            db.add(Category(id=c["id"], name_th=c["name_th"], name_en=c.get("name_en"), room=c.get("room"), icon=c.get("icon"), sort=c.get("sort", 0)))
        db.flush()
        for i, ch in enumerate(c.get("children", [])):
            if not db.get(Category, ch["id"]):
                db.add(Category(id=ch["id"], name_th=ch["name_th"], parent_id=c["id"], room=c.get("room"), sort=i))
    for b in brands:
        if not db.get(Brand, b["id"]):
            db.add(Brand(id=b["id"], name=b["name"]))
    db.commit()


def upsert_plants(db: Session, plants: list[dict]) -> None:
    for p in plants:
        row = db.get(Plant, p["plant_code"])
        if not row:
            row = Plant(plant_code=p["plant_code"], name=p["name"], type=p["type"])
            db.add(row)
        row.name = p["name"]
        row.type = p["type"]
        row.zone_codes = p.get("zone_codes")
        row.address = p.get("address")
    db.commit()
