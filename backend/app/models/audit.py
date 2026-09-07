from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow, uuid_pk


class AuditLog(Base):
    """PDPA + ตรวจย้อนหลัง: ใครทำอะไรกับอะไร"""

    __tablename__ = "audit_logs"

    id: Mapped[str] = uuid_pk()
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # guest | customer | sales | manager | admin | system
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # cart.item_add · customer.view · discount.apply
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)  # cart | preso | quotation | user
    target_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
