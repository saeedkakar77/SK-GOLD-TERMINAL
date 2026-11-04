$appDir = "C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app"

# 1. Start Python Server detached
$pyCmd = "cmd.exe /c cd /d `"$appDir`" && python server.py"
$pyProc = ([wmiclass]"win32_process").Create($pyCmd)
Write-Host "Started Python Server PID: $($pyProc.ProcessId)"

Start-Sleep -Seconds 2

# 2. Start Ngrok Tunnel detached
$nodeCmd = "cmd.exe /c cd /d `"$appDir`" && node ngrok_tunnel.js"
$nodeProc = ([wmiclass]"win32_process").Create($nodeCmd)
Write-Host "Started Ngrok Tunnel PID: $($nodeProc.ProcessId)"

Start-Sleep -Seconds 3
