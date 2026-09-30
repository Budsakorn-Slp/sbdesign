"""ดึงแกลเลอรีรูปสินค้าจากฐานเว็บ (sb_products_image) มาลง material_images ของแอป

    .venv\\Scripts\\python.exe -m app.etl.import_product_gallery
    .venv\\Scripts\\python.exe -m app.etl.import_product_gallery --matnr 19244933
    .venv\\Scripts\\python.exe -m app.etl.import_product_gallery --dry-run

ทำไมต้องมีตารางแยก: materials.image_url เก็บได้ใบเดียว หน้าสินค้าจึงเคยเอารูปของ
"สีอื่นในรุ่นเดียวกัน" มาวางเป็นแถวรูปย่อยแทน ซึ่งไม่ใช่รูปของสินค้าตัวนั้นจริงๆ
ของจริงมีเฉลี่ย 6 ใบต่อรหัส (สูงสุด 41) เรียงด้วย image_position อยู่แล้ว

ที่กรองทิ้ง:
  image_disabled = 1     ต้นทางปิดไว้
  media_type อื่น        external-video ไม่ใช่รูปสินค้า (เก็บแต่ภาพนิ่ง)
  image_position < 0     ของที่ไม่ได้อยู่ในแกลเลอรีจริง
  ป้ายบริการ             ship_special / ธงโปรโมชัน ไม่ใช่รูปสินค้า (ดู JUNK)
"""
from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.catalog import Material, MaterialImage

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# รูปที่อยู่ในแกลเลอรีแต่ไม่ใช่รูปสินค้า — เป็นป้ายบริการ/แบนเนอร์ที่ทีมเว็บแปะไว้ทุกตัว
# ถ้าไม่ตัดออก ลูกค้าเลื่อนดูรูปเตียงแล้วเจอป้าย "จัดส่งพิเศษ" คั่นกลาง
JUNK = re.compile(r"(ship[_-]?special|banner|promotion|logo|size[_-]?chart)", re.I)

BATCH = 2000


def fetch(c, matnrs: list[str] | None) -> list[tuple[str, str, int, str | None]]:
    sql = """
        SELECT sku, image_url, image_position, image_label
        FROM sb_products_image
        WHERE image_disabled = 0 AND media_type = 'image'
          AND image_position >= 0 AND image_url IS NOT NULL AND image_url <> ''
    """
    params: dict = {}
    if matnrs:
        sql += " AND sku IN :skus"
        params["skus"] = tuple(matnrs)
    sql += " ORDER BY sku, image_position"
    stmt = text(sql)
    if matnrs:
        stmt = stmt.bindparams(__import__("sqlalchemy").bindparam("skus", expanding=True))
    return [(r[0], r[1], int(r[2] or 0), r[3]) for r in c.execute(stmt, params)]


def sync(db: Session, matnrs: list[str] | None, *, dry_run: bool) -> dict:
    s = get_settings()
    if not s.sbweb_database_url:
        raise SystemExit("! ไม่ได้ตั้ง SBWEB_DATABASE_URL ใน .env")
    eng = create_engine(s.sbweb_database_url, pool_pre_ping=True, pool_recycle=3600)
    with eng.connect() as c:
        rows = fetch(c, matnrs)
    eng.dispose()

    known = {m for (m,) in db.execute(select(Material.matnr))}
    by_matnr: dict[str, list[tuple[str, int, str | None]]] = {}
    dropped = 0
    for sku, url, pos, label in rows:
        if sku not in known:
            continue
        if JUNK.search(url or "") or JUNK.search(label or ""):
            dropped += 1
            continue
        by_matnr.setdefault(sku, []).append((url, pos, label))

    if dry_run:
        return {"matnrs": len(by_matnr), "images": sum(len(v) for v in by_matnr.values()), "dropped": dropped}

    # เขียนทับทั้งรหัส — ต้นทางถอดรูปออกได้ ถ้า upsert ทีละใบรูปที่ถูกถอดจะค้างอยู่ตลอดไป
    targets = list(by_matnr)
    for i in range(0, len(targets), BATCH):
        chunk = targets[i : i + BATCH]
        db.execute(delete(MaterialImage).where(MaterialImage.matnr.in_(chunk)))
        objs = []
        for m in chunk:
            seen = set()
            for url, pos, label in by_matnr[m]:
                if url in seen:  # ต้นทางมีรูปซ้ำ url เดียวกันคนละ position อยู่บ้าง
                    continue
                seen.add(url)
                objs.append(MaterialImage(matnr=m, url=url[:400], position=pos, label=(label or None) and label[:200]))
        db.bulk_save_objects(objs)
        db.commit()
        print(f"  {min(i + BATCH, len(targets)):,}/{len(targets):,}")
    return {"matnrs": len(by_matnr), "images": sum(len(v) for v in by_matnr.values()), "dropped": dropped}


def main() -> int:
    ap = argparse.ArgumentParser(description="ดึงแกลเลอรีรูปสินค้าจากฐานเว็บมาลงฐานแอป")
    ap.add_argument("--matnr", action="append", help="เจาะจงรหัส (ใส่ซ้ำได้)")
    ap.add_argument("--dry-run", action="store_true", help="ดูผลก่อน ไม่เขียน")
    args = ap.parse_args()
    with SessionLocal() as db:
        r = sync(db, args.matnr, dry_run=args.dry_run)
    print(f"เสร็จ: สินค้า {r['matnrs']:,} รหัส · รูป {r['images']:,} ใบ · ตัดป้าย/แบนเนอร์ทิ้ง {r['dropped']:,}"
          + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
