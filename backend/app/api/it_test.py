"""โหมดทดสอบของทีม IT — บัญชีในรายชื่อ IT_TEST_STAFF_CODES สลับ role/สาขาของตัวเองได้

ทำไมมี: ทีม IT ต้องลองระบบในมุมของทุกตำแหน่งทุกสาขา (เซลล์ / ผู้จัดการ / แอดมิน)
เดิมต้องให้คนที่เข้าเครื่องเซิร์ฟเวอร์รันคำสั่งให้ทุกครั้ง

กันไว้สามชั้น:
  - แก้ได้เฉพาะบัญชีตัวเอง (ไม่มีช่องให้ระบุบัญชีอื่น)
  - เฉพาะรหัสพนักงานที่อยู่ในรายชื่อ — ตั้งรายชื่อเป็นค่าว่างแล้วทั้งความสามารถนี้ปิด
  - เปลี่ยนเป็นลูกค้าไม่ได้ (ล็อกอินพนักงานจะเข้าไม่ได้อีก กลับมาแก้ไม่ได้)
ทุกครั้งที่เปลี่ยนเขียน audit log
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.catalog import Plant
from app.models.common import utcnow
from app.models.user import User
from app.services import audit_service

router = APIRouter(tags=["it-test"])

ROLES = {"sales": "พนักงานขาย (SA)", "manager": "ผู้จัดการ", "admin": "แอดมิน"}


def _codes() -> set[str]:
    return {c.strip().upper() for c in get_settings().it_test_staff_codes.split(",") if c.strip()}


def _require_it(user: User) -> None:
    if not user.staff_code or user.staff_code.upper() not in _codes():
        raise HTTPException(status_code=403, detail="เฉพาะบัญชีทดสอบของทีม IT")


class BranchOpt(BaseModel):
    code: str
    name: str


class TestProfileOut(BaseModel):
    staff_code: str
    name: str
    role: str
    branch_code: str | None
    branch_name: str | None
    roles: dict[str, str]
    branches: list[BranchOpt]


class TestProfileIn(BaseModel):
    role: str | None = Field(default=None, pattern="^(sales|manager|admin)$")
    branch_code: str | None = Field(default=None, max_length=16)


def _out(db: Session, u: User) -> TestProfileOut:
    plants = db.scalars(select(Plant).where(Plant.type == "store").order_by(Plant.name)).all()
    return TestProfileOut(staff_code=u.staff_code or "", name=u.name, role=u.role, branch_code=u.branch_id,
                          branch_name=u.branch_name, roles=ROLES,
                          branches=[BranchOpt(code=p.plant_code, name=p.name) for p in plants])


@router.get("/it-test/profile", response_model=TestProfileOut)
def get_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_it(user)
    return _out(db, user)


@router.put("/it-test/profile", response_model=TestProfileOut)
def set_profile(body: TestProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_it(user)
    before = {"role": user.role, "branch": user.branch_id}
    if body.role:
        user.role = body.role
    if body.branch_code:
        plant = db.get(Plant, body.branch_code)
        if not plant:
            raise HTTPException(status_code=404, detail=f"ไม่พบสาขา {body.branch_code}")
        user.branch_id, user.branch_name = plant.plant_code, plant.name
    user.updated_at = utcnow()
    audit_service.log(db, user, "it_test.profile_change", "user", user.id,
                      {"before": before, "after": {"role": user.role, "branch": user.branch_id}})
    db.commit()
    db.refresh(user)
    return _out(db, user)
