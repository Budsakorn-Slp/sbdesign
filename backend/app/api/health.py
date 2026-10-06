from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    s = get_settings()
    return {"status": "ok", "app": s.app_name, "sap_mode": s.sap_mode, "db": "sqlite" if s.is_sqlite else "postgresql"}


@router.get("/public-config")
def public_config():
    """ค่าที่หน้าเว็บต้องรู้ก่อนเข้าสู่ระบบ — เปิดสาธารณะ ห้ามใส่อะไรที่เป็นความลับ

    อ่านตอนรันไทม์ ไม่ใช่ตอน build หน้าเว็บ · จะเปิด/ปิดช่วงทดสอบก็แค่แก้ env แล้วรีสตาร์ท
    ไม่ต้อง build เว็บใหม่ และหน้าเว็บกับหลังบ้านไม่มีทางตั้งค่าไม่ตรงกัน
    """
    s = get_settings()
    return {
        "invite_only": s.invite_only,
        # OTP ใช้ได้จริงไหม — ถ้าไม่ หน้าเว็บต้องซ่อนปุ่ม ไม่ใช่ให้กดแล้วรอรหัสที่ไม่มีวันมา
        "otp_enabled": s.otp_enabled,
        # รับมัดจำไหม — ถ้าไม่ หน้าจ่ายเงินต้องไม่โชว์ปุ่มมัดจำ ไม่ใช่โชว์แล้วกดไม่ผ่าน
        "deposit_enabled": s.deposit_enabled,
        # เซลล์กดลดราคาเองได้ไหม — หน้าจอต้องไม่โชว์ช่องที่หลังบ้านตีกลับอยู่ดี
        "staff_discount_enabled": s.staff_discount_enabled,
        # ปุ่ม Pay Now ของกสิกรต้องใช้ public key + ที่อยู่ kpayment.js
        # ทั้งคู่ไม่ลับโดยออกแบบ (ฝังในหน้าเว็บอยู่แล้ว) ส่วน secret key ห้ามหลุดมาทางนี้เด็ดขาด
        "payment_provider": s.payment_provider,
        "kbank_public_key": s.kbank_public_key,
        "kbank_script_url": s.kbank_script_url,
        "coming_soon_title": s.coming_soon_title,
        "coming_soon_text": s.coming_soon_text,
    }
