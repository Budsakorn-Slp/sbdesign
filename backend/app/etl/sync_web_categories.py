"""ยกการจัดหมวดของ sbdesignsquare.com มาใช้ — อ่านจากฐาน Magento ตรงๆ

    .venv\\Scripts\\python.exe -m app.etl.sync_web_categories              # กลุ่มที่ตั้งไว้ใน ROOTS
    .venv\\Scripts\\python.exe -m app.etl.sync_web_categories --dry-run    # ดูว่าจะได้อะไรก่อนเขียนจริง

ทำไมอ่านจากฐาน ไม่ scrape หน้าเว็บ:
  หน้าหมวดของเว็บ render รายการสินค้าด้วย JavaScript — ดึงด้วย HTTP ธรรมดาได้แค่ 6 ชิ้น
  จาก 458 ต้องใช้ headless browser ซึ่งเป็นภาระและพังง่ายเวลาเว็บเปลี่ยนหน้าตา
  ส่วนฐาน Magento เก็บของจริงไว้ครบและนิ่งกว่า:
    catalog_category_entity          โครงหมวด (แม่-ลูก, ลำดับ, ธงเปิด/ปิด)
    catalog_category_product         การจับคู่หมวด-สินค้า 224,756 คู่
    catalog_product_entity.sku       = MATNR ตรงๆ จับคู่กับของเราได้ทันที
  ชื่อไทยอยู่ที่ store_id = 2 (store_id 0 เป็นภาษาอังกฤษ)

เมนูบนเว็บจริงเกิดจากธง is_active + include_in_menu เรียงตาม position — ใช้เงื่อนไขเดียวกัน
เป๊ะๆ เมนูของเราจึงออกมาเหมือนเว็บจริงโดยไม่ต้องไล่พิมพ์ชื่อหมวดเอง (เทียบกับหน้าจริงแล้วตรง)

ฐาน Magento เป็นระบบจริงที่ใช้งานอยู่ — ไฟล์นี้ "อ่านอย่างเดียว" ห้ามเขียนกลับเด็ดขาด
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.catalog import Category, Material, MaterialCategory

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# รหัส attribute ของ Magento (คงที่ต่อการติดตั้งหนึ่งชุด — อ่านสดทุกครั้งกันพลาดเวลาย้ายเครื่อง)
ATTR_CODES = ("name", "url_key", "url_path", "is_active", "include_in_menu")

# กลุ่มที่จะยกมา — ค่าใน ROOTS คือ entity_id ของหมวดระดับกลุ่มในเว็บจริง
# EXTRA คือหมวดที่เมนูเว็บจริงหยิบข้ามต้นไม้มาใส่ไว้ (เตียงสั่งทำอยู่ใต้ "เฟอร์นิเจอร์สั่งทำ"
# แต่โผล่ในเมนูห้องนอนด้วย) — ระบุคู่ (หมวด, ไปอยู่ใต้กลุ่มไหน)
ROOTS = {
    "bedroom": [824, 955, 963, 976, 970],  # ห้องนอน · ที่นอน · ชุดเครื่องนอน · แผ่นรองนอนฯ · หมอน
    # เรียงตามเมนูเว็บจริง · ห้องทานอาหาร (847) อยู่คนละต้นไม้ (furniture) แต่เว็บวางไว้คอลัมน์ท้าย
    # หลายกลุ่มในนี้เราไม่มีสินค้าเลย (แก้วน้ำ/เครื่องครัว/เครื่องใช้ไฟฟ้า — เป็นของ marketplace
    # ของเว็บ ไม่ได้อยู่ในแคตตาล็อก SAP ที่เราดึงมา) ใส่ไว้ได้ เพราะเมนูตัดหมวดที่ไม่มีของทิ้งเอง
    # วันไหนมีสินค้ากลุ่มนั้นเข้ามา หมวดจะโผล่เองโดยไม่ต้องแก้โค้ด
    "dining": [994, 1000, 1006, 1011, 1016, 1021, 1304, 847],
    # ห้องนั่งเล่น — เมนูเว็บจริงรวม 4 กลุ่มนี้ไว้ด้วยกัน (โซฟา/เก้าอี้พักผ่อน/ตู้เก็บของ
    # อยู่คนละกิ่งใน furniture แต่เว็บเอามาไว้ในเมนูเดียว)
    "living": [834, 873, 894, 863],
    # ห้องทำงาน/เกมมิ่ง — เว็บจริงมีกลุ่มเดียว
    "office": [884],
    "decor": [1031, 1034, 1038, 1044, 1048, 1054, 1058, 1065, 1072, 1076, 1087],
    "special": [1138, 1156, 1139, 1192, 1140, 1310, 1311, 1193, 1329, 1212],
}
EXTRA = {
    "bedroom": [(905, 824)],  # เตียงสั่งทำ -> อยู่ใต้กลุ่ม "ห้องนอน" เหมือนเว็บจริง
}

# id ของหมวด = url_key ของเว็บจริง (beds, spring-mattresses) ไม่ใช่เลขรหัส
# เพราะมันโผล่ใน URL ที่ลูกค้าเห็น (/search?category=beds) ต้องอ่านรู้เรื่อง
# ถ้าไปชนกับหมวดที่มีอยู่แล้วค่อยเติมเลขต่อท้าย (กันพัง ไม่ใช่กรณีปกติ)
def cat_id(r: dict, taken: set[str]) -> str:
    base = (r.get("url_key") or f"c{r['entity_id']}").strip().lower()[:36]
    if base not in taken:
        return base
    return f"{base}-{r['entity_id']}"[:40]


def _attr_ids(c) -> dict[str, int]:
    rows = c.execute(text("""
        SELECT attribute_code, attribute_id FROM eav_attribute
        WHERE attribute_code IN :codes
          AND entity_type_id = (SELECT entity_type_id FROM eav_entity_type WHERE entity_type_code='catalog_category')
    """), {"codes": ATTR_CODES}).all()
    return {code: aid for code, aid in rows}


def fetch_tree(c, ids: list[int], attrs: dict[str, int]) -> list[dict]:
    """หมวดที่ขอ + ลูกของมัน เฉพาะตัวที่เว็บจริงเปิดให้เห็นในเมนู เรียงตามลำดับของเว็บ"""
    rows = c.execute(text("""
        SELECT e.entity_id, e.parent_id, e.level, e.position,
               COALESCE(nt.value, n0.value) AS name_th,
               n0.value AS name_en,
               uk.value AS url_key
        FROM catalog_category_entity e
        LEFT JOIN catalog_category_entity_varchar n0
               ON n0.entity_id = e.entity_id AND n0.attribute_id = :na AND n0.store_id = 0
        LEFT JOIN catalog_category_entity_varchar nt
               ON nt.entity_id = e.entity_id AND nt.attribute_id = :na AND nt.store_id = 2
        LEFT JOIN catalog_category_entity_varchar uk
               ON uk.entity_id = e.entity_id AND uk.attribute_id = :ka AND uk.store_id = 0
        LEFT JOIN catalog_category_entity_int act
               ON act.entity_id = e.entity_id AND act.attribute_id = :ia AND act.store_id = 0
        LEFT JOIN catalog_category_entity_int men
               ON men.entity_id = e.entity_id AND men.attribute_id = :ma AND men.store_id = 0
        WHERE (e.entity_id IN :ids OR e.parent_id IN :ids)
          AND act.value = 1 AND men.value = 1
        ORDER BY e.level, e.position
    """), {"na": attrs["name"], "ka": attrs["url_key"], "ia": attrs["is_active"], "ma": attrs["include_in_menu"], "ids": tuple(ids)}).all()
    return [dict(r._mapping) for r in rows]


def fetch_links(c, ids: list[int]) -> list[tuple[int, str]]:
    rows = c.execute(text("""
        SELECT cp.category_id, p.sku
        FROM catalog_category_product cp
        JOIN catalog_product_entity p ON p.entity_id = cp.product_id
        WHERE cp.category_id IN :ids
    """), {"ids": tuple(ids)}).all()
    return [(cid, sku) for cid, sku in rows]


def _dead_slugs(db: Session, room: str) -> set[str]:
    """หมวดที่ตั้งมือไว้ในห้องนี้และไม่มีสินค้าเลย — ของตายที่หมดหน้าที่เมื่อยกชุดเว็บเข้ามา

    เหลือไว้จะเจอสองปัญหา: ลูกค้าเห็นหมวดชื่อซ้ำที่กดแล้วว่าง และมันจองชื่อ id
    ที่เราอยากใช้ (bedding, pillow) ไว้ · หมวดจาก SAP (c3-/c4-) ไม่แตะ ยังมีของอยู่
    """
    rows = db.execute(select(Category.id).where(
        Category.room == room, Category.id != room,
        ~Category.id.like("c3-%"), ~Category.id.like("c4-%"),
    )).all()
    out = set()
    for (cid,) in rows:
        n = db.scalar(select(func.count()).select_from(Material).where(Material.category_id == cid)) or 0
        n += db.scalar(select(func.count()).select_from(MaterialCategory).where(MaterialCategory.category_id == cid)) or 0
        if n == 0:
            out.add(cid)
    return out


def sync(db: Session, group: str, *, dry_run: bool) -> dict:
    s = get_settings()
    if not s.magento_url:
        raise SystemExit("! ยังไม่ได้ตั้งค่าเชื่อม Magento ใน .env")
    roots = ROOTS[group]
    extra = EXTRA.get(group, [])

    eng = create_engine(s.magento_url, pool_pre_ping=True)
    with eng.connect() as c:
        attrs = _attr_ids(c)
        tree = fetch_tree(c, roots, attrs)
        # หมวดข้ามต้นไม้ที่เมนูเว็บจริงหยิบมาใส่ (เช่นเตียงสั่งทำ) — ดึงเดี่ยวแล้วย้ายพ่อให้
        for mid, new_parent in extra:
            got = fetch_tree(c, [mid], attrs)
            for r in got:
                if r["entity_id"] == mid:
                    r["parent_id"] = new_parent
                    # position ของมันนับจากต้นไม้เดิม (เตียงสั่งทำเป็นลูกคนแรกของเฟอร์นิเจอร์สั่งทำ)
                    # ถ้าใช้ตามนั้นจะไปแทรกกลางเมนู — เว็บจริงวางไว้ท้ายสุด ดันไปท้ายเลย
                    r["position"] = 999
                    tree.append(r)
        ids = [r["entity_id"] for r in tree]
        links = fetch_links(c, ids)
    eng.dispose()

    known = {m for (m,) in db.execute(select(Material.matnr).where(Material.matnr.in_({sku for _, sku in links})))}

    # ตั้ง id ให้ทุกหมวดก่อน (ต้องรู้ทั้งชุดถึงจะกันชนกันเองได้) — เลี่ยง id ที่ระบบใช้อยู่แล้ว
    # ยกเว้นหมวดเปล่าที่ตั้งมือไว้ในห้องนี้ ซึ่งกำลังจะถูกแทนที่อยู่แล้ว (ลบทิ้งข้างล่าง)
    dead = _dead_slugs(db, group)
    # ชุดเว็บของห้องนี้ถูกสร้างใหม่ทั้งชุดทุกรอบ จึงต้องปล่อย id เดิมให้ว่างก่อนแจกใหม่
    # ไม่งั้นรอบนี้จะเลี่ยงไปใช้ชื่อมีเลขต่อท้าย (beds-955) แล้วรอบหน้าที่ของเก่าถูกลบไปแล้ว
    # ก็กลับมาใช้ beds อีก — id สลับไปมาทุกรอบ ลิงก์หมวดที่ลูกค้าบุ๊กมาร์กไว้พังหมด
    web_of_group = {i for (i,) in db.execute(select(Category.id).where(
        Category.room == group, Category.source == "web", Category.id != group,
    )).all()}
    taken = {i for (i,) in db.execute(select(Category.id))} - dead - web_of_group
    ids_by_magento: dict[int, str] = {}
    for r in tree:
        cid = cat_id(r, taken)
        taken.add(cid)
        ids_by_magento[r["entity_id"]] = cid
    pairs = {(ids_by_magento[cid], sku) for cid, sku in links if sku in known and cid in ids_by_magento}

    if dry_run:
        return {"categories": len(tree), "links": len(pairs), "materials": len({m for _, m in pairs}), "tree": tree}

    # หมวดเปล่าที่ตั้งมือไว้ของห้องนี้ (bed, bedding, pillow ...) หมดหน้าที่แล้ว ลบทิ้ง
    # ไม่งั้นเหลือหมวดชื่อซ้ำที่ไม่มีสินค้าค้างอยู่ และไปกิน id ที่เราอยากใช้ด้วย
    if dead:
        # ลูกของหมวดที่จะลบต้องย้ายพ่อก่อน ไม่งั้น FK พัง (mattress เป็นพ่อของ mattress-spring)
        # ย้ายไปแขวนกับหมวดห้อง ของที่ยังมีสินค้าอยู่จะได้ไม่หลุดหายไปจากต้นไม้
        db.execute(update(Category).where(Category.parent_id.in_(dead), ~Category.id.in_(dead)).values(parent_id=group))
        db.execute(delete(MaterialCategory).where(MaterialCategory.category_id.in_(dead)))
        db.flush()
        db.execute(delete(Category).where(Category.id.in_(dead)))
        db.flush()

    # หมวดชุดเว็บ "รุ่นก่อน" ของห้องนี้ที่ไม่มีอยู่ในชุดใหม่ ต้องลบทิ้งทุกครั้งที่ sync
    #
    # ทำไมต้องมี: รูปแบบ id เคยเปลี่ยน (bedroom-furniture -> bedroom-furniture-824)
    # พอรันรอบใหม่ก็สร้างชุดใหม่ทั้งชุด ส่วนชุดเก่าไม่โดนลบเพราะ _dead_slugs ไว้ชีวิต
    # หมวดที่ยังมีสินค้าผูกอยู่ ผลคือเมนูมี "ห้องนอน" / "ห้องนั่งเล่น" โผล่ซ้ำสองอัน
    #
    # ตัดทิ้งได้ปลอดภัยเพราะชุด source="web" ถูกสร้างใหม่ทั้งหมดทุกรอบอยู่แล้ว
    # และความสัมพันธ์สินค้า-หมวดก็เขียนใหม่ท้ายฟังก์ชันนี้ · หมวดของ SAP (c3-/c4-) ไม่แตะ
    stale = web_of_group - set(ids_by_magento.values())
    if stale:
        db.execute(update(Category).where(Category.parent_id.in_(stale), ~Category.id.in_(stale)).values(parent_id=group))
        db.execute(delete(MaterialCategory).where(MaterialCategory.category_id.in_(stale)))
        db.flush()
        db.execute(delete(Category).where(Category.id.in_(stale)))
        db.flush()
        print(f"  ลบหมวดชุดเก่าที่ตกค้าง {len(stale)} หมวด")

    top = set(roots)
    # เขียนสองรอบ เพราะ Magento ส่งหมวดมาไม่เรียงตามชั้น หมวดลูกมาก่อนหมวดแม่ได้
    # ถ้าผูก parent_id ตั้งแต่รอบแรก จะชี้ไปหาแถวที่ยังไม่มีในฐาน แล้วโดน FOREIGN KEY
    # constraint failed ตีตกทั้งกลุ่ม (เคยทำให้ living/office/decor/special ไม่เข้าเลย)
    #   รอบแรก  = สร้างแถวให้ครบ แขวนไว้ใต้หมวดห้องซึ่งมีอยู่แน่นอน
    #   รอบสอง  = ผูกแม่-ลูกจริง ตอนนี้ทุกแถวมีตัวตนแล้ว ชี้ไปไหนก็ไม่พัง
    parent_of: dict[str, str] = {}
    for r in tree:
        cid = ids_by_magento[r["entity_id"]]
        # กลุ่มบนสุดของชุดเว็บไปแขวนใต้หมวดห้องเดิม (bedroom) ไม่ปล่อยลอยเป็นหมวดบนสุด
        # ไม่งั้นเมนู "สินค้าทั้งหมด" จะมี "ห้องนอน" โผล่สองอัน (ของ SAP กับของเว็บ)
        # และได้ความลึก 3 ชั้นพอดี: ห้องนอน > ที่นอน > ที่นอนสปริง
        parent_of[cid] = group if r["entity_id"] in top else ids_by_magento.get(r["parent_id"], group)
        row = db.get(Category, cid)
        if not row:
            row = Category(id=cid)
            db.add(row)
        row.name_th = (r["name_th"] or r["name_en"] or cid)[:120]
        row.name_en = (r["name_en"] or None) and r["name_en"][:120]
        row.parent_id = group
        row.room = group
        row.source = "web"
        # position ของ Magento นับเฉพาะในหมู่พี่น้องพ่อเดียวกัน กลุ่มบนสุดคนละต้นไม้จึงชนกันหมด
        # (ห้องนอนกับที่นอนได้ position 1 ทั้งคู่) — กลุ่มบนสุดเรียงตามลำดับที่เขียนไว้ใน ROOTS
        # ซึ่งเรียงตามเมนูเว็บจริง ส่วนหมวดย่อยใช้ position ตามเดิมเพราะพ่อเดียวกัน
        row.sort = roots.index(r["entity_id"]) if r["entity_id"] in top else int(r["position"] or 0)
    db.flush()

    for cid, parent in parent_of.items():
        db.get(Category, cid).parent_id = parent
    db.flush()

    # ความสัมพันธ์: ลบของกลุ่มนี้ทิ้งแล้วเขียนใหม่ทั้งชุด — เว็บจริงย้ายของเข้าออกหมวดได้
    # ถ้า upsert ทีละแถวโดยไม่ลบ ของที่ถูกถอดออกจากหมวดแล้วจะค้างอยู่ตลอดไป
    our_ids = list(ids_by_magento.values())
    db.execute(delete(MaterialCategory).where(MaterialCategory.category_id.in_(our_ids)))
    db.bulk_save_objects([MaterialCategory(matnr=m, category_id=c) for c, m in pairs])
    db.commit()
    return {"categories": len(tree), "links": len(pairs), "materials": len({m for _, m in pairs}), "tree": tree}


def main() -> int:
    ap = argparse.ArgumentParser(description="ยกหมวดสินค้าจากเว็บจริง (Magento) มาใช้")
    ap.add_argument("--group", default="bedroom", choices=sorted(ROOTS), help="กลุ่มที่จะยกมา")
    ap.add_argument("--dry-run", action="store_true", help="ดูผลก่อน ไม่เขียนลงฐาน")
    args = ap.parse_args()

    with SessionLocal() as db:
        res = sync(db, args.group, dry_run=args.dry_run)
    by_parent: dict = {}
    for r in res["tree"]:
        by_parent.setdefault(r["parent_id"], []).append(r)
    print(f"กลุ่ม {args.group}: หมวด {res['categories']} · จับคู่ {res['links']:,} คู่ · สินค้า {res['materials']:,} ตัว"
          + (" (dry-run ไม่ได้เขียน)" if args.dry_run else ""))
    for top in ROOTS[args.group]:
        me = next((r for r in res["tree"] if r["entity_id"] == top), None)
        if not me:
            continue
        print(f"  {me['name_th']}")
        for ch in by_parent.get(top, []):
            if ch["entity_id"] != top:
                print(f"    - {ch['name_th']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
