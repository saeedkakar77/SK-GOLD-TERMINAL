@echo off
title SK Institutional Trading Terminal
cd /d "C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app"

echo ========================================================
echo    SK INSTITUTIONAL TRADING TERMINAL (100% ONLINE)
echo ========================================================

:: 1. Clean up any previous server on port 5000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: 2. Launch the server in background
echo Starting SK Trading Signal Server...
start "SK Trading Server" /min python server.py
ping 127.0.0.1 -n 3 >nul

:: 3. Launch Dedicated App Window in Edge or Chrome
echo Launching Standalone Terminal Window...
start msedge --app="http://127.0.0.1:5000" --start-maximized 2>nul || start chrome --app="http://127.0.0.1:5000" 2>nul || start http://127.0.0.1:5000
exit
