# FINS 2026 — v0.8 SwimTime LAN TEST release

Start with **START_HERE_v08_AR.html** or **docs/README_v08_AR.html**.

Existing v0.7: stop FINS and the raw monitor, then run UPDATE_EXISTING_v07.cmd from the new release. It updates the existing project with backup, preserving credentials, databases and assets. Run RUN_SWIMTIME_TEST_LAN.cmd from the updated project and open SwimTime TEST. Fresh installs use INSTALL_SINGLE_OPERATOR.cmd.

The integrated UDP observer shows received TEST clock/channel values and supports replay of the supplied 2,754-message recording. Ten lane values match the source screen at 0.0001 s/tick. No official timing, finish interpretation, publication, TVG or LED program routing is enabled from this feed. See docs/SwimTime_v08_Verification.md.

Windows v0.8 acceptance, physical ALGE lane/finish test and FISU template approval remain pending.

---

## Historical v0.7 notes

# FINS 2026 — v0.7 Single Operator / OBS LAN engineering build

Start with **READ_ME_AR.html** (Arabic installation, Wi-Fi, OBS, timing limitations and recovery).

1. Extract into a new folder and retain the old project and database.
2. Install Python 3.12 x64 and run `INSTALL_SINGLE_OPERATOR.cmd`.
3. Read the locally generated `runtime/SINGLE_TEST_CREDENTIALS.txt`.
4. Run `RUN_SINGLE_TEST_LAN.cmd`; sign in as `operator`.
5. On the OBS computer open `http://SERVER_PRIVATE_IP:8765/broadcast_tvg/setup.html`.
6. OBS Browser Source URL: `http://SERVER_PRIVATE_IP:8765/broadcast_tvg/?program=1`, 1920x1080, transparent background.

The included frontend is already built; Node is not required on the venue PC. Windows wheels are bundled. Actual Windows installation, OBS, Wi-Fi, physical LED and ALGE tests remain pending.

Single-operator mode retains reason/audit/revision checks. Recording external Chief/Jury approvals requires the named authority and document reference; it is not a claim of independent software signatures. TEST and VENUE databases remain separate. VENUE graphics remain gated by production approval.

GEN support is read-only structural inspection of the five supplied SwimTime 2.4.10.1 files. Field meanings, identity/lane mapping and corrected-file precedence are not verified. Network Display protocol decoding is not implemented. Existing serial profiles require real device validation. No new live ALGE integration is claimed.

The FISU results asset correction is included. Missing ranked-row, clock and medal sprites remain explicit blockers; no complete FISU visual match or approved LED layout is claimed. No purple venue/mascot replacement is loaded by LED results.

Current evidence: `docs/Release_v07_Status.json` and `testing/reports/v07_*`. Older reports remain historical v0.6 evidence.
