"""สิทธิ์เจ้าของข้อมูล (PDPA) + ดู audit log

- ลูกค้าจัดการความยินยอม/ขอสำเนา/ขอลบข้อมูลของตัวเองได้
- แอดมินทำแทนได้ (เช่นลูกค้าโทรเข้ามา) และดู audit log ได้
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.pdpa import AuditOut, ConsentIn, DataRequestOut, DeleteIn, PrivacyOut
from app.services import pdpa_service

router = APIRouter(tags=["pdpa"])
admin_only = require_role("admin")


def _privacy(db: Session, user: User) -> PrivacyOut:
    return PrivacyOut(consent_marketing=user.consent_marketing, consent_marketing_at=user.consent_marketing_at, anonymized_at=user.anonymized_at, history=pdpa_service.consent_history(db, user))


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/me/privacy", response_model=PrivacyOut)
def my_privacy(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _privacy(db, user)


@router.post("/me/consents", response_model=PrivacyOut)
def set_consents(body: ConsentIn, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pdpa_service.set_marketing_consent(db, user, body.marketing, source="web", ip=_client_ip(request))
    return _privacy(db, user)


@router.get("/me/data/export")
def export_my_data(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """สำเนาข้อมูลทั้งหมดที่ระบบเก็บของบัญชีนี้ (JSON)"""
    return pdpa_service.export_data(db, user)


@router.post("/me/data/delete")
def delete_my_data(body: DeleteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="ต้องยืนยัน (confirm=true) — การลบข้อมูลย้อนกลับไม่ได้")
    return {"ok": True, "removed": pdpa_service.anonymize_user(db, user, actor=user, note=body.note)}


@router.post("/admin/users/{user_id}/anonymize")
def admin_anonymize(user_id: str, body: DeleteIn, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้")
    return {"ok": True, "removed": pdpa_service.anonymize_user(db, target, actor=admin, note=body.note)}


@router.get("/admin/users/{user_id}/data-export")
def admin_export(user_id: str, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้")
    return pdpa_service.export_data(db, target, actor=admin)


@router.get("/admin/data-requests", response_model=list[DataRequestOut])
def list_data_requests(kind: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return pdpa_service.list_requests(db, kind, limit)


@router.get("/admin/audit-logs", response_model=list[AuditOut])
def list_audit_logs(action: str | None = Query(default=None), target_id: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return pdpa_service.list_audit(db, action, target_id, limit)
