r"""ยกเลิกใบเสนอราคาที่ไม่ได้ชำระเงินภายในเวลาที่กำหนด

    .venv\Scripts\python.exe -m app.etl.expire_payments

ต้องรันตามรอบ (ทุก 15-30 นาที) ไม่ใช่รอให้มีคนเปิดหน้าเว็บ — คนที่ไม่จ่ายก็คือคนที่
ไม่กลับมาเปิดอีก ใบจะค้างเป็น "รอชำระ" ตลอดกาล และคิวจัดส่งที่กันไว้ก็กินที่ของคนอื่น

อายุรายการตั้งที่ PAYMENT_EXPIRE_HOURS (ค่าตั้งต้น 24 ชั่วโมง)
"""
from __future__ import annotations

import sys

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services import payment_service

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    with SessionLocal() as db:
        n = payment_service.sweep_expired(db)
    print(f"ยกเลิกรายการที่เลย {get_settings().payment_expire_hours} ชั่วโมงแล้ว {n} รายการ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
