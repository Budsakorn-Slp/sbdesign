-- ============================================================================
--  sb_products v3 — สร้างตารางสินค้าใหม่ทั้งใบ (แทน 008)
--  รันครั้งเดียว:  mysql -h 10.9.11.111 -P 3307 -u dba -p web < 010_sb_products_v3.sql
--
--  ทำไมต้องสร้างใหม่ ไม่ ALTER:
--    v2 ไม่ได้เก็บ MAABC (รหัสชั้นสินค้าของ SAP) ทั้งที่ mdm_products ส่งมาให้ตลอด
--    "สินค้าขายดี" ที่ลูกค้าเห็นทุกแถวบนเว็บ ตอนนี้เดาจาก sold_qty ที่นับจาก Magento
--    ซึ่งเป็นยอดของเว็บอย่างเดียว ไม่ใช่ยอดขายจริงทั้งบริษัท · MAABC='Z' คือกลุ่มที่
--    ฝ่ายสินค้าจัดว่าขายดี — วัดกับ sb_product_signals แล้วตรงกัน:
--        Z เฉลี่ย 3.5 ชิ้น/ตัว (266 ตัว) · ชั้นอื่นทั้งหมด ≤ 1.1 (C 1.1 · M 1.0 · A 0.8 · ที่เหลือ ≤0.3)
--    ตารางถูก rebuild ทั้งใบทุกคืนอยู่แล้ว (ไม่มีใครเขียนมือ) สร้างใหม่จึงไม่เสียข้อมูล
--
--  ชื่อคอลัมน์ — ตัวพิมพ์ใหญ่ ชุดเดียวกับ maison_products / mdm_products
--    ช่องไหนที่เป็นค่าดิบจาก SAP ใช้ชื่อ SAP ตรงๆ (MATNR MAKTX MVGR1T MAABC PRICE ...)
--    เปิดตารางเทียบกับ mdm_products แล้วรู้ทันทีว่าช่องไหนคือช่องไหน ไม่ต้องเปิดแมปดู
--    ช่องที่เราคำนวณเองไม่มีชื่อ SAP ให้ใช้ ตั้งชื่อเองแต่พิมพ์ใหญ่ให้เข้าชุดกัน
--      (DISPLAY_NAME · IS_PUBLIC · IMAGE_URL · SIZE_TEXT ...)
--    MariaDB ไม่แคร์ตัวพิมพ์ของชื่อคอลัมน์อยู่แล้ว เรื่องนี้จึงมีผลกับตาที่อ่านเท่านั้น
--
--  ต่างจาก v2 ตรงไหน — เพิ่มช่อง ไม่ได้ตัดหรือเปลี่ยนความหมายของช่องเดิม
--    MAABC / IS_BESTSELLER               ชั้นสินค้า และธง "อยู่ชั้น Z"
--    MVGR5N/T · MVGR6N/T · MVGR7N/T      กลุ่มที่ maison_products ใช้ แต่ v2 ไม่ได้ดึง
--                                        (5 = กลุ่มตามขนาด · 6 = สี/ผิว · 7 = วัสดุ)
--    DISCOUNT                            ส่วนลดที่ตั้งไว้ใน MDM (คนละตัวกับ DISCOUNT_PCT ที่เราคิดเอง)
--    VIEW_COUNT / STOCK_QTY              จาก maison_products เท่าที่มี (1,298 แถว)
--    ไม่เก็บ CPIC — ทั้ง 199,742 แถวเป็นค่าว่าง ดึงมาก็ได้คอลัมน์เปล่า
--
--  ตารางเดิม sb_products ถูก DROP ในไฟล์นี้ (ตารางของโปรเจกต์นี้เอง ไม่มีระบบอื่นอ่าน)
--  ไม่มี DROP/ALTER ตารางของเว็บเดิมแม้แต่บรรทัดเดียว
-- ============================================================================

DROP TABLE IF EXISTS sb_products;

CREATE TABLE sb_products (
  MATNR        VARCHAR(50)  NOT NULL PRIMARY KEY,

  -- ---- ชื่อ ----------------------------------------------------------------
  -- MAKTX        = ชื่อดิบจาก SAP · เซลล์ใช้ค้นตามที่พิมพ์กันมาแต่เดิม ห้ามทิ้ง
  -- DISPLAY_NAME = ชื่อที่ลูกค้าเห็น มาจากเว็บจริงก่อน ถ้าไม่มีค่อยไล่ลงไปตาม NAME_SOURCE
  -- NAME_EN      = ชื่ออังกฤษเดิมของเว็บ เก็บไว้ตอนที่เราประกอบชื่อไทยทับ (ค้นด้วยชื่ออังกฤษยังเจอ)
  MAKTX        VARCHAR(255) NOT NULL,
  DISPLAY_NAME VARCHAR(255) NULL,
  NAME_EN      VARCHAR(255) NULL,
  NAME_SOURCE  VARCHAR(10)  NULL,               -- magento | maison | disney | extend | compose | maktx

  MVGR1N       VARCHAR(20)  NULL,               -- รหัสแบรนด์
  MVGR1T       VARCHAR(200) NULL,               -- ชื่อแบรนด์
  MVGR2T       VARCHAR(200) NULL,               -- ซีรีส์/คอลเลกชัน
  MVGR3N       VARCHAR(100) NULL,               -- รหัสหมวดหลัก
  MVGR3T       VARCHAR(200) NULL,               -- ชื่อหมวดหลัก
  MVGR4N       VARCHAR(100) NULL,               -- รหัสหมวดย่อย
  MVGR4T       VARCHAR(200) NULL,               -- ชื่อหมวดย่อย

  -- ---- กลุ่มย่อยชั้น 5-7 (ของใหม่ v3) — ชุดเดียวกับที่ maison_products ใช้ ---
  -- 5 = กลุ่มตามขนาด ("โต๊ะอาหารขนาด 150-179") · 6 = สี/ผิว ("WHITE OAK") · 7 = วัสดุ ("WOOD")
  -- ไว้ทำตัวกรองละเอียดและจับสินค้ารุ่นเดียวกันคนละสี ตอนนี้ยังไม่มีหน้าไหนใช้ แต่เก็บก่อน
  MVGR5N       VARCHAR(100) NULL,
  MVGR5T       VARCHAR(200) NULL,
  MVGR6N       VARCHAR(100) NULL,
  MVGR6T       VARCHAR(200) NULL,
  MVGR7N       VARCHAR(100) NULL,
  MVGR7T       VARCHAR(200) NULL,

  -- ---- สี / สไตล์ — จาก mdm_products_color / mdm_products_style ------------
  COLOR_TH     VARCHAR(100) NULL,
  COLOR_EN     VARCHAR(100) NULL,
  STYLE_TH     VARCHAR(100) NULL,
  STYLE_EN     VARCHAR(100) NULL,

  PRICE        DECIMAL(12,2) NULL,              -- ราคาตั้ง (ไว้ขีดฆ่า)
  NETPRICE     DECIMAL(12,2) NULL,              -- ราคาขายจริง
  DISCOUNT_PCT DECIMAL(5,2)  NULL,              -- คิดเองจาก (PRICE-NETPRICE)/PRICE
  -- DISCOUNT ของ MDM เก็บเป็นเลขติดลบ ("-30.00" = ลด 30%) พลิกเป็นบวกตอน rebuild
  -- ไม่เอามาแทน DISCOUNT_PCT เพราะบางตัวตั้งไว้แต่ราคาจริงไม่ได้ลดตาม — ใช้เทียบ/ตรวจสอบ
  DISCOUNT     DECIMAL(5,2)  NULL,

  PATH         VARCHAR(765) NULL,               -- path เครื่องภายในของ MDM เปิดจากเน็ตไม่ได้
  IMAGE_URL    VARCHAR(500) NULL,               -- URL จริงบนเว็บ
  IMAGE_COUNT  INT          NOT NULL DEFAULT 0,

  -- ขนาดจริงอยู่ใน GROES ("150X79X80") — WIDTH/LEGHT/HEGHT ของต้นทางว่างเกือบทั้งตาราง
  -- SIZE_TEXT คือ GROES ที่ล้างแล้ว ไม่ใช่ค่าดิบ จึงไม่ใช้ชื่อ GROES
  SIZE_TEXT    VARCHAR(96)  NULL,
  WIDTH_CM     DECIMAL(8,1) NULL,
  LENGTH_CM    DECIMAL(8,1) NULL,
  HEIGHT_CM    DECIMAL(8,1) NULL,

  SPART_TEXT   VARCHAR(8)   NULL,               -- MER / KD / BI / Consign
  ASSEM        VARCHAR(8)   NULL,               -- P/MP/L (เก็บรหัสดิบไว้ด้วย)
  NEEDS_ASSEMBLY TINYINT(1) NOT NULL DEFAULT 0,
  IS_FLATPACK    TINYINT(1) NOT NULL DEFAULT 0,
  IS_LUXURY      TINYINT(1) NOT NULL DEFAULT 0,
  ASSEM_ONLINE   TINYINT(1) NOT NULL DEFAULT 0,

  -- ---- ชั้นสินค้า SAP (ของใหม่ v3) -----------------------------------------
  -- MAABC มีค่า 171,666 แถว · ชั้นที่เจอ: A B C E F G M N P R S T V Z
  -- IS_BESTSELLER = ชั้น Z เท่านั้น · แอปเอาไปเรียงแถว "สินค้าขายดี" ก่อน sold_qty
  MAABC         VARCHAR(20) NULL,
  IS_BESTSELLER TINYINT(1) NOT NULL DEFAULT 0,

  -- ---- ธงการตลาดจาก mdm_products_extend ------------------------------------
  -- หมายเหตุ: รอบแรกที่รัน (8 ก.ย. 69) ต้นทางยังเป็นค่าว่างทั้ง 46,470 แถว ได้ 0 ทุกช่อง
  -- เก็บช่องไว้ก่อน วันไหนฝ่ายการตลาดเริ่มติ๊กใน MDM ก็ไหลเข้ามาเองโดยไม่ต้องแก้อะไร
  IS_HOT            TINYINT(1) NOT NULL DEFAULT 0,  -- HOTITEM
  IS_NEW_COLLECTION TINYINT(1) NOT NULL DEFAULT 0,  -- NEWCOLLECTION
  IS_SPECIAL_DEAL   TINYINT(1) NOT NULL DEFAULT 0,  -- SPECIALDEAL
  FREE_DELIVERY     TINYINT(1) NOT NULL DEFAULT 0,  -- FREEDELIVERY

  -- ---- ตัวเลขจาก maison_products (มีแค่ ~1,298 sku ที่เหลือเป็น NULL) -------
  VIEW_COUNT   INT NULL,
  STOCK_QTY    INT NULL,

  -- ---- สถานะ ---------------------------------------------------------------
  IS_ACTIVE    TINYINT(1) NOT NULL DEFAULT 0,   -- อยู่ใน mdm_products_active
  HAS_WEB      TINYINT(1) NOT NULL DEFAULT 0,   -- มีหน้าอยู่บน sbdesignsquare.com จริง
  -- ครบพอให้ลูกค้าเห็นไหม — คิดตอน rebuild ที่เดียว แอปไม่ต้องเดาเงื่อนไขเอง
  IS_PUBLIC    TINYINT(1) NOT NULL DEFAULT 0,
  PROMO_INFO   VARCHAR(500) NULL,

  SHORT_DESC   VARCHAR(255) NULL,
  LONG_DESC    TEXT NULL,
  -- ชื่อเว็บ + ชื่อดิบ + แบรนด์ + หมวด + สี + สไตล์ ต่อกัน ไว้ LIKE '%คำ%' ทีเดียวจบ
  -- ไม่ทำ FULLTEXT: MariaDB ตัดคำไทยไม่ได้ index จะไม่ช่วยอะไร
  SEARCH_TEXT  VARCHAR(800) NULL,

  BATCH_ID     VARCHAR(32) NOT NULL,
  UPDATED_AT   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  KEY ix_p_public (IS_PUBLIC),
  KEY ix_p_active (IS_ACTIVE),
  KEY ix_p_cat (MVGR3N),
  KEY ix_p_subcat (MVGR4N),
  KEY ix_p_brand (MVGR1N),
  KEY ix_p_price (NETPRICE),
  KEY ix_p_name (MAKTX),
  KEY ix_p_color (COLOR_TH),
  KEY ix_p_style (STYLE_TH),
  KEY ix_p_abc (MAABC),
  -- แถวขายดีดึงด้วย "IS_PUBLIC=1 AND IS_BESTSELLER=1" ทุกหน้า เลยทำ index คู่กันไปเลย
  KEY ix_p_best (IS_BESTSELLER, IS_PUBLIC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='สินค้าที่คลีนแล้ว v3 — แอป sbdesign อ่านตารางนี้';


-- ---------------------------------------------------------------------------
--  วิวสำหรับคนอื่น (BI / ทีมอื่นที่มาต่อทีหลัง) — จะได้ไม่ต้องจำเงื่อนไข IS_PUBLIC
--  แอปเราไม่ได้อ่านวิวนี้ (อ่านตารางตรงแล้วกรองเอง เพราะเซลล์ต้องเห็นของที่ไม่ public ด้วย)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW sb_products_public AS
SELECT * FROM sb_products WHERE IS_PUBLIC = 1;
