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

    pend = db.scalar(select(Payment.payment_no).where(Payment.big_bill_id == b.id, Payment.status == "pending")
                     .order_by(Payment.created_at.desc()))
    return BillOut(
        bill_no=b.bill_no, status=b.status, customer=_customer(b.customer), promo_code=b.promo_code, promo_title=b.promo_title,
        subtotal=b.subtotal, discount=b.discount, grand_total=b.grand_total, created_at=b.created_at, paid_at=b.paid_at,
        items=[BillItemOut(quotation_no=it.quotation.quotation_no, status=it.quotation.status, amount=it.amount,
                           discount_share=it.discount_share, sales_name=it.quotation.sales.name if it.quotation.sales else None,
                           sap_so_no=it.quotation.sap_so_no) for it in b.items],
        pending_payment=pend,
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


@router.post("/sales/bigbills", response_model=BillOut, status_code=201)
def create(body: CreateIn, db: Session = Depends(get_db), me: User = Depends(staff)):
    return _bill(db, bigbill_service.create(db, me, body.quotation_nos, body.promo_code))


@router.get("/sales/bigbills/{bill_no}", response_model=BillOut)
def get(bill_no: str, db: Session = Depends(get_db), me: User = Depends(staff)):
    return _bill(db, bigbill_service.get(db, bill_no))


@router.post("/sales/bigbills/{bill_no}/pay", response_model=PaymentOut, status_code=201)
def pay(bill_no: str, body: PayIn, db: Session = Depends(get_db), me: User = Depends(staff)):
    return payment_out(bigbill_service.pay(db, bigbill_service.get(db, bill_no), me, body.method))
