@echo off
rem Double-click to start the Swarm Maestro hub and open the dashboard.
rem Keep this window open during the demo. Close it (or press Ctrl+C) to stop.
title Swarm Maestro hub
cd /d "%~dp0hub"
if not exist ".venv\Scripts\python.exe" (
    echo Setting up Python environment, first run only...
    python -m venv .venv || goto :fail
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :fail
)
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul && (
    echo Hub is already running. Opening the dashboard.
    start "" http://localhost:8000
    timeout /t 3 >nul
    exit /b 0
)
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
echo Starting hub on http://localhost:8000  (close this window to stop)
".venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000
exit /b 0
:fail
echo Setup failed. Is Python installed?
pause
