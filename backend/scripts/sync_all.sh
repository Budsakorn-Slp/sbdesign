#!/bin/sh
# อัปเดตทุกอย่างในคำสั่งเดียว — เทียบเท่า sync_all.ps1 ฝั่ง Windows
#
#   scripts/sync_all.sh            ข้อมูลสินค้า + ค่าส่ง/ที่อยู่ + เนื้อหาหน้าเว็บ
#   scripts/sync_all.sh --with-sap รวมสต็อก/ราคาจาก SAP ด้วย
#
# ไม่มีขั้นสำรองฐานเหมือนฝั่ง Windows เพราะของจริงเป็น Postgres ที่อยู่คนละ container
# — สำรองทำที่โฮสต์ด้วย deploy/cron/backup_db.sh (pg_dump) ให้รันก่อนตัวนี้
set -u
# หาที่อยู่ของตัวเองให้เสร็จ "ก่อน" cd — ไม่งั้น $0 ที่เป็น path แบบสัมพัทธ์จะชี้ผิดที่
# แล้วหา lib.sh ไม่เจอ (เจอตอนทดสอบ: เรียกจากโฟลเดอร์อื่นแล้วพังทันที)
here="$(cd "$(dirname "$0")" && pwd)"
cd "${APP_DIR:-/app}" || { echo "เข้าโฟลเดอร์แอปไม่ได้: ${APP_DIR:-/app}" >&2; exit 1; }
. "$here/lib.sh"

with_sap=0
[ "${1:-}" = "--with-sap" ] && with_sap=1

started=$(date +%s)
say "===== SYNC ALL เริ่ม ====="

run "สินค้า"          sh "$here/sync_products.sh"
run "ค่าส่ง+ที่อยู่"   sh "$here/sync_daily.sh"
run "ภาพหน้าแรก"      python -m app.etl.sync_home_media
run "หน้า CMS"        python -m app.etl.sync_cms_pages

if [ "$with_sap" = "1" ]; then
  run "สต็อก+ราคา SAP" sh "$here/sync_stock.sh"
else
  say "ข้ามสต็อก/ราคาจาก SAP — ใส่ --with-sap ถ้าต้องการ"
fi

say "ใช้เวลา $(( ($(date +%s) - started) / 60 )) นาที"
finish "SYNC ALL"
