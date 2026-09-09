-- ============================================================================
--  sbdesign — ตารางสินค้าสำหรับแอป บนฐาน web @ 10.9.11.111 (MariaDB 10.4)
--  รันครั้งเดียว:  mysql -h 10.9.11.111 -P 3307 -u dba -p web < 001_sb_products_tables.sql
--
--  ไหลของข้อมูล (ไม่มีตาราง raw ของเราเอง — mdm_products คือ raw อยู่แล้ว)
--    10.9.12.67 --[job เดิม]--> web.mdm_products --[002 clean+swap]--> sb_products --> แอป
--
--  ทุกตารางขึ้นต้นด้วย sb_ เพื่อไม่ชนกับ 222 ตารางเดิมของเว็บ
--  ไฟล์นี้ "สร้างใหม่เท่านั้น" ไม่มี DROP/ALTER ตารางเดิมแม้แต่บรรทัดเดียว
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) สินค้าที่คลีนแล้ว — ตารางเดียวที่แอปอ่าน
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sb_products (
  matnr        VARCHAR(50)  NOT NULL PRIMARY KEY,
  name_th      VARCHAR(255) NOT NULL,

  brand_code   VARCHAR(20)  NULL,               -- MVGR1N
  brand_name   VARCHAR(200) NULL,               -- MVGR1T
  series_name  VARCHAR(200) NULL,               -- MVGR2T ซีรีส์/คอลเลกชัน
  cat_code     VARCHAR(100) NULL,               -- MVGR3N หมวดหลัก
  cat_name     VARCHAR(200) NULL,
  subcat_code  VARCHAR(100) NULL,               -- MVGR4N หมวดย่อย
  subcat_name  VARCHAR(200) NULL,

  list_price   DECIMAL(12,2) NULL,              -- PRICE ราคาตั้ง (ไว้ขีดฆ่า)
  net_price    DECIMAL(12,2) NULL,              -- NETPRICE ราคาขายจริง
  discount_pct DECIMAL(5,2)  NULL,              -- คำนวณจาก list vs net

  image_path   VARCHAR(765) NULL,               -- PATH ของ MDM — เป็น path เครื่องภายใน เปิดจากเน็ตไม่ได้
  image_url    VARCHAR(500) NULL,               -- URL จริงที่เว็บใช้ มาจาก mdm_products_media
  image_count  INT          NOT NULL DEFAULT 0, -- จำนวนรูปทั้งหมดของสินค้าตัวนี้               -- PATH — เป็น relative เช่น /cyber/images/mat/xxx.jpg
  -- ขนาดจริงอยู่ใน GROES ("150X79X80") — คอลัมน์ WIDTH/LEGHT/HEGHT ของต้นทางว่างเกือบทั้งตาราง
  size_text    VARCHAR(96)  NULL,
  width_cm     DECIMAL(8,1) NULL,
  length_cm    DECIMAL(8,1) NULL,
  height_cm    DECIMAL(8,1) NULL,

  spart        VARCHAR(8)   NULL,               -- MER / KD / BI / Consign
  -- ต้นทางเป็น "รหัส" ไม่ใช่ 0/1 (ASSEM = P/MP/L · FLATPACK = X · LUXURY = L · ASSEM_ONLINE = R)
  -- เก็บรหัสดิบไว้ด้วย เผื่อวันหน้าต้องแยกว่า P กับ MP ต่างกันยังไง
  assem_code   VARCHAR(8)   NULL,
  needs_assembly TINYINT(1) NOT NULL DEFAULT 0, -- = ASSEM ไม่ว่าง
  is_flatpack    TINYINT(1) NOT NULL DEFAULT 0,
  is_luxury      TINYINT(1) NOT NULL DEFAULT 0,
  assem_online   TINYINT(1) NOT NULL DEFAULT 0,

  -- ขายอยู่จริงไหม — มาจากตาราง mdm_products_active (25,305 ตัว) ที่ต้นทางทำไว้ให้แล้ว
  -- เก็บสินค้าไว้ทั้งหมด ไม่ตัดทิ้ง แล้วให้แอปดึงเฉพาะ is_active=1
  -- (ถ้าตัดทิ้งตั้งแต่ตรงนี้ วันที่ต้นทางปิดสินค้าผิด เราจะกู้กลับไม่ได้เลย)
  is_active    TINYINT(1) NOT NULL DEFAULT 0,
  promo_info   VARCHAR(500) NULL,               -- PROMO_INFO จาก mdm_products_active

  short_desc   VARCHAR(255) NULL,
  long_desc    TEXT NULL,
  search_text  VARCHAR(600) NULL,               -- ชื่อ+แบรนด์+หมวด ต่อกัน ไว้ LIKE
                                                -- ไม่ทำ FULLTEXT: MariaDB ตัดคำไทยไม่ได้ index จะไม่ช่วยอะไร

  batch_id     VARCHAR(32) NOT NULL,            -- รอบที่ rebuild — ผูกกับ sb_import_log
  updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  KEY ix_p_active (is_active),
  KEY ix_p_cat (cat_code),
  KEY ix_p_subcat (subcat_code),
  KEY ix_p_brand (brand_code),
  KEY ix_p_price (net_price),
  KEY ix_p_name (name_th)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='สินค้าที่คลีนจาก mdm_products — แอป sbdesign อ่านตารางนี้';


-- ---------------------------------------------------------------------------
-- 2) log ทุกรอบ — เข้ากี่แถว ออกกี่แถว ตกกี่แถว เพราะอะไร
--    ไม่มีตารางนี้ = วันที่ข้อมูลหาย จะไม่มีทางรู้ว่าหายตอนไหน
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sb_import_log (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id     VARCHAR(32) NOT NULL,
  stage        VARCHAR(16) NOT NULL,            -- rebuild | push_app
  started_at   DATETIME NOT NULL,
  finished_at  DATETIME NULL,
  status       VARCHAR(16) NOT NULL,            -- running | ok | failed
  rows_in      INT NOT NULL DEFAULT 0,          -- แถวใน mdm_products
  rows_out     INT NOT NULL DEFAULT 0,          -- แถวที่ลง sb_products
  rows_skipped INT NOT NULL DEFAULT 0,
  message      TEXT NULL,
  KEY ix_log_batch (batch_id),
  KEY ix_log_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
