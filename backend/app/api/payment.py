import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, require_role
from app.models.common import utcnow
from app.core.config import get_settings
from app.db.session import get_db
from app.models.payment import Payment, SapSyncJob
from app.models.user import User
from app.services import payment_service, quotation_service

router = APIRouter(tags=["payment"])
manager = require_role("manager", "admin")


class IntentIn(BaseModel):
    method: str = "qr_promptpay"  # qr_promptpay | card | installment | link (ไม่มี cash)
    kind: str = "full"  # full | deposit


class PendingPaymentOut(BaseModel):
    """รายการรอชำระที่โชว์ในแท็บของลูกค้า"""

    quotation_no: str
    payment_no: str | None = None
    amount: str
    method: str | None = None
    issued_at: datetime
    expires_at: datetime | None = None
    seconds_left: int | None = None   # ติดลบได้ถ้าเพิ่งหมดพอดี — หน้าเว็บปัดเป็น 0 เอง
    item_count: int = 0
    first_item: str | None = None


class PaymentOut(BaseModel):
    payment_no: str
    quotation_no: str
    method: str
    kind: str
    amount: str
    status: str
    qr_payload: str | None
    pay_url: str | None
    expires_at: datetime
    paid_at: datetime | None
    sap_so_no: str | None
    sap_sync_status: str
    quotation_status: str
    # เหตุผลที่ธนาคารปฏิเสธ — หน้าผลการชำระเงินต้องบอกให้ตรง ไม่ใช่ "ไม่สำเร็จ" ลอยๆ
    # แล้วลูกค้าโทรมาถามว่าทำไม
    failed_reason: str | None = None


class SyncJobOut(BaseModel):
    quotation_no: str
    customer_name: str | None
    grand_total: str
    status: str
    attempts: int
    last_error: str | None
    next_retry_at: datetime
    sap_so_no: str | None
    paid_at: datetime | None


def payment_out(p: Payment) -> PaymentOut:
    q = p.quotation
    return PaymentOut(
        payment_no=p.payment_no, quotation_no=q.quotation_no, method=p.method, kind=p.kind, amount=str(p.amount), status=p.status,
        qr_payload=p.qr_payload, pay_url=p.pay_url, expires_at=p.expires_at, paid_at=p.paid_at,
        sap_so_no=q.sap_so_no, sap_sync_status=q.sap_sync_status, quotation_status=q.status,
        failed_reason=p.failed_reason,
    )


@router.post("/quotations/{no}/payment-intent", response_model=PaymentOut, status_code=201)
def create_payment_intent(no: str, body: IntentIn, t: str | None = Query(default=None), db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    """ลูกค้าเปิดจากลิงก์ (?t=) หรือเซลล์กดที่แท็บเล็ต — ได้ QR / ลิงก์จ่าย · เต็มจำนวนหรือมัดจำ 20%"""
    q = quotation_service.get_quotation(db, no)
    quotation_service.check_access(q, user, t)
    return payment_out(payment_service.create_intent(db, q, user, body.method, body.kind))


@router.get("/payments/{payment_no}", response_model=PaymentOut)
def get_payment(payment_no: str, t: str | None = Query(default=None), db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    """หน้าจ่ายเงิน poll สถานะจากตรงนี้ (รอ webhook จาก provider)"""
    p = payment_service.get_payment(db, payment_no)
    quotation_service.check_access(p.quotation, user, t)
    return payment_out(p)


@router.post("/webhooks/payment")
async def payment_webhook(request: Request, x_signature: str | None = Header(default=None), db: Session = Depends(get_db)):
    """provider ยิงเข้ามา — ต้องเซ็น HMAC-SHA256 ด้วย PAYMENT_WEBHOOK_SECRET · ยิงซ้ำได้ (idempotent)"""
    return payment_service.handle_webhook(db, await request.body(), x_signature)


@router.post("/payments/{payment_no}/mock-confirm", response_model=PaymentOut)
def mock_confirm(
    payment_no: str,
    outcome: str = Query(default="paid", pattern="^(paid|failed|cancelled)$", description="ผลที่อยากจำลอง"),
    t: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """โหมด dev เท่านั้น: จำลองผลจากธนาคาร — หน้า mock ของ KBank เรียกตัวนี้

    จำลองได้ 3 ทางเพราะของจริงก็มีสามทาง และเส้นทางที่ไม่สำเร็จคือเส้นที่คนลืมทดสอบ
    แล้วไปเจอหน้างานว่าเว็บค้างอยู่ที่ "กำลังรอผล" ตลอดกาล

    ปิดด้วย APP_ENV ไม่ใช่ OTP_DEBUG — ของเดิมผูกกับ OTP_DEBUG ซึ่งเป็นคนละเรื่องกัน
    พอเปิด OTP_DEBUG ไว้ให้ผู้ทดสอบดูรหัสบนจอ ปุ่ม "จ่ายเงินสำเร็จ" ก็เปิดตามไปด้วย
    (ตรวจบนเว็บทดสอบจริงแล้วว่าเปิดอยู่) · APP_ENV เป็นธงเดียวที่บอกว่า "นี่ของจริงแล้ว"
    """
    s = get_settings()
    # ต่อ gateway จริงแล้วห้ามใช้เด็ดขาด ไม่ว่าตั้งธงอะไรไว้ — ปลอมว่าจ่ายแล้วทั้งที่เงินไม่เข้า
    # จะไหลต่อไปเป็น SO ใน SAP แล้วตามเก็บเงินทีหลังไม่ได้
    if s.payment_provider != "mock":
        raise HTTPException(status_code=404, detail="ต่อช่องทางชำระเงินจริงอยู่ — จำลองผลไม่ได้")
    if s.is_prod and not s.mock_payment_enabled:
        raise HTTPException(status_code=404, detail="ปิดใช้งานในโหมด production")
    p = payment_service.get_payment(db, payment_no)
    quotation_service.check_access(p.quotation, user, t)

    # ลูกค้ากดยกเลิกเอง ไม่ใช่ธนาคารปฏิเสธ — webhook ของจริงไม่มีเหตุการณ์นี้
    # (provider ถือว่ารายการยังค้าง แล้วหมดอายุไปเอง) จึงตั้งสถานะตรงนี้ ไม่ผ่าน webhook
    if outcome == "cancelled":
        return payment_out(payment_service.cancel_payment(db, p))

    event = "payment.succeeded" if outcome == "paid" else "payment.failed"
    payload = {"event": event, "payment_no": p.payment_no, "provider_ref": p.provider_ref, "amount": str(p.amount)}
    if outcome == "failed":
        payload["reason"] = "จำลอง: ธนาคารปฏิเสธรายการ (ยอดเงินไม่พอ)"
    body = json.dumps(payload).encode()
    payment_service.handle_webhook(db, body, payment_service.sign(body))
    return payment_out(payment_service.get_payment(db, payment_no))


@router.get("/me/pending-payments", response_model=list[PendingPaymentOut])
def my_pending_payments(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """คำสั่งซื้อที่รอชำระของฉัน — แท็บ "รอชำระเงิน" กับตัวเลขบนกระดิ่งอ่านจากตัวนี้

    กวาดของที่หมดเวลาก่อนตอบเสมอ ไม่งั้นลูกค้าเห็นรายการที่หมดอายุไปแล้วค้างอยู่
    แล้วกดจ่ายไม่ได้ (job ตามรอบก็กวาดอยู่ แต่คนเปิดหน้าต้องเห็นของจริง ณ วินาทีนั้น)
    """
    payment_service.sweep_expired(db)
    rows = payment_service.pending_for_user(db, me)
    now = utcnow()
    return [
        PendingPaymentOut(
            quotation_no=q.quotation_no, payment_no=p.payment_no if p else None,
            amount=str(p.amount if p else q.grand_total), method=p.method if p else None,
            issued_at=q.issued_at, expires_at=p.expires_at if p else None,
            seconds_left=int((p.expires_at - now).total_seconds()) if p else None,
            item_count=len(q.lines), first_item=q.lines[0].name if q.lines else None,
        )
        for q, p in rows
    ]


# ---------- admin: คิวส่ง SAP ----------
@router.get("/admin/sap-sync", response_model=list[SyncJobOut])
def list_sap_sync(status: str | None = None, db: Session = Depends(get_db), me: User = Depends(manager)):
    return [_job_out(j) for j in payment_service.list_sync_jobs(db, status)]


@router.post("/admin/sap-sync/run")
def run_sap_sync(db: Session = Depends(get_db), me: User = Depends(manager)):
    return payment_service.run_retry_queue(db)


@router.post("/admin/sap-sync/{quotation_no}/retry", response_model=SyncJobOut)
def retry_sap_sync(quotation_no: str, db: Session = Depends(get_db), me: User = Depends(manager)):
    q = payment_service.retry_one(db, quotation_no, me)
    return _job_out(payment_service._job_for(db, q))


def _job_out(j: SapSyncJob) -> SyncJobOut:
    q = j.quotation
    return SyncJobOut(
        quotation_no=q.quotation_no, customer_name=(q.customer_snapshot or {}).get("name"), grand_total=str(q.grand_total),
        status=j.status, attempts=j.attempts, last_error=j.last_error, next_retry_at=j.next_retry_at, sap_so_no=q.sap_so_no, paid_at=q.paid_at,
    )
