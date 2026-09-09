# ซิงค์รายวัน — เงื่อนไขค่าส่ง (Amasty) + ที่อยู่ไทย (directory_*) จาก Magento
#
# ลงตารางเรียบร้อยทั้งฐานเว็บ 10.9.11.111 (sb_*) และฐานแอป — อ่าน Magento อย่างเดียว
# ล็อกเก็บที่ backend/logs/sync_YYYY-MM-DD.log เก็บ 30 วันล่าสุด
#
# ตั้งให้รันทุกวันตี 3 (รันครั้งเดียวใน PowerShell แบบ Administrator):
#
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" `
#        -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\Users\Budsakorn.s\Documents\sbdesign\backend\scripts\sync_daily.ps1"
#   $t = New-ScheduledTaskTrigger -Daily -At 3am
#   Register-ScheduledTask -TaskName "sbdesign-sync-daily" -Action $a -Trigger $t -RunLevel Highest
#
# ตรวจผลย้อนหลัง:  Get-ScheduledTaskInfo -TaskName "sbdesign-sync-daily"

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $PSScriptRoot
$python  = Join-Path $backend ".venv\Scripts\python.exe"
$logDir  = Join-Path $backend "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ("sync_" + (Get-Date -Format "yyyy-MM-dd") + ".log")

$env:PYTHONPATH = $backend
$env:PYTHONIOENCODING = "utf-8"
Set-Location $backend

$failed = @()
foreach ($mod in @("app.etl.sync_shipping_rules", "app.etl.sync_thai_geo")) {
  "=== $(Get-Date -Format 'HH:mm:ss') $mod ===" | Out-File -FilePath $log -Append -Encoding utf8
  & $python -m $mod | Out-File -FilePath $log -Append -Encoding utf8
  # ตัวไหนล้มก็ให้ตัวที่เหลือรันต่อ แล้วค่อยรายงานรวมตอนจบ — ค่าส่งกับที่อยู่ไม่ได้ขึ้นต่อกัน
  if ($LASTEXITCODE -ne 0) { $failed += $mod; "! $mod exit $LASTEXITCODE" | Out-File -FilePath $log -Append -Encoding utf8 }
}

Get-ChildItem $logDir -Filter "sync_*.log" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force

if ($failed.Count -gt 0) {
  "เสร็จแบบมีปัญหา: $($failed -join ', ')" | Out-File -FilePath $log -Append -Encoding utf8
  exit 1   # ให้ Task Scheduler เห็นว่า last run result ไม่ใช่ 0
}
"เสร็จเรียบร้อย $(Get-Date -Format 'HH:mm:ss')" | Out-File -FilePath $log -Append -Encoding utf8
