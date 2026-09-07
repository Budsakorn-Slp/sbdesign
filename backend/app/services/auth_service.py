import logging
import secrets
from datetime import timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, hash_token, new_refresh_token, verify_password
from app.models.common import utcnow
from app.models.user import OtpCode, User, UserSession
from app.schemas.auth import TokenPair, UserOut

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


def login(db: Session, identifier: str, password: str, account_type: str, request: Request | None) -> TokenPair:
    if account_type == "staff":
        user = db.scalar(select(User).where(User.staff_code == identifier.strip().upper(), User.role.in_(("sales", "manager", "admin"))))
    else:
        user = find_customer_by_identifier(db, identifier)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="บัญชีหรือรหัสผ่านไม่ถูกต้อง")
    _run_hooks(db, user, request)
    return issue_tokens(db, user, request)


def register(db: Session, phone: str, password: str, name: str, email: str | None, request: Request | None) -> TokenPair:
    digits = normalize_phone(phone)
    if db.scalar(select(User).where(User.phone == digits)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="เบอร์นี้สมัครแล้ว")
    if email and db.scalar(select(User).where(User.email == email.lower())):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="อีเมลนี้สมัครแล้ว")
    user = User(role="customer", name=name, phone=digits, email=(email.lower() if email else None), password_hash=hash_password(password), is_guest=False)
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


def otp_request(db: Session, phone: str) -> dict:
    digits = normalize_phone(phone)
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(OtpCode(phone=digits, code=code, expires_at=utcnow() + timedelta(minutes=5)))
    db.commit()
    log.info("[MOCK SMS] OTP %s -> %s", code, digits)  # ของจริงส่งผ่าน SMS gateway
    out = {"sent": True, "phone": digits, "expires_in": 300}
    if get_settings().otp_debug:
        out["debug_code"] = code
    return out


def otp_verify(db: Session, phone: str, code: str, name: str | None, request: Request | None) -> TokenPair:
    digits = normalize_phone(phone)
    otp = db.scalar(
        select(OtpCode).where(OtpCode.phone == digits, OtpCode.code == code, OtpCode.used.is_(False)).order_by(OtpCode.created_at.desc())
    )
    if not otp or otp.expires_at < utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="รหัส OTP ไม่ถูกต้องหรือหมดอายุ")
    otp.used = True
    user = db.scalar(select(User).where(User.phone == digits))
    if not user:
        user = User(role="customer", name=name or f"ลูกค้า {digits[-4:]}", phone=digits, is_guest=False)
        db.add(user)
    db.commit()
    _run_hooks(db, user, request)
    return issue_tokens(db, user, request)
