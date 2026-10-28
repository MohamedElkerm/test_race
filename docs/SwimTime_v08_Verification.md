# FINS v0.8 — observed SwimTime TEST reception

Story: one operator starts the UDP observer in the FINS dashboard; bytes relayed from SwimTime are parsed and logged; WebSocket updates show the received clock and channel times; missing or stopped clock data is suppressed. The observer never changes competition timing, approvals, publications or graphics routes.

## Field evidence supplied by the operator

- SwimTime 2.4.10.1; SU3 available for start testing, no physical lane touchpad/backup-button test available.
- Capture: evidence/swimtime/udp26-20261024T000648Z-1792800408138675400.jsonl.
- SHA-256: f406de2726311dc569a2bc17fcd6d4a5c34c72f7e68c0497b931bb38553644fe.
- 2,754 datagrams, all structurally parsed with the observed v2 parser. 2,690 RunningTime; 24 LaneTime; 24 Ready; 16 metadata records.
- Ten nonnegative LaneTime values match the ten lane times in the supplied 03:12:13 Cairo photograph. Conversion: 10,000 ticks/second, truncated to hundredths. Every pair is in field_screen_match.json.
- 642 nonnegative RunningTime updates corroborate about 10,000 ticks/second against receiver time intervals. This is not calibration or one-way latency measurement.
- Negative LaneTime: ten -3 and four -1. They remain uninterpreted; DNF/DNS/DQ mappings are unverified.
- The photograph shows one touch/50 m per lane, configured total two touches/100 m, Race stopped and DNF labels. No independently verified finish or DNF event is present in this recording.
- Repeated content within two seconds: 2,069. This is not proof of duplicated packets. No documented source sequence number is present.
- Last RunningTime is -1; final receiver summary is STALE after 3.305 seconds. The relay photograph shows its five-minute window stopped. Different time windows/counters do not establish packet loss.
- MeetName/City contain misplaced test CSV strings. Raw metadata is not imported as athletes, universities or a roster.

## Implementation boundary

- alge_gateway/swimtime_observed.py preserves the v2 structural parser/raw diagnostic.
- alge_gateway/swimtime_network.py adds source-pinned UDP, exact JSONL logging, observed TEST conversion, independent freshness, negative codes, regression hold and bounded channel state.
- POST /api/swimtime/start, /stop, /replay require Timing Operator or Single Operator and record Audit. Start/replay are disabled in VENUE.
- GET /api/swimtime, /api/state and /ws expose observer state. No raw metadata is adopted as competition data. React escapes displayed text.
- SwimTime TEST contains source IP/port, start/stop, recorded replay, nonextrapolated clock and channel table. Results and program routes remain separate.
- The listener stays open across feed interruption. No clock continuation or restart replay occurs. Clock blanks after 2 seconds without progressing nonnegative RunningTime, or immediately on Ready/negative suppression. The feed is stale after 3 seconds without a valid datagram.
- Unannounced clock regression is held and raw data retained. Complete out-of-order protection is not claimed without a documented sequence identifier.
- Unknown Layout suppresses times until LaneOriented or listener restart. Channel numbering is screen-matched for this test, not hardware verified.
- The old FINS raw monitor and integrated listener bind the same port; stop the old monitor. Relay stays on the separate SwimTime PC and auto-stops after 300 seconds.

## Installation and execution evidence

The Arabic guide covers updating the existing v0.7 project and fresh offline Windows Python 3.12 x64 installation. The updater backs up code and SQLite, preserves credentials/databases/assets, checks active server/listener and rolls back code after a copy failure. The Windows batch launcher needs an on-site acceptance run.

Python execution evidence is in testing/reports/v08/python_tests.xml; browser-to-UDP-to-API-to-WebSocket evidence is in browser.json; original/processed asset hash verification is in preflight.json. Historical v0.6/v0.7 reports remain historical. Local testing uses Linux/Python 3.12/headless Chromium/loopback sockets and does not certify Windows, Wi-Fi, OBS, LED cabinets or ALGE lane hardware.

## Approval and remaining work

| Area | Status |
|---|---|
| Supplied recording | All 2,754 messages structurally parsed |
| Ten lane-time values versus supplied source screen | Matched for this TEST capture |
| Received values inside FINS | Implemented; see v0.8 execution reports |
| Official hardware lane numbering | Awaiting physical test |
| Finish, deletion, correction, IRM semantics | Awaiting documented/recorded cases |
| Network Display to competition results | Not enabled |
| Network Display to TVG / six LED program feeds | Not enabled in this release |
| FISU visual matching / missing clock and ranked-row assets | Previous blockers remain |
| Windows v0.8 field acceptance | Pending |
| Production approval | No |

Official reference for Simulator and its required deactivation in competition: ALGE Swimming Timing System Manual 4.5.1.4.12, https://alge-timing.com/downloads/userGuides/Swimming-BE.pdf. Splash and Network Display are configured separately in 4.5.2. Network Display semantics above are derived from the supplied recording/screen, not asserted as a complete manufacturer protocol.
