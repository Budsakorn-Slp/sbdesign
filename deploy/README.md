# เปิดเว็บทดสอบที่ designdev.sbhapps.com

เครื่องในออฟฟิศเป็นคนรันทั้ง API และหน้าเว็บ ส่วน Cloudflare ทำหน้าที่เป็นประตูหน้า
**backend ย้ายขึ้น Cloudflare ไม่ได้** เพราะต้องคุยกับ SAP (192.168.7.110) และ Magento (10.9.x)
ซึ่งอยู่ในเครือข่ายภายใน โค้ดที่รันบนเครื่องของ Cloudflare วิ่งไปไม่ถึง

```
ผู้ใช้ -> Cloudflare Access (ถามอีเมล) -> Tunnel -> เครื่องออฟฟิศ :4173 -> :8000 -> SAP / Magento
```

> เครื่องต้องเปิดค้างไว้ ปิดเมื่อไรเว็บล่ม

---

## ครั้งแรก ทำ 4 ขั้น

### 1. ล็อกอิน Cloudflare (เปิดเบราว์เซอร์ให้ยืนยันตัวตน)

```powershell
cloudflared tunnel login
```

เลือกโดเมน `sbhapps.com` ในหน้าที่เด้งขึ้นมา · จะได้ไฟล์ `cert.pem` เก็บไว้ที่ `%USERPROFILE%\.cloudflared\`

### 2. สร้าง tunnel

```powershell
cloudflared tunnel create sbdesign-dev
```

จะได้ข้อความประมาณนี้ — **จด UUID ไว้**

```
Created tunnel sbdesign-dev with id 6a7f2c10-....-....-....-............
```

### 3. ใส่ UUID ลงไฟล์ config

เปิด `deploy\cloudflared\config.yml` แล้วแทน `PUT-TUNNEL-UUID-HERE` **ทั้งสองที่** ด้วย UUID ที่ได้

### 4. ผูกโดเมนเข้ากับ tunnel (สร้าง DNS ให้อัตโนมัติ)

```powershell
cloudflared tunnel route dns sbdesign-dev designdev.sbhapps.com
```

---

## ⚠️ กับดักของเครื่องนี้ — ต้องใส่ `--config` ทุกครั้ง

เครื่องนี้มี `~/.cloudflared/config.yml` ของ Disney Home อยู่ และ cloudflared **อ่านไฟล์นั้นเป็นค่าตั้งต้น**
ทำให้คำสั่งที่ไม่ได้ใส่ `--config` ไปทำงานกับ tunnel ของ Disney แทน **แม้จะพิมพ์ชื่อ tunnel ของเราไปแล้วก็ตาม**

เจอของจริงมาแล้ว — สั่ง route ชื่อ `sbdesign-dev` แต่มันไปผูกกับ tunnel ของ Disney:

```
cloudflared tunnel route dns sbdesign-dev designdev.sbhapps.com
INF Added CNAME designdev.sbhapps.com ... tunnelID=9738d7ff-...   <- ของ Disney!
```

ที่ถูกต้องคือใส่ `--config` **ก่อน** คำสั่งย่อยเสมอ:

```powershell
cloudflared tunnel --config deploy\cloudflared\config.yml info sbdesign-dev
cloudflared tunnel --config deploy\cloudflared\config.yml route dns --overwrite-dns sbdesign-dev designdev.sbhapps.com
```

`serve_test.ps1` ส่ง `--config` ให้อยู่แล้ว จึงไม่มีปัญหานี้ — ระวังเฉพาะตอนพิมพ์คำสั่งเอง

---

## เปิดใช้งาน

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File deploy\serve_test.ps1 -Build
```

สคริปต์จะ **ตรวจการตั้งค่าก่อนเปิดเสมอ** ถ้ายังไม่ปลอดภัยจะไม่ยอมเปิด tunnel ให้:

| ตรวจอะไร | ถ้าผิดจะเกิดอะไร |
|---|---|
| `APP_ENV=prod` | `/docs` เปิดให้คนนอกเห็น API ทั้งหมด · cookie ไม่มี `secure` |
| `INVITE_ONLY=true` | ใครก็สมัครสมาชิกเองได้ |
| `OTP_DEBUG_PHONES` มีค่า | ใครก็ขอ OTP ของเบอร์คนอื่นแล้วยึดบัญชีได้ |
| `CORS_ORIGINS` มีโดเมนนี้ | เรียก API ไม่ผ่าน |

ทดสอบในเครื่องอย่างเดียว (ไม่เปิดออกเน็ต) ใส่ `-NoTunnel`

---

## ⚠️ ขั้นที่สำคัญที่สุด — Cloudflare Access

Tunnel อย่างเดียว **ใครก็เปิด `designdev.sbhapps.com` ได้** ต้องครอบด้วย Access อีกชั้น
ฟรีถึง 50 คน และทำที่หน้าเว็บ Cloudflare ไม่ต้องแตะโค้ด

1. เข้า **Zero Trust** → `Access` → `Applications` → **Add an application** → **Self-hosted**
2. Application name: `SB Design Dev`
3. Subdomain `designdev` · Domain `sbhapps.com` · Path เว้นว่าง
4. **Add policy**
   - Policy name: `ทีมทดสอบ`
   - Action: **Allow**
   - Include → **Emails** → ใส่อีเมลทีมทีละคน
     (หรือ **Emails ending in** → `@sbdesignsquare.com` ถ้าจะให้ทั้งบริษัท)
5. Save

เสร็จแล้วคนนอกจะเจอหน้า Cloudflare ขออีเมล → รับ PIN ทางอีเมล → ผ่านแล้วถึงเห็นเว็บเรา
→ แล้วค่อย login แอปอีกชั้น **รวมเป็นสองด่าน**

ประโยชน์ที่ได้นอกจากกันคนนอก: Google เก็บ index ไม่ได้ ราคาและสินค้าไม่หลุดออกไปตอนยังไม่พร้อมขาย
และถ้าแอปมีช่องโหว่ คนนอกก็ยังยิงไม่ถึง

---

## เข้าระบบยังไง

ช่วงนี้ **ยังไม่ได้ต่อ SMS จริง** (ไม่อยากเสียค่าส่ง) จึงเข้าได้สองทาง:

| วิธี | ใช้กับใคร |
|---|---|
| **เบอร์ + รหัสผ่าน** | ทางหลัก — หน้า login จะโชว์เฉพาะช่องนี้ |
| **OTP โชว์รหัสบนจอ** | เฉพาะเบอร์ใน `OTP_DEBUG_PHONES` เท่านั้น เบอร์อื่นไม่เห็นรหัส |

เพิ่มผู้ทดสอบ:

```powershell
cd backend
.venv\Scripts\python.exe -m app.cli.testers add 0800000001 --name "ทีม A" --password xxxx
.venv\Scripts\python.exe -m app.cli.testers list
```

หน้าพนักงานอยู่ที่ `/staff` (รหัสพนักงาน + รหัสผ่าน) · หน้าลูกค้าอยู่ที่ `/login`
หน้า `/login` จะขึ้น "เร็ว ๆ นี้" ก่อน มีลิงก์เล็กๆ ให้กดเข้าฟอร์ม หรือส่งลิงก์ตรง `/login?login=1`

---

## ปัญหาที่เจอบ่อย

| อาการ | สาเหตุ |
|---|---|
| `Blocked request. This host is not allowed` | โดเมนไม่อยู่ใน `preview.allowedHosts` ของ `web/vite.config.ts` |
| เปิดเว็บได้ แต่ API 404 ทั้งหมด | ลืม build — รันใหม่พร้อม `-Build` |
| `502 Bad Gateway` | API หรือ vite preview ไม่ได้รัน ดูหน้าต่างที่รันสคริปต์อยู่ |
| ล็อกอินแล้วเด้งออก | `CORS_ORIGINS` ยังไม่มีโดเมนนี้ |
| เว็บล่มเฉยๆ | เครื่องออฟฟิศปิด/หลับ — ตั้งไม่ให้เครื่อง sleep |

ดูสถานะ tunnel: `cloudflared tunnel info sbdesign-dev`
ลบทิ้ง: `cloudflared tunnel delete sbdesign-dev`
