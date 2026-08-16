---
phase: 01-physical-keypad-and-proven-transport
plan: 10
subsystem: protocol
tags: [draft-2020-12, jsonschema, python, cpp, parity, serial]
requires:
  - phase: 01-09
    provides: production protocol admission ordering and integrated runtime contract
provides:
  - hash-locked host validation environment with supported Python 3.11-3.14 range
  - closed Draft 2020-12 schema with executable per-frame payload definitions
  - duplicate-key rejection and 40 shared adversarial host/native vectors
  - native parser bounds and typed rejection parity, including unhashable discriminants
affects: [phase-01-11, protocol, host bringup, firmware]
actuals:
  tokens: 16337
  tasks: 3
  commits: 3
tech-stack:
  added: [jsonschema 4.25.1, Draft202012Validator]
  patterns: [duplicate-key rejecting JSON loads, closed per-type schema refs, bounded parser nesting]
key-files:
  created: []
  modified:
    - tools/phase1_bringup/pyproject.toml
    - tools/phase1_bringup/requirements.lock
    - tools/phase1_bringup/src/phase1_bringup/__main__.py
    - tools/phase1_bringup/src/phase1_bringup/protocol.py
    - protocol/schema/v1.json
    - protocol/fixtures/v1-golden.json
    - firmware/src/protocol/protocol.h
    - firmware/src/protocol/protocol.cpp
    - test/protocol/test_main.cpp
key-decisions:
  - "Keep the repository-supported Python range at >=3.11,<3.15 and lock pyserial plus jsonschema transitively with hashes; do not require an older interpreter."
  - "Classify a non-string frame type as unknown_type before membership checks so list/object discriminants cannot raise or drift across implementations."
  - "Treat duplicate object members as duplicate_key and reject over-limit JSON nesting as invalid_json before dispatch."
patterns-established:
  - "Every concrete fixture records schema validity separately from codec/session outcome."
  - "Native and host parsers validate wide numeric values before narrowing and never dispatch rejected frames."
requirements-completed: [HARD-01, HARD-03]
coverage:
  - id: D1
    description: "Hash-locked supported host environment reports full runtime and dependency versions from the plan-owned virtualenv."
    requirement: HARD-01
    verification:
      - kind: unit
        ref: "phase1_bringup self-check --environment"
        status: pass
    human_judgment: false
  - id: D2
    description: "Closed Draft 2020-12 schema validates accepted payloads and rejects closed-contract violations."
    requirement: HARD-03
    verification:
      - kind: unit
        ref: "phase1_bringup self-check --schema protocol/schema/v1.json --schema-draft-2020 --protocol-golden protocol/fixtures/v1-golden.json"
        status: pass
    human_judgment: false
  - id: D3
    description: "Native production parser matches all 40 shared vectors and selected-usb remains buildable."
    requirement: HARD-03
    verification:
      - kind: integration
        ref: "pio test -e native -f protocol"
        status: pass
      - kind: integration
        ref: "pio run -e selected-usb"
        status: pass
    human_judgment: false
duration: 133min
completed: 2026-08-16
status: complete
---

# Phase 1 Plan 10: Exact schema and parser parity Summary

**Hash-locked host dependencies, executable closed Draft 2020-12 payload schemas, and 40-vector host/native rejection parity are restored and verified.**

## Performance

- **Duration:** Recovery session from the aborted executor transcript; focused implementation and verification completed without hardware access.
- **Started:** 2026-08-16T20:45:44Z (aborted executor transcript)
- **Completed:** 2026-08-16T22:58:08Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Locked pyserial 3.5, jsonschema 4.25.1, and all transitive packages with universal hashes; dependency gating now records the full executable/runtime and rejects unsupported minors or ambient packages.
- Replaced metadata-only schema checks with `Draft202012Validator.check_schema` and concrete vector validation against closed per-type `$defs`, including both event alternatives and integer-vs-boolean distinctions.
- Recovered and expanded the shared fixture to 40 vectors covering duplicate keys, wide/boolean values, unhashable types, parser bounds, Unicode/escape handling, digest/session/queue behavior, and canonical frame acceptance.
- Hardened native parsing with uint32 overflow checks, explicit nesting bounds, duplicate-key classification, full input consumption, and `unknown_type` classification for array/object discriminants.

## Task Commits

1. **Task 1: Recreate the plan-owned environment on the supported Python runtime** - `6b42271` (feat)
2. **Task 2: Make the schema closed, standards-valid, and executable** - `166529b` (feat)
3. **Task 3: Expand adversarial host/native/runtime parity vectors** - `94e6bb8` (fix)

## Files Created/Modified

- `tools/phase1_bringup/pyproject.toml` - Supported Python range and direct jsonschema dependency.
- `tools/phase1_bringup/requirements.lock` - Universal hash-locked direct/transitive dependency graph.
- `tools/phase1_bringup/src/phase1_bringup/__main__.py` - Runtime/dependency gate and Draft 2020-12 CLI self-check reporting.
- `tools/phase1_bringup/src/phase1_bringup/protocol.py` - Duplicate-key, nesting, ASCII, schema-vector, and typed host validation.
- `protocol/schema/v1.json` - Closed per-type Draft 2020-12 schema definitions.
- `protocol/fixtures/v1-golden.json` - Shared accepted/rejected and adversarial vectors.
- `firmware/src/protocol/protocol.h` - Duplicate-key rejection vocabulary.
- `firmware/src/protocol/protocol.cpp` - Bounded native parser and typed parity fixes.
- `test/protocol/test_main.cpp` - Native fixture count updated to 40 vectors.

## Decisions Made

- Preserved the repository-supported Python 3.11-3.14 range rather than attempting an unavailable Python 3.11 installation; the existing plan-owned 3.14.7 environment satisfies the gate.
- Rejected duplicate JSON object names before last-write-wins parsing and kept schema-invalid outcomes distinct from valid-schema session rejections.
- Classified the known `unhashable_type` vector as `unknown_type` in native code, matching host behavior before any discriminant membership operation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed native unhashable discriminant parity**
- **Found during:** Task 3 native fixture execution.
- **Issue:** An array-valued `type` was rejected by the native string parser as `invalid_json`, while host classification correctly returned `unknown_type`.
- **Fix:** Consume non-string type values through the bounded generic parser and classify them as `unknown_type`; malformed tokens remain `invalid_json`.
- **Files modified:** `firmware/src/protocol/protocol.cpp`, `protocol/fixtures/v1-golden.json`.
- **Verification:** Native fixture suite passed all 40 vectors; host golden check passed the same 40 vectors.
- **Committed in:** `94e6bb8`.

**2. [Rule 2 - Missing critical] Added parser-level duplicate-key and nesting defenses**
- **Found during:** Task 2/3 parity implementation.
- **Issue:** JSON object duplicates were silently last-write-wins on host and reported as generic shape/field failures in native code; recursive native parsing had no explicit depth bound.
- **Fix:** Added duplicate-key hooks and `duplicate_key` vocabulary, native duplicate tracking, and an eight-level nesting bound with typed failure.
- **Files modified:** `tools/phase1_bringup/src/phase1_bringup/protocol.py`, `protocol/schema/v1.json`, `firmware/src/protocol/protocol.cpp`, `firmware/src/protocol/protocol.h`.
- **Verification:** Host schema/golden check and native protocol fixture suite passed.
- **Committed in:** `166529b`, `94e6bb8`.

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical parser defense).
**Impact on plan:** Both corrections are directly required for the planned adversarial parity and do not broaden the protocol surface.

## Issues Encountered

- The prior executor transcript ended after uncommitted firmware edits and the working tree had been restored. Changes were reconstructed from the transcript and current baseline; unrelated `guide.py`, `qualification.py`, planning, and artifact changes were left untouched.
- PlatformIO was reinstalled into the existing plan-owned virtualenv after lock synchronization removed its tooling; no hardware was flashed.

## Verification Evidence

- `tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --environment --schema protocol/schema/v1.json --schema-draft-2020 --protocol-golden protocol/fixtures/v1-golden.json` — passed; reports Python 3.14.7, pyserial 3.5, jsonschema 4.25.1 and verifies 40 vectors.
- `tools/phase1_bringup/.venv/bin/pio test -e native -f protocol` — passed; 4 native tests, including all 40 fixture rows.
- `tools/phase1_bringup/.venv/bin/pio run -e selected-usb` — passed; production selected-usb image built without flashing.
- `git diff --check` — passed.

## Next Phase Readiness

- The frozen schema, host codec, native codec/session, and selected-usb build are aligned for subsequent recovery/qualification work.
- No physical/manual validation or firmware flash was performed, as required for this recovery.

---
*Phase: 01-physical-keypad-and-proven-transport*
*Completed: 2026-08-16*

## Self-Check: PASSED

- Summary file exists at the required path.
- Task commits `6b42271`, `166529b`, and `94e6bb8` are present in git history.
