@echo off
title SK Gold Terminal - VPS Setup & 24/7 Launcher
cd /d "%~dp0"

echo =================================================================
echo    SK INSTITUTIONAL GOLD TERMINAL — VPS SETUP & 24/7 LAUNCHER
echo =================================================================
echo.

:: 1. Check if Python is already available
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Python is already installed and ready!
    goto :RUN_SERVER
)

echo [!] Python is not installed on this VPS yet.
echo [*] Downloading and installing official Python 3.11 automatically...
echo [*] Please wait 1-2 minutes...
echo.

powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', 'python_setup.exe')"

if not exist "python_setup.exe" (
    echo [ERROR] Failed to download Python automatically.
    echo Please open your VPS browser and download Python from:
    echo https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    pause
    exit /b 1
)

echo [*] Installing Python silently with system PATH...
python_setup.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
timeout /t 15 /nobreak >nul
del python_setup.exe >nul 2>&1

:: Refresh PATH in current cmd session
set "PATH=C:\Program Files\Python311;C:\Program Files\Python311\Scripts;%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [!] Python installation finished.
    echo Please double-click 'INSTALL_AND_RUN_VPS.bat' once again to start the server!
    pause
    exit /b 0
)

echo.
echo [SUCCESS] Python is now successfully installed on your VPS!
echo.

:RUN_SERVER
echo =================================================================
echo [*] Starting SK Institutional Gold Terminal 24/7 Server...
echo [*] Scanning Gold 24/7 across 16 SMC Strategies...
echo =================================================================
echo.
python server.py
echo.
echo [Server stopped]
pause
