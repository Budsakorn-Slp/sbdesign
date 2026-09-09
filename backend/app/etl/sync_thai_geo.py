"""ที่อยู่ไทย (ตำบล/อำเภอ/จังหวัด + รหัสไปรษณีย์) จาก Magento -> sb_thai_geo -> thai_geo

    python -m app.etl.sync_thai_geo --report-only    # ดูสรุปอย่างเดียว ไม่เขียนอะไร
    python -m app.etl.sync_thai_geo                  # เขียนทั้งฐานเว็บและฐานแอป
    python -m app.etl.sync_thai_geo --no-sbweb       # ลงเฉพาะฐานแอป

เดินทางเดียวกับ ETL ตัวอื่น: Magento (อ่านอย่างเดียว) -> sb_* บนฐานเว็บ -> ฐานแอป
ชุดนี้แทบไม่เปลี่ยน (รหัสไปรษณีย์ไทยขยับปีละไม่กี่ครั้ง) แต่ให้ sync รายวันไปพร้อมกฎค่าส่ง
จะได้ไม่ต้องจำว่าต้องรันตัวไหนเพิ่มตอนกรมไปรษณีย์ประกาศรหัสใหม่

area_id ผูกกับ ship_area_postcodes ของเรา (prefix ยาวสุดชนะ) — ถ้าวันหนึ่งย้ายจังหวัดไหน
เข้า/ออกเขตปริมณฑล แก้ที่ AREA_POSTCODES ใน sync_shipping_rules ที่เดียว แล้วรันตัวนี้ตาม
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, delete, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.etl.sync_shipping_rules import AREA_POSTCODES
from app.models.geo import ThaiGeo

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CHUNK = 2000
DEFAULT_AREA = 2  # ไม่เข้า prefix ไหน = ต่างจังหวัด (ตรงกับ ShipArea.is_default)

# ชื่อจังหวัดเอา th_TH ก่อน ไม่มีค่อยใช้ default_name (อังกฤษ) — 74 จังหวัด ไม่มีสามจังหวัดชายแดนใต้
#
# ไม่กรอง s.enable ทิ้ง: enable = 0 คือ "ส่งไม่ถึง" ไม่ใช่ "ไม่มีตำบลนี้" (เกาะสีชัง เกาะช้าง
# เกาะพะงัน ระนอง และบึงกาฬทั้งจังหวัด) ถ้าตัดออกตั้งแต่ต้นทาง ลูกค้าบึงกาฬจะหาจังหวัดตัวเอง
# ไม่เจอโดยไม่มีคำอธิบาย — เก็บมาทั้งหมดแล้วติดธง is_blocked ให้หน้าเว็บบอกเหตุผลได้แทน
GEO_SQL = """
SELECT s.subdistrict_id, s.zipcode, s.th_name, s.name,
       d.district_id, d.th_name, d.name,
       r.region_id, COALESCE(n.name, r.default_name), r.default_name, s.enable
  FROM directory_subdistrict s
  JOIN directory_district d       ON d.district_id = s.district_id
  JOIN directory_country_region r ON r.region_id = d.region_id AND r.country_id = 'TH'
  LEFT JOIN directory_country_region_name n ON n.region_id = r.region_id AND n.locale = 'th_TH'
"""


def _area_of(zipcode: str) -> int:
    """prefix ยาวสุดชนะ — ตรรกะเดียวกับ shipping_engine.area_for_postcode"""
    for n in (5, 4, 3, 2, 1):
        for prefix, area_id, _ in AREA_POSTCODES:
            if len(prefix) == n and zipcode.startswith(prefix):
                return area_id
    return DEFAULT_AREA


def fetch() -> tuple[list[dict], list[str]]:
    url = get_settings().magento_url
    if not url:
        raise SystemExit("! ไม่ได้ตั้ง MAGENTO_HOST/USER/PASSWORD ใน .env (ฐาน Magento บน 10.9.12.67)")
    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as c:
        blocked = {str(z) for z in c.execute(text("SELECT postcode FROM forbidden_postcode")).scalars().all()}
        rows = c.execute(text(GEO_SQL)).fetchall()
    out = []
    for sid, zipcode, sub_th, sub_en, did, dis_th, dis_en, rid, prov_th, prov_en, enable in rows:
        z = str(zipcode).strip()
        out.append({
            "subdistrict_id": int(sid), "zipcode": z,
            "subdistrict_th": sub_th or sub_en, "subdistrict_en": sub_en,
            "district_id": int(did), "district_th": dis_th or dis_en, "district_en": dis_en,
            "province_id": int(rid), "province_th": prov_th, "province_en": prov_en,
            # ปิดที่ตำบล (enable=0) หรือรหัสอยู่ในลิสต์ห้ามส่ง — ต้นทางใช้สองที่ ไม่ซ้อนกันทั้งหมด
            # (23170 ตำบลยังเปิดแต่รหัสอยู่ในลิสต์ห้าม · บึงกาฬปิดที่ตำบลแต่ไม่ได้อยู่ในลิสต์)
            "area_id": _area_of(z), "is_blocked": z in blocked or not enable,
        })
    provinces = {r["province_id"] for r in out}
    a1 = sum(1 for r in out if r["area_id"] == 1)
    open_prov = {r["province_th"] for r in out if not r["is_blocked"]}
    shut = sorted({r["province_th"] for r in out} - open_prov)  # ปิดครบทุกตำบล = ทั้งจังหวัดส่งไม่ได้
    log = [
        f"ตำบล {len(out):,} · อำเภอ {len({r['district_id'] for r in out}):,} · จังหวัด {len(provinces)} · รหัสไปรษณีย์ {len({r['zipcode'] for r in out}):,}",
        f"เขต 1 (กทม.+ปริมณฑล) {a1:,} ตำบล · เขต 2 (ต่างจังหวัด) {len(out) - a1:,} ตำบล",
        f"พื้นที่ส่งไม่ได้ {len({r['zipcode'] for r in out if r['is_blocked']})} รหัส · {sum(1 for r in out if r['is_blocked']):,} ตำบล"
        f" · ปิดทั้งจังหวัด: {', '.join(shut) or 'ไม่มี'}",
    ]
    if len(provinces) < 77:
        log.append(f"! ต้นทางมี {len(provinces)} จังหวัด ไม่ครบ 77 — เว็บเดิมตั้งใจตัด ยะลา/ปัตตานี/นราธิวาส ออก")
    return out, log


COLS = ("subdistrict_id", "zipcode", "subdistrict_th", "subdistrict_en", "district_id", "district_th",
        "district_en", "province_id", "province_th", "province_en", "area_id", "is_blocked")


def upsert_sbweb(rows: list[dict]) -> str:
    url = get_settings().sbweb_database_url
    if not url:
        raise SystemExit("! ไม่ได้ตั้ง SBWEB_DATABASE_URL ใน .env (ฐานเว็บ 10.9.11.111)")
    sql = f"INSERT INTO sb_thai_geo ({', '.join(COLS)}) VALUES ({', '.join(['%s'] * len(COLS))})"
    data = [tuple(int(r[c]) if c == "is_blocked" else r[c] for c in COLS) for r in rows]
    with create_engine(url, pool_pre_ping=True).connect() as c:
        raw = c.connection
        cur = raw.cursor()
        cur.execute("DELETE FROM sb_thai_geo")  # ข้อมูลอนุพันธ์ล้วน ล้างแล้วใส่ใหม่ทั้งชุด
        for i in range(0, len(data), CHUNK):
            cur.executemany(sql, data[i : i + CHUNK])
        raw.commit()
    return f"sb_thai_geo: {len(data):,} แถว"


def write_app(db: Session, rows: list[dict]) -> str:
    db.execute(delete(ThaiGeo))
    db.flush()
    db.bulk_save_objects([ThaiGeo(**r) for r in rows])
    db.commit()
    return f"thai_geo: {len(rows):,} แถว"


def main() -> int:
    ap = argparse.ArgumentParser(description="ดึงที่อยู่ไทยจาก Magento มาลงตารางของเรา")
    ap.add_argument("--report-only", action="store_true", help="ดูสรุปอย่างเดียว ไม่เขียนฐาน")
    ap.add_argument("--no-sbweb", action="store_true", help="ข้ามการเขียนฐานเว็บ ลงเฉพาะฐานแอป")
    args = ap.parse_args()

    rows, log = fetch()
    for line in log:
        print("  ", line)
    if args.report_only:
        print("\n(--report-only: ไม่ได้เขียนฐาน)")
        return 0
    if not args.no_sbweb:
        print("\n== ฐานเว็บ 10.9.11.111 ==")
        print("  ", upsert_sbweb(rows))
    print("\n== ฐานแอป ==")
    with SessionLocal() as db:
        print("  ", write_app(db, rows))
    print("\nเสร็จ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
