@echo off
title Low DR Website Finder Dashboard
cd /d "%~dp0"

echo ================================================
echo   LOW DR WEBSITE FINDER - Starting dashboard...
echo ================================================
echo.

:: Check if Python is installed
set "PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"

"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python installed nahi hai!
    echo Please install Python from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [INFO] Checking and installing dependencies...
if not exist "%~dp0.env" (
    copy /y "%~dp0.env.example" "%~dp0.env" >nul
    echo [INFO] Created .env. Add your own API keys there before searching.
)
"%PYTHON%" -m pip install -q -r requirements.txt

echo.
echo [INFO] Starting dashboard in your browser...
echo [INFO] This computer: http://localhost:8502
echo [INFO] Same Wi-Fi devices can use the Network URL shown below.
echo.

:: Make the dashboard reachable from devices on the same trusted Wi-Fi network.
"%PYTHON%" -m streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8502 --server.headless true --browser.gatherUsageStats false

echo.
echo ================================================
echo   Task Complete. Press any key to exit.
echo ================================================
pause