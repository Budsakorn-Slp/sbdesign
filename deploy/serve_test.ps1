# เปิดเว็บทดสอบที่ designdev.sbhapps.com — รัน 3 อย่างพร้อมกัน
#
#   1 API      uvicorn :8000
#   2 หน้าเว็บ  vite preview :4173 (เสิร์ฟไฟล์ที่ build แล้ว + ส่งต่อ /api ไปที่ :8000)
#   3 tunnel   cloudflared เชื่อมเครื่องนี้เข้ากับ Cloudflare
#
# วิธีรัน:
#   powershell -NoProfile -ExecutionPolicy Bypass -File deploy\serve_test.ps1
#   ... -Build        # build หน้าเว็บใหม่ก่อน (ใช้หลังแก้โค้ดหน้าบ้าน)
#   ... -NoTunnel     # ไม่เปิด tunnel ทดสอบในเครื่องอย่างเดียว
#
# เปิดค้างไว้แล้ว: แก้โค้ดหลังบ้าน/ .env → API เปิดใหม่เอง · ตัวไหนหยุด → เปิดใหม่เอง (ไม่ปิดทั้งหมด)
#
# ปิดด้วย Ctrl+C ที่หน้าต่างนี้ · เครื่องต้องเปิดค้างไว้ ปิดเมื่อไรเว็บล่ม

param([switch]$Build, [switch]$NoTunnel)

$ErrorActionPreference = "Stop"
$root    = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$web     = Join-Path $root "web"
$python  = Join-Path $backend ".venv\Scripts\python.exe"
$cfg     = Join-Path $PSScriptRoot "cloudflared\config.yml"

$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$env:PYTHONIOENCODING = "utf-8"

# --- ตรวจก่อนเปิด: ถ้าตั้งค่าผิดแล้วเปิดสู่เน็ต จะรู้ตัวตอนสายไป ---
Write-Host "=== checking config ===" -ForegroundColor Cyan
$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) { throw "ไม่พบ backend\.env" }
$conf = Get-Content $envFile -Raw

$problems = @()
if ($conf -notmatch '(?m)^APP_ENV\s*=\s*prod')      { $problems += "APP_ENV ยังไม่ใช่ prod -> /docs จะเปิดให้คนนอกเห็น และ cookie ไม่มี secure" }
if ($conf -notmatch '(?m)^INVITE_ONLY\s*=\s*true')  { $problems += "INVITE_ONLY ไม่ใช่ true -> ใครก็สมัครสมาชิกเองได้" }
if ($conf -match '(?m)^OTP_DEBUG\s*=\s*true' -and $conf -notmatch '(?m)^OTP_DEBUG_PHONES\s*=\s*\S') {
  $problems += "OTP_DEBUG เปิดแต่ไม่ได้จำกัดเบอร์ -> ใครก็ขอ OTP ของเบอร์คนอื่นแล้วยึดบัญชีได้"
}
if ($conf -notmatch 'designdev\.sbhapps\.com')      { $problems += "CORS_ORIGINS ยังไม่มี designdev.sbhapps.com" }

if ($problems.Count -gt 0) {
  Write-Host "`n!! ตั้งค่ายังไม่พร้อมเปิดสู่อินเทอร์เน็ต:" -ForegroundColor Red
  $problems | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
  if (-not $NoTunnel) {
    Write-Host "`n   แก้ backend\.env ก่อน หรือใส่ -NoTunnel เพื่อทดสอบเฉพาะในเครื่อง`n" -ForegroundColor Yellow
    exit 1
  }
  Write-Host "   (-NoTunnel อยู่ ไม่ได้เปิดออกเน็ต ข้ามไปก่อน)`n" -ForegroundColor Yellow
} else {
  Write-Host "ok - config พร้อมเปิดสู่เน็ต" -ForegroundColor Green
}

# --- build หน้าเว็บ ---
if ($Build) {
  Write-Host "`n=== building web ===" -ForegroundColor Cyan
  Push-Location $web
  & npx vite build
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "build หน้าเว็บไม่ผ่าน" }
  Pop-Location
}
if (-not (Test-Path (Join-Path $web "dist\index.html"))) {
  throw "ยังไม่มี web\dist - รันใหม่พร้อม -Build"
}

$web_job = $null
$tunnel_job = $null
$api = $null
$apiStartedAt = Get-Date

# ไฟล์ที่ถ้าแก้แล้วต้องเปิด API ใหม่ — โค้ดหลังบ้าน + .env
function Get-ApiCodeStamp {
  $files = @(Get-ChildItem -Path (Join-Path $backend "app") -Recurse -Filter *.py -File -ErrorAction SilentlyContinue)
  $files += Get-Item $envFile -ErrorAction SilentlyContinue
  ($files | Measure-Object -Property LastWriteTime -Maximum).Maximum
}

function Stop-Api {
  if ($script:api -and -not $script:api.HasExited) { try { $script:api.Kill() } catch {} }
  # เผื่อมี API ตัวอื่นค้างยึดพอร์ต (เช่นเปิดจากหน้าต่าง dev) — เก็บให้หมดก่อนเปิดตัวใหม่
  Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -Expand OwningProcess -Unique | ForEach-Object {
      Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn|spawn_main' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 1
}

function Start-Api([string]$why) {
  Write-Host "=== starting api :8000 $why ===" -ForegroundColor Cyan
  # ไม่ใช้ uvicorn --reload: เคยเจอตัวลูกค้างยึดพอร์ตแล้วตอบ 500 ทุก request
  # สคริปต์นี้คอยดูไฟล์เองแล้วเปิดใหม่ทั้งตัวแทน (ดู loop ข้างล่าง)
  $script:apiStartedAt = Get-Date
  $script:api = Start-Process -FilePath $python -WorkingDirectory $backend -PassThru -NoNewWindow `
                  -ArgumentList @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000")
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if ($script:api.HasExited) { break }
    try {
      if ((Invoke-WebRequest "http://127.0.0.1:8000/healthz" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) {
        Write-Host "    api พร้อมแล้ว ($($i + 1) วิ)" -ForegroundColor Green
        return
      }
    } catch {}
  }
  Write-Host "    !! api ยังไม่ตอบ - ดู error ข้างบน (แก้โค้ดแล้วบันทึกไฟล์ สคริปต์จะลองเปิดใหม่เอง)" -ForegroundColor Red
}

function Start-Web {
  Write-Host "=== starting web :4173 ===" -ForegroundColor Cyan
  # เรียก node + vite.js ตรงๆ ไม่ผ่าน npx — npx เป็นไฟล์ .cmd ซึ่ง Start-Process เปิดไม่ได้
  # ("%1 is not a valid Win32 application") และ npx ยังแทรกชั้นโปรเซสเกินมาอีกตัว
  $node = (Get-Command node).Source
  $vite = Join-Path $web (Join-Path "node_modules" (Join-Path "vite" (Join-Path "bin" "vite.js")))
  if (-not (Test-Path $vite)) { throw "ไม่พบ vite - รัน npm install ในโฟลเดอร์ web ก่อน" }
  $script:web_job = Start-Process -FilePath $node -WorkingDirectory $web -PassThru -NoNewWindow `
                      -ArgumentList @($vite,"preview","--port","4173","--host","127.0.0.1")
}

function Start-Tunnel {
  Write-Host "=== starting tunnel ===" -ForegroundColor Cyan
  $cfd = (Get-Command cloudflared).Source
  $script:tunnel_job = Start-Process -FilePath $cfd -PassThru -NoNewWindow `
                         -ArgumentList @("tunnel","--config",$cfg,"run")
}

function Stop-All {
  Write-Host "`nกำลังปิด..." -ForegroundColor Yellow
  foreach ($j in @($script:tunnel_job, $script:web_job, $script:api)) {
    if ($j -and -not $j.HasExited) { try { $j.Kill() } catch {} }
  }
}

try {
  # API ตัวที่ค้างอยู่ก่อน (หน้าต่างเก่า/หน้าต่าง dev) ปิดทิ้งแล้วเปิดตัวของสคริปต์นี้เสมอ
  # เดิมใช้ตัวที่ค้างต่อ — ผลคือรันสคริปต์ใหม่แล้วยังได้โค้ดเก่า (เจอจริง: แก้โค้ดแล้วเว็บไม่เปลี่ยน 2 วัน)
  # และสคริปต์เปิดใหม่ให้อัตโนมัติไม่ได้ เพราะไม่ใช่โปรเซสของมัน
  if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "`n=== มี API ค้างอยู่ที่ :8000 - ปิดแล้วเปิดตัวใหม่ (ได้โค้ดล่าสุด) ===" -ForegroundColor DarkYellow
    Stop-Api
  }
  Start-Api ""
  $stamp = Get-ApiCodeStamp

  if (Get-NetTCPConnection -LocalPort 4173 -State Listen -ErrorAction SilentlyContinue) {
    Get-NetTCPConnection -LocalPort 4173 -State Listen | Select-Object -Expand OwningProcess -Unique |
      ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
  }
  Start-Web

  if ($NoTunnel) {
    Write-Host "`nเปิดที่ http://localhost:4173 (ไม่ได้เปิด tunnel)" -ForegroundColor Green
  } else {
    if (-not (Test-Path $cfg)) { throw "ไม่พบ $cfg" }
    if ((Get-Content $cfg -Raw) -match 'PUT-TUNNEL-UUID-HERE') {
      throw "ยังไม่ได้ใส่ tunnel UUID ใน deploy\cloudflared\config.yml - ดู deploy\README.md"
    }
    Start-Tunnel
    Write-Host "`nเปิดที่ https://designdev.sbhapps.com" -ForegroundColor Green
  }

  Write-Host "แก้โค้ดหลังบ้าน (backend\app) หรือ .env แล้วบันทึก = API เปิดใหม่เอง ไม่ต้องรันสคริปต์ใหม่" -ForegroundColor DarkGray
  Write-Host "แก้หน้าบ้าน = build ใหม่ (npm run build) แล้วรีเฟรช · Ctrl+C เพื่อปิดทั้งหมด`n" -ForegroundColor DarkGray

  # คอยดูทุก 5 วินาที — ตัวไหนหยุด เปิดตัวนั้นใหม่ ไม่ปิดทั้งหมด
  # (เดิมตัวไหนหยุด ปิดหมดรวม tunnel = เว็บล่มยาวจนกว่าจะมีคนมารันใหม่)
  while ($true) {
    Start-Sleep -Seconds 5

    $now = Get-ApiCodeStamp
    if ($now -gt $stamp) {
      # รอให้บันทึกไฟล์ชุดเดียวกันเสร็จก่อน (แก้หลายไฟล์ติดกัน) ค่อยเปิดใหม่ครั้งเดียว
      Start-Sleep -Seconds 2
      $stamp = Get-ApiCodeStamp
      Write-Host "`n[$(Get-Date -Format HH:mm:ss)] โค้ดหลังบ้านเปลี่ยน - เปิด API ใหม่" -ForegroundColor Cyan
      Stop-Api
      Start-Api "(โค้ดเปลี่ยน)"
      continue
    }
    if ($api.HasExited) {
      Write-Host "`n[$(Get-Date -Format HH:mm:ss)] API หยุดไป - เปิดใหม่" -ForegroundColor Yellow
      Stop-Api
      Start-Api "(หยุดไป)"
      $stamp = Get-ApiCodeStamp
    }
    if ($web_job.HasExited) {
      Write-Host "`n[$(Get-Date -Format HH:mm:ss)] หน้าเว็บหยุดไป - เปิดใหม่" -ForegroundColor Yellow
      Start-Web
    }
    if ($tunnel_job -and $tunnel_job.HasExited) {
      Write-Host "`n[$(Get-Date -Format HH:mm:ss)] tunnel หยุดไป - เปิดใหม่" -ForegroundColor Yellow
      Start-Sleep -Seconds 3
      Start-Tunnel
    }
  }
} finally {
  Stop-All
}
