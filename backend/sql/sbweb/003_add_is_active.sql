-- ============================================================================
--  เพิ่ม is_active + promo_info ให้ sb_products ที่สร้างไปแล้ว
--  (001 เป็น CREATE TABLE IF NOT EXISTS — ตารางที่มีอยู่แล้วจะไม่ได้คอลัมน์ใหม่)
--  ฐานใหม่ที่รัน 001 ตั้งแต่ต้นไม่ต้องรันไฟล์นี้ แต่รันซ้ำก็ไม่เสียหาย
-- ============================================================================

ALTER TABLE sb_products
  ADD COLUMN is_active  TINYINT(1)   NOT NULL DEFAULT 0 AFTER assem_online,
  ADD COLUMN promo_info VARCHAR(500) NULL              AFTER is_active,
  ADD KEY ix_p_active (is_active);
