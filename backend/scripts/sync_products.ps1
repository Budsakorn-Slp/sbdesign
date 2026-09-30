# อัปเดต "ข้อมูลสินค้า" ทั้งชุด — รันตัวเดียวจบ ไม่ต้องไล่พิมพ์ทีละคำสั่ง
#
# ลำดับสำคัญ ตัวหลังกินผลจากตัวหน้า:
#   1 rebuild_products        mdm_products -> sb_products      (ฐานเว็บ 10.9.11.111)
#   2 sync_product_images     Magento -> sb_products_image
#   3 sync_product_signals    ยอดขาย 365 วัน -> มาใหม่/ขายดี
#   4 import_catalog          sb_products -> สินค้า/หมวด/แบรนด์/ราคา (ฐานแอป)
#   5 import_product_gallery  sb_products_image -> material_images
#   6 sync_english_names      ชื่อ EN จาก store view 1 ของ Magento
#   7 sync_web_categories     ยกการจัดหมวดของเว็บจริงมา ทีละกลุ่ม
#
# ไม่รวมสต็อก — สต็อกยิง SAP ต้องรันแยก (refresh_stock / sync_display_items)
# เพราะมันเป็นข้อมูลที่เปลี่ยนทุกชั่วโมง คนละจังหวะกับข้อมูลสินค้าที่เปลี่ยนวันละครั้ง
#
# วิธีรัน (PowerShell):
#   powershell -NoProfile -ExecutionPolicy Bypass -File backend\scripts\sync_products.ps1
#
# ซ้อมก่อนโดยไม่เขียนอะไร (ดูว่าจะได้กี่แถว):
#   ... -File backend\scripts\sync_products.ps1 -DryRun
#
# ตั้งให้รันทุกคืนตี 2 (รันครั้งเดียวใน PowerShell แบบ Administrator):
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" `
#        -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\Users\Budsakorn.s\Documents\sbdesign\backend\scripts\sync_products.ps1"
#   $t = New-ScheduledTaskTrigger -Daily -At 2am
#   Register-ScheduledTask -TaskName "sbdesign-sync-products" -Action $a -Trigger $t -RunLevel Highest
#
# ล็อกเก็บที่ backend\logs\products_YYYY-MM-DD.log เก็บ 30 วันล่าสุด

param([switch]$DryRun)

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $PSScriptRoot
$python  = Join-Path $backend ".venv\Scripts\python.exe"
$logDir  = Join-Path $backend "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ("products_" + (Get-Date -Format "yyyy-MM-dd") + ".log")

$env:PYTHONPATH = $backend
$env:PYTHONIOENCODING = "utf-8"
Set-Location $backend

# ตัวไหนมีโหมดซ้อม ใส่ flag ให้ตรงกับที่ตัวนั้นรองรับ (ชื่อ flag ไม่เหมือนกันทุกตัว)
# หมายเหตุ encoding: Windows PowerShell 5.1 เขียนไฟล์เป็น UTF-16 โดยปริยาย
# ทำให้เปิดล็อกด้วยเครื่องมืออื่น (หรือ Get-Content -Encoding utf8) อ่านเป็นภาษาต่างดาว
# บังคับ UTF-8 ให้ทุก Out-File/Tee-Object ในสคริปต์นี้ทีเดียว
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Tee-Object:Encoding'] = 'utf8'

$steps = @(
  @{ m = "app.etl.rebuild_products";       dry = "--dry-run" },
  @{ m = "app.etl.sync_product_images";    dry = $null       },
  @{ m = "app.etl.sync_product_signals";   dry = "--dry"     },
  @{ m = "app.etl.import_catalog";         dry = $null       },
  @{ m = "app.etl.import_product_gallery"; dry = "--dry-run" },
  @{ m = "app.etl.sync_english_names";     dry = "--dry-run" }
)

function Run-Step($label, $argList) {
  "=== $(Get-Date -Format 'HH:mm:ss') $label ===" | Tee-Object -FilePath $log -Append
  & $python @argList 2>&1 | Tee-Object -FilePath $log -Append
  if ($LASTEXITCODE -ne 0) {
    "! $label exit $LASTEXITCODE" | Tee-Object -FilePath $log -Append
    return $false
  }
  return $true
}

$failed = @()
foreach ($s in $steps) {
  $argList = @("-m", $s.m)
  # โหมดซ้อม: ตัวที่ไม่มี flag ให้ข้ามไปเลย ดีกว่ารันจริงโดยไม่ตั้งใจ
  if ($DryRun) {
    if (-not $s.dry) { "-- SKIP $($s.m) (no dry-run mode)" | Tee-Object -FilePath $log -Append; continue }
    $argList += $s.dry
  }
  if (-not (Run-Step $s.m $argList)) { $failed += $s.m }
}

# หมวดของเว็บทำทีละกลุ่ม — กลุ่มไหนพังก็ไม่ลากกลุ่มอื่นล้มตาม
foreach ($g in @("bedroom", "living", "dining", "office", "decor", "special")) {
  $argList = @("-m", "app.etl.sync_web_categories", "--group", $g)
  if ($DryRun) { $argList += "--dry-run" }
  if (-not (Run-Step "sync_web_categories --group $g" $argList)) { $failed += "web_categories:$g" }
}

Get-ChildItem $logDir -Filter "products_*.log" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force

if ($failed.Count -gt 0) {
  "FINISHED WITH ERRORS: $($failed -join ', ')" | Tee-Object -FilePath $log -Append
  exit 1   # ให้ Task Scheduler เห็นว่า last run result ไม่ใช่ 0
}
"PRODUCTS DONE $(Get-Date -Format 'HH:mm:ss') - log: $log" | Tee-Object -FilePath $log -Append
