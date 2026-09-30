from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AddressIn, AddressOut, LoginIn, MemberCardOut, MemberLinkIn, MemberLinkStartOut, MemberLinkedOut, MemberLookupIn,
    OtpRequestIn, OtpVerifyIn, PasswordForgotIn, PasswordResetIn, ProfileIn, RefreshIn, RegisterIn, TokenPair, UserOut,
)
from app.services import address_service, auth_service, member_service

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenPair, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    return auth_service.register(db, body.phone, body.password, body.name, body.email, request)


@router.post("/auth/login", response_model=TokenPair)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    return auth_service.login(db, body.identifier, body.password, body.account_type, request)


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    return auth_service.refresh(db, body.refresh_token, request)


@router.post("/auth/logout", status_code=204)
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    auth_service.logout(db, body.refresh_token)
    return None


@router.post("/auth/otp/request")
def otp_request(body: OtpRequestIn, request: Request, db: Session = Depends(get_db)):
    """ขอ OTP — ตอบเหมือนกันทุกเบอร์ ไม่บอกว่าเบอร์นี้มีบัญชีอยู่แล้วหรือยัง"""
    return auth_service.otp_request(db, body.phone, request)


@router.post("/auth/otp/verify", response_model=TokenPair)
def otp_verify(body: OtpVerifyIn, request: Request, db: Session = Depends(get_db)):
    return auth_service.otp_verify(db, body.phone, body.code, body.name, request)


@router.post("/auth/password/forgot")
def password_forgot(body: PasswordForgotIn, request: Request, db: Session = Depends(get_db)):
    """ขอรหัสตั้งรหัสผ่านใหม่ — ตอบเหมือนกันทุกเบอร์ ไม่บอกว่าเบอร์นี้มีบัญชีไหม"""
    return auth_service.password_forgot(db, body.phone, request)


@router.post("/auth/password/reset", response_model=TokenPair)
def password_reset(body: PasswordResetIn, request: Request, db: Session = Depends(get_db)):
    """ยืนยัน OTP + ตั้งรหัสใหม่ · อุปกรณ์อื่นที่ค้างอยู่จะถูกตัดออกทั้งหมด"""
    return auth_service.password_reset(db, body.phone, body.code, body.new_password, request)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ตั้งค่าบัญชีของตัวเอง — ชื่อ / อีเมล / รหัสผ่าน

    จำเป็นเพราะเบอร์ที่เข้าระบบด้วย OTP ครั้งแรกจะได้ชื่อชั่วคราว "ลูกค้า 4600" ไปก่อน
    (ตอนล็อกอินเรายังไม่รู้ว่าเป็นคนใหม่หรือเก่า จึงไม่ควรถามชื่อทุกคน) — ค่อยมาถามตอนที่
    รู้แล้วว่าเขาไม่มีบัตรสมาชิกให้ดึงชื่อมาใช้

    รหัสผ่านตั้งได้เฉพาะตอนที่ยังไม่เคยตั้ง — การ "เปลี่ยน" รหัสที่มีอยู่แล้วต้องไปทาง
    ลืมรหัสผ่าน (ยืนยัน OTP) เสมอ ไม่งั้นใครที่ยืม session ไปได้จะยึดบัญชีด้วยการตั้งรหัสทับ
    """
    if body.name is not None:
        name = body.name.strip()
        # ผูกบัตรสมาชิกแล้ว = SAP เป็นเจ้าของชื่อ แก้บนเว็บจะไม่ตรงกับเอกสารขาย/ใบกำกับภาษี
        # ที่ออกจาก SAP อยู่ดี · ล็อกที่นี่ด้วย ไม่ใช่แค่ซ่อนช่องกรอกในหน้าเว็บ
        if user.sap_customer_no and name != user.name:
            raise HTTPException(status_code=409, detail="ชื่อมาจากบัตรสมาชิก — แก้ไขได้ที่สาขาหรือศูนย์บริการลูกค้า")
        user.name = name

    if body.email is not None:
        email = body.email.strip().lower() or None
        if email and email != user.email:
            if "@" not in email or "." not in email.split("@")[-1]:
                raise HTTPException(status_code=422, detail="รูปแบบอีเมลไม่ถูกต้อง")
            # email เป็น unique ใน DB — ดักที่นี่เพื่อให้ได้ข้อความไทย ไม่ใช่ IntegrityError 500
            if db.scalar(select(User).where(User.email == email, User.id != user.id)):
                raise HTTPException(status_code=409, detail="อีเมลนี้ถูกใช้กับบัญชีอื่นแล้ว")
        user.email = email

    if body.password:
        if user.password_hash:
            raise HTTPException(status_code=409, detail="บัญชีนี้มีรหัสผ่านอยู่แล้ว — เปลี่ยนรหัสผ่านผ่านเมนู ลืมรหัสผ่าน")
        user.password_hash = auth_service.hash_password(body.password)

    if body.onboarded and not user.onboarded_at:
        user.onboarded_at = auth_service.utcnow()

    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# ผูกบัญชีเว็บเข้ากับเลขสมาชิก — กฎความปลอดภัยทั้งหมดอยู่ใน member_service
# ลำดับที่ตั้งใจให้หน้าเว็บเรียก:
#   1) GET  /me/member/candidates      ระบบหาให้เองจากเบอร์ที่ยืนยันแล้ว (ทางที่ลูกค้าควรได้ใช้)
#   2) POST /me/member/lookup          กรณีลูกค้ายืนยันว่ามีเลขสมาชิกอยู่แล้ว อยากพิมพ์เอง
#   3) POST /me/member/otp             ส่ง OTP ไปเบอร์ในทะเบียน (เฉพาะเมื่อ requires_otp)
#   4) POST /me/member/link            ผูกจริง
# ---------------------------------------------------------------------------
# ---------- สมุดที่อยู่จัดส่ง ----------
@router.get("/me/addresses", response_model=list[AddressOut])
def list_addresses(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ที่อยู่ทั้งหมดของตัวเอง — ใบที่ตั้งเป็นค่าเริ่มต้นมาก่อนเสมอ"""
    return address_service.list_for(db, user)


@router.post("/me/addresses", response_model=AddressOut, status_code=201)
def create_address(body: AddressIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return address_service.create(db, user, body.model_dump(exclude_unset=True))


@router.patch("/me/addresses/{address_id}", response_model=AddressOut)
def update_address(address_id: str, body: AddressIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return address_service.update(db, user, address_id, body.model_dump(exclude_unset=True))


@router.post("/me/addresses/{address_id}/default", response_model=AddressOut)
def default_address(address_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return address_service.set_default(db, user, address_id)


@router.delete("/me/addresses/{address_id}", status_code=204)
def delete_address(address_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    address_service.remove(db, user, address_id)


@router.get("/me/member/candidates", response_model=list[MemberCardOut])
def member_candidates(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """สมาชิกที่ตรงกับเบอร์ที่ยืนยันแล้วของผู้ใช้ — ว่างเปล่าแปลว่ายังไม่เคยเป็นสมาชิก"""
    return member_service.candidates(db, user, request)


@router.post("/me/member/lookup", response_model=MemberLinkStartOut)
def member_lookup(body: MemberLookupIn, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """เช็คเลขสมาชิกที่ลูกค้าพิมพ์มา แล้วบอกว่าต้องยืนยัน OTP ต่อไหม (ยังไม่ผูกอะไรทั้งสิ้น)"""
    return member_service.start_link(db, user, body.sap_customer_no, request)


@router.post("/me/member/otp")
def member_link_otp(body: MemberLookupIn, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ส่ง OTP ไปที่เบอร์ในทะเบียนสมาชิก — ผู้ขอเห็นได้แค่เบอร์แบบปิดบัง"""
    return member_service.send_link_otp(db, user, body.sap_customer_no, request)


@router.post("/me/member/link", response_model=MemberLinkedOut)
def member_link(body: MemberLinkIn, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return member_service.link(db, user, body.sap_customer_no, body.otp_code, request)


@router.delete("/me/member/link", status_code=204)
def member_unlink(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member_service.unlink(db, user, request)
    return None
