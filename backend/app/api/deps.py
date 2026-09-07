from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def get_current_user_optional(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    token = _bearer(authorization)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    return db.get(User, payload["sub"])


def get_current_user(user: User | None = Depends(get_current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ต้องเข้าสู่ระบบก่อน")
    return user


def require_role(*roles: str) -> Callable[..., User]:
    """ใช้ป้องกัน endpoint ตาม role - บังคับที่ backend ไม่ใช่แค่ซ่อน UI"""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="สิทธิ์ไม่พอ (ต้องเป็น " + ", ".join(roles) + ")")
        return user

    return _dep
