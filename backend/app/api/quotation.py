import html

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cart import CartCtx, cart_out
from app.api.deps import get_current_user, get_current_user_optional, require_role
from app.db.session import get_db
from app.models.promo import AppliedDiscount
from app.models.quotation import Preso, Quotation
from app.models.user import User
from app.schemas.cart import CartOut
from app.schemas.quotation import CancelIn, CreateQuotationIn, PresoIn, PresoOut, PresoSummaryOut, QuotationDiscountOut, QuotationLineOut, QuotationOut, SendIn
from app.services import quotation_service

router = APIRouter(tags=["preso-quotation"])
staff = require_role("sales", "manager")


def preso_summary(db: Session, p: Preso) -> PresoSummaryOut:
    q = db.scalar(select(Quotation).where(Quotation.preso_id == p.id).order_by(Quotation.issued_at.desc()))
    snap = p.snapshot_json or {}
    return PresoSummaryOut(
        id=p.id, preso_no=p.preso_no, status=p.status, cart_id=p.cart_id, customer_name=p.customer.name if p.customer else (snap.get("customer") or {}).get("name"),
        customer_tier=p.customer.tier if p.customer else None, sales_name=p.sales.name if p.sales else None, item_count=sum(int(i["qty"]) for i in snap.get("items", [])),
        grand_total=(snap.get("totals") or {}).get("grand_total", "0"), note=p.note, quotation_no=q.quotation_no if q else None, quotation_status=q.status if q else None,
        updated_at=p.updated_at, created_at=p.created_at,
    )


def preso_out(db: Session, p: Preso) -> PresoOut:
    return PresoOut(**preso_summary(db, p).model_dump(), snapshot=p.snapshot_json or {})


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
        cancelled_at=q.cancelled_at, cancel_reason=q.cancel_reason, link_token=quotation_service.link_token(q.quotation_no) if user and user.is_staff else None,
    )


# ---------- Preso ----------
@router.post("/presos", response_model=PresoOut, status_code=201)
def save_preso(body: PresoIn, ctx: CartCtx = Depends(), me: User = Depends(staff)):
    """Save Preso — snapshot ตะกร้า (save ซ้ำ = อัปเดตใบร่างเดิม)"""
    cart = ctx.by_id(body.cart_id)
    return preso_out(ctx.db, quotation_service.save_preso(ctx.db, cart, me, body.note))


@router.get("/presos", response_model=list[PresoSummaryOut])
def list_presos(status: str | None = None, mine: bool = True, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return [preso_summary(db, p) for p in quotation_service.list_presos(db, me, status, mine)]


@router.get("/presos/{preso_no}", response_model=PresoOut)
def get_preso(preso_no: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return preso_out(db, quotation_service.get_preso(db, me, preso_no))


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
def quotation_document(no: str, t: str | None = Query(default=None), db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    """เอกสารใบเสนอราคาแบบพิมพ์ได้ (mock ของ PDF — ของจริงต่อ PDF service)"""
    q = quotation_service.get_quotation(db, no)
    quotation_service.check_access(q, user, t)
    return HTMLResponse(render_document(db, q))


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


def _money(v) -> str:
    return f"{float(v):,.2f}"


def render_document(db: Session, q: Quotation) -> str:
    e = html.escape
    c = q.customer_snapshot or {}
    rows = "".join(
        f"<tr><td>{i + 1}</td><td>{e(l.name)}<br><small>{e(l.variant or '')} · MATNR {l.matnr}</small></td><td class='r'>{l.qty}</td><td class='r'>{_money(l.unit_price)}</td><td class='r'>{_money(l.line_total)}</td><td>{e({'takeaway': 'ยกกลับ', 'ship': 'จัดส่ง', 'install': 'ส่ง+ติดตั้ง', 'pickup': 'รับที่สาขา'}.get(l.supply_mode, l.supply_mode))}</td></tr>"
        for i, l in enumerate(q.lines)
    )
    discs = db.scalars(select(AppliedDiscount).where(AppliedDiscount.quotation_id == q.id)).all()
    disc_rows = "".join(f"<tr><td colspan='4' class='r'>{e(d.title or d.promo_code or d.kind)}</td><td class='r'>-{_money(d.amount)}</td><td></td></tr>" for d in discs)
    slot = f"{q.slot_date.strftime('%d/%m/%Y')} {'รอบเช้า' if q.slot_period == 'am' else 'รอบบ่าย'}" if q.slot_date else "-"
    status_txt = {"issued": "ออกแล้ว · รอชำระ", "paid": "ชำระแล้ว", "converted": "สร้าง SO แล้ว", "cancelled": "ยกเลิก", "expired": "หมดอายุ"}.get(q.status, q.status)
    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8"><title>ใบเสนอราคา {e(q.quotation_no)}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;600;700&display=swap" rel="stylesheet">
<style>body{{font-family:'Noto Sans Thai',sans-serif;color:#111;max-width:820px;margin:32px auto;padding:0 24px;font-size:14px}}h1{{font-size:22px;margin:0}}table{{width:100%;border-collapse:collapse;margin-top:16px}}th,td{{padding:8px 10px;border-bottom:1px solid #e0e0de;vertical-align:top;text-align:left}}th{{background:#f2f2f0;font-size:12px}}.r{{text-align:right}}.tot td{{font-weight:700;border-top:2px solid #111}}.box{{display:flex;justify-content:space-between;gap:24px;margin-top:16px}}.muted{{color:#777;font-size:12px}}.tag{{display:inline-block;padding:2px 8px;border-radius:4px;background:#111;color:#fff;font-size:12px}}@media print{{body{{margin:0}}}}</style></head>
<body><div class="box"><div><h1>ใบเสนอราคา / Quotation</h1><div class="muted">SB Design Square · บริษัท เอส.บี.อุตสาหกรรมเครื่องเรือน จำกัด</div></div>
<div style="text-align:right"><div><b>{e(q.quotation_no)}</b> <span class="tag">{e(status_txt)}</span></div><div class="muted">ออกเมื่อ {q.issued_at.strftime('%d/%m/%Y %H:%M')} · ยืนราคาถึง <b>{q.valid_until.strftime('%d/%m/%Y')}</b></div></div></div>
<div class="box"><div><b>ลูกค้า</b><br>{e(c.get('name') or '')} · CUST {e(c.get('sap_customer_no') or '-')} · {e(c.get('tier') or 'ทั่วไป')}<br><span class="muted">{e(c.get('phone') or '')} · {e(c.get('email') or '')}</span><br><span class="muted">{e(q.ship_address or '')} {e(q.ship_postcode or '')}</span></div>
<div style="text-align:right"><b>พนักงานขาย</b><br>{e(q.sales.name if q.sales else 'สั่งซื้อออนไลน์')}{(' (' + e(q.sales.staff_code) + ')') if q.sales and q.sales.staff_code else ''}<br><span class="muted">คิวจัดส่ง: {e(slot)}</span></div></div>
<table><thead><tr><th>#</th><th>รายการ</th><th class="r">จำนวน</th><th class="r">ราคา/หน่วย</th><th class="r">รวม</th><th>รับสินค้า</th></tr></thead><tbody>{rows}
<tr><td colspan="4" class="r">รวมสินค้า</td><td class="r">{_money(q.subtotal)}</td><td></td></tr>{disc_rows}
<tr><td colspan="4" class="r">ค่าขนส่ง{' + ติดตั้ง' if float(q.install_fee) else ''}</td><td class="r">{_money(float(q.shipping_fee) + float(q.install_fee) - float(q.shipping_discount))}</td><td></td></tr>
<tr class="tot"><td colspan="4" class="r">รวมสุทธิ (รวม VAT 7% = {_money(q.vat)})</td><td class="r">{_money(q.grand_total)}</td><td></td></tr>
<tr><td colspan="4" class="r muted">มัดจำ 20% วันนี้ · ที่เหลือชำระวันส่ง</td><td class="r muted">{_money(q.deposit_amount)}</td><td></td></tr></tbody></table>
<p class="muted">เอกสารนี้สร้างจากระบบ SB Sales App (mock PDF) · ราคาและโปรโมชั่นถูกล็อกไว้จนถึงวันยืนราคา · เมื่อชำระเงินสำเร็จ ระบบจะส่งใบเสนอราคาไป convert เป็น Sales Order ใน SAP{(' · SO ' + e(q.sap_so_no)) if q.sap_so_no else ''}</p>
</body></html>"""
