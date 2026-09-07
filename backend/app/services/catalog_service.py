from datetime import date
from decimal import Decimal

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.integrations.sap.base import MaterialDTO
from app.models.catalog import Brand, Category, Material, MaterialPrice, Plant, StockCache
from app.models.common import utcnow
from app.models.user import User


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
    ids = [category_id]
    ids += [c.id for c in db.scalars(select(Category).where(Category.parent_id == category_id))]
    return ids


def search(db: Session, q: str | None, category: str | None, room: str | None, tag: str | None, limit: int = 24, offset: int = 0) -> tuple[list[Material], int]:
    stmt = select(Material).options(selectinload(Material.prices), selectinload(Material.category), selectinload(Material.brand))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Material.name_th.ilike(like), Material.name_en.ilike(like), Material.matnr.ilike(like), Material.sku.ilike(like), Material.barcode == q.strip(), Material.variant.ilike(like)))
    if category:
        stmt = stmt.where(Material.category_id.in_(descendant_category_ids(db, category)))
    if room:
        stmt = stmt.where(Material.room == room)
    if tag == "new":
        stmt = stmt.where(Material.is_new.is_(True))
    elif tag:
        stmt = stmt.where(cast(Material.tags, String).like(f'%"{tag}"%'))  # JSON text match - พอสำหรับ seed 20 ตัว
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Material.name_th).offset(offset).limit(limit)).all()
    return list(rows), int(total)


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
