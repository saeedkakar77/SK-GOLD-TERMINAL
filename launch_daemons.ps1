$appDir = "C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app"
$pyExe = "C:\Users\princ\AppData\Local\Programs\Python\Python312\python.exe"
$nodeExe = "C:\Users\princ\tools\node\node.exe"

# 0. Clean up existing instances first
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*server.py*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*ngrok_tunnel.js*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 1

# 1. Start Python Server detached via WMI
$p1 = ([wmiclass]"win32_process").Create("`"$pyExe`" -u `"$appDir\server.py`"", $appDir, $null)
Write-Host "Started Python Server PID: $($p1.ProcessId)"

Start-Sleep -Seconds 2

# 2. Start Ngrok Tunnel detached via WMI
$p2 = ([wmiclass]"win32_process").Create("`"$nodeExe`" `"$appDir\ngrok_tunnel.js`"", $appDir, $null)
Write-Host "Started Ngrok Tunnel PID: $($p2.ProcessId)"

Start-Sleep -Seconds 3
