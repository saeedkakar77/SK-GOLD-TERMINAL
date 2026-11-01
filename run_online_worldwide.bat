@echo off
title SK Institutional Gold Terminal (Worldwide Online Mode)
cd /d "C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app"

echo ========================================================
echo    SK INSTITUTIONAL GOLD TERMINAL — WORLDWIDE ONLINE
echo ========================================================

:: 1. Start python server if not listening on port 5000
netstat -aon | findstr :5000 | findstr LISTENING >nul
if errorlevel 1 (
    echo Starting SK Gold Signal Engine on Port 5000...
    start "SK Trading Server" /min python server.py
    ping 127.0.0.1 -n 3 >nul
) else (
    echo SK Gold Signal Engine is already active on Port 5000.
)

:: 2. Launch Ngrok High-Speed Edge Tunnel
echo Starting Ngrok Worldwide Secure Tunnel...
start "SK Ngrok Tunnel" /min node ngrok_tunnel.js

ping 127.0.0.1 -n 3 >nul

echo ========================================================
echo [*] TERMINAL IS LIVE WORLDWIDE 24/7!
echo [*] Desktop Shortcut: ONLINE_MOBILE_LINK.url
echo ========================================================
