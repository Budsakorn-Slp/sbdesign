# อัปเดตทุกอย่างในคำสั่งเดียว — เรียกสคริปต์ย่อยตามลำดับที่ถูกต้อง
#
#   1 sync_products.ps1   ข้อมูลสินค้า (7 ขั้น) — หนักสุด ใช้เวลาส่วนใหญ่
#   2 sync_daily.ps1      กฎค่าส่ง Amasty + ที่อยู่ไทย
#   3 เนื้อหาหน้าเว็บ      ภาพหน้าแรก + หน้านโยบาย/CMS
#   4 สต็อกจาก SAP        ต้องใส่ -WithSap ถึงจะรัน (ดูหมายเหตุข้างล่าง)
#
# วิธีรัน (PowerShell):
#   powershell -NoProfile -ExecutionPolicy Bypass -File backend\scripts\sync_all.ps1
#   ... -File backend\scripts\sync_all.ps1 -WithSap     # รวมสต็อกด้วย
#   ... -File backend\scripts\sync_all.ps1 -DryRun      # ซ้อม ไม่เขียนอะไร
#
# ทำไมสต็อกต้องสั่งเพิ่มเอง:
#   มันยิง SAP ~3,700 ครั้ง (สินค้าที่ขึ้นเว็บ) + อีก ~3,400 ครั้งสำหรับสินค้าตัวโชว์
#   เป็นภาระฝั่ง SAP ที่ควรรู้ตัวก่อนกด และควรรันนอกเวลาทำการ
#   ส่วนข้อมูลสินค้าเป็นการอ่าน/เขียนฐานเราเอง ไม่กวนใคร
#
# ห้ามใส่ --mock กับขั้นสต็อกเด็ดขาด — มันเขียนตัวเลขปลอมทับของจริง
#
# ล็อกรวมอยู่ที่ backend\logs\ (ไฟล์แยกตามสคริปต์ย่อย)

param([switch]$WithSap, [switch]$DryRun)

$ErrorActionPreference = "Continue"
$backend = Split-Path -Parent $PSScriptRoot
$python  = Join-Path $backend ".venv\Scripts\python.exe"
$logDir  = Join-Path $backend "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ("all_" + (Get-Date -Format "yyyy-MM-dd") + ".log")

$env:PYTHONPATH = $backend
$env:PYTHONIOENCODING = "utf-8"
Set-Location $backend

# หมายเหตุ encoding: Windows PowerShell 5.1 เขียนไฟล์เป็น UTF-16 โดยปริยาย
# ทำให้เปิดล็อกด้วยเครื่องมืออื่น (หรือ Get-Content -Encoding utf8) อ่านเป็นภาษาต่างดาว
# บังคับ UTF-8 ให้ทุก Out-File/Tee-Object ในสคริปต์นี้ทีเดียว
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Tee-Object:Encoding'] = 'utf8'

$started = Get-Date
$failed = @()
function Note($t) { "$(Get-Date -Format 'HH:mm:ss') $t" | Tee-Object -FilePath $log -Append }

Note "===== SYNC ALL START$(if ($DryRun) {' (DRY RUN)'}) ====="

# --- 0 สำรองฐานแอปก่อนแตะอะไร ---
#
# ถ้าอัปเดตพังกลางทาง (ETL bug / ต้นทางส่งข้อมูลเพี้ยน / ไฟดับ) จะได้ย้อนกลับได้ในไม่กี่วินาที
# แทนที่จะต้องรัน sync ใหม่ทั้งชุด 45 นาทีโดยไม่รู้ว่าข้อมูลเหลือสภาพไหน
#
# ใช้ .backup ของ SQLite ไม่ใช่ copy ไฟล์เฉยๆ — copy ระหว่างมีคนเขียนอยู่ได้ไฟล์ที่ใช้ไม่ได้
# (โหมด WAL ยิ่งต้องระวัง เพราะข้อมูลบางส่วนยังอยู่ในไฟล์ -wal ที่ยังไม่ถูกรวมเข้าฐาน)
if (-not $DryRun) {
  $stamp = Get-Date -Format "yyyyMMdd-HHmm"
  $bakDir = Join-Path $backend "backups"
  if (-not (Test-Path $bakDir)) { New-Item -ItemType Directory -Path $bakDir | Out-Null }
  $bak = Join-Path $bakDir "sbdesign_$stamp.db"
  & $python -c "import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()" (Join-Path $backend "sbdesign.db") $bak
  if ($LASTEXITCODE -eq 0) {
    Note ("[0/4] BACKUP ok -> " + $bak + " (" + [int]((Get-Item $bak).Length / 1MB) + " MB)")
    # เก็บ 7 ชุดล่าสุดพอ ไฟล์ละ ~50MB
    Get-ChildItem $bakDir -Filter "sbdesign_*.db" | Sort-Object LastWriteTime -Descending |
      Select-Object -Skip 7 | Remove-Item -Force
  } else {
    Note "[0/4] BACKUP FAILED - stopping, fix this before syncing"
    exit 1
  }
}

# --- 1 ข้อมูลสินค้า ---
Note "[1/4] PRODUCTS (rebuild, images, signals, catalog, gallery, EN names, categories)"
$a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "sync_products.ps1"))
if ($DryRun) { $a += "-DryRun" }
& powershell @a
if ($LASTEXITCODE -ne 0) { $failed += "sync_products" }

# --- 2 กฎค่าส่ง + ที่อยู่ไทย ---
Note "[2/4] SHIPPING RULES + THAI ADDRESSES"
if ($DryRun) {
  & $python -m app.etl.sync_shipping_rules --report-only 2>&1 | Tee-Object -FilePath $log -Append
  & $python -m app.etl.sync_thai_geo --report-only 2>&1 | Tee-Object -FilePath $log -Append
} else {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "sync_daily.ps1")
  if ($LASTEXITCODE -ne 0) { $failed += "sync_daily" }
}

# --- 3 เนื้อหาหน้าเว็บ ---
Note "[3/4] HOMEPAGE BANNERS + CMS PAGES"
foreach ($m in @("app.etl.sync_home_media", "app.etl.sync_cms_pages")) {
  $argList = @("-m", $m)
  if ($DryRun) { $argList += $(if ($m -like "*home_media") { "--dry" } else { "--dry-run" }) }
  & $python @argList 2>&1 | Tee-Object -FilePath $log -Append
  if ($LASTEXITCODE -ne 0) { $failed += $m }
}

# --- 4 สต็อกจาก SAP (ต้องสั่งเพิ่ม) ---
if ($WithSap -and -not $DryRun) {
  Note "[4/4] STOCK FROM SAP - live calls, keep this window open"
  foreach ($m in @("app.etl.refresh_stock", "app.etl.sync_display_items")) {
    & $python -m $m --all 2>&1 | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) { $failed += $m }
  }
} else {
  Note "[4/4] SKIPPED stock from SAP - add -WithSap to include it"
}

$mins = [int]((Get-Date) - $started).TotalMinutes
if ($failed.Count -gt 0) {
  Note "FINISHED WITH ERRORS ($mins min) - failed: $($failed -join ', ')"
  Note "Check that step log, then re-run only the failed step - no need to start over"
  exit 1
}
Note "ALL DONE ($mins min) - log: $log"
