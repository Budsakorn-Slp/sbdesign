-- ============================================================================
--  sb_products_image — รูป/วิดีโอสินค้าทุกใบ ดึงจาก Magento (10.9.12.67)
--  เทียบเคียง maison_product_image แต่ไม่จำกัดแบรนด์ และแก้ 2 จุดที่ของเดิมขาด
--
--  1) ของเดิมไม่มีคอลัมน์ is_manual / position_locked ทั้งที่สคริปต์ UPDATE อ้างถึง
--     — ใส่ให้ครบ เพื่อให้ที่แก้มือไว้ไม่โดน sync รอบถัดไปทับ
--  2) ของเดิมไม่มี index เลย ตอน upsert ต้อง scan ทั้งตารางทุกแถว
--     — 3,670 แถวยังไหว แต่ของเราหลักแสน ต้องมี PK (entity_id, value_id)
--
--  แถวที่ image_position = -1 คือรูปหลักที่มาจาก attribute image (ไม่ใช่ gallery)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sb_products_image (
  entity_id       VARCHAR(20)  NOT NULL,
  value_id        VARCHAR(20)  NOT NULL,        -- 0 = รูปจาก attribute ไม่ใช่ gallery
  sku             VARCHAR(50)  NULL,            -- = MATNR
  product_name    VARCHAR(255) NULL,
  image_file      VARCHAR(255) NULL,            -- /1/9/19144682-1_23.jpg
  image_url       VARCHAR(500) NULL,            -- URL เต็มที่เว็บใช้จริง
  image_label     VARCHAR(255) NULL,
  image_position  INT          NOT NULL DEFAULT 100,
  image_disabled  TINYINT(1)   NOT NULL DEFAULT 0,
  media_type      VARCHAR(30)  NULL,            -- image | external-video
  video_url       TEXT         NULL,

  -- ธงกันของที่คนแก้มือโดน sync ทับ
  is_manual       TINYINT(1)   NOT NULL DEFAULT 0,  -- 1 = แถวนี้คนทำเอง ห้ามแตะทุกคอลัมน์
  position_locked TINYINT(1)   NOT NULL DEFAULT 0,  -- 1 = ล็อกลำดับไว้ คอลัมน์อื่น sync ได้

  synced_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (entity_id, value_id),
  KEY ix_img_sku (sku, image_position),
  KEY ix_img_type (media_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
