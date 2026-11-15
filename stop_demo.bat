@echo off
rem Double-click to stop the Swarm Maestro hub (whatever is serving port 8000).
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do (
    taskkill /PID %%p /T /F >nul 2>&1 && echo Stopped hub, process %%p.
)
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul || echo Hub is not running.
timeout /t 3 >nul
