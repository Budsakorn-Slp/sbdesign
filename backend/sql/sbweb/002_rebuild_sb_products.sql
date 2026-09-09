-- ============================================================================
--  เลิกใช้แล้ว — ใช้ 009_rebuild_sb_products_v2.sql แทน (เก็บไฟล์นี้ไว้อ้างอิงเฉยๆ)
--
--  rebuild sb_products จาก mdm_products — รันซ้ำได้ทุกวัน
--  ทั้งหมดเกิดในเครื่องเดียวกัน ไม่มีข้อมูลวิ่งผ่าน network เลย
--
--  วิธี: สร้างตารางใหม่ข้างๆ → เติมให้เต็ม → RENAME สลับ (atomic)
--  ไม่ใช้ TRUNCATE+INSERT เพราะระหว่างนั้นเว็บจะเห็นสินค้า 0 ชิ้นเป็นนาที
--
--  แทนที่ :BATCH ด้วยรหัสรอบ เช่น 20260908-0300 ก่อนรัน
--  (ตัว runner ที่ backend/app/etl/rebuild_products.py ใส่ให้อัตโนมัติ)
-- ============================================================================

DROP TABLE IF EXISTS sb_products_new;
CREATE TABLE sb_products_new LIKE sb_products;

INSERT INTO sb_products_new (
  matnr, name_th,
  brand_code, brand_name, series_name, cat_code, cat_name, subcat_code, subcat_name,
  list_price, net_price, discount_pct,
  image_path, size_text, width_cm, length_cm, height_cm,
  spart, assem_code, needs_assembly, is_flatpack, is_luxury, assem_online,
  is_active, promo_info,
  short_desc, long_desc, search_text,
  batch_id, updated_at
)
SELECT
  m.MATNR,
  TRIM(m.MAKTX),

  NULLIF(TRIM(m.MVGR1N),''), NULLIF(TRIM(m.MVGR1T),''),
  NULLIF(TRIM(m.MVGR2T),''),
  NULLIF(TRIM(m.MVGR3N),''), NULLIF(TRIM(m.MVGR3T),''),
  NULLIF(TRIM(m.MVGR4N),''), NULLIF(TRIM(m.MVGR4T),''),

  NULLIF(m.PRICE, 0),
  m.NETPRICE,
  -- ส่วนลด % คิดจากราคาตั้งเทียบราคาขาย · ถ้าราคาตั้งไม่มากกว่าราคาขายก็ไม่ถือว่าลด
  CASE WHEN m.PRICE > m.NETPRICE AND m.PRICE > 0
       THEN ROUND((m.PRICE - m.NETPRICE) / m.PRICE * 100, 2) END,

  NULLIF(TRIM(m.PATH),''),
  -- GROES มีขยะปนมาเยอะ (เลขเดี่ยว "1" 1,086 ตัว · คำว่า "null" 208 ตัว) ถ้าโชว์ดิบจะขึ้น "ขนาด 49152"
  -- เก็บเฉพาะที่ดูเป็นขนาดจริง คือมีรูปแบบ เลขXเลข · และล้างช่องว่างที่แทรกมา ("100X100X 28")
  CASE WHEN REPLACE(m.GROES,' ','') REGEXP '[0-9]X[0-9]'
       THEN UPPER(REPLACE(m.GROES,' ','')) END,
  -- แยกตัวเลขเฉพาะที่ครบ 3 ส่วน "กว้างXยาวXสูง" · ที่เหลือ (เช่น "60X60") เก็บเป็นข้อความอย่างเดียว
  CASE WHEN REPLACE(m.GROES,' ','') REGEXP '^[0-9.]+X[0-9.]+X[0-9.]+$'
       THEN SUBSTRING_INDEX(REPLACE(m.GROES,' ',''),'X',1) + 0 END,
  CASE WHEN REPLACE(m.GROES,' ','') REGEXP '^[0-9.]+X[0-9.]+X[0-9.]+$'
       THEN SUBSTRING_INDEX(SUBSTRING_INDEX(REPLACE(m.GROES,' ',''),'X',2),'X',-1) + 0 END,
  CASE WHEN REPLACE(m.GROES,' ','') REGEXP '^[0-9.]+X[0-9.]+X[0-9.]+$'
       THEN SUBSTRING_INDEX(REPLACE(m.GROES,' ',''),'X',-1) + 0 END,

  NULLIF(TRIM(m.SPART_TEXT),''),
  NULLIF(TRIM(m.ASSEM),''),
  m.ASSEM        IS NOT NULL AND TRIM(m.ASSEM) <> '',
  m.FLATPACK     IS NOT NULL AND TRIM(m.FLATPACK) <> '',
  m.LUXURY       IS NOT NULL AND TRIM(m.LUXURY) <> '',
  m.ASSEM_ONLINE IS NOT NULL AND TRIM(m.ASSEM_ONLINE) <> '',

  a.MATNR IS NOT NULL,                          -- อยู่ใน mdm_products_active = ขายอยู่จริง
  NULLIF(TRIM(a.PROMO_INFO),''),

  NULLIF(TRIM(m.SHORTDESC),''),
  NULLIF(TRIM(m.LONGDESC),''),
  -- รวมไว้ช่องเดียวเพื่อ LIKE '%คำ%' ทีเดียวจบ ไม่ต้อง OR หลายคอลัมน์
  LEFT(CONCAT_WS(' ', m.MAKTX, m.MVGR1T, m.MVGR2T, m.MVGR3T, m.MVGR4T, m.MATNR), 600),

  ':BATCH', NOW()
FROM mdm_products m
-- ต้นทางแยกรายการที่ยังขายอยู่ไว้อีกตาราง — LEFT JOIN เพื่อ "ติดธง" ไม่ใช่ "กรองทิ้ง"
LEFT JOIN mdm_products_active a ON a.MATNR = m.MATNR
WHERE m.MATNR IS NOT NULL AND TRIM(m.MATNR) <> ''
  AND m.MAKTX  IS NOT NULL AND TRIM(m.MAKTX)  <> ''
  -- ขายออนไลน์ไม่ได้ถ้าไม่มีราคาหรือไม่มีรูป — ตัดทิ้งตั้งแต่ตรงนี้ ไม่ต้องไปกรองในแอป
  AND m.NETPRICE > 0
  AND m.PATH IS NOT NULL AND TRIM(m.PATH) <> '';

-- ---------------------------------------------------------------------------
--  รูปสินค้า — จาก mdm_products_media (sku = MATNR) ซึ่งเก็บ URL เต็มของเว็บจริง
--  ห้ามเดา URL เอง ชื่อไฟล์มี suffix ที่คาดเดาไม่ได้ (19144682-1_23.jpg)
--  กรอง image_file ให้มี MATNR อยู่ในชื่อ เพราะ Magento แปะ banner ร่วมไว้ในนี้ด้วย
--  (ship_special.jpg ติดมา 20,337 แถว · flat-pack2.jpg อีก 2,519)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS sb_media_first;
CREATE TABLE sb_media_first (
  sku         VARCHAR(50)  NOT NULL PRIMARY KEY,
  image_url   VARCHAR(500) NOT NULL,
  image_count INT          NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO sb_media_first (sku, image_url, image_count)
SELECT g.sku, MIN(m.image_url), g.n
FROM (
  SELECT sku, MIN(IFNULL(image_position, 999)) AS mp, COUNT(*) AS n
  FROM mdm_products_media
  WHERE media_type = 'image'
    AND IFNULL(image_disabled, 0) = 0
    AND image_url IS NOT NULL AND TRIM(image_url) <> ''
    AND image_file LIKE CONCAT('%', sku, '%')
  GROUP BY sku
) g
JOIN mdm_products_media m
  ON  m.sku = g.sku
  AND IFNULL(m.image_position, 999) = g.mp
  AND m.media_type = 'image'
  AND IFNULL(m.image_disabled, 0) = 0
  AND m.image_file LIKE CONCAT('%', m.sku, '%')
GROUP BY g.sku, g.n;

UPDATE sb_products_new p
JOIN sb_media_first f ON f.sku = p.matnr
SET p.image_url = f.image_url, p.image_count = f.image_count;

DROP TABLE sb_media_first;

-- sb_products_image (ดึงตรงจาก Magento) ทับทีหลัง เพราะสดกว่า mdm_products_media
-- ตารางว่างอยู่ = UPDATE ไม่โดนแถวไหน rebuild ก็ยังใช้ mdm_products_media ต่อได้ตามเดิม
DROP TABLE IF EXISTS sb_media_first;
CREATE TABLE sb_media_first (
  sku         VARCHAR(50)  NOT NULL PRIMARY KEY,
  image_url   VARCHAR(500) NOT NULL,
  image_count INT          NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- banner ที่ Magento แปะร่วมทุกสินค้า (ship_special.jpg, flat-pack2.jpg ฯลฯ)
-- ตัดด้วย "ไฟล์เดียวถูกใช้เกิน 50 สินค้า" ไม่ใช่ "ชื่อไฟล์ต้องมี MATNR"
-- เพราะรูปสินค้าจริงบางใบตั้งชื่อเป็นตัวเลขล้วน (1777447346400.jpg) จะโดนตัดทิ้งไปด้วย
-- เกณฑ์นี้ดูแลตัวเองได้ ถ้าวันหลังมี banner ใหม่ก็โดนตัดเองโดยไม่ต้องมาแก้ list
DROP TABLE IF EXISTS sb_media_banner;
CREATE TABLE sb_media_banner (
  image_file VARCHAR(255) NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO sb_media_banner (image_file)
SELECT image_file FROM sb_products_image
WHERE image_file IS NOT NULL
GROUP BY image_file HAVING COUNT(DISTINCT sku) > 50;

INSERT INTO sb_media_first (sku, image_url, image_count)
SELECT g.sku, MIN(i.image_url), g.n
FROM (
  SELECT i.sku, MIN(i.image_position) AS mp, COUNT(*) AS n
  FROM sb_products_image i
  LEFT JOIN sb_media_banner b ON b.image_file = i.image_file
  WHERE i.media_type = 'image'
    AND i.image_disabled = 0
    AND i.image_url IS NOT NULL AND TRIM(i.image_url) <> ''
    AND b.image_file IS NULL
  GROUP BY i.sku
) g
JOIN sb_products_image i
  ON  i.sku = g.sku
  AND i.image_position = g.mp
  AND i.media_type = 'image'
  AND i.image_disabled = 0
LEFT JOIN sb_media_banner b2 ON b2.image_file = i.image_file
WHERE b2.image_file IS NULL
GROUP BY g.sku, g.n;

DROP TABLE sb_media_banner;

UPDATE sb_products_new p
JOIN sb_media_first f ON f.sku = p.matnr
SET p.image_url = f.image_url, p.image_count = f.image_count;

DROP TABLE sb_media_first;

-- สลับตาราง — MariaDB ทำ RENAME หลายตัวใน statement เดียวแบบ atomic
-- เว็บจะไม่มีวินาทีไหนที่มองไม่เห็นตาราง
DROP TABLE IF EXISTS sb_products_old;
RENAME TABLE sb_products     TO sb_products_old,
             sb_products_new TO sb_products;
DROP TABLE sb_products_old;
