from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User


def log(db: Session, actor: User | None, action: str, target_type: str, target_id: str | None, payload: dict | None = None, role: str | None = None) -> AuditLog:
    """เขียน audit_logs (ไม่ commit เอง — ให้ service ที่เรียกเป็นคน commit ในธุรกรรมเดียวกัน)"""
    row = AuditLog(actor_user_id=actor.id if actor else None, role=role or (actor.role if actor else "guest"), action=action, target_type=target_type, target_id=target_id, payload=payload or {})
    db.add(row)
    return row
