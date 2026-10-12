"""บิลรวม (Big Bill) — หน้าพนักงาน: รวมใบเสนอราคาที่รอชำระของลูกค้าคนเดียว จ่ายครั้งเดียว"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.api.payment import PaymentOut, payment_out
from app.db.session import get_db
from app.models.bigbill import BigBill
from app.models.quotation import Quotation
from app.models.user import User
from app.services import bigbill_service, quotation_service

router = APIRouter(tags=["big-bill"])
staff = require_role("sales", "manager")


class CandidateOut(BaseModel):
    quotation_no: str
    issued_at: datetime
    valid_until: date
    grand_total: Decimal
    discount_total: Decimal
    item_count: int
    first_item: str
    sales_name: str | None
    sales_code: str | None
    mine: bool                       # ใบที่พนักงานคนนี้ออกเอง


class CustomerOut(BaseModel):
    id: str
    name: str
    sap_customer_no: str | None
    phone: str | None


class CandidatesOut(BaseModel):
    customer: CustomerOut
    quotations: list[CandidateOut]


class PromoOut(BaseModel):
    code: str
    title: str
    min: Decimal
    amount: Decimal
    expires: date
    eligible: bool
    short_by: Decimal


class BillItemOut(BaseModel):
    quotation_no: str
    status: str
    amount: Decimal
    discount_share: Decimal
    sales_name: str | None
    sap_so_no: str | None


class AttemptOut(BaseModel):
    payment_no: str
    method: str
    status: str                 # pending | paid | failed | cancelled | expired
    amount: Decimal
    created_at: datetime
    paid_at: datetime | None = None
    failed_reason: str | None = None


class BillOut(BaseModel):
    bill_no: str
    status: str
    customer: CustomerOut
    promo_code: str | None
    promo_title: str | None
    subtotal: Decimal
    discount: Decimal
    grand_total: Decimal
    created_at: datetime
    paid_at: datetime | None
    items: list[BillItemOut]
    pending_payment: str | None = None   # เลขรายการชำระที่รออยู่ (กดจ่ายต่อได้)
    attempts: list[AttemptOut] = []      # ทุกครั้งที่กดชำระ ล่าสุดก่อน — บอกว่ารอบก่อนยกเลิก/ไม่สำเร็จ/หมดเวลา


class BillRowOut(BaseModel):
    bill_no: str
    status: str
    customer_name: str
    count: int
    grand_total: Decimal
    discount: Decimal
    created_at: datetime
    paid_at: datetime | None
    created_by: str | None


class CreateIn(BaseModel):
    quotation_nos: list[str] = Field(min_length=1, max_length=30)
    promo_code: str | None = Field(default=None, max_length=32)


class PayIn(BaseModel):
    method: str = Field(pattern="^(qr_promptpay|card|installment)$")


def _customer(u: User) -> CustomerOut:
    return CustomerOut(id=u.id, name=u.name, sap_customer_no=u.sap_customer_no, phone=u.phone)


def _cand(q: Quotation, me: User) -> CandidateOut:
    lines = [l for l in q.lines]
    return CandidateOut(
        quotation_no=q.quotation_no, issued_at=q.issued_at, valid_until=q.valid_until, grand_total=q.grand_total,
        discount_total=q.discount_total, item_count=len(lines), first_item=lines[0].name if lines else "",
        sales_name=q.sales.name if q.sales else None, sales_code=q.sales.staff_code if q.sales else None,
        mine=q.sales_user_id == me.id,
    )


def _bill(db: Session, b: BigBill) -> BillOut:
    from sqlalchemy import select

    from app.models.payment import Payment

    pays = db.scalars(select(Payment).where(Payment.big_bill_id == b.id).order_by(Payment.created_at.desc())).all()
    # รายการที่ยังรอแต่เลยเวลาแล้ว — ปิดเป็นหมดเวลาก่อนแสดง (ไม่งั้นขึ้น "รอชำระ" ทั้งที่จ่ายไม่ได้แล้ว)
    from app.services import payment_service

    for x in pays:
        if x.status == "pending":
            payment_service.get_payment(db, x.payment_no)
    pend = next((x.payment_no for x in pays if x.status == "pending"), None)
    return BillOut(
        bill_no=b.bill_no, status=b.status, customer=_customer(b.customer), promo_code=b.promo_code, promo_title=b.promo_title,
        subtotal=b.subtotal, discount=b.discount, grand_total=b.grand_total, created_at=b.created_at, paid_at=b.paid_at,
        items=[BillItemOut(quotation_no=it.quotation.quotation_no, status=it.quotation.status, amount=it.amount,
                           discount_share=it.discount_share, sales_name=it.quotation.sales.name if it.quotation.sales else None,
                           sap_so_no=it.quotation.sap_so_no) for it in b.items],
        pending_payment=pend,
        attempts=[AttemptOut(payment_no=x.payment_no, method=x.method, status=x.status, amount=x.amount, created_at=x.created_at,
                             paid_at=x.paid_at, failed_reason=x.failed_reason) for x in pays],
    )


@router.get("/sales/bigbill/candidates", response_model=CandidatesOut)
def candidates(quotation_no: str = Query(min_length=1), db: Session = Depends(get_db), me: User = Depends(staff)):
    """ใบรอชำระทั้งหมดของลูกค้าเจ้าของใบที่ส่งมา — รวมใบที่พนักงานคนอื่นออก (ติ๊กเพิ่มได้)"""
    q = quotation_service.get_quotation(db, quotation_no)
    return CandidatesOut(customer=_customer(q.customer),
                         quotations=[_cand(x, me) for x in bigbill_service.candidates(db, q.customer_user_id)])


@router.get("/sales/bigbill/promos", response_model=list[PromoOut])
def promos(amount: Decimal = Query(ge=0), me: User = Depends(staff)):
    return [PromoOut(**p) for p in bigbill_service.promos(amount)]


@router.get("/sales/bigbills", response_model=list[BillRowOut])
def list_bills(db: Session = Depends(get_db), me: User = Depends(staff)):
    """บิลรวมที่เกี่ยวกับฉัน: ที่ฉันสร้าง หรือมีใบของฉันอยู่ · ผู้จัดการเห็นทุกบิล — ล่าสุดก่อน"""
    from sqlalchemy import or_, select

    from app.models.bigbill import BigBillItem

    q = select(BigBill).order_by(BigBill.created_at.desc()).limit(200)
    if me.role != "manager":
        mine = select(BigBillItem.bill_id).join(Quotation, Quotation.id == BigBillItem.quotation_id).where(Quotation.sales_user_id == me.id)
        q = q.where(or_(BigBill.created_by_user_id == me.id, BigBill.id.in_(mine)))
    return [BillRowOut(bill_no=b.bill_no, status=b.status, customer_name=b.customer.name, count=len(b.items),
                       grand_total=b.grand_total, discount=b.discount, created_at=b.created_at, paid_at=b.paid_at,
                       created_by=b.created_by.name if b.created_by else None) for b in db.scalars(q).all()]


@router.post("/sales/bigbills", response_model=BillOut, status_code=201)
def create(body: CreateIn, db: Session = Depends(get_db), me: User = Depends(staff)):
    return _bill(db, bigbill_service.create(db, me, body.quotation_nos, body.promo_code))


@router.get("/sales/bigbills/{bill_no}", response_model=BillOut)
def get(bill_no: str, db: Session = Depends(get_db), me: User = Depends(staff)):
    return _bill(db, bigbill_service.get(db, bill_no))


@router.post("/sales/bigbills/{bill_no}/cancel", response_model=BillOut)
def cancel(bill_no: str, db: Session = Depends(get_db), me: User = Depends(staff)):
    """ยกเลิกบิลรวม — ใบในบิลกลับไปเป็นใบรอชำระปกติ (จ่ายแยก/รวมบิลใหม่ได้)"""
    b = bigbill_service.get(db, bill_no)
    if b.status == "paid":
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="บิลนี้ชำระแล้ว ยกเลิกไม่ได้")
    bigbill_service.cancel(db, b, me, "พนักงานกดยกเลิกบิลรวม")
    db.commit()
    return _bill(db, b)


@router.post("/sales/bigbills/{bill_no}/pay", response_model=PaymentOut, status_code=201)
def pay(bill_no: str, body: PayIn, db: Session = Depends(get_db), me: User = Depends(staff)):
    return payment_out(bigbill_service.pay(db, bigbill_service.get(db, bill_no), me, body.method))
