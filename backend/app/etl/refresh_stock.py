"""เติมจำนวนของจาก SAP ลง availability_cache ให้สินค้าที่ลูกค้าเห็นบนเว็บ

    .venv\\Scripts\\python.exe -m app.etl.refresh_stock            # เฉพาะตัวที่หมดอายุ/ยังไม่เคยเช็ค
    .venv\\Scripts\\python.exe -m app.etl.refresh_stock --all      # บังคับเช็คใหม่ทุกตัว
    .venv\\Scripts\\python.exe -m app.etl.refresh_stock --limit 100

ตั้งให้รันทุก 1 ชม. (Task Scheduler / cron) — สินค้าที่ลูกค้าเห็นมี ~3,600 ตัว ชุดละ 20
เท่ากับ ~180 ครั้งต่อรอบ เฉลี่ยราว 3 ครั้ง/นาที ซึ่งเป็นภาระคงที่ ไม่ผูกกับจำนวนคนเข้าเว็บ

หน้าเว็บอ่านจากตารางนี้อย่างเดียว ไม่เคยยิง SAP เอง — ตอนขายจริงถึงจะยิงสดทั้งตะกร้า
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.etl.progress import Progress
from app.models.catalog import Material
from app.services import product_stock_service

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description="เติมจำนวนของจาก SAP ลง availability_cache")
    ap.add_argument("--all", action="store_true", help="เช็คใหม่ทุกตัว ไม่สนว่ายังไม่หมดอายุ")
    ap.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนรหัสต่อรอบ")
    ap.add_argument("--mock", action="store_true", help="ใส่ตัวเลขปลอมแทนการยิง SAP (ใช้ตอน SAP ต่อไม่ได้)")
    args = ap.parse_args()

    with SessionLocal() as db:
        public = list(db.scalars(select(Material.matnr).where(Material.is_public.is_(True)).order_by(Material.matnr)))
        todo = public if args.all else product_stock_service.stale_matnrs(db, public)
        if args.limit:
            todo = todo[: args.limit]
        if not todo:
            print(f"สินค้าบนเว็บ {len(public):,} ตัว — ข้อมูลยังไม่หมดอายุทั้งหมด ไม่ต้องทำอะไร")
            return 0

        print(f"สินค้าบนเว็บ {len(public):,} ตัว · ต้องเช็ค {len(todo):,} ตัว"
              + (" (โหมด mock — ไม่ได้ยิง SAP จริง)" if args.mock else "")
              + f" · ยิงทีละ {get_settings().stock_batch_size} รหัส")
        # ไม่มีตัวบอกความคืบหน้าแล้วคนรันนึกว่าค้าง (รอบเต็มเงียบ ~15 นาที) แล้วกด Ctrl+C ทิ้ง
        bar = Progress(len(todo), "เช็คไปแล้ว ")
        done = (product_stock_service.refresh_mock(db, todo, bar.step) if args.mock
                else product_stock_service.refresh(db, todo, on_batch=bar.step))
        bar.close()
        print(f"เสร็จ: อัปเดต {done:,}/{len(todo):,} ตัว")
        if done < len(todo):
            print(f"  ({len(todo) - done:,} ตัวไม่สำเร็จ — SAP ไม่รู้จักรหัส หรือยิงไม่ผ่าน ดู log)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
