
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cart import CartCtx, cart_out
from app.api.deps import get_current_user, get_current_user_optional, require_role
from app.api.quotation_doc import render_document
from app.db.session import get_db
from app.models.promo import AppliedDiscount
from app.models.quotation import Preso, Quotation
from app.models.user import User
from app.schemas.cart import CartOut
from app.schemas.quotation import CancelIn, CreateQuotationIn, PresoIn, PresoOut, PresoSummaryOut, QuotationDiscountOut, QuotationLineOut, QuotationOut, SendIn
from app.services import quotation_service

router = APIRouter(tags=["preso-quotation"])
staff = require_role("sales", "manager")


def preso_summary(db: Session, p: Preso, user: User | None = None) -> PresoSummaryOut:
    q = db.scalar(select(Quotation).where(Quotation.preso_id == p.id).order_by(Quotation.issued_at.desc()))
    snap = p.snapshot_json or {}
    return PresoSummaryOut(
        id=p.id, preso_no=p.preso_no, status=p.status, cart_id=p.cart_id, customer_name=p.customer.name if p.customer else (snap.get("customer") or {}).get("name"),
        sales_name=p.sales.name if p.sales else None, item_count=sum(int(i["qty"]) for i in snap.get("items", [])),
        grand_total=(snap.get("totals") or {}).get("grand_total", "0"), note=p.note, quotation_no=q.quotation_no if q else None, quotation_status=q.status if q else None,
        # ให้เฉพาะพนักงาน — ลูกค้าเปิดเอกสารของตัวเองผ่านหน้าใบเสนอราคาอยู่แล้ว
        # ไม่ต้องแจก token เพิ่มให้มีของลับลอยอยู่ในมือมากกว่าที่จำเป็น
        quotation_token=quotation_service.link_token(q.quotation_no) if q and user and user.is_staff else None,
        updated_at=p.updated_at, created_at=p.created_at,
    )


def preso_out(db: Session, p: Preso, user: User | None = None) -> PresoOut:
    return PresoOut(**preso_summary(db, p, user).model_dump(), snapshot=p.snapshot_json or {})


def _link_token_for(q: Quotation, user: User | None) -> str | None:
    """token สำหรับเปิดเอกสารในแท็บใหม่ — แท็บใหม่ไม่พก Authorization header ไปด้วย
    (token ของหน้าเว็บเก็บใน JS ไม่ใช่คุกกี้) ปุ่ม PDF จึงต้องพ่วง ?t= ไปเอง

    เดิมให้เฉพาะพนักงาน ลูกค้ากดปุ่ม PDF ของใบตัวเองแล้วได้ 401 "ต้องเข้าสู่ระบบ"
    ทั้งที่ล็อกอินอยู่ · ให้เจ้าของใบด้วยไม่ได้เปิดสิทธิ์อะไรเพิ่ม — เขาเปิดดูใบนี้ได้อยู่แล้ว
    token นี้ผูกกับใบเดียวและไม่ได้ให้สิทธิ์อื่นนอกจากอ่านใบนั้น
    """
    if not user:
        return None
    if user.is_staff or (user.role == "customer" and q.customer_user_id == user.id):
        return quotation_service.link_token(q.quotation_no)
    return None


def quotation_out(db: Session, q: Quotation, user: User | None) -> QuotationOut:
    discs = db.scalars(select(AppliedDiscount).where(AppliedDiscount.quotation_id == q.id)).all()
    return QuotationOut(
        id=q.id, quotation_no=q.quotation_no, preso_no=q.preso.preso_no if q.preso else None, status=q.status, channel=q.channel, customer=q.customer_snapshot,
        sales_name=q.sales.name if q.sales else None, sales_code=q.sales.staff_code if q.sales else None,
        lines=[QuotationLineOut(matnr=l.matnr, sku=l.sku, name=l.name, variant=l.variant, qty=l.qty, unit_price=l.unit_price, line_discount=l.line_discount, line_total=l.line_total, supply_mode=l.supply_mode, plant_code=l.plant_code, atp_date=l.atp_date, added_by=l.added_by, requires_install=l.requires_install) for l in q.lines],
        discounts=[QuotationDiscountOut(kind=d.kind, code=d.promo_code, title=d.title, amount=d.amount) for d in discs],
        subtotal=q.subtotal, discount_total=q.discount_total, shipping_fee=q.shipping_fee, install_fee=q.install_fee, shipping_discount=q.shipping_discount, vat=q.vat, grand_total=q.grand_total,
        deposit_amount=q.deposit_amount, valid_until=q.valid_until, pdf_url=q.pdf_url, ship_address=q.ship_address, ship_postcode=q.ship_postcode, ship_zone=q.ship_zone, slot_date=q.slot_date,
        slot_period=q.slot_period, stock_warnings=q.stock_warnings, sap_so_no=q.sap_so_no, sap_sync_status=q.sap_sync_status, sap_sync_error=q.sap_sync_error, issued_at=q.issued_at, paid_at=q.paid_at,
        cancelled_at=q.cancelled_at, cancel_reason=q.cancel_reason, link_token=_link_token_for(q, user),
    )


# ---------- Preso ----------
@router.post("/presos", response_model=PresoOut, status_code=201)
def save_preso(body: PresoIn, ctx: CartCtx = Depends(), me: User = Depends(staff)):
    """Save Preso — snapshot ตะกร้า (save ซ้ำ = อัปเดตใบร่างเดิม)"""
    cart = ctx.by_id(body.cart_id)
    return preso_out(ctx.db, quotation_service.save_preso(ctx.db, cart, me, body.note, force_stock=body.force), me)


@router.get("/presos", response_model=list[PresoSummaryOut])
def list_presos(status: str | None = None, mine: bool = True, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return [preso_summary(db, p, me) for p in quotation_service.list_presos(db, me, status, mine)]


@router.get("/presos/{preso_no}", response_model=PresoOut)
def get_preso(preso_no: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return preso_out(db, quotation_service.get_preso(db, me, preso_no), me)


@router.post("/presos/{preso_no}/reopen", response_model=CartOut)
def reopen_preso(preso_no: str, db: Session = Depends(get_db), me: User = Depends(staff)):
    """ดึง Preso กลับมาทำต่อ → ตะกร้าเดิมกลับเข้าเซสชันของเซลล์"""
    p = quotation_service.get_preso(db, me, preso_no)
    return cart_out(quotation_service.reopen_preso(db, me, p), db)


@router.post("/presos/{preso_no}/quotation", response_model=QuotationOut, status_code=201)
def create_quotation(preso_no: str, body: CreateQuotationIn, db: Session = Depends(get_db), me: User = Depends(staff)):
    """สร้าง Quotation — ยิงเช็คสต็อกสดก่อน ของไม่พอได้ 409 (force=true เพื่อออกทั้งที่ของไม่พอ)"""
    p = quotation_service.get_preso(db, me, preso_no)
    return quotation_out(db, quotation_service.create_quotation(db, p, me, body.force), me)


@router.post("/checkout/quotation", response_model=QuotationOut, status_code=201)
def checkout_online(body: CreateQuotationIn, db: Session = Depends(get_db), me: User = Depends(require_role("customer")), ctx: CartCtx = Depends()):
    """ลูกค้าสั่งเองออนไลน์ — เซฟ Preso จากตะกร้าตัวเองแล้วออกใบเสนอราคาช่องทาง online ไปหน้าชำระเงิน

    เฉพาะบทบาทลูกค้า: เซลล์ห้ามรับเงินเอง (ต้องออกใบเสนอราคาให้ลูกค้าไปจ่ายเอง)
    """
    cart = ctx.current()
    if cart.customer_user_id != me.id:
        raise HTTPException(status_code=403, detail="ตะกร้านี้ไม่ใช่ของคุณ")
    preso = quotation_service.save_preso(db, cart, me, None)
    return quotation_out(db, quotation_service.create_quotation(db, preso, me, body.force, channel="online"), me)


# ---------- Quotation ----------
@router.get("/quotations", response_model=list[QuotationOut])
def list_quotations(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return [quotation_out(db, q, me) for q in quotation_service.list_quotations(db, me)]


@router.get("/quotations/{no}", response_model=QuotationOut)
def get_quotation(no: str, t: str | None = Query(default=None), db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    """ลูกค้าเปิดจากลิงก์ได้ด้วย ?t=<signed token> โดยไม่ต้องล็อกอิน"""
    q = quotation_service.get_quotation(db, no)
    quotation_service.check_access(q, user, t)
    return quotation_out(db, q, user)


@router.get("/quotations/{no}/document", response_class=HTMLResponse)
def quotation_document(
    no: str,
    t: str | None = Query(default=None),
    images: bool = Query(default=False, description="ใส่รูปสินค้าในเอกสาร"),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """เอกสารใบเสนอราคาแบบพิมพ์ได้ (mock ของ PDF — ของจริงต่อ PDF service)

    ?images=1 = แบบมีรูปสินค้า (ใช้คุยกับลูกค้า) · ไม่ใส่ = แบบไม่มีรูป (แนบอีเมล/ปรินต์)
    """
    q = quotation_service.get_quotation(db, no)
    quotation_service.check_access(q, user, t)
    return HTMLResponse(render_document(db, q, with_images=images))


@router.post("/quotations/{no}/send")
def send_quotation(no: str, body: SendIn, db: Session = Depends(get_db), me: User = Depends(staff)):
    q = quotation_service.get_quotation(db, no)
    quotation_service.check_access(q, me, None)
    return quotation_service.send_link(db, q, me, body.channel)


@router.post("/quotations/{no}/cancel", response_model=QuotationOut)
def cancel_quotation(no: str, body: CancelIn, db: Session = Depends(get_db), me: User = Depends(staff)):
    """issued แล้วแก้ไม่ได้ — cancel แล้วออกใหม่"""
    q = quotation_service.get_quotation(db, no)
    quotation_service.check_access(q, me, None)
    return quotation_out(db, quotation_service.cancel_quotation(db, q, me, body.reason), me)
