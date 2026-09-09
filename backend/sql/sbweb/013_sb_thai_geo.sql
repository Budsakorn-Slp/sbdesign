-- ============================================================================
--  sb_thai_geo — ตำบล/อำเภอ/จังหวัด + รหัสไปรษณีย์ ที่หน้าเว็บใหม่ใช้เติมที่อยู่อัตโนมัติ
--
--  ต้นทาง directory_subdistrict + directory_district + directory_country_region
--  บน Magento (10.9.12.67) ซึ่งเป็นชุดเดียวกับที่เว็บเดิมใช้ ที่อยู่ลูกค้าเก่าจึงสะกดตรงกัน
--
--  ยกกฎธุรกิจของเว็บเดิมมาด้วย ไม่ได้ตกหล่น:
--    · 74 จังหวัด — ไม่มี ยะลา ปัตตานี นราธิวาส
--    · is_blocked = อยู่ใน forbidden_postcode 15 รหัส (เกาะ/พื้นที่รถส่งไม่ถึง)
--
--  area_id คือเขตค่าส่ง (1 = กทม.+ปริมณฑล · 2 = ต่างจังหวัด) คิดจาก prefix รหัสไปรษณีย์
--  เก็บติดมาด้วยเพื่อให้หน้าเว็บโชว์ค่าส่งคร่าวๆ ได้ตั้งแต่ลูกค้าเพิ่งเลือกจังหวัด
-- ============================================================================

CREATE TABLE IF NOT EXISTS sb_thai_geo (
  subdistrict_id  INT          NOT NULL,
  zipcode         VARCHAR(5)   NOT NULL,
  subdistrict_th  VARCHAR(120) NOT NULL,
  subdistrict_en  VARCHAR(120) NULL,
  district_id     INT          NOT NULL,
  district_th     VARCHAR(120) NOT NULL,
  district_en     VARCHAR(120) NULL,
  province_id     INT          NOT NULL,   -- region_id ฝั่ง Magento
  province_th     VARCHAR(120) NOT NULL,
  province_en     VARCHAR(120) NULL,
  area_id         INT          NULL,
  is_blocked      TINYINT(1)   NOT NULL DEFAULT 0,

  synced_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (subdistrict_id),
  KEY ix_thai_geo_zip      (zipcode),
  KEY ix_thai_geo_district (district_id),
  KEY ix_thai_geo_province (province_id, district_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
