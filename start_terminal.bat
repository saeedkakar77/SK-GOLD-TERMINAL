@echo off
cd /d "C:\Users\princ\.gemini\antigravity\scratch\trading_signal_app"

:: 1. Start Python Server in background
netstat -ano | findstr 0.0.0.0:5000 >nul 2>&1
if %errorlevel% neq 0 (
    start "SK_Gold_Server" /min "C:\Users\princ\AppData\Local\Programs\Python\Python312\python.exe" -u server.py
)

:: Wait 3 seconds cleanly without timeout error
ping -n 3 127.0.0.1 >nul

:: 2. Start Ngrok Tunnel in background
tasklist /fi "imagename eq node.exe" | findstr /i "node.exe" >nul 2>&1
if %errorlevel% neq 0 (
    start "SK_Ngrok_Tunnel" /min "C:\Users\princ\tools\node\node.exe" ngrok_tunnel.js
)
