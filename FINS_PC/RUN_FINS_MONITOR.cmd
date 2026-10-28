@echo off
setlocal
cd /d "%~dp0"
set "finsPython=%~dp0..\.venv\Scripts\python.exe"
if not exist "%finsPython%" (
  echo Copy the FINS_PC folder into FINS2026_LIVE_RESULTS, beside .venv.
  echo Then run this file again.
  pause
  exit /b 1
)
"%finsPython%" "%~dp0swimtime_monitor.py" --port 26 --source-ip 10.227.186.112 --seconds 300
pause
