@echo off
title Stop SK Trading Terminal
echo Stopping SK Trading Terminal Server...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
    echo Server process %%a terminated.
)
echo SK Terminal Server stopped.
timeout /t 2 /nobreak >nul
