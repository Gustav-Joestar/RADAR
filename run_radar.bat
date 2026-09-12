@echo off
setlocal
cd /d "%~dp0"
title RADAR

if not exist ".venv\Scripts\python.exe" (
    echo [*] Virtual environment not found. Running installation...
    call install.bat
)

if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" launcher.py
) else (
    start "" python launcher.py
)