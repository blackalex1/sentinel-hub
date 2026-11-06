param(
    [switch]$Clean
)

# Скрипт для сборки проекта в ЕДИНЫЙ EXE файл

$ProjectRoot = Get-Location
$BinDir = Join-Path $ProjectRoot "bin"
$BuildTmp = Join-Path $ProjectRoot "build_tmp"

Write-Host "--- Starting Single EXE Build Process ---" -ForegroundColor Cyan

# 1. Проверка
if (!(Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "PyInstaller not found. Installing..." -ForegroundColor Yellow
    pip install pyinstaller pillow
}

# 2. Очистка
Write-Host "Cleaning up old builds..."
if ($Clean) {
    if (Test-Path $BinDir) { Remove-Item -Recurse -Force $BinDir }
    if (Test-Path $BuildTmp) { Remove-Item -Recurse -Force $BuildTmp }
    if (Test-Path "MonitHome.spec") { Remove-Item "MonitHome.spec" }
} else {
    $ExePath = Join-Path $BinDir "MonitHome.exe"
    if (Test-Path $ExePath) { Remove-Item -Force $ExePath }
}

# 3. Сборка
Write-Host "Building single executable (please wait)..." -ForegroundColor Green

$ArgsList = @(
    "--noconsole",
    "--onefile",
    "--name", "MonitHome",
    "--distpath", "$BinDir",
    "--workpath", "$BuildTmp",
    "--noupx",
    "--exclude-module", "numpy",
    "--exclude-module", "pandas",
    "--exclude-module", "matplotlib",
    "--exclude-module", "scipy",
    "--exclude-module", "tkinter",
    "--exclude-module", "IPython",
    "--add-data", "web;web",
    "--add-data", "plugins;plugins",
    "--icon", "web/favicon.png",
    "pc_gui_app.py"
)

if ($Clean) {
    $ArgsList += "--clean"
}

pyinstaller @ArgsList

if ($LASTEXITCODE -eq 0) {
    # Очистка мусора
    if (Test-Path $BuildTmp) { Remove-Item -Recurse -Force $BuildTmp }
    if (Test-Path "MonitHome.spec") { Remove-Item "MonitHome.spec" }

    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "BUILD SUCCESSFUL!" -ForegroundColor Green
    Write-Host "Single EXE is located in: $BinDir\MonitHome.exe"
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host "`nBUILD FAILED!" -ForegroundColor Red
}
