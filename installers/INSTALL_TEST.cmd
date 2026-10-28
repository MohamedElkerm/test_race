@echo off
setlocal
cd /d "%~dp0.."
echo FINS 2026 - engineering TEST setup. Production approval is pending.
py -3.12 -c "import sys,struct; assert sys.version_info[:2] == (3,12); assert struct.calcsize('P')==8" 2>nul
if errorlevel 1 (
 echo Install Python 3.12 64-bit with the Windows Python launcher first.
 pause
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install --no-index --find-links installers\wheels-win64 -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m deployment.preflight
if errorlevel 1 goto :failed
set "FINS_MODE=TEST"
".venv\Scripts\python.exe" -m deployment.bootstrap
if errorlevel 1 goto :failed
echo.
echo Setup complete. Open runtime\TEST_OPERATOR_CREDENTIALS.txt for your local test accounts.
echo Start RUN_TEST.cmd from the project root.
echo Windows installation procedure requires a witnessed Windows 11 acceptance test.
pause
exit /b 0
:failed
echo Setup failed. Review the error above; no production installation has been approved.
pause
exit /b 1
