-- ============================================================================
--  sb_ship_* — เงื่อนไขค่าส่งที่คลีนแล้ว (ต้นทาง Amasty Shipping Rules บน 10.9.12.67)
--
--  ทำไมต้องมีบนฐานเว็บด้วย ไม่เก็บแค่ฐานแอป: ฐานนี้เป็นจุดนัดพบของ ETL ทุกตัวอยู่แล้ว
--  (sb_products / sb_products_image / sb_product_signals) เดินทางเดียวกันคือ
--  Magento -> sb_* บนฐานเว็บ -> import เข้าฐานแอป · ได้ของแถมคือเปิดดู/แก้ราคาผ่าน SQL
--  ได้โดยไม่ต้องเข้าเครื่องที่รันแอป และมีสำเนาไว้เทียบเวลาค่าส่งออกมาไม่ตรงที่คิด
--
--  ทุกตารางเป็นข้อมูลอนุพันธ์ทั้งหมด — sync รอบถัดไปล้างแล้วใส่ใหม่ ห้ามแก้มือแล้วหวังว่าจะอยู่
--
--    sb_ship_rates          ตารางอัตราตามน้ำหนัก แยกเขต · ช่วงครึ่งเปิด [weight_from, weight_to)
--    sb_ship_rules          กฎที่ไม่ใช่ตาราง (ส่งฟรีเมื่อครบยอด / เรตเดียว / ยกเว้นตาม SKU)
--    sb_ship_product_attrs  ธงรายสินค้า + น้ำหนัก ที่กฎเอาไปใช้กรอง (key = matnr)
--    sb_ship_areas          เขตค่าส่ง 1 = กทม.+ปริมณฑล · 2 = ต่างจังหวัด
--    sb_ship_area_postcodes รหัสไปรษณีย์ -> เขต เก็บเป็น prefix จับแบบยาวสุดชนะ
-- ============================================================================

CREATE TABLE IF NOT EXISTS sb_ship_areas (
  id          INT          NOT NULL,          -- 1 | 2 ตรงกับเลขเขตฝั่ง Amasty
  code        VARCHAR(16)  NOT NULL,
  name        VARCHAR(80)  NOT NULL,
  is_default  TINYINT(1)   NOT NULL DEFAULT 0,  -- ใช้เมื่อรหัสไปรษณีย์ไม่เข้า prefix ไหนเลย

  synced_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY uq_ship_area_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS sb_ship_area_postcodes (
  prefix      VARCHAR(5)   NOT NULL,
  area_id     INT          NOT NULL,
  note        VARCHAR(120) NULL,

  synced_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (prefix),
  KEY ix_ship_area_postcodes_area (area_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS sb_ship_rates (
  area_id         INT           NOT NULL,
  weight_from     DECIMAL(10,3) NOT NULL,   -- รวมค่านี้
  weight_to       DECIMAL(10,3) NOT NULL,   -- ไม่รวมค่านี้
  fee             DECIMAL(12,2) NOT NULL,
  source_rule_id  INT           NULL,       -- rule_id ฝั่ง Amasty ไว้ตามรอยตอนราคาไม่ตรง
  note            VARCHAR(200)  NULL,       -- บันทึกตอนคลีน เช่น "ปิดช่องว่าง" "แก้ช่วงกลับหัว"

  synced_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,

  -- คีย์คือ (เขต, ขอบล่าง) — หนึ่งเขตมีช่วงที่เริ่มตรงกันได้แถวเดียว กันตารางพังซ้ำรอยต้นทาง
  PRIMARY KEY (area_id, weight_from),
  KEY ix_ship_rates_lookup (area_id, weight_from, weight_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS sb_ship_rules (
  code            VARCHAR(40)   NOT NULL,
  name            VARCHAR(160)  NOT NULL,
  kind            VARCHAR(16)   NOT NULL,     -- free | flat | table
  priority        INT           NOT NULL DEFAULT 0,
  stop_on_match   TINYINT(1)    NOT NULL DEFAULT 1,
  fee             DECIMAL(12,2) NOT NULL DEFAULT 0,
  -- เงื่อนไขเป็น JSON คีย์ที่ engine ของเรารู้จัก ไม่ใช่ JSON ดิบของ Amasty
  -- (min_subtotal / max_subtotal / any_sku / require_item_all_of / weight_attr)
  conditions      LONGTEXT      NULL,
  is_active       TINYINT(1)    NOT NULL DEFAULT 1,
  source_rule_id  INT           NULL,

  synced_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (code),
  KEY ix_ship_rules_order (priority, code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS sb_ship_product_attrs (
  matnr                VARCHAR(50)   NOT NULL,   -- = sku ฝั่ง Magento
  weight_kg            DECIMAL(10,3) NULL,       -- ตัดค่า 999 / 0 ที่แปลว่า "ไม่ได้กรอก" ออกแล้ว
  flat_pack            TINYINT(1)    NOT NULL DEFAULT 0,
  flatpack_not_seller  TINYINT(1)    NOT NULL DEFAULT 0,  -- ธงที่ตารางน้ำหนักใช้
  flat_pack_bulky      TINYINT(1)    NOT NULL DEFAULT 0,
  attr_19_rule         TINYINT(1)    NOT NULL DEFAULT 0,
  attr_25_rule         TINYINT(1)    NOT NULL DEFAULT 0,

  synced_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (matnr),
  KEY ix_ship_attrs_flagged (flatpack_not_seller)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
