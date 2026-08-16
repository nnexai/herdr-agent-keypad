---
phase: 01-physical-keypad-and-proven-transport
plan: 05
subsystem: protocol-testing
tags: [protocol, firmware, host, platformio, unity, golden-fixture]

# Dependency graph
requires:
  - phase: 01-physical-keypad-and-proven-transport
    provides: 01-04 exact paired identity, fresh-session recovery, and bounded host serial path
provides:
  - Closed v1 envelope/schema with a 4096-byte including-LF bound, deterministic FNV-1a-64 payload digest, and typed rejection vocabulary
  - Consolidated production FrameCodec and ProtocolSession with session reset, sequence/deduplication, queue bounds, and discard semantics
  - Matching host codec/session implementation and 21-vector cross-language golden fixture
  - Concrete PlatformIO native Unity harness linked to production firmware protocol.cpp
affects: [01-06 USB qualification, 01-07 Wi-Fi fallback, 01-08 archive]

# Actuals (#2632)
actuals:
  tokens: 15623
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: [PlatformIO native, Unity 2.6.0]
  patterns: [closed canonical envelope, FNV-1a-64 payload digest, typed pre-dispatch rejection, bounded fixed-buffer session state, repository golden fixture]

key-files:
  created:
    - protocol/fixtures/v1-golden.json
    - firmware/src/protocol/protocol.h
    - firmware/src/protocol/protocol.cpp
    - test/protocol/test_main.cpp
    - test/test_protocol/test_main.cpp
  modified:
    - protocol/schema/v1.json
    - tools/phase1_bringup/src/phase1_bringup/protocol.py
    - tools/phase1_bringup/src/phase1_bringup/__main__.py
    - platformio.ini

key-decisions:
  - "Freeze the smallest defensible v1 line limit at 4096 bytes including LF; oversized bytes are rejected before JSON parsing."
  - "Use a closed envelope and payload contract with canonical sorted-key payload JSON and FNV-1a-64 digest so firmware and host can compute the same bounded result without a heavyweight native crypto dependency."
  - "Keep FrameCodec and ProtocolSession consolidated in protocol.{h,cpp}; they share fixed buffers, rejection codes, sequence state, and reset/discard invariants."
  - "A fresh ProtocolSession reset clears pending work and sequence/deduplication state; boot/session mismatch, duplicate, and out-of-order frames never dispatch."

patterns-established:
  - "Every golden vector records accepted/rejected outcome, typed reason, dispatch flag, and optional prior/session state."
  - "The native harness opens the absolute project-derived fixture path and fails on unreadable/empty/count-drifted input."

requirements-completed: [HARD-01, HARD-03]

coverage:
  - id: D1
    description: "Closed v1 schema and host codec/session enforce bounded valid and invalid frame semantics."
    requirement: HARD-03
    verification:
      - kind: other
        ref: "tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --protocol-golden protocol/fixtures/v1-golden.json --schema protocol/schema/v1.json"
        status: pass
    human_judgment: false
  - id: D2
    description: "Production firmware protocol.cpp is exercised by the fixture-loading native Unity runner."
    requirement: HARD-03
    verification:
      - kind: unit
        ref: "tools/phase1_bringup/.venv/bin/pio test -e native"
        status: pass
    human_judgment: false

# Metrics
duration: execution window
completed: 2026-08-16
status: complete
---

# Phase 1 Plan 5: Frozen Protocol and Native Golden Harness Summary

**A closed, digest-bound v1 protocol now has matching host/firmware session semantics and a runnable native Unity fixture harness covering 21 valid, malformed, incompatible, corrupt, oversized, duplicate, session, and ordering vectors.**

## Performance

- **Duration:** execution window; wall-clock duration was not separately measured
- **Started:** 2026-08-16T14:12:50Z (planning state timestamp; execution start was not separately persisted)
- **Completed:** 2026-08-16
- **Tasks:** 2 plan tasks completed
- **Files modified:** 9 source/config/test files

## Accomplishments

- Froze `protocol/schema/v1.json` and `protocol/fixtures/v1-golden.json` around the closed v1 envelope, 4096-byte including-LF bound, canonical payload digest, exact payload shapes, and stable typed rejection codes.
- Implemented consolidated fixed-buffer firmware `FrameCodec`/`ProtocolSession` production code. It rejects malformed, unknown, incompatible, oversized, digest-corrupt, mismatched-session, duplicate, out-of-order, and queue-overflow traffic before dispatch; reset clears uncertain pending work.
- Updated the host codec/session and added `self-check --protocol-golden`, proving host semantics over all 21 frozen vectors.
- Added the exact project-derived fixture macro and native Unity runner. The concrete suite runs all vectors against firmware `protocol.cpp`, asserts no-dispatch failures, checks encode/decode parity, reset/discard, and queue behavior.

## Task Commits

Each task was committed atomically:

1. **Task 1: Freeze matching production host and firmware protocol semantics** - `8c5d7d8` (`feat`)
2. **Task 2: Author and run the concrete PlatformIO native fixture harness** - `cb17635` (`test`)

**Plan metadata:** pending state/roadmap metadata commit after this summary.

## Files Created/Modified

- `protocol/schema/v1.json` - closed v1 envelope, digest contract, payload contracts, and rejection vocabulary.
- `protocol/fixtures/v1-golden.json` - 21 canonical valid/invalid/session vectors shared by host and native tests.
- `firmware/src/protocol/protocol.h` - fixed-size codec/session API and typed `RejectReason`.
- `firmware/src/protocol/protocol.cpp` - bounded native/firmware parser, digest, encoder, and session state machine.
- `tools/phase1_bringup/src/phase1_bringup/protocol.py` - matching host validator, digest, typed classification, bounded session, and golden runner.
- `tools/phase1_bringup/src/phase1_bringup/__main__.py` - `--protocol-golden` self-check surface.
- `platformio.ini` - native Unity environment, production source filter, absolute fixture macro, and test source build.
- `test/protocol/test_main.cpp` - authored fixture-loading Unity runner.
- `test/test_protocol/test_main.cpp` - PlatformIO 6 suite-name compatibility include preserving the authored runner path.

## Decisions Made

- The v1 line bound is frozen at 4096 bytes including LF and is checked before parsing/allocation.
- Digest input is canonical sorted-key payload JSON and digest encoding is lowercase FNV-1a-64 hexadecimal, which is implementable identically in Python and fixed-buffer C++.
- Protocol and session state remain one consolidated firmware module rather than duplicating fixed-buffer and rejection invariants across files.
- Session changes explicitly reset sequence/deduplication and pending-work state; uncertain work is discarded, never replayed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Corrected native source/test build composition**
- **Found during:** Task 2 native harness execution
- **Issue:** The inherited source filter pointed outside the configured `firmware/src` source root, and PlatformIO test mode did not link project sources.
- **Fix:** Set `build_src_filter = +<protocol/**>` relative to the configured source root and enable `test_build_src = yes`.
- **Files modified:** `platformio.ini`
- **Verification:** `pio test -e native` compiled `firmware/src/protocol/protocol.cpp` and passed all three Unity tests.
- **Committed in:** `cb17635`

**2. [Rule 3 - Blocking] Added PlatformIO 6 test-suite compatibility path**
- **Found during:** Task 2 exact `pio test -e native -f protocol` discovery
- **Issue:** PlatformIO 6.1.19 only discovers test directories whose basename starts with `test_`; the authored required path `test/protocol/test_main.cpp` was otherwise not collected.
- **Fix:** Added `test/test_protocol/test_main.cpp` as a small include wrapper and a wildcard-compatible native filter. The authored runner remains at the required `test/protocol/test_main.cpp` path.
- **Files modified:** `platformio.ini`, `test/test_protocol/test_main.cpp`
- **Verification:** `pio test -e native` collected `test_protocol` and passed all three tests; the exact filtered command exits successfully but PlatformIO reports zero cases because its CLI filter `protocol` cannot match the required `test_protocol` suite name.
- **Committed in:** `cb17635`

### Environment Deviation

**3. Exact Python 3.11 remains unavailable**
- **Found during:** host verification
- **Handling:** All host checks used `tools/phase1_bringup/.venv/bin/python` version 3.14.7, which satisfies the declared `>=3.11` floor; no exact 3.11 claim is made.
- **Impact:** No protocol scope change; exact Python 3.11 reproducibility remains an environment concern.

**Total deviations:** 2 auto-fixed issues plus 1 documented environment deviation.
**Impact on plan:** Source/build fixes were required to make the requested production-code native test runnable. The PlatformIO suite-name limitation is explicitly recorded; no hardware or interactive script was started.

## Issues Encountered

- `pio test -e native -f protocol` exits zero but reports `0 test cases` under PlatformIO Core 6.1.19 because the required `test/protocol` path is not a discoverable suite name. The compatibility suite was run without the CLI filter and passed all tests; this limitation is not represented as a false passing test claim.
- Native Unity initially failed to link protocol.cpp until `test_build_src = yes` and the source-root-relative filter were corrected.

## User Setup Required

None - no external service configuration required. No interactive hardware or hardware script was launched.

## Next Phase Readiness

- Plan 01-06 can consume the frozen schema/fixture hashes and consolidated protocol/session module for adapter-neutral USB qualification.
- Host and firmware now have one typed bounded contract for pre-dispatch validation; later transport work must preserve the 4096-byte bound, digest, fresh-session, and discard semantics.
- Exact Python 3.11 remains unavailable; continue using the project-local Python 3.14.7 environment without claiming 3.11.

## Verification Evidence

- `tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --protocol-golden protocol/fixtures/v1-golden.json --schema protocol/schema/v1.json` → `Protocol golden: verified 21 vectors with host codec/session`.
- `tools/phase1_bringup/.venv/bin/pio test -e native` → `native:test_protocol [PASSED]`; `3 test cases: 3 succeeded`.
- `tools/phase1_bringup/.venv/bin/pio test -e native -f protocol` → exit 0 with `0 test cases`; see the explicit PlatformIO limitation above.

## Self-Check: PASSED

- Summary file created with required frontmatter, actuals, dependency graph, coverage, decisions, deviations, environment limitation, and status `complete`.
- Task commits `8c5d7d8` and `cb17635` exist in repository history.
- Final host golden check passed 21 vectors; final concrete native suite passed all 3 Unity tests.
- No stubs, placeholders, TODOs, or interactive hardware processes were introduced.
