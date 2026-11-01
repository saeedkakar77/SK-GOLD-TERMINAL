$appDir = "C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app"
$pyExe = "C:\Users\princ\AppData\Local\Programs\Python\Python312\python.exe"
$nodeExe = "C:\Users\princ\tools\node\node.exe"

# 1. Start Python Server if not running
$serverProc = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*server.py*" }
if (-not $serverProc) {
    Write-Host "[1/2] Starting SK Gold Signal Engine on Port 5000..." -ForegroundColor Cyan
    Start-Process -FilePath $pyExe -ArgumentList "-u server.py" -WorkingDirectory $appDir -WindowStyle Hidden
    Start-Sleep -Seconds 2
} else {
    Write-Host "[1/2] Signal Engine already running in background (PID: $($serverProc.ProcessId))." -ForegroundColor Green
}

# 2. Start Ngrok Tunnel if not running
$ngrokProc = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*ngrok_tunnel.js*" }
if (-not $ngrokProc) {
    Write-Host "[2/2] Starting 24/7 Ngrok Worldwide Tunnel..." -ForegroundColor Cyan
    Start-Process -FilePath $nodeExe -ArgumentList "ngrok_tunnel.js" -WorkingDirectory $appDir -WindowStyle Hidden
    Start-Sleep -Seconds 2
} else {
    Write-Host "[2/2] Ngrok Tunnel already running in background (PID: $($ngrokProc.ProcessId))." -ForegroundColor Green
}

Write-Host "`n========================================================" -ForegroundColor Yellow
Write-Host " [SUCCESS] SK GOLD TERMINAL IS RUNNING INDEPENDENTLY!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Yellow
Write-Host " Aap is window ko aur Antigravity ko befikar CLOSE kar sakte hain." -ForegroundColor White
Write-Host " Link background mein 24/7 bina kisi rukawat ke chalta rahega!" -ForegroundColor White
Write-Host "`n Active Worldwide Link:" -ForegroundColor Yellow
Write-Host " https://unholy-boondocks-snazzy.ngrok-free.dev" -ForegroundColor Green
Write-Host "========================================================`n" -ForegroundColor Yellow
