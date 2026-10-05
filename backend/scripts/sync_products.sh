#!/bin/sh
# ข้อมูลสินค้าทั้งชุด — เทียบเท่า sync_products.ps1 ฝั่ง Windows
#
# ลำดับสำคัญ ตัวหลังกินผลจากตัวหน้า:
#   1 rebuild_products        mdm_products -> sb_products      (ฐานเว็บ 10.9.11.111)
#   2 sync_product_images     Magento -> sb_products_image
#   3 sync_product_signals    ยอดขาย 365 วัน -> มาใหม่/ขายดี
#   4 import_catalog          sb_products -> สินค้า/หมวด/แบรนด์/ราคา (ฐานแอป)
#   5 import_product_gallery  sb_products_image -> material_images
#   6 sync_english_names      ชื่อ EN จาก store view 1 ของ Magento
#   7 sync_web_categories     ยกการจัดหมวดของเว็บจริงมา ทีละกลุ่ม
#
# ไม่รวมสต็อก/ราคา SAP — อยู่ใน sync_stock.sh เพราะยิง SAP หนักและเปลี่ยนคนละจังหวะ
#
# รันข้างใน container:
#   docker compose -f docker-compose.prod.yml exec api scripts/sync_products.sh
set -u
# หาที่อยู่ของตัวเองให้เสร็จ "ก่อน" cd — ไม่งั้น $0 ที่เป็น path แบบสัมพัทธ์จะชี้ผิดที่
# แล้วหา lib.sh ไม่เจอ (เจอตอนทดสอบ: เรียกจากโฟลเดอร์อื่นแล้วพังทันที)
here="$(cd "$(dirname "$0")" && pwd)"
cd "${APP_DIR:-/app}" || { echo "เข้าโฟลเดอร์แอปไม่ได้: ${APP_DIR:-/app}" >&2; exit 1; }
. "$here/lib.sh"

say "===== SYNC PRODUCTS เริ่ม ====="

run "rebuild_products"       python -m app.etl.rebuild_products
run "sync_product_images"    python -m app.etl.sync_product_images
run "sync_product_signals"   python -m app.etl.sync_product_signals
run "import_catalog"         python -m app.etl.import_catalog
run "import_product_gallery" python -m app.etl.import_product_gallery
run "sync_english_names"     python -m app.etl.sync_english_names

# หมวดของเว็บทำทีละกลุ่ม — กลุ่มไหนพังก็ไม่ลากกลุ่มอื่นล้มตาม
for g in bedroom living dining office decor special; do
  run "sync_web_categories --group $g" python -m app.etl.sync_web_categories --group "$g"
done

finish "SYNC PRODUCTS"
