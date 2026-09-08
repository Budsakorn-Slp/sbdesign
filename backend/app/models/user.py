from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, utcnow, uuid_pk

ROLES = ("customer", "sales", "manager", "admin")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = uuid_pk()
    role: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # customer|sales|manager|admin
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    sap_customer_no: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    staff_code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    branch_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)  # Gold / Silver / ...
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_postcode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # PDPA — ความยินยอมการตลาด (ค่าเริ่มต้น "ไม่ยินยอม") + วันที่ลบตัวตนตามคำขอ
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_marketing_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def is_staff(self) -> bool:
        return self.role in ("sales", "manager", "admin")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class OtpCode(Base):
    """OTP mock — ของจริงต้องต่อ SMS gateway"""

    __tablename__ = "otp_codes"

    id: Mapped[str] = uuid_pk()
    phone: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
