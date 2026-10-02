"""ผูกบัญชีเว็บเข้ากับ "เลขสมาชิก" (SAP customer) — และกฎความปลอดภัยของการผูก

กฎเดียวที่ห้ามหย่อนเด็ดขาด: **ผูกได้ก็ต่อเมื่อพิสูจน์ว่าถือเบอร์ของสมาชิกรายนั้นจริง**

ถ้าปล่อยให้พิมพ์เลขสมาชิกแล้วผูกได้เลย ใครก็เดา/ไล่เลขสมาชิกคนอื่นมาผูกเข้าบัญชีตัวเอง
แล้วเห็นแต้ม ประวัติการซื้อ ที่อยู่ และเบอร์ของคนนั้นได้ทันที — เลขสมาชิกเป็น "ตัวระบุ"
ไม่ใช่ "ความลับ" (พิมพ์อยู่บนใบเสร็จทุกใบ) จึงใช้เป็นหลักฐานยืนยันตัวตนไม่ได้

ทางผ่านมีสองทางเท่านั้น:
  1. เบอร์ที่ผู้ใช้ยืนยัน OTP ไว้แล้ว ตรงกับเบอร์ในทะเบียนสมาชิก → ผูกได้เลย
  2. ไม่ตรง → ต้องส่ง OTP ไปที่ "เบอร์ในทะเบียนสมาชิก" แล้วกรอกกลับมา (step-up)
     เบอร์นั้นไม่เคยถูกส่งกลับไปให้ผู้ขอเห็นเต็ม โชว์แบบปิดบังอย่างเดียว

การค้นทะเบียนสมาชิกวิ่งผ่าน SAP client เดิม (ตอนนี้เป็น mock) — วันที่ระบบสมาชิกจริงเสร็จ
เปลี่ยนแค่ adapter ตัวนั้น ไม่ต้องแก้ API หรือกฎในไฟล์นี้
"""
import logging

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.sap import get_sap_client
from app.integrations.sap.base import SapError
from app.models.common import utcnow
from app.models.user import MemberLinkEvent, User
from app.services import audit_service, auth_service
from app.services import rate_limit as rl

log = logging.getLogger("sb.member")


def _record(db: Session, user: User | None, kind: str, sap_customer_no: str | None,
            via: str | None = None, phone: str | None = None,
            request: Request | None = None, reason: str | None = None) -> None:
    """ลงบันทึกการผูก/ถอด/ถูกปฏิเสธ — เขียนอย่างเดียว ไม่แก้ไม่ลบ

    บันทึกครั้งที่ไม่ผ่านด้วย เพราะคนที่ไล่เดาเลขสมาชิกคนอื่นจะทิ้งรอยเป็นชุด
    ถ้าเก็บแต่ครั้งที่สำเร็จ จะมองไม่เห็นความพยายามที่ระบบกันไว้ได้เลย
    """
    db.add(MemberLinkEvent(
        user_id=user.id if user else None,
        sap_customer_no=sap_customer_no or None,
        kind=kind,
        via=via,
        # เก็บแบบปิดบัง — เบอร์เต็มมีอยู่ที่ users อยู่แล้ว เก็บซ้ำคือเพิ่มของที่ต้องปกป้อง
        phone_masked=auth_service.mask_phone(phone) if phone else None,
        ip=rl.client_ip(request),
        device=(request.headers.get("user-agent", "")[:200] if request else None) or None,
        reason=reason,
    ))


def _require_verified_customer(user: User) -> str:
    """ผูกได้เฉพาะลูกค้าที่พิสูจน์เบอร์แล้ว — คืนเบอร์ที่พิสูจน์แล้ว"""
    if user.role != "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="บัญชีพนักงานไม่ต้องผูกเลขสมาชิก")
    if not user.phone or not user.phone_verified_at:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ต้องยืนยันเบอร์โทรด้วย OTP ก่อนจึงจะผูกเลขสมาชิกได้")
    return user.phone


def _lookup(key: str):
    """ถามทะเบียนสมาชิก — ระบบปลายทางล่มถือว่า "ยังตอบไม่ได้" ไม่ใช่ "ไม่มีสมาชิก" """
    try:
        return get_sap_client().get_customer(key)
    except SapError as e:
        log.warning("ถามทะเบียนสมาชิกไม่ได้ (%s): %s", key, e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ระบบสมาชิกตอบไม่ได้ตอนนี้ — ลองใหม่อีกครั้ง") from e


def _taken_by_other(db: Session, sap_customer_no: str, user: User) -> bool:
    owner = db.scalar(select(User).where(User.sap_customer_no == sap_customer_no))
    return bool(owner and owner.id != user.id)


def _card(c, matched_phone: bool) -> dict:
    """ข้อมูลสมาชิกที่ยอมให้ฝั่งหน้าเว็บเห็น — ปิดบังเบอร์/อีเมลเสมอ

    ตอนนี้ผู้ขอ *ยังไม่ได้* พิสูจน์ว่าเป็นเจ้าของรายนี้ ถ้าคืนข้อมูลเต็มไปก่อน หน้าจอนี้จะ
    กลายเป็นเครื่องมือค้นข้อมูลส่วนบุคคลจากเลขสมาชิกไปเลย (ชื่อยังต้องโชว์ให้พอยืนยันว่าใช่ตัวเอง)
    """
    email = c.email or ""
    return {
        "sap_customer_no": c.sap_customer_no,
        "name": c.name,
        "points": c.points,
        "phone_masked": auth_service.mask_phone(c.phone or ""),
        "email_masked": (email[0] + "***" + email[email.index("@"):]) if "@" in email else None,
        # True = เบอร์ตรงกับที่ยืนยันไว้แล้ว กดผูกได้เลย · False = ต้องยืนยัน OTP ที่เบอร์ในทะเบียนก่อน
        "can_link_now": matched_phone,
    }


def candidates(db: Session, user: User, request: Request | None = None) -> list[dict]:
    """หาสมาชิกที่น่าจะเป็นคนเดียวกับผู้ใช้ — ค้นด้วย "เบอร์ที่ยืนยันแล้ว" เท่านั้น

    ตั้งใจไม่รับคำค้นจากผู้ใช้ เพราะนี่คือจุดที่ล่อให้ทำเป็นช่องค้นหาแล้วกลายเป็นรูรั่ว
    ผู้ใช้ที่มีเลขสมาชิกอยู่แล้วให้ไปทาง start_link() ซึ่งบังคับยืนยัน OTP
    """
    phone = _require_verified_customer(user)
    # ผูกเลขสมาชิกไปแล้วก็ไม่ต้องชวนผูกอีก — ของเดิมยังตอบใบเดิมกลับมา หน้าเว็บเลยขึ้นการ์ด
    # "เจอบัญชีสมาชิกของคุณ · ใช่ ผูกบัญชีนี้" ค้างอยู่ทั้งที่ผูกเรียบร้อยแล้ว
    if user.sap_customer_no:
        return []
    c = _lookup(phone)
    if not c or _taken_by_other(db, c.sap_customer_no, user):
        return []
    return [_card(c, matched_phone=True)]


def start_link(db: Session, user: User, sap_customer_no: str, request: Request | None = None) -> dict:
    """ขั้นแรกของการผูกด้วยเลขสมาชิกที่ผู้ใช้พิมพ์เอง — ตอบว่าต้องยืนยันอะไรต่อ

    ไม่ยืนยันอะไรที่นี่ และไม่บอกว่าเลขนี้มีจริงไหมในรูปแบบที่เอาไปไล่เดาต่อได้ —
    เลขที่ไม่มีจริงกับเลขที่ถูกผูกไปแล้วตอบข้อความเดียวกัน
    """
    phone = _require_verified_customer(user)
    rl.guard(db, "link_member", f"user:{user.id}", rl.LINK_PER_USER, "ลองผูกบ่อยเกินไป — ลองใหม่ในอีก 1 ชั่วโมง")
    no = (sap_customer_no or "").strip()
    c = _lookup(no)
    if not c or c.sap_customer_no != no or _taken_by_other(db, no, user):
        rl.record(db, "link_member", f"user:{user.id}", ok=False, request=request)
        audit_service.log(db, user, "member.link_failed", "user", user.id, {"sap_customer_no": no})
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบเลขสมาชิกนี้ หรือถูกผูกกับบัญชีอื่นไปแล้ว")

    if auth_service.normalize_phone(c.phone or "") == phone:
        return {"sap_customer_no": no, "requires_otp": False, "member": _card(c, matched_phone=True)}
    if not c.phone:
        # ไม่มีเบอร์ในทะเบียน = พิสูจน์ทางออนไลน์ไม่ได้ ต้องให้พนักงานยืนยันตัวตนที่สาขา
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="สมาชิกรายนี้ไม่มีเบอร์โทรในระบบ — ติดต่อพนักงานที่สาขาเพื่อผูกบัญชี")
    return {"sap_customer_no": no, "requires_otp": True, "member": _card(c, matched_phone=False)}


def send_link_otp(db: Session, user: User, sap_customer_no: str, request: Request | None = None) -> dict:
    """ส่ง OTP ไปที่เบอร์ "ในทะเบียนสมาชิก" (ไม่ใช่เบอร์ที่ผู้ขอพิมพ์มา) — หัวใจของ step-up"""
    _require_verified_customer(user)
    rl.guard(db, "link_member", f"user:{user.id}", rl.LINK_PER_USER, "ลองผูกบ่อยเกินไป — ลองใหม่ในอีก 1 ชั่วโมง")
    no = (sap_customer_no or "").strip()
    c = _lookup(no)
    if not c or c.sap_customer_no != no or not c.phone or _taken_by_other(db, no, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบเลขสมาชิกนี้ หรือถูกผูกกับบัญชีอื่นไปแล้ว")
    # target ล็อกไว้ว่ารหัสใบนี้ใช้ผูกเลขนี้เท่านั้น — เอาไปใช้กับเลขสมาชิกใบอื่นไม่ได้
    out = auth_service.issue_otp(db, c.phone, purpose="link_member", target=no, request=request)
    audit_service.log(db, user, "member.link_otp_sent", "user", user.id, {"sap_customer_no": no})
    db.commit()
    return out


def link(db: Session, user: User, sap_customer_no: str, otp_code: str | None, request: Request | None = None) -> dict:
    """ผูกจริง — ผ่านได้สองทางเท่านั้นตามที่เขียนไว้หัวไฟล์"""
    phone = _require_verified_customer(user)
    rl.guard(db, "link_member", f"user:{user.id}", rl.LINK_PER_USER, "ลองผูกบ่อยเกินไป — ลองใหม่ในอีก 1 ชั่วโมง")
    no = (sap_customer_no or "").strip()
    c = _lookup(no)
    if not c or c.sap_customer_no != no or _taken_by_other(db, no, user):
        rl.record(db, "link_member", f"user:{user.id}", ok=False, request=request)
        _record(db, user, "denied", no, phone=phone, request=request,
                reason="ไม่พบเลขสมาชิก หรือถูกผูกกับบัญชีอื่นไปแล้ว")
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบเลขสมาชิกนี้ หรือถูกผูกกับบัญชีอื่นไปแล้ว")

    member_phone = auth_service.normalize_phone(c.phone or "")
    if member_phone != phone:
        if not member_phone:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="สมาชิกรายนี้ไม่มีเบอร์โทรในระบบ — ติดต่อพนักงานที่สาขาเพื่อผูกบัญชี")
        if not otp_code:
            _record(db, user, "denied", no, phone=phone, request=request,
                    reason="เบอร์ไม่ตรงทะเบียน ต้องยืนยัน OTP ที่เบอร์ในทะเบียนก่อน")
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ต้องยืนยัน OTP ที่เบอร์ของสมาชิกรายนี้ก่อน")
        # ตรวจกับ "เบอร์ในทะเบียน" + target ต้องตรงเลขสมาชิกใบนี้ ใบอื่นใช้ข้ามกันไม่ได้
        auth_service.consume_otp(db, member_phone, otp_code, purpose="link_member", target=no, request=request)

    user.sap_customer_no = no
    user.points = c.points or 0
    # ผูกแล้ว = ทะเบียนสมาชิกเป็นเจ้าของชื่อ จึงทับด้วยชื่อจากทะเบียนเสมอ แม้ลูกค้าจะเคยพิมพ์เอง
    # เพราะหลังผูกแล้วหน้าเว็บล็อกไม่ให้แก้ชื่อ (ชื่อไปโผล่บนใบเสนอราคา/ใบกำกับภาษีที่ออกจาก SAP)
    # ถ้าเก็บชื่อที่ลูกค้าพิมพ์ไว้จะได้สภาพที่ขัดกันเอง: ล็อกชื่อในนามความถูกต้องของเอกสาร
    # ทั้งที่เอกสารจริงพิมพ์อีกชื่อ · อยากใช้ชื่อเล่นได้เฉพาะตอนยังไม่ผูก
    if c.name:
        user.name = c.name
    # ตั้งใจ "ไม่" ก๊อปอีเมลจากทะเบียนมาใส่ users.email — คอลัมน์นั้นคืออีเมลสำหรับล็อกอิน
    # ซึ่งลูกค้าต้องเป็นคนเลือกเอง · และมันชนกับบัญชีเงาที่ระบบสร้างให้ลูกค้า SAP ตอนเซลล์
    # ผูกลูกค้าเข้าตะกร้า (ใช้อีเมลเดียวกัน คอลัมน์เป็น unique → IntegrityError)
    # อีเมลสำหรับส่งใบเสร็จมาจาก customer_snapshot ของใบเสนอราคาอยู่แล้ว ไม่ต้องซ้ำที่นี่
    # ที่อยู่ทะเบียนสมาชิกเก็บแยกช่องของมันเอง — ลูกค้าแก้ที่อยู่จัดส่งแล้วต้องไม่ทับอันนี้
    if c.address:
        user.sap_address, user.sap_postcode = c.address, c.postcode
    if not user.default_address and c.address:
        user.default_address, user.default_postcode = c.address, c.postcode
    rl.record(db, "link_member", f"user:{user.id}", ok=True, request=request)
    via = "phone_match" if member_phone == phone else "otp"
    audit_service.log(db, user, "member.linked", "user", user.id, {"sap_customer_no": no, "via": via})
    _record(db, user, "linked", no, via=via, phone=member_phone or phone, request=request)
    db.commit()
    return {"sap_customer_no": no, "name": c.name, "points": user.points, "linked_at": utcnow().isoformat()}


def unlink(db: Session, user: User, request: Request | None = None) -> None:
    """ถอดการผูกด้วยตัวเอง — แต้มกลับเป็น 0 เพราะแต้มเป็นของสมาชิก ไม่ใช่ของบัญชีเว็บ"""
    if not user.sap_customer_no:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="บัญชีนี้ยังไม่ได้ผูกเลขสมาชิก")
    audit_service.log(db, user, "member.unlinked", "user", user.id, {"sap_customer_no": user.sap_customer_no})
    _record(db, user, "unlinked", user.sap_customer_no, phone=user.phone, request=request)
    user.sap_customer_no = None
    user.points = 0
    db.commit()
