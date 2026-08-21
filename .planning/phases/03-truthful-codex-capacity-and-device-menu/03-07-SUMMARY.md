---
phase: 03-truthful-codex-capacity-and-device-menu
plan: 07
subsystem: firmware-menu-rendering
status: complete
tags: [menu, themes, diagnostics, bounds, panel-4]

requires:
  - phase: 03-06
    provides: six-row controller, bounded viewport, previews, timeout, and direct-key routing
provides:
  - Exact six-row root viewport and edit-page geometry in all four existing themes
  - Fixed bounded HEALTH and ABOUT pages backed only by committed diagnostics
  - Panel-4-only menu repaint with live diagnostic and direct-focus invariants
  - Production-renderer native matrix covering every theme and menu page
affects: [03-08, 03-09, device acceptance, menu contact sheets]

actuals:
  duration: 10min
  tasks: 1
  commits: 1

key-files:
  created: []
  modified:
    - firmware/src/ui/theme.h
    - firmware/src/ui/theme_common.h
    - firmware/src/ui/theme_signal_edge.cpp
    - firmware/src/ui/theme_ledger.cpp
    - firmware/src/ui/theme_beacon.cpp
    - firmware/src/ui/theme_instrument.cpp
    - firmware/src/app/agent_projection.cpp
    - test/test_agent_projection/test_main.cpp

requirements-completed: [SYNC-03, SAFE-01, MENU-01, MENU-02, MENU-03, MENU-04]
completed: 2026-08-21
---

# Phase 03 Plan 07: Bounded All-Theme Device Menu Summary

**All four existing renderers now draw the approved root, value previews, brightness, HEALTH, and ABOUT pages from one shared bounded menu model while `AgentProjection` continues to repaint panel 4 only.**

## Accomplishments

- Replaced the two-row placeholder menus with exactly six root rows in the approved order, a clamped three-row viewport, baselines at 30/54/78, current THEME/LEDS/BRIGHTNESS values, and exact Signal Edge, Ledger, Beacon, and Instrument cursor/value treatments.
- Added THEME and LEDS candidate pages plus the 10%–100% brightness page with the approved title, content, track, and `TURN:CHANGE` / `CLICK:SAVE` bands. Each renderer preserves its existing rail, rules, centered beacon language, or instrument bezel.
- Added fixed six-row HEALTH and ABOUT pages at baselines 30/46/62/78/94/110 with `CLICK:BACK` at 122. HEALTH maps only the closed link/Herdr/Codex vocabulary, bounded ages, and `NONE` or an allowlisted `E-####` code.
- ABOUT renders only firmware, protocol, bridge, and six-character device/session/revision suffix rows. Missing values become `N/A`; long versions are tail-ellipsized; non-hex suffixes are withheld as `N/A`.
- Extended the existing `MenuState` presentation view with diagnostics pointers and had `AgentProjection::renderMenu()` populate them from the committed generation immediately before synchronous composition. No controller, cache, renderer family, or interaction path was added.
- Added native primitive-log coverage for all cursor positions, all four themes, every preview/detail page, exact anchors and baselines, long and absent values, closed diagnostic admission, live updates, timeout/cursor invariants, direct focus, and panel-4-only flushing.

## Task Commit

1. **Task 1: Render root, previews, HEALTH, and ABOUT in every theme** — `9d90444` (`feat(03-07): render bounded device menu pages`)

**Plan metadata:** committed last with this summary and STATE/ROADMAP progress.

## Decisions Made

- Shared row, footer, status, age, error, version, suffix, and ellipsis behavior lives in `theme_common.h`; each existing renderer retains ownership only of its established visual decoration.
- Menu diagnostics are a transient copy of pointers into the already committed generation. Rendering remains synchronous and read-only, so it cannot move the cursor, alter the viewport, reset the encoder deadline, or create a second diagnostic cache.
- The upstream bounded alphanumeric suffix admission remains compatible with disconnected sentinels, while ABOUT displays only exact six-character uppercase hexadecimal suffixes and otherwise shows `N/A`.
- Firmware and bridge versions admit only bounded semantic-style characters plus the existing unavailable sentinel, preventing paths, account strings, and raw diagnostic copy from entering the committed view.

## Deviations from Plan

### Clarified viewport example

The implementation and tests follow the approved formula already implemented in Plan 03-06: `min(max(cursor - 1, 0), 3)`, yielding starts `0,0,1,2,3,3`. This resolves the contradictory prose example in the UI specification without changing controller behavior.

No second menu, renderer, diagnostics cache, input path, settings authority, or host field was introduced.

## Verification

- `tools/phase1_bringup/.venv/bin/python3 -m platformio test -e native-agent-projection` — **PASS**, 65/65 cases.
- Native logs prove each `renderMenu()` call pushes only display index 3 and committed direct focus remains actionable after live diagnostic replacement.

## Next Phase Readiness

- Plan 03-08 can capture the complete all-theme/menu acceptance matrix and contact sheets from the production renderer seam.
- Exact-device optical proof remains intentionally pending for the blocking Plan 03-09 checkpoint.

## Self-Check: PASSED

- Implementation commit `9d90444` exists.
- All plan-specific native renderer tests pass.
- Summary, STATE, and ROADMAP are ready for the final metadata commit.
