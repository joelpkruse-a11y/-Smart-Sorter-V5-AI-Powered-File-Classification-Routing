@echo off
cd /d C:\SmartInbox

echo Starting Smart Sorter Dashboard...
start "" C:\SmartInbox\.venv\Scripts\python.exe -c "from v3_debug_dashboard import start_dashboard; start_dashboard(port=8765)"

echo Starting Photo Dashboard...
start "" C:\SmartInbox\.venv\Scripts\python.exe photo_dashboard.py

echo Waiting for dashboards to start...
timeout /t 2 >nul

echo Opening dashboards in browser...
start http://localhost:8765
start http://localhost:5005

echo Dashboards launched.