"""ดึงสินค้าจาก sb_products (ฐานเว็บ) เข้าฐานของแอป

    python -m app.etl.import_catalog              # เฉพาะ is_active=1
    python -m app.etl.import_catalog --all        # เอาทั้งหมดรวมที่เลิกขาย
    python -m app.etl.import_catalog --limit 500  # ลองน้อยๆ ก่อน

เขียนลง categories / brands / materials / material_prices ด้วย upsert
ไม่ลบของเดิม — mock 20 ตัวจาก seed และตะกร้า/ออเดอร์เก่าที่อ้างถึงมันยังใช้ได้ต่อ

รหัสหมวด: ต้นทางใช้ MVGR4N ซ้ำได้ภายใต้ MVGR3N คนละตัว (เช่น "01" มีได้หลายหมวดแม่)
เลยต้องผูกรหัสแม่เข้าไปในรหัสลูก เป็น c4-<แม่>-<ลูก> ไม่งั้นต้นไม้หมวดจะพันกัน
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.catalog import Brand, Category, Material, MaterialPrice, shuffle_key_for
from app.etl.html_clean import clean
from app.services.catalog_service import is_web_visible

# ราคาต่ำกว่านี้ถือว่าเป็น "ราคาหลอก" ไม่ใช่ราคาขายจริง
# ต้นทาง sb_products มีของที่ตั้ง PRICE = NETPRICE = 1.00 ไว้ (เช่น 19196621 บอดี้+หน้าบาน
# ชุดครัว Kitchen Solutions ซึ่งเป็นงานสั่งทำ ต้องวัดหน้างานแล้วเสนอราคา) ถ้าปล่อยผ่าน
# หน้าเว็บจะขึ้น "฿1" ให้ลูกค้ากดซื้อได้ทันที — ซ่อนจากหน้าร้านไปก่อน แต่ยังเก็บไว้ในฐาน
# ให้เซลล์ค้นเจอและออกใบเสนอราคาเองได้ ของถูกสุดที่เป็นราคาจริงตอนนี้คือ 11 บาท

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CHUNK = 2000


def _cat_id(code: str) -> str:
    return f"c3-{code}"


def _sub_id(parent: str, code: str) -> str:
    return f"c4-{parent}-{code}"


def _brand_id(code: str) -> str:
    return f"b-{code}"


def fetch_rows(limit: int | None, only_active: bool) -> list[dict]:
    url = get_settings().sbweb_database_url
    if not url:
        raise SystemExit("! ไม่ได้ตั้ง SBWEB_DATABASE_URL ใน .env")
    eng = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
    sql = "SELECT * FROM sb_products"
    if only_active:
        sql += " WHERE IS_ACTIVE = 1"
    sql += " ORDER BY MATNR"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with eng.connect() as c:
        # ชื่อคอลัมน์ในฐานเว็บเป็นตัวพิมพ์ใหญ่ (ชุดเดียวกับ mdm_products) แต่ MariaDB ไม่แคร์ตัวพิมพ์
        # ฝั่งนี้แปลงเป็นตัวเล็กทีเดียวตรงนี้ โค้ดข้างล่างจะได้อ่านง่ายและไม่พังถ้าฐานเปลี่ยนตัวพิมพ์
        return [{k.lower(): v for k, v in r._mapping.items()} for r in c.execute(text(sql))]


def upsert_taxonomy(db: Session, rows: list[dict]) -> tuple[int, int]:
    """สร้าง/อัปเดต หมวดหลัก · หมวดย่อย · แบรนด์ ให้ครบก่อนใส่สินค้า (materials มี FK ไปหา)"""
    cats: dict[str, tuple[str, str | None, int]] = {}  # id -> (ชื่อ, พ่อ, ลำดับ)
    brands: dict[str, str] = {}

    for r in rows:
        # MVGR3N/T = หมวดหลัก · MVGR4N/T = หมวดย่อย · MVGR1N/T = แบรนด์ (ชื่อช่องตามฐานเว็บ v3)
        cc, cn = r.get("mvgr3n"), r.get("mvgr3t")
        if cc:
            cats.setdefault(_cat_id(cc), (cn or cc, None, int(cc) if str(cc).isdigit() else 999))
            sc, sn = r.get("mvgr4n"), r.get("mvgr4t")
            if sc:
                cats.setdefault(_sub_id(cc, sc), (sn or sc, _cat_id(cc), 0))
        bc, bn = r.get("mvgr1n"), r.get("mvgr1t")
        if bc:
            brands.setdefault(_brand_id(bc), bn or bc)

    have_cat = {c.id: c for c in db.scalars(select(Category)).all()}
    for cid, (name, parent, sort) in cats.items():
        if cid in have_cat:
            have_cat[cid].name_th, have_cat[cid].parent_id, have_cat[cid].sort = name[:120], parent, sort
        else:
            db.add(Category(id=cid, name_th=name[:120], parent_id=parent, sort=sort, icon="category"))
    db.flush()

    have_brand = {b.id: b for b in db.scalars(select(Brand)).all()}
    for bid, name in brands.items():
        if bid in have_brand:
            have_brand[bid].name = name[:120]
        else:
            db.add(Brand(id=bid, name=name[:120]))
    db.flush()
    return len(cats), len(brands)


# ---------- กลุ่มบนแถบเมนู ----------
# MDM ส่งหมวดมาแบนๆ 70 กว่าหมวด (c3-*) เอาขึ้นแถบเมนูตรงๆ ไม่ไหว เลยจับเข้ากลุ่มตามหน้าเว็บจริง
# แล้วให้ /home ปั้นเมนูจากต้นไม้หมวดนี้อีกที
#
# ต้องทำตรงนี้ ไม่ใช่แก้ในฐาน เพราะ upsert_taxonomy เซ็ต parent_id ของ c3-* เป็น None ใหม่ทุกรอบ
# id ของกลุ่มใช้ตัวเดิมจาก seed (bedroom/living/...) ลิงก์เก่าที่ชี้มาเลยยังใช้ได้ และกลายเป็นมีสินค้าจริง
GROUPS: dict[str, dict] = {
    "bedroom": {"name": "ห้องนอน", "name_en": "Bedroom", "room": "bedroom", "icon": "bed", "sort": 1,
                "members": ["c3-02", "c3-13", "c3-20", "c3-19", "c3-27", "c3-28", "c3-09", "c3-B8", "c3-A6", "mattress"]},
    "living": {"name": "ห้องนั่งเล่น", "name_en": "Living Room", "room": "living", "icon": "weekend", "sort": 2,
               "members": ["c3-12", "c3-35", "c3-36", "c3-37", "c3-38", "c3-64", "c3-31", "c3-32", "c3-33", "c3-34",
                           "c3-66", "c3-62", "c3-03", "c3-06", "c3-08", "c3-18", "c3-57", "sofa", "storage", "small-spaces"]},
    "dining": {"name": "ห้องทานอาหาร / ห้องครัว", "name_en": "Dining & Kitchen", "room": "dining", "icon": "restaurant", "sort": 3,
               "members": ["c3-05", "c3-04", "c3-10", "c3-22", "c3-43", "c3-49", "kitchen"]},
    "office": {"name": "ห้องทำงาน / ห้องเกมมิ่ง", "name_en": "Home Office & Gaming", "room": "office", "icon": "desk", "sort": 4,
               "members": ["c3-14", "c3-44", "c3-45", "office-furniture"]},
    "special": {"name": "สินค้าพิเศษ", "name_en": "Special Items", "room": None, "icon": "star", "sort": 5,
                "members": ["c3-21", "c3-01", "c3-C2", "c3-40", "c3-B3", "c3-15", "c3-A9", "outdoor", "kids"]},
    "decor": {"name": "ของตกแต่ง", "name_en": "Home Decor", "room": None, "icon": "chair", "sort": 6,
              "members": ["c3-07", "c3-48", "c3-51", "c3-55", "c3-46", "c3-23", "c3-B1", "c3-B6", "c3-47", "c3-50",
                          "c3-B2", "lighting", "wall-decor", "rugs-curtains"]},
}


def apply_groups(db: Session) -> int:
    """สร้างหมวดกลุ่ม แล้วย้ายหมวดจริงเข้าไปอยู่ใต้กลุ่ม — เรียกทุกครั้งหลัง upsert_taxonomy"""
    have = {c.id: c for c in db.scalars(select(Category)).all()}
    moved = 0
    for gid, g in GROUPS.items():
        row = have.get(gid)
        if not row:
            row = Category(id=gid)
            db.add(row)
            have[gid] = row
        row.name_th, row.room, row.icon, row.sort, row.parent_id = g["name"], g["room"], g["icon"], g["sort"], None
        row.name_en = g.get("name_en") or row.name_en
        db.flush()
        for cid in g["members"]:
            child = have.get(cid)
            if child and child.parent_id != gid:
                child.parent_id = gid
                moved += 1
    db.flush()
    return moved


MIN_REAL_PRICE = 10  # บาท


def _fake_price(net) -> bool:
    """ราคานี้เชื่อไม่ได้ใช่ไหม (ไม่มีราคา หรือถูกจนเป็นไปไม่ได้)"""
    try:
        return net is None or float(net) <= MIN_REAL_PRICE
    except (TypeError, ValueError):
        return True


def _trim(v, n: int) -> str | None:
    t = str(v).strip() if v is not None else ""
    return t[:n] or None


def _desc_html(raw) -> str | None:
    """คำบรรยายเต็มจากฐานเว็บ — บางตัวเป็น HTML บางตัวเป็นข้อความเปล่า

    ล้างด้วยตัวเดียวกับหน้า CMS (ตัด script/style/inline style ทิ้ง เหลือแต่แท็กเนื้อหา)
    ข้อความเปล่าผ่านตัวล้างแล้วก็ยังเป็นข้อความเปล่า ไม่ต้องแยกทางเดิน
    """
    txt = (raw or "").strip()
    if not txt:
        return None
    return clean(txt) or None


def upsert_materials(db: Session, rows: list[dict]) -> int:
    have = set(db.scalars(select(Material.matnr)).all())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    done = 0

    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        matnrs = [r["matnr"] for r in chunk]
        # ราคาเขียนทับทั้งชุด: ลบของเดิมแล้วใส่ใหม่ ง่ายและถูกกว่าไล่เทียบทีละ tier
        db.execute(delete(MaterialPrice).where(MaterialPrice.matnr.in_(matnrs)))

        for r in chunk:
            cc, sc = r.get("mvgr3n"), r.get("mvgr4n")
            cat_id = _sub_id(cc, sc) if cc and sc else (_cat_id(cc) if cc else None)
            bc = r.get("mvgr1n")
            fields = dict(
                sku=r["matnr"],
                # ชื่อโชว์มาจาก DISPLAY_NAME (ฐานเว็บคลีนไว้แล้ว) · MAKTX ดิบเก็บไว้ให้เซลล์ค้น
                name_th=((r.get("display_name") or r.get("maktx") or "")[:200]),
                name_raw=(r.get("maktx") or None),
                # ชื่ออังกฤษเดิมของเว็บ (เฉพาะตัวที่ฐานเว็บประกอบชื่อไทยให้) — ยังค้นเจอด้วยคำอังกฤษ
                name_en=(r.get("name_en") or None),
                variant=(r.get("mvgr2t") or None),
                spec=(r.get("size_text") or None),
                color=(r.get("color_th") or r.get("color_en") or None),
                # แกนตัวเลือกบนหน้าสินค้า — SAP แยกไว้ให้แล้ว ไม่ต้องแกะจากชื่อ
                size_label=_trim(r.get("mvgr5t"), 80),
                color_code=_trim(r.get("mvgr6t"), 60),
                style=(r.get("style_th") or r.get("style_en") or None),
                # SHORT_DESC -> กล่อง "ข้อมูลสินค้า" · LONG_DESC -> บล็อกยาวใต้หน้าสินค้า
                # ของเดิมยัดรวมช่องเดียวโดยเอา long มาก่อน ทำให้กล่องสั้นกลายเป็นข้อความยาวเต็มไปหมด
                description=(r.get("short_desc") or None),
                description_long=_desc_html(r.get("long_desc")),
                category_id=cat_id,
                brand_id=_brand_id(bc) if bc else None,
                image_url=r.get("image_url") or None,
                # เว็บโชว์เฉพาะกลุ่มที่ตั้งไว้ (ตอนนี้ MATNR ขึ้นต้น 19) ที่เหลือซ่อนแต่เซลล์ยังค้นเจอ
                is_public=bool(r.get("is_public")) and is_web_visible(r["matnr"]) and not _fake_price(r.get("netprice")),
                # ชั้น MAABC มาจาก sb_products v3 — ถ้ายังเป็นตาราง v2 อยู่ ช่องนี้ไม่มี ได้ None/False
                abc_class=(r.get("maabc") or None),
                is_bestseller=bool(r.get("is_bestseller")),
                requires_install=bool(r.get("needs_assembly")),
                is_takeaway_ok=bool(r.get("is_flatpack")),
                tags=[t for t in (r.get("spart_text"), "luxury" if r.get("is_luxury") else None) if t],
                # เลขประจำตัวสำหรับสลับลำดับหน้าเว็บ — คิดจากรหัส จึงได้ค่าเดิมทุกรอบ
                # ตั้งทุกครั้งที่ import เผื่อแถวเก่าที่ยังเป็น 0 จากตอนเพิ่มคอลัมน์
                shuffle_key=shuffle_key_for(r["matnr"]),
                synced_at=now,
            )
            if r["matnr"] in have:
                m = db.get(Material, r["matnr"])
                for k, v in fields.items():
                    setattr(m, k, v)
            else:
                db.add(Material(matnr=r["matnr"], **fields))

            net, lst = r.get("netprice"), r.get("price")
            if net:
                db.add(MaterialPrice(matnr=r["matnr"], tier="standard", price=net))
            if lst and net and lst > net:
                db.add(MaterialPrice(matnr=r["matnr"], tier="compare_at", price=lst))

        db.flush()
        done += len(chunk)
        print(f"  {done:,}/{len(rows):,}")
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description="import sb_products เข้าฐานแอป")
    ap.add_argument("--all", action="store_true", help="เอาทั้งหมด ไม่กรอง is_active")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--groups-only", action="store_true", help="จัดกลุ่มหมวดใหม่อย่างเดียว ไม่ต้องดึงสินค้า")
    args = ap.parse_args()

    if args.groups_only:
        with SessionLocal() as db:
            print(f"จัดกลุ่มหมวด: ย้าย {apply_groups(db):,} หมวดเข้ากลุ่ม")
            db.commit()
        return 0

    print(f"อ่านจาก sb_products{'' if args.all else ' (is_active=1)'} ...")
    rows = fetch_rows(args.limit, only_active=not args.all)
    print(f"  ได้ {len(rows):,} แถว")
    if not rows:
        print("! ไม่มีข้อมูล — rebuild sb_products ก่อนหรือยัง")
        return 1

    with SessionLocal() as db:
        n_cat, n_brand = upsert_taxonomy(db, rows)
        print(f"  หมวด {n_cat:,} · แบรนด์ {n_brand:,} · จัดกลุ่ม {apply_groups(db):,}")
        n = upsert_materials(db, rows)
        db.commit()

        total = db.scalar(select(func.count()).select_from(Material))
        print(f"เสร็จ: นำเข้า {n:,} · materials ทั้งหมดในฐานแอป {total:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
