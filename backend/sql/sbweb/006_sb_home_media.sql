-- ============================================================================
--  sb_home_media — ภาพ/ป้ายของหน้าแรก ดึงจาก Magento CMS (10.9.12.67)
--
--  ที่ต้องมีตารางนี้: หน้าแรกของ sbdesignsquare.com ไม่มีตารางแบนเนอร์
--  (amasty_banners_lite_banner_data ว่างเปล่า) ทุกอย่างฝังเป็น HTML ของ PageBuilder
--  อยู่ใน cms_page.content ก้อนเดียว — อ่านตรงๆ ไม่ได้ ต้อง parse แล้วเก็บเป็นแถว
--
--  3 section ในตารางเดียว เพราะโครงคอลัมน์เหมือนกันหมด (รูป + ป้าย + ลิงก์):
--    hero          แบนเนอร์แคมเปญหลัก — มีไฟล์แยก PC / MB
--    top_category  แถบ TOP CATEGORIES — 12 หมวด
--    inspiration   แถบ HOME INSPIRATIONS — การ์ดคอลเลกชัน
--
--  slug ตั้งจากชื่อไฟล์ภาพ เพื่อให้ upsert รอบถัดไปลงแถวเดิม ไม่ใช่ insert ซ้ำ
-- ============================================================================

CREATE TABLE IF NOT EXISTS sb_home_media (
  section       VARCHAR(30)  NOT NULL,        -- hero | top_category | inspiration
  slug          VARCHAR(160) NOT NULL,        -- ชื่อไฟล์ภาพแบบไม่มีนามสกุล
  position      INT          NOT NULL DEFAULT 0,
  label         VARCHAR(255) NULL,            -- ชื่อหมวด/คอลเลกชันที่โชว์ใต้รูป
  alt           VARCHAR(255) NULL,
  image_url     VARCHAR(500) NOT NULL,
  image_mb_url  VARCHAR(500) NULL,            -- เฉพาะ hero ที่ Magento แยกไฟล์มือถือ
  source_href   VARCHAR(500) NULL,            -- ลิงก์ปลายทางบน sbdesignsquare.com

  is_active     TINYINT(1)   NOT NULL DEFAULT 1,
  is_manual     TINYINT(1)   NOT NULL DEFAULT 0,  -- 1 = คนแก้มือไว้ sync ห้ามทับ
  page_id       INT          NULL,            -- cms_page ที่ดึงมา ไว้ไล่ย้อนตอนแคมเปญเปลี่ยน

  synced_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (section, slug),
  KEY ix_home_media_sec (section, is_active, position)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
