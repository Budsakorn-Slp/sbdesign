-- ============================================================================
--  เลิกใช้แล้ว — ใช้ 011_rebuild_sb_products_v3.sql แทน (เก็บไฟล์นี้ไว้อ้างอิงเฉยๆ)
--  rebuild sb_products v2 — รันซ้ำได้ทุกคืน (แทนที่ 002 ซึ่งเลิกใช้แล้ว)
--  ทุกตารางอยู่เครื่องเดียวกัน ไม่มีข้อมูลวิ่งผ่าน network
--
--  วิธี: สร้างตารางใหม่ข้างๆ → เติมให้เต็ม → RENAME สลับ (atomic)
--  แทนที่ :BATCH ด้วยรหัสรอบ เช่น 20260908-0300 ก่อนรัน
--  (backend/app/etl/rebuild_products.py ใส่ให้อัตโนมัติ)
--
--  ต่างจาก 002 ตรงไหน
--   1) เอาเงื่อนไข NETPRICE>0 / PATH<>'' ออกจาก WHERE
--      ของเดิมตัดตั้งแต่ต้นทาง 199,742 → 120,842 แถว ทำให้สินค้า active หายไป 106 ตัว
--      และของที่มีรูปบนเว็บจริง 5,116 sku หลุดเพราะยังไม่ตั้งราคาใน MDM
--      v2 เก็บทุกแถวไว้ค้นได้ แล้วใช้ธง is_public ตัดสินว่าลูกค้าเห็นตัวไหน
--   2) display_name — ชื่อที่คนอ่านรู้เรื่อง ไล่หาจากแหล่งที่คลีนแล้วตามลำดับ
--   3) เพิ่ม สี/สไตล์/ธงการตลาด จากตารางที่มีอยู่แล้วแต่ไม่เคยถูกดึงมาใช้
-- ============================================================================

DROP TABLE IF EXISTS sb_products_new;
CREATE TABLE sb_products_new LIKE sb_products;

-- ---------------------------------------------------------------------------
--  ชื่อจากเว็บจริง (Magento) — sb_products_image เก็บ product_name ติดมาด้วย
--  1 sku มีหลายรูป จึงต้องยุบให้เหลือแถวเดียวก่อน ไม่งั้น JOIN แล้วแถวบาน
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS sb_web_name;
CREATE TABLE sb_web_name (
  sku          VARCHAR(50)  NOT NULL PRIMARY KEY,
  product_name VARCHAR(255) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO sb_web_name (sku, product_name)
SELECT sku, NULLIF(TRIM(MAX(product_name)), '')
FROM sb_products_image
GROUP BY sku;

-- ---------------------------------------------------------------------------
--  สี/สไตล์ — mdm_products_color กับ _style "ไม่มี index เลยสักตัว" (ของทีมอื่น เราไม่ไปแตะ)
--  ถ้า LEFT JOIN ตรงๆ MariaDB จะไล่สแกนทั้งตารางให้ทุกแถวของ 199,742 แถว = ค้างข้ามคืน
--  (ลองแล้ว รัน 21 นาทียังไม่ขยับ) จึงคัดลอกมาไว้ในตารางของเราที่มี PK ก่อน แล้วค่อย join
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS sb_color_map;
CREATE TABLE sb_color_map (
  sku      VARCHAR(50)  NOT NULL PRIMARY KEY,
  color_th VARCHAR(100) NULL,
  color_en VARCHAR(100) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO sb_color_map (sku, color_th, color_en)
SELECT sku, NULLIF(TRIM(MAX(color_th)),''), NULLIF(TRIM(MAX(color_en)),'')
FROM mdm_products_color
WHERE sku IS NOT NULL AND TRIM(sku) <> ''
GROUP BY sku;

DROP TABLE IF EXISTS sb_style_map;
CREATE TABLE sb_style_map (
  sku      VARCHAR(50)  NOT NULL PRIMARY KEY,
  style_th VARCHAR(100) NULL,
  style_en VARCHAR(100) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO sb_style_map (sku, style_th, style_en)
SELECT sku, NULLIF(TRIM(MAX(style_th)),''), NULLIF(TRIM(MAX(style_en)),'')
FROM mdm_products_style
WHERE sku IS NOT NULL AND TRIM(sku) <> ''
GROUP BY sku;

INSERT INTO sb_products_new (
  matnr, name_th, display_name, name_source,
  brand_code, brand_name, series_name, cat_code, cat_name, subcat_code, subcat_name,
  color_th, color_en, style_th, style_en,
  list_price, net_price, discount_pct,
  image_path, size_text, width_cm, length_cm, height_cm,
  spart, assem_code, needs_assembly, is_flatpack, is_luxury, assem_online,
  is_hot, is_new_collection, is_special_deal, free_delivery,
  is_active, has_web, is_public, promo_info,
  short_desc, long_desc, search_text,
  batch_id, updated_at
)
SELECT
  m.MATNR,
  TRIM(m.MAKTX),                                -- ชื่อดิบ เซลล์ค้นตามที่พิมพ์กันมาแต่เดิม

  -- ชื่อโชว์ลูกค้า ไล่จากแหล่งที่คลีนที่สุดลงมา
  --   1 เว็บจริง (Magento)   "ชั้นวางทีวี ขนาด 90 ซม. รุ่น Urbani"
  --   2 maison / disney      ตารางที่ทีมคลีนชื่อไว้เองแล้ว
  --   3 mdm_products_extend.SHORTDESC  ชื่อชุดเดียวกับเว็บ แต่มีบางตัวที่เว็บไม่มี
  --   4 สุดท้ายจริงๆ ค่อยใช้ MAKTX ที่ล้าง / ออกให้พออ่านได้
  COALESCE(
    w.product_name,
    NULLIF(TRIM(mai.PRODUCT_NAME), ''),
    NULLIF(TRIM(dis.PRODUCT_NAME), ''),
    NULLIF(TRIM(e.SHORTDESC), ''),
    NULLIF(TRIM(REPLACE(REPLACE(REPLACE(REPLACE(m.MAKTX,'/',' '),'  ',' '),'  ',' '),'  ',' ')), '')
  ),
  CASE
    WHEN w.product_name IS NOT NULL              THEN 'magento'
    WHEN NULLIF(TRIM(mai.PRODUCT_NAME),'') IS NOT NULL THEN 'maison'
    WHEN NULLIF(TRIM(dis.PRODUCT_NAME),'') IS NOT NULL THEN 'disney'
    WHEN NULLIF(TRIM(e.SHORTDESC),'')      IS NOT NULL THEN 'extend'
    ELSE 'maktx'
  END,

  NULLIF(TRIM(m.MVGR1N),''), NULLIF(TRIM(m.MVGR1T),''),
  NULLIF(TRIM(m.MVGR2T),''),
  NULLIF(TRIM(m.MVGR3N),''), NULLIF(TRIM(m.MVGR3T),''),
  NULLIF(TRIM(m.MVGR4N),''), NULLIF(TRIM(m.MVGR4T),''),

  -- สี/สไตล์ — mdm_products_color / _style มี sku ละแถวเดียว (เช็คแล้ว) JOIN ตรงได้
  COALESCE(NULLIF(TRIM(col.color_th),''), NULLIF(TRIM(mai.COLOR_TH),''), NULLIF(TRIM(dis.COLOR_TH),'')),
  COALESCE(NULLIF(TRIM(col.color_en),''), NULLIF(TRIM(dis.COLOR_NAME),'')),
  COALESCE(NULLIF(TRIM(st.style_th),''),  NULLIF(TRIM(dis.STYLE_TH),'')),
  NULLIF(TRIM(st.style_en),''),

  NULLIF(m.PRICE, 0),
  NULLIF(m.NETPRICE, 0),
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

  -- ธงการตลาดเก็บเป็น varchar(3) ค่าที่ใช้จริงคือ 'Y'/ว่าง — เช็คแบบไม่ว่างพอ
  TRIM(IFNULL(e.HOTITEM,''))       <> '',
  TRIM(IFNULL(e.NEWCOLLECTION,'')) <> '',
  TRIM(IFNULL(e.SPECIALDEAL,''))   <> '',
  TRIM(IFNULL(e.FREEDELIVERY,''))  <> '',

  a.MATNR IS NOT NULL,                          -- อยู่ใน mdm_products_active = ขายอยู่จริง
  w.sku   IS NOT NULL,                          -- มีหน้าอยู่บนเว็บจริง
  0,                                            -- is_public คิดทีหลัง ตอนนั้นรูปถึงจะเติมเสร็จ
  NULLIF(TRIM(a.PROMO_INFO),''),

  COALESCE(NULLIF(TRIM(m.SHORTDESC),''), NULLIF(TRIM(e.SHORTDESC),'')),
  COALESCE(NULLIF(TRIM(m.LONGDESC),''),  NULLIF(TRIM(e.LONGDESC),'')),
  -- รวมไว้ช่องเดียวเพื่อ LIKE '%คำ%' ทีเดียวจบ ไม่ต้อง OR หลายคอลัมน์
  -- ใส่ทั้งชื่อโชว์และชื่อดิบ ลูกค้าค้นด้วยชื่อเว็บ เซลล์ค้นด้วยรหัสรุ่น เจอเหมือนกัน
  LEFT(CONCAT_WS(' ',
    COALESCE(w.product_name, NULLIF(TRIM(mai.PRODUCT_NAME),''), NULLIF(TRIM(dis.PRODUCT_NAME),''),
             NULLIF(TRIM(e.SHORTDESC),'')),
    m.MAKTX, m.MVGR1T, m.MVGR2T, m.MVGR3T, m.MVGR4T,
    col.color_th, st.style_th, m.MATNR), 800),

  ':BATCH', NOW()
FROM mdm_products m
-- ต้นทางแยกรายการที่ยังขายอยู่ไว้อีกตาราง — LEFT JOIN เพื่อ "ติดธง" ไม่ใช่ "กรองทิ้ง"
LEFT JOIN mdm_products_active a   ON a.MATNR   = m.MATNR
LEFT JOIN mdm_products_extend e   ON e.MATNR   = m.MATNR
LEFT JOIN sb_color_map        col ON col.sku   = m.MATNR
LEFT JOIN sb_style_map        st  ON st.sku    = m.MATNR
LEFT JOIN sb_web_name         w   ON w.sku     = m.MATNR
LEFT JOIN maison_products     mai ON mai.MATNR = m.MATNR
LEFT JOIN disneyhome_products dis ON dis.MATNR = m.MATNR
WHERE m.MATNR IS NOT NULL AND TRIM(m.MATNR) <> ''
  AND m.MAKTX IS NOT NULL AND TRIM(m.MAKTX) <> '';

DROP TABLE sb_web_name;
DROP TABLE sb_color_map;
DROP TABLE sb_style_map;

-- ---------------------------------------------------------------------------
--  ขนาด — ถ้า GROES ของ MDM ใช้ไม่ได้ ลองหยิบจาก maison/disney ที่คลีนไว้แล้ว
-- ---------------------------------------------------------------------------
UPDATE sb_products_new p
JOIN maison_products mai ON mai.MATNR = p.matnr
SET p.width_cm  = COALESCE(p.width_cm,  NULLIF(mai.WIDTH, 0)),
    p.length_cm = COALESCE(p.length_cm, NULLIF(mai.LEGHT, 0)),
    p.height_cm = COALESCE(p.height_cm, NULLIF(mai.HEGHT, 0))
WHERE p.width_cm IS NULL OR p.length_cm IS NULL OR p.height_cm IS NULL;

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
-- วัดแล้วเกณฑ์นี้โดน 3 ไฟล์ และทำให้เหลือ sku ที่ไม่มีรูปเลยแค่ 6 ตัว
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

-- ---------------------------------------------------------------------------
--  ชื่อไทย — บนเว็บจริงมีของที่คนกรอกเป็นอังกฤษล้วนอยู่ ~1,900 ตัว
--  ("Chairs Zeal Black") ทั้งที่ตัวข้างๆ กันเป็นไทย ("โต๊ะกลาง รุ่น Adorn สีขาว")
--  ไม่ได้แปล — ประกอบจากช่องที่เป็นไทยอยู่แล้วในฐาน ตามรูปแบบเดียวกับที่เว็บใช้:
--      <หมวดย่อย> รุ่น <ซีรีส์> สี<สี>   →  "เก้าอี้ไม้เบาะหนัง รุ่น Zeal สีดำ"
--  ชื่ออังกฤษเดิมย้ายไปอยู่ name_en ไม่ได้หายไปไหน · search_text ถูกสร้างไว้ก่อนหน้านี้แล้ว
--  จึงยังมีชื่ออังกฤษอยู่ ค้นด้วย "Zeal" หรือ "Chairs" ก็ยังเจอเหมือนเดิม
--  ทำไม่ได้ = ไม่มีทั้งหมวดย่อยและหมวดหลักเป็นไทย (~50 ตัว) ปล่อยชื่ออังกฤษไว้อย่างเดิม
-- ---------------------------------------------------------------------------
UPDATE sb_products_new
SET
  name_en = display_name,
  display_name = CONCAT(
    -- "โต๊ะอาหารสั่งทำ-I" → "โต๊ะอาหารสั่งทำ" (ท้ายชื่อเป็นรหัสกลุ่มของฝ่ายจัดหมวด ลูกค้าไม่ต้องเห็น)
    TRIM(TRAILING '-I' FROM TRIM(COALESCE(NULLIF(TRIM(subcat_name),''), TRIM(cat_name)))),
    -- ซีรีส์ที่หน้าตาเป็นรหัส ("KC-GO") ข้ามไป เอาเฉพาะที่เป็นชื่อรุ่นจริง
    CASE WHEN series_name IS NULL OR TRIM(series_name) = '' OR series_name LIKE '%-%' THEN ''
         ELSE CONCAT(' รุ่น ', TRIM(series_name)) END,
    -- "หลากสี" ไม่ได้บอกอะไร · บางค่ามีคำว่า "สี" นำอยู่แล้ว ("สีไม้อ่อน") จะได้ไม่เป็น "สีสีไม้อ่อน"
    CASE WHEN color_th IS NULL OR TRIM(color_th) = '' OR TRIM(color_th) = 'หลากสี' THEN ''
         WHEN TRIM(color_th) LIKE 'สี%' THEN CONCAT(' ', TRIM(color_th))
         ELSE CONCAT(' สี', TRIM(color_th)) END
  ),
  name_source = 'compose'
WHERE display_name IS NOT NULL
  AND display_name NOT REGEXP '[ก-๙]'
  AND name_source <> 'maktx'
  AND COALESCE(NULLIF(TRIM(subcat_name),''), NULLIF(TRIM(cat_name),'')) REGEXP '[ก-๙]';

-- ---------------------------------------------------------------------------
--  is_public — "ข้อมูลครบพอโชว์ลูกค้าไหม" ตัดสินที่นี่ที่เดียว
--  แอปแค่เช็ค is_public = 1 ไม่ต้องรู้เงื่อนไข ถ้าวันหลังเกณฑ์เปลี่ยนก็แก้บรรทัดนี้บรรทัดเดียว
--    ยังขายอยู่ + มีรูปจริง + มีราคา + มีชื่อที่คนอ่านรู้เรื่อง (ไม่ใช่ MAKTX ดิบ)
-- ---------------------------------------------------------------------------
UPDATE sb_products_new
SET is_public = (
      is_active = 1
  AND image_url IS NOT NULL
  AND net_price > 0
  AND display_name IS NOT NULL
  AND name_source <> 'maktx'
);

-- สลับตาราง — MariaDB ทำ RENAME หลายตัวใน statement เดียวแบบ atomic
-- เว็บจะไม่มีวินาทีไหนที่มองไม่เห็นตาราง
DROP TABLE IF EXISTS sb_products_old;
RENAME TABLE sb_products     TO sb_products_old,
             sb_products_new TO sb_products;
DROP TABLE sb_products_old;

-- RENAME ทำให้วิวชี้ตารางใหม่เองอยู่แล้ว (วิวผูกด้วยชื่อ ไม่ใช่ id)
-- สร้างซ้ำไว้เผื่อกรณีตารางถูกสร้างใหม่โดยไม่ผ่าน 008
CREATE OR REPLACE VIEW sb_products_public AS
SELECT * FROM sb_products WHERE is_public = 1;
