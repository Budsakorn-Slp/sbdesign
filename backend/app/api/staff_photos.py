"""รูปถ่ายสินค้าตัวโชว์รายสาขา (ฝั่งพนักงาน)

สิทธิ์ทั้งหมดตรวจใน photo_service — ตรงนี้แค่แปลงคำขอ/คำตอบ
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.photo import ProductPhoto
from app.services import photo_service
from app.services.employee_provider import CurrentEmployee, get_current_employee

router = APIRouter(tags=["staff-photos"])


class PhotoOut(BaseModel):
    id: str
    matnr: str
    branch_code: str
    url: str
    width: int
    height: int
    owner_employee_code: str
    owner_employee_name: str
    created_at: datetime
    updated_at: datetime | None = None
    # หน้าเว็บใช้แค่ซ่อน/โชว์ปุ่ม — หลังบ้านตรวจซ้ำทุกครั้งอยู่ดี
    can_edit: bool
    can_delete: bool
    mine: bool


class PhotoAuditOut(BaseModel):
    image_id: str
    matnr: str
    branch_code: str
    image_owner_employee: str
    action: str
    action_by_employee: str
    action_by_role: str
    action_at: datetime
    old_image_url: str | None = None
    new_image_url: str | None = None


class MeOut(BaseModel):
    employee_code: str
    employee_name: str
    branch_code: str | None
    branch_name: str | None
    role: str
    permissions: list[str]


def _out(p: ProductPhoto, emp: CurrentEmployee) -> PhotoOut:
    return PhotoOut(
        id=p.id, matnr=p.matnr, branch_code=p.branch_code, url=photo_service.url_of(p.file_path),
        width=p.width, height=p.height, owner_employee_code=p.owner_employee_code,
        owner_employee_name=p.owner_employee_name, created_at=p.created_at, updated_at=p.updated_at,
        can_edit=photo_service.can_update(emp, p), can_delete=photo_service.can_delete(emp, p),
        mine=p.owner_user_id == emp.user_id,
    )


@router.get("/staff/me", response_model=MeOut)
def staff_me(emp: CurrentEmployee = Depends(get_current_employee)):
    """พนักงานที่ใช้งานอยู่ + สิทธิ์ — หน้าเว็บใช้ตัดสินว่าจะโชว์เมนูไหน"""
    return MeOut(employee_code=emp.employee_code, employee_name=emp.employee_name,
                 branch_code=emp.branch_code, branch_name=emp.branch_name, role=emp.role,
                 permissions=sorted(emp.permissions))


@router.get("/staff/materials/{matnr}/photos", response_model=list[PhotoOut])
def list_photos(matnr: str, branch: str | None = Query(default=None, description="ใช้ได้เฉพาะคนที่ดูได้ทุกสาขา"),
                db: Session = Depends(get_db), emp: CurrentEmployee = Depends(get_current_employee)):
    return [_out(p, emp) for p in photo_service.list_photos(db, emp, matnr, branch)]


@router.post("/staff/materials/{matnr}/photos", response_model=list[PhotoOut], status_code=status.HTTP_201_CREATED)
async def add_photos(matnr: str, files: list[UploadFile] = File(...),
                     db: Session = Depends(get_db), emp: CurrentEmployee = Depends(get_current_employee)):
    """อัปโหลดได้หลายรูปพร้อมกัน · สาขาไม่รับจากคำขอ ใช้สาขาของบัญชีเสมอ"""
    return [_out(p, emp) for p in await photo_service.add_photos(db, emp, matnr, files)]


@router.put("/staff/photos/{photo_id}", response_model=PhotoOut)
async def replace_photo(photo_id: str, file: UploadFile = File(...),
                        db: Session = Depends(get_db), emp: CurrentEmployee = Depends(get_current_employee)):
    return _out(await photo_service.replace_photo(db, emp, photo_id, file), emp)


@router.delete("/staff/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(photo_id: str, db: Session = Depends(get_db), emp: CurrentEmployee = Depends(get_current_employee)):
    photo_service.delete_photo(db, emp, photo_id)


@router.get("/staff/photos/audit", response_model=list[PhotoAuditOut])
def photo_audit(matnr: str | None = None, db: Session = Depends(get_db),
                emp: CurrentEmployee = Depends(get_current_employee)):
    return [
        PhotoAuditOut(
            image_id=a.image_id, matnr=a.matnr, branch_code=a.branch_code,
            image_owner_employee=a.image_owner_employee, action=a.action,
            action_by_employee=a.action_by_employee, action_by_role=a.action_by_role, action_at=a.action_at,
            old_image_url=photo_service.url_of(a.old_image_path) if a.old_image_path else None,
            new_image_url=photo_service.url_of(a.new_image_path) if a.new_image_path else None,
        )
        for a in photo_service.audit_log(db, emp, matnr)
    ]
