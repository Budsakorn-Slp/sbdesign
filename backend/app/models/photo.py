"""รูปถ่ายสินค้าตัวโชว์รายสาขา — พนักงานถ่ายของจริงที่ตั้งอยู่ในสาขาตัวเอง

ทำไมแยกจาก material_images: นั่นคือรูปโฆษณาจาก Magento (รูปเดียวกันทุกสาขา) ส่วนนี่คือ
"ตัวนี้ที่สาขานี้หน้าตาเป็นแบบนี้" ของตัวโชว์มีรอย สีซีด ชิ้นส่วนหายได้ต่างกันไปแต่ละสาขา
ลูกค้าต้องเห็นของจริงก่อนตัดสินใจซื้อของ "ขายตามสภาพ"
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow, uuid_pk


class ProductPhoto(Base):
    __tablename__ = "product_photos"
    __table_args__ = (
        # คำถามหลัก: "รูปของรหัสนี้ที่สาขานี้" เรียงตามลำดับที่ถ่าย
        Index("ix_product_photos_matnr_branch", "matnr", "branch_code", "is_deleted"),
    )

    id: Mapped[str] = uuid_pk()
    matnr: Mapped[str] = mapped_column(String(18), nullable=False)
    # สาขามาจากบัญชีพนักงานที่อัปโหลดเท่านั้น ไม่เคยรับจากหน้าเว็บ
    branch_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # เจ้าของรูป — แยกจากคนที่ลงมือแก้/ลบ (ผู้จัดการแก้รูปของเซลล์ได้ แต่เจ้าของยังเป็นเซลล์)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_employee_code: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_employee_name: Mapped[str] = mapped_column(String(120), nullable=False)
    file_path: Mapped[str] = mapped_column(String(300), nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_employee: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_by_employee: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ลบแบบ soft — รูปหายจากหน้าจอแต่แถวยังอยู่ ตอบได้เสมอว่าใครลบเมื่อไร
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_by_employee: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProductPhotoAudit(Base):
    """ประวัติทุกการจัดการรูป — ใคร ทำอะไร รูปไหน รูปของใคร MATNR ไหน สาขาไหน เมื่อไร

    ไม่มี FK ไปที่ product_photos โดยตั้งใจ: ต่อให้วันหนึ่งมีคนลบแถวรูปจริงออกจากฐาน
    ประวัติก็ต้องไม่หายตาม (cascade) · คัดลอกค่าที่ต้องใช้มาเก็บไว้เองทั้งหมด
    """

    __tablename__ = "product_photo_audit"

    id: Mapped[str] = uuid_pk()
    image_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    matnr: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    branch_code: Mapped[str] = mapped_column(String(16), nullable=False)
    image_owner_employee: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)          # CREATE | UPDATE | DELETE
    action_by_employee: Mapped[str] = mapped_column(String(32), nullable=False)
    action_by_role: Mapped[str] = mapped_column(String(16), nullable=False)
    action_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    old_image_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    new_image_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
