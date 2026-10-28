@echo off
setlocal
cd /d "%~dp0"
echo Stop the existing FINS server and RUN_FINS_MONITOR before updating.
echo Enter the existing FINS2026_LIVE_RESULTS folder path without quotation marks.
set /p "FINS_TARGET=Existing project folder: "
if not exist "%FINS_TARGET%\.venv\Scripts\python.exe" (
 echo Existing Python environment not found. No files changed.
 pause
 exit /b 1
)
"%FINS_TARGET%\.venv\Scripts\python.exe" "%~dp0deployment\apply_v08.py" --target "%FINS_TARGET%"
pause
