"""พนักงานที่กำลังใช้งาน — จุดเดียวที่โค้ดธุรกิจถาม "ใคร สาขาไหน มีสิทธิ์อะไร"

TODO: Replace MockCurrentUser with Employee Login API

ตอนนี้ยังไม่มี Employee Login API จริง จึงใช้ "บัญชีพนักงานในฐานเรา" (SA-104, MG-001 ...)
เป็นตัวจำลอง · ไม่ได้ฝังผู้ใช้ปลอมคนเดียวตายตัว เพราะงานนี้ต้องทดสอบเรื่อง "รูปของฉัน vs
รูปของคนอื่น" ซึ่งต้องมีพนักงานอย่างน้อยสองคนล็อกอินสลับกันได้จริง

วันที่ API จริงมา: เขียน provider ตัวใหม่ที่คืน CurrentEmployee หน้าตาเดิม แล้วเปลี่ยนที่
get_employee_provider() ที่เดียว · โค้ดรูปสินค้า/ใบเสนอราคา/ตะกร้า ไม่ต้องแก้สักบรรทัด
เพราะไม่มีใครอ่าน User ตรงๆ — ทุกที่อ่านผ่าน CurrentEmployee

สาขาของพนักงานมาจากตรงนี้เท่านั้น ห้ามรับจากหน้าเว็บ (หน้าเว็บส่งอะไรมาก็ไม่สนใจ)
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.permissions import permissions_for_role
from app.models.user import User


@dataclass(frozen=True)
class CurrentEmployee:
    user_id: str
    employee_code: str
    employee_name: str
    branch_code: str | None
    branch_name: str | None
    role: str
    permissions: frozenset[str]

    def can(self, permission: str) -> bool:
        return permission in self.permissions


@dataclass(frozen=True)
class EmployeeRef:
    """พนักงานในรายการให้เลือก (dropdown ผู้ร่วมบิล)"""

    user_id: str
    employee_code: str
    employee_name: str
    branch_code: str | None

    @property
    def label(self) -> str:
        return f"{self.employee_code} – {self.employee_name}"


class EmployeeProvider(Protocol):
    def from_user(self, user: User) -> CurrentEmployee: ...
    def list_employees(self, db: Session) -> list[EmployeeRef]: ...
    def get(self, db: Session, user_id: str) -> EmployeeRef | None: ...
    def get_by_code(self, db: Session, employee_code: str) -> EmployeeRef | None: ...


class LocalAccountEmployeeProvider:
    """ตัวจำลองระหว่างรอ Employee Login API — อ่านจากบัญชีพนักงานในฐานเรา

    TODO: Replace MockCurrentUser with Employee Login API
    """

    def from_user(self, user: User) -> CurrentEmployee:
        return CurrentEmployee(
            user_id=user.id,
            employee_code=user.staff_code or user.id,
            employee_name=user.name,
            branch_code=user.branch_id,
            branch_name=user.branch_name,
            role=user.role,
            permissions=permissions_for_role(user.role),
        )

    def list_employees(self, db: Session) -> list[EmployeeRef]:
        rows = db.scalars(
            select(User).where(User.role.in_(("sales", "manager")), User.staff_code.is_not(None))  # แอดมินระบบไม่ใช่คนขาย
            .order_by(User.staff_code)
        ).all()
        return [self._ref(u) for u in rows]

    def get(self, db: Session, user_id: str) -> EmployeeRef | None:
        u = db.get(User, user_id)
        if not u or u.role not in ("sales", "manager") or not u.staff_code:
            return None
        return self._ref(u)

    def get_by_code(self, db: Session, employee_code: str) -> EmployeeRef | None:
        """หาจากรหัสพนักงานที่เซลล์พิมพ์ — ไม่สนตัวพิมพ์เล็ก/ใหญ่ และช่องว่างหัวท้าย"""
        code = (employee_code or "").strip().upper()
        if not code:
            return None
        u = db.scalar(select(User).where(func.upper(User.staff_code) == code))
        return self.get(db, u.id) if u else None

    @staticmethod
    def _ref(u: User) -> EmployeeRef:
        return EmployeeRef(user_id=u.id, employee_code=u.staff_code or u.id, employee_name=u.name, branch_code=u.branch_id)


@lru_cache
def get_employee_provider() -> EmployeeProvider:
    # TODO: Replace MockCurrentUser with Employee Login API — เปลี่ยนตรงนี้ที่เดียว
    return LocalAccountEmployeeProvider()


def get_current_employee(user: User = Depends(get_current_user)) -> CurrentEmployee:
    """dependency สำหรับ endpoint ฝั่งพนักงาน — ลูกค้าเข้าไม่ได้

    ชื่อไม่ใช่ get_current_user เพราะชื่อนั้นมีอยู่แล้วและถูกใช้ทั้งระบบ (คืน User)
    เปลี่ยนความหมายของมันจะกระทบทุก endpoint ที่มีอยู่
    """
    if not user.is_staff:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="เฉพาะพนักงาน")
    return get_employee_provider().from_user(user)
