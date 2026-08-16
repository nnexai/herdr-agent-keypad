---
phase: 01-physical-keypad-and-proven-transport
plan: 01
subsystem: firmware-and-host-transport
tags: [esp32-s3, usb-cdc, platformio, pyserial, physical-bringup]

# Dependency graph
requires: []
provides:
  - Bounded v1 USB CDC hello/probe/event tracer on the delivered keypad.
  - Physical PANEL-1 to key-0 correspondence evidence.
  - Plan-owned host self-check and atomic, hash-verified evidence output.
affects: [01-02, 01-03, 01-04, 01-05, 01-06, 01-07, 01-08]

# Actuals
actuals:
  tokens: 900
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: [pioarduino 55.03.311, Arduino-ESP32 3.3.11, pyserial 3.5]
  patterns: [closed NDJSON envelope, descriptor-pinned USB selection, atomic evidence with reopen/hash verification]

key-files:
  created: [artifacts/phase1/20260816T083124Z-c8553c/manifest.json, artifacts/phase1/20260816T083124Z-c8553c/result.json, artifacts/phase1/20260816T083124Z-c8553c/SHA256SUMS]
  modified: [tools/phase1_bringup/src/phase1_bringup/__main__.py]

key-decisions:
  - "USB CDC remains the Phase 1 transport candidate: the delivered ESP32-S3 accepted a bounded correlated exchange over its stable USB descriptor path."
  - "The host guide requires an explicit stable /dev/serial/by-id path because automatic discovery sees unrelated ttyS devices."
  - "Empty serial reads are ignored inside bounded receive loops; timeout remains the failure condition rather than treating a transient CDC read as malformed protocol data."

patterns-established:
  - "Protocol reads distinguish a timeout/no-data read from a malformed non-empty frame."
  - "Physical PASS requires the visible step identifier and explicit Y/N/R confirmation; firmware ACKs alone never qualify the observation."

requirements-completed: [HARD-01, HARD-03]

coverage:
  - id: D1
    description: "The delivered keypad completed a correlated v1 USB hello/probe exchange and emitted a matching physical key event."
    requirement: HARD-03
    verification:
      - kind: e2e
        ref: "artifacts/phase1/20260816T083124Z-c8553c/result.json"
        status: pass
    human_judgment: true
    rationale: "The host/device exchange is automated, but the connected hardware and transport were required for the evidence run."
  - id: D2
    description: "PANEL-1 displayed the cyan 1-arrow stimulus and its matching physical key was confirmed as key index 0."
    requirement: HARD-01
    verification:
      - kind: manual_procedural
        ref: "phase1_bringup start; explicit confirmation Y PANEL-1; result.json machine_facts.event.key=0"
        status: pass
    human_judgment: true
    rationale: "Only direct observation can establish that the visible panel and pressed key correspond on the delivered unit."
  - id: D3
    description: "The production evidence writer preserved manifest/result files and reopened them after SHA-256 finalization."
    verification:
      - kind: integration
        ref: "phase1_bringup self-check --environment --schema protocol/schema/v1.json --evidence-roundtrip artifacts/phase1/tracer-self-check"
        status: pass
    human_judgment: false

# Metrics
duration: 14min
completed: 2026-08-16
status: complete
---

# Phase 1 Plan 01 Summary

**The delivered T-Keyboard S3 Pro completed a physical PANEL-1/key-0 USB CDC tracer run with bounded protocol and hash-verified evidence.**

## Performance

- **Duration:** 14 min for the resumed execution segment
- **Started:** 2026-08-16T08:17:45Z
- **Completed:** 2026-08-16
- **Tasks:** 2
- **Files modified:** 1 source file plus this summary and generated evidence

## Accomplishments

- Self-check passed for the closed v1 schema, 4096-byte including-LF bound, pyserial 3.5, and production evidence round trip.
- PlatformIO built and flashed the tracer using the pinned pioarduino/Arduino-ESP32 stack and the stable Espressif USB JTAG serial descriptor.
- The connected device accepted hello/probe, displayed the PANEL-1 cyan `1 ^` stimulus, reported physical key index 0, and received explicit `Y PANEL-1` confirmation.
- The successful run was preserved at `artifacts/phase1/20260816T083124Z-c8553c/` with manifest, result, and SHA256SUMS files; the tracer reported reopen/hash verification success.

## Task Commits

1. **Task 1: Prove one panel-key USB round trip end to end** - `3912fc6`, `c5d8a32` (tracer implementation and PlatformIO source-root correction)
2. **Task 2: Lock the reproducible host environment and evidence verifier** - `5141ff1` (tolerate transient empty CDC reads during bounded receive)

## Files Created/Modified

- `platformio.ini` - pinned Phase 1 firmware build configuration from prior task commits.
- `protocol/schema/v1.json` - closed bounded v1 protocol contract from prior task commits.
- `firmware/src/main.cpp` - physical stimulus, key event, and USB tracer firmware from prior task commits.
- `tools/phase1_bringup/src/phase1_bringup/__main__.py` - plan-owned host guide; now ignores empty serial reads while retaining malformed-frame rejection and bounded timeouts.
- `artifacts/phase1/20260816T083124Z-c8553c/` - successful real-device evidence.

## Decisions Made

- USB CDC is suitable as the Phase 1 candidate on the delivered unit: the ESP32-S3 USB JTAG serial descriptor remained stable and the bounded exchange completed.
- Automatic port discovery is not sufficient because pyserial also reports unrelated `/dev/ttyS*` entries; the guided run used the stable `/dev/serial/by-id/...` path.
- The exact plan gate requested Python 3.11, but the user directed execution with the available Python 3.14.7 runtime. Python 3.14.7 and pyserial 3.5 were recorded in the real manifest; this is an explicit environment deviation, not a claim of Python 3.11 equivalence.

## Deviations from Plan

### User-directed environment deviation

- **Found during:** Task 2 verification
- **Issue:** `python3.11` is unavailable; the project-owned environment resolves Python 3.14.7.
- **Decision:** Continue with `python3`/the existing project environment at the user's direction.
- **Verification:** Self-check passed under Python 3.14.7 with pyserial 3.5; the runtime and executable path are recorded in the successful manifest.
- **Impact:** The tracer is proven on the current host runtime, but the exact Python 3.11 reproducibility claim remains unverified.

### Correctness fix

- **Found during:** Task 1 physical run
- **Issue:** A transient empty CDC read was passed to strict frame decoding and aborted the handshake.
- **Fix:** Receive loops now ignore empty timeout reads and continue until their existing bounded deadlines.
- **Verification:** A subsequent real-device run completed hello, probe, event, explicit physical confirmation, and evidence verification.
- **Committed in:** `5141ff1`

## Issues Encountered

- Automatic tracer discovery rejected the port set because unrelated ttyS devices are visible; explicit stable descriptor selection succeeded.
- The first post-reset handshake timed out before the device was ready; after a device restart, the explicit stable-port run completed successfully.
- No credentials or host paths were written into device payloads; the evidence manifest redacts the selected port.

## User Setup Required

None - no external service configuration required. The host user must retain access to the stable USB serial device, currently provided by `dialout` membership.

## Next Phase Readiness

- Plan 01-01 is complete with real USB CDC and one physical panel/key mapping evidence.
- Phase 1 Wave 2 can proceed to expand the firmware into the complete four-panel stimulus and renderer surface.
- Carry forward the Python 3.11 reproducibility gap and the requirement to use descriptor-pinned device selection in later qualification runs.

---
*Phase: 01-physical-keypad-and-proven-transport*
*Completed: 2026-08-16*
