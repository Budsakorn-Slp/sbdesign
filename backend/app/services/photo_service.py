"""รูปถ่ายสินค้าตัวโชว์รายสาขา — สิทธิ์ตาม สาขา + เจ้าของ + permission และประวัติทุกครั้ง

กติกา (ตรวจที่หลังบ้านทั้งหมด หน้าเว็บแค่ซ่อน/โชว์ปุ่มตาม can_edit/can_delete):
  ดู      สาขาเดียวกับรูป หรือมี VIEW_ALL_BRANCH
  เพิ่ม    เข้าสาขาของตัวเองเท่านั้น (สาขามาจากบัญชี ไม่รับจากหน้าเว็บ)
  แก้/ลบ  ต้องเห็นรูปนั้นได้ก่อน แล้ว
            รูปของตัวเอง → *_OWN
            รูปของคนอื่น → *_ALL
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permissions as P
from app.models.common import utcnow
from app.models.photo import ProductPhoto, ProductPhotoAudit
from app.services import catalog_service
from app.services.employee_provider import CurrentEmployee

# อยู่ใต้ data/ — ไม่ติดเข้า image และ docker-compose.prod mount เป็น volume ไว้แล้ว
# build ใหม่กี่รอบรูปก็ไม่หาย
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "data" / "uploads"
PHOTO_DIR = UPLOAD_ROOT / "product_photos"
MEDIA_PREFIX = "/media"

MAX_BYTES = 12 * 1024 * 1024      # รูปจากกล้องมือถือรุ่นใหม่ใหญ่ราว 4-8 MB
MAX_SIDE = 2000                   # ย่อเหลือด้านยาว 2000px พอดูรายละเอียดรอย ไม่เปลืองที่
MAX_PER_BRANCH = 30               # ต่อหนึ่งรหัสต่อหนึ่งสาขา — กันกดอัปโหลดรัวจนดิสก์เต็ม
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "MPO"}


# ---------- สิทธิ์ ----------
def can_view(emp: CurrentEmployee, photo_branch: str) -> bool:
    if not emp.can(P.PRODUCT_IMAGE_READ):
        return False
    return emp.can(P.PRODUCT_IMAGE_VIEW_ALL_BRANCH) or (emp.branch_code is not None and emp.branch_code == photo_branch)


def _can_change(emp: CurrentEmployee, photo: ProductPhoto, own_perm: str, all_perm: str) -> bool:
    if not can_view(emp, photo.branch_code):
        return False
    mine = photo.owner_user_id == emp.user_id
    return emp.can(own_perm) if mine else emp.can(all_perm)


def can_update(emp: CurrentEmployee, photo: ProductPhoto) -> bool:
    return _can_change(emp, photo, P.PRODUCT_IMAGE_UPDATE_OWN, P.PRODUCT_IMAGE_UPDATE_ALL)


def can_delete(emp: CurrentEmployee, photo: ProductPhoto) -> bool:
    return _can_change(emp, photo, P.PRODUCT_IMAGE_DELETE_OWN, P.PRODUCT_IMAGE_DELETE_ALL)


# ---------- ไฟล์ ----------
def _store(raw: bytes) -> tuple[str, int, int]:
    """ตรวจว่าเป็นรูปจริง หมุนตามกล้อง ล้าง EXIF แล้วเก็บเป็น JPEG

    ต้องหมุนก่อนล้าง EXIF — มือถือไม่ได้หมุนพิกเซลจริง แค่จดไว้ใน EXIF ว่า "แสดงตะแคง"
    ล้างทิ้งโดยไม่หมุนก่อน รูปจะขึ้นนอนตะแคงทุกใบที่ถ่ายแนวตั้ง

    ล้าง EXIF เพราะมีพิกัด GPS ของสาขา เวลาถ่าย และรุ่นโทรศัพท์ของพนักงานติดมาด้วย
    เข้ารหัสใหม่ทั้งไฟล์ยังกันไฟล์ปลอมนามสกุล (สคริปต์ที่ตั้งชื่อเป็น .jpg) ได้ในตัว
    """
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"รูปใหญ่เกิน {MAX_BYTES // (1024 * 1024)} MB")
    try:
        im = Image.open(io.BytesIO(raw))
        fmt = (im.format or "").upper()
        im.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="ไฟล์นี้ไม่ใช่รูปภาพ")
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=f"ไม่รองรับไฟล์ชนิด {fmt or 'นี้'} — ใช้ JPG / PNG / WEBP")
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"     # ชื่อสุ่ม เดา URL ไม่ได้ และไม่พกชื่อไฟล์เดิมของเครื่องพนักงาน
    im.save(PHOTO_DIR / name, format="JPEG", quality=85, optimize=True)   # ไม่ส่ง exif= คือทิ้ง EXIF
    return f"product_photos/{name}", im.width, im.height


def url_of(path: str) -> str:
    return f"{MEDIA_PREFIX}/{path}"


# ---------- ประวัติ ----------
def _audit(db: Session, emp: CurrentEmployee, photo: ProductPhoto, action: str,
           old_path: str | None, new_path: str | None) -> None:
    db.add(ProductPhotoAudit(
        image_id=photo.id, matnr=photo.matnr, branch_code=photo.branch_code,
        image_owner_employee=photo.owner_employee_code,
        action=action, action_by_employee=emp.employee_code, action_by_role=emp.role,
        old_image_path=old_path, new_image_path=new_path,
    ))


# ---------- งานหลัก ----------
def _require_display(matnr: str) -> None:
    # ทำเฉพาะตัวโชว์ (MATNR 20) — ของทั่วไปใช้รูปโฆษณาชุดเดียวกันทุกสาขาอยู่แล้ว
    if not catalog_service.is_display_item(matnr):
        raise HTTPException(status_code=400, detail="ถ่ายรูปรายสาขาได้เฉพาะสินค้าตัวโชว์ (รหัสขึ้นต้น 20)")


def list_photos(db: Session, emp: CurrentEmployee, matnr: str, branch: str | None = None) -> list[ProductPhoto]:
    """พนักงานทั่วไปเห็นเฉพาะสาขาตัวเอง ไม่ว่าจะขอสาขาอะไรมา
    คนที่มี VIEW_ALL_BRANCH เลือกสาขาได้ ไม่ระบุ = ทุกสาขา"""
    if not emp.can(P.PRODUCT_IMAGE_READ):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ดูรูปสินค้า")
    q = select(ProductPhoto).where(ProductPhoto.matnr == matnr, ProductPhoto.is_deleted.is_(False))
    if emp.can(P.PRODUCT_IMAGE_VIEW_ALL_BRANCH):
        if branch:
            q = q.where(ProductPhoto.branch_code == branch)
    else:
        if not emp.branch_code:
            return []
        q = q.where(ProductPhoto.branch_code == emp.branch_code)
    return list(db.scalars(q.order_by(ProductPhoto.created_at)).all())


async def add_photos(db: Session, emp: CurrentEmployee, matnr: str, files: list[UploadFile]) -> list[ProductPhoto]:
    if not emp.can(P.PRODUCT_IMAGE_CREATE):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เพิ่มรูปสินค้า")
    _require_display(matnr)
    if not emp.branch_code:
        raise HTTPException(status_code=400, detail="บัญชีนี้ยังไม่ได้ผูกสาขา — เพิ่มรูปไม่ได้ (ให้แอดมินตั้งสาขาก่อน)")
    if not files:
        raise HTTPException(status_code=422, detail="ไม่ได้แนบรูปมา")

    have = db.query(ProductPhoto).filter(ProductPhoto.matnr == matnr, ProductPhoto.branch_code == emp.branch_code,
                                         ProductPhoto.is_deleted.is_(False)).count()
    if have + len(files) > MAX_PER_BRANCH:
        raise HTTPException(status_code=400, detail=f"รูปของสาขานี้เต็มแล้ว (สูงสุด {MAX_PER_BRANCH} รูปต่อสินค้า)")

    out: list[ProductPhoto] = []
    for f in files:
        path, w, h = _store(await f.read())
        photo = ProductPhoto(
            matnr=matnr, branch_code=emp.branch_code,       # สาขาจากบัญชีเท่านั้น
            owner_user_id=emp.user_id, owner_employee_code=emp.employee_code, owner_employee_name=emp.employee_name,
            file_path=path, width=w, height=h, created_by_employee=emp.employee_code,
        )
        db.add(photo)
        db.flush()
        _audit(db, emp, photo, "CREATE", None, path)
        out.append(photo)
    db.commit()
    return out


def _get(db: Session, emp: CurrentEmployee, photo_id: str) -> ProductPhoto:
    photo = db.get(ProductPhoto, photo_id)
    # ไม่เจอ กับ เจอแต่ดูไม่ได้ ตอบเหมือนกัน — ไม่บอกใบ้ว่ารูปของสาขาอื่นมีอยู่จริง
    if not photo or photo.is_deleted or not can_view(emp, photo.branch_code):
        raise HTTPException(status_code=404, detail="ไม่พบรูปนี้")
    return photo


async def replace_photo(db: Session, emp: CurrentEmployee, photo_id: str, file: UploadFile) -> ProductPhoto:
    photo = _get(db, emp, photo_id)
    if not can_update(emp, photo):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="แก้ได้เฉพาะรูปของตัวเอง")
    old = photo.file_path
    path, w, h = _store(await file.read())
    photo.file_path, photo.width, photo.height = path, w, h
    photo.updated_by_employee, photo.updated_at = emp.employee_code, utcnow()
    _audit(db, emp, photo, "UPDATE", old, path)
    db.commit()
    # ไฟล์เดิมไม่ลบทิ้ง — ประวัติอ้างถึง old_image_path อยู่ ลบไปแล้วตรวจย้อนหลังดูรูปเก่าไม่ได้
    return photo


def delete_photo(db: Session, emp: CurrentEmployee, photo_id: str) -> None:
    photo = _get(db, emp, photo_id)
    if not can_delete(emp, photo):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ลบได้เฉพาะรูปของตัวเอง")
    photo.is_deleted = True
    photo.deleted_by_employee, photo.deleted_at = emp.employee_code, utcnow()
    _audit(db, emp, photo, "DELETE", photo.file_path, None)
    db.commit()


def set_public(db: Session, emp: CurrentEmployee, photo_id: str, public: bool) -> ProductPhoto:
    """แชร์/เลิกแชร์ให้ลูกค้าเห็น — สิทธิ์เท่ากับการแก้รูป (ของตัวเอง หรือ UPDATE_ALL)"""
    photo = _get(db, emp, photo_id)
    if not can_update(emp, photo):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="แชร์ได้เฉพาะรูปของตัวเอง")
    if photo.is_public != public:
        photo.is_public = public
        photo.shared_by_employee, photo.shared_at = (emp.employee_code, utcnow()) if public else (None, None)
        _audit(db, emp, photo, "SHARE" if public else "UNSHARE", photo.file_path, photo.file_path)
        db.commit()
    return photo


def public_photos(db: Session, matnr: str) -> list[ProductPhoto]:
    """รูปที่แชร์แล้วของทุกสาขา — สำหรับหน้าสินค้าฝั่งลูกค้า (ไม่ต้องล็อกอิน)"""
    if not catalog_service.is_display_item(matnr):
        return []
    q = select(ProductPhoto).where(ProductPhoto.matnr == matnr, ProductPhoto.is_public.is_(True),
                                   ProductPhoto.is_deleted.is_(False))
    return list(db.scalars(q.order_by(ProductPhoto.branch_code, ProductPhoto.created_at)).all())


def audit_log(db: Session, emp: CurrentEmployee, matnr: str | None = None, limit: int = 200) -> list[ProductPhotoAudit]:
    if not emp.can(P.PRODUCT_IMAGE_AUDIT_VIEW):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ดูประวัติรูปสินค้า")
    q = select(ProductPhotoAudit)
    if matnr:
        q = q.where(ProductPhotoAudit.matnr == matnr)
    # ไม่มีสิทธิ์ดูทุกสาขา = เห็นประวัติเฉพาะสาขาตัวเอง
    if not emp.can(P.PRODUCT_IMAGE_VIEW_ALL_BRANCH):
        q = q.where(ProductPhotoAudit.branch_code == (emp.branch_code or ""))
    return list(db.scalars(q.order_by(ProductPhotoAudit.action_at.desc()).limit(limit)).all())
