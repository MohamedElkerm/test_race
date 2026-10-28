@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run INSTALL_SINGLE_OPERATOR.cmd first.
 pause
 exit /b 1
)
set "FINS_OPERATOR_MODE=SINGLE"
set "FINS_MODE=VENUE"
set "FINS_DB=%CD%\runtime\single_venue.sqlite3"
".venv\Scripts\python.exe" -m deployment.bootstrap_single
if errorlevel 1 (pause & exit /b 1)
echo Private credentials: runtime\SINGLE_VENUE_CREDENTIALS.txt
echo Control: http://127.0.0.1:8765
echo OBS: http://SERVER_PRIVATE_IP:8765/broadcast_tvg/?program=1
echo Limit firewall TCP 8765 to the local production network. This script changes no firewall rules.
".venv\Scripts\python.exe" -m uvicorn results_backend.app:app --host 0.0.0.0 --port 8765
pause
