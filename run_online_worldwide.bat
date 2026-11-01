@echo off
title SK Institutional Gold Terminal (Worldwide Online Mode)
cd /d "C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app"

echo ========================================================
echo    SK INSTITUTIONAL GOLD TERMINAL — WORLDWIDE ONLINE
echo ========================================================

:: 1. Start python server if not listening on port 5000
netstat -aon | findstr :5000 | findstr LISTENING >nul
if errorlevel 1 (
    echo Starting SK Gold Signal Server...
    start "SK Trading Server" /min python server.py
    ping 127.0.0.1 -n 3 >nul
) else (
    echo SK Gold Signal Server is already running.
)

:: 2. Launch Cloudflare Worldwide Secure Tunnel
echo Connecting to Worldwide Secure Edge Network...
python tunnel_launcher.py
