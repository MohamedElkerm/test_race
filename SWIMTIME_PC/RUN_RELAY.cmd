@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0RELAY_LOCAL_TO_FINS.ps1" -TargetIP 10.227.186.166 -Port 26 -Seconds 300
pause
