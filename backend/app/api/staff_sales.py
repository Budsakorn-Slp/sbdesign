"""เครื่องมือพนักงานขาย: พนักงานร่วมบิล Z1-ZK · หมายเหตุหลักของตะกร้า · template ใบเสนอราคา · export

สิทธิ์ตรวจใน sales_extras_service (ตาม permission) และ sales_service.require_my_cart (ตะกร้าของใคร)
ตรงนี้แค่แปลงคำขอ/คำตอบ
"""
from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.cart import cart_out
from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.models.cart import STAFF_ROLES
from app.models.quotation import QuotationTemplate
from app.models.user import User
from app.schemas.cart import CartOut
from app.services import audit_service, quotation_export, quotation_service, sales_extras_service, sales_service
from app.services.employee_provider import CurrentEmployee, get_current_employee, get_employee_provider

router = APIRouter(tags=["staff-sales"])


# ---------- schemas ----------
class EmployeeOut(BaseModel):
    user_id: str
    employee_code: str
    employee_name: str
    branch_code: str | None = None
    label: str          # "รหัส – ชื่อ" ใช้เป็นข้อความใน dropdown ตรงๆ


class RoleOut(BaseModel):
    code: str
    name: str


class StaffSetIn(BaseModel):
    role_code: str = Field(min_length=2, max_length=4)
    user_id: str | None = None      # เลือกจากรายชื่อ
    employee_code: str | None = Field(default=None, max_length=32)   # หรือพิมพ์รหัสพนักงาน
    # ทั้งคู่ว่าง = ถอดคนออกจากบทบาทนี้ · ชื่อไม่รับจากหน้าเว็บ — ระบบเปิดทะเบียนหาเองเสมอ


class RemarkIn(BaseModel):
    overall_remark: str | None = Field(default=None, max_length=sales_extras_service.REMARK_MAX)


class TemplateIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    bank_accounts: str | None = Field(default=None, max_length=2000)
    footer_terms: str | None = Field(default=None, max_length=5000)
    standard_remark: str | None = Field(default=None, max_length=2000)


class TemplateOut(BaseModel):
    employee_code: str
    employee_name: str
    branch_code: str | None = None
    branch_name: str | None = None
    display_name: str | None = None
    phone: str | None = None
    logo_url: str | None = None
    bank_accounts: str | None = None
    footer_terms: str | None = None
    standard_remark: str | None = None
    updated_at: datetime | None = None
    month_end_preview: str          # วันท้ายบิลถ้าออกใบวันนี้ — ให้ DS เห็นว่า {month_end} จะกลายเป็นอะไร


def _tpl_out(emp: CurrentEmployee, t: QuotationTemplate | None) -> TemplateOut:
    return TemplateOut(
        employee_code=emp.employee_code, employee_name=emp.employee_name,
        branch_code=emp.branch_code, branch_name=emp.branch_name,
        display_name=t.display_name if t else None, phone=t.phone if t else None,
        logo_url=sales_extras_service.logo_url(t.logo_path) if t else None,
        bank_accounts=t.bank_accounts if t else None, footer_terms=t.footer_terms if t else None,
        standard_remark=t.standard_remark if t else None, updated_at=t.updated_at if t else None,
        month_end_preview=sales_extras_service.month_end(datetime.now().date()).strftime("%d/%m/%Y"),
    )


# ---------- ทะเบียนพนักงาน / บทบาท ----------
@router.get("/staff/employees", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db), emp: CurrentEmployee = Depends(get_current_employee)):
    """รายชื่อสำหรับ dropdown "รหัส – ชื่อ" — วันที่ต่อ Employee API จะมาจากที่นั่นแทน"""
    return [EmployeeOut(user_id=r.user_id, employee_code=r.employee_code, employee_name=r.employee_name,
                        branch_code=r.branch_code, label=r.label)
            for r in get_employee_provider().list_employees(db)]


@router.get("/staff/roles", response_model=list[RoleOut])
def list_roles(emp: CurrentEmployee = Depends(get_current_employee)):
    return [RoleOut(code=k, name=v) for k, v in STAFF_ROLES.items()]


# ---------- ตะกร้า ----------
def _my_cart(db: Session, emp: CurrentEmployee, cart_id: str):
    user = db.get(User, emp.user_id)
    return sales_service.require_my_cart(db, user, cart_id)


@router.put("/sales/carts/{cart_id}/staff", response_model=CartOut)
def set_cart_staff(cart_id: str, body: StaffSetIn, db: Session = Depends(get_db),
                   emp: CurrentEmployee = Depends(get_current_employee)):
    cart = _my_cart(db, emp, cart_id)
    sales_extras_service.set_staff(db, emp, cart, body.role_code, body.user_id, body.employee_code)
    return cart_out(cart, db)


@router.put("/sales/carts/{cart_id}/remark", response_model=CartOut)
def set_cart_remark(cart_id: str, body: RemarkIn, db: Session = Depends(get_db),
                    emp: CurrentEmployee = Depends(get_current_employee)):
    cart = _my_cart(db, emp, cart_id)
    sales_extras_service.set_overall_remark(db, emp, cart, body.overall_remark)
    return cart_out(cart, db)


# ---------- template ----------
@router.get("/staff/quotation-template", response_model=TemplateOut)
def get_template(db: Session = Depends(get_db), emp: CurrentEmployee = Depends(get_current_employee)):
    """ของตัวเองเท่านั้น — ไม่มี endpoint ให้ระบุ id ของคนอื่น"""
    return _tpl_out(emp, sales_extras_service.get_template(db, emp))


@router.put("/staff/quotation-template", response_model=TemplateOut)
def save_template(body: TemplateIn, db: Session = Depends(get_db), emp: CurrentEmployee = Depends(get_current_employee)):
    return _tpl_out(emp, sales_extras_service.save_template(db, emp, body.model_dump(exclude_unset=True)))


@router.post("/staff/quotation-template/logo", response_model=TemplateOut)
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db),
                      emp: CurrentEmployee = Depends(get_current_employee)):
    return _tpl_out(emp, await sales_extras_service.save_logo(db, emp, file))


# ---------- export ----------
@router.get("/quotations/{no}/export")
def export_quotation(no: str, format: str = Query(default="xlsx", pattern="^(xlsx|csv)$"),
                     t: str | None = Query(default=None), bom: bool = Query(default=True),
                     db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    """ใช้สิทธิ์ชุดเดียวกับหน้าเอกสาร — ใครเปิดใบได้ export ได้"""
    q = quotation_service.get_quotation(db, no)
    quotation_service.check_access(q, user, t)
    if format == "csv":
        body, mime = quotation_export.csv_bytes(q, bom), "text/csv; charset=utf-8"
    else:
        body, mime = quotation_export.xlsx_bytes(q), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(body, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{q.quotation_no}.{format}"'})



class SheetOut(BaseModel):
    url: str


@router.post("/quotations/{no}/google-sheet", response_model=SheetOut)
def to_google_sheet(no: str, db: Session = Depends(get_db), emp: CurrentEmployee = Depends(get_current_employee)):
    """สร้าง Google Sheet ของใบนี้ใน Shared Drive ของบริษัท แล้วแชร์สิทธิ์แก้ไขให้คนที่กด

    ยังไม่ได้ตั้ง service account → 501 · หน้าเว็บจะใช้ทางสำรอง (สูตร IMPORTDATA) แทน
    """
    from app.integrations.google import sheets

    user = db.get(User, emp.user_id)
    q = quotation_service.get_quotation(db, no)
    quotation_service.check_access(q, user, None)
    try:
        url = sheets.create_sheet(f"{q.quotation_no} · {(q.customer_snapshot or {}).get('name') or ''}".strip(" ·"),
                                  quotation_export.flat_rows(q), user.email if user else None)
    except sheets.SheetsNotConfigured:
        raise HTTPException(status_code=501, detail="ยังไม่ได้ตั้งค่า Google service account")
    except (sheets.SheetsError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=str(e) or "ติดต่อ Google ไม่สำเร็จ")
    audit_service.log(db, user, "quotation.google_sheet", "quotation", q.quotation_no, {"url": url})
    db.commit()
    return SheetOut(url=url)
