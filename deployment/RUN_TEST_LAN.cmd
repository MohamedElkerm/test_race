@echo off
setlocal
cd /d "%~dp0.."
set "FINS_MODE=TEST"
set "FINS_DB=%CD%\runtime\test.sqlite3"
echo TEST LAN server. Use the server's actual private IPv4 address from the other computers.
echo Keep this venue network isolated and restrict inbound TCP 8765 to the operator and player hosts.
echo This command does not change Windows Firewall.
".venv\Scripts\python.exe" -m uvicorn results_backend.app:app --host 0.0.0.0 --port 8765
pause
