"""ที่อยู่ไทย: ตำบล/อำเภอ/จังหวัด + รหัสไปรษณีย์ — ยกมาจาก directory_* บน Magento

ทำไมใช้ของ Magento ไม่หาชุดข้อมูลใหม่: เว็บจริงกรอกที่อยู่จากชุดนี้อยู่แล้ว ลูกค้าเก่า
ที่อยู่ในระบบก็สะกดตามชุดนี้ ถ้าเราใช้คนละชุดชื่อตำบลจะไม่ตรงกันเวลาเทียบที่อยู่เดิม

สองเรื่องที่เป็น "กฎธุรกิจ" ไม่ใช่ข้อมูลขาด ยกมาด้วยทั้งคู่:
  · ชุดนี้มี 74 จังหวัด ขาด ยะลา ปัตตานี นราธิวาส — เว็บเดิมตั้งใจไม่ให้เลือก
  · forbidden_postcode 15 รหัส (เกาะ/พื้นที่ที่รถส่งไม่ถึง) → is_blocked
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utcnow


class ThaiGeo(Base):
    """หนึ่งแถว = หนึ่งตำบล · แบนไว้แถวเดียวจบ ไม่แตกสามตารางเพราะอ่านอย่างเดียวล้วน

    รหัสไปรษณีย์เดียวกันมีได้หลายตำบล (922 รหัส ต่อ 7,391 ตำบล) — หน้าเว็บจึงต้อง
    ให้เลือกตำบลต่อหลังกรอกรหัส ไม่ใช่เติมให้อัตโนมัติแล้วจบ
    """

    __tablename__ = "thai_geo"

    subdistrict_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    zipcode: Mapped[str] = mapped_column(String(5), index=True, nullable=False)
    subdistrict_th: Mapped[str] = mapped_column(String(120), nullable=False)  # "แขวงหิรัญรูจี" / "ต.บางพลี"
    subdistrict_en: Mapped[str | None] = mapped_column(String(120), nullable=True)
    district_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    district_th: Mapped[str] = mapped_column(String(120), nullable=False)
    district_en: Mapped[str | None] = mapped_column(String(120), nullable=True)
    province_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)  # region_id ฝั่ง Magento
    province_th: Mapped[str] = mapped_column(String(120), nullable=False)
    province_en: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # เขตค่าส่ง 1/2 คิดจาก prefix ของรหัสไปรษณีย์ตอน ETL — เก็บไว้เลยจะได้โชว์ค่าส่งได้ตั้งแต่ยังไม่รู้ที่อยู่เต็ม
    area_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # forbidden_postcode
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
