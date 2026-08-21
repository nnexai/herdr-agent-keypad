---
phase: 03-truthful-codex-capacity-and-device-menu
plan: 09
subsystem: physical-acceptance-and-live-capacity
status: complete
tags: [codex, menu, physical-device, usb, evidence, polish]

requires:
  - phase: 03-08
    provides: exact-device deployment, capture matrix, and pending evidence package
provides:
  - Thirteen explicit exact-device physical acceptance passes plus fresh machine resynchronization
  - Live installed-account Codex capacity on panel 4 with required client metadata
  - Duration-aware 5H/WEEK normalization and bounded day/hour/minute reset countdowns
  - Polished all-theme Codex and menu layouts without value-crossing overlays or clipped footers
  - USB bridge recovery after transient serial errors and live bridge ownership during guided checks
affects: [phase-03-verification, phase-03.1]

actuals:
  tasks: 3
  commits: 2

key-files:
  created:
    - artifacts/phase3/screenshots/live-codex-current.png
  modified:
    - firmware/src/app/agent_projection.cpp
    - firmware/src/app/agent_projection.h
    - firmware/src/main.cpp
    - firmware/src/ui/theme_beacon.cpp
    - firmware/src/ui/theme_common.h
    - firmware/src/ui/theme_instrument.cpp
    - firmware/src/ui/theme_ledger.cpp
    - firmware/src/ui/theme_signal_edge.cpp
    - host/herdr_keypad/src/herdr_keypad/bridge.py
    - host/herdr_keypad/src/herdr_keypad/codex.py
    - host/herdr_keypad/tests/test_codex.py
    - host/herdr_keypad/tests/test_integration.py
    - test/test_agent_projection/test_main.cpp
    - tools/phase1_bringup/src/phase1_bringup/phase3_smoke.py
    - tools/phase1_bringup/test_phase3_smoke.py
    - artifacts/phase3/03-CODEX-TRACER.json
    - artifacts/phase3/03-DEVICE-EVIDENCE.json

requirements-completed: [CODEX-01, CODEX-02, CODEX-03, CODEX-04, SYNC-03, SAFE-01, MENU-01, MENU-02, MENU-03, MENU-04]
completed: 2026-08-21
---

# Phase 03 Plan 09: Physical Acceptance and Live Capacity Summary

**The exact keypad passed every physical Phase 3 interaction check, panel 4 now shows the installed Codex account's live capacity, and final evidence closes against a freshly acknowledged permanent-bridge publication.**

## Accomplishments

- Recorded explicit physical passes for all four themes at 10% brightness, truthful unavailable/source labels, direct agent keys from every menu context, the complete 10–100% brightness ladder, 0% rejection, close/timeout reversion, LED preview semantics, confirmed persistence, and reboot restoration.
- Kept a temporary live bridge active throughout guided physical prompts. Agent focus requests remained available while root, BRIGHTNESS, HEALTH, and ABOUT were open.
- Fixed same-revision Codex refreshes so panel 4 recomposes the open menu rather than overpainting it with the Codex tile.
- Removed cross-value hatching and oversized alert marks, separated Codex labels from tracks, replaced the beacon's overlapping rings, lifted HEALTH/ABOUT content above the footer, and allowed the firmware version to use its actual available width.
- Fixed the installed Codex handshake: `initialize.params.clientInfo` is now supplied as required by Codex 0.147.0. The live tracer observes `initialize`, `initialized`, `account/read`, and `account/rateLimits/read`, then records a current redacted result.
- Used `windowDurationMins` to map the installed account's weekly-only `primary` payload into the WEEK display row instead of falsely labeling it 5H. Reset countdowns now use bounded day/hour/minute units, for example `RESET WEEK 6D0H49M`, rather than thousands of raw minutes.
- Changed transient USB failures from graceful bridge termination into fenced disconnect/reconnect behavior. The permanent guard now survives and republishes after short serial disruptions.
- Allowed final resynchronization after the required reboot to carry a new boot identity while still requiring the exact binary SHA-256, paired device, firmware identity, protocol, fresh publication timestamp, and acknowledged snapshot.

## Task Commits

1. **Task 1: Add guarded physical evidence flow** — `996fbbe` (`fix(03-09): add guarded physical evidence flow`)
2. **Task 2: Fix physical UI, bridge, and live Codex findings** — `6d0cbc4` (`fix(03-09): close physical and live Codex findings`)

## Deployment and Evidence Linkage

- Deployment ID: `9d1b8a7090930fafb42dd3f68cd3ea34267ad032e576118a310ba71ab2978f4b`
- Deployed firmware SHA-256: `d188d8f4f3177c12a9116df80b728017dcb2ad97df66928e292422e70fc1f26e`
- Exact paired device: `0000fccb0deabf8c`; USB serial `8C:BF:EA:0D:CB:FC`
- Installed Codex tracer SHA-256: `fa365c0ea20561f075cf57a6a2575166e4a7451b002279884dfb6e0e774e1ce8`
- Physical rows: **13/13 passed**; fresh bridge resynchronization: **passed**
- Device evidence status: **pass**; checksum sidecar reopens successfully.

## Verification

- Host bridge/Codex/protocol suite: **65/65 passed**.
- Phase 3 guided/finalization regressions: **4/4 passed**.
- Native projection/menu/LED/UI suite: **69/69 passed**.
- Current selected-usb firmware built and uploaded successfully through the project venv.
- Live installed Codex tracer: **passed**, current source, real account rate-limit response, redaction pass, bounded child exit.
- Fresh live panel framebuffer: WEEK usage visible, 5H absent as `N/A`, current source and age visible, reset rendered in day/hour/minute units without overlap or clipping.
- Strict `phase3_smoke validate --require-current-deployment --require-fresh-bridge-publication`: **passed**.
- `sha256sum -c artifacts/phase3/03-DEVICE-EVIDENCE.json.sha256`: **passed**.

## Deviations from Plan

- Physical inspection exposed layout defects that logical completeness tests did not reject. The production theme code was corrected and recaptured before acceptance closed.
- The initial guided runner held direct serial without a bridge, so direct agent keys could not be exercised. The runner now starts a guarded temporary bridge before prompting and fails closed if it exits.
- The installed Codex process exited cleanly after rejecting an incomplete `initialize` request. Official 0.147.0 protocol evidence identified required `clientInfo`; fixing that request exposed the real weekly-only window shape and led to duration-aware normalization.
- Reopening the serial device can produce a new boot identity. Finalization now treats the post-reboot boot ID as evidence rather than requiring it to equal the pre-reboot capture boot ID; binary, device, firmware, protocol, timing, and acknowledgment remain mandatory.

## Next Phase Readiness

- Phase 3 implementation and exact-device acceptance are complete.
- Phase 03.1 can build animation and interaction polish on a stable live Codex/menu baseline.
- Focus reliability was explicitly observed as a separate concern; it was not reproduced as a failure in the Phase 3 physical rows and remains outside this plan's acceptance claim.
- Standard-depth review closed all blockers and retained one non-blocking Signal Edge discriminator-width item plus one dead-helper cleanup item for the next firmware/evidence cycle in Phase 03.1.

## Self-Check: PASSED

- Every physical row is explicit and bound to the current firmware/device evidence package.
- The installed-account tracer contains live normalized values, not fixture values.
- The permanent bridge owns the guarded serial path and has published a fresh acknowledged snapshot.
