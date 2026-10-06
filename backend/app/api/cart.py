from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.core.config import get_settings
from app.db.session import get_db
from app.models.cart import Cart, CartItem
from app.models.user import User
from app.schemas.cart import CartSiteOut, AddItemIn, CartItemOut, CartOut, CartStaffOut, CartPersonOut, DeliveryInfoOut, MergeIn, PresoReadyOut, SelectIn, ShipToIn, UpdateItemIn
from app.schemas.catalog import ProductStockOut
from app.services import cart_service, catalog_service, product_stock_service, staff_shipping_service

router = APIRouter(tags=["cart"])


def person(u: User | None) -> CartPersonOut | None:
    if not u:
        return None
    return CartPersonOut(id=u.id, name=u.name, points=u.points, sap_customer_no=u.sap_customer_no, staff_code=u.staff_code, phone=u.phone, branch_id=u.branch_id, email=u.email, default_address=u.default_address, default_postcode=u.default_postcode)


def item_out(it: CartItem, stock: dict | None = None, sites: list | None = None) -> CartItemOut:
    u = it.added_by_user
    charge = staff_shipping_service.is_charge_line(it)
    return CartItemOut(
        stock=ProductStockOut(**stock) if stock else None,
        group=catalog_service.group_of(it.matnr), pickup_only=catalog_service.pickup_only(it.matnr),
        id=it.id, matnr=it.matnr, sku=it.sku, name=it.name_snapshot, variant=it.variant_snapshot, spec=it.spec_snapshot, image_url=it.image_url, category_id=it.category_id,
        qty=it.qty, unit_price=it.unit_price_snapshot, price_tier=it.price_tier, line_total=it.line_total, added_by=it.added_by, added_by_name=u.name if u else None,
        added_by_code=u.staff_code if u else None, added_at=it.added_at, pending_ack=it.pending_ack, supply_mode=it.supply_mode, plant_code=it.plant_code, atp_date=it.atp_date,
        requires_install=it.requires_install, note=it.note, selected=it.selected,
        is_charge=charge, charge_role=staff_shipping_service.role_of(it.matnr) if charge else None,
        show_at_sites=[CartSiteOut(plant_code=x.plant_code, name=x.name, qty=x.available_qty) for x in (sites or [])],
    )


def cart_out(cart: Cart, db: Session | None = None) -> CartOut:
    t = cart_service.totals(cart)
    totals = None
    delivery = None
    if db is not None:
        from app.api.promo import totals_out  # หลีกเลี่ยง circular import
        from app.models.delivery import DeliverySlot, DeliveryZone

        totals = totals_out(db, cart)
        zone = db.get(DeliveryZone, cart.ship_postcode) if cart.ship_postcode else None
        slot = db.get(DeliverySlot, cart.slot_id) if cart.slot_id else None
        delivery = DeliveryInfoOut(
            postcode=cart.ship_postcode, address=cart.ship_address, zone=cart.ship_zone, zone_name=zone.zone_name if zone else None, shipping_fee=cart.shipping_fee,
            install_fee=cart.install_fee, slot_id=cart.slot_id, slot_date=slot.date if slot else None, slot_period=slot.period if slot else None, quoted_at=cart.delivery_quoted_at,
        )
    preso = None
    if db is not None and cart.owner_sales_id:
        from app.services import quotation_service  # หลีกเลี่ยง circular import

        preso = PresoReadyOut(**quotation_service.preso_ready(db, cart))
    # ป้ายสต็อกในตะกร้าอ่านจาก cache เดียวกับการ์ดสินค้า — ไม่ยิง SAP ตอนเปิดตะกร้า
    # (ของจริงยืนยันอีกทีตอนเช็คทั้งบิลก่อนออกใบ) รหัสที่ยังไม่เคยเช็คจะไม่มี key = "ยังไม่รู้"
    stock = product_stock_service.summary_for(db, [it.matnr for it in cart.items]) if db is not None else {}
    # สินค้าตัวโชว์ต้องไปรับที่สาขาอยู่แล้ว บอกไปเลยว่าไปดูของจริงได้ที่ไหน
    # ถามเฉพาะรหัสกลุ่มนี้ ไม่ใช่ทั้งตะกร้า — ของทั่วไปส่งถึงบ้าน ไม่ต้องรู้ว่าสาขาไหนมี
    display = [it.matnr for it in cart.items if catalog_service.pickup_only(it.matnr)]
    sites = product_stock_service.sites_for(db, display) if (db is not None and display) else {}
    staff = []
    if db is not None and cart.owner_sales_id:
        from app.models.cart import STAFF_ROLES
        from app.services import sales_extras_service

        staff = [CartStaffOut(role_code=r.role_code, role_name=STAFF_ROLES.get(r.role_code, r.role_code), user_id=r.user_id,
                              employee_code=r.employee_code, employee_name=r.employee_name)
                 for r in sales_extras_service.list_staff(db, cart.id)]
    return CartOut(
        id=cart.id, no=cart.no, label=cart.label, status=cart.status, customer=person(cart.customer), owner_sales=person(cart.owner_sales),
        is_guest=cart.customer_user_id is None and cart.owner_sales_id is None, items=[item_out(it, stock.get(it.matnr), sites.get(it.matnr)) for it in cart.items], count=t["count"], subtotal=t["subtotal"],
        pending_count=t["pending_count"], all_count=t["all_count"], item_count=t["item_count"], selected_count=t["selected_count"], expires_at=cart.expires_at, updated_at=cart.updated_at, totals=totals, delivery=delivery,
        preso=preso, overall_remark=cart.overall_remark, staff=staff,
    )


class CartCtx:
    """แก้ปัญหา anon cookie: ถ้า guest ยังไม่มี token ให้สร้างและ set cookie กลับไป"""

    def __init__(self, request: Request, response: Response, user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
        self.db = db
        self.user = user
        self.anon = cart_service.anon_token_from(request)
        if user is None and not self.anon:
            self.anon = cart_service.new_anon_token()
            # secure=True บน prod — ไม่งั้น cookie วิ่งผ่าน http ธรรมดาได้ ใครดักกลางทางก็สวมตะกร้าได้
            response.set_cookie(cart_service.ANON_COOKIE, self.anon, max_age=60 * 60 * 24 * 90,
                                samesite="lax", httponly=False, secure=get_settings().is_prod)

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


@router.post("/cart/select", response_model=CartOut)
def select_items(body: SelectIn, ctx: CartCtx = Depends()):
    """ติ๊กเลือกสินค้าที่จะคิดเงิน — ไม่ส่ง item_ids = ทั้งตะกร้า"""
    cart = ctx.current()
    cart_service.set_selected(ctx.db, cart, ctx.user, body.item_ids, body.selected)
    return cart_out(cart_service.load_cart(ctx.db, cart.id), ctx.db)


@router.post("/cart/shipto", response_model=CartOut)
def set_shipto(body: ShipToIn, ctx: CartCtx = Depends()):
    """บอกปลายทางคร่าวๆ (รหัสไปรษณีย์ที่เลือกบน nav) เพื่อให้ค่าส่งในตะกร้าเป็นเลขจริง"""
    cart = ctx.current()
    cart_service.set_shipto(ctx.db, cart, ctx.user, body.postcode)
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
    if not cart.selected_items:
        raise HTTPException(status_code=400, detail="ยังไม่ได้เลือกสินค้าที่จะชำระเงิน" if cart.items else "ตะกร้าว่าง")
    # ของตัวโชว์/ฝากขาย: ใส่ตะกร้าได้ แต่ยังจ่ายออนไลน์ไม่ได้ — เป็นของชิ้นเดียวที่อยู่หน้าร้าน
    # ต้องไปดูของจริงแล้วรับที่สาขา · ด่านนี้อยู่ฝั่งเซิร์ฟเวอร์ ไม่ใช่แค่ปิดปุ่มในหน้าเว็บ
    blocked = [it for it in cart.selected_items if catalog_service.pickup_only(it.matnr)]
    if blocked:
        raise HTTPException(status_code=409, detail={
            "message": "มีสินค้าที่ต้องรับที่สาขา ชำระเงินออนไลน์ไม่ได้ — เอาออกจากรายการที่เลือก หรือติดต่อสาขาที่มีของ",
            "pickup_only": [{"item_id": it.id, "matnr": it.matnr, "name": it.name_snapshot} for it in blocked],
        })
    t = cart_service.totals(cart)
    return {"ok": True, "cart_id": cart.id, "count": t["count"], "subtotal": t["subtotal"]}
