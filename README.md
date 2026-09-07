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
