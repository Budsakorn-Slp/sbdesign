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
    return TotalsOut(subtotal=t.subtotal, standard_subtotal=t.standard_subtotal, member_savings=t.member_savings, discount_total=t.discount_total, net_total=t.net_total, lines=[DiscountLineOut(**line) for line in t.lines], warnings=t.warnings)


@router.post("/promotions/evaluate", response_model=EvaluateOut)
def evaluate(body: EvaluateIn, ctx: CartCtx = Depends()):
    """โปรที่เข้าเงื่อนไข + ที่ยังไม่เข้า (บอกว่าขาดอะไร) + โควตาส่วนลดพนักงาน + ยอดหลังส่วนลด"""
    cart = ctx.by_id(body.cart_id)
    res = promo_service.evaluate_with_sap(ctx.db, cart)
    applied = {d.promo_code: d for d in promo_service.active_discounts(ctx.db, cart) if d.kind == "promotion"}
    staff = next((d for d in promo_service.active_discounts(ctx.db, cart) if d.kind == "staff_manual"), None)

    def out(o) -> OfferOut:
        a = applied.get(o.code)
        return OfferOut(code=o.code, title=o.title, condition_text=o.condition_text, eligible=o.eligible, amount=promo_service.q1(o.amount), reason=o.reason, stackable=o.stackable, discount_type=o.discount_type, applied=bool(a), applied_id=a.id if a else None)

    t = totals_out(ctx.db, cart, res)
    return EvaluateOut(
        cart_id=cart.id, customer_name=cart.customer.name if cart.customer else None, customer_tier=cart.customer.tier if cart.customer else None,
        eligible=[out(o) for o in res.eligible], ineligible=[out(o) for o in res.ineligible], staff_discount_quota_percent=res.staff_discount_quota_percent,
        staff_discount=DiscountLineOut(id=staff.id, kind="staff_manual", title=f"ส่วนลดพนักงาน {staff.percent:g}%", amount=staff.amount, status=staff.status, percent=staff.percent) if staff else None,
        totals=t,
    )


@router.post("/cart/{cart_id}/discounts", response_model=CartOut, status_code=201)
def add_discount(cart_id: str, body: DiscountIn, ctx: CartCtx = Depends()):
    """promotion: ลูกค้า/เซลล์กดใช้โปรที่เข้าเงื่อนไข · staff_manual: เซลล์ ≤ 3% ใช้ได้เลย, เกินสร้างคำขออนุมัติให้ manager"""
    cart = ctx.by_id(cart_id)
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
    return cart_out(cart_service.load_cart(ctx.db, cart.id), ctx.db)


@router.delete("/cart/{cart_id}/discounts/{discount_id}", response_model=CartOut)
def remove_discount(cart_id: str, discount_id: str, ctx: CartCtx = Depends()):
    cart = ctx.by_id(cart_id)
    promo_service.remove_discount(ctx.db, cart, ctx.user, discount_id)
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
