#!/bin/sh
# เงื่อนไขค่าส่ง (Amasty) + ที่อยู่ไทย (directory_*) จาก Magento — อ่าน Magento อย่างเดียว
# เทียบเท่า sync_daily.ps1 ฝั่ง Windows
#
#   docker compose -f docker-compose.prod.yml exec api scripts/sync_daily.sh
set -u
# หาที่อยู่ของตัวเองให้เสร็จ "ก่อน" cd — ไม่งั้น $0 ที่เป็น path แบบสัมพัทธ์จะชี้ผิดที่
# แล้วหา lib.sh ไม่เจอ (เจอตอนทดสอบ: เรียกจากโฟลเดอร์อื่นแล้วพังทันที)
here="$(cd "$(dirname "$0")" && pwd)"
cd "${APP_DIR:-/app}" || { echo "เข้าโฟลเดอร์แอปไม่ได้: ${APP_DIR:-/app}" >&2; exit 1; }
. "$here/lib.sh"

say "===== SYNC DAILY เริ่ม ====="

# สองตัวนี้ไม่ได้ขึ้นต่อกัน ตัวไหนล้มอีกตัวยังต้องได้รัน
run "sync_shipping_rules" python -m app.etl.sync_shipping_rules
run "sync_thai_geo"       python -m app.etl.sync_thai_geo

finish "SYNC DAILY"
