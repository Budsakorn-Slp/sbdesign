-- ============================================================================
--  เลิกใช้แล้ว — ใช้ 010_sb_products_v3.sql แทน (เก็บไฟล์นี้ไว้อ้างอิงเฉยๆ)
--  sb_products v2 — สร้างตารางสินค้าใหม่ทั้งใบ (แทนของเดิมจาก 001)
--  รันครั้งเดียว:  mysql -h 10.9.11.111 -P 3307 -u dba -p web < 008_sb_products_v2.sql
--
--  ทำไมต้องสร้างใหม่ ไม่ ALTER:
--    ของเดิมเก็บ name_th = MAKTX ดิบ ("โต๊ะกลาง/SALON2/โครงไม้/เวงเก้") ซึ่งเป็นรหัสของ
--    ฝ่ายผลิต ไม่ใช่ชื่อที่ลูกค้าอ่านรู้เรื่อง · และไม่มีช่องเก็บสี/สไตล์/ชื่อเว็บเลย
--    ตารางถูก rebuild ทั้งใบทุกคืนอยู่แล้ว (ไม่มีใครเขียนมือ) สร้างใหม่จึงไม่เสียข้อมูล
--
--  แนวคิดหลัก — "เก็บทุกตัว แต่โชว์เฉพาะตัวที่ข้อมูลครบ"
--    is_active = 1  → ต้นทางบอกว่ายังขายอยู่ (~25,200)  ใช้ให้แอดมิน/เซลล์ค้น+เช็คสต็อก
--    is_public = 1  → ข้อมูลครบพอโชว์ลูกค้า (active + มีรูป + มีราคา)
--  ลูกค้าเห็นเฉพาะ is_public = 1 · เซลล์/แอดมินเห็นทั้งหมด
--
--  ตารางเดิม sb_products ถูก DROP ในไฟล์นี้ (ตารางของโปรเจกต์นี้เอง ไม่มีระบบอื่นอ่าน)
--  ไม่มี DROP/ALTER ตารางของเว็บเดิมแม้แต่บรรทัดเดียว
-- ============================================================================

DROP TABLE IF EXISTS sb_products;

CREATE TABLE sb_products (
  matnr        VARCHAR(50)  NOT NULL PRIMARY KEY,

  -- ---- ชื่อ ----------------------------------------------------------------
  -- name_th   = MAKTX ดิบ · เซลล์ใช้ค้นตามที่พิมพ์กันมาแต่เดิม ห้ามทิ้ง
  -- display_name = ชื่อที่ลูกค้าเห็น มาจากเว็บจริงก่อน ถ้าไม่มีค่อยไล่ลงไปตาม name_source
  -- name_en   = ชื่ออังกฤษเดิมของเว็บ เก็บไว้ตอนที่เราประกอบชื่อไทยทับ (ค้นด้วยชื่ออังกฤษยังเจอ)
  name_th      VARCHAR(255) NOT NULL,
  display_name VARCHAR(255) NULL,
  name_en      VARCHAR(255) NULL,
  name_source  VARCHAR(10)  NULL,               -- magento | maison | disney | extend | compose | maktx

  brand_code   VARCHAR(20)  NULL,               -- MVGR1N
  brand_name   VARCHAR(200) NULL,               -- MVGR1T
  series_name  VARCHAR(200) NULL,               -- MVGR2T ซีรีส์/คอลเลกชัน
  cat_code     VARCHAR(100) NULL,               -- MVGR3N หมวดหลัก
  cat_name     VARCHAR(200) NULL,
  subcat_code  VARCHAR(100) NULL,               -- MVGR4N หมวดย่อย
  subcat_name  VARCHAR(200) NULL,

  -- ---- สี / สไตล์ (ของใหม่) — จาก mdm_products_color / mdm_products_style ----
  color_th     VARCHAR(100) NULL,
  color_en     VARCHAR(100) NULL,
  style_th     VARCHAR(100) NULL,
  style_en     VARCHAR(100) NULL,

  list_price   DECIMAL(12,2) NULL,              -- PRICE ราคาตั้ง (ไว้ขีดฆ่า)
  net_price    DECIMAL(12,2) NULL,              -- NETPRICE ราคาขายจริง
  discount_pct DECIMAL(5,2)  NULL,

  image_path   VARCHAR(765) NULL,               -- PATH ของ MDM — path เครื่องภายใน เปิดจากเน็ตไม่ได้
  image_url    VARCHAR(500) NULL,               -- URL จริงบนเว็บ
  image_count  INT          NOT NULL DEFAULT 0,

  -- ขนาดจริงอยู่ใน GROES ("150X79X80") — WIDTH/LEGHT/HEGHT ของต้นทางว่างเกือบทั้งตาราง
  size_text    VARCHAR(96)  NULL,
  width_cm     DECIMAL(8,1) NULL,
  length_cm    DECIMAL(8,1) NULL,
  height_cm    DECIMAL(8,1) NULL,

  spart        VARCHAR(8)   NULL,               -- MER / KD / BI / Consign
  assem_code   VARCHAR(8)   NULL,               -- ASSEM = P/MP/L (เก็บรหัสดิบไว้ด้วย)
  needs_assembly TINYINT(1) NOT NULL DEFAULT 0,
  is_flatpack    TINYINT(1) NOT NULL DEFAULT 0,
  is_luxury      TINYINT(1) NOT NULL DEFAULT 0,
  assem_online   TINYINT(1) NOT NULL DEFAULT 0,

  -- ---- ธงการตลาดจาก mdm_products_extend (ของใหม่) --------------------------
  -- หมายเหตุ: รอบแรกที่รัน (8 ก.ย. 69) ต้นทางยังเป็นค่าว่างทั้ง 46,470 แถว ได้ 0 ทุกช่อง
  -- เก็บช่องไว้ก่อน วันไหนฝ่ายการตลาดเริ่มติ๊กใน MDM ก็ไหลเข้ามาเองโดยไม่ต้องแก้อะไร
  is_hot           TINYINT(1) NOT NULL DEFAULT 0,   -- HOTITEM
  is_new_collection TINYINT(1) NOT NULL DEFAULT 0,  -- NEWCOLLECTION
  is_special_deal  TINYINT(1) NOT NULL DEFAULT 0,   -- SPECIALDEAL
  free_delivery    TINYINT(1) NOT NULL DEFAULT 0,   -- FREEDELIVERY

  -- ---- สถานะ ---------------------------------------------------------------
  is_active    TINYINT(1) NOT NULL DEFAULT 0,   -- อยู่ใน mdm_products_active
  has_web      TINYINT(1) NOT NULL DEFAULT 0,   -- มีหน้าอยู่บน sbdesignsquare.com จริง
  -- ครบพอให้ลูกค้าเห็นไหม — คิดตอน rebuild ที่เดียว แอปไม่ต้องเดาเงื่อนไขเอง
  is_public    TINYINT(1) NOT NULL DEFAULT 0,
  promo_info   VARCHAR(500) NULL,

  short_desc   VARCHAR(255) NULL,
  long_desc    TEXT NULL,
  -- ชื่อเว็บ + ชื่อดิบ + แบรนด์ + หมวด + สี + สไตล์ ต่อกัน ไว้ LIKE '%คำ%' ทีเดียวจบ
  -- ไม่ทำ FULLTEXT: MariaDB ตัดคำไทยไม่ได้ index จะไม่ช่วยอะไร
  search_text  VARCHAR(800) NULL,

  batch_id     VARCHAR(32) NOT NULL,
  updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  KEY ix_p_public (is_public),
  KEY ix_p_active (is_active),
  KEY ix_p_cat (cat_code),
  KEY ix_p_subcat (subcat_code),
  KEY ix_p_brand (brand_code),
  KEY ix_p_price (net_price),
  KEY ix_p_name (name_th),
  KEY ix_p_color (color_th),
  KEY ix_p_style (style_th)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='สินค้าที่คลีนแล้ว v2 — แอป sbdesign อ่านตารางนี้';


-- ---------------------------------------------------------------------------
--  วิวสำหรับคนอื่น (BI / ทีมอื่นที่มาต่อทีหลัง) — จะได้ไม่ต้องจำเงื่อนไข is_public
--  แอปเราไม่ได้อ่านวิวนี้ (อ่านตารางตรงแล้วกรองเอง เพราะเซลล์ต้องเห็นของที่ไม่ public ด้วย)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW sb_products_public AS
SELECT * FROM sb_products WHERE is_public = 1;
