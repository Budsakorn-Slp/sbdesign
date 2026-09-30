"""สมุดที่อยู่จัดส่งของลูกค้า — เพิ่ม/แก้/ลบ/ตั้งเป็นค่าเริ่มต้น

ที่อยู่ในสมุดนี้ใช้สำหรับ "ส่งของ" อย่างเดียว ไม่ใช่ที่อยู่ใบกำกับภาษี
ค่าส่งคิดจากรหัสไปรษณีย์ จึงบังคับให้มีรหัสไปรษณีย์เสมอ (ไม่มี = คิดค่าส่งไม่ได้จริง)
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common import utcnow
from app.models.user import User, UserAddress
from app.services import audit_service

MAX_ADDRESSES = 20  # กันสมุดบวมจนหน้าเลือกที่อยู่ใช้ไม่ได้ · ลูกค้าจริงไม่เกินหลักหน่วย


def list_for(db: Session, user: User) -> list[UserAddress]:
    """ค่าเริ่มต้นขึ้นก่อนเสมอ ที่เหลือเรียงตามเวลาที่เพิ่ม — ลำดับคงที่ทุกครั้งที่เปิดหน้า"""
    rows = db.scalars(select(UserAddress).where(UserAddress.user_id == user.id)).all()
    return sorted(rows, key=lambda a: (not a.is_default, a.created_at))


def get(db: Session, user: User, address_id: str) -> UserAddress:
    a = db.get(UserAddress, address_id)
    if not a or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="ไม่พบที่อยู่นี้")
    return a


def _clean(data: dict) -> dict:
    out = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items() if v is not None}
    if "postcode" in out:
        out["postcode"] = "".join(ch for ch in out["postcode"] if ch.isdigit())[:5]
    return out


def _require(a: UserAddress) -> None:
    missing = [w for w, ok in (("ชื่อผู้รับ", a.receiver), ("เบอร์โทร", a.phone),
                               ("ที่อยู่", a.address), ("รหัสไปรษณีย์", len(a.postcode) == 5)) if not ok]
    if missing:
        raise HTTPException(status_code=422, detail="ยังขาด " + " · ".join(missing))


def _set_default(db: Session, user: User, target: UserAddress) -> None:
    """ค่าเริ่มต้นมีได้ใบเดียว — ตั้งใบใหม่ก็ถอดใบเก่าออกให้เอง"""
    for other in db.scalars(select(UserAddress).where(UserAddress.user_id == user.id)).all():
        other.is_default = other.id == target.id
    target.is_default = True
    # users.default_* ยังมีระบบเก่าใช้อยู่ (หัวเว็บ/หน้าโปรไฟล์) — ให้ตรงกับใบที่ตั้งไว้
    user.default_address = target.one_line
    user.default_postcode = target.postcode


def create(db: Session, user: User, data: dict) -> UserAddress:
    if len(list_for(db, user)) >= MAX_ADDRESSES:
        raise HTTPException(status_code=422, detail=f"เก็บที่อยู่ได้สูงสุด {MAX_ADDRESSES} รายการ — ลบที่ไม่ใช้แล้วออกก่อน")
    want_default = bool(data.pop("is_default", False))
    a = UserAddress(user_id=user.id, **_clean(data))
    _require(a)
    db.add(a)
    db.flush()
    # ใบแรกของบัญชี = ค่าเริ่มต้นอัตโนมัติ ไม่ต้องให้ลูกค้ามากดเองอีกที
    if want_default or len(list_for(db, user)) == 1:
        _set_default(db, user, a)
    audit_service.log(db, user, "address.create", "user_address", a.id, {"postcode": a.postcode})
    db.commit()
    db.refresh(a)
    return a


def update(db: Session, user: User, address_id: str, data: dict) -> UserAddress:
    a = get(db, user, address_id)
    want_default = data.pop("is_default", None)
    for k, v in _clean(data).items():
        setattr(a, k, v)
    _require(a)
    if want_default:
        _set_default(db, user, a)
    elif a.is_default:
        # แก้ใบที่เป็นค่าเริ่มต้นอยู่ → ข้อมูลที่ระบบเก่าอ่าน (users.default_*) ต้องตามไปด้วย
        _set_default(db, user, a)
    a.updated_at = utcnow()
    audit_service.log(db, user, "address.update", "user_address", a.id, {"postcode": a.postcode})
    db.commit()
    db.refresh(a)
    return a


def set_default(db: Session, user: User, address_id: str) -> UserAddress:
    a = get(db, user, address_id)
    _set_default(db, user, a)
    audit_service.log(db, user, "address.set_default", "user_address", a.id, {})
    db.commit()
    db.refresh(a)
    return a


def remove(db: Session, user: User, address_id: str) -> None:
    a = get(db, user, address_id)
    was_default = a.is_default
    db.delete(a)
    db.flush()
    # ลบใบที่เป็นค่าเริ่มต้น → เลื่อนใบที่เหลือใบแรกขึ้นมาแทน จะได้ไม่มีสถานะ "ไม่มีค่าเริ่มต้น"
    left = list_for(db, user)
    if was_default and left:
        _set_default(db, user, left[0])
    elif not left:
        user.default_address = None
        user.default_postcode = None
    audit_service.log(db, user, "address.delete", "user_address", address_id, {})
    db.commit()
