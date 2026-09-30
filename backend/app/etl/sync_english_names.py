"""เติมชื่อภาษาอังกฤษให้สินค้าและหมวด — ดึงจาก store view ภาษาอังกฤษของ Magento

    .venv\\Scripts\\python.exe -m app.etl.sync_english_names
    .venv\\Scripts\\python.exe -m app.etl.sync_english_names --dry-run

Magento แยก store view ตามภาษา (store_id 1 = English, 2 = Thai) ชื่อสินค้าจึงมีสองชุด
อยู่แล้วในตาราง catalog_product_entity_varchar — ไม่ต้องแปลเอง

ข้อควรรู้ที่วัดจากของจริง: store "English" ไม่ได้เป็นอังกฤษทุกแถว
  ใช้ได้จริง   58%  ("Coffee Table Adorn")
  ยังเป็นไทย   26%  ("กระจกแบบแขวน รุ่น Selector" — ฝ่ายสินค้ายังไม่ได้แปล)
  รหัสดิบ SAP   6%  ("SELECTOR/กระจกแขวนM080/ขาว" — ไม่ใช่ชื่อที่เอาไปโชว์ลูกค้าได้)
จึงรับเฉพาะตัวที่เป็นอังกฤษจริง ที่เหลือปล่อยว่างไว้ให้หน้าเว็บถอยไปใช้ชื่อไทยแทน
ดีกว่าโชว์รหัสโรงงานให้ลูกค้าต่างชาติอ่าน

ฐาน Magento เป็นระบบจริงที่ใช้งานอยู่ — ไฟล์นี้ "อ่านอย่างเดียว" ห้ามเขียนกลับเด็ดขาด
"""
from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.catalog import Category, Material

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

EN_STORE = 1  # store view "English" ของ Magento
THAI = re.compile("[฀-๿]")


def usable(name: str | None) -> bool:
    """ชื่อนี้เอาไปโชว์เป็นภาษาอังกฤษได้ไหม

    ตัดสองอย่างทิ้ง: ตัวที่ยังมีอักษรไทยปน (แปลว่ายังไม่ได้แปล) กับตัวที่เป็นรหัสดิบจาก SAP
    ซึ่งสังเกตได้จากเครื่องหมาย / คั่นกลาง ("SELECTOR/กระจกแขวนM080/ขาว")
    """
    n = (name or "").strip()
    return bool(n) and not THAI.search(n) and "/" not in n and len(n) > 2


def _attr_id(c, entity_type: str, code: str) -> int:
    return c.execute(text("""
        SELECT attribute_id FROM eav_attribute
        WHERE attribute_code = :code
          AND entity_type_id = (SELECT entity_type_id FROM eav_entity_type WHERE entity_type_code = :et)
    """), {"code": code, "et": entity_type}).scalar()


def fetch_products(c) -> dict[str, str]:
    aid = _attr_id(c, "catalog_product", "name")
    rows = c.execute(text("""
        SELECT p.sku, v.value
        FROM catalog_product_entity p
        JOIN catalog_product_entity_varchar v
          ON v.entity_id = p.entity_id AND v.attribute_id = :a AND v.store_id = :s
    """), {"a": aid, "s": EN_STORE}).all()
    return {sku: val for sku, val in rows if usable(val)}


def fetch_categories(c) -> dict[int, str]:
    aid = _attr_id(c, "catalog_category", "name")
    # หมวดใช้ store 0 (admin) เป็นอังกฤษอยู่แล้ว ส่วน store 1 บางหมวดถึงจะตั้งทับ
    rows = c.execute(text("""
        SELECT entity_id, store_id, value FROM catalog_category_entity_varchar
        WHERE attribute_id = :a AND store_id IN (0, :s)
    """), {"a": aid, "s": EN_STORE}).all()
    out: dict[int, str] = {}
    for eid, store, val in sorted(rows, key=lambda r: r[1]):  # store 0 ก่อน แล้วให้ store 1 ทับ
        if usable(val):
            out[eid] = val
    return out


def sync(db: Session, *, dry_run: bool) -> dict:
    s = get_settings()
    if not s.magento_url:
        raise SystemExit("! ยังไม่ได้ตั้งค่าเชื่อม Magento ใน .env")
    eng = create_engine(s.magento_url, pool_pre_ping=True)
    with eng.connect() as c:
        prod = fetch_products(c)
        cats = fetch_categories(c)
    eng.dispose()

    mats = db.scalars(select(Material)).all()
    filled = skipped = 0
    for m in mats:
        name = prod.get(m.matnr)
        if not name:
            skipped += 1
            continue
        if m.name_en != name:
            filled += 1
            if not dry_run:
                m.name_en = name

    # หมวดชุดที่ยกมาจากเว็บจริงใช้ id เป็น url_key แล้ว จับกลับไปหา entity_id ไม่ได้ตรงๆ
    # จึงจับด้วยชื่ออังกฤษที่ ETL หมวดเก็บไว้ตอน sync (name_en) — ตัวไหนมีอยู่แล้วก็ข้าม
    cat_filled = sum(1 for cat in db.scalars(select(Category)).all() if usable(cat.name_en))

    if not dry_run:
        db.commit()
    return {"materials": len(mats), "filled": filled, "no_english": skipped,
            "cats_with_en": cat_filled, "cat_source": len(cats)}


def main() -> int:
    ap = argparse.ArgumentParser(description="เติมชื่อภาษาอังกฤษจาก Magento")
    ap.add_argument("--dry-run", action="store_true", help="ดูผลก่อน ไม่เขียนลงฐาน")
    args = ap.parse_args()
    with SessionLocal() as db:
        r = sync(db, dry_run=args.dry_run)
        pub = db.scalar(text("SELECT COUNT(*) FROM materials WHERE is_public=1")) if False else None
    print(f"สินค้าทั้งหมด {r['materials']:,} · เติมชื่ออังกฤษ {r['filled']:,} · ไม่มีอังกฤษที่ใช้ได้ {r['no_english']:,}")
    print(f"หมวดที่มีชื่ออังกฤษแล้ว {r['cats_with_en']:,}")
    if args.dry_run:
        print("(dry-run ไม่ได้เขียน)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
