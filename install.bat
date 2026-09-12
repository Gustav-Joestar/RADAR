@echo off
setlocal
cd /d "%~dp0"
title RADAR - Installation

echo ============================================================
echo  RADAR: Setup and Virtual Environment Installation
echo ============================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found on system PATH.
    echo Please install Python 3.10+ from python.org and check Add Python to PATH.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment: .venv
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created successfully.
) else (
    echo [*] Existing virtual environment detected.
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Upgrading pip...
python -m pip install --upgrade pip --quiet

echo [*] Installing required packages from requirements.txt...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  [SUCCESS] RADAR installation complete!
echo  You can now launch the app using run_radar.bat
echo ============================================================
echo.
pause