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

$jobs = @()
function Stop-All {
  Write-Host "`nกำลังปิด..." -ForegroundColor Yellow
  foreach ($j in $jobs) { if ($j -and -not $j.HasExited) { try { $j.Kill() } catch {} } }
}

try {
  # ถ้า API รันค้างอยู่แล้ว (เช่น หน้าต่าง dev ที่เปิดทิ้งไว้) ใช้ตัวนั้นต่อ อย่าไปเปิดซ้อน
  # เปิดซ้อนจะชนพอร์ตแล้วตายทันที ทำให้ดูเหมือนสคริปต์พัง ทั้งที่ของเดิมยังทำงานดีอยู่
  $apiUp = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
  if ($apiUp) {
    Write-Host "`n=== api :8000 รันอยู่แล้ว ใช้ตัวเดิม ===" -ForegroundColor DarkYellow
    Write-Host "    (ถ้าเพิ่งแก้ .env ต้องปิดตัวเดิมแล้วรันใหม่ ไม่งั้นยังใช้ค่าเก่า)" -ForegroundColor DarkYellow
  } else {
    Write-Host "`n=== starting api :8000 ===" -ForegroundColor Cyan
    $jobs += Start-Process -FilePath $python -WorkingDirectory $backend -PassThru -NoNewWindow `
              -ArgumentList @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000")
  }

  Write-Host "=== starting web :4173 ===" -ForegroundColor Cyan
  # เรียก node + vite.js ตรงๆ ไม่ผ่าน npx — npx เป็นไฟล์ .cmd ซึ่ง Start-Process เปิดไม่ได้
  # ("%1 is not a valid Win32 application") และ npx ยังแทรกชั้นโปรเซสเกินมาอีกตัว
  $node = (Get-Command node).Source
  $vite = Join-Path $web (Join-Path "node_modules" (Join-Path "vite" (Join-Path "bin" "vite.js")))
  if (-not (Test-Path $vite)) { throw "ไม่พบ vite - รัน npm install ในโฟลเดอร์ web ก่อน" }
  $jobs += Start-Process -FilePath $node -WorkingDirectory $web -PassThru -NoNewWindow `
            -ArgumentList @($vite,"preview","--port","4173","--host","127.0.0.1")

  if ($NoTunnel) {
    Write-Host "`nเปิดที่ http://localhost:4173 (ไม่ได้เปิด tunnel)" -ForegroundColor Green
  } else {
    if (-not (Test-Path $cfg)) { throw "ไม่พบ $cfg" }
    if ((Get-Content $cfg -Raw) -match 'PUT-TUNNEL-UUID-HERE') {
      throw "ยังไม่ได้ใส่ tunnel UUID ใน deploy\cloudflared\config.yml - ดู deploy\README.md"
    }
    Write-Host "=== starting tunnel ===" -ForegroundColor Cyan
    $cfd = (Get-Command cloudflared).Source
    $jobs += Start-Process -FilePath $cfd -PassThru -NoNewWindow `
              -ArgumentList @("tunnel","--config",$cfg,"run")
    Write-Host "`nเปิดที่ https://designdev.sbhapps.com" -ForegroundColor Green
  }

  Write-Host "Ctrl+C เพื่อปิดทั้งหมด`n" -ForegroundColor DarkGray
  while ($true) {
    Start-Sleep -Seconds 5
    foreach ($j in $jobs) {
      if ($j.HasExited) { Write-Host "process $($j.Id) หยุดไปแล้ว - กำลังปิดตัวอื่น" -ForegroundColor Red; Stop-All; exit 1 }
    }
  }
} finally {
  Stop-All
}
