# إيقاف خدمات المشروع — الخادم (منفذ 8501) + بوت تليجرام
# يستدعيه إيقاف_المشروع.bat — بلا اقتباس مزدوج هش
$ErrorActionPreference = "SilentlyContinue"

# 1) الخادم: مالك منفذ 8501
$serverPid = Get-NetTCPConnection -LocalPort 8501 -State Listen |
    Select-Object -ExpandProperty OwningProcess
if ($serverPid) {
    Stop-Process -Id $serverPid -Force
    Write-Host "[OK] Server stopped (PID $serverPid)"
} else {
    Write-Host "[i] Server was not running"
}

# 2) بوت تليجرام: أي عملية bot.py
$bots = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*bot.py*" }
if ($bots) {
    foreach ($b in $bots) {
        Stop-Process -Id $b.ProcessId -Force
        Write-Host "[OK] Bot stopped (PID $($b.ProcessId))"
    }
} else {
    Write-Host "[i] Bot was not running"
}

if (Test-Path "bot.lock") { Remove-Item "bot.lock" -Force }
Write-Host "[OK] All project services stopped."
