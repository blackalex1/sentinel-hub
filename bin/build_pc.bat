@echo off
setlocal

:: Корень проекта на уровень выше от папки bin
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

echo [1/3] Activating virtual environment...
if not exist "venv10\Scripts\activate.bat" (
    echo Error: Virtual environment not found in "%CD%\venv10\"
    pause
    exit /b 1
)
call venv10\Scripts\activate.bat

echo [2/3] Checking requirements for build...
where pyinstaller >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo PyInstaller not found. Installing requirements...
    pip install pyinstaller pillow
) else (
    echo PyInstaller is already installed. Skipping install check.
)

echo [3/3] Starting build script in bin...
python bin\build_exe.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] BUILD FAILED with error code %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [OK] Build process completed!
echo Your executable should be in bin/
pause
