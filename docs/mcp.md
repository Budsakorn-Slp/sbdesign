# MCP Server ของ SB Sales App

ต่อ Claude เข้ากับระบบขาย เพื่อให้ **ค้นหาสินค้า · เช็คสต็อกกับ SAP · ออกใบเสนอราคา** ได้จากห้องแชท

- โค้ด: `backend/app/mcp/` (`server.py` โปรโตคอล · `tools.py` เครื่องมือ · `api.py` ตัวคุยกับ backend)
- เทส: `backend/tests/test_step13_mcp.py`
- โปรโตคอล: MCP over stdio (JSON-RPC 2.0) เวอร์ชัน `2025-06-18` เขียนเองด้วย stdlib + `httpx` **ไม่ต้องลงแพ็กเกจเพิ่ม**

---

## 1. สถาปัตยกรรม

```
Claude  ──stdio(JSON-RPC)──►  app.mcp.server  ──HTTP──►  FastAPI backend  ──►  SAP RFC gateway
                                                              │
                                                              └──►  MySQL/SQLite (สินค้า ตะกร้า ใบเสนอราคา)
```

**MCP ไม่แตะฐานข้อมูลโดยตรง** ทุกอย่างวิ่งผ่าน REST API ตัวเดียวกับที่หน้าเว็บใช้ ผลคือ:

| เรื่อง | ได้อะไร |
| --- | --- |
| สิทธิ์ | ใช้ `require_role("sales","manager")` ตัวเดิม — Claude ทำได้ไม่เกินที่เซลล์คนนั้นทำได้ |
| ราคา/ส่วนลด/VAT | คิดที่ `promo_service.compute_totals` จุดเดียว Claude ไม่คำนวณเงินเอง |
| เช็คสต็อก | ใช้เส้นทางเดียวกับปุ่มบนหน้าเว็บ — ยิงทั้งบิลครั้งเดียวเสมอ |
| ร่องรอย | ทุกครั้งที่เช็คสต็อก/ออกเอกสาร ลง `audit_logs` เหมือนเซลล์กดเอง |

---

## 2. ติดตั้ง

### 2.1 เตรียม backend

MCP เป็นแค่หน้าบ้าน — ต้องมี backend รันอยู่ก่อน

```bat
cd C:\Users\Budsakorn.s\Documents\sbdesign\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

ต้องขึ้นที่ **พอร์ต 8000** (ค่าเริ่มต้นของ `SB_API_BASE`)

### 2.2 ตัวแปรสภาพแวดล้อม

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
| --- | --- | --- |
| `SB_API_BASE` | `http://localhost:8000` | ที่อยู่ backend |
| `SB_MCP_STAFF_CODE` | — | **จำเป็น** รหัสพนักงานที่ให้ MCP ใช้ (บทบาท sales หรือ manager) |
| `SB_MCP_STAFF_PASSWORD` | — | **จำเป็น** รหัสผ่านของบัญชีนั้น |
| `SB_MCP_ALLOW_WRITE` | `1` | ตั้ง `0` = เปิดเฉพาะเครื่องมืออ่าน (ค้นหา/เช็คสต็อก) ตัวที่แก้ข้อมูลจะหายจากรายการทันที |
| `SB_MCP_TIMEOUT` | `60` | วินาที — ตะกร้าใหญ่ SAP คิดนาน |

> **ความปลอดภัย** รหัสผ่านอยู่ในไฟล์ config ของ Claude ซึ่งอยู่นอก repo — **ห้ามใส่ลงโค้ดหรือ commit**
> แนะนำให้เปิดบัญชีเซลล์แยกไว้ให้ MCP โดยเฉพาะ (เช่น `SA-MCP`) จะได้แยก audit log ออกจากคนจริงได้

### 2.3 ต่อกับ Claude Desktop

แก้ไฟล์ `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "sbdesign": {
      "command": "C:\\Users\\Budsakorn.s\\Documents\\sbdesign\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.mcp.server"],
      "cwd": "C:\\Users\\Budsakorn.s\\Documents\\sbdesign\\backend",
      "env": {
        "SB_API_BASE": "http://localhost:8000",
        "SB_MCP_STAFF_CODE": "SA-104",
        "SB_MCP_STAFF_PASSWORD": "••••••",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

ปิด–เปิด Claude Desktop ใหม่ แล้วดูว่ามีเครื่องมือของ `sbdesign` ขึ้นมาไหม

### 2.4 ต่อกับ Claude Code

```bat
claude mcp add sbdesign --env SB_MCP_STAFF_CODE=SA-104 --env SB_MCP_STAFF_PASSWORD=xxxx -- C:\Users\Budsakorn.s\Documents\sbdesign\backend\.venv\Scripts\python.exe -m app.mcp.server
```

### 2.5 ทดสอบด้วยมือ (ไม่ต้องมี Claude)

```bat
cd backend
echo {"jsonrpc":"2.0","id":1,"method":"tools/list"} | .venv\Scripts\python.exe -m app.mcp.server
```

ได้รายชื่อเครื่องมือกลับมา = โปรโตคอลใช้ได้ (ขั้นนี้ยังไม่ล็อกอิน backend)

---

## 3. เครื่องมือทั้งหมด

### สินค้า (อ่านอย่างเดียว)

| เครื่องมือ | ใส่อะไร | ได้อะไร |
| --- | --- | --- |
| `search_products` | `q`, `category`, `room`, `brand[]`, `min_price`, `max_price`, `discount_only`, `sort`, `limit`, `offset` | รายการสินค้า + MATNR + ราคา (โชว์เฉพาะ MATNR ขึ้นต้น 19 ตามที่ตั้งไว้ใน `catalog_matnr_prefixes`) |
| `get_product` | `matnr` | รายละเอียด สเปก ขนาด สีอื่นของรุ่นเดียวกัน |
| `list_categories` | — | ต้นไม้หมวดที่มีของขายจริง (เอา `id` ไปกรองต่อ) |

### สต็อก (อ่านอย่างเดียว แต่ยิง SAP จริง)

| เครื่องมือ | ใส่อะไร | ได้อะไร |
| --- | --- | --- |
| `check_stock` | `items[{matnr, qty}]` (สูงสุด 25 บรรทัด), `customer_no` | ผลเช็คทั้งชุดในการยิงครั้งเดียว |
| `check_cart_stock` | `cart_id` | เช็คทุกอย่างในตะกร้าใบนั้นครั้งเดียว |

### ลูกค้า / ตะกร้า

| เครื่องมือ | ใส่อะไร |
| --- | --- |
| `search_customers` | `q` (เลขสมาชิก / เบอร์ / อีเมล) |
| `list_carts` | — |
| `open_cart` | `label` |
| `view_cart` | `cart_id` |
| `add_item` | `cart_id`, `matnr`, `qty`, `supply_mode` |
| `remove_item` | `cart_id`, `item_id` |
| `attach_customer` | `cart_id`, `customer_key` |

### ค่าส่ง / คิว

| เครื่องมือ | ใส่อะไร | หมายเหตุ |
| --- | --- | --- |
| `quote_delivery` | `cart_id`, `postcode`, `address` | คืนค่าส่งตามเขต + คิวว่าง |
| `pick_slot` | `cart_id`, `slot_id` | จองคิวไว้ 15 นาที |

### ใบเสนอราคา

| เครื่องมือ | ใส่อะไร | หมายเหตุ |
| --- | --- | --- |
| `create_quotation` | `cart_id`, `note`, `force` | เซฟ Preso + ออก Quotation ในขั้นตอนเดียว · backend ยิงเช็คสต็อกสดก่อนเสมอ |
| `get_quotation` | `quotation_no` | |
| `list_quotations` | — | |
| `cancel_quotation` | `quotation_no`, `reason` | ออกแล้วแก้ไม่ได้ ต้องยกเลิกแล้วออกใหม่ |

---

## 4. ลำดับงานปกติ

```
search_products               ค้นของที่ลูกค้าอยากได้ → ได้ MATNR
check_stock                   เช็คของ "ทุกตัวพร้อมกัน" ก่อนคุยราคา
search_customers              หาลูกค้า
open_cart → attach_customer   เปิดใบ + ผูกลูกค้า (ผูกก่อน ราคาจะได้เป็นเรตสมาชิก)
add_item × n                  ใส่ของ
quote_delivery → pick_slot    ถ้ามีรายการที่ต้องส่ง/ติดตั้ง
create_quotation              ออกเอกสาร → ได้ QT-YYMMDD-#### + ลิงก์เอกสาร
```

ลิงก์เอกสารที่คืนมา (`document_url`) เปิดได้ที่ `http://localhost:8000/quotations/<เลขที่>/document`

**สิ่งที่ backend บังคับ ไม่ใช่ Claude ตัดสินเอง**

- ยังไม่ผูกลูกค้า → ออกใบเสนอราคาไม่ได้
- มีรายการที่ต้องจัดส่ง แต่ยังไม่คิดค่าส่ง/เลือกคิว → ออกไม่ได้
- มีส่วนลดที่รอผู้จัดการอนุมัติ → ออกไม่ได้
- ของไม่พอ → ตอบกลับพร้อมรายการที่ขาด ต้องยืนยัน `force=true` ถึงจะออกให้

---

## 5. เรื่องเช็คสต็อกที่ต้องเข้าใจก่อนใช้

### 5.1 ทำไมต้องยิงทั้งบิลครั้งเดียว

SAP จำลอง **ใบสั่งขายทั้งใบ** ของที่มีจะถูกบรรทัดแรกจองไปก่อน บรรทัดหลังจึงเห็นของน้อยลงตามจริง

ถ้าถามทีละรหัสแล้วเอาผลมาต่อกันเอง ทุกบรรทัดจะเห็นของก้อนเดียวกันเต็มเหมือนกันหมด → **ขายเกิน**

เพราะแบบนี้ MCP จึงตั้งใจ **ไม่มี** เครื่องมือ "เช็คทีละตัว" ให้เรียกวน — มีแต่ `check_stock` ที่รับทั้งรายการ
และคำอธิบายของเครื่องมือก็เขียนกำกับไว้ตรงๆ ว่าห้ามแยกยิง

### 5.2 อ่านผลยังไง

| ฟิลด์ | ความหมาย |
| --- | --- |
| `source` | `sap` = ยิงของจริง · `mock` = ข้อมูลจำลอง **ห้ามเอาไปยืนยันกับลูกค้า** |
| `status` | `full` ได้ครบ · `split` ได้ครบแต่แบ่งส่ง · `short` ไม่พอ · `none` ไม่มีของ · `unknown` SAP ไม่รู้จักรหัสนี้ |
| `ready_qty` / `ready_date` | ได้ทันทีตามวันที่ขอ |
| `later_qty` / `later_date` | ต้องรอของเข้ารอบหน้า |
| `short_qty` | ยังหาไม่ได้ |

ค่าดิบจาก SAP: `AVAILABLE_QUAN` = ของที่มีอยู่ตอนนี้ · `COMMITTED_QUAN` = ของที่จะเข้ามาเพิ่มในวัน `COMMITTED_DATE`

วันที่ขอ (`req_date`) = วันนี้ + `SAP_AVAIL_LEAD_DAYS` (ตอนนี้ 7 วัน)

### 5.3 สินค้าชุด (BOM)

สินค้าชุดอย่าง `59064091` SAP กางส่วนประกอบออกมาเป็นหลายแถวต่อหนึ่งบรรทัดที่ขอ
ฝั่งเราตัดแถวลูกทิ้งด้วย `HIGH_LEVEL` (`top_level_rows`) แล้วใช้แถวแม่ซึ่งสรุปของ (= ค่าน้อยสุดของลูก) และราคาชุดมาให้แล้ว

### 5.4 ข้อควรระวังที่ยังแก้ไม่ได้ (ฝั่ง SAP)

- **`19248757`** ตอบ `AVAILABLE_QUAN` = จำนวนที่ขอ + 14 เสมอ (ขอ 500 ตอบ 514) = **เชื่อตัวเลขไม่ได้**
  และเมื่ออยู่ในบิลรวมกับตัวอื่น SAP จะคืน 0 แถวพร้อม `AI_MESSAGE` ว่าง ทำให้ระบบถอยไปไล่ถามทีละบรรทัด
- ตรวจรหัสที่สงสัยเองได้ด้วย `backend/app/etl/sap_check.py`:

  ```bat
  cd backend
  .venv\Scripts\python.exe -m app.etl.sap_check 19217394 19248757 19205233
  ```

  หลักอ่านผล: ขอ 1 กับ ขอ 500 แล้วได้เลข **เท่ากัน** = ของมีจริง · เลข **วิ่งตามที่ขอ** = SAP ยืนยันให้โดยไม่เช็คของ

การยิงทั้งหมดนี้เป็นการ **จำลอง** ใบสั่งขาย (`ORDER_NUMBER` ว่าง) ไม่สร้างเอกสารและไม่จองของจริงใน SAP — ยิงกี่ครั้งก็ปลอดภัย

---

## 6. ขอบเขต / สิ่งที่ MCP ทำไม่ได้

- ไม่มีเครื่องมือแก้ราคา แก้สต็อก ลบลูกค้า อนุมัติส่วนลด หรือรับชำระเงิน
- ไม่เห็นข้อมูลลูกค้าเกินกว่าที่ endpoint ค้นหาลูกค้าคืนมา
- ไม่ได้ต่อฐาน Magento หรือฐานเว็บ production โดยตรง
- ยังไม่ push ใบเสนอราคาไป SAP เป็น Sales Order — จุดนั้นเกิดตอนชำระเงิน (นอกขอบเขต MCP)

## 7. แก้ปัญหา

| อาการ | สาเหตุที่พบบ่อย |
| --- | --- |
| `ล็อกอินไม่ผ่าน (401)` | รหัสพนักงาน/รหัสผ่านใน env ผิด หรือบัญชีไม่ใช่ sales/manager |
| `ต่อ backend ไม่ได้` | ยังไม่ได้รัน uvicorn หรือขึ้นคนละพอร์ต (ต้อง 8000) |
| `source: "mock"` | ยังไม่ได้ตั้ง `SAP_AVAIL_URL` / `SAP_API_KEY` ใน `backend/.env` — ตัวเลขเป็นของปลอม |
| แก้ `.env` แล้วยังเป็น mock | `uvicorn --reload` ดูแค่ไฟล์ `.py` ต้องปิด–เปิด process ใหม่ |
| เครื่องมือที่แก้ข้อมูลหายไป | `SB_MCP_ALLOW_WRITE=0` อยู่ |
| ภาษาไทยเพี้ยนใน log | ตั้ง `PYTHONIOENCODING=utf-8` ใน env ของ MCP |
