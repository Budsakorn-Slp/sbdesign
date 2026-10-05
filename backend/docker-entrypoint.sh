#!/bin/sh
# จุดเริ่มของ container ฝั่ง API
#
# เดิม CMD เป็น "alembic upgrade head && python -m app.seed && uvicorn ..." ซึ่งแปลว่า
# ทุกครั้งที่ container รีสตาร์ท ข้อมูลตัวอย่างจะถูกยัดลงฐานใหม่ — บน prd นั่นคือ
#   - สร้างบัญชีพนักงาน SA-104/SA-105/MG-001/ADM-001 รหัส 1122 ขึ้นมาใหม่ทุกรอบ
#     (ถึงจะเปลี่ยนรหัสไปแล้วก็ตาม) = ใครก็เดารหัสเข้าระบบหลังบ้านได้
#   - ยัดสินค้า/โปรโมชั่น/โซนจัดส่งปลอมปนกับของจริง
# และมันจะเกิดเงียบๆ ตอนเครื่องรีบูตหรือ deploy รอบถัดไป ไม่มีใครสั่ง
#
# ตอนนี้ seed ต้องสั่งให้ชัดด้วย SEED_ON_START=true เท่านั้น และถึงสั่งมา ถ้า APP_ENV=prod
# ก็ไม่ทำให้ — หยุดตั้งแต่ต้นพร้อมบอกเหตุผล ดีกว่าปล่อยข้อมูลปลอมเข้าฐานจริง
set -e

echo "[entrypoint] APP_ENV=${APP_ENV:-dev}"

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

if [ "${SEED_ON_START}" = "true" ]; then
  if [ "${APP_ENV}" = "prod" ]; then
    echo "[entrypoint] ปฏิเสธ: SEED_ON_START=true พร้อมกับ APP_ENV=prod" >&2
    echo "[entrypoint] seed จะสร้างบัญชีพนักงานรหัส 1122 และข้อมูลตัวอย่างทับฐานจริง" >&2
    echo "[entrypoint] ถ้าตั้งใจจะ seed จริงๆ ให้รัน 'python -m app.seed' เองทีละครั้ง" >&2
    exit 1
  fi
  echo "[entrypoint] python -m app.seed (ข้อมูลตัวอย่าง)"
  python -m app.seed
else
  echo "[entrypoint] ข้าม seed (ตั้ง SEED_ON_START=true ถ้าต้องการข้อมูลตัวอย่าง)"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
