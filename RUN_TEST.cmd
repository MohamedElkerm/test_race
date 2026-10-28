@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run installers\INSTALL_TEST.cmd first.
 pause
 exit /b 1
)
set "FINS_MODE=TEST"
set "FINS_DB=%CD%\runtime\test.sqlite3"
echo Open http://127.0.0.1:8765 on this computer.
echo TEST credentials: runtime\TEST_OPERATOR_CREDENTIALS.txt
echo Press Ctrl+C to stop cleanly.
".venv\Scripts\python.exe" -m uvicorn results_backend.app:app --host 127.0.0.1 --port 8765
pause
