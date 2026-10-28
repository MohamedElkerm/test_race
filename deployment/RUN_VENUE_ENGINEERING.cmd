@echo off
setlocal
cd /d "%~dp0.."
set "FINS_MODE=VENUE"
set "FINS_DB=%CD%\runtime\venue.sqlite3"
echo VENUE ENGINEERING MODE - not production approved.
echo No test fixtures are loaded. Provision users with results_backend.cli.
echo TV TAKE remains blocked until template production approval is recorded in the registry.
".venv\Scripts\python.exe" -m uvicorn results_backend.app:app --host 0.0.0.0 --port 8765
pause
