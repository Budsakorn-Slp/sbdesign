"""เส้นที่ K-Payment Gateway (กสิกร) จะเรียกกลับมาหาเรา — Embedded UI / Smart Pay

    POST /payment/card/notify     ธนาคารแจ้งผลบัตรเครดิต (server-to-server)
    POST /payment/qr/notify       ธนาคารแจ้งผล QR (server-to-server)
    GET  /payment/card/callback   เบราว์เซอร์ลูกค้าถูกพากลับมาที่นี่หลังจ่ายเสร็จ
    POST /payment/card/callback   เผื่อธนาคารส่งกลับเป็น form post

สถานะ: **เปิดรับไว้แล้ว แต่ยังไม่ตัดสถานะการจ่าย**

ยังไม่มีเอกสาร API ฉบับเต็ม (หน้า apiportal เป็นหน้า JS ดึงเนื้อหาไม่ได้) จึงยังไม่รู้
ชื่อฟิลด์และวิธีเซ็นข้อความ · เดาเองไม่ได้เพราะสองอย่างนี้ผิดแล้วจะรู้ตอนเงินไม่เข้า

สิ่งที่ทำได้ตอนนี้และมีประโยชน์จริง: **บันทึก payload ดิบทุกครั้งที่ธนาคารยิงเข้ามา**
พอเริ่มทดสอบ sandbox จะเห็นชื่อฟิลด์จริงจาก audit_logs ทันที ไม่ต้องรอเอกสาร

notify ตอบ 503 ไว้ก่อน (ไม่ใช่ 200) เพราะ gateway ส่วนใหญ่จะยิงซ้ำเมื่อไม่ได้ 2xx —
ถ้าตอบ 200 ทิ้งไปเฉยๆ รายการจ่ายจริงจะหายไปโดยไม่มีใครรู้ · ตอบ 503 แปลว่า
"รับไว้แล้วแต่ยังประมวลผลไม่ได้" ธนาคารจะยิงใหม่ และเราเห็นของค้างในล็อก
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.models.user import User
from app.services import audit_service

log = logging.getLogger("sb.payment.kbank")
router = APIRouter(tags=["payment"])

# header ที่ "น่าจะ" มีลายเซ็น — เก็บทุกตัวที่เข้าข่ายไว้ดูตอนทดสอบจริง
# ไม่ได้ใช้ตัดสินอะไร แค่ช่วยให้รู้ว่าธนาคารส่งอะไรมาบ้าง
SIGNATURE_HEADER_HINTS = ("x-signature", "x-kbank-signature", "signature", "x-api-signature", "authorization")


def _snapshot(request: Request, raw: bytes) -> dict:
    """เก็บเท่าที่จำเป็นต่อการถอดสเปก — ไม่เก็บทั้ง header เพราะมีคุกกี้/โทเคนปนได้"""
    heads = {k.lower(): v for k, v in request.headers.items() if k.lower() in SIGNATURE_HEADER_HINTS}
    body = raw.decode("utf-8", "replace")[:4000]
    return {"path": request.url.path, "query": str(request.url.query)[:1000],
            "headers": heads, "body": body, "content_type": request.headers.get("content-type", "")}


async def _record(request: Request, db: Session, kind: str) -> dict:
    raw = await request.body()
    snap = _snapshot(request, raw)
    audit_service.log(db, None, f"kbank.{kind}", "payment", None, snap, role="system")
    db.commit()
    log.warning("ได้รับ %s จาก K-Payment Gateway แต่ยังประมวลผลไม่ได้: %s", kind, snap["body"][:300])
    return snap


@router.post("/payment/card/notify")
async def card_notify(request: Request, db: Session = Depends(get_db)):
    await _record(request, db, "card_notify")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="ยังไม่ได้ต่อ K-Payment Gateway — บันทึกข้อความไว้แล้ว กรุณาส่งซ้ำภายหลัง",
    )


@router.post("/payment/qr/notify")
async def qr_notify(request: Request, db: Session = Depends(get_db)):
    await _record(request, db, "qr_notify")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="ยังไม่ได้ต่อ K-Payment Gateway — บันทึกข้อความไว้แล้ว กรุณาส่งซ้ำภายหลัง",
    )


# ตั้งชื่อ operation ให้เองเพราะ GET กับ POST ใช้ฟังก์ชันเดียวกัน
# ปล่อยไว้ FastAPI จะตั้งชื่อซ้ำกันแล้วเตือนทุกครั้งที่สร้าง OpenAPI
@router.api_route("/payment/card/callback", methods=["GET", "POST"], operation_id="kbank_card_callback")
async def card_callback(request: Request, db: Session = Depends(get_db)):
    """ลูกค้าถูกพากลับมาจากหน้าธนาคาร — ต้องพาไปหน้าผลเสมอ ห้ามโชว์ JSON

    ตรงนี้คือสายตาลูกค้า ไม่ใช่ช่องทางตัดสถานะ · สถานะจริงมาจาก notify (server-to-server)
    ซึ่งเชื่อถือได้กว่า เพราะ callback ปลอมได้ด้วยการพิมพ์ URL เอง
    """
    snap = await _record(request, db, "card_callback")

    # ธนาคารน่าจะส่งเลขอ้างอิงของเรากลับมาด้วย แต่ยังไม่รู้ชื่อพารามิเตอร์
    # ลองหาจากชื่อที่พบบ่อย ถ้าไม่เจอก็พาไปหน้ารวมรายการรอชำระแทน ดีกว่าค้างหน้าเปล่า
    q = request.query_params
    ref = next((q[k] for k in ("merchantOrderId", "orderId", "order_id", "ref", "reference", "invoice") if q.get(k)), None)
    target = f"/pay/{ref}/result" if ref else "/account/pending"
    log.info("callback จากธนาคาร — พาไป %s (ref=%s)", target, ref)
    _ = snap
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


class ChargeIn(BaseModel):
    token: str


@router.post("/payments/{payment_no}/kbank/charge")
def kbank_charge(
    payment_no: str,
    body: ChargeIn,
    t: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """ขั้นที่ 10 ของโฟลว์ Embedded UI — ได้ token จาก kpayment.js แล้วเรียก Create Charge API

    คืน redirect_url (Dynamic URL) ให้หน้าเว็บพาลูกค้าไปยืนยันตัวตนกับธนาคารต่อ
    ยังไม่ตัดสถานะว่าจ่ายแล้ว — สถานะจริงมาทาง /payment/card/notify เท่านั้น
    """
    from app.integrations.payment import ChargeRequest, PaymentError
    from app.integrations.payment.kbank import KBankGateway
    from app.services import payment_service, quotation_service

    s = get_settings()
    if s.payment_provider != "kbank":
        raise HTTPException(status_code=400, detail="ยังไม่ได้ตั้งค่าให้ใช้ K-Payment Gateway")
    p = payment_service.get_payment(db, payment_no)
    quotation_service.check_access(p.quotation, user, t)
    if p.status != "pending":
        raise HTTPException(status_code=400, detail=f"รายการนี้สถานะ {p.status} ชำระเงินไม่ได้")

    try:
        gw = KBankGateway.from_settings(s)
        res = gw.charge_with_token(ChargeRequest(
            payment_no=p.payment_no, amount=p.amount, method=p.method,
            description=f"SB Design Square · {p.quotation.quotation_no}",
        ), body.token)
    except PaymentError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    p.provider_ref = res.provider_ref
    p.raw_json = res.raw
    audit_service.log(db, user, "kbank.charge", "payment", p.payment_no, {"provider_ref": res.provider_ref}, role="system")
    db.commit()
    return {"redirect_url": res.redirect_url}


@router.get("/payment/kbank/status")
def kbank_status():
    """บอกว่าโครงฝั่งเราพร้อมแค่ไหน — ไว้เช็คตอนคุยกับทีมธนาคาร"""
    s = get_settings()
    return {
        "provider": s.payment_provider,
        "base_url_set": bool(s.kbank_base_url),
        "merchant_id_set": bool(s.kbank_merchant_id),
        "secret_key_set": bool(s.kbank_secret_key),
        "endpoints": ["/payment/card/notify", "/payment/qr/notify", "/payment/card/callback"],
        "ready": False,
        "blocked_by": "ยังไม่มีสเปกชื่อฟิลด์และวิธีเซ็นข้อความจากธนาคาร",
    }
