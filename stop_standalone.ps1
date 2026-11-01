# Stop Signal Engine
$serverProc = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*server.py*" }
if ($serverProc) {
    Stop-Process -Id $serverProc.ProcessId -Force
    Write-Host "[x] Stopped Signal Engine (PID: $($serverProc.ProcessId))" -ForegroundColor Red
} else {
    Write-Host "[i] Signal Engine was not running." -ForegroundColor Yellow
}

# Stop Ngrok Tunnel
$ngrokProc = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*ngrok_tunnel.js*" }
if ($ngrokProc) {
    Stop-Process -Id $ngrokProc.ProcessId -Force
    Write-Host "[x] Stopped Ngrok Tunnel (PID: $($ngrokProc.ProcessId))" -ForegroundColor Red
} else {
    Write-Host "[i] Ngrok Tunnel was not running." -ForegroundColor Yellow
}

Write-Host "`nSK Gold Terminal processes have been cleanly stopped.`n" -ForegroundColor Green
