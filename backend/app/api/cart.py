from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.models.cart import Cart, CartItem
from app.models.user import User
from app.schemas.cart import AddItemIn, CartItemOut, CartOut, CartPersonOut, MergeIn, UpdateItemIn
from app.services import cart_service

router = APIRouter(tags=["cart"])


def person(u: User | None) -> CartPersonOut | None:
    if not u:
        return None
    return CartPersonOut(id=u.id, name=u.name, tier=u.tier, sap_customer_no=u.sap_customer_no, staff_code=u.staff_code, phone=u.phone, branch_id=u.branch_id)


def item_out(it: CartItem) -> CartItemOut:
    u = it.added_by_user
    return CartItemOut(
        id=it.id, matnr=it.matnr, sku=it.sku, name=it.name_snapshot, variant=it.variant_snapshot, spec=it.spec_snapshot, image_url=it.image_url, category_id=it.category_id,
        qty=it.qty, unit_price=it.unit_price_snapshot, price_tier=it.price_tier, line_total=it.line_total, added_by=it.added_by, added_by_name=u.name if u else None,
        added_by_code=u.staff_code if u else None, added_at=it.added_at, pending_ack=it.pending_ack, supply_mode=it.supply_mode, plant_code=it.plant_code, atp_date=it.atp_date,
        requires_install=it.requires_install, note=it.note,
    )


def cart_out(cart: Cart, db: Session | None = None) -> CartOut:
    t = cart_service.totals(cart)
    totals = None
    if db is not None:
        from app.api.promo import totals_out  # หลีกเลี่ยง circular import

        totals = totals_out(db, cart)
    return CartOut(
        id=cart.id, no=cart.no, label=cart.label, status=cart.status, customer=person(cart.customer), owner_sales=person(cart.owner_sales),
        is_guest=cart.customer_user_id is None and cart.owner_sales_id is None, items=[item_out(it) for it in cart.items], count=t["count"], subtotal=t["subtotal"],
        pending_count=t["pending_count"], expires_at=cart.expires_at, updated_at=cart.updated_at, totals=totals,
    )


class CartCtx:
    """แก้ปัญหา anon cookie: ถ้า guest ยังไม่มี token ให้สร้างและ set cookie กลับไป"""

    def __init__(self, request: Request, response: Response, user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
        self.db = db
        self.user = user
        self.anon = cart_service.anon_token_from(request)
        if user is None and not self.anon:
            self.anon = cart_service.new_anon_token()
            response.set_cookie(cart_service.ANON_COOKIE, self.anon, max_age=60 * 60 * 24 * 90, samesite="lax", httponly=False)

    def current(self) -> Cart:
        return cart_service.get_or_create_cart(self.db, self.user, self.anon)

    def by_id(self, cart_id: str) -> Cart:
        return cart_service.require_cart(self.db, cart_id, self.user, self.anon)


@router.get("/cart", response_model=CartOut)
def get_cart(ctx: CartCtx = Depends()):
    """ตะกร้าของ user/anon ปัจจุบัน (ลูกค้าจะได้ใบที่เซลล์ถืออยู่ถ้ามี)"""
    return cart_out(ctx.current(), ctx.db)


@router.post("/cart/items", response_model=CartOut, status_code=201)
def add_item(body: AddItemIn, ctx: CartCtx = Depends()):
    cart = ctx.current()
    cart_service.add_item(ctx.db, cart, ctx.user, body.matnr, body.qty, body.supply_mode, body.plant_code, body.note)
    return cart_out(cart_service.load_cart(ctx.db, cart.id), ctx.db)


@router.patch("/cart/items/{item_id}", response_model=CartOut)
def update_item(item_id: str, body: UpdateItemIn, ctx: CartCtx = Depends()):
    cart = ctx.current()
    cart_service.update_item(ctx.db, cart, ctx.user, item_id, body.qty, body.supply_mode, body.plant_code, body.note)
    return cart_out(cart_service.load_cart(ctx.db, cart.id), ctx.db)


@router.delete("/cart/items/{item_id}", response_model=CartOut)
def remove_item(item_id: str, ctx: CartCtx = Depends()):
    cart = ctx.current()
    cart_service.remove_item(ctx.db, cart, ctx.user, item_id)
    return cart_out(cart_service.load_cart(ctx.db, cart.id), ctx.db)


@router.post("/cart/items/{item_id}/ack", response_model=CartOut)
def ack_item(item_id: str, ctx: CartCtx = Depends()):
    """ลูกค้ากด 'เก็บไว้' รายการที่พนักงานเพิ่มให้"""
    cart = ctx.current()
    cart_service.ack_item(ctx.db, cart, ctx.user, item_id)
    return cart_out(cart_service.load_cart(ctx.db, cart.id), ctx.db)


@router.post("/carts/{cart_id}/merge", response_model=CartOut)
def merge(cart_id: str, body: MergeIn, ctx: CartCtx = Depends()):
    """รวม source เข้า cart_id — ต้องมีสิทธิ์ทั้งสองใบ"""
    target = ctx.by_id(cart_id)
    source = ctx.by_id(body.source_cart_id)
    return cart_out(cart_service.merge_carts(ctx.db, source, target, ctx.user), ctx.db)


@router.post("/cart/checkout-check")
def checkout_check(ctx: CartCtx = Depends()):
    """guest กดชำระเงินไม่ได้ — บังคับที่ backend (ขั้นตอนชำระเงินจริงอยู่ที่ /checkout ใน STEP 8-9)"""
    if ctx.user is None:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบหรือลงทะเบียนก่อนชำระเงิน")
    if ctx.user.role != "customer":
        raise HTTPException(status_code=403, detail="เฉพาะลูกค้าเท่านั้นที่ชำระเงินเองได้")
    cart = ctx.current()
    if not cart.items:
        raise HTTPException(status_code=400, detail="ตะกร้าว่าง")
    t = cart_service.totals(cart)
    return {"ok": True, "cart_id": cart.id, "count": t["count"], "subtotal": t["subtotal"]}
