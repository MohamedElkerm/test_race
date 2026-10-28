# FINS 2026 - operator manual

All competition-facing data and the control dashboard are in English. TEST data is visibly labelled. This release is for engineering rehearsal and formal acceptance testing.

## Start a local rehearsal

1. Extract the package to a local folder, for example `C:\FINS2026_LIVE_RESULTS`. Do not run from inside the ZIP or a cloud-sync folder.
2. Install Python 3.12 64-bit with the Python launcher if it is not already installed. Run `installers\INSTALL_TEST.cmd`.
3. Setup installs bundled Windows wheels without downloading dependencies and generates unique local test passwords. Read `runtime\TEST_OPERATOR_CREDENTIALS.txt` privately. No operator passwords are included in this delivery.
4. Run `RUN_TEST.cmd`. Open `http://127.0.0.1:8765` in Edge or Chrome. Sign in with the relevant role. TEST and VENUE use separate database files.
5. For multi-computer rehearsal, run `deployment\RUN_TEST_LAN.cmd` on the server and browse its actual private address from the other hosts. Venue IT must configure the restricted private network/firewall. The scripts do not change firewall rules automatically.

## Roles

| Account created for TEST | Role | Tasks |
|---|---|---|
| timing | Timing Operator | Bind event/heat, replay test race, run serial gateway |
| results | Results Operator | Import roster, compile unofficial results, submit review, publish approved results |
| chief | Chief Results Officer | Review and endorse the current result revision |
| jury | Technical/Jury Approver | Official approval, adjudication, documented correction and reopening |
| broadcast | Broadcast Operator | Preview, Take, Hold and Clear TV graphics |
| led | LED Operator | Independent routes, grouped playlists, safe margins, blackout and approved operational notices |
| admin | System Administrator | User provisioning via local CLI, roster import, audit and backup |

Administrator privileges do not confer Jury approval or timing-edit privileges. Sign out before changing accounts. Tokens expire after eight hours and are revoked on sign-out. Do not share real venue accounts.

## Rehearse a race and official approval

- As timing: choose an unused READY TEST heat. In Control, select Run TEST race. This sends synthetic manual-reconstructed ASCII frames; it is not a recorded ALGE race.
- As results: open Results, enter the operation reason and Compile unofficial. Finish observations remain raw and immutable. Then Submit for review.
- As chief: inspect names, lanes, times and source evidence. Enter a reason and select Chief endorsement.
- As jury: inspect the same revision. Enter the signed approval reference and reason, then Jury official approval. An earlier endorsement is rejected if the result revision changed.
- As results/chief: Publish official. The public-results API now includes that TEST heat, still labelled TEST. Unpublish is available independently of approval.
- Jury corrections require UNDER REVIEW, evidence source, document reference and reason. Reopening an OFFICIAL result removes publication and invalidates old signatures. A correction never overwrites the raw timing log.

Do not infer qualification, records or medals from a timing comparison. They are separate documented Jury decisions. Equal hundredth times retain equal proposed rank. Swim-off is a Jury workflow decision, not an automatic clock rule. IRM codes cannot be used until the technical team supplies approved mappings in `deployment/approved_rule_codes.json`.

## Broadcast operation

Use Preview before TAKE. The default program output is clear. All supplied assets keep their original proportions; TV outputs remain transparent at 1920 x 1080. Missing sprites are clearly marked and are not replaced. In TEST, engineering previews may be taken with a visible warning. In VENUE, TAKE rejects every template that lacks production approval. No template in this release has that approval.

- Load preview: choose SFS code and lane, enter reason, load the preview.
- TAKE: copy the preview scene to program. The scene then follows its bound heat, not a later unrelated operator selection.
- Hold: freezes non-timing graphics only. Timing templates cannot be held as a live clock. A changed/reopened result clears held result graphics.
- Clear graphics: remove program content immediately.
- OBS: add a Browser Source using `http://SERVER:8765/broadcast_tvg/`, width 1920, height 1080. Keep the source transparent and test the actual composition chain. HDMI, SDI, NDI and key/fill integration are not implemented or verified by this package.

If DATA LOST appears, check timing port, gateway process, selected heat and LAN. Do not present a frozen value as LIVE. Do not disable engineering/asset warnings to create an impression of approval.

## LED operation

In LED routing, select one or more of the six screens. Choose the content and bound heat, enter a reason and Route. Use the actual native resolution on each player. Thin slides paginate competitors every five seconds. The Stage screen shows four rows per page and advances every eight seconds; other scoreboards show up to eight rows per page. The safe margin is in native pixels. Optional playlists alternate selected content and identity every ten seconds and share a server timestamp.

Open the corresponding output URL on each player, then Fullscreen, or use `deployment\OPEN_LED_PLAYER.cmd SERVER_PRIVATE_IP SCREEN_KEY`. Player windows are separate from hardware output channels. BLACKOUT SELECTED and Release blackout affect only selected LED routes. A software online indicator is not proof of physical signal continuity.

Official, qualification and medal views wait for official approval. Medal views also require explicit medal decisions and support equal ranks rather than forcing three competitors. Operational notices require a LOC approval reference and source. Physical viewing-distance, glare, refresh, brightness and scan tests remain to be witnessed at the pool.

## Comparator and audit

Template library links to the Visual Template Comparator. It displays original JPG, actual canvas, adjustable overlay and absolute difference image. Export comparison metrics for review. Full-image errors include source camera matte and reference sample text; they must not be treated as a pixel-perfect pass score. Each template has its own missing-asset state and remains NOT APPROVED.

Audit & recovery lets authorised officers review identity, timestamp, source, reason and old/new values. Administrator backup uses the SQLite online backup API. Follow the separate disaster recovery procedure before restoring.
