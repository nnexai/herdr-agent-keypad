---
phase: 01-physical-keypad-and-proven-transport
plan: 09
subsystem: firmware-protocol-transport
tags: [protocol, session, queue, serial, usb, physical-map, readiness]

# Dependency graph
requires:
  - phase: 01-physical-keypad-and-proven-transport
    provides: selected-usb composition, frozen v1 codec/session contract, verified physical map evidence
provides:
  - Flashed runtime admission and dispatch through the consolidated FrameCodec/ProtocolSession path
  - Bounded protocol queue completion and truthful frame-unit high-water metrics
  - Full-write serial boundaries with stale-link closure on short writes and read failures
  - Persistent board readiness and fail-closed PhysicalMap/BoardAdapter lookups
affects: [phase-1 gap plans 01-10 through 01-13, phase-2 host bridge]

# Actuals (#2632)
actuals:
  tokens: 33000
  tasks: 3
  commits: 7

# Tech tracking
tech-stack:
  added: []
  patterns: [single production codec/session admission, explicit pending-frame completion, pointer-based fail-closed board lookups]

key-files:
  created:
    - .planning/phases/01-physical-keypad-and-proven-transport/01-09-SUMMARY.md
  modified:
    - firmware/src/main.cpp
    - firmware/src/protocol/protocol.h
    - firmware/src/protocol/protocol.cpp
    - firmware/src/metrics/proof_metrics.h
    - firmware/src/transport/usb_cdc.cpp
    - firmware/src/board/board_adapter.h
    - firmware/src/board/board_adapter.cpp
    - firmware/src/board/physical_map.h
    - firmware/src/ui/bringup_renderer.h
    - tools/phase1_bringup/src/phase1_bringup/protocol.py
    - tools/phase1_bringup/src/phase1_bringup/serial_link.py
    - test/protocol/test_main.cpp

key-decisions:
  - "Every complete firmware input line is counted and admitted through ProtocolSession before any typed hardware dispatch or session side effect."
  - "Protocol pending_count is completed after each dispatch outcome and queue_high_water reports bounded protocol frames, not transport bytes."
  - "BoardAdapter readiness and PhysicalMap lookup failures are persistent and fail closed; no raw-index fallback is permitted."

patterns-established:
  - "The production runtime uses the same bounded FrameCodec/ProtocolSession implementation exercised by native tests."
  - "SerialLink and UsbCdcLink use bounded write-all behavior and close stale links on short or exceptional I/O."

requirements-completed: [HARD-01, HARD-03]

coverage:
  - id: D1
    description: "Selected-usb firmware admits complete frames through the production codec/session and dispatches only accepted typed commands."
    requirement: HARD-03
    verification:
      - kind: integration
        ref: "test/protocol/test_main.cpp: test_queue_bound_completion_and_bootstrap"
        status: pass
      - kind: build
        ref: "tools/phase1_bringup/.venv/bin/pio run -e selected-usb"
        status: pass
    human_judgment: false
  - id: D2
    description: "Protocol queue capacity is recoverable through explicit completion and metrics remain frame-bounded."
    requirement: HARD-03
    verification:
      - kind: unit
        ref: "test/protocol/test_main.cpp: test_queue_bound_completion_and_bootstrap"
        status: pass
      - kind: other
        ref: "tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --serial-reconnect"
        status: pass
    human_judgment: false
  - id: D3
    description: "Board readiness and the verified PhysicalMap govern hardware access and reject unavailable mappings without fallback."
    requirement: HARD-01
    verification:
      - kind: build
        ref: "tools/phase1_bringup/.venv/bin/pio run -e selected-usb"
        status: pass
    human_judgment: true
    rationale: "Physical readiness and delivered-unit mapping still require the actual connected device; this assignment intentionally performs no manual hardware validation."

# Metrics
duration: execution window
completed: 2026-08-17
status: complete
---

# Phase 1 Plan 9: Production Protocol, Bounded I/O, and Physical Readiness Summary

**The selected-usb runtime now uses one production codec/session admission path with recoverable frame queues, bounded serial delivery, and fail-closed readiness/map access.**

## Performance

- **Duration:** execution window
- **Started:** 2026-08-17T00:00:00Z (prior partial implementation was resumed from the current tree)
- **Completed:** 2026-08-17
- **Tasks:** 3
- **Files modified:** 12 source/test files, plus this summary

## Accomplishments

- Removed the runtime's independent frame admission path: complete lines are bounded, decoded, session-checked, sequence/digest-checked, queued, typed-dispatched, and completed through `ProtocolSession`.
- Added integrated native proof for hello bootstrap, accepted probe dispatch admission, wide-version/trailing-byte rejection, queue-full behavior, completion, and restored capacity.
- Added typed host rejection for boolean protocol versions and non-string discriminants; retained bounded host protocol/session and serial reconnect checks.
- Implemented bounded write-all behavior on USB and host serial boundaries, with durable sequence state advancing only after complete writes and stale descriptors closed on short/error paths.
- Persisted board readiness, consumed the verified `PhysicalMap` through `BoardAdapter`, validated map indices, and made renderer/display access fail closed instead of falling back to raw index zero.

## Task Commits

1. **Task 3: Fail closed on board readiness and consume one physical map** - `46e0094` (feat)
2. **Task 1: Route one flashed hello/probe path through the frozen production session** - `00afeb4` (feat)
3. **Task 2: Complete bounded queue and serial I/O lifecycle semantics** - `f62671c` (feat)
Follow-up fix: `168a43b` ensures complete-line metrics are recorded only after ProtocolSession admission.

Metadata commits: `9a3c326`, `fd66b63`; `168a43b` is the admission-ordering follow-up fix.

## Files Created/Modified

- `firmware/src/main.cpp` - production runtime line admission, typed dispatch, completion, readiness gate, and physical stimulus routing.
- `firmware/src/protocol/protocol.{h,cpp}` - bounded frame codec, bootstrap/session transitions, sequence/digest checks, and queue lifecycle.
- `firmware/src/metrics/proof_metrics.h` - frame-unit queue high-water measurement.
- `firmware/src/transport/usb_cdc.cpp` - complete bounded writes and close-on-failure behavior.
- `firmware/src/board/board_adapter.{h,cpp}` - persistent readiness and fail-closed mapped access.
- `firmware/src/board/physical_map.h` - verified map initialization and index validation.
- `firmware/src/ui/bringup_renderer.h` - nullable adapter display access handling.
- `tools/phase1_bringup/src/phase1_bringup/protocol.py` - typed host discriminant validation and bootstrap checks.
- `tools/phase1_bringup/src/phase1_bringup/serial_link.py` - bounded write-all/read error closure and reconnect proof.
- `test/protocol/test_main.cpp` - integrated production protocol/session and queue tests.

## Decisions Made

- Kept USB as the only selected adapter and did not create or revive Wi-Fi source.
- Kept boot/session freshness generation and long qualification remediation out of this gap plan; those remain in the explicitly sequenced later gap plans.
- Kept physical PASS as human evidence: the firmware only exposes readiness and map gates and never turns an acknowledgement into physical truth.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Rejected wide protocol versions before narrowing**
- **Found during:** Task 1
- **Issue:** C++ decoded `v:257` into `uint8_t` before validation, allowing it to become v1.
- **Fix:** Validate the parsed uint32 version before storing it in the frame.
- **Files modified:** `firmware/src/protocol/protocol.cpp`, `test/protocol/test_main.cpp`
- **Verification:** Native `test_rejects_wide_version_and_trailing_bytes` passed.
- **Committed in:** `00afeb4`

**2. [Rule 1 - Bug] Converted malformed host discriminants to stable typed rejections**
- **Found during:** Task 1
- **Issue:** Boolean versions and list-valued type/request fields could pass equality or raise `TypeError` before typed rejection.
- **Fix:** Type-check discriminants before comparisons/set membership and exercise the cases in the host bootstrap self-check.
- **Files modified:** `tools/phase1_bringup/src/phase1_bringup/protocol.py`
- **Verification:** Host self-check passed and direct cases returned `invalid_version`, `unknown_type`, and `invalid_shape`.
- **Committed in:** `00afeb4`

**3. [Rule 2 - Missing critical functionality] Removed raw-index fallback from board access**
- **Found during:** Task 3
- **Issue:** Invalid map lookups fell back to display/key index zero, violating fail-closed physical dispatch.
- **Fix:** Use nullable adapter lookups, validate all mapped indices, and stop renderer access on an unavailable mapping.
- **Files modified:** `firmware/src/board/board_adapter.{h,cpp}`, `firmware/src/board/physical_map.h`, `firmware/src/ui/bringup_renderer.h`
- **Verification:** Selected-usb build passed; all runtime hardware entry points remain readiness-gated.
- **Committed in:** `46e0094`

**4. [Rule 1 - Bug] Replaced misleading queue metric semantics**
- **Found during:** Task 2
- **Issue:** The queue high-water helper accepted a byte-oriented value and could report beyond the configured frame bound.
- **Fix:** Name the input as pending frames, clamp it to the 16-frame protocol capacity, and keep transport bytes out of the field.
- **Files modified:** `firmware/src/metrics/proof_metrics.h`
- **Verification:** Native queue-capacity test and selected-usb build passed.
- **Committed in:** `f62671c`

**5. [Rule 1 - Bug] Moved complete-line accounting behind admission**
- **Found during:** Final source review
- **Issue:** `recordReceived()` ran before the production session returned, leaving a metrics side effect ahead of the admission result.
- **Fix:** Record the line only after `ProtocolSession::accept()` returns and before typed dispatch.
- **Files modified:** `firmware/src/main.cpp`
- **Verification:** Selected-usb build passed.
- **Committed in:** `168a43b`

---

**Total deviations:** 5 auto-fixed (3 Rule 1, 1 Rule 2, 1 Rule 1)
**Impact on plan:** All fixes directly closed identified protocol, queue, or fail-closed safety gaps; no new transport or hardware architecture was introduced.

## Issues Encountered

- The cancelled prior executor had already left a broad partial implementation in the working tree. It was preserved and completed rather than reset or duplicated.
- Native and selected-usb checks required the existing PlatformIO environment; no project-wide tests, formatters, linters, hardware, Wi-Fi, or long qualification run were performed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The selected-usb firmware and host now share the production bounded protocol/session path and can be used by the remaining Phase 1 gap plans. Physical readiness/map behavior is fail-closed in source and build checks, but connected-device observation remains intentionally deferred to the later non-fabricable physical-proof plan.

## Verification

- `tools/phase1_bringup/.venv/bin/pio test -e native -f protocol` — PASS (4 tests).
- `tools/phase1_bringup/.venv/bin/pio run -e selected-usb` — PASS.
- `tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --protocol-golden protocol/fixtures/v1-golden.json --schema protocol/schema/v1.json --serial-reconnect` — PASS.

## Self-Check: PASSED

- All three task commits and the follow-up fix exist: `46e0094`, `00afeb4`, `f62671c`, `168a43b`.
- Metadata commits exist: `9a3c326`, `fd66b63`.
- Focused native, selected-usb, host golden, and serial reconnect checks passed.
- No physical/manual validation or long qualification run was performed, per assignment boundary.
