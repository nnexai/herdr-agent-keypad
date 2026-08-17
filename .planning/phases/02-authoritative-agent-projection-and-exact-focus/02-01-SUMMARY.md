---
phase: 02-authoritative-agent-projection-and-exact-focus
plan: 01
subsystem: authoritative-projection-and-focus-protocol
tags: [herdr, protocol-v2, focus, firmware, usb, identity]
requires:
  - phase: 02-authoritative-agent-projection-and-exact-focus
    plan: 00
    provides: "Baseline-compatible Herdr contract, exact opaque identity evidence, and Phase 1 handoff"
provides:
  - "Closed bounded v2 snapshot, acknowledgement, focus-intent, and focus-result wire contract"
  - "Host staged/committed three-slot projection and exact identity-bound tracer"
  - "Firmware v2 admission and fixed-capacity AgentProjection boundary"
affects: [02-02, 02-03, 02-04]
tech-stack:
  added: ["Python v2 codec helpers over the Phase 1 codec/session seam", "fixed-capacity C++ AgentProjection"]
  patterns: ["staged generation commit", "opaque identity plus host epoch/revision correlation", "focus-only typed action"]
key-files:
  created:
    - host/herdr_keypad/src/herdr_keypad/bridge.py
    - host/herdr_keypad/src/herdr_keypad/__init__.py
    - host/herdr_keypad/tests/test_protocol.py
    - firmware/src/app/agent_projection.h
    - firmware/src/app/agent_projection.cpp
    - protocol/schema/v2.json
    - protocol/fixtures/v2-golden.json
  modified:
    - firmware/src/protocol/protocol.cpp
    - firmware/src/main.cpp
    - tools/phase1_bringup/src/phase1_bringup/protocol.py
    - test/protocol/test_main.cpp
    - platformio.ini
decisions:
  - "V2 retains the Phase 1 envelope and FrameCodec/ProtocolSession admission seam; v1 schema and fixture remain byte-for-byte unchanged."
  - "Exactly three fixed slots are product-actionable; key/panel 4 and the encoder remain unbound."
  - "Herdr opaque pane/terminal/optional-session/source revision are carried separately from bridge-owned action ID, host epoch, and snapshot revision."
  - "The installed Herdr source revision remains 78b243279b4da55150b58dc2cc3cffcdc2fd6a04 from Wave 0."
actuals:
  tokens: 34333
  tasks: 2
  commits: 3
metrics:
  duration: 3h
  completed: 2026-08-17
status: complete
---

# Phase 2 Plan 1: Exact identity-bound v2 projection and focus Summary

**A bounded v2 product path carries one complete authoritative tile through the existing session seam, stages it before commit, emits a typed exact focus intent, and accepts visible success only after matching identity and generation correlation.**

## Accomplishments

- Added v2 host validation and frame helpers without introducing a second transport. The host tracer stages and commits a complete three-slot snapshot, captures an immutable binding on canonical key 0..2 presses, exposes pending feedback, and rejects pane, terminal, action, epoch, source-revision, and snapshot-revision mismatches.
- Extended firmware `FrameCodec` to admit v2 product types while preserving v1 behavior and typed rejection. `main.cpp` routes admitted snapshots/results into the fixed-capacity `AgentProjection`; physical key handling can emit only the typed `focus_intent` for committed slots.
- Added closed `v2.json` and shared vectors for snapshots, focus intent/result, version/type rejection, and oversized-frame rejection. Native tests execute production `protocol.cpp` against both v1 and v2 fixtures.
- Preserved the exact v1 schema and fixture hashes: `f538512c517dab6588a64ea24a06c8464e46d605fd48fa669e68358a9bfbdcd8` and `9633d4a2fa47267bb39cece549c92ac2fe6949ceef1570bb2cd05b1920967c52`.

## Verification Evidence

- `PYTHONPATH=host/herdr_keypad/src tools/phase1_bringup/.venv/bin/python -m herdr_keypad.bridge --self-check-tracer` — passed; stages/commits, captures pending intent, accepts matching result, and rejects six identity/generation mismatches.
- `PYTHONPATH=host/herdr_keypad/src tools/phase1_bringup/.venv/bin/python -m unittest host.herdr_keypad.tests.test_protocol` — passed, 5 tests.
- `tools/phase1_bringup/.venv/bin/pio test -e native -f protocol` — passed, 5 native tests including v1 and v2 vectors.
- `tools/phase1_bringup/.venv/bin/pio run -e selected-usb` — passed; firmware image compiled with no Wi-Fi source in the selected source filter. The build emitted only the pre-existing Arduino log-level redefinition warnings.
- Draft 2020-12 schema validation — passed for `protocol/schema/v2.json` and four v2 vectors.
- Wave 0 handoff and Herdr verify-only checks passed before the required selected-usb build.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved v1 version rejection while admitting v2**
- **Found during:** Task 2 native parity
- **Issue:** A v1 fixture using a v2 envelope version with a v1 type initially returned `unknown_type` instead of the established `invalid_version` reason.
- **Fix:** Version/type dispatch now treats v2 with a known v1 type as an invalid version while routing only the closed v2 type set to the v2 parser.
- **Files modified:** `firmware/src/protocol/protocol.cpp`
- **Verification:** Native protocol suite passed all 5 tests.

### Verification Blocker

The Wave 0 handoff binary at `.pio/build/selected-usb/firmware.bin` was overwritten by the required selected-usb build. The build itself passed, but the original archived binary hash (`280e8250b733abd0f534fab89e9578d2cd1a7b51b862e7451a8f3007ca82dbcb`) is not reproducible from the current checkout/build metadata, so a post-build `phase2_handoff_gate.py --verify-only` reports `EvidenceError: final build binary hash mismatch`. The precondition gate passed before this plan's build. No Phase 1 source or JSON artifact was intentionally edited by this plan; the original binary is required to restore the final immutable handoff receipt.

## Known Stubs

None. No placeholder, TODO, mock data source, or unrun plan verification was left in the changed product path.

## Self-Check: PASSED

- Created v2 host, firmware, schema, fixture, and test files exist.
- Host tracer, host parity tests, native protocol tests, schema validation, and selected-usb compilation produced the evidence recorded above.
- v1 schema and fixture hashes were checked after implementation and remain unchanged.
