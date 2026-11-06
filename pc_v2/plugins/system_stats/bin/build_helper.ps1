# Скрипт сборки MonitHomeHelper
$ErrorActionPreference = "Stop"

# Определяем пути
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = Resolve-Path "$ScriptDir\.."
$SourceFile = "$RootDir\sensor_helper.py"
$BinDir = "$RootDir\bin"
$DllPath = "$BinDir\LibreHardwareMonitorLib.dll"

Write-Host "--- Starting Build Process ---" -ForegroundColor Cyan

# 1. Очистка
Write-Host "Cleaning old artifacts..."
if (Test-Path "$RootDir\build") { Remove-Item -Recurse -Force "$RootDir\build" }
if (Test-Path "$RootDir\dist") { Remove-Item -Recurse -Force "$RootDir\dist" }
if (Test-Path "$RootDir\MonitHomeHelper.spec") { Remove-Item -Force "$RootDir\MonitHomeHelper.spec" }

# 2. Сборка
Write-Host "Running PyInstaller..."
Set-Location $RootDir
# Используем venv если он есть в корне проекта
$PythonExe = "python"
if (Test-Path "$RootDir\..\..\..\venv10\Scripts\python.exe") {
    $PythonExe = "$RootDir\..\..\..\venv10\Scripts\python.exe"
}

& $PythonExe -m PyInstaller --onefile --noconsole `
    --add-data "bin/LibreHardwareMonitorLib.dll;bin" `
    --name MonitHomeHelper `
    sensor_helper.py

# 3. Перемещение результата
Write-Host "Stopping running helper processes..."
try {
    Stop-Process -Name "MonitHomeHelper" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
} catch {}

Write-Host "Moving EXE to expected locations..."
$GlobalBin = Resolve-Path "$RootDir\..\..\bin" -ErrorAction SilentlyContinue
if (-not $GlobalBin) {
    # Пытаемся создать pc_v2/bin
    $GlobalBin = New-Item -ItemType Directory -Force -Path "$RootDir\..\..\bin"
}

if (Test-Path "$RootDir\dist\MonitHomeHelper.exe") {
    # Копируем в локальный bin плагина
    Copy-Item -Path "$RootDir\dist\MonitHomeHelper.exe" -Destination "$BinDir\MonitHomeHelper.exe" -Force
    # Перемещаем в глобальный bin проекта
    Move-Item -Path "$RootDir\dist\MonitHomeHelper.exe" -Destination "$GlobalBin\MonitHomeHelper.exe" -Force
    Write-Host "Copied to: $BinDir"
    Write-Host "Moved to: $GlobalBin"
}

# 4. Финальная очистка
Write-Host "Final cleaning..."
Remove-Item -Recurse -Force "$RootDir\build"
Remove-Item -Recurse -Force "$RootDir\dist"
Remove-Item -Force "$RootDir\MonitHomeHelper.spec"

Write-Host "--- Build Finished Successfully! ---" -ForegroundColor Green
Write-Host "New helper is located at: $BinDir\MonitHomeHelper.exe"
