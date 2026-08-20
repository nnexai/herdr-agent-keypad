---
phase: 03-truthful-codex-capacity-and-device-menu
plan: 04
subsystem: firmware-ui
tags: [codex, renderers, primitive-log, bounded-text, compose-then-flush]

requires:
  - phase: 03-03
    provides: closed Codex wire contract, fixed-capacity Generation, and shared committed RenderState
provides:
  - Complete truthful Codex panel-4 state matrix in Signal Edge, Ledger, Beacon, and Instrument
  - Shared allocation-free percentage, reset, age, state, limit, hatch, and offline-fence helpers
  - Native primitive-log coverage for truth precedence, exact geometry, bounded copy, and Codex-only focus invariants
affects: [03-05, 03-06, 03-07, Codex LEDs, device menu, physical acceptance]

actuals:
  tokens: 11207
  tasks: 1
  commits: 1

tech-stack:
  added: []
  patterns:
    - Shared semantic formatting with theme-owned geometry
    - Fixed-capacity tail ellipsis and literal-plus-geometric state cues
    - Staged Generation data used while composing every frame of a new snapshot

key-files:
  created:
    - .planning/phases/03-truthful-codex-capacity-and-device-menu/03-04-SUMMARY.md
  modified:
    - firmware/src/app/agent_projection.cpp
    - firmware/src/app/agent_projection.h
    - firmware/src/ui/theme_common.h
    - firmware/src/ui/theme_signal_edge.cpp
    - firmware/src/ui/theme_ledger.cpp
    - firmware/src/ui/theme_beacon.cpp
    - firmware/src/ui/theme_instrument.cpp
    - test/test_agent_projection/stubs/TKeyboardS3Pro.h
    - test/test_agent_projection/test_main.cpp

key-decisions:
  - "Unavailable and auth-required presentation clear both usage windows and reset copy in firmware even if a malformed caller leaves cached fields populated."
  - "LIMIT replaces the current status-lane treatment where required, but becomes a compact header marker when stale, auth, Codex-offline, or host-offline truth must remain in the state lane."
  - "The native sprite stub records text coordinates alongside existing vocabulary entries so tests can prove exact baselines and the 4px safe inset without changing production rendering."

patterns-established:
  - "Codex semantics live in theme_common.h; each established theme owns only its approved geometry and warning vehicle."
  - "New-generation reveal frames read all presentation fields from the staged Generation, preventing mixed old-source/new-tile frames."

requirements-completed: [CODEX-01, CODEX-02, CODEX-03, CODEX-04, SAFE-01]

coverage:
  - id: D1
    description: "All four themes render fixed 5H/WEEK rows, reset, age, exact source vocabulary, and limit precedence without converting null to zero."
    requirement: CODEX-01
    verification:
      - kind: unit
        ref: "test/test_agent_projection/test_main.cpp#test_codex_rows_preserve_null_zero_partial_and_populated_values and test_codex_source_precedence_clears_or_retains_values_truthfully"
        status: pass
    human_judgment: false
  - id: D2
    description: "Signal Edge, Ledger, Beacon, and Instrument use approved title anchors, shared baselines, gauge geometry, and safe bounded tail ellipsis."
    requirement: CODEX-02
    verification:
      - kind: unit
        ref: "test/test_agent_projection/test_main.cpp#test_codex_exact_theme_geometry_and_shared_baselines and test_codex_copy_is_tail_ellipsized_inside_safe_inset"
        status: pass
    human_judgment: false
  - id: D3
    description: "LIMIT remains visible without hiding STALE, AUTH REQUIRED, CODEX OFFLINE, or HOST OFFLINE, and unknown reached state produces no positive cue."
    requirement: CODEX-03
    verification:
      - kind: unit
        ref: "test/test_agent_projection/test_main.cpp#test_codex_limit_layers_without_hiding_source_state"
        status: pass
    human_judgment: false
  - id: D4
    description: "Codex-only panel redraw flushes only panel 4 and preserves agent text, binding, snapshot revision, and direct focus intake."
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: "test/test_agent_projection/test_main.cpp#test_codex_only_redraw_preserves_agents_bindings_and_snapshot_identity"
        status: pass
    human_judgment: false

# Metrics
duration: 30min
completed: 2026-08-21
status: complete
---

# Phase 03 Plan 04: Complete truthful Codex panel renderers Summary

**All four existing display languages now render one bounded Codex view with exact null, cache, source-state, age, reset, and LIMIT semantics.**

## Performance

- **Duration:** approximately 30 min of recovery, implementation, and targeted verification
- **Started:** 2026-08-20T23:04:00Z
- **Completed:** 2026-08-20T23:34:25Z
- **Tasks:** 1
- **Files modified:** 9 implementation/test files

## Recovery Context

Two earlier specialized Plan 03-04 executors hung before producing a commit or summary. The second attempt left useful uncommitted work in `theme_common.h` and all four theme renderers. This recovery inspected and preserved that work, corrected its truth and geometry gaps, added the missing native matrix, fixed the staged-frame source mismatch exposed by the existing tests, and completed the plan without discarding unrelated working-tree changes.

## Accomplishments

- Completed Signal Edge, Ledger, Beacon, and Instrument panel 4 with fixed `5H` and `WEEK` rows, independent `N/A`, supplied zero, bounded reset/age copy, exact source words, cached-value veils, auth clearing, and layered LIMIT treatment.
- Added shared fixed-storage formatting and fence helpers, dynamic centering, 18-cell tail ellipsis, stale hatches, offline broken-link marks, auth crosses, and theme-specific alert geometry.
- Added real sprite primitive/text-coordinate assertions covering empty/loading-unavailable, zero, partial and populated windows, reset presence, reached unknown/true, stale cached, auth clear, Codex/host offline cached and empty, long text, exact baselines, safe bounds, and Codex-only focus invariants.
- Corrected new-snapshot reveal composition to read source/Codex/diagnostic presentation data from the staged Generation, eliminating mixed old-source/new-tile frames and closing the five inherited native failures.

## Task Commits

1. **Task 1: Finish the complete Codex state matrix in all four themes** - `e777d7b` (`feat(03-04): complete truthful Codex panel renderers`)

**Plan metadata:** committed with this summary and STATE/ROADMAP progress.

## Files Created/Modified

- `firmware/src/ui/theme_common.h` - Shared bounded formatting, value clearing, state precedence, gauge, hatch, broken-link, and LIMIT helpers.
- `firmware/src/ui/theme_signal_edge.cpp` - Exact rail, gauge, footer, auth, offline, stale, and limit presentation.
- `firmware/src/ui/theme_ledger.cpp` - Exact ruled rows, active-row limit inversion, header/state fences, and cached-value treatment.
- `firmware/src/ui/theme_beacon.cpp` - Dual-ring usage field, centered authoritative row copy, crossed/broken rings, halo and limit treatment.
- `firmware/src/ui/theme_instrument.cpp` - Exact tracks, warning marks, bezel state, centered metadata, and status-lane limit treatment.
- `firmware/src/app/agent_projection.cpp` and `.h` - Compose staged reveal frames from one staged Generation rather than mixing committed source fields with staged tiles.
- `test/test_agent_projection/stubs/TKeyboardS3Pro.h` - Primitive log records text coordinates while retaining existing vocabulary events.
- `test/test_agent_projection/test_main.cpp` - Complete Codex renderer matrix, exact geometry/bounds, precedence, and redraw invariants.

## Decisions Made

- Firmware defensively clears values and reset presentation for `AUTH REQUIRED` and `UNAVAILABLE`; stale and offline states retain supplied cache behind literal and geometric fences.
- Unknown reached state is silent. A supplied true limit uses each theme's established warning vehicle and never replaces a higher-priority source-state word.
- Centered themes compute x from the final bounded string, not from fallback copy, so long reset and age text remains centered and inside the safe inset.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] New snapshot reveal mixed staged tile data with committed source fields**
- **Found during:** targeted native renderer verification
- **Issue:** `commitSnapshot(BoardAdapter&)` passed staged tiles to `renderTile`, but `renderTile` built the rest of `RenderState` from `committed_generation_`. Source fences were therefore absent during the new frame reveal and five existing vocabulary assertions failed.
- **Fix:** Added a Generation-aware render helper and passed `staged_` during reveal; normal redraw paths continue to use the committed Generation.
- **Files modified:** `firmware/src/app/agent_projection.cpp`, `firmware/src/app/agent_projection.h`
- **Verification:** all inherited fence tests and the complete targeted suite pass.
- **Committed in:** `e777d7b`

**2. [Rule 2 - Missing critical functionality] Native primitive log could not prove text geometry**
- **Found during:** plan acceptance coverage
- **Issue:** The existing stub recorded text vocabulary but discarded x/y, making approved title anchors and shared baselines untestable.
- **Fix:** Preserved existing `text:` events and added parallel `textAt:` entries for exact coordinate and safe-inset assertions.
- **Files modified:** `test/test_agent_projection/stubs/TKeyboardS3Pro.h`, `test/test_agent_projection/test_main.cpp`
- **Verification:** exact theme geometry and bounded-text tests pass.
- **Committed in:** `e777d7b`

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 2 missing critical coverage)
**Impact on plan:** Both fixes were required for complete-frame truth and the plan's exact primitive-log acceptance. No renderer family, cache, allocation path, font, or display abstraction was added.

## Issues Encountered

- Two prior specialized executors hung. Neither produced a commit or summary; useful renderer edits from the second attempt were recovered in place.
- The targeted suite initially reproduced the five failures already recorded by Plan 03-03. They were caused by the staged/committed render-state mix and are now resolved rather than waived.
- Generated `.pio`, cache, artifact, debug, and unrelated planning changes already present in the working tree were preserved and excluded from both Plan 03-04 commits.

## Verification

- `tools/phase1_bringup/.venv/bin/python3 -m platformio test -e native-agent-projection` — **PASS**, 54/54 cases.
- Targeted diff whitespace check over the nine implementation/test files — **PASS**.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03-05 can map the same committed Codex/source semantics into the four existing LED grammars.
- No Plan 03-04 renderer or native-test blocker remains.

---
*Phase: 03-truthful-codex-capacity-and-device-menu*
*Completed: 2026-08-21*

## Self-Check: PASSED

- Implementation commit `e777d7b` exists.
- The targeted native renderer suite passes 54/54 cases.
- Summary, STATE, and ROADMAP are committed only after the implementation commit.
