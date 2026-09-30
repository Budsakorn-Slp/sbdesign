import logging
import secrets
from datetime import timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, hash_token, new_refresh_token, verify_password
from app.integrations.sms import SmsError, get_sms_client
from app.models.common import utcnow
from app.models.user import OtpCode, User, UserSession
from app.schemas.auth import TokenPair, UserOut
from app.services import audit_service
from app.services import rate_limit as rl

log = logging.getLogger("sb.auth")

# hooks ที่ step ถัดไปมาเสียบ (เช่น merge guest cart ตอน login)
_login_hooks: list = []


def register_login_hook(fn) -> None:
    _login_hooks.append(fn)


def normalize_phone(p: str) -> str:
    return "".join(ch for ch in p if ch.isdigit())


def issue_tokens(db: Session, user: User, request: Request | None) -> TokenPair:
    s = get_settings()
    refresh = new_refresh_token()
    sess = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh),
        device=(request.headers.get("user-agent", "")[:200] if request else None),
        ip=(request.client.host if request and request.client else None),
        expires_at=utcnow() + timedelta(days=s.refresh_token_days),
    )
    db.add(sess)
    db.commit()
    return TokenPair(access_token=create_access_token(user.id, user.role), refresh_token=refresh, user=UserOut.model_validate(user))


def find_customer_by_identifier(db: Session, identifier: str) -> User | None:
    ident = identifier.strip()
    digits = normalize_phone(ident)
    conds = [User.email == ident.lower(), User.sap_customer_no == ident]
    if digits:
        conds.append(User.phone == digits)
    return db.scalar(select(User).where(User.role == "customer", or_(*conds)))


def _run_hooks(db: Session, user: User, request: Request | None) -> None:
    for hook in _login_hooks:
        hook(db, user, request)


# hash ของรหัสผ่านที่ไม่มีวันตรงกับอะไร — เอาไว้ให้ bcrypt ทำงานครบรอบตอนไม่เจอบัญชี
# ถ้าข้ามไปเลย เวลาตอบกลับจะสั้นกว่าเคสที่เจอบัญชีอย่างเห็นได้ชัด คนนอกจะจับได้ว่าบัญชีไหนมีจริง
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))

# ข้อความเดียวใช้ทุกกรณีที่ล็อกอินไม่ผ่าน — ห้ามแยกว่า "ไม่มีบัญชีนี้" กับ "รหัสผ่านผิด"
_LOGIN_FAIL = "บัญชีหรือรหัสผ่านไม่ถูกต้อง"


def login(db: Session, identifier: str, password: str, account_type: str, request: Request | None) -> TokenPair:
    """ล็อกอินด้วยรหัสผ่าน — ผิดซ้ำเกินเพดานจะโดนหยุดชั่วคราวทั้งรายบัญชีและราย IP"""
    ident = identifier.strip()
    acct_key = f"{account_type}:{ident.upper() if account_type == 'staff' else normalize_phone(ident) or ident.lower()}"
    ip = rl.client_ip(request)
    rl.guard(db, "login", acct_key, rl.LOGIN_PER_ACCOUNT, "ลองผิดหลายครั้งเกินไป — รอสักครู่แล้วลองใหม่")
    if ip:
        rl.guard(db, "login", f"ip:{ip}", rl.LOGIN_PER_IP, "ลองผิดหลายครั้งเกินไป — รอสักครู่แล้วลองใหม่")

    if account_type == "staff":
        user = db.scalar(select(User).where(User.staff_code == ident.upper(), User.role.in_(("sales", "manager", "admin"))))
    else:
        user = find_customer_by_identifier(db, ident)
    ok = verify_password(password, user.password_hash) if user else verify_password(password, _DUMMY_HASH)

    if not user or not ok:
        rl.record(db, "login", acct_key, ok=False, request=request)
        if ip:
            rl.record(db, "login", f"ip:{ip}", ok=False, request=request)
        # เก็บ audit เฉพาะความพยายามเข้าบัญชีพนักงาน — ของลูกค้ามีเยอะและนัยด้านความปลอดภัยต่ำกว่า
        if account_type == "staff":
            audit_service.log(db, None, "auth.login_failed", "user", None, {"identifier": ident.upper(), "ip": ip}, role="guest")
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_LOGIN_FAIL)

    rl.record(db, "login", acct_key, ok=True, request=request)
    if user.is_staff:
        audit_service.log(db, user, "auth.login", "user", user.id, {"ip": ip, "staff_code": user.staff_code})
    _run_hooks(db, user, request)
    return issue_tokens(db, user, request)


def register(db: Session, phone: str, password: str, name: str, email: str | None, request: Request | None) -> TokenPair:
    digits = normalize_phone(phone)
    if db.scalar(select(User).where(User.phone == digits)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="เบอร์นี้สมัครแล้ว")
    if email and db.scalar(select(User).where(User.email == email.lower())):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="อีเมลนี้สมัครแล้ว")
    # สมัครทางนี้กรอกชื่อ+รหัสผ่านมาครบแล้ว ไม่ต้องพาไปหน้าตั้งค่าบัญชีซ้ำ
    user = User(role="customer", name=name, phone=digits, email=(email.lower() if email else None),
                password_hash=hash_password(password), is_guest=False, onboarded_at=utcnow())
    db.add(user)
    db.commit()
    _run_hooks(db, user, request)
    return issue_tokens(db, user, request)


def refresh(db: Session, refresh_token: str, request: Request | None) -> TokenPair:
    sess = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == hash_token(refresh_token)))
    if not sess or sess.revoked_at or sess.expires_at < utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token ใช้ไม่ได้")
    sess.revoked_at = utcnow()  # rotate: ใบเก่าใช้ซ้ำไม่ได้
    user = db.get(User, sess.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ไม่พบผู้ใช้")
    return issue_tokens(db, user, request)


def logout(db: Session, refresh_token: str) -> None:
    sess = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == hash_token(refresh_token)))
    if sess and not sess.revoked_at:
        sess.revoked_at = utcnow()
        db.commit()


def mask_phone(digits: str) -> str:
    """โชว์เบอร์แบบปิดบัง — ใช้ทุกที่ที่ต้องบอกว่า "ส่งไปเบอร์ไหน" โดยไม่เปิดเผยเบอร์เต็ม"""
    d = normalize_phone(digits or "")
    return f"{d[:3]}-xxx-{d[-4:]}" if len(d) >= 7 else "xxx"


def issue_otp(db: Session, phone: str, purpose: str = "login", target: str | None = None, request: Request | None = None) -> dict:
    """สร้างและส่ง OTP หนึ่งใบ — ใช้ร่วมกันทั้งตอนล็อกอินและตอนยืนยันการผูกเลขสมาชิก

    ใบเก่าของเบอร์นี้ที่ purpose เดียวกันถูกยกเลิกทิ้งทุกครั้ง ให้มีรหัสที่ใช้ได้ใบเดียว ณ เวลาหนึ่ง
    (ปล่อยให้มีหลายใบพร้อมกัน = โอกาสเดาถูกเพิ่มขึ้นตามจำนวนใบที่ยังไม่หมดอายุ)
    """
    digits = normalize_phone(phone)
    ip = rl.client_ip(request)
    rl.guard_cooldown(db, "otp_send", f"phone:{digits}", rl.OTP_RESEND_COOLDOWN_SECONDS, "เพิ่งส่งไปเมื่อสักครู่ — รอ 1 นาทีแล้วกดใหม่")
    rl.guard(db, "otp_send", f"phone:{digits}", rl.OTP_SEND_PER_PHONE, "ขอรหัสบ่อยเกินไป — ลองใหม่ในอีก 1 ชั่วโมง")
    if ip:
        rl.guard(db, "otp_send", f"ip:{ip}", rl.OTP_SEND_PER_IP, "ขอรหัสบ่อยเกินไป — ลองใหม่ในอีก 1 ชั่วโมง")

    db.query(OtpCode).filter(OtpCode.phone == digits, OtpCode.purpose == purpose, OtpCode.used.is_(False)).update(
        {"used": True}, synchronize_session=False
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(OtpCode(phone=digits, code_hash=hash_token(code), purpose=purpose, target=target, expires_at=utcnow() + timedelta(minutes=5)))
    # ฝั่งส่งนับทุกครั้งที่ส่งจริง (ไม่ใช่นับเฉพาะที่ล้มเหลว) เพราะเพดานคือจำนวน SMS ที่ยิงออกไป
    rl.record(db, "otp_send", f"phone:{digits}", ok=True, request=request)
    if ip:
        rl.record(db, "otp_send", f"ip:{ip}", ok=True, request=request)
    db.commit()
    # ส่งผ่าน SMS client (mock = พิมพ์ออก console · http = ยิงผู้ให้บริการจริง)
    # ส่งไม่ได้ก็ไม่ล้ม request — รหัสถูกบันทึกไปแล้ว ผู้ใช้กด "ส่งใหม่" ได้ และถ้าเปิด
    # OTP_DEBUG อยู่ก็ยังเห็นรหัสบนจอ · ถ้าล้มทั้ง request ผู้ใช้จะติดอยู่หน้าเดิมโดยไม่มีทางไปต่อ
    try:
        get_sms_client().send(digits, get_settings().sms_otp_template.format(code=code))
    except SmsError:
        log.warning("ส่ง OTP ไม่สำเร็จ (%s) — ผู้ใช้ต้องกดส่งใหม่", mask_phone(digits))
    out = {"sent": True, "phone": mask_phone(digits), "expires_in": 300}
    if get_settings().otp_debug:
        out["debug_code"] = code
    return out


def otp_request(db: Session, phone: str, request: Request | None = None) -> dict:
    return issue_otp(db, phone, purpose="login", request=request)


def consume_otp(db: Session, phone: str, code: str, purpose: str = "login", target: str | None = None, request: Request | None = None) -> OtpCode:
    """ตรวจ OTP แล้วเผาทิ้ง — ใช้ได้ครั้งเดียว · กรอกผิดเกินโควตาใบนั้นตายทันที ต้องขอใหม่"""
    digits = normalize_phone(phone)
    rl.guard(db, "otp_verify", f"phone:{digits}", rl.OTP_VERIFY_PER_PHONE, "กรอกรหัสผิดหลายครั้งเกินไป — ลองใหม่ในอีก 1 ชั่วโมง")
    otp = db.scalar(
        select(OtpCode)
        .where(OtpCode.phone == digits, OtpCode.purpose == purpose, OtpCode.used.is_(False))
        .order_by(OtpCode.created_at.desc())
    )
    bad = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="รหัส OTP ไม่ถูกต้องหรือหมดอายุ")
    if not otp or otp.expires_at < utcnow():
        rl.record(db, "otp_verify", f"phone:{digits}", ok=False, request=request)
        db.commit()
        raise bad
    # เทียบแบบ constant-time — กันจับเวลาเดารหัสทีละหลัก
    if not secrets.compare_digest(otp.code_hash, hash_token(code or "")) or (target is not None and otp.target != target):
        otp.attempts += 1
        if otp.attempts >= rl.OTP_MAX_ATTEMPTS_PER_CODE:
            otp.used = True
        rl.record(db, "otp_verify", f"phone:{digits}", ok=False, request=request)
        db.commit()
        raise bad
    otp.used = True
    rl.record(db, "otp_verify", f"phone:{digits}", ok=True, request=request)
    return otp


def otp_verify(db: Session, phone: str, code: str, name: str | None, request: Request | None) -> TokenPair:
    """ยืนยัน OTP = เข้าสู่ระบบ · เบอร์ที่ยังไม่มีบัญชีจะถูกสร้างให้เลย (สมัครกับล็อกอินทางเดียวกัน)"""
    digits = normalize_phone(phone)
    consume_otp(db, digits, code, purpose="login", request=request)
    user = db.scalar(select(User).where(User.phone == digits))
    if not user:
        user = User(role="customer", name=name or f"ลูกค้า {digits[-4:]}", phone=digits, is_guest=False)
        db.add(user)
    # ผ่าน OTP = พิสูจน์แล้วว่าถือเบอร์นี้จริง ซึ่งเป็นเงื่อนไขตั้งต้นของการผูกเลขสมาชิก
    user.phone_verified_at = utcnow()
    db.commit()
    _run_hooks(db, user, request)
    return issue_tokens(db, user, request)


def password_forgot(db: Session, phone: str, request: Request | None = None) -> dict:
    """ขอรหัสสำหรับตั้งรหัสผ่านใหม่

    ส่ง OTP ให้ทุกเบอร์ที่ขอ ไม่ว่าจะมีบัญชีอยู่จริงหรือไม่ และตอบข้อความเดียวกันเสมอ —
    ถ้าตอบต่างกันจะกลายเป็นเครื่องมือไล่เช็คว่าเบอร์ไหนเป็นลูกค้าของเรา

    ใช้ purpose แยกจาก OTP ตอนล็อกอิน เพื่อไม่ให้รหัสที่ขอไว้เพื่อ "เข้าระบบ" ถูกเอาไป
    "เปลี่ยนรหัสผ่าน" ต่อได้ (คนละเจตนา ควรต้องขอใหม่)
    """
    return issue_otp(db, phone, purpose="reset_password", request=request)


def password_reset(db: Session, phone: str, code: str, new_password: str, request: Request | None = None) -> TokenPair:
    """ยืนยัน OTP แล้วตั้งรหัสผ่านใหม่ — สำเร็จแล้วเข้าสู่ระบบให้เลย ไม่ต้องกรอกซ้ำ"""
    digits = normalize_phone(phone)
    consume_otp(db, digits, code, purpose="reset_password", request=request)
    user = db.scalar(select(User).where(User.phone == digits, User.role == "customer"))
    if not user:
        # ถึงตรงนี้แปลว่าถือ OTP ของเบอร์นี้จริง แต่เบอร์ไม่มีบัญชี — สร้างให้แล้วตั้งรหัสเลย
        user = User(role="customer", name=f"ลูกค้า {digits[-4:]}", phone=digits, is_guest=False)
        db.add(user)
    user.password_hash = hash_password(new_password)
    user.phone_verified_at = utcnow()
    # ตั้งรหัสใหม่ = ตัดอุปกรณ์อื่นที่ค้างอยู่ทั้งหมด เผื่อกรณีโดนคนอื่นเข้าบัญชีไปก่อนหน้า
    revoked = 0
    for sess in db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))):
        sess.revoked_at = utcnow()
        revoked += 1
    audit_service.log(db, user, "auth.password_reset", "user", user.id, {"sessions_revoked": revoked})
    db.commit()
    _run_hooks(db, user, request)
    return issue_tokens(db, user, request)
