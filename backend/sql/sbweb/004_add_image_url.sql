-- ============================================================================
--  เพิ่ม image_url + image_count ให้ sb_products ที่สร้างไปแล้ว แล้วเติมข้อมูลรอบแรก
--  (001 เป็น CREATE TABLE IF NOT EXISTS — ตารางที่มีอยู่แล้วจะไม่ได้คอลัมน์ใหม่)
--  รอบถัดๆ ไป 002 เติมให้เองตอน rebuild ไม่ต้องรันไฟล์นี้ซ้ำ
-- ============================================================================

ALTER TABLE sb_products
  ADD COLUMN image_url   VARCHAR(500) NULL              AFTER image_path,
  ADD COLUMN image_count INT          NOT NULL DEFAULT 0 AFTER image_url;

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

UPDATE sb_products p
JOIN sb_media_first f ON f.sku = p.matnr
SET p.image_url = f.image_url, p.image_count = f.image_count;

DROP TABLE sb_media_first;
