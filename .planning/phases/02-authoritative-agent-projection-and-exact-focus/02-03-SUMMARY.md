---
phase: 02-authoritative-agent-projection-and-exact-focus
plan: 03
subsystem: firmware-three-slot-renderer-and-focus-feedback
tags: [firmware, renderer, fixed-slots, sync-veil, focus]
requires:
  - phase: 02-authoritative-agent-projection-and-exact-focus
    plan: 01
    provides: "v2 protocol/session seam, fixed three-slot payload, and typed focus result"
provides:
  - "Atomic fixed-capacity three-slot firmware projection and sequential renderer"
  - "Truthful state colors, labels, geometric cues, empty/stale/offline/unavailable veils"
  - "Generation-bound physical key focus intents with pending, timeout, and correlated terminal feedback"
affects: [02-04]
tech-stack:
  added: ["BoardAdapter sequential panel renderer using LovyanGFX Display abstraction"]
  patterns: ["global sync veil", "staged generation commit", "bounded pending deadline"]
key-files:
  created: []
  modified:
    - firmware/src/app/agent_projection.h
    - firmware/src/app/agent_projection.cpp
    - firmware/src/main.cpp
decisions:
  - "Three canonical keys remain the only product actions; panel/key 4 and encoder stay untouched."
  - "A replacement first disables all bindings and renders SYNC, then draws all three staged tiles before one active-generation commit."
  - "Focus terminal feedback is static, bounded, and non-retrying: FOCUSED, REJECTED, STALE, VANISHED, OFFLINE, UNCERTAIN, or FAILED."
actuals:
  tokens: 27500
  tasks: 2
  commits: 3
metrics:
  duration: 1h
  completed: 2026-08-17
status: complete
---

# Phase 2 Plan 3: Firmware three-slot renderer and focus feedback Summary

**Firmware now presents one truthful host-supplied three-slot generation at a time and binds physical presses to exact identities with correlated, non-retrying feedback.**

## Accomplishments

- Expanded `AgentProjection` to fixed-capacity staged and active generations with bounded NUL-terminated title, discriminator, entry, pane, terminal, optional session, and source revision fields; no heap-backed collection or rank/status sorting exists in firmware.
- Added monotonic snapshot revision validation within a host epoch, exact three-position validation, explicit empty records, and fail-closed source/identity checks.
- Added sequential BoardAdapter rendering: all three keys are disabled and panels receive a neutral `SYNC` veil before staged tiles are drawn one panel at a time; active bindings switch only after all draws succeed.
- Implemented the specified bounded tile layout and non-color cues for BLOCKED, UNSEEN, WORKING, IDLE, SETTLED, UNKNOWN, EMPTY, plus dominant STALE, OFFLINE, and UNAVAILABLE states. Titles and discriminators are bounded/truncated and raw paths are never rendered.
- Replaced armed-input-only product handling with canonical key 0..2 focus capture. Captured intents copy the exact committed opaque identity and generation, suppress duplicate pending presses, enforce a three-second deadline, and render PENDING immediately.
- Added strict result correlation and static two-second terminal feedback for FOCUSED, REJECTED, STALE, VANISHED, OFFLINE, UNCERTAIN, and FAILED; late/unrelated/mismatched results are ignored and no retry/triage action is emitted.

## Verification Evidence

- `tools/phase1_bringup/.venv/bin/pio run -e selected-usb` — passed; firmware compiled with the official sequential board abstraction and no Wi-Fi source. The build emitted only the pre-existing Arduino log-level redefinition warnings.
- `tools/phase1_bringup/.venv/bin/pio test -e native -f protocol` — passed, 5/5 existing production protocol tests, including v1/v2 golden vectors, queue bounds, version rejection, and reset behavior.
- Host focused checks from Plan 02 remained green: projection/focus 9 tests and protocol 5 tests passed before this firmware-only plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Kept stale/offline tiles visibly non-actionable during sequential redraw**
- **Found during:** Task 1 renderer integration
- **Issue:** The staged draw occurred while the previous generation's source status was still selected, which could hide the dominant stale/offline veil.
- **Fix:** The renderer now adopts the staged source status while the global sync veil remains active, then commits bindings only after all three draws succeed.
- **Files modified:** `firmware/src/app/agent_projection.cpp`
- **Commit:** `024984f`

## Auth Gates

None.

## Known Stubs

None. No placeholder renderer, skipped native check, or unrun selected-usb verification remains for this plan's requested checks.

## Self-Check: PASSED

- Firmware projection header/source and main integration exist.
- Commits `e782861`, `eb4e1a0`, and `024984f` are present.
- Final selected-usb build and native protocol suite both passed.
