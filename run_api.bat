@echo off
cd /d "%~dp0"
set "FLASK_PORT=5001"
".venv\Scripts\python.exe" app_api.py
pause
