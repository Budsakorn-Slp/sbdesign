"""บิลรวม (Big Bill) — พนักงานรวมใบเสนอราคาที่รอชำระของลูกค้าคนเดียว แล้วเก็บเงินครั้งเดียว

ขั้นตอน:
  1. candidates()  ใบรอชำระทั้งหมดของลูกค้า (ทุกพนักงาน — ทาง ก) ให้ติ๊กเลือก
  2. promos()      โค้ดส่วนลดระดับบิล คิดจาก "ยอดรวมทุกใบที่เลือก" บอกว่าใช้ได้ไหม/ขาดอีกเท่าไร
  3. create()      สร้างบิล (ล็อกยอดแต่ละใบ + โค้ด) → pay() ได้รายการชำระครั้งเดียวผ่าน gateway
  4. on_paid()     จ่ายสำเร็จ: ทุกใบเป็น "จ่ายแล้ว" กระจายส่วนลดบิลลงแต่ละใบตามสัดส่วน แล้วส่งเข้า SAP แยก SO

DEMO: โค้ดส่วนลดระดับบิลยังเป็นรายการตัวอย่างในไฟล์นี้ (แบบหน้าระบบเดิม)
TODO: ต่อกับตารางโปรโมชั่นจริงของ SAP/FI เมื่อมีสเปก
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.integrations.payment import ChargeRequest, PaymentError, get_payment_gateway
from app.models.bigbill import BigBill, BigBillItem
from app.models.common import utcnow
from app.models.payment import Payment
from app.models.promo import AppliedDiscount
from app.models.quotation import Quotation
from app.models.user import User
from app.services import audit_service, quotation_service

# โค้ดระดับบิล (ตัวอย่างสำหรับ demo) — คิดจากยอดรวมทุกใบในบิล ใช้ได้ครั้งละหนึ่งโค้ด
BILL_PROMOS = [
    {"code": "MC0626500B", "title": "ลดเพิ่ม 500.- เมื่อช้อปครบ 5,000.-", "min": Decimal("5000"), "amount": Decimal("500"), "expires": date(2026, 12, 31)},
    {"code": "BB50K5000", "title": "ลดเพิ่ม 5,000.- เมื่อช้อปครบ 50,000.-", "min": Decimal("50000"), "amount": Decimal("5000"), "expires": date(2026, 12, 31)},
    {"code": "BB100K12000", "title": "ลดเพิ่ม 12,000.- เมื่อช้อปครบ 100,000.- (บิลรวมหลายใบ)", "min": Decimal("100000"), "amount": Decimal("12000"), "expires": date(2026, 12, 31)},
]
METHODS = ("qr_promptpay", "card", "installment")
TWO = Decimal("0.01")


def _q(v) -> Decimal:
    return Decimal(v).quantize(TWO, rounding=ROUND_HALF_UP)


def _open_bill_of(db: Session, q: Quotation) -> BigBill | None:
    """บิลรวมที่ใบนี้อยู่และยังไม่จบ — ใบเดียวอยู่ได้ทีละบิล"""
    return db.scalar(select(BigBill).join(BigBillItem).where(BigBillItem.quotation_id == q.id, BigBill.status == "open"))


# ---------- 1. ใบที่เลือกได้ ----------
def candidates(db: Session, customer_user_id: str) -> list[Quotation]:
    today = utcnow().date()
    rows = db.scalars(
        select(Quotation).options(selectinload(Quotation.sales), selectinload(Quotation.lines))
        .where(Quotation.customer_user_id == customer_user_id, Quotation.status == "issued", Quotation.valid_until >= today)
        .order_by(Quotation.issued_at)
    ).all()
    return list(rows)


# ---------- 2. โค้ดระดับบิล ----------
def promos(amount: Decimal) -> list[dict]:
    today = utcnow().date()
    out = []
    for p in BILL_PROMOS:
        if p["expires"] < today:
            continue
        short = max(Decimal(0), p["min"] - amount)
        out.append({**p, "eligible": short == 0, "short_by": short})
    return out


def _promo(code: str | None, amount: Decimal) -> dict | None:
    if not code:
        return None
    p = next((x for x in promos(amount) if x["code"] == code.strip().upper()), None)
    if not p:
        raise HTTPException(status_code=404, detail=f"ไม่พบโค้ด {code} หรือหมดอายุแล้ว")
    if not p["eligible"]:
        raise HTTPException(status_code=400, detail=f"ยอดรวมยังไม่ถึงเงื่อนไขโค้ด {p['code']} (ขาดอีก {p['short_by']:,.2f} บาท)")
    return p


# ---------- 3. สร้างบิล / จ่าย ----------
def create(db: Session, actor: User, quotation_nos: list[str], promo_code: str | None) -> BigBill:
    nos = list(dict.fromkeys(n.strip() for n in quotation_nos if n.strip()))
    if len(nos) < 1:
        raise HTTPException(status_code=422, detail="เลือกใบเสนอราคาอย่างน้อย 1 ใบ")
    qs = [quotation_service.get_quotation(db, n) for n in nos]
    customers = {q.customer_user_id for q in qs}
    if len(customers) != 1 or None in customers:
        raise HTTPException(status_code=400, detail="บิลรวมต้องเป็นใบของลูกค้าคนเดียวกัน")
    today = utcnow().date()
    for q in qs:
        if q.status != "issued":
            raise HTTPException(status_code=400, detail=f"{q.quotation_no} ชำระไม่ได้ (สถานะ {q.status})")
        if q.valid_until < today:
            raise HTTPException(status_code=400, detail=f"{q.quotation_no} หมดอายุแล้ว")
        other = _open_bill_of(db, q)
        if other:
            # บิลเก่าที่ยังไม่จ่าย ถูกแทนด้วยบิลใหม่ — ยกเลิกบิลเก่า (ไม่แตะตัวใบ)
            cancel(db, other, actor, f"รวมใหม่เป็นบิลใหม่")
    subtotal = _q(sum((Decimal(q.grand_total) for q in qs), Decimal(0)))
    promo = _promo(promo_code, subtotal)
    discount = _q(promo["amount"]) if promo else Decimal(0)
    bill = BigBill(
        bill_no=quotation_service._doc_no(db, BigBill, BigBill.bill_no, "BB"),
        customer_user_id=qs[0].customer_user_id, created_by_user_id=actor.id,
        promo_code=promo["code"] if promo else None, promo_title=promo["title"] if promo else None,
        subtotal=subtotal, discount=discount, grand_total=_q(subtotal - discount),
    )
    # กระจายส่วนลดตามสัดส่วนยอด · เศษสตางค์ไปลงใบสุดท้ายให้รวมแล้วเท่าส่วนลดพอดี
    left = discount
    for i, q in enumerate(qs):
        share = left if i == len(qs) - 1 else _q(discount * Decimal(q.grand_total) / subtotal) if subtotal else Decimal(0)
        left -= share
        bill.items.append(BigBillItem(quotation_id=q.id, amount=_q(q.grand_total), discount_share=share))
    db.add(bill)
    audit_service.log(db, actor, "bigbill.create", "big_bill", bill.bill_no,
                      {"quotations": nos, "promo": bill.promo_code, "grand_total": str(bill.grand_total)})
    db.commit()
    return get(db, bill.bill_no)


def get(db: Session, bill_no: str) -> BigBill:
    b = db.scalar(select(BigBill).where(BigBill.bill_no == bill_no))
    if not b:
        raise HTTPException(status_code=404, detail="ไม่พบบิลรวมนี้")
    return b


def cancel(db: Session, b: BigBill, actor: User | None, reason: str) -> None:
    if b.status != "open":
        return
    b.status = "cancelled"
    for p in db.scalars(select(Payment).where(Payment.big_bill_id == b.id, Payment.status == "pending")).all():
        p.status = "cancelled"
    audit_service.log(db, actor, "bigbill.cancel", "big_bill", b.bill_no, {"reason": reason})
    db.flush()


def pay(db: Session, b: BigBill, actor: User, method: str) -> Payment:
    if method not in METHODS:
        raise HTTPException(status_code=422, detail="ระบบไม่รับเงินสด — เลือก QR / บัตร / ผ่อน")
    if b.status != "open":
        raise HTTPException(status_code=400, detail=f"บิลนี้ชำระไม่ได้ (สถานะ {b.status})")
    for it in b.items:
        if it.quotation.status != "issued":
            raise HTTPException(status_code=400, detail=f"{it.quotation.quotation_no} ถูกชำระ/ยกเลิกไปแล้ว — สร้างบิลใหม่")
    now = utcnow()
    old = db.scalar(select(Payment).where(Payment.big_bill_id == b.id, Payment.status == "pending").order_by(Payment.created_at.desc()))
    if old and old.expires_at > now and old.method == method:
        return old
    if old:
        old.status = "cancelled"
    # ใบในบิลมี QR เดี่ยวค้างอยู่ — ปิดก่อน ไม่งั้นลูกค้าจ่ายได้สองทาง
    from app.services.payment_service import close_other_channels

    close_other_channels(db, [it.quotation for it in b.items], keep=None, keep_bill_id=b.id)
    anchor = b.items[0].quotation
    no = quotation_service._doc_no(db, Payment, Payment.payment_no, "PAY")
    try:
        res = get_payment_gateway().charge(ChargeRequest(
            payment_no=no, amount=Decimal(b.grand_total), method=method,
            description=f"SB Design Square · บิลรวม {b.bill_no} ({len(b.items)} ใบ)",
            customer_name=(anchor.customer_snapshot or {}).get("name"),
            customer_email=(anchor.customer_snapshot or {}).get("email"),
            return_url=f"/sales/bigbill/{b.bill_no}",
        ))
    except PaymentError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"เปิดรายการชำระเงินไม่ได้: {e}")
    p = Payment(
        payment_no=no, quotation_id=anchor.id, big_bill_id=b.id, method=method, kind="full", amount=b.grand_total,
        status="pending", provider_ref=res.provider_ref, qr_payload=res.qr_payload,
        pay_url=res.redirect_url or f"/pay/{no}/bank",
        expires_at=now + timedelta(hours=get_settings().payment_expire_hours), created_by_user_id=actor.id,
    )
    db.add(p)
    audit_service.log(db, actor, "bigbill.payment_intent", "big_bill", b.bill_no, {"payment_no": no, "method": method, "amount": str(b.grand_total)})
    db.commit()
    db.refresh(p)
    return p


# ---------- 4. จ่ายสำเร็จ ----------
def on_paid(db: Session, p: Payment) -> list[Quotation]:
    """เรียกจาก webhook ตอนรายการชำระของบิลรวมสำเร็จ — คืนรายการใบที่ต้องส่งเข้า SAP"""
    from app.services.payment_service import _refund_due

    b = p.big_bill
    done: list[Quotation] = []
    for it in b.items:
        q = it.quotation
        if q.status != "issued":
            # ใบนี้ถูกจ่าย/ยกเลิกทางอื่นไปแล้ว — ไม่แตะใบ ยอดของใบนี้ในบิลคือเงินที่ต้องคืน
            _refund_due(db, p, _q(Decimal(it.amount) - Decimal(it.discount_share or 0)),
                        f"{q.quotation_no} สถานะ {q.status} อยู่แล้ว (ชำระซ้ำในบิล {b.bill_no})", full=False)
            continue
        share = Decimal(it.discount_share or 0)
        if share > 0:
            # ส่วนลดบิลลงใบนี้ — SO ใน SAP ได้ยอดตรงกับที่ลูกค้าจ่ายจริง
            q.discount_total = _q(Decimal(q.discount_total) + share)
            q.grand_total = _q(Decimal(q.grand_total) - share)
            q.vat = _q(Decimal(q.grand_total) * 7 / 107)
            db.add(AppliedDiscount(cart_id=None, quotation_id=q.id, kind="promotion", promo_code=b.promo_code,
                                   title=f"ส่วนลดบิลรวม {b.bill_no} · {b.promo_title or b.promo_code}",
                                   percent=None, amount=share, status="applied", applied_by_user_id=b.created_by_user_id))
        q.status = "paid"
        q.paid_at = p.paid_at
        done.append(q)
    if not done:
        # ทุกใบในบิลถูกชำระทางอื่นไปหมดแล้ว — ทั้งก้อนคือเงินรอคืน บิลไม่มีผล
        p.status = "refund_due"
        b.status = "cancelled"
        return done
    b.status = "paid"
    b.paid_at = p.paid_at
    audit_service.log(db, None, "bigbill.paid", "big_bill", b.bill_no,
                      {"payment_no": p.payment_no, "quotations": [q.quotation_no for q in done]}, role="system")
    return done


def on_expired(db: Session, p: Payment) -> None:
    """รายการชำระของบิลหมดเวลา — ไม่ยกเลิกใบในบิล (ใบมีอายุของตัวเอง) แค่ให้กดจ่ายใหม่ได้"""
    p.status = "expired"
