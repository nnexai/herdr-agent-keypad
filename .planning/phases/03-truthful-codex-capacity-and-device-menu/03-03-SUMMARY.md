---
phase: 03-truthful-codex-capacity-and-device-menu
plan: 03
subsystem: protocol-and-firmware-ui
tags: [protocol-v2, codex, diagnostics, firmware, render-state, atomic-staging]

# Dependency graph
requires:
  - phase: 03-02
    provides: Codex projection, independent health clocks, and focus-generation invariants
provides:
  - Closed v2 agent_snapshot Codex and diagnostics contract with host/native parity
  - Canonical golden vectors for accepted and rejected Codex/diagnostic payloads
  - One atomically staged firmware Generation and shared committed RenderState
affects: [phase-03-renderers, phase-03-device-menu, firmware-protocol, host-bridge]

# Actuals (#2632)
actuals:
  tokens: 15159
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns: [closed allowlisted payload validation, fixed-capacity Generation storage, candidate-then-swap staging]

key-files:
  created: []
  modified:
    - protocol/schema/v2.json
    - protocol/fixtures/v2-golden.json
    - tools/phase1_bringup/src/phase1_bringup/protocol.py
    - host/herdr_keypad/src/herdr_keypad/bridge.py
    - firmware/src/protocol/protocol.cpp
    - firmware/src/ui/render_state.h
    - firmware/src/app/agent_projection.h
    - firmware/src/app/agent_projection.cpp
    - test/protocol/test_main.cpp
    - test/test_agent_projection/test_main.cpp

key-decisions:
  - "Require the extended Codex and diagnostics objects on every v2 agent_snapshot; no legacy Phase 3 payload remains."
  - "Use an allowlisted E-2400 through E-2410 error-code range, including E-2401 for unavailable Codex capacity."
  - "Stage into a complete local Generation candidate and swap it only after every field and agent binding validates."
  - "Expose diagnostics as non-owning views from the committed Generation rather than introducing renderer or menu caches."

patterns-established:
  - "Host and native admission share exact field sets, bounds, enum sets, suffix grammar, and E-#### allowlist."
  - "Rejected snapshots clear only the pending stage and cannot mutate committed generation or active bindings."

requirements-completed: [CODEX-01, CODEX-02, CODEX-03, CODEX-04, SYNC-03, SAFE-01]

coverage:
  - id: D1
    description: "Closed v2 agent_snapshot Codex and diagnostics payload is admitted and rejected consistently across host and native codecs."
    requirement: CODEX-01
    verification:
      - kind: unit
        ref: "host.herdr_keypad.tests.test_protocol (6 tests)"
        status: pass
      - kind: unit
        ref: "test/protocol/test_main.cpp direct native Unity run (5 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "One fixed-capacity Generation carries complete agent, Codex, and diagnostics data into one shared RenderState."
    requirement: CODEX-02
    verification:
      - kind: unit
        ref: "test_committed_render_state_exposes_one_codex_and_diagnostics_view"
        status: pass
    human_judgment: false
  - id: D3
    description: "Invalid diagnostics are rejected without changing committed diagnostics or active agent binding."
    requirement: SYNC-03
    verification:
      - kind: unit
        ref: "test_rejected_diagnostics_preserve_committed_generation_and_binding"
        status: pass
    human_judgment: false
  - id: D4
    description: "Host protocol, projection, and integration callers use the closed complete snapshot contract."
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: "host.herdr_keypad.tests.test_protocol test_projection test_integration (38 tests)"
        status: pass
    human_judgment: false

# Metrics
duration: 3min
completed: 2026-08-20
status: complete
---

# Phase 3 Plan 3: Closed Codex protocol and atomic firmware presentation Summary

**Closed the v2 Codex/diagnostics wire contract and staged all agent, Codex, and health data through one atomic firmware Generation into one shared RenderState.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-08-20T21:49:26Z
- **Completed:** 2026-08-20T22:08:59Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Tightened the schema, golden fixture, host bridge, bring-up codec, and native FrameCodec around complete bounded Codex and diagnostics objects, including E-2401 bucket-unavailable semantics, suffix validation, duplicate/unknown/sensitive-field rejection, and the existing 4096-byte transport bound.
- Migrated the current integration caller to the complete snapshot shape while preserving v2 focus intent/result identity fencing and canonical digest behavior.
- Added fixed-capacity Codex and diagnostic storage beside agent tiles, validates into a local candidate Generation, and only swaps into the pending stage after all fields and bindings pass.
- Added shared non-owning diagnostics views to RenderState and populated them from the same committed Generation used by every tile render.

## Task Commits

Each task was committed atomically with TDD red/green commits:

1. **Task 1: Close the version 2 Codex and diagnostics payload across host and native codecs** - `11524c9` (test), `0f04cc5` (feat)
2. **Task 2: Stage one complete Codex and diagnostic RenderState** - `707dd20` (test), `deff94a` (feat)

**Plan metadata:** Pending state/roadmap metadata commit after this summary and self-check.

## Files Created/Modified

- `protocol/schema/v2.json` - Closed Codex and diagnostics schemas and bounds.
- `protocol/fixtures/v2-golden.json` - Accepted E-2401 and rejection vectors.
- `tools/phase1_bringup/src/phase1_bringup/protocol.py` - Host/native-facing strict v2 admission rules.
- `host/herdr_keypad/src/herdr_keypad/bridge.py` - Complete diagnostic projection and snapshot payload.
- `host/herdr_keypad/tests/test_protocol.py` - Presence, error-code, sensitive-field, and type coverage.
- `host/herdr_keypad/tests/test_integration.py` - Complete snapshot caller migration.
- `firmware/src/protocol/protocol.cpp` - Native strict Codex/diagnostics admission.
- `test/protocol/test_main.cpp` - Native golden-vector parity coverage.
- `firmware/src/ui/render_state.h` - Shared Codex and diagnostics presentation views.
- `firmware/src/app/agent_projection.h` - Fixed-capacity Generation diagnostic storage.
- `firmware/src/app/agent_projection.cpp` - Atomic candidate staging and committed-view mapping.
- `test/test_agent_projection/test_main.cpp` - Shared-view and rejection-preservation tests.

## Decisions Made

- The extended `agent_snapshot` is the sole v2 publication; no optional legacy payload or second diagnostics message family was introduced.
- Error codes remain a closed E-2400..E-2410 allowlist; E-2401 carries only unavailable capacity semantics and no bucket identity or claim.
- Native staging validates all Codex and diagnostic fields into a local candidate before assigning `staged_`, preventing partial mutation on rejection.
- Firmware RenderState owns only non-owning views; fixed storage remains in AgentProjection's Generation so renderers and LED grammars cannot drift.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Migrated an existing integration caller to the closed snapshot shape**
- **Found during:** Task 1
- **Issue:** One current host integration fixture still constructed the former shorter agent snapshot and failed once Codex and diagnostics became required.
- **Fix:** Updated that caller to use the complete bridge snapshot contract; no alternate or legacy payload was retained.
- **Files modified:** `host/herdr_keypad/tests/test_integration.py`
- **Verification:** Full targeted host protocol, projection, and integration run passed 38 tests.
- **Committed in:** `0f04cc5`

**2. [Rule 2 - Missing critical functionality] Enforced atomic candidate staging for Codex and diagnostics**
- **Found during:** Task 2
- **Issue:** The previous stage path wrote directly into `staged_`, allowing a later validation failure to leave partial pending data and did not carry diagnostics into RenderState.
- **Fix:** Validate and copy all fields into a local Generation candidate, assign the stage only on complete success, and expose diagnostics from the committed Generation.
- **Files modified:** `firmware/src/app/agent_projection.cpp`, `firmware/src/app/agent_projection.h`, `firmware/src/ui/render_state.h`
- **Verification:** New shared-view and rejected-diagnostics preservation tests passed in the native projection run.
- **Committed in:** `deff94a`

**Total deviations:** 2 auto-fixed (Rule 1: 1, Rule 2: 1)
**Impact on plan:** Both fixes were required for the closed cutover and atomicity acceptance criteria; no scope creep was introduced.

## Issues Encountered

- The PlatformIO native protocol selector reported zero test cases in this checkout. The protocol suite was still compiled and executed directly with the repository's Unity source; all five native protocol tests passed.
- The complete `native-agent-projection` run reports five existing visual assertion failures (`STALE`/theme vocabulary and usage-placeholder geometry) while the two new Codex/diagnostics tests and 43 other cases pass. The failing assertions are in unchanged theme test areas; they do not involve the new staging or diagnostics behavior.
- Build/test commands modified ignored `.pio` artifacts and installed the already-declared Unity dependency; these generated changes were not staged.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The next renderer/menu work can consume `RenderState::codex` and `RenderState::diagnostics` directly. Protocol admission, identity fencing, bounded values, and atomic Generation commit are now fixed seams. Existing unrelated visual assertion failures should be addressed by the renderer-focused plan before shipping.

---
*Phase: 03-truthful-codex-capacity-and-device-menu*
*Completed: 2026-08-20*
## Self-Check: PASSED

- Summary file exists at the required phase path.
- Task commits `11524c9`, `0f04cc5`, `707dd20`, and `deff94a` are present in repository history.
