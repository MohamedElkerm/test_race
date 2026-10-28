# Installation, backup and disaster recovery

## Verified scope

Python services, bundled frontend build, browser outputs, API/workflow tests, native raster conversions, software serial PTY and local failure recovery were executed in Linux. A Windows 11 computer, ALGE device, LED processor and broadcast mixer were not available. The Windows scripts were prepared and reviewed; their execution on Windows 11 is PENDING. This release is source + built browser application + Windows dependency wheels, not a signed Windows EXE/MSI.

## Windows requirements

- Windows 11 x64 with Python 3.12 x64 and its launcher. The Surface is the dashboard client.
- A local writable project directory. Python dependencies in `installers/wheels-win64` are for CPython 3.12 x64.
- A supported browser on each operator/output host. The built dashboard needs no Node runtime and no Internet/CDN connection.
- An approved, receive-only RS232 adapter/cable on the timing PC. Do not connect TTL, scoreboard output or an unknown pinout to TM-SWIM Video-Out.
- A vendor-confirmed LED output chain. Independent software canvases do not create six physical GPU channels.

Run `installers\INSTALL_TEST.cmd`, then `RUN_TEST.cmd`. Installation runs preflight hashes and writes `runtime/preflight.json`. The setup fails on missing or modified source/built files. A Python installer is not bundled; obtain the approved Python distribution before offline deployment.

For a separate engineering venue database:

```powershell
.venv\Scripts\python.exe -m results_backend.cli --mode VENUE user osama_admin SYSTEM_ADMINISTRATOR
.venv\Scripts\python.exe -m results_backend.cli --mode VENUE user timing_01 TIMING_OPERATOR
```

Provision the other five named roles similarly with separate operators and passwords. Passwords are prompted, not placed on the command line. Start `deployment\RUN_VENUE_ENGINEERING.cmd`. Do not import TEST fixtures. VENUE TAKE remains approval-gated. The package does not install a Windows service or scheduled task; use a supervised console for first acceptance, then agree restart/autostart policy with venue IT.

## Gateway connection

Record device model/serial, firmware, SwimTime version, COM port, actual baud, cable pinout and selected profile in the acceptance record. Inspect the manufacturer manual pp32-33 with the timing supplier. The interface section gives 19200 8N1; an older summary differs, so actual settings must be confirmed. RR columns and START behaviour vary by version.

```powershell
.venv\Scripts\python.exe -m alge_gateway.main --url http://RESULTS_SERVER:8765 --user timing_01 --source TM-SWIM-PRIMARY --heat VENUE_HEAT_ID --profile tm-swim-video-modern-v1 --port COM3 --baud 19200 --spool runtime\alge-primary.sqlite3 --confirm-profile
```

`--confirm-profile` is an operator acknowledgement to open the selected profile, not a claim that hardware was verified by this development. The gateway prompts for the timing password. Do not change its stable source ID or discard its spool during a race. Bind a new heat only between races. Retain raw captures of start, running, every split/finish, corrections, deletion, false starts and reconnect scenarios. On serial/network loss the gateway retries with bounded backoff and keeps raw queued frames. No device commands are transmitted.

For synthetic replay in TEST only:

```powershell
.venv\Scripts\python.exe -m alge_gateway.main --url http://127.0.0.1:8765 --user timing --source TEST-REPLAY-01 --heat TEST-IND-1 --profile tm-swim-video-modern-v1 --spool runtime\test-replay.sqlite3 --replay testing\fixtures\manual_reconstructed_modern.hex
```

Use an unused READY heat. Replaying into an OFFICIAL heat is rejected. A physical device connection has not been tested in this delivery. Network Display, Splash/Lenex and Hy-Tek adapters require their own approved real samples before implementation.

## Backup policy

1. Before each session, take a results-server backup through Audit & recovery as Administrator. This uses SQLite's online backup API and produces a consistent file in `backups/`.
2. Keep backup, gateway spool/raw data, approvals/audit, configuration and immutable assets together with their checksums. The gateway spool is separate from the results database; include it in the operational backup plan when its process is stopped or use a separate SQLite online backup.
3. Copy verified backups to a second local drive/workstation under venue access controls. No automatic replication or offsite backup is implemented.
4. After each approved session, record filename, timestamp, operator, revision and successful restore rehearsal.

## Restore procedure

- Black out outputs and stop the FastAPI process. Stop gateway delivery while deciding the recovery point; preserve its spool.
- Preserve the interrupted database and its WAL/SHM files for investigation. Do not copy a live SQLite file as a backup.
- Restore with the local CLI, using the correct mode and path:

```powershell
.venv\Scripts\python.exe -m results_backend.cli --mode TEST restore backups\SELECTED_BACKUP.sqlite3 --confirm-stopped
```

- The CLI checks database integrity and mode, restores via SQLite backup, revokes sessions, blacks out LED routes, clears TV program/preview and sets recovery hold.
- Restart, sign in, verify roster/heat, raw-source continuity, approvals and publication status. Reconnect the preserved gateway and reconcile any queued data. Old official heats remain locked; do not silently replay into an approved heat.
- Re-authorise routes and release blackout only after the operators verify the displayed revision. No automatic multi-server failover is claimed.

## Rebuild and rerun QA

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.venv\Scripts\python.exe -m pytest testing\test_system.py -q --junitxml=testing\reports\functional.xml
```

Frontend rebuild from `control_dashboard`: `npm ci`, then `npm run build`. Browser QA needs Playwright and an installed Chromium executable; run `testing/browser.cjs` with `FINS_CHROME` set to its path and Playwright available in Node's module path. The POSIX PTY harness is a software serial test and is not a Windows COM acceptance test.

The final venue acceptance must include at least a full competition-day soak, actual Surface resource monitoring, end-to-end hardware latency, LAN switch disconnect, serial cable disconnect, power restoration, approved backup restore, mixer alpha capture and all six physical LED screens.
