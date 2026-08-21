---
phase: 03-truthful-codex-capacity-and-device-menu
plan: 06
subsystem: firmware-input-menu
status: complete
tags: [menu, brightness, nvs, input-router, non-modal]

requires:
  - phase: 03-05
    provides: committed Codex presentation and focus-safe LED projection
provides:
  - Six-row clamped menu controller with bounded root, edit, health, and about modes
  - Local 10%-step brightness preview, confirmation, timeout, and revert intents
  - Schema-v1-compatible, marker-last schema-v2 presentation persistence
  - Pure fixed-capacity ProductInputRouter shared by production and native tests
  - One-frame production input capture with direct-agent actions before menu actions
affects: [03-07, menu rendering, device controls, direct focus]

actuals:
  duration: 11min
  tasks: 2
  commits: 2

key-files:
  created:
    - firmware/src/app/product_input_router.h
    - firmware/src/app/product_input_router.cpp
  modified:
    - firmware/src/app/menu_controller.h
    - firmware/src/app/menu_controller.cpp
    - firmware/src/app/settings_store.h
    - firmware/src/app/settings_store.cpp
    - firmware/src/ui/theme.h
    - firmware/src/main.cpp
    - platformio.ini
    - test/test_agent_projection/test_main.cpp
    - test/test_agent_projection/stubs/TKeyboardS3Pro.h

requirements-completed: [MENU-01, MENU-04, SAFE-01]
completed: 2026-08-21
---

# Phase 03 Plan 06: Non-modal device input and local brightness Summary

**The production loop now captures one hardware frame after `board.update()`, routes all direct agent slots before encoder actions through the same pure fixed-capacity module executed by native tests, and drives a six-row menu with local confirm-only brightness persistence.**

## Accomplishments

- Expanded the existing controller to closed, root, theme, LED, brightness, health, and about modes with six clamped rows, the exact bounded viewport formula, clamped four-value edits, click-only enter/confirm/back/close behavior, and a wrap-safe 30-second encoder-only inactivity deadline.
- Added brightness candidates from 10% through 100% in 10-point steps. Rotation emits an immediate local hardware intent; close and timeout emit a stored-value revert; confirmation persists locally without host state or protocol actions.
- Extended the sole NVS record to schema v2 with only `ver`, `theme`, `ledgram`, and `bright`. Valid schema-v1 records load their original theme and grammar plus 80% in memory with zero boot writes. Explicit confirmation invalidates the marker first and commits it last; recoverable write failures restore the prior valid record.
- Added `ProductInputFrame`, `ProductInputAction`, and `ProductInputRouter` as a stateless five-action-capacity ordering seam. It emits pressed slots 0–2 in displayed order, then encoder click, then encoder rotation.
- Reworked `main.cpp` to capture physical edges once immediately after `board.update()`, dispatch routed focus actions before menu actions, apply loaded brightness at boot, and apply preview/revert intents directly through `BoardAdapter::setBrightness()`.
- Native tests compile and execute `product_input_router.cpp`, cover simultaneous three-key/click/rotation frames, every menu mode, direct-key cursor/deadline invariants, all root viewport positions, brightness clamps/reverts, wraparound timeout, schema-v1 reads, schema-v2 inventory, and every marker-last write failure.

## Task Commits

1. **Task 1: Extend the menu state machine and brightness-only persistence** — `e5d990c` (`feat(03-06): extend menu and brightness persistence`)
2. **Task 2: Wire encoder-only menu intents after unconditional direct keys** — `c77cb32` (`feat(03-06): route product input before menu events`)

**Plan metadata:** committed last with this summary and STATE/ROADMAP progress.

## Decisions Made

- Menu timing uses the existing loop's 32-bit microsecond clock. Unsigned elapsed subtraction gives the required 30-second behavior across clock wrap without another timer or scheduler.
- Confirming any presentation value writes one complete schema-v2 record, so schema-v1 migration occurs only as a consequence of an explicit user confirmation and never during load or boot.
- The router carries captured values and ordering only. It does not own menu state, focus state, hardware, timing, a queue, key mapping, or protocol authorization.
- Agent input remains absent from `MenuController`; production dispatch continues through `AgentProjection::captureFocusIntent()` and the existing focus-only protocol path.

## Deviations from Plan

### Necessary supporting-file changes

- `firmware/src/ui/theme.h` gained the bounded menu page and brightness fields consumed by the controller and reserved for Plan 03-07 rendering.
- The native Preferences stub gained the production API's `remove()` operation so rollback of a failed schema-v2 replacement can restore a prior schema-v1 record exactly.
- `platformio.ini` now compiles the production router into the native test environment, preventing a test-only routing implementation.

No second controller, settings store, key map, brightness path, focus path, queue, host action, or persisted host field was introduced.

## Verification

- `tools/phase1_bringup/.venv/bin/python3 -m platformio test -e native-agent-projection` — **PASS**, 61/61 cases.
- `tools/phase1_bringup/.venv/bin/python3 -m platformio run -e selected-usb` — **PASS**; firmware image built successfully.

## Next Phase Readiness

- Plan 03-07 can render the root viewport, preview pages, HEALTH, and ABOUT directly from the bounded `MenuState` page/candidate fields.
- Controller, persistence, input ordering, timeout, and local brightness hardware semantics have native production-module coverage; no Plan 03-06 blocker remains.

## Self-Check: PASSED

- Both implementation commits exist and are task-atomic.
- Summary, STATE, and ROADMAP are committed after both implementation tasks.
- Native tests execute the exact production router module and selected firmware links it.
