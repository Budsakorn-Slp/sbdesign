#!/bin/sh
# สต็อก + ราคาจาก SAP — ยิง SAP จริงหลายพันครั้ง ควรรันนอกเวลาทำการ
#
#   refresh_stock       สต็อกสินค้าที่ขึ้นเว็บ (~3,700 ครั้ง)
#   sync_display_items  สินค้าตัวโชว์ (~3,400 ครั้ง)
#   sync_sap_prices     ราคา+MAT ทั้งก้อนจาก zaibapi-material-get-all (snapshot ลง data/sap/)
#
# ห้ามใส่ --mock เด็ดขาด — มันเขียนตัวเลขปลอมทับสต็อกจริง
#
#   docker compose -f docker-compose.prod.yml exec api scripts/sync_stock.sh
set -u
# หาที่อยู่ของตัวเองให้เสร็จ "ก่อน" cd — ไม่งั้น $0 ที่เป็น path แบบสัมพัทธ์จะชี้ผิดที่
# แล้วหา lib.sh ไม่เจอ (เจอตอนทดสอบ: เรียกจากโฟลเดอร์อื่นแล้วพังทันที)
here="$(cd "$(dirname "$0")" && pwd)"
cd "${APP_DIR:-/app}" || { echo "เข้าโฟลเดอร์แอปไม่ได้: ${APP_DIR:-/app}" >&2; exit 1; }
. "$here/lib.sh"

say "===== SYNC STOCK + PRICES เริ่ม (ยิง SAP จริง) ====="

# ราคามาก่อน — sync_display_items อ่าน snapshot ราคาที่ตัวนี้เขียนไว้
run "sync_sap_prices"    python -m app.etl.sync_sap_prices
run "refresh_stock"      python -m app.etl.refresh_stock --all
run "sync_display_items" python -m app.etl.sync_display_items --all
# รายชื่อสาขามาจากคำตอบของ refresh_stock ต้องอัปเดตตามทุกรอบ ไม่งั้นสาขาใหม่ไม่โผล่ให้เลือก
run "sync_plants"        python -m app.etl.sync_plants

finish "SYNC STOCK + PRICES"
