#!/bin/sh
# สำรองฐานข้อมูล Postgres — รันบน "โฮสต์" ไม่ใช่ในคอนเทนเนอร์
#
# ฝั่ง Windows สำรองด้วย sqlite .backup ซึ่งใช้กับ Postgres ไม่ได้ · ตัวนี้ใช้ pg_dump
# ที่มีอยู่ใน image ของ postgres อยู่แล้ว จึงไม่ต้องลงอะไรเพิ่มบนโฮสต์
#
#   /opt/sbdesign/deploy/cron/backup_db.sh
#
# กู้คืน:
#   gunzip -c <ไฟล์>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U sb -d sbdesign
set -eu

APP_DIR="${SBDESIGN_DIR:-/opt/sbdesign}"
BACKUP_DIR="${SBDESIGN_BACKUP_DIR:-$APP_DIR/backups}"
KEEP_DAYS="${SBDESIGN_BACKUP_KEEP_DAYS:-14}"

cd "$APP_DIR"
mkdir -p "$BACKUP_DIR"

# อ่านชื่อ user/db จาก .env เดียวกับที่ compose ใช้ จะได้ไม่ต้องมาแก้สองที่
. ./.env 2>/dev/null || true
DB_USER="${POSTGRES_USER:-sb}"
DB_NAME="${POSTGRES_DB:-sbdesign}"

out="$BACKUP_DIR/sbdesign_$(date +%Y%m%d-%H%M).sql.gz"

# เขียนลงไฟล์ชั่วคราวก่อนแล้วค่อยเปลี่ยนชื่อ — ถ้า dump พังกลางทางจะได้ไม่มีไฟล์ครึ่งๆ
# กลางๆ นั่งอยู่ในโฟลเดอร์สำรองแล้วหลอกเราว่ามีของสำรองอยู่
tmp="$out.part"
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$tmp"

if [ ! -s "$tmp" ]; then
  echo "$(date '+%F %T') สำรองล้มเหลว — ไฟล์ว่าง" >&2
  rm -f "$tmp"
  exit 1
fi
mv "$tmp" "$out"
echo "$(date '+%F %T') สำรองแล้ว: $out ($(du -h "$out" | cut -f1))"

# ลบของเก่า
find "$BACKUP_DIR" -name 'sbdesign_*.sql.gz' -mtime "+$KEEP_DAYS" -delete
