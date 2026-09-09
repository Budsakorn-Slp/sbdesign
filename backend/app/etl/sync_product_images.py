"""ดึงรูปสินค้าจาก Magento (10.9.12.67) มาลง sb_products_image บนฐานเว็บ (10.9.11.111)

    python -m app.etl.sync_product_images              # ทั้งหมด
    python -m app.etl.sync_product_images --sku 19144682   # ทดสอบตัวเดียว
    python -m app.etl.sync_product_images --limit 500  # ลองน้อยๆ ก่อน
    python -m app.etl.sync_product_images --prune      # ลบรูปที่ Magento ถอดออกแล้วด้วย

ต่อยอดจากสคริปต์ maison_product_image เดิม ต่างกัน 3 จุด:

  1. ไม่กรองแบรนด์ — ของเดิม INNER JOIN eav_attribute_option_value ... LIKE '%MAISON%CO%'
     ทำให้ได้เฉพาะแบรนด์เดียว ตรงนี้เอาทุกแบรนด์
  2. upsert เป็นชุด ไม่ใช่ทีละแถว — ของเดิมยิง SELECT + INSERT/UPDATE 3 รอบต่อแถว
     3,670 แถวยังไหว แต่ของเราหลักแสน จะกลายเป็นครึ่งล้าน query
     เปลี่ยนเป็น INSERT ... ON DUPLICATE KEY UPDATE ทีละ 1,000 แถว
  3. ธง is_manual / position_locked ทำงานได้จริง — ตารางเดิมไม่มีสองคอลัมน์นี้
     ทั้งที่ UPDATE อ้างถึง (ดู 005_sb_products_image.sql)
"""

from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import create_engine, text

from app.core.config import get_settings

for _s in (sys.stdout, sys.stderr):
    if getattr(_s, "encoding", "") and _s.encoding.lower() not in ("utf-8", "utf8"):
        _s.reconfigure(encoding="utf-8", errors="replace")

MEDIA_BASE = "https://sbdesignsquare.com/media/catalog/product"
CHUNK = 1000

# entity_type_id 4 = catalog_product · attribute_id 565 = image (รูปหลัก ไม่ได้อยู่ใน gallery)
FETCH_SQL = f"""
-- DISTINCT: join ชั้น gallery กับ attribute image ทำให้แถวซ้ำ 5 เท่า
-- (1,020,447 แถว ทั้งที่ของจริง 189,675) PK ยุบให้อยู่แล้วแต่เสียเวลาเขียนเปล่า
SELECT DISTINCT
    cpe.entity_id,
    cpe.sku,
    cpev_name.value AS product_name,
    COALESCE(val.value_id, 0) AS value_id,
    COALESCE(gal.value, cpev_img.value) AS image_file,
    CASE WHEN gal.value IS NOT NULL
         THEN CONCAT('{MEDIA_BASE}', gal.value)
         ELSE CONCAT('{MEDIA_BASE}', cpev_img.value) END AS image_url,
    val.label AS image_label,
    -- รูปหลักจาก attribute ไม่มีลำดับของตัวเอง ให้ -1 เพื่อให้มาก่อน gallery เสมอ
    CASE WHEN gal.value IS NOT NULL THEN COALESCE(val.position, 100) ELSE -1 END AS image_position,
    val.disabled AS image_disabled,
    gal.media_type,
    vid.url AS video_url
FROM catalog_product_entity cpe
LEFT JOIN catalog_product_entity_varchar cpev_name
       ON cpe.entity_id = cpev_name.entity_id
      AND cpev_name.attribute_id = (SELECT attribute_id FROM eav_attribute
                                     WHERE attribute_code = 'name' AND entity_type_id = 4 LIMIT 1)
      AND cpev_name.store_id = 0
LEFT JOIN catalog_product_entity_media_gallery_value_to_entity mgve
       ON cpe.entity_id = mgve.entity_id
LEFT JOIN catalog_product_entity_media_gallery gal
       ON mgve.value_id = gal.value_id
      AND gal.media_type IN ('image', 'external-video')
      AND gal.disabled = 0
LEFT JOIN catalog_product_entity_media_gallery_value val
       ON gal.value_id = val.value_id
      AND val.store_id = 0
      AND val.disabled = 0
LEFT JOIN catalog_product_entity_varchar cpev_img
       ON cpe.entity_id = cpev_img.entity_id
      AND cpev_img.store_id = 0
      AND cpev_img.attribute_id = 565
      AND cpev_img.value IS NOT NULL
      AND cpev_img.value != 'no_selection'
      AND cpev_img.value != ''
LEFT JOIN catalog_product_entity_media_gallery_value_video vid
       ON gal.value_id = vid.value_id
WHERE (gal.value IS NOT NULL OR cpev_img.value IS NOT NULL)
"""

# is_manual / position_locked ที่อ้างถึงใน SET คือค่าของแถวเดิมในตาราง ไม่ใช่ค่าที่กำลังจะใส่
# (MariaDB อ่านคอลัมน์เปล่าใน ON DUPLICATE KEY UPDATE เป็นค่าปัจจุบัน) — ธงจึงกันทับได้จริง
UPSERT_SQL = """
INSERT INTO sb_products_image
  (entity_id, value_id, sku, product_name, image_file, image_url,
   image_label, image_position, image_disabled, media_type, video_url)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  sku            = IF(is_manual = 1, sku,            VALUES(sku)),
  product_name   = IF(is_manual = 1, product_name,   VALUES(product_name)),
  image_file     = IF(is_manual = 1, image_file,     VALUES(image_file)),
  image_url      = IF(is_manual = 1, image_url,      VALUES(image_url)),
  image_label    = IF(is_manual = 1, image_label,    VALUES(image_label)),
  image_position = IF(is_manual = 1 OR position_locked = 1, image_position, VALUES(image_position)),
  image_disabled = IF(is_manual = 1, image_disabled, VALUES(image_disabled)),
  media_type     = IF(is_manual = 1, media_type,     VALUES(media_type)),
  video_url      = IF(is_manual = 1, video_url,      VALUES(video_url))
"""


def fetch_from_magento(sku: str | None, limit: int | None) -> list[tuple]:
    url = get_settings().magento_url
    if not url:
        raise SystemExit("! ไม่ได้ตั้ง MAGENTO_HOST/USER/PASSWORD ใน .env (ฐาน Magento บน 10.9.12.67)")
    sql = FETCH_SQL
    params: dict = {}
    if sku:
        sql += " AND cpe.sku = :sku"
        params["sku"] = sku
    sql += " ORDER BY cpe.entity_id, val.position, val.value_id"
    if limit:
        sql += f" LIMIT {int(limit)}"

    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as c:
        rows = c.execute(text(sql), params).fetchall()

    out = []
    for r in rows:
        m = r._mapping
        out.append(
            (
                str(m["entity_id"]),
                str(m["value_id"]),
                (m["sku"] or None),
                (m["product_name"] or None),
                (m["image_file"] or None),
                (m["image_url"] or None),
                (m["image_label"] or None),
                int(m["image_position"] if m["image_position"] is not None else 100),
                int(m["image_disabled"] or 0),
                (m["media_type"] or None),
                (m["video_url"] or None),
            )
        )
    return out


def upsert(rows: list[tuple], prune: bool) -> tuple[int, int]:
    eng = create_engine(get_settings().sbweb_database_url, pool_pre_ping=True)
    written = pruned = 0
    with eng.connect() as c:
        raw = c.connection
        cur = raw.cursor()
        for i in range(0, len(rows), CHUNK):
            cur.executemany(UPSERT_SQL, rows[i : i + CHUNK])
            raw.commit()
            written += len(rows[i : i + CHUNK])
            print(f"  {written:,}/{len(rows):,}")

        if prune:
            # เทียบด้วยตารางชั่วคราวแทน NOT IN (...) เพราะ key มีเป็นแสน
            # แตะเฉพาะแถวที่ is_manual = 0 — ที่คนแก้มือไว้ไม่ลบ
            cur.execute("DROP TEMPORARY TABLE IF EXISTS sb_img_seen")
            cur.execute(
                "CREATE TEMPORARY TABLE sb_img_seen ("
                "entity_id VARCHAR(20) NOT NULL, value_id VARCHAR(20) NOT NULL,"
                "PRIMARY KEY (entity_id, value_id)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci"
            )
            keys = [(r[0], r[1]) for r in rows]
            for i in range(0, len(keys), CHUNK):
                cur.executemany(
                    "INSERT IGNORE INTO sb_img_seen (entity_id, value_id) VALUES (%s, %s)",
                    keys[i : i + CHUNK],
                )
            cur.execute(
                "DELETE p FROM sb_products_image p "
                "LEFT JOIN sb_img_seen s ON s.entity_id = p.entity_id AND s.value_id = p.value_id "
                "WHERE s.entity_id IS NULL AND p.is_manual = 0"
            )
            pruned = cur.rowcount or 0
            cur.execute("DROP TEMPORARY TABLE sb_img_seen")
            raw.commit()
    return written, pruned


def main() -> int:
    ap = argparse.ArgumentParser(description="sync รูปสินค้า Magento -> sb_products_image")
    ap.add_argument("--sku", default=None, help="ทำ MATNR เดียว ใช้ทดสอบ")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--prune", action="store_true", help="ลบรูปที่ Magento ถอดออกแล้ว (ไม่แตะ is_manual=1)")
    args = ap.parse_args()

    if args.prune and (args.sku or args.limit):
        raise SystemExit("! --prune ใช้กับ --sku/--limit ไม่ได้ จะลบรูปที่ไม่ได้ดึงมารอบนี้ทิ้งหมด")

    t0 = time.time()
    print("อ่านจาก Magento ...")
    rows = fetch_from_magento(args.sku, args.limit)
    print(f"  ได้ {len(rows):,} แถว ({time.time() - t0:.0f}s)")
    if not rows:
        print("! ไม่มีข้อมูล")
        return 1

    written, pruned = upsert(rows, args.prune)
    skus = len({r[2] for r in rows if r[2]})
    print(f"เสร็จ: เขียน {written:,} แถว · สินค้า {skus:,} รายการ" + (f" · ลบ {pruned:,}" if args.prune else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
