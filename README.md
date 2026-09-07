# sbdesign — SB Sales-Assisted Commerce

เว็บ e-commerce ของ SB Design Square ที่ใช้ได้ทั้ง **ลูกค้า** (ซื้อเองจากบ้าน) และ **พนักงานขาย** (เดินตามลูกค้าในโชว์รูมด้วยแท็บเล็ต เพิ่มของเข้าตะกร้าลูกค้า ออกใบเสนอราคา)
สเปคเต็มอยู่ที่ [BUILD_PROMPT.md](BUILD_PROMPT.md) · mockup อยู่ที่ [docs/design](docs/design)

## โครงสร้าง

```
backend/   FastAPI + SQLAlchemy 2 + Alembic  (Python 3.12)
web/       React + Vite + TypeScript
docker-compose.yml   postgres + api + web
.env.example         ตัวอย่าง env ทั้งหมด
```

## รันด้วย Docker (ทางหลัก)

```bash
cp .env.example .env
docker compose up --build
```

| service | URL |
|---|---|
| web | http://localhost:5173 |
| api | http://localhost:8000 · OpenAPI ที่ http://localhost:8000/docs |
| postgres | localhost:5432 (sb / sb_secret / sbdesign) |

## ไฟล์ .env

| ไฟล์ | ใช้เมื่อ | หมายเหตุ |
|---|---|---|
| `.env` (root) | `docker compose up` | ค่า Postgres + backend ทั้งหมด (ไม่ commit — copy จาก `.env.example`) |
| `backend/.env` | รัน backend ในเครื่องด้วย python ตรง ๆ | ตั้ง `DATABASE_URL=sqlite:///./sbdesign.db` ไว้ให้รันได้ทันทีโดยไม่มี Postgres · มี Postgres เมื่อไหร่สลับเป็นบรรทัด postgresql ที่คอมเมนต์ไว้ |

## เช็คว่าเชื่อมต่อ DB ติดไหม

```bash
cd backend && .venv/Scripts/python -m app.dbcheck
```

จะพิมพ์ URL (ซ่อนรหัสผ่าน), เวลาที่ใช้ต่อ, เวอร์ชัน DB, จำนวนตาราง และ alembic revision ปัจจุบัน · exit 0 = ติด, 1 = ไม่ติดพร้อมบอกสาเหตุ
เช็ค DB อื่นโดยไม่แก้ .env: `python -m app.dbcheck --url postgresql+psycopg://sb:sb_secret@localhost:5432/sbdesign`

แบบ pytest:

```bash
cd backend && .venv/Scripts/python -m pytest tests/test_db_connection.py -v
```

- `test_engine_connects` — DB ที่ test ใช้ (sqlite) ต้องต่อได้เสมอ
- `test_external_db_connects` — ต่อ DB จริงเมื่อตั้ง env `DBCHECK_URL` (ไม่ตั้งจะ skip) เช่น PowerShell: `$env:DBCHECK_URL="postgresql+psycopg://sb:sb_secret@localhost:5432/sbdesign"; .venv/Scripts/python -m pytest tests/test_db_connection.py -v -s`

## รันในเครื่องโดยไม่ใช้ Docker

backend (ใช้ SQLite แทน Postgres ได้ทันที):

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # macOS/Linux: .venv/bin/pip
set DATABASE_URL=sqlite:///./sbdesign.db               # macOS/Linux: export DATABASE_URL=...
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.seed
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

web (ต้องมี Node 20+):

```bash
cd web
npm install
npm run dev        # http://localhost:5173  (proxy /api -> http://localhost:8000)
```

test:

```bash
cd backend && .venv/Scripts/python -m pytest
cd web && npm test
```

---

## วิธีลองแต่ละ STEP

### STEP 0 — โครงโปรเจ็ค
1. `docker compose up --build` (หรือรันในเครื่องตามด้านบน)
2. เปิด http://localhost:5173 จะเห็นหน้า placeholder ที่ fetch `/api/healthz` แล้วแสดงผล JSON `{"status":"ok", ...}`
3. `curl http://localhost:8000/healthz` ต้องได้ `{"status":"ok","app":"SB Sales App API","sap_mode":"mock","db":"postgresql"}`
4. test: `cd backend && .venv/Scripts/python -m pytest` → ผ่าน 2 เคส (healthz ok + 404)

### STEP 1 — Auth + Roles
บัญชีทดสอบ (รหัสผ่านทุกบัญชี = `1234`, สร้างโดย `python -m app.seed`)

| role | ล็อกอินด้วย | account_type |
|---|---|---|
| customer (Gold) | `089-234-4471` / `napat@email.com` / เลขสมาชิก `4400182` | customer |
| customer (Silver) | `081-222-3333` | customer |
| sales | `SA-104` (สมชาย ก. · สาขาบางนา), `SA-105` | staff |
| manager | `MG-001` | staff |
| admin | `ADM-001` | staff |

1. หน้าเว็บ → ปุ่ม **เข้าสู่ระบบ** → เลือกแท็บ ลูกค้า / พนักงานขาย → กดบัญชีทดสอบด้านล่างเพื่อกรอกอัตโนมัติ → เข้าสู่ระบบ จะเห็นสิทธิ์ของ role นั้น
2. ลูกค้ายังล็อกอินด้วย OTP ได้ (โหมดทดสอบโชว์รหัส OTP ในหน้าจอ เพราะ `OTP_DEBUG=true`) และลงทะเบียนใหม่ได้
3. API: `POST /auth/login {identifier, password, account_type}` → `{access_token, refresh_token, user}` · `GET /me` ต้องส่ง `Authorization: Bearer <access_token>`
4. endpoint ที่จำกัด role: `GET /admin/users` → sales ได้ **403**, admin ได้ 200 (ใช้ `require_role(...)` ใน `app/api/deps.py`)
5. test: `pytest tests/test_step1_auth.py` — ล็อกอิน 4 role, 401 รหัสผิด, 403 role ผิด, refresh token หมุนแล้วใบเก่าใช้ไม่ได้, register ซ้ำ 409, OTP ผิด 400

### STEP 2 — Catalog + SAP mock
- SAP adapter อยู่ที่ `backend/app/integrations/sap/` — interface `SapClient` (base.py) · `MockSapClient` (mock.py อ่าน `backend/seed/sap_mock/*.json`: แมท 20 ตัว · สต็อก 4 สาขา · โปร 3 ตัว · โซนจัดส่ง 5 โซน) · สลับด้วย `SAP_MODE=mock|rfc|http` (rfc/http มาใน STEP 12)
- `python -m app.seed` จะ sync แมทจาก mock ลงตาราง mirror (`materials`, `material_prices`, `plants`, `stock_cache`) + หมวดหมู่/แบรนด์

วิธีลอง
1. หน้าแรก http://localhost:5173 — hero / promo / หมวดหมู่ / สินค้าใหม่ / ดีล / ช้อปตามห้อง / แบรนด์ / footer ตาม mockup (`docs/design`)
2. ค้นหาด้วยชื่อ (`โซฟา`), MATNR (`10023841`) หรือบาร์โค้ด (`8850100442904`) ที่ช่องค้นหา → `GET /materials/search?q=`
3. เปิดหน้าสินค้า → กด **เช็คสต็อก** (`GET /materials/{matnr}/stock`) — ยิง SAP สดทุกครั้งและเขียน `stock_checks`
   - ล็อกอินเป็นพนักงาน (SA-104) จะเห็นทุกสาขา/คลัง + ATP · ลูกค้า/guest เห็นแค่สาขาที่เลือกจาก "รับที่สาขา" + สรุปว่าจัดส่งได้เมื่อไหร่ (ไม่เห็นสต็อกข้ามสาขา)
   - ล็อกอินเป็นลูกค้า Gold จะเห็นราคาสมาชิก (ต่ำกว่าราคาปกติ 6%) · guest เห็นราคาปกติอย่างเดียว
4. จำลอง SAP ล่ม: ใน test ใช้ `get_sap_client().fail_next(2)` → response `source=cache, stale=true` พร้อมเวลาที่ cache ถูกดึง
5. test: `pytest tests/test_step2_catalog.py` (7 เคส)

### STEP 3 — ตะกร้าลูกค้า (customer / guest)
- guest ได้ cookie `sb_anon` อัตโนมัติเมื่อเรียก `GET /cart` ครั้งแรก → ตะกร้าผูกกับ token นี้
- ล็อกอินเมื่อไหร่ (login / register / OTP) ของในตะกร้า guest ถูก **merge เข้าตะกร้าลูกค้า** และคิดราคาใหม่ตาม tier (hook ใน `cart_service.merge_guest_cart_on_login`)
- ทุกการแก้ตะกร้าเขียน `audit_logs` + `cart_item_history` · ราคาเป็น snapshot (`unit_price_snapshot`, `price_tier`)
- guest กด "ชำระเงิน" ไม่ได้ — backend คืน 401 ที่ `POST /cart/checkout-check` (UI โชว์ปุ่ม "เข้าสู่ระบบเพื่อชำระเงิน")

วิธีลอง
1. ไม่ต้องล็อกอิน เปิดหน้าสินค้า → เลือกวิธีรับ (ยกกลับจากสาขา / จัดส่ง / ส่ง+ติดตั้ง) → **ลงตะกร้า** → ไอคอนตะกร้าขึ้นจำนวน
2. เปิด /cart แก้จำนวน / ลบ / ดูยอดรวม → กดชำระเงินจะถูกบังคับให้ล็อกอิน
3. ล็อกอินเป็น ณภัทร (089-234-4471) → ของยังอยู่ในตะกร้าเดิม แต่ราคาเปลี่ยนเป็นราคาสมาชิก Gold
4. API: `GET /cart` · `POST /cart/items {matnr, qty, supply_mode?, plant_code?}` · `PATCH /cart/items/{id}` · `DELETE /cart/items/{id}` · `POST /cart/items/{id}/ack` · `POST /carts/{id}/merge {source_cart_id}`
5. test: `pytest tests/test_step3_cart.py` (5 เคส: guest→login ของยังอยู่, history/audit, ข้ามตะกร้าคนอื่น 403, พนักงานใช้ /cart ไม่ได้, แมทไม่มี 404)

### STEP 4 — โหมดเซลล์ + หลายตะกร้า
- เซลล์ (SA-104) เปิดตะกร้าได้หลายใบ (`owner_sales_id`) แต่ละใบหมดอายุอัตโนมัติใน 4 ชม. (`SALES_CART_TTL_HOURS`, ต่ออายุทุกครั้งที่ใช้งาน)
- ค้นหาลูกค้าด้วยเลขสมาชิก / เบอร์โทร / อีเมล → **ผูกลูกค้า** → ถ้าลูกค้ามีตะกร้าออนไลน์อยู่จะ merge เข้าใบที่เซลล์ถือ และลูกค้าเปิด `/cart` จะเห็นใบเดียวกัน
- ของที่เซลล์เพิ่ม → `added_by=sales`, `pending_ack=true` (ลูกค้ากด "เก็บไว้" หรือ "ลบออก")
- ปิดตะกร้า (`DELETE /sales/carts/{id}`): มีลูกค้าผูก → คืนตะกร้าให้ลูกค้า (เซลล์หมดสิทธิ์ทันที) · ไม่มีลูกค้า → abandoned
- ลูกค้า 1 คน มีเซลล์ดูแลได้ทีละคน (ผูกซ้ำจากเซลล์อื่นได้ 409)

วิธีลอง
1. แท็บ 1: ล็อกอินลูกค้า ณภัทร → ใส่ของลงตะกร้าจากบ้าน
2. แท็บ 2 (หรือ incognito): ล็อกอิน SA-104 → ไอคอนตะกร้าจะพาไป **/sales** → "เปิดตะกร้าใหม่" 3 ใบ สลับแท็บ เพิ่มของคนละใบ ของไม่ปนกัน
3. ในใบใดใบหนึ่ง ค้นหาลูกค้า `089-234` → ผูกลูกค้า → เห็น "จากตะกร้าลูกค้า" + ของที่เซลล์เพิ่มติดป้าย "รอลูกค้ายืนยัน"
4. กลับแท็บ 1 รีเฟรช `/cart` → เห็นการ์ด "พนักงานเพิ่มสินค้าให้คุณ N รายการ" (เรียลไทม์มาใน STEP 5)
5. API: `GET/POST /sales/carts` · `GET/DELETE /sales/carts/{id}` · `POST/PATCH/DELETE /sales/carts/{id}/items[/{item_id}]` · `POST/DELETE /sales/carts/{id}/attach-customer` · `GET /customers/search?q=`
6. test: `pytest tests/test_step4_sales.py` (5 เคส: ถือ 3 ตะกร้าไม่ปน, เซลล์อื่น 403, ผูกลูกค้า+merge+ack+ปิดเซสชัน, ตัดการเชื่อมต่อคืนของลูกค้า, ลูกค้าที่มีเฉพาะใน SAP)

### STEP 5 — Realtime + การยืนยันของลูกค้า
- WebSocket `WS /ws/cart/{cart_id}?token=<access_token>` (ลูกค้า/เซลล์) หรือ `?anon=<sb_anon>` (guest) — ใช้กฎสิทธิ์เดียวกับ REST, ไม่มีสิทธิ์ปิดด้วย code 1008
- เหตุการณ์: `item_added` / `item_updated` / `item_removed` / `item_acked` / `cart_merged` / `customer_attached` / `customer_detached` / `session_closed` (ส่งจาก `cart_service.emit` → `app/realtime.py`)
- ลูกค้ากด **เก็บไว้** = `POST /cart/items/{id}/ack` · **ลบออก** = `DELETE /cart/items/{id}` · ป้าย "พนักงานเพิ่มให้ · ชื่อเซลล์ · เวลา" ค้างบนบรรทัดสินค้า

วิธีลอง
1. แท็บ 1 ล็อกอินลูกค้า ณภัทร เปิด `/cart` · แท็บ 2 ล็อกอิน SA-104 เปิด `/sales` → ผูกลูกค้า 4400182 → "เพิ่มสินค้าให้ลูกค้า"
2. แท็บ 1 เด้งการ์ด "พนักงานเพิ่มสินค้าให้คุณ 1 รายการ" ภายใน 1 วินาที → กด เก็บไว้ / ลบออก → แท็บ 2 เห็นผลทันที
3. test: `pytest tests/test_step5_realtime.py` (3 เคส: เซลล์เพิ่ม→ลูกค้าได้ event/ack/remove, ไม่มีสิทธิ์ถูกปิด 1008, guest ใช้ anon token)

### STEP 6 — โปรโมชั่น + ส่วนลด
- `POST /promotions/evaluate {cart_id}` → โปรที่ **เข้าเงื่อนไข** (พร้อมยอดลดเป็นบาท) และ **ยังไม่เข้าเงื่อนไขพร้อมเหตุผลว่าขาดอะไร** + โควตาส่วนลดพนักงาน + ยอดหลังส่วนลด (ประเมินผ่าน `SapClient.evaluate_promotions` — mock ใช้กติกาใน `integrations/sap/promo_engine.py`)
- `POST /cart/{id}/discounts` — `{kind:"promotion", promo_code}` (ลูกค้า/เซลล์กดใช้โปรที่เข้าเงื่อนไข) หรือ `{kind:"staff_manual", percent, reason?}` (เซลล์ ≤ 3% ใช้ได้เลย · > 3% เป็น `pending_approval` รอผู้จัดการ)
- `GET /discount-approvals` · `POST /discount-approvals/{id}/approve|reject` (manager เท่านั้น — sales ได้ 403)
- ส่วนลดผูก **รายตะกร้า** (`applied_discounts.cart_id`) · ยอดทุกจุด (`/cart`, `/sales/carts/{id}`, `/promotions/evaluate`, ใบเสนอราคา) คำนวณจาก `promo_service.compute_totals` ฟังก์ชันเดียว → ตรงกันเสมอ · โปรที่ apply แล้วแต่ตะกร้าเปลี่ยนจนไม่เข้าเงื่อนไขจะเป็น 0 พร้อม warning

วิธีลอง
1. `/sales` ผูกลูกค้า Gold + ใส่โซฟา NORDIC → กด **เช็คโปรโมชั่น** → SEP-SOFA15 เข้าเงื่อนไข (กดใช้) · BUNDLE-BED บอกว่า "ขาดที่นอน 1 ชิ้น"
2. ใส่ส่วนลดพนักงาน 2% → ยอดในสรุปเปลี่ยนทันที · ใส่ 5% + เหตุผล → ขึ้น "รออนุมัติ" → ล็อกอิน MG-001 ไปที่ไอคอน ✓ (คำขออนุมัติส่วนลด) → อนุมัติ → ยอดหักส่วนลด
3. ฝั่งลูกค้า `/cart` กด "เช็คโปรโมชั่น" ใช้โปรที่เข้าเงื่อนไขเองได้ แต่ให้ส่วนลดพนักงานไม่ได้ (403)
4. test: `pytest tests/test_step6_promo.py` (5 เคส)

### STEP 7 — ค่าขนส่ง + คิวจัดส่ง
- `POST /delivery/quote {cart_id, postcode, address?}` → เขต/ค่าส่งฐาน/ค่าติดตั้ง (ผ่าน `SapClient.quote_delivery`, mirror ลง `delivery_zones` + `delivery_slots`) + แยกกลุ่ม **ยกกลับวันนี้ / ส่งจากคลัง / ส่ง+ติดตั้ง** + slot ว่าง 7 วัน × เช้า/บ่าย
- `POST /delivery/slots/{id}/hold {cart_id}` จองคิวชั่วคราว 15 นาที (โควตาลดทันที · คิวเต็ม 409 · หมดอายุคืนโควตาอัตโนมัติ · ย้ายคิวคืนคิวเดิม) — ยืนยันถาวรตอนออกใบเสนอราคา
- ยอดรวมทั้งบิลใน `totals`: `net_total + shipping_fee + install_fee − shipping_discount = grand_total` (+ `vat_included` 7% ที่รวมในราคา) · โปร GOLD-FREESHIP หักจากค่าส่ง

วิธีลอง
1. `/sales` → "เช็คสต็อก + คิวจัดส่ง" → ใส่รหัส ปณ. 10110 → ค่าส่ง 800 · เปลี่ยนเป็น 50000 → 3,500 · ใส่ตู้เสื้อผ้า (ต้องติดตั้ง) → มีค่าติดตั้งและกลุ่ม "ส่ง+ติดตั้ง"
2. กดเลือกคิว → "จองแล้ว" · รอบที่เต็มกดไม่ได้ (รอบบ่ายวันแรกของทุกเขตเต็มใน mock)
3. ฝั่งลูกค้า `/checkout` มีฟอร์มที่อยู่ + คำนวณค่าส่ง + เลือกคิว + สรุปยอดรวม VAT
4. test: `pytest tests/test_step7_delivery.py` (3 เคส)

### STEP 8 — Preso + ใบเสนอราคา (Quotation)
- **Preso = ใบร่างที่ยังแก้ได้** · `POST /presos {cart_id, note?}` เซฟ snapshot (สินค้า + ส่วนลด + ยอด + จัดส่ง) เป็นเลข `PRE-YYMMDD-NNNN` (เซฟซ้ำ = อัปเดตใบเดิม) · `GET /presos?mine=true&status=draft` · `POST /presos/{no}/reopen` ดึงตะกร้ากลับเข้าเซสชันเซลล์ (409 ถ้าเซลล์คนอื่นถืออยู่)
- **Quotation = ล็อกราคา/โปร แก้ไม่ได้** · `POST /presos/{no}/quotation {force?}` — ก่อนออกจะ **เช็คสต็อกสดจาก SAP** ทุกบรรทัด: ของไม่พอ → 409 พร้อมรายการที่ขาด (กด "ออกทั้งที่ของไม่พอ" = `force:true` แล้วบันทึกเป็น `stock_warnings`) · ต้องผูกลูกค้าก่อน (400) · ต้องคำนวณค่าส่งถ้ามีรายการต้องจัดส่ง (400) · มีส่วนลดค้างอนุมัติ → 409 · SAP ล่มก็ยังออกใบได้ (ใช้ราคา snapshot)
- ออกแล้ว: ยอดถูกล็อกจาก `compute_totals` (subtotal / discount_total / ค่าส่ง / VAT / `grand_total` / มัดจำ 20%) · ยืนราคา `QUOTATION_VALID_DAYS` วัน · คิวจัดส่งเปลี่ยนเป็นจองถาวร · Preso → `quoted` · ตะกร้า → `converted`
- **แก้ไม่ได้ ต้องยกเลิกแล้วออกใหม่** · `POST /quotations/{no}/cancel {reason}` → ใบเป็น `cancelled`, Preso กลับเป็น `draft`, ตะกร้ากลับมาแก้ได้, คิวจัดส่งกลับเป็น hold 15 นาที
- เอกสาร/ส่งต่อ: `GET /quotations/{no}/document` (PDF mock — HTML พร้อมพิมพ์) · `POST /quotations/{no}/send {channel:"sms"|"email"}` (mock ลง log) → ลิงก์ `/q/{no}?t=<token>` ที่ลูกค้าเปิดได้โดยไม่ต้องล็อกอิน (HMAC · token ผิด 403 · ไม่มี token และไม่ล็อกอิน 401)

วิธีลอง
1. `/sales` ผูกลูกค้า + ใส่สินค้า + ใช้โปร + เลือกคิวส่ง → กด **Save Preso** → ไปที่ "Preso ของฉัน" (`/sales/presos`) เห็นใบร่าง
2. ล็อกเอาต์/ล็อกอินใหม่ → กด **เปิด** ดึงตะกร้ากลับมาทำต่อได้ (เซลล์คนอื่นกดจะได้ 403)
3. กด **สร้าง Quotation** → ถ้าของไม่พอจะถามยืนยันก่อน → ได้หน้าใบเสนอราคา `/sales/quotations/{no}`: กด PDF / ส่ง SMS / คัดลอกลิงก์ → เปิดลิงก์ `/q/{no}?t=...` ในหน้าต่าง incognito ก็เห็นใบ
4. กด **ยกเลิก + ออกใหม่** → เด้งกลับ `/sales` พร้อมตะกร้าเดิมที่แก้ได้
5. test: `pytest tests/test_step8_quotation.py` (4 เคส)

### STEP 9 — ชำระเงิน + ส่งต่อ SAP
- `POST /quotations/{no}/payment-intent {method, kind}` — `method`: `qr_promptpay | card | installment | link` · `kind`: `full` หรือ `deposit` (มัดจำ 20%) → ได้ `payment_no` + QR payload + ลิงก์จ่าย อายุ 15 นาที (กดซ้ำได้ intent เดิม) · เปิดจากลิงก์ลูกค้า `?t=<token>` ได้โดยไม่ต้องล็อกอิน
- **ไม่มีช่องทางเงินสด** — `method:"cash"` ตอบ 400 เสมอ (เซลล์รับเงินเองไม่ได้ตามข้อกำหนด)
- `POST /webhooks/payment` — provider ยิงกลับ ต้องเซ็น `X-Signature` = HMAC-SHA256(body, `PAYMENT_WEBHOOK_SECRET`) · ลายเซ็นผิด 401 · ยิงซ้ำ idempotent (ไม่สร้าง SO ซ้ำ)
- จ่ายสำเร็จ → ใบเป็น `paid` → เรียก `SapClient.create_sales_order` → ได้ `sap_so_no` แล้วใบเป็น `converted` · **SAP ล่ม: เงินไม่หาย** ใบค้างที่ `paid` + `sap_sync_status=failed` และเข้าคิว `sap_sync_jobs` (retry 1/5/15/60/240 นาที)
- `GET /admin/sap-sync` · `POST /admin/sap-sync/run` · `POST /admin/sap-sync/{no}/retry` (manager/admin เท่านั้น — เซลล์ 403)
- `POST /checkout/quotation` — ลูกค้าสั่งเองออนไลน์: เซฟ Preso จากตะกร้าตัวเอง + ออกใบ `channel="online"` แล้วไปหน้าชำระเงิน
- `POST /payments/{no}/mock-confirm` — เฉพาะโหมด dev (`OTP_DEBUG=true`) จำลองว่า provider จ่ายสำเร็จ

วิธีลอง
1. ที่หน้าใบเสนอราคา กด **ไปหน้าชำระเงิน** → `/pay/{no}` เลือกเต็มจำนวน/มัดจำ 20% + ช่องทาง → กดชำระ → เห็น QR (mock) และหน้าจอรอผล
2. กด **จำลองจ่ายสำเร็จ (dev)** → หน้าจอขึ้น "ชำระเงินสำเร็จ" พร้อม **เลข SO** และวันนัดส่ง
3. ฝั่งลูกค้า: `/cart` → `/checkout` กรอกที่อยู่ + คำนวณค่าส่ง + เลือกคิว → **ยืนยันการสั่งซื้อ** → เด้งไปหน้าชำระเงิน
4. จำลอง SAP ล่ม: ใน pytest ใช้ `get_sap_client().fail_next(1)` → ล็อกอิน MG-001 เปิดไอคอน sync ที่ header (`/manager/sap-sync`) เห็นใบค้าง กด **ส่งใหม่** ได้เลข SO
5. test: `pytest tests/test_step9_payment.py` (5 เคส)

### STEP 10 — ประวัติ + สินค้าขายดี
- **เก็บพฤติกรรม**: `user_events` (view_material / search / add_to_cart / …) บันทึกอัตโนมัติจาก `GET /materials/{matnr}`, `GET /materials/search` และตอนใส่ตะกร้า (ทั้งฝั่งลูกค้าและเซลล์ — นับให้ลูกค้าเจ้าของตะกร้าเสมอ) · ยิงเองเพิ่มได้ที่ `POST /events` · คำค้นแยกเก็บใน `search_queries`
- guest ก็เก็บได้ (ผูกกับ `sb_anon` cookie) แล้ว **ย้ายมาเป็นของบัญชีตอนล็อกอิน** พร้อมกับตะกร้า
- `GET /me/recently-viewed` (ดูล่าสุด · guest ใช้ได้) · `GET /me/wishlist` + `POST /me/wishlist/{matnr}` (toggle) · `GET /me/bought-again`
- **ประวัติการสั่งซื้อ mirror จาก SAP**: `GET /me/orders` sync `order_history` + `order_history_lines` จาก `SapClient.get_order_history` ทุกครั้ง (mock สุ่มแบบ deterministic ต่อเลขลูกค้า) · `GET /me/orders/{so_no}` — ของคนอื่นตอบ 404
- **job รายวัน**: `POST /admin/jobs/daily-stats?days=30` (manager/admin) ย่อย events + ยอดขายลง `material_daily_stats` แล้ว refresh `best_sellers` · คะแนน = ยอดขาย×10 + ใส่ตะกร้า×2 + วิว×0.2 (ย้อนหลัง 30 วัน) · ของจริงตั้งเป็น cron รายวัน
- `GET /best-sellers` (อันดับจากยอดจริง ไม่ใช่ tag ที่ตั้งมือ) · `GET /admin/top-searches` ดูคำค้นยอดฮิต
- หน้าเว็บ: หน้าแรกมีแถบ **สินค้าขายดีจริงจากยอดสั่งซื้อ** + **ดูล่าสุด** · หน้าสินค้ามีปุ่มหัวใจเก็บรายการโปรด · `/account` มี 3 แท็บ: ประวัติการสั่งซื้อ (กดดูรายการในใบได้) · รายการโปรด · ดูล่าสุด

วิธีลอง
1. เปิดสินค้าสัก 2-3 ตัว แล้วใส่ตะกร้า → เช็ค DB: `select event, matnr from user_events order by created_at desc limit 10;` เห็น row ทันที
2. หน้าแรกเลื่อนลง เห็นแถบ **ดูล่าสุด** ขึ้นตามที่เพิ่งดู (ยังไม่ล็อกอินก็เห็น เพราะผูกกับ cookie) → ล็อกอินแล้วยังอยู่ครบ
3. กดหัวใจที่หน้าสินค้า → ไปที่ไอคอนหัวใจบน header (`/account/wishlist`) เห็นรายการ กดเอาออกได้
4. `/account/orders` — ดึงประวัติจาก SAP mock มาแสดง กดที่ใบเพื่อดูรายการสินค้าในออร์เดอร์
5. ล็อกอิน MG-001 แล้ว `POST /admin/jobs/daily-stats` → เรียก `GET /best-sellers` เทียบก่อน/หลัง จะเห็นอันดับเปลี่ยนตามยอดจริง
6. test: `pytest tests/test_step10_history.py` (5 เคส)
