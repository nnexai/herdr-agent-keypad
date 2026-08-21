---
phase: 03-truthful-codex-capacity-and-device-menu
plan: 05
subsystem: firmware-ui
tags: [codex, leds, render-state, focus-feedback, power-policy]

requires:
  - phase: 03-04
    provides: committed Codex RenderState and complete panel-4 truth semantics
  - phase: 02.2-03
    provides: four bounded LED grammars and centralized LedEngine power policy
provides:
  - Current-only Codex primary usage in every established grammar usage zone
  - Shared LIMIT and source-failure LED classification from committed RenderState
  - Focus-over-health precedence with preserved menu, dim, cap, and all-off behavior
affects: [03-06, 03-07, 03-08, Codex LEDs, device menu, physical acceptance]

actuals:
  tokens: 7414
  tasks: 1
  commits: 1

tech-stack:
  added: []
  patterns:
    - Shared allocation-free Codex LED cue derived from committed RenderState
    - Grammar-owned physical zones under centralized LedEngine power and precedence policy

key-files:
  created:
    - .planning/phases/03-truthful-codex-capacity-and-device-menu/03-05-SUMMARY.md
  modified:
    - firmware/src/ui/led_grammar.h
    - firmware/src/ui/led_engine.cpp
    - firmware/src/ui/led_grammar_rail_echo.cpp
    - firmware/src/ui/led_grammar_exception.cpp
    - firmware/src/ui/led_grammar_field_ext.cpp
    - firmware/src/ui/led_grammar_meter_lamps.cpp
    - test/test_agent_projection/test_main.cpp

key-decisions:
  - "A committed CURRENT primary value owns only the grammar's existing usage zone; absent or non-current primary data never emits a current cyan/amber cue."
  - "LIMIT is a current warning cue, while stale, unavailable, auth-required, Codex-offline, and host-offline states use the established grammar health layer."
  - "A bounded focus cue is emitted after ambient health so pending and failure feedback remain visible without relaxing global brightness, high-count, dim, or all-off limits."

patterns-established:
  - "LedEvents remains transient-only: menu_open, dim, and all_off; every Codex LED fact comes from RenderState.codex."
  - "All four grammars share source/usage classification but retain independent physical geometry."

requirements-completed: [CODEX-01, CODEX-02, CODEX-03, SYNC-03]

coverage:
  - id: D1
    description: "Rail Echo, Exception, Field Extension, and Meter + Lamps consume committed current primary usage, including supplied zero, 75% warning, exact meter quarter boundaries, and absent-dark behavior."
    requirement: CODEX-01
    verification:
      - kind: integration
        ref: "test/test_agent_projection/test_main.cpp#test_led_grammars_consume_committed_current_usage_boundaries and test_meter_lamps_uses_exact_primary_quarter_boundaries"
        status: pass
    human_judgment: false
  - id: D2
    description: "LIMIT and every Codex failure state use warning or health channels without making cached percentages look current."
    requirement: CODEX-03
    verification:
      - kind: integration
        ref: "test/test_agent_projection/test_main.cpp#test_codex_failures_use_health_overlays_and_focus_preempts_them"
        status: pass
    human_judgment: false
  - id: D3
    description: "Committed focus feedback preempts ambient health while L13 menu indication, grammar switching, global caps, and all-off retain their established behavior."
    requirement: SYNC-03
    verification:
      - kind: integration
        ref: "test/test_agent_projection/test_main.cpp#test_codex_failures_use_health_overlays_and_focus_preempts_them and test_menu_all_off_and_grammar_switch_keep_led_engine_precedence"
        status: pass
    human_judgment: false

# Metrics
duration: 28min
completed: 2026-08-21
status: complete
---

# Phase 03 Plan 05: Truthful Codex LED projection Summary

**All four existing LED grammars now derive current usage, LIMIT, and source-health cues from the same committed Codex RenderState used by panel 4, without adding a second producer path.**

## Performance

- **Duration:** 28 min
- **Completed:** 2026-08-21T00:17:52Z
- **Tasks:** 1
- **Files modified:** 8 implementation/test files

## Accomplishments

- Added one shared, allocation-free Codex LED classification over `RenderState.codex`: current supplied primary values produce cyan below 75%, amber at or above 75%, and red only for supplied LIMIT; absent primary stays dark.
- Filled each established zone without changing the physical grammar: Rail Echo and Exception use L10, Field Extension uses L9-L11, and Meter + Lamps uses L10 plus the exact L0/L2/L3/L6 quarter meter.
- Routed stale, unavailable, auth-required, Codex-offline, and host-offline states through each grammar's established health overlay and suppressed current usage cues while cached data is veiled.
- Preserved direct focus feedback over health overlays, Field Extension's health-owned encoder pair, the healthy menu-open L13 cue, bounded grammar output, dim/global/high-count caps, redundant-write suppression, and one-write all-off.
- Added production-module native coverage built from committed `AgentProjection::renderState()` fixtures; transient `LedEvents` cannot manufacture Codex usage or health.

## Task Commits

1. **Task 1: Map truthful Codex usage and health through all four LED grammars** — `7ef4cce` (`feat(03-05): project Codex truth into LED grammars`)

**Plan metadata:** committed with this summary and STATE/ROADMAP progress.

## Files Created/Modified

- `firmware/src/ui/led_grammar.h` — Shared current-usage, LIMIT, Herdr-health, and Codex-health classification; `LedEvents` remains transient-only.
- `firmware/src/ui/led_engine.cpp` — Codex health participates in semantic priority and the health cap while bounded focus feedback can preempt the ambient layer.
- `firmware/src/ui/led_grammar_rail_echo.cpp` — L10 current/warning cue plus health-safe focus precedence.
- `firmware/src/ui/led_grammar_exception.cpp` — L10 Codex exception cue alongside the existing above-key health channel.
- `firmware/src/ui/led_grammar_field_ext.cpp` — L9-L11 usage halo with health-owned L12-L13 and focus sweep/blink precedence.
- `firmware/src/ui/led_grammar_meter_lamps.cpp` — L10 source lamp and exact proportional four-step primary meter; meter stays dark for non-current source states.
- `test/test_agent_projection/test_main.cpp` — Committed RenderState matrix for zero, absent, thresholds, LIMIT, five failure states, focus, menu, grammar changes, caps, and all-off.

## Decisions Made

- The panel remains text-authoritative. LEDs provide a redundant physical cue, so zero and absent remain distinguishable on panel 4 even where a proportional meter is dark at exact zero.
- Reached-limit true is allowed to produce its red warning even when a current primary percentage is absent; unknown or false reached state produces no positive claim.
- Source state is consumed as committed. Firmware does not reclassify observation age or invent a provider clock.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing health-first branches suppressed direct focus feedback**
- **Found during:** the committed source-failure and focus-precedence matrix
- **Issue:** Rail Echo, Field Extension, and Meter + Lamps returned or skipped their focus zones while a source health overlay was active.
- **Fix:** Kept health in its established zone and emitted bounded focus feedback afterward only in the pressed agent's mapped zone.
- **Verification:** pending and rejected feedback assertions pass for all four production grammars under committed stale Codex state.
- **Committed in:** `7ef4cce`

**2. [Rule 1 - Bug] Health capping could erase a later red failure cue**
- **Found during:** focus-over-health verification
- **Issue:** LedEngine's generic red health clamp could reduce an intentional bounded failure cue to health brightness.
- **Fix:** Retained the fail-safe health clamp outside active feedback; production health layers still request at most brightness 10, while bounded focus feedback retains its existing grammar level.
- **Verification:** rejected focus remains visible in every grammar while health outputs stay at or below the health cap.
- **Committed in:** `7ef4cce`

**Total deviations:** 2 auto-fixed correctness defects.
**Impact on plan:** Both fixes were necessary to satisfy the locked focus-precedence and power-policy contract. No new LED engine, cache, event producer, clock, or hardware path was added.

## Issues Encountered

The first red test run exposed the missing usage/source behavior as intended. After implementation, inherited native fixtures that constructed a default unavailable Codex view were updated to declare CURRENT explicitly where they were testing agent-only scenes.

## Verification

- `tools/phase1_bringup/.venv/bin/python3 -m platformio test -e native-agent-projection` — **PASS**, 58/58 cases.
- Targeted implementation whitespace check — **PASS**.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03-06 can extend the existing menu controller and settings store; LED grammar switching and L13 behavior are covered against the committed presentation path.
- No Plan 03-05 native blocker remains.

---
*Phase: 03-truthful-codex-capacity-and-device-menu*
*Completed: 2026-08-21*

## Self-Check: PASSED

- Implementation commit `7ef4cce` exists.
- The targeted native suite passes 58/58 cases.
- `LedEvents` still contains only `menu_open`, `dim`, and `all_off`.
- Summary, STATE, and ROADMAP are committed only after the implementation commit.
