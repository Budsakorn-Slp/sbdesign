# SB Sales-Assisted Commerce — เอกสารสั่งงาน (Build Prompt)

> วิธีใช้: เปิดโปรเจ็คว่างในเครื่อง แล้ววางไฟล์นี้ไว้ที่ root ชื่อ `BUILD_PROMPT.md`
> จากนั้นสั่ง AI coding agent ว่า:
> **"อ่าน BUILD_PROMPT.md แล้วทำ STEP 0 ให้เสร็จก่อน หยุดรอให้ฉันตรวจ แล้วค่อยไป STEP ถัดไป ห้ามข้ามขั้น ห้ามทำหลาย STEP รวบเดียว"**

---

## 0. บริบทโปรเจ็ค (อ่านก่อนเขียนโค้ดบรรทัดแรก)

**ชื่อระบบ:** SB Sales App — เว็บ e-commerce ที่ใช้ได้ทั้งลูกค้าและพนักงานขาย (sales-assisted commerce)

**โจทย์ธุรกิจ**
- ลูกค้าซื้อเองจากบ้านได้ (เหมือน e-commerce ปกติ)
- พนักงานขาย (เซลล์) เดินตามลูกค้าในโชว์รูมด้วยแท็บเล็ต ค้นหาสินค้า เช็คสต็อก แล้วใส่ตะกร้าให้ลูกค้าได้
- ลูกค้าที่ใส่ตะกร้ามาจากบ้าน เมื่อมาถึงร้าน เซลล์ต้อง "จับคู่" กับตะกร้าใบนั้นและเพิ่มของเข้าไปได้
- 1 เซลล์ต้องถือได้หลายตะกร้าพร้อมกัน (ดูแลลูกค้าหลายคนสลับกันไปมา)
- ปลายทางของฝั่งเซลล์คือ **Quotation (ใบเสนอราคา)** → ระบบหลังบ้านจะไป convert เป็น Sales Order ใน SAP

**Tech stack ที่กำหนด**
| ชั้น | เทคโนโลยี |
|---|---|
| Backend | Python 3.12 + FastAPI + SQLAlchemy 2.x + Alembic |
| Database | PostgreSQL 16 |
| Auth | JWT (access + refresh), bcrypt/argon2 |
| Realtime | WebSocket (FastAPI native) |
| Frontend | React + Vite + TypeScript |
| Test | pytest (backend), vitest (frontend) |
| Dev env | docker compose (postgres + api + web) |

**ขอบเขต (สำคัญมาก)**
- ระบบ SAP **มีทีมอื่นทำ service ให้** เราไม่เขียน integration จริงในเฟสนี้
- ทุกจุดที่ต้องคุยกับ SAP ให้สร้างเป็น **adapter layer + mock implementation** ที่สลับเป็นของจริงได้ด้วย env var เดียว
- ห้ามเขียน SQL ตัดสต็อกจริง / ห้ามสร้าง Sales Order เอง

**Definition of Done ของทุก STEP**
1. โค้ดรันได้ด้วย `docker compose up` โดยไม่มี error
2. มี test ครอบ happy path + 1 error case
3. มี seed data ให้กดลองได้ทันที
4. อัปเดต `README.md` ส่วน "วิธีลอง STEP นี้"
5. commit ด้วย message `step-N: <สิ่งที่ทำ>`

---

## 1. บทบาทผู้ใช้ (Roles)

| role | ทำอะไรได้ | ทำไม่ได้ |
|---|---|---|
| `guest` (ไม่ล็อกอิน) | ดูสินค้า, ใส่/ลบตะกร้าของตัวเอง | ชำระเงิน, เห็นราคาสมาชิก |
| `customer` | แก้ตะกร้า, ชำระเงินเอง, เห็นราคาสมาชิก, ลบของที่เซลล์เพิ่มให้, ดูประวัติซื้อ | เห็นต้นทุน, เห็นสต็อกข้ามสาขา, เครื่องมือเซลล์ |
| `sales` | ค้นหา MATNR, เช็คสต็อกทุกสาขา, เพิ่มของในตะกร้าลูกค้า, ถือหลายตะกร้า, ใส่ส่วนลด ≤ 3%, Save Preso, ออก Quotation | รับเงินเอง (เงินสดต้องผ่านแคชเชียร์), ส่วนลด > 3% ต้องขออนุมัติ |
| `manager` | ทุกอย่างของ sales + อนุมัติส่วนลดเกินโควตา + ดูรายงานยอดขายทีม | — |
| `admin` | จัดการผู้ใช้, ตั้งค่าระบบ, ดู audit log | — |

**กฎสิทธิ์ที่ต้อง enforce ที่ backend (ไม่ใช่แค่ซ่อน UI)**
- เซลล์เข้าถึงตะกร้าได้เฉพาะเมื่อ `carts.owner_sales_id = ตัวเอง` และ `carts.status = 'open'`
- เมื่อปิดตะกร้า/จบเซสชัน สิทธิ์ต้องหมดทันที (สำคัญเรื่อง PDPA)
- ทุกการเปลี่ยนแปลงตะกร้าเขียน `audit_logs` + `cart_item_history`

---

## 2. โฟลว์หลักของเซลล์ 9 สเต็ป (ต้องทำได้ครบตามลำดับนี้)

1. **ค้นหาแมท** — ชื่อสินค้า / MATNR / บาร์โค้ด (สแกนได้)
2. **เช็คสต็อก** — รายสาขา + คลัง + ATP date (ยิง SAP สดทุกครั้ง)
3. **ลงตะกร้า** — ระบุจำนวน + แหล่งจ่ายของ (สาขา/คลัง) + วิธีรับ (ยกกลับ / ส่ง / ติดตั้ง)
4. **ไปหน้าตะกร้า** — แก้จำนวน / ลบ / ใส่หมายเหตุ
5. **ค้นหา Customer** — จากเลขสมาชิก / เบอร์โทร / อีเมล → ถ้าลูกค้ามีตะกร้าออนไลน์อยู่แล้วให้ **merge เป็นใบเดียว**
6. **เช็คโปรโมชั่น** — โปรที่เข้าเงื่อนไข + โปรที่ยังไม่เข้าเงื่อนไข (บอกว่าขาดอะไร) + ส่วนลดพนักงาน 0–3%
7. **เช็คสต็อก + คิวจัดส่งอีกครั้ง** — ยืนยัน ATP, คำนวณค่าขนส่งตามเขต, จอง slot จัดส่ง
8. **Save Preso** — เซฟใบร่าง ดึงกลับมาทำต่อได้ (ลูกค้ากลับมาวันหลัง)
9. **สร้าง Quotation → ไปหน้าชำระเงิน** — ล็อกราคา/โปร แล้วส่งต่อ service ไป convert เป็น SO ใน SAP

**โฟลว์ฝั่งลูกค้าที่ต้องมี**
- เห็นการ์ดแจ้งเตือนเมื่อเซลล์เพิ่มของ: "พนักงานเพิ่มสินค้าให้คุณ N รายการ" + ปุ่ม **เก็บไว้ / ลบออก**
- สินค้าที่เซลล์เพิ่มติดป้ายถาวร "เพิ่มโดย <ชื่อเซลล์> · <เวลา>"
- รับ Quotation ทางลิงก์ SMS/อีเมล แล้วจ่ายเองได้
- ติดตามสถานะแยกตามวิธีรับของ (ยกกลับแล้ว / กำลังส่ง / รอนัดติดตั้ง) + เลข SO

---

## 3. Database schema

### 3.1 ตารางที่เราสร้างเอง (Group A)

```
users(id PK, role ENUM[customer,sales,manager,admin], phone UQ, email UQ NULL,
      password_hash NULL, sap_customer_no NULL, staff_code NULL, branch_id NULL,
      tier NULL, is_guest BOOL, created_at, updated_at)

user_sessions(id PK, user_id FK, refresh_token_hash, device, ip, expires_at, created_at)

carts(id PK, customer_user_id FK NULL, owner_sales_id FK NULL, anon_token NULL,
      label, no UQ, status ENUM[open,merged,converted,abandoned],
      merged_into_cart_id FK NULL, created_at, updated_at)

cart_items(id PK, cart_id FK, matnr, sku, name_snapshot, variant_snapshot,
           qty INT, unit_price_snapshot NUMERIC(12,2),
           added_by ENUM[customer,sales], added_by_user_id FK, added_at,
           pending_ack BOOL DEFAULT false,
           supply_mode ENUM[takeaway,ship,install,pickup],
           plant_code NULL, atp_date NULL)

presos(id PK, preso_no UQ, cart_id FK, sales_user_id FK, customer_user_id FK NULL,
       snapshot_json JSONB, status ENUM[draft,quoted,expired,cancelled], note, created_at, updated_at)

quotations(id PK, quotation_no UQ, preso_id FK, subtotal, discount_total,
           shipping_fee, vat, grand_total, valid_until DATE, pdf_url NULL,
           sap_so_no NULL, sap_sync_status ENUM[pending,ok,failed],
           status ENUM[issued,paid,converted,expired,cancelled], created_at)

quotation_lines(id PK, quotation_id FK, matnr, name, qty, unit_price,
                line_discount, supply_mode, plant_code, added_by)

applied_discounts(id PK, cart_id FK NULL, quotation_id FK NULL,
                  kind ENUM[promotion,member_price,staff_manual], promo_code NULL,
                  amount NUMERIC(12,2), applied_by_user_id FK,
                  approved_by_user_id FK NULL, approved_at NULL, created_at)

stock_checks(id PK, user_id FK, matnr, plant_code, qty_returned,
             atp_date NULL, source ENUM[sap,cache], checked_at)

audit_logs(id PK, actor_user_id FK, role, action, target_type, target_id,
           payload JSONB, created_at)
```

### 3.2 ตาราง mirror/cache จาก SAP (Group B)

```
materials(matnr PK, sku, barcode, name_th, name_en, category_id, brand_id,
          image_url, requires_install BOOL, is_takeaway_ok BOOL, volume, weight, synced_at)
material_prices(matnr FK, tier, price NUMERIC, valid_from, valid_to)
plants(plant_code PK, name, type ENUM[store,warehouse], zone_codes[])
stock_cache(matnr, plant_code, on_hand INT, reserved INT, atp_date, fetched_at)  -- PK(matnr,plant_code)
promotions(code PK, title, condition JSONB, discount_type, discount_value,
           stackable BOOL, valid_from, valid_to)
delivery_zones(postcode PK, zone, base_fee, install_fee)
delivery_slots(id PK, date, period ENUM[am,pm], zone, quota INT, booked INT)
```

### 3.3 ประวัติ / analytics (Group C)

```
user_events(id PK, user_id FK NULL, anon_token NULL, session_id,
            event_type ENUM[page_view,product_view,search,add_to_cart,remove_from_cart,
                            checkout_start,purchase],
            matnr NULL, payload JSONB, device, branch_id NULL, created_at)
            -- partition by month

search_queries(id PK, user_id NULL, query, result_count, clicked_matnr NULL, created_at)

cart_item_history(id PK, cart_id FK, matnr, action ENUM[add,update,remove],
                  qty_before, qty_after, added_by, actor_user_id FK, created_at)

order_history(id PK, sap_so_no UQ, quotation_no, customer_user_id FK,
              sales_user_id FK NULL, order_date, grand_total,
              channel ENUM[online,in_store_assisted], fulfillment_status)
order_history_lines(id PK, order_id FK, matnr, name, qty, unit_price, discount)

material_daily_stats(date, matnr, branch_id, views, add_to_cart, units_sold,
                     revenue, conversion_rate)  -- PK(date,matnr,branch_id)
best_sellers  -- MATERIALIZED VIEW: อันดับจาก units_sold 7/30/90 วัน แยกหมวด/สาขา

recently_viewed(user_id, matnr, last_viewed_at)  -- PK(user_id,matnr), เก็บล่าสุด 20
wishlists(id PK, user_id FK, matnr, note, created_at)
```

### 3.4 สิ่งที่ SAP เป็นเจ้าของ — ห้ามสร้างตารางซ้ำ (Group D)
Sales Order, Delivery Order, ใบกำกับภาษี, สต็อกจริง/การตัดสต็อก, master ลูกค้าเชิงบัญชี, การรับชำระเงิน
→ ฝั่งเราเก็บแค่ `sap_so_no` + `sap_sync_status`

### 3.5 กฎข้อมูล 4 ข้อ
1. ราคาในตะกร้าเป็น **snapshot** เสมอ — ห้าม join ราคาปัจจุบันตอนแสดง Quotation
2. ทุกการแก้ตะกร้าเขียน `audit_logs` + `cart_item_history` พร้อม role ผู้ทำ
3. เซลล์เห็นตะกร้าลูกค้าได้เฉพาะตอนถือตะกร้าใบนั้น
4. Quotation เมื่อ `issued` แล้ว **ห้ามแก้** — ต้อง cancel แล้วออกใหม่

---

## 4. SAP adapter (mock ก่อน)

สร้าง `app/integrations/sap/` ที่มี interface เดียวและ 2 implementation (`MockSapClient`, `HttpSapClient`) สลับด้วย `SAP_MODE=mock|http`

```python
class SapClient(Protocol):
    def search_materials(self, q: str, limit: int) -> list[Material]: ...
    def get_stock(self, matnr: str) -> list[StockRow]: ...        # ต่อ plant + atp_date
    def evaluate_promotions(self, cart: CartDTO, customer: CustomerDTO | None) -> PromoResult: ...
    def quote_delivery(self, cart: CartDTO, postcode: str) -> DeliveryQuote: ...
    def create_sales_order(self, quotation_no: str) -> SapSoResult: ...
    def get_customer(self, key: str) -> CustomerDTO | None: ...
```

- `MockSapClient` อ่านจาก `seed/sap_mock/*.json` (แมท 20 ตัว, สต็อก 4 สาขา, โปร 3 ตัว, โซนจัดส่ง 5 โซน)
- ทุก call ของ `get_stock` เขียน `stock_checks` เสมอ พร้อม `source`
- ตั้ง timeout 3 วิ + retry 1 ครั้ง + fallback อ่าน `stock_cache` พร้อมส่ง flag `stale=true` กลับไปให้ UI โชว์เวลา

---

## 5. API ที่ต้องมี

```
POST   /auth/register                 POST /auth/login            POST /auth/refresh
POST   /auth/otp/request              POST /auth/otp/verify       GET  /me

GET    /materials/search?q=&category=&limit=
GET    /materials/{matnr}
GET    /materials/{matnr}/stock              # ยิง SAP สด + log
GET    /best-sellers?range=7|30|90&category=

GET    /cart                                  # ตะกร้าของ user/anon ปัจจุบัน
POST   /cart/items                            # {matnr, qty, supply_mode, plant_code}
PATCH  /cart/items/{id}                       # qty / supply_mode
DELETE /cart/items/{id}
POST   /cart/items/{id}/ack                   # ลูกค้ากด "เก็บไว้"
POST   /carts/{id}/merge                      # {source_cart_id}

GET    /sales/carts                           # ตะกร้าทั้งหมดที่เซลล์ถืออยู่ (แท็บ)
POST   /sales/carts                           # เปิดตะกร้าใหม่
DELETE /sales/carts/{id}                      # ปิดตะกร้า
POST   /sales/carts/{id}/attach-customer      # {customer_key}
DELETE /sales/carts/{id}/attach-customer
GET    /customers/search?q=                   # เลขสมาชิก / เบอร์ / อีเมล

POST   /promotions/evaluate                   # {cart_id} → เข้าเงื่อนไข / ไม่เข้า + เหตุผล
POST   /cart/{id}/discounts                   # staff manual ≤3% ; เกินต้องขออนุมัติ
POST   /discount-approvals/{id}/approve       # manager only

POST   /delivery/quote                        # {cart_id, postcode} → fee + slots ว่าง
POST   /delivery/slots/{id}/hold               # จองคิวชั่วคราว 15 นาที

POST   /presos                                # Save Preso
GET    /presos?status=&mine=true
GET    /presos/{no}
POST   /presos/{no}/quotation                 # สร้าง Quotation (ยิงเช็คสต็อกสดก่อน)
GET    /quotations/{no}                       # ลูกค้าเปิดจากลิงก์ได้ (signed token)
POST   /quotations/{no}/payment-intent        # QR / payment link / มัดจำ 20%
POST   /webhooks/payment                      # ชำระสำเร็จ → เรียก create_sales_order

GET    /orders                                # ประวัติซื้อของลูกค้า
GET    /orders/{sap_so_no}

WS     /ws/cart/{cart_id}                     # เหตุการณ์ item_added / item_removed / customer_attached
POST   /events                                # bulk user_events จาก frontend
GET    /admin/reports/sales-by-staff
```

---

## 6. แผนงานทีละ STEP (ทำตามลำดับ หยุดให้ตรวจทุกขั้น)

### STEP 0 — โครงโปรเจ็ค
- monorepo: `backend/`, `web/`, `docker-compose.yml`, `.env.example`, `README.md`
- FastAPI hello + PostgreSQL + Alembic init + healthcheck `/healthz`
- Vite React TS + proxy ไป api
- **ตรวจ:** `docker compose up` แล้วเปิด web เห็นหน้า placeholder ที่ fetch `/healthz` ได้

### STEP 1 — Auth + Roles
- ตาราง `users`, `user_sessions`; register/login/refresh; JWT มี `role`
- dependency `require_role(...)` สำหรับป้องกัน endpoint
- seed 4 บัญชี: customer(Gold), sales(SA-104), manager, admin
- หน้า login ที่เลือกประเภทบัญชี (ลูกค้า / พนักงาน) + ปุ่มบัญชีทดสอบ
- **ตรวจ:** ล็อกอินทั้ง 4 บัญชี, endpoint ที่จำกัด role คืน 403 ถูกต้อง

### STEP 2 — Catalog + SAP mock
- ตาราง `materials`, `material_prices`, `plants`, `stock_cache` + seed จาก mock json
- `SapClient` + `MockSapClient`; `/materials/search`, `/materials/{matnr}/stock`
- เขียน `stock_checks` ทุกครั้งที่เช็ค; รองรับ fallback + flag `stale`
- **ตรวจ:** ค้นด้วยชื่อและ MATNR ได้, เช็คสต็อกคืนหลายสาขาพร้อม ATP, มี row ใน `stock_checks`

### STEP 3 — ตะกร้าลูกค้า (customer / guest)
- ตาราง `carts`, `cart_items`, `cart_item_history`
- guest cart ผูก `anon_token` (cookie) → merge เข้าบัญชีเมื่อล็อกอิน
- หน้าตะกร้าฝั่งลูกค้า: แก้จำนวน, ลบ, ยอดรวม
- guest กดชำระเงินไม่ได้ (ต้องล็อกอิน) — enforce ที่ backend
- **ตรวจ:** ใส่ของแบบไม่ล็อกอิน → ล็อกอิน → ของยังอยู่ในตะกร้าเดิม

### STEP 4 — โหมดเซลล์ + หลายตะกร้า
- `/sales/carts` CRUD, `owner_sales_id`, แท็บสลับตะกร้าใน UI
- ค้นหาลูกค้า + attach/detach + merge ตะกร้าลูกค้าเข้าใบที่ถืออยู่
- เพิ่มของแทนลูกค้า → `added_by='sales'`, `pending_ack=true`
- **ตรวจ:** เซลล์ถือ 3 ตะกร้าสลับไปมา ของไม่ปนกัน; แก้ตะกร้าที่ไม่ใช่ของตัวเองได้ 403

### STEP 5 — Realtime + การยืนยันของลูกค้า
- WebSocket `/ws/cart/{id}`; เซลล์เพิ่มของ → มือถือลูกค้าเด้งการ์ดทันที
- `POST /cart/items/{id}/ack` = เก็บไว้, `DELETE` = ลบออก
- ป้าย "เพิ่มโดย <เซลล์> · <เวลา>" ค้างบนบรรทัดสินค้า
- **ตรวจ:** เปิด 2 แท็บ (เซลล์/ลูกค้า) เพิ่มของแล้วเห็นสดภายใน 1 วินาที

### STEP 6 — โปรโมชั่น + ส่วนลด
- ตาราง `promotions`, `applied_discounts`; `/promotions/evaluate`
- คืนทั้งโปรที่เข้าเงื่อนไข **และไม่เข้าเงื่อนไขพร้อมเหตุผล**
- ส่วนลดพนักงาน ≤3% ทำได้เลย, >3% สร้างคำขออนุมัติให้ manager
- ส่วนลดผูก **รายตะกร้า** (ไม่ใช่ global) และไม่มีผลกับตะกร้าลูกค้าที่เซลล์ไม่ได้ถือ
- **ตรวจ:** ยอดรวมในตะกร้าและใน Quotation หักส่วนลดตรงกันทุกจุด

### STEP 7 — ค่าขนส่ง + คิวจัดส่ง
- ตาราง `delivery_zones`, `delivery_slots`; `/delivery/quote`, `/delivery/slots/{id}/hold`
- แยกตะกร้าเป็นกลุ่ม: ยกกลับวันนี้ / ส่งจากคลัง / ส่ง+ติดตั้ง
- **ตรวจ:** เปลี่ยนรหัสไปรษณีย์ → ค่าส่งเปลี่ยน; จอง slot แล้วโควตาลด; slot เต็มกดไม่ได้

### STEP 8 — Preso + Quotation
- ตาราง `presos`, `quotations`, `quotation_lines`
- Save Preso (snapshot_json), ลิสต์ Preso ของฉัน, ดึงกลับมาแก้
- สร้าง Quotation: **ยิงเช็คสต็อกสดก่อน** ถ้าของไม่พอให้เตือนก่อนออกเอกสาร
- ออก PDF + ส่งลิงก์ (mock ส่งอีเมล/SMS ลง log ได้)
- Quotation `issued` แล้วแก้ไม่ได้ (cancel + ออกใหม่)
- **ตรวจ:** Save Preso → ปิดเบราว์เซอร์ → เปิดใหม่ → ดึง Preso มาออก Quotation ได้

### STEP 9 — ชำระเงิน + ส่งต่อ SAP
- `/quotations/{no}/payment-intent` (QR / link / มัดจำ 20%), `/webhooks/payment`
- ชำระสำเร็จ → เรียก `create_sales_order` → เก็บ `sap_so_no`, `sap_sync_status`
- retry queue เมื่อ SAP ล่ม + หน้า admin ดูรายการ `failed`
- เซลล์ห้ามรับเงินสด (ไม่มี endpoint ให้ทำ)
- **ตรวจ:** จ่ายผ่าน mock สำเร็จ → ลูกค้าเห็นเลข SO และสถานะจัดส่ง

### STEP 10 — ประวัติ + สินค้าขายดี
- ตาราง `user_events` (partition), `search_queries`, `recently_viewed`, `wishlists`
- `order_history` + `order_history_lines` (mirror จาก mock SAP)
- job รายวันสร้าง `material_daily_stats` + refresh `best_sellers`
- หน้าเว็บ: แถบสินค้าขายดี, ดูล่าสุด, ประวัติการสั่งซื้อ, รายการโปรด
- **ตรวจ:** คลิกดูสินค้า/ใส่ตะกร้า → เห็น row ใน `user_events`; รัน job แล้ว best sellers เปลี่ยนอันดับ

### STEP 11 — สิทธิ์ · audit · PDPA
- ตรวจซ้ำทุก endpoint ด้วย matrix สิทธิ์ในข้อ 1 (เขียน test ครอบทุกช่อง)
- ปิดตะกร้า/จบเซสชัน → เซลล์เข้าถึงไม่ได้อีก
- consent เก็บพฤติกรรมเพื่อการตลาด (แยกจากการใช้งานทั่วไป)
- endpoint ลบ/anonymize ข้อมูลรายบุคคล
- **ตรวจ:** test สิทธิ์ผ่านทั้งหมด; ขอลบข้อมูลแล้ว events ไม่ระบุตัวบุคคลได้อีก

### STEP 12 — เตรียมต่อ SAP จริง + ส่งมอบ
- `HttpSapClient` ตาม contract ข้อ 4 (ยังไม่ต้องมี endpoint จริงก็ทำ test ด้วย mock server ได้)
- เอกสาร: ER diagram, OpenAPI, คู่มือติดตั้ง, checklist สิ่งที่ต้องขอจากทีม SAP
- **ตรวจ:** สลับ `SAP_MODE=http` ชี้ mock server แล้วระบบยังทำงานครบโฟลว์

---

## 7. สิ่งที่ยังต้องเคาะกับผู้เกี่ยวข้อง (ให้ agent ถามก่อนเดา)
1. โปรโมชั่น/ส่วนลดคำนวณที่ SAP หรือฝั่งเรา (มีผลกับ response time)
2. เลข Quotation ใครออก — ระบบเรา หรือ SAP
3. ลูกค้าใหม่ walk-in ต้องมี `sap_customer_no` ก่อนออก Quotation ไหม
4. โควตาส่วนลดเซลล์จริงกี่ % และใครอนุมัติ
5. เซลล์ดูประวัติซื้อย้อนหลังของลูกค้าได้แค่ไหน (PDPA)
6. อายุการถือตะกร้าของเซลล์ (แนะนำหมดอายุอัตโนมัติ 4 ชม.)
