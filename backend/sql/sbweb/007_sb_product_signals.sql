-- ============================================================================
--  sb_product_signals — สัญญาณ "มาใหม่" / "ขายดี" ของสินค้าแต่ละตัว
--
--  ที่ต้องแยกตาราง ไม่ไปต่อท้าย sb_products: sb_products ถูก rebuild ใหม่ทั้งตาราง
--  จาก mdm_products ทุกรอบ (ดู 002_rebuild_sb_products.sql) ค่าที่มาจากคนละต้นทาง
--  จะหายไปด้วย — แยกตารางแล้ว join เอาตอน import จึงปลอดภัยกว่า
--
--  ต้นทางคือ Magento (10.9.12.67) ซึ่ง sku = matnr ตรงกันทั้งชุด:
--    created_at   catalog_product_entity.created_at  — วันที่สินค้าขึ้นเว็บ
--    sold_qty     SUM(sales_order_item.qty_ordered)  — ยอดขายจริงย้อนหลัง N วัน
--    sold_orders  จำนวนออเดอร์ที่มีสินค้าตัวนี้ (กันตัวที่ขายทีเดียวล็อตใหญ่ทะลุอันดับ)
--
--  ตัวที่ยังไม่เคยขายจะไม่มีแถวในนี้ ฝั่ง import ถือเป็น sold_qty = 0
-- ============================================================================

CREATE TABLE IF NOT EXISTS sb_product_signals (
  matnr        VARCHAR(50) NOT NULL,
  created_at   DATETIME    NULL,             -- วันที่สินค้าถูกสร้างบนเว็บ
  sold_qty     INT         NOT NULL DEFAULT 0,
  sold_orders  INT         NOT NULL DEFAULT 0,
  window_days  INT         NOT NULL DEFAULT 365,  -- ช่วงที่นับยอดขาย

  synced_at    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (matnr),
  KEY ix_signals_new  (created_at),
  KEY ix_signals_sold (sold_qty)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
