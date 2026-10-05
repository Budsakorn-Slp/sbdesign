"""ชำระเงิน + ส่งต่อ SAP
- ไม่มีช่องทาง "เงินสด" ในระบบเลย — เซลล์ห้ามรับเงินเอง (ข้อกำหนดข้อ 9)
- จ่ายผ่าน provider (mock) → webhook เซ็น HMAC เข้ามา → mark paid → สร้าง Sales Order ที่ SAP
- SAP ล่ม: เงินรับแล้วต้องไม่หาย → เข้าคิว sap_sync_jobs ให้ retry (แอดมินเห็นรายการ failed)
"""
import hashlib
import hmac
import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.sap import SapError, get_sap_client
from app.models.common import utcnow
from app.integrations.sap.sales_order import SalesOrderDTO, SoAmounts, SoLine
from app.models.payment import Payment, SapSyncJob
from app.models.quotation import Quotation
from app.models.user import User
from app.services import audit_service, quotation_service

log = logging.getLogger("sb.payment")

METHODS = ("qr_promptpay", "card", "installment", "link")
INTENT_MINUTES = 15
RETRY_BACKOFF_MINUTES = (1, 5, 15, 60, 240)
MAX_ATTEMPTS = len(RETRY_BACKOFF_MINUTES)


def _payment_no(db: Session) -> str:
    return quotation_service._doc_no(db, Payment, Payment.payment_no, "PAY")


def amount_for(q: Quotation, kind: str) -> Decimal:
    return Decimal(q.deposit_amount if kind == "deposit" else q.grand_total)


def _qr_payload(no: str, amount: Decimal) -> str:
    """mock EMVCo QR — ฝั่ง frontend เอาไปวาดเป็น QR ได้เลย"""
    return f"00020101021229370016A000000677010111011300000000000053037645402{amount:.2f}5802TH6304{no[-4:]}"


def create_intent(db: Session, q: Quotation, actor: User | None, method: str, kind: str) -> Payment:
    if method == "cash":
        raise HTTPException(status_code=400, detail="ระบบไม่รับเงินสด — ลูกค้าชำระที่แคชเชียร์หรือผ่าน QR/บัตร/ผ่อนเท่านั้น")
    if method not in METHODS:
        raise HTTPException(status_code=422, detail=f"ช่องทางชำระเงินไม่ถูกต้อง (ใช้ได้: {', '.join(METHODS)})")
    if kind not in ("full", "deposit"):
        raise HTTPException(status_code=422, detail="kind ต้องเป็น full หรือ deposit")
    # ด่านนี้ต้องอยู่ฝั่งหลังบ้าน ไม่ใช่แค่ซ่อนปุ่ม — ลิงก์จ่ายเงินที่เคยส่งให้ลูกค้าไปแล้ว
    # ยังมี ?deposit=1 ติดอยู่ และใครก็ยิง API ตรงได้ ถ้ากันแค่หน้าจอก็เก็บเงินไม่ครบจริง
    if kind == "deposit" and not get_settings().deposit_enabled:
        raise HTTPException(status_code=400, detail="ตอนนี้รับชำระเต็มจำนวนอย่างเดียว ยังไม่เปิดรับมัดจำ")
    if q.status != "issued":
        raise HTTPException(status_code=400, detail=f"ใบเสนอราคานี้ชำระเงินไม่ได้ (สถานะ {q.status})")
    if q.valid_until < utcnow().date():
        raise HTTPException(status_code=400, detail="ใบเสนอราคาหมดอายุแล้ว กรุณาให้พนักงานออกใบใหม่")

    # intent เดิมที่ยังไม่หมดอายุและเงื่อนไขเดียวกัน → ใช้ใบเดิม (กดซ้ำไม่สร้างซ้ำ)
    now = utcnow()
    old = db.scalar(select(Payment).where(Payment.quotation_id == q.id, Payment.status == "pending").order_by(Payment.created_at.desc()))
    if old and old.expires_at > now:
        if old.method == method and old.kind == kind:
            return old
        old.status = "cancelled"

    amount = amount_for(q, kind)
    no = _payment_no(db)
    p = Payment(
        payment_no=no, quotation_id=q.id, method=method, kind=kind, amount=amount, status="pending",
        provider_ref=f"mockpsp_{no.replace('-', '').lower()}",
        qr_payload=_qr_payload(no, amount) if method == "qr_promptpay" else None,
        pay_url=f"/pay/{q.quotation_no}?p={no}",
        expires_at=now + timedelta(minutes=INTENT_MINUTES),
        created_by_user_id=actor.id if actor else None,
    )
    db.add(p)
    audit_service.log(db, actor, "payment.intent", "quotation", q.quotation_no, {"payment_no": no, "method": method, "kind": kind, "amount": str(amount)})
    db.commit()
    db.refresh(p)
    return p


def get_payment(db: Session, payment_no: str) -> Payment:
    p = db.scalar(select(Payment).where(Payment.payment_no == payment_no))
    if not p:
        raise HTTPException(status_code=404, detail="ไม่พบรายการชำระเงินนี้")
    if p.status == "pending" and p.expires_at < utcnow():
        p.status = "expired"
        db.commit()
    return p


# ---------- webhook ----------
def sign(body: bytes) -> str:
    return hmac.new(get_settings().payment_webhook_secret.encode(), body, hashlib.sha256).hexdigest()


def handle_webhook(db: Session, body: bytes, signature: str | None) -> dict:
    if not signature or not hmac.compare_digest(signature, sign(body)):
        raise HTTPException(status_code=401, detail="ลายเซ็น webhook ไม่ถูกต้อง")
    try:
        data = json.loads(body.decode())
    except ValueError:
        raise HTTPException(status_code=400, detail="payload ไม่ใช่ JSON")

    p = db.scalar(select(Payment).where(Payment.payment_no == str(data.get("payment_no", ""))))
    if not p:
        raise HTTPException(status_code=404, detail="ไม่พบรายการชำระเงินนี้")
    event = str(data.get("event", "payment.succeeded"))
    p.raw_json = data

    if p.status == "paid":  # provider ยิงซ้ำได้ — ต้อง idempotent
        return {"ok": True, "duplicate": True, "payment_no": p.payment_no, "status": p.status, "sap_so_no": p.quotation.sap_so_no}
    if event != "payment.succeeded":
        p.status = "failed"
        p.failed_reason = str(data.get("reason") or event)
        db.commit()
        return {"ok": True, "payment_no": p.payment_no, "status": p.status}

    p.status = "paid"
    p.paid_at = utcnow()
    q = p.quotation
    q.status = "paid"
    q.paid_at = p.paid_at
    audit_service.log(db, None, "payment.paid", "quotation", q.quotation_no, {"payment_no": p.payment_no, "kind": p.kind, "amount": str(p.amount)}, role="system")
    db.commit()

    push_to_sap(db, q)
    db.refresh(q)
    return {"ok": True, "payment_no": p.payment_no, "status": p.status, "quotation_status": q.status, "sap_so_no": q.sap_so_no, "sap_sync_status": q.sap_sync_status}


# ---------- ส่งต่อ SAP ----------
def _job_for(db: Session, q: Quotation) -> SapSyncJob:
    job = db.scalar(select(SapSyncJob).where(SapSyncJob.quotation_id == q.id))
    if not job:
        job = SapSyncJob(quotation_id=q.id)
        db.add(job)
    return job


def push_to_sap(db: Session, q: Quotation) -> Quotation:
    """เรียก create_sales_order — ล้มเหลวไม่ throw ต่อ (เงินรับแล้ว) แต่เข้าคิว retry"""
    job = _job_for(db, q)
    job.attempts = (job.attempts or 0) + 1
    try:
        client = get_sap_client()
        doc = build_sales_order(db, q)
        # adapter ที่รองรับ payload เต็มใช้ตัวใหม่ · mock เก่าที่ยังไม่มี method นี้ถอยไปตัวเดิม
        res = client.create_sales_order_doc(doc) if hasattr(client, "create_sales_order_doc") else client.create_sales_order(q.quotation_no)
        if not res.ok or not res.sap_so_no:
            raise SapError(res.message or "SAP ปฏิเสธการสร้าง Sales Order")
        q.sap_so_no = res.sap_so_no
        q.sap_sync_status = "ok"
        q.sap_sync_error = None
        q.status = "converted"
        job.status, job.last_error, job.done_at = "ok", None, utcnow()
        audit_service.log(db, None, "sap.so_created", "quotation", q.quotation_no, {"sap_so_no": res.sap_so_no, "attempts": job.attempts}, role="system")
    except SapError as e:
        q.sap_sync_status = "failed"
        q.sap_sync_error = str(e)
        job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "pending"
        job.last_error = str(e)
        job.next_retry_at = utcnow() + timedelta(minutes=RETRY_BACKOFF_MINUTES[min(job.attempts, MAX_ATTEMPTS) - 1])
        log.warning("สร้าง SO ไม่สำเร็จ %s (ครั้งที่ %s): %s", q.quotation_no, job.attempts, e)
        audit_service.log(db, None, "sap.so_failed", "quotation", q.quotation_no, {"error": str(e), "attempts": job.attempts}, role="system")
    db.commit()
    db.refresh(q)
    return q


def due_jobs(db: Session, limit: int = 20) -> list[SapSyncJob]:
    return list(db.scalars(select(SapSyncJob).where(SapSyncJob.status == "pending", SapSyncJob.next_retry_at <= utcnow()).limit(limit)).all())


def run_retry_queue(db: Session, limit: int = 20) -> dict:
    """เรียกจาก worker/cron หรือปุ่มในหน้า admin"""
    ok = failed = 0
    for job in due_jobs(db, limit):
        q = push_to_sap(db, job.quotation)
        ok, failed = (ok + 1, failed) if q.sap_sync_status == "ok" else (ok, failed + 1)
    return {"processed": ok + failed, "ok": ok, "failed": failed}


def list_sync_jobs(db: Session, status: str | None = None) -> list[SapSyncJob]:
    stmt = select(SapSyncJob).order_by(SapSyncJob.updated_at.desc())
    if status:
        stmt = stmt.where(SapSyncJob.status == status)
    return list(db.scalars(stmt).all())


def retry_one(db: Session, quotation_no: str, actor: User) -> Quotation:
    q = db.scalar(select(Quotation).where(Quotation.quotation_no == quotation_no))
    if not q:
        raise HTTPException(status_code=404, detail="ไม่พบใบเสนอราคานี้")
    if q.status not in ("paid", "converted") or q.sap_sync_status == "ok":
        raise HTTPException(status_code=400, detail="ใบนี้ไม่มีงานค้างส่ง SAP")
    job = _job_for(db, q)
    job.status, job.next_retry_at = "pending", utcnow()
    audit_service.log(db, actor, "sap.retry", "quotation", q.quotation_no, {"attempts": job.attempts})
    db.commit()
    return push_to_sap(db, q)


def paid_summary(db: Session, q: Quotation) -> dict:
    rows = db.scalars(select(Payment).where(Payment.quotation_id == q.id, Payment.status == "paid")).all()
    paid = sum((Decimal(r.amount) for r in rows), Decimal(0))
    return {"paid_total": str(paid), "outstanding": str(max(Decimal(0), Decimal(q.grand_total) - paid)), "payments": rows}


def count_paid(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(Payment).where(Payment.status == "paid")) or 0)


# ---------- ประกอบ payload ส่ง SAP ----------
def build_sales_order(db: Session, q: Quotation) -> SalesOrderDTO:
    """แปลง Quotation ที่จ่ายเงินแล้ว → payload สร้าง Sales Order

    อ่านจากเอกสารที่บันทึกไว้อย่างเดียว ไม่ดึงสดจากตะกร้าหรือ SAP ใหม่ — ราคา/ส่วนลด/ค่าส่ง
    ต้องเป็นชุดเดียวกับที่ลูกค้าเห็นตอนกดจ่าย ไม่งั้นยอดใน SAP กับใบเสร็จจะไม่ตรงกัน
    เวลาโปรโมชันหมดอายุระหว่างทาง
    """
    s = get_settings()
    snap = q.customer_snapshot or {}
    pay = db.scalar(
        select(Payment).where(Payment.quotation_id == q.id, Payment.status == "paid").order_by(Payment.created_at.desc())
    )
    return SalesOrderDTO(
        quotation_no=q.quotation_no,
        # ลูกค้าที่ยังไม่ผูกเลขสมาชิกใช้เลข walk-in — SAP บังคับต้องมี CUSTOMER เสมอ
        customer_no=(snap.get("sap_customer_no") or s.sap_walkin_customer),
        order_type=s.sap_order_type,
        sales_org=s.sap_sales_org,
        distr_chan=s.sap_distr_chan,
        division=s.sap_division,
        req_date=q.slot_date or (date.today() + timedelta(days=s.sap_avail_lead_days)),
        channel=q.channel,
        customer_name=snap.get("name") or "",
        customer_phone=snap.get("phone"),
        customer_email=snap.get("email"),
        ship_address=q.ship_address,
        ship_postcode=q.ship_postcode,
        ship_zone=q.ship_zone,
        slot_date=q.slot_date,
        slot_period=q.slot_period,
        amounts=SoAmounts(
            subtotal=q.subtotal,
            discount_total=q.discount_total,
            shipping_fee=q.shipping_fee,
            install_fee=q.install_fee,
            shipping_discount=q.shipping_discount,
            vat=q.vat,
            grand_total=q.grand_total,
            deposit_amount=q.deposit_amount,
        ),
        items=[
            SoLine(
                line_no=(i + 1) * 10,  # POSNR 10, 20, 30... ตามธรรมเนียม SAP
                matnr=ln.matnr,
                name=ln.name,
                qty=ln.qty,
                unit_price=ln.unit_price,
                line_discount=ln.line_discount,
                line_total=ln.line_total,
                supply_mode=ln.supply_mode,
                plant_code=ln.plant_code,
                atp_date=ln.atp_date,
                requires_install=ln.requires_install,
            )
            for i, ln in enumerate(q.lines)
        ],
        payment_no=pay.payment_no if pay else None,
        paid_at=q.paid_at.isoformat() if q.paid_at else None,
    )
