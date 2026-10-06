"""ของเพิ่มฝั่งพนักงานขาย: หมายเหตุหลักของตะกร้า · พนักงานร่วมบิล Z1-ZK · template ใบเสนอราคา

แยกจาก cart_service / quotation_service เพื่อไม่ไปแตะตรรกะเดิมที่ทำงานอยู่แล้ว
ทุกอย่างในนี้อ่านตัวตนพนักงานผ่าน CurrentEmployee — วันที่ Employee Login API มา ไม่ต้องแก้ไฟล์นี้
"""
from __future__ import annotations

import calendar
from datetime import date

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permissions as P
from app.core.config import get_settings
from app.models.cart import STAFF_ROLES, Cart, CartStaff
from app.models.common import utcnow
from app.models.quotation import QuotationTemplate
from app.services import audit_service
from app.services.employee_provider import CurrentEmployee, get_employee_provider
from app.services.photo_service import UPLOAD_ROOT, _store, url_of

REMARK_MAX = 1000


# ---------- หมายเหตุหลักของตะกร้า ----------
def set_overall_remark(db: Session, emp: CurrentEmployee, cart: Cart, text: str | None) -> Cart:
    v = (text or "").strip()
    if len(v) > REMARK_MAX:
        raise HTTPException(status_code=422, detail=f"หมายเหตุยาวเกิน {REMARK_MAX} ตัวอักษร")
    cart.overall_remark = v or None
    audit_service.log(db, None, "cart.overall_remark", "cart", cart.id, {"by": emp.employee_code, "len": len(v)}, role=emp.role)
    db.commit()
    return cart


# ---------- พนักงานร่วมบิล ----------
def list_staff(db: Session, cart_id: str) -> list[CartStaff]:
    rows = db.scalars(select(CartStaff).where(CartStaff.cart_id == cart_id)).all()
    order = list(STAFF_ROLES)
    return sorted(rows, key=lambda r: order.index(r.role_code) if r.role_code in order else 99)


def set_staff(db: Session, emp: CurrentEmployee, cart: Cart, role_code: str, user_id: str | None) -> list[CartStaff]:
    """ใส่/เปลี่ยน/ถอด พนักงานของบทบาทหนึ่ง — บทบาทละหนึ่งคน

    รับแค่ user_id แล้วไปเปิดทะเบียนพนักงานเอาชื่อกับรหัสมาเอง ไม่รับชื่อ/รหัสจากหน้าเว็บ
    ไม่งั้นใครก็พิมพ์ชื่อคนอื่นลงบิลได้ ซึ่งมีผลกับค่าคอมมิชชั่น
    """
    if not emp.can(P.CART_STAFF_ASSIGN):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์กำหนดพนักงานร่วมบิล")
    if role_code not in STAFF_ROLES:
        raise HTTPException(status_code=422, detail=f"ไม่รู้จักบทบาท {role_code} (ใช้ได้: {', '.join(STAFF_ROLES)})")

    row = db.scalar(select(CartStaff).where(CartStaff.cart_id == cart.id, CartStaff.role_code == role_code))
    if user_id is None:
        if row:
            db.delete(row)
            audit_service.log(db, None, "cart.staff_remove", "cart", cart.id,
                              {"role": role_code, "employee": row.employee_code, "by": emp.employee_code}, role=emp.role)
        db.commit()
        return list_staff(db, cart.id)

    ref = get_employee_provider().get(db, user_id)
    if not ref:
        raise HTTPException(status_code=404, detail="ไม่พบพนักงานคนนี้ในทะเบียน")
    if row is None:
        row = CartStaff(cart_id=cart.id, role_code=role_code)
        db.add(row)
    row.user_id, row.employee_code, row.employee_name = ref.user_id, ref.employee_code, ref.employee_name
    row.assigned_by, row.assigned_at = emp.employee_code, utcnow()
    audit_service.log(db, None, "cart.staff_set", "cart", cart.id,
                      {"role": role_code, "employee": ref.employee_code, "by": emp.employee_code}, role=emp.role)
    db.commit()
    return list_staff(db, cart.id)


def staff_snapshot(db: Session, cart_id: str) -> list[dict] | None:
    rows = list_staff(db, cart_id)
    if not rows:
        return None
    return [{"role_code": r.role_code, "role_name": STAFF_ROLES.get(r.role_code, r.role_code),
             "employee_code": r.employee_code, "employee_name": r.employee_name} for r in rows]


# ---------- วันที่ท้ายบิล ----------
def month_end(d: date) -> date:
    """วันสุดท้ายของเดือน — วันที่ในเงื่อนไขท้ายบิล (ไม่ใช่วันหมดอายุของใบ)
    06/10/2026 -> 31/10/2026 · 15/11/2026 -> 30/11/2026 · ปีอธิกสุรทิน ก.พ. -> 29"""
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


# ---------- template ส่วนตัวของ DS ----------
def get_template(db: Session, emp: CurrentEmployee) -> QuotationTemplate | None:
    return db.scalar(select(QuotationTemplate).where(QuotationTemplate.user_id == emp.user_id))


def save_template(db: Session, emp: CurrentEmployee, data: dict) -> QuotationTemplate:
    """แก้ได้เฉพาะ template ของตัวเอง — ผูกกับ user_id ของคนที่ล็อกอิน ไม่รับ id จากหน้าเว็บ"""
    if not emp.can(P.QUOTATION_TEMPLATE_OWN):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ใช้ template ใบเสนอราคา")
    t = get_template(db, emp)
    if t is None:
        t = QuotationTemplate(user_id=emp.user_id, employee_code=emp.employee_code)
        db.add(t)
    for k in ("display_name", "phone", "bank_accounts", "footer_terms", "standard_remark"):
        if k in data:
            v = (data[k] or "").strip()
            setattr(t, k, v or None)
    t.employee_code, t.updated_at = emp.employee_code, utcnow()
    db.commit()
    db.refresh(t)
    return t


async def save_logo(db: Session, emp: CurrentEmployee, file: UploadFile) -> QuotationTemplate:
    if not emp.can(P.QUOTATION_TEMPLATE_OWN):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ใช้ template ใบเสนอราคา")
    path, _, _ = _store(await file.read())     # ผ่านด่านเดียวกับรูปสินค้า: ตรวจไฟล์จริง ล้าง EXIF
    t = get_template(db, emp) or QuotationTemplate(user_id=emp.user_id, employee_code=emp.employee_code)
    if t.id is None:
        db.add(t)
    t.logo_path, t.updated_at = path, utcnow()
    db.commit()
    db.refresh(t)
    return t


def template_snapshot(db: Session, emp: CurrentEmployee | None, issued: date) -> dict:
    """ค่าที่จะพิมพ์บนใบ ณ วันออกใบ — template ของคนออกใบ ทับค่ากลางของบริษัท

    ช่องไหนใน template ว่าง ใช้ค่ากลาง ไม่ใช่พิมพ์ช่องว่างลงใบ
    คัดลอกเก็บไว้กับใบ (template_snapshot) เพราะ DS แก้ template ทีหลังได้ แต่ใบที่ส่งลูกค้า
    ไปแล้วต้องเหมือนเดิมทุกตัวอักษร
    """
    s = get_settings()
    t = get_template(db, emp) if emp else None
    return {
        "employee_code": emp.employee_code if emp else None,
        "employee_name": (t.display_name if t and t.display_name else (emp.employee_name if emp else None)),
        "phone": t.phone if t else None,
        "branch_code": emp.branch_code if emp else None,
        "branch_name": emp.branch_name if emp else None,
        "logo_path": t.logo_path if t else None,
        "bank_accounts": t.bank_accounts if t else None,
        "footer_terms": t.footer_terms if t else None,      # ว่าง = ใช้เงื่อนไขกลาง
        "standard_remark": t.standard_remark if t else None,
        "month_end": month_end(issued).isoformat(),
        "company_name_th": s.company_name_th,
        "company_address_th": s.company_address_th,
        "company_tax_id": s.company_tax_id,
    }


def logo_url(path: str | None) -> str | None:
    return url_of(path) if path else None


def logo_file(path: str | None):
    """ที่อยู่ไฟล์จริงของโลโก้ — ใช้ฝังลง Excel"""
    if not path:
        return None
    f = UPLOAD_ROOT / path
    return f if f.is_file() else None

