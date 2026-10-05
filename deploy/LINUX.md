# ขึ้นเซิร์ฟเวอร์ Linux (ให้พนักงานเข้าเทส)

ไฟล์นี้คือการขึ้นจริงด้วย Docker บนเครื่อง Linux · ส่วน `README.md` ข้างๆ คือวิธีเปิดจาก
เครื่อง Windows ในออฟฟิศแบบชั่วคราว (ต้องเปิดหน้าต่างค้างไว้) ซึ่งใช้คนละชุดคำสั่งกัน

```
ผู้ใช้ -> Cloudflare -> tunnel -> nginx (web) -> api -> db
                                       |
                                       +-> SAP 192.168.7.110 / Magento 10.9.x
```

**เครื่องที่จะลงต้องอยู่ในเครือข่ายที่วิ่งถึง SAP ได้** ไม่งั้นเช็คสต็อก/ราคาใช้ไม่ได้ทั้งระบบ
— ลองก่อนด้วย `curl -m 5 http://192.168.7.110:18080/` จากเครื่องนั้น

---

## ครั้งแรก

### 1. เตรียมไฟล์ลับ 2 ไฟล์ (ไม่อยู่ใน git ต้องทำเอง)

`backend/.env` — ก๊อปจาก `.env.example` แล้วใส่ค่าจริง อย่างน้อยต้องมี

```
APP_ENV=prod
INVITE_ONLY=true
JWT_SECRET=<สุ่มใหม่ อย่างน้อย 32 ตัว ห้ามใช้ตัวเดียวกับเครื่อง dev>
SAP_API_KEY=<คีย์จากทีม SAP>
SAP_AVAIL_URL=... SAP_STOCK_URL=... SAP_CATALOG_URL=...
CORS_ORIGINS=https://<โดเมนที่จะใช้>
```

`.env` ที่โฟลเดอร์บนสุด — ใช้ตอน compose ประกอบค่า

```
POSTGRES_PASSWORD=<สุ่มใหม่>
CLOUDFLARE_TUNNEL_TOKEN=<token จากหน้า Cloudflare Zero Trust>
```

> สุ่มรหัส: `openssl rand -base64 32`

### 2. เปิดระบบ

```bash
docker compose -f docker-compose.prod.yml --profile tunnel up -d --build
```

ครั้งแรกจะ build สักพัก (ติดตั้ง deps + `npm run build`) · migration ฐานข้อมูลรันเองตอน
container ขึ้น (`alembic upgrade head` ใน `backend/docker-entrypoint.sh`)

### 3. ชี้โดเมนมาที่ tunnel

ที่หน้า Cloudflare Zero Trust > Networks > Tunnels > tunnel ตัวนี้ > Public Hostname
ตั้ง service เป็น **`http://web:80`** (ชื่อ service ใน compose ไม่ใช่ localhost)

### 4. ตรวจว่าขึ้นจริง

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/          # 200
curl -s http://127.0.0.1:8080/api/public-config                          # ต้องได้ JSON
curl -sI http://127.0.0.1:8080/ | grep -i x-frame-options                # ต้องมี DENY
docker compose -f docker-compose.prod.yml logs --tail=30 api
```

---

## ข้อมูลตั้งต้น

ฐานใหม่จะว่างเปล่า — **ไม่ seed ให้อัตโนมัติ** และถ้าตั้ง `SEED_ON_START=true` คู่กับ
`APP_ENV=prod` container จะไม่ยอมขึ้นเลย (ดูเหตุผลใน `backend/docker-entrypoint.sh`)
เพราะ seed สร้างบัญชีพนักงานรหัส `1122` และยัดสินค้าตัวอย่างทับของจริงทุกครั้งที่รีสตาร์ท

ดึงของจริงเข้าแทน — ลำดับเดียวกับที่ `backend/scripts/sync_all.ps1` ทำบน Windows
(`dc` = `docker compose -f docker-compose.prod.yml`)

```bash
dc exec api python -m app.etl.import_catalog          # สินค้าจากเว็บจริง
dc exec api python -m app.etl.sync_web_categories
dc exec api python -m app.etl.sync_product_images
dc exec api python -m app.etl.sync_english_names
dc exec api python -m app.etl.sync_product_signals
dc exec api python -m app.etl.sync_shipping_rules
dc exec api python -m app.etl.sync_thai_geo
dc exec api python -m app.etl.sync_home_media
dc exec api python -m app.etl.sync_cms_pages
dc exec api python -m app.etl.refresh_stock
dc exec api python -m app.etl.sync_sap_prices         # ราคาจาก SAP (ตัวนี้ตั้ง cron รายวัน)
dc exec api python -m app.etl.sync_display_items
```

> `refresh_stock` ห้ามใส่ `--mock` เด็ดขาด — มันเขียนทับจำนวนจริงด้วยเลขสุ่ม

ตรวจความปลอดภัย/บัญชีพนักงาน:

```bash
dc exec api python -m app.cli.secure audit
```

---

## อัปเดตโค้ด

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

ฐานข้อมูลกับ snapshot ราคาอยู่ใน named volume (`pgdata`, `sapdata`) ไม่หายตอน build ใหม่

## ปิด / ดูสถานะ

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml down          # ข้อมูลยังอยู่
docker compose -f docker-compose.prod.yml down -v       # ลบข้อมูลด้วย ระวัง
```

---

## ที่ต่างจากชุดรันในเครื่อง (`docker-compose.yml`)

| | รันในเครื่อง | เซิร์ฟเวอร์จริง |
|---|---|---|
| หน้าเว็บ | vite dev server (แจก source map, เปิด HMR) | ไฟล์ที่ build แล้ว เสิร์ฟด้วย nginx |
| source code | mount จากเครื่องเข้า container | อยู่ใน image เท่านั้น |
| เครื่องมือเทส | มี (pytest) | ไม่มี |
| ผู้ใช้ใน container | root | `sbapp` (uid 10001) |
| ข้อมูลตัวอย่าง | seed ให้ | ไม่ seed · และปฏิเสธถ้าสั่ง |
| พอร์ตฐานข้อมูล | ไม่เปิด | ไม่เปิด |
| `backend/.env` | mount เข้าไป | **ไม่อยู่ใน image** ส่งเข้าตอนรันผ่าน `env_file` |

---

## ยังไม่ได้ทำ

- ETL ยังเป็น `.ps1` (3 ไฟล์ใน `backend/scripts/`) — Linux รันไม่ได้ ต้องแปลงเป็น `.sh` + cron
  ไม่งั้นสินค้า/ราคาจะไม่อัปเดตเองหลังขึ้น ต้องสั่งมือตามคำสั่งข้างบน
- สำรองฐานข้อมูล (`pg_dump` ตามรอบ)
