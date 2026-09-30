from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.cart import CartCtx, cart_out
from app.api.deps import require_role
from app.db.session import get_db
from app.models.cart import Cart
from app.models.user import User
from app.schemas.cart import CartOut
from app.schemas.promo import ApprovalOut, DiscountIn, DiscountLineOut, EvaluateIn, EvaluateOut, OfferOut, TotalsOut
from app.services import cart_service, promo_service

router = APIRouter(tags=["promotions"])


def totals_out(db: Session, cart: Cart, promo_result=None) -> TotalsOut:
    t = promo_service.compute_totals(db, cart, promo_result)
    return TotalsOut(
        subtotal=t.subtotal, standard_subtotal=t.standard_subtotal, member_savings=t.member_savings, discount_total=t.discount_total, net_total=t.net_total,
        shipping_fee=t.shipping_fee, install_fee=t.install_fee, shipping_discount=t.shipping_discount, grand_total=t.grand_total, vat_included=t.vat_included,
        lines=[DiscountLineOut(**line) for line in t.lines], warnings=t.warnings,
    )


def _mark_promo_checked(db: Session, cart) -> None:
    """ผ่านด่าน "เช็คโปรโมชั่น 1 รอบ" ของใบ PRE แล้ว

    นับตั้งแต่ตอนกดดูรายการโปรฯ — ไม่มีโปรฯ ให้ใช้ก็ถือว่าผ่าน (ใช้ราคาปกติ) ตามผังงาน
    ผูกกับเลขรุ่นตะกร้า ถ้าหลังจากนี้มีการแก้ของ เลขจะไม่ตรงและต้องกดเช็คใหม่เอง
    """
    if cart.rev is not None and cart.promo_rev != cart.rev:
        cart.promo_rev = cart.rev
        db.commit()


@router.post("/promotions/evaluate", response_model=EvaluateOut)
def evaluate(body: EvaluateIn, ctx: CartCtx = Depends()):
    """โปรที่เข้าเงื่อนไข + ที่ยังไม่เข้า (บอกว่าขาดอะไร) + โควตาส่วนลดพนักงาน + ยอดหลังส่วนลด"""
    cart = ctx.by_id(body.cart_id)
    res = promo_service.evaluate_with_sap(ctx.db, cart)
    _mark_promo_checked(ctx.db, cart)
    applied = {d.promo_code: d for d in promo_service.active_discounts(ctx.db, cart) if d.kind == "promotion"}
    staff = next((d for d in promo_service.active_discounts(ctx.db, cart) if d.kind == "staff_manual"), None)

    def out(o) -> OfferOut:
        a = applied.get(o.code)
        return OfferOut(code=o.code, title=o.title, condition_text=o.condition_text, eligible=o.eligible, amount=promo_service.q1(o.amount), reason=o.reason, stackable=o.stackable, discount_type=o.discount_type, applied=bool(a), applied_id=a.id if a else None, requires_code=o.requires_code, exclusive_group=o.exclusive_group)

    # คูปองที่ต้องใช้โค้ดไม่เอามาโชว์ในลิสต์ — ลิสต์นี้คือ "โปรฯ ที่ระบบเช็คให้เอง"
    # ส่วนคูปองใช้ได้ทางเดียวคือกรอกโค้ด ถ้าโชว์ไว้ด้วยก็เท่ากับแจกโค้ดให้ทุกคนเห็น
    def visible(offers):
        return [out(o) for o in offers if not o.requires_code]

    t = totals_out(ctx.db, cart, res)
    return EvaluateOut(
        cart_id=cart.id, customer_name=cart.customer.name if cart.customer else None,         eligible=visible(res.eligible), ineligible=visible(res.ineligible), staff_discount_quota_percent=res.staff_discount_quota_percent,
        staff_discount=DiscountLineOut(id=staff.id, kind="staff_manual", title=f"ส่วนลดพนักงาน {staff.percent:g}%", amount=staff.amount, status=staff.status, percent=staff.percent) if staff else None,
        totals=t,
    )


@router.post("/cart/{cart_id}/discounts", response_model=CartOut, status_code=201)
def add_discount(cart_id: str, body: DiscountIn, ctx: CartCtx = Depends()):
    """promotion: ลูกค้า/เซลล์กดใช้โปรที่เข้าเงื่อนไข · staff_manual: เซลล์ ≤ 3% ใช้ได้เลย, เกินสร้างคำขออนุมัติให้ manager"""
    cart = ctx.by_id(cart_id)
    # ตะกร้าที่พนักงานดูแลอยู่ ลูกค้าแตะส่วนลดเองไม่ได้ — ไม่งั้นลูกค้าได้โค้ดหน้าสโตร์
    # จากพนักงาน แล้วเติมโค้ดออนไลน์ทับอีกชั้น กลายเป็นลดสองต่อโดยไม่มีใครอนุมัติ
    # อยากใส่เองต้องกด "ออกจากการดูแล" ก่อน (DELETE /cart/{id}/sales-owner)
    if cart.owner_sales_id and not (ctx.user and ctx.user.is_staff):
        raise HTTPException(status_code=403, detail="ตะกร้านี้พนักงานกำลังดูแลอยู่ — ส่วนลดให้พนักงานเป็นคนใส่")
    if body.kind == "promotion":
        if not body.promo_code:
            raise HTTPException(status_code=422, detail="ต้องระบุ promo_code")
        promo_service.apply_promotion(ctx.db, cart, ctx.user, body.promo_code)
    else:
        if not ctx.user or ctx.user.role not in ("sales", "manager"):
            raise HTTPException(status_code=403, detail="ส่วนลดพนักงานให้ได้เฉพาะพนักงานขาย/ผู้จัดการ")
        if body.percent is None:
            raise HTTPException(status_code=422, detail="ต้องระบุ percent")
        promo_service.apply_staff_discount(ctx.db, cart, ctx.user, body.percent, body.reason)
    _mark_promo_checked(ctx.db, cart)
    return cart_out(cart_service.load_cart(ctx.db, cart.id), ctx.db)


@router.delete("/cart/{cart_id}/sales-owner", response_model=CartOut)
def leave_sales_care(cart_id: str, ctx: CartCtx = Depends()):
    """ลูกค้าขอออกจากการดูแลของพนักงาน กลับไปสั่งออนไลน์เอง

    ส่วนลดที่พนักงานใส่ไว้ถูกถอดออกทั้งหมด เพราะเป็นสิทธิ์ของการซื้อหน้าร้าน
    ถ้าปล่อยติดไปด้วย ลูกค้าจะรับโค้ดหน้าสโตร์แล้วหนีไปจ่ายออนไลน์ได้ฟรีๆ
    ของในตะกร้ายังอยู่ครบ ไม่ต้องหยิบใหม่
    """
    # เช็คสิทธิ์ก่อนแตะตะกร้า — คนที่ไม่มีสิทธิ์ต้องได้ 401/403 ไม่ใช่ 404
    # ที่บอกใบ้ว่าตะกร้าใบนั้นมีอยู่จริงหรือเปล่า
    if not ctx.user:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบก่อน")
    if ctx.user.is_staff:
        raise HTTPException(status_code=403, detail="ปุ่มนี้สำหรับลูกค้า — พนักงานใช้ปุ่มปลดลูกค้าในหน้าขาย")
    cart = ctx.by_id(cart_id)
    if not cart.owner_sales_id:
        raise HTTPException(status_code=409, detail="ตะกร้านี้ไม่มีพนักงานดูแลอยู่แล้ว")
    cart_service.leave_sales_care(ctx.db, cart, ctx.user)
    return cart_out(cart_service.load_cart(ctx.db, cart.id), ctx.db)


@router.delete("/cart/{cart_id}/discounts/{discount_id}", response_model=CartOut)
def remove_discount(cart_id: str, discount_id: str, ctx: CartCtx = Depends()):
    cart = ctx.by_id(cart_id)
    promo_service.remove_discount(ctx.db, cart, ctx.user, discount_id)
    _mark_promo_checked(ctx.db, cart)
    return cart_out(cart_service.load_cart(ctx.db, cart.id), ctx.db)


def approval_out(db: Session, d) -> ApprovalOut:
    cart = cart_service.load_cart(db, d.cart_id) if d.cart_id else None
    sales = db.get(User, d.applied_by_user_id) if d.applied_by_user_id else None
    return ApprovalOut(id=d.id, cart_id=d.cart_id, cart_no=cart.no if cart else None, customer_name=cart.customer.name if cart and cart.customer else None, sales_name=sales.name if sales else None, percent=d.percent, amount=d.amount, reason=d.reason, status=d.status, created_at=d.created_at)


@router.get("/discount-approvals", response_model=list[ApprovalOut])
def list_approvals(db: Session = Depends(get_db), _: User = Depends(require_role("manager", "admin"))):
    return [approval_out(db, d) for d in promo_service.pending_approvals(db)]


@router.post("/discount-approvals/{discount_id}/approve", response_model=ApprovalOut)
def approve(discount_id: str, db: Session = Depends(get_db), me: User = Depends(require_role("manager"))):
    return approval_out(db, promo_service.decide(db, me, discount_id, True))


@router.post("/discount-approvals/{discount_id}/reject", response_model=ApprovalOut)
def reject(discount_id: str, db: Session = Depends(get_db), me: User = Depends(require_role("manager"))):
    return approval_out(db, promo_service.decide(db, me, discount_id, False))
