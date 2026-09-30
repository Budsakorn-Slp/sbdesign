"""จำกัดอัตราการยืนยันตัวตน — กันเดารหัส/ยิง OTP รัว

นับจากตาราง auth_attempts ไม่ได้เก็บในหน่วยความจำ เพราะโปรดักชันรันหลาย worker/หลายเครื่อง
ตัวนับในหน่วยความจำจะแยกกันคนละชุด ทำให้เพดานจริงคูณตามจำนวน worker (= แทบไม่ได้กันอะไรเลย)

เพดานทั้งหมดตั้งไว้ที่เดียวตรงนี้ ปรับได้โดยไม่ต้องไล่แก้ตาม service
"""
from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.common import utcnow
from app.models.user import AuthAttempt


@dataclass(frozen=True)
class Limit:
    """ล้มเหลวได้ไม่เกิน max ครั้งในช่วง window นาที"""

    max: int
    window_minutes: int


# --- เพดานของแต่ละอย่าง -------------------------------------------------------
# ล็อกอินผิดซ้ำ: ผูกกับ "บัญชีที่ถูกลอง" เป็นหลัก + เพดานรวมต่อ IP กันคนไล่ลองหลายบัญชี
LOGIN_PER_ACCOUNT = Limit(max=5, window_minutes=15)
LOGIN_PER_IP = Limit(max=20, window_minutes=15)
# ขอ OTP: กันยิงรัวใส่เบอร์คนอื่น (ค่าส่ง SMS เป็นเงินจริง และปลายทางโดนสแปม)
OTP_SEND_PER_PHONE = Limit(max=5, window_minutes=60)
OTP_SEND_PER_IP = Limit(max=20, window_minutes=60)
OTP_RESEND_COOLDOWN_SECONDS = 60
# กรอก OTP ผิด: ต่อเบอร์ (กันไล่เดา 6 หลักข้ามรหัสหลายใบ) — ต่อ "ใบ" คุมด้วย OtpCode.attempts
OTP_VERIFY_PER_PHONE = Limit(max=10, window_minutes=60)
OTP_MAX_ATTEMPTS_PER_CODE = 5
# ผูกเลขสมาชิก: ช้าๆ พอ ไม่ควรมีใครต้องลองเกินนี้ในหนึ่งชั่วโมง
LINK_PER_USER = Limit(max=10, window_minutes=60)


def client_ip(request: Request | None) -> str | None:
    return request.client.host if request and request.client else None


def record(db: Session, kind: str, key: str, ok: bool, request: Request | None = None) -> None:
    """บันทึกหนึ่งครั้ง — ผู้เรียกเป็นคน commit (ให้อยู่ธุรกรรมเดียวกับงานหลัก)"""
    db.add(AuthAttempt(kind=kind, key=key, ok=ok, ip=client_ip(request)))


def _failures(db: Session, kind: str, key: str, limit: Limit) -> int:
    since = utcnow() - timedelta(minutes=limit.window_minutes)
    return int(
        db.scalar(
            select(func.count())
            .select_from(AuthAttempt)
            .where(AuthAttempt.kind == kind, AuthAttempt.key == key, AuthAttempt.ok.is_(False), AuthAttempt.created_at >= since)
        )
        or 0
    )


def guard(db: Session, kind: str, key: str, limit: Limit, message: str) -> None:
    """เกินเพดานแล้วโยน 429 — เรียกก่อนทำงานจริงเสมอ

    นับเฉพาะครั้งที่ "ล้มเหลว" เพื่อให้คนที่ใช้งานถูกต้องไม่โดนลูกหลง และตัวนับจะคลายเองตามเวลา
    (ไม่ต้องมีปุ่มปลดล็อกให้แอดมิน ซึ่งเป็นภาระและเป็นช่องให้หลอกถามกันเอง)
    """
    if _failures(db, kind, key, limit) >= limit.max:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message)


def guard_cooldown(db: Session, kind: str, key: str, seconds: int, message: str) -> None:
    """กันกดซ้ำเร็วเกิน — นับจากครั้งล่าสุดไม่ว่าจะสำเร็จหรือไม่"""
    last = db.scalar(
        select(func.max(AuthAttempt.created_at)).where(AuthAttempt.kind == kind, AuthAttempt.key == key)
    )
    if last and (utcnow() - last).total_seconds() < seconds:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message)


def purge(db: Session, older_than_days: int = 30) -> int:
    """ลบของเก่าทิ้ง — ตารางนี้โตเร็วและไม่มีประโยชน์เมื่อพ้นหน้าต่างเวลาไปแล้ว"""
    cutoff = utcnow() - timedelta(days=older_than_days)
    rows = db.query(AuthAttempt).filter(AuthAttempt.created_at < cutoff).delete(synchronize_session=False)
    db.commit()
    return int(rows or 0)
