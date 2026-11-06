@echo off
setlocal
cd /d "%~dp0.."

set PYTHON_EXE=venv10\Scripts\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment not found at %PYTHON_EXE%
    echo Please run build_pc.bat first or fix your venv.
    pause
    exit /b 1
)

echo [INFO] Starting MonitHome PC from source...
"%PYTHON_EXE%" pc_v2\pc_gui_app.py

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Application crashed with exit code %ERRORLEVEL%
    pause
)
