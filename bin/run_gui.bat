@echo off
cd /d "%~dp0.."
call venv\Scripts\activate 2>nul || call ..\venv\Scripts\activate 2>nul
python pc_gui_app.py
pause
