"""เอารายชื่อสาขาจริงฝั่ง SAP มาลงตาราง plants

    .venv\\Scripts\\python.exe -m app.etl.sync_plants
    .venv\\Scripts\\python.exe -m app.etl.sync_plants --dry-run

ต้นทางคือ product_stock_sites ที่ etl.refresh_stock เขียนไว้ (ฟิลด์ NAME ของ
STOCK_ON_SITES) — ไม่ได้ยิง SAP เอง จึงต้องรัน refresh_stock ก่อนอย่างน้อยหนึ่งรอบ

ทำไมต้องมี: ตาราง plants เดิมมาจาก seed/plants.json ซึ่งเป็นสาขาสมมติ 4 แห่ง
(บางนา/รามอินทรา/เชียงใหม่/คลังบางพลี) ที่เอาไว้ให้หน้าเว็บมีอะไรแสดงตอนยังไม่มีของจริง
ตัวเลือก "เลือกสาขา" บนหัวเว็บอ่านจากตารางนี้ ลูกค้าจึงเห็นสาขาที่ไม่มีอยู่จริง

สาขาสมมติที่ SAP ไม่รู้จักจะถูกลบทิ้ง — ปล่อยไว้ปนกันแล้วไม่มีใครรู้ว่าอันไหนของจริง
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Plant, ProductStockSite
from app.services.product_stock_service import NON_STORE_PLANTS

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def sync(db, dry: bool = False) -> dict:
    rows = db.execute(
        select(ProductStockSite.plant_code, ProductStockSite.name)
        .where(ProductStockSite.name != "").distinct()
    ).all()
    if not rows:
        return {"error": "ไม่มีข้อมูลใน product_stock_sites — รัน etl.refresh_stock ก่อน"}

    # 1000/9000 เป็นระดับบริษัท/โรงงาน เก็บไว้เป็น warehouse จะได้ไม่โผล่ในตัวเลือกของลูกค้า
    # (หน้าเว็บกรอง type == "store") แต่ยังมีชื่อให้ใช้เวลาต้องอ้างถึง
    want = {code: (name, "warehouse" if code in NON_STORE_PLANTS else "store") for code, name in rows}
    have = {p.plant_code: p for p in db.scalars(select(Plant)).all()}

    added, updated = [], []
    for code, (name, kind) in sorted(want.items()):
        row = have.get(code)
        if row is None:
            added.append(code)
            if not dry:
                db.add(Plant(plant_code=code, name=name, type=kind))
        elif (row.name, row.type) != (name, kind):
            updated.append(code)
            if not dry:
                row.name, row.type = name, kind

    # สาขาที่ SAP ไม่รู้จัก = ของสมมติจาก seed ลบทิ้ง
    stale = [c for c in have if c not in want]
    if not dry:
        for c in stale:
            db.delete(have[c])
        db.commit()
    return {"added": added, "updated": updated, "removed": stale, "total": len(want)}


def main() -> int:
    ap = argparse.ArgumentParser(description="ซิงค์รายชื่อสาขาจาก SAP ลงตาราง plants")
    ap.add_argument("--dry-run", action="store_true", help="ดูว่าจะเปลี่ยนอะไร ไม่เขียนจริง")
    args = ap.parse_args()

    with SessionLocal() as db:
        res = sync(db, dry=args.dry_run)
    if res.get("error"):
        print("!", res["error"])
        return 1
    tag = " (ซ้อม)" if args.dry_run else ""
    print(f"สาขาจาก SAP {res['total']} แห่ง{tag}")
    print(f"  เพิ่ม  {len(res['added'])} {' '.join(res['added']) if res['added'] else ''}")
    print(f"  แก้ชื่อ {len(res['updated'])} {' '.join(res['updated']) if res['updated'] else ''}")
    print(f"  ลบทิ้ง {len(res['removed'])} {' '.join(res['removed']) if res['removed'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
