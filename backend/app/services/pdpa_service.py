"""PDPA: ความยินยอม · ขอสำเนาข้อมูล · ขอลบข้อมูล (anonymize)

หลักที่ยึด
- เก็บพฤติกรรม "เพื่อการใช้งาน" (ดูล่าสุด/ตะกร้า) ทำได้โดยไม่ต้องขอ · เก็บ "เพื่อการตลาด" ต้องมี consent
- ถอนความยินยอม = row เก่าที่เก็บไว้เพื่อการตลาดถูกลบตัวตนย้อนหลังทันที
- คำขอลบ: ลบตัวตนออกจากทุกที่ที่ลบได้ · เอกสารการเงินที่ออกไปแล้ว (ใบเสนอราคา/ใบเสร็จ/ออร์เดอร์ใน SAP)
  เก็บต่อตามหน้าที่ทางกฎหมาย แต่ตัดลิงก์กลับมาที่บัญชี
"""
import logging

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.analytics import OrderHistory, RecentlyViewed, SearchQuery, UserEvent, Wishlist
from app.models.audit import AuditLog
from app.models.cart import Cart
from app.models.common import utcnow
from app.models.consent import Consent, DataRequest
from app.models.quotation import Preso, Quotation
from app.models.user import User, UserSession
from app.services import audit_service

log = logging.getLogger("sb.pdpa")
ANON_NAME = "ผู้ใช้ที่ขอลบข้อมูล"


# ---------- consent ----------
def marketing_allowed(user: User | None) -> bool:
    return bool(user and user.consent_marketing and not user.anonymized_at)


def set_marketing_consent(db: Session, user: User, granted: bool, source: str = "web", ip: str | None = None) -> Consent:
    row = Consent(user_id=user.id, kind="marketing", granted=granted, source=source, ip=ip)
    db.add(row)
    user.consent_marketing = granted
    user.consent_marketing_at = utcnow()
    if not granted:
        # ถอนความยินยอม → ข้อมูลที่เก็บไว้เพื่อการตลาดต้องระบุตัวไม่ได้อีก
        db.execute(update(UserEvent).where(UserEvent.user_id == user.id, UserEvent.purpose == "marketing").values(user_id=None, anon_token=None))
    audit_service.log(db, user, "pdpa.consent", "user", user.id, {"kind": "marketing", "granted": granted, "source": source})
    db.commit()
    return row


def consent_history(db: Session, user: User) -> list[Consent]:
    return list(db.scalars(select(Consent).where(Consent.user_id == user.id).order_by(Consent.created_at.desc())).all())


# ---------- ขอสำเนาข้อมูล ----------
def export_data(db: Session, user: User, actor: User | None = None) -> dict:
    from app.services import analytics_service  # หลีกเลี่ยง circular import

    orders = analytics_service.list_orders(db, user, refresh=False)
    data = {
        "exported_at": utcnow().isoformat(),
        "profile": {
            "id": user.id, "name": user.name, "phone": user.phone, "email": user.email, "role": user.role, "tier": user.tier,
            "sap_customer_no": user.sap_customer_no, "default_address": user.default_address, "default_postcode": user.default_postcode,
            "created_at": user.created_at.isoformat() if user.created_at else None, "anonymized_at": user.anonymized_at.isoformat() if user.anonymized_at else None,
        },
        "consents": [{"kind": c.kind, "granted": c.granted, "source": c.source, "at": c.created_at.isoformat()} for c in consent_history(db, user)],
        "recently_viewed": [{"matnr": r.matnr, "views": r.views, "at": r.viewed_at.isoformat()} for r in db.scalars(select(RecentlyViewed).where(RecentlyViewed.user_id == user.id)).all()],
        "wishlist": [w.matnr for w in db.scalars(select(Wishlist).where(Wishlist.user_id == user.id)).all()],
        "searches": [{"q": s.q, "at": s.created_at.isoformat()} for s in db.scalars(select(SearchQuery).where(SearchQuery.user_id == user.id)).all()],
        "events": [{"event": e.event, "matnr": e.matnr, "purpose": e.purpose, "at": e.created_at.isoformat()} for e in db.scalars(select(UserEvent).where(UserEvent.user_id == user.id).order_by(UserEvent.created_at.desc()).limit(500)).all()],
        "orders": [{"so_no": o.so_no, "date": o.order_date.isoformat(), "status": o.status, "grand_total": str(o.grand_total), "lines": [{"matnr": l.matnr, "name": l.name, "qty": l.qty} for l in o.lines]} for o in orders],
        "quotations": [{"quotation_no": q.quotation_no, "status": q.status, "grand_total": str(q.grand_total)} for q in db.scalars(select(Quotation).where(Quotation.customer_user_id == user.id)).all()],
    }
    db.add(DataRequest(user_id=user.id, kind="export", status="done", requested_by_user_id=(actor or user).id, done_at=utcnow(), result={"counts": {k: len(v) for k, v in data.items() if isinstance(v, list)}}))
    audit_service.log(db, actor or user, "pdpa.export", "user", user.id, {"by": (actor or user).id})
    db.commit()
    return data


# ---------- ขอลบข้อมูล ----------
def anonymize_user(db: Session, user: User, actor: User | None = None, note: str | None = None) -> dict:
    if user.anonymized_at:
        raise HTTPException(status_code=400, detail="บัญชีนี้ถูกลบข้อมูลไปแล้ว")
    if user.is_staff:
        raise HTTPException(status_code=400, detail="บัญชีพนักงานลบผ่านช่องทางนี้ไม่ได้ — ต้องให้ HR/แอดมินปิดบัญชี")
    open_q = db.scalar(select(func.count()).select_from(Quotation).where(Quotation.customer_user_id == user.id, Quotation.status.in_(("issued", "paid"))))
    if open_q:
        raise HTTPException(status_code=409, detail=f"ยังมีใบเสนอราคา/ออร์เดอร์ค้างอยู่ {open_q} ใบ — ต้องปิดงานก่อนจึงลบข้อมูลได้")

    now = utcnow()
    counts: dict[str, int] = {}

    # 1) ลบสิ่งที่เป็นความชอบส่วนตัวทิ้งทั้งแถว
    counts["wishlists"] = db.execute(delete(Wishlist).where(Wishlist.user_id == user.id)).rowcount or 0
    counts["recently_viewed"] = db.execute(delete(RecentlyViewed).where(RecentlyViewed.user_id == user.id)).rowcount or 0

    # 2) พฤติกรรม/คำค้น: เก็บไว้เป็นสถิติรวมได้ แต่ต้องระบุตัวบุคคลไม่ได้
    counts["user_events"] = db.execute(update(UserEvent).where(UserEvent.user_id == user.id).values(user_id=None, anon_token=None)).rowcount or 0
    counts["search_queries"] = db.execute(update(SearchQuery).where(SearchQuery.user_id == user.id).values(user_id=None, anon_token=None)).rowcount or 0

    # 3) ตะกร้าที่ยังเปิด/ใบร่าง: ไม่มีเหตุต้องเก็บ
    counts["carts"] = db.execute(update(Cart).where(Cart.customer_user_id == user.id, Cart.status == "open").values(status="closed", customer_user_id=None)).rowcount or 0
    counts["presos"] = db.execute(update(Preso).where(Preso.customer_user_id == user.id).values(customer_user_id=None, snapshot_json={})).rowcount or 0

    # 4) เอกสารการเงิน: เก็บตัวเอกสารตามหน้าที่ทางกฎหมาย แต่ตัดลิงก์กลับมาที่บัญชี
    #    (ใบที่ยกเลิกแล้วไม่มีเหตุต้องเก็บชื่อ/ที่อยู่ → ล้างทิ้ง)
    counts["quotations"] = db.execute(update(Quotation).where(Quotation.customer_user_id == user.id).values(customer_user_id=None)).rowcount or 0
    db.execute(update(Quotation).where(Quotation.customer_user_id.is_(None), Quotation.status == "cancelled").values(customer_snapshot={}, ship_address=None))
    counts["order_history"] = db.execute(update(OrderHistory).where(OrderHistory.customer_user_id == user.id).values(customer_user_id=None)).rowcount or 0

    # 5) audit: เก็บ row ไว้ (ต้องตรวจย้อนหลังได้) แต่ตัดว่าเป็นใคร
    counts["audit_logs"] = db.execute(update(AuditLog).where(AuditLog.actor_user_id == user.id).values(actor_user_id=None)).rowcount or 0

    # 6) โปรไฟล์ + ตัดการเข้าใช้งานทันที
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=now))
    user.name, user.phone, user.email = ANON_NAME, None, None
    user.password_hash = user.sap_customer_no = user.default_address = user.default_postcode = user.tier = None
    user.consent_marketing, user.consent_marketing_at, user.anonymized_at = False, now, now

    db.add(DataRequest(user_id=user.id, kind="delete", status="done", requested_by_user_id=(actor or user).id, note=note, done_at=now, result=counts))
    audit_service.log(db, actor, "pdpa.anonymize", "user", user.id, {"counts": counts, "note": note}, role=(actor.role if actor else "system"))
    db.commit()
    log.info("ลบข้อมูลส่วนบุคคลของ user %s แล้ว: %s", user.id, counts)
    return counts


def list_requests(db: Session, kind: str | None = None, limit: int = 100) -> list[DataRequest]:
    stmt = select(DataRequest).order_by(DataRequest.created_at.desc()).limit(limit)
    if kind:
        stmt = stmt.where(DataRequest.kind == kind)
    return list(db.scalars(stmt).all())


def list_audit(db: Session, action: str | None = None, target_id: str | None = None, limit: int = 100) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    if target_id:
        stmt = stmt.where(AuditLog.target_id == target_id)
    return list(db.scalars(stmt).all())
