@echo off
setlocal
cd /d "%~dp0.."

call venv\Scripts\activate 2>nul || call ..\venv\Scripts\activate 2>nul
echo [INFO] Starting Sentinel Hub from source...
python pc_gui_app.py

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Application exited with error code %ERRORLEVEL%
    pause
)
