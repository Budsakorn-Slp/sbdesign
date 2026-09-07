"""ตะกร้า: guest (anon_token) · customer · sales-held (owner_sales_id)
กฎ: ทุกการแก้ตะกร้าเขียน audit_logs + cart_item_history · ราคาในตะกร้าเป็น snapshot เสมอ
"""
import secrets
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.cart import Cart, CartItem, CartItemHistory
from app.models.catalog import Material, StockCache
from app.models.common import utcnow
from app.models.user import User
from app.services import audit_service, catalog_service
from app.services.auth_service import register_login_hook

ANON_COOKIE = "sb_anon"

# hooks ให้ step 5 (websocket) เสียบรับเหตุการณ์ตะกร้าเปลี่ยน
_change_hooks: list = []


def register_change_hook(fn) -> None:
    _change_hooks.append(fn)


def emit(cart: Cart, event: str, payload: dict | None = None) -> None:
    for fn in _change_hooks:
        try:
            fn(cart, event, payload or {})
        except Exception:  # realtime ล้มต้องไม่ทำให้ธุรกรรมหลักล้ม
            pass


# ---------- anon token ----------
def anon_token_from(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.cookies.get(ANON_COOKIE)


def new_anon_token() -> str:
    return secrets.token_urlsafe(24)


# ---------- lookup ----------
def _next_no(db: Session) -> str:
    base = 8823 + int(db.scalar(select(func.count()).select_from(Cart)) or 0)
    while True:
        no = f"#{base}"
        if not db.scalar(select(Cart.id).where(Cart.no == no)):
            return no
        base += 1


def load_cart(db: Session, cart_id: str) -> Cart | None:
    return db.scalar(select(Cart).options(selectinload(Cart.items), selectinload(Cart.customer), selectinload(Cart.owner_sales)).where(Cart.id == cart_id))


def expire_stale_sales_carts(db: Session, sales_id: str) -> None:
    now = utcnow()
    for c in db.scalars(select(Cart).where(Cart.owner_sales_id == sales_id, Cart.status == "open", Cart.expires_at.is_not(None), Cart.expires_at < now)).all():
        c.status = "abandoned"
        c.closed_at = now
        audit_service.log(db, None, "cart.expired", "cart", c.id, {"owner_sales_id": sales_id}, role="system")
    db.commit()


def find_customer_open_cart(db: Session, customer_id: str) -> Cart | None:
    """ตะกร้า open ของลูกค้า — ถ้ามีเซลล์ถืออยู่ (owner_sales_id) จะได้ใบนั้น เพื่อให้ลูกค้าเห็นของที่เซลล์เพิ่มสด ๆ"""
    return db.scalar(
        select(Cart).options(selectinload(Cart.items), selectinload(Cart.customer), selectinload(Cart.owner_sales))
        .where(Cart.customer_user_id == customer_id, Cart.status == "open")
        .order_by(Cart.owner_sales_id.is_(None), Cart.updated_at.desc())
    )


def find_guest_cart(db: Session, token: str) -> Cart | None:
    return db.scalar(select(Cart).options(selectinload(Cart.items)).where(Cart.anon_token == token, Cart.customer_user_id.is_(None), Cart.status == "open"))


def get_or_create_cart(db: Session, user: User | None, anon_token: str | None) -> Cart:
    if user and user.role == "customer":
        cart = find_customer_open_cart(db, user.id)
        if not cart:
            cart = Cart(customer_user_id=user.id, no=_next_no(db), label=user.name)
            db.add(cart)
            db.commit()
            cart = load_cart(db, cart.id)
        return cart
    if user and user.is_staff:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="พนักงานใช้ตะกร้าผ่าน /sales/carts")
    if not anon_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ไม่มี anon token")
    cart = find_guest_cart(db, anon_token)
    if not cart:
        cart = Cart(anon_token=anon_token, no=_next_no(db), label="guest")
        db.add(cart)
        db.commit()
        cart = load_cart(db, cart.id)
    return cart


# ---------- สิทธิ์ ----------
def can_access(cart: Cart, user: User | None, anon_token: str | None) -> bool:
    if not cart.is_open:
        return False
    if user is None:
        return bool(anon_token) and cart.anon_token == anon_token and cart.customer_user_id is None
    if user.role == "customer":
        return cart.customer_user_id == user.id
    if user.role in ("sales", "manager"):
        return cart.owner_sales_id == user.id  # เซลล์เห็นตะกร้าลูกค้าได้เฉพาะตอนถือใบนั้น
    return False


def require_cart(db: Session, cart_id: str, user: User | None, anon_token: str | None) -> Cart:
    cart = load_cart(db, cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="ไม่พบตะกร้า")
    if not can_access(cart, user, anon_token):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงตะกร้านี้")
    return cart


def actor_role(user: User | None) -> str:
    return user.role if user else "guest"


# ---------- ราคา ----------
def price_user_for(cart: Cart, acting: User | None) -> User | None:
    """ราคาที่ใช้ = tier ของลูกค้าเจ้าของตะกร้า (ถ้าผูกแล้ว) ไม่ใช่ของเซลล์"""
    if cart.customer:
        return cart.customer
    if acting and acting.role == "customer":
        return acting
    return None  # guest / ตะกร้าเซลล์ที่ยังไม่ผูกลูกค้า → ราคาปกติ


def resolve_supply_mode(m: Material, requested: str | None, plant_code: str | None) -> str:
    if requested in ("takeaway", "ship", "install", "pickup"):
        if requested == "takeaway" and not m.is_takeaway_ok:
            return "install" if m.requires_install else "ship"
        return requested
    if m.requires_install:
        return "install"
    if plant_code and m.is_takeaway_ok:
        return "takeaway"
    return "ship"


def atp_from_cache(db: Session, matnr: str, plant_code: str | None):
    if not plant_code:
        return None
    row = db.get(StockCache, (matnr, plant_code))
    return row.atp_date if row else None


# ---------- mutations ----------
def _history(db: Session, cart: Cart, matnr: str, action: str, before: int, after: int, actor: User | None) -> None:
    db.add(CartItemHistory(cart_id=cart.id, matnr=matnr, action=action, qty_before=before, qty_after=after, added_by=actor_role(actor), actor_user_id=actor.id if actor else None))


def add_item(db: Session, cart: Cart, actor: User | None, matnr: str, qty: int, supply_mode: str | None, plant_code: str | None, note: str | None = None) -> CartItem:
    if qty < 1:
        raise HTTPException(status_code=422, detail="จำนวนต้องอย่างน้อย 1")
    m = catalog_service.get_material(db, matnr)
    if not m:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    by_sales = bool(actor and actor.is_staff)
    mode = resolve_supply_mode(m, supply_mode, plant_code)
    price, tier = catalog_service.unit_price_for(m, price_user_for(cart, actor))
    existing = next((it for it in cart.items if it.matnr == matnr and it.supply_mode == mode and (it.plant_code or None) == (plant_code or None) and it.added_by == ("sales" if by_sales else "customer")), None)
    if existing:
        before = existing.qty
        existing.qty += qty
        if note:
            existing.note = note
        item = existing
        _history(db, cart, matnr, "update", before, item.qty, actor)
    else:
        item = CartItem(
            cart_id=cart.id, matnr=m.matnr, sku=m.sku, name_snapshot=m.name_th, variant_snapshot=m.variant, spec_snapshot=m.spec, image_url=m.image_url,
            category_id=m.category_id, qty=qty, unit_price_snapshot=price, price_tier=tier, added_by="sales" if by_sales else "customer",
            added_by_user_id=actor.id if actor else None, pending_ack=by_sales and cart.customer_user_id is not None, supply_mode=mode,
            plant_code=plant_code, atp_date=atp_from_cache(db, matnr, plant_code), requires_install=m.requires_install, note=note,
        )
        db.add(item)
        cart.items.append(item)
        _history(db, cart, matnr, "add", 0, qty, actor)
    cart.updated_at = utcnow()
    audit_service.log(db, actor, "cart.item_add", "cart", cart.id, {"matnr": matnr, "qty": qty, "supply_mode": mode, "plant_code": plant_code, "unit_price": str(price)})
    db.commit()
    db.refresh(item)
    emit(cart, "item_added", {"item_id": item.id, "matnr": matnr, "qty": item.qty, "added_by": item.added_by, "by_name": actor.name if actor else None})
    return item


def _get_item(cart: Cart, item_id: str) -> CartItem:
    item = next((it for it in cart.items if it.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="ไม่พบรายการในตะกร้า")
    return item


def update_item(db: Session, cart: Cart, actor: User | None, item_id: str, qty: int | None, supply_mode: str | None, plant_code: str | None, note: str | None) -> CartItem:
    item = _get_item(cart, item_id)
    before = item.qty
    if qty is not None:
        if qty < 1:
            raise HTTPException(status_code=422, detail="จำนวนต้องอย่างน้อย 1 (ใช้ลบถ้าไม่ต้องการ)")
        item.qty = qty
    if supply_mode is not None or plant_code is not None:
        m = catalog_service.get_material(db, item.matnr)
        pc = plant_code if plant_code is not None else item.plant_code
        item.plant_code = pc or None
        item.supply_mode = resolve_supply_mode(m, supply_mode or item.supply_mode, item.plant_code) if m else (supply_mode or item.supply_mode)
        item.atp_date = atp_from_cache(db, item.matnr, item.plant_code)
    if note is not None:
        item.note = note
    _history(db, cart, item.matnr, "update", before, item.qty, actor)
    cart.updated_at = utcnow()
    audit_service.log(db, actor, "cart.item_update", "cart", cart.id, {"item_id": item.id, "matnr": item.matnr, "qty_before": before, "qty_after": item.qty, "supply_mode": item.supply_mode})
    db.commit()
    db.refresh(item)
    emit(cart, "item_updated", {"item_id": item.id, "matnr": item.matnr, "qty": item.qty})
    return item


def remove_item(db: Session, cart: Cart, actor: User | None, item_id: str) -> None:
    item = _get_item(cart, item_id)
    _history(db, cart, item.matnr, "remove", item.qty, 0, actor)
    audit_service.log(db, actor, "cart.item_remove", "cart", cart.id, {"item_id": item.id, "matnr": item.matnr, "qty": item.qty, "was_added_by": item.added_by})
    payload = {"item_id": item.id, "matnr": item.matnr}
    cart.items.remove(item)
    db.delete(item)
    cart.updated_at = utcnow()
    db.commit()
    emit(cart, "item_removed", payload)


def ack_item(db: Session, cart: Cart, actor: User | None, item_id: str) -> CartItem:
    """ลูกค้ากด 'เก็บไว้' ของที่เซลล์เพิ่มให้"""
    item = _get_item(cart, item_id)
    item.pending_ack = False
    _history(db, cart, item.matnr, "ack", item.qty, item.qty, actor)
    audit_service.log(db, actor, "cart.item_ack", "cart", cart.id, {"item_id": item.id, "matnr": item.matnr})
    db.commit()
    db.refresh(item)
    emit(cart, "item_acked", {"item_id": item.id, "matnr": item.matnr})
    return item


def merge_carts(db: Session, source: Cart, target: Cart, actor: User | None) -> Cart:
    """ย้ายทุกรายการจาก source เข้า target แล้วปิด source เป็น merged"""
    if source.id == target.id:
        return target
    moved = 0
    for it in list(source.items):
        same = next((t for t in target.items if t.matnr == it.matnr and t.supply_mode == it.supply_mode and (t.plant_code or None) == (it.plant_code or None) and t.added_by == it.added_by), None)
        if same:
            before = same.qty
            same.qty += it.qty
            _history(db, target, it.matnr, "update", before, same.qty, actor)
            source.items.remove(it)
            db.delete(it)
        else:
            source.items.remove(it)
            it.cart_id = target.id
            target.items.append(it)
            _history(db, target, it.matnr, "add", 0, it.qty, actor)
        moved += 1
    # ราคา snapshot ของ guest เป็นราคาปกติ → คิดใหม่ตาม tier ลูกค้าเจ้าของตะกร้าปลายทาง
    reprice(db, target)
    source.status = "merged"
    source.merged_into_cart_id = target.id
    source.closed_at = utcnow()
    target.updated_at = utcnow()
    audit_service.log(db, actor, "cart.merge", "cart", target.id, {"source_cart_id": source.id, "moved": moved})
    db.commit()
    emit(target, "cart_merged", {"source_cart_id": source.id, "moved": moved})
    return load_cart(db, target.id)


def reprice(db: Session, cart: Cart) -> None:
    pu = price_user_for(cart, None)
    for it in cart.items:
        m = catalog_service.get_material(db, it.matnr)
        if m:
            it.unit_price_snapshot, it.price_tier = catalog_service.unit_price_for(m, pu)


# ---------- totals ----------
def totals(cart: Cart) -> dict:
    subtotal = sum((it.line_total for it in cart.items), Decimal(0))
    return {"count": sum(it.qty for it in cart.items), "subtotal": subtotal, "pending_count": sum(1 for it in cart.items if it.pending_ack)}


# ---------- login hook: guest cart -> customer cart ----------
def merge_guest_cart_on_login(db: Session, user: User, request: Request | None) -> None:
    if user.role != "customer":
        return
    token = anon_token_from(request)
    if not token:
        return
    guest = find_guest_cart(db, token)
    if not guest or not guest.items:
        return
    target = get_or_create_cart(db, user, None)
    merge_carts(db, guest, target, user)


register_login_hook(merge_guest_cart_on_login)


def sales_cart_ttl() -> timedelta:
    return timedelta(hours=get_settings().sales_cart_ttl_hours)
