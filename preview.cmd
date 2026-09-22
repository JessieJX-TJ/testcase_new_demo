@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo Starting Workbench at http://127.0.0.1:4000/index.html
start "" "http://127.0.0.1:4000/index.html"
python app.py
