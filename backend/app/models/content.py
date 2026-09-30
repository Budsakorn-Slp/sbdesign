"""Group B: content ของหน้าแรก mirror มาจาก Magento CMS (ผ่าน sb_home_media บนฐานเว็บ)"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow


class HomeMedia(Base):
    """ภาพหน้าแรก 1 ใบ = 1 แถว — แบนเนอร์, การ์ดหมวด, การ์ดคอลเลกชัน อยู่ตารางเดียวกัน

    section/slug เป็นคีย์เดียวกับ sb_home_media ฝั่งฐานเว็บ import ทับได้เรื่อยๆ
    href คือลิงก์ในแอปเรา (คนละอันกับ source_href ที่ชี้ไป sbdesignsquare.com)
    """

    __tablename__ = "home_media"

    section: Mapped[str] = mapped_column(String(30), primary_key=True)  # hero | top_category | inspiration | inspire_tab
    slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # บล็อก FIND YOUR INSPIRATION แบ่งเป็นแท็บ — แถวไหนอยู่แท็บไหนเก็บไว้ตรงนี้
    # (section อื่นเป็น None) ตาราง sb_home_media ฝั่งฐานเว็บไม่มีสองคอลัมน์นี้ section
    # inspire_tab เลยลงเฉพาะฐานแอป ไม่ผ่าน mirror
    group_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    group_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    image_mb_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_href: Mapped[str | None] = mapped_column(String(500), nullable=True)
    href: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class InfoPage(Base):
    """หน้าเนื้อหาคงที่ (วิธีสั่งซื้อ/การรับประกัน/นโยบาย ฯลฯ) ที่ยกมาจาก CMS ของเว็บจริง

    เก็บเป็น HTML ที่ล้างแล้วจาก Magento (ดู etl/sync_cms_pages.py) ไม่ได้เขียนใหม่เอง
    เพราะเป็นข้อความเชิงนโยบาย/กฎหมาย ที่ต้องตรงกับที่บริษัทประกาศไว้จริงคำต่อคำ
    """

    __tablename__ = "info_pages"

    slug: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
