---
status: resolved
trigger: "The keypad is attached and available for direct control. Capture all relevant screen and theme renderings, identify visual defects, fix them inline, and verify a polished result with no overlap and intended composition before any other project work continues."
created: 2026-08-20T13:07:15+02:00
updated: 2026-08-20T13:29:29+02:00
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "the renderers use fixed coordinates without enforcing text budgets, unsupported UTF-8 copy, and a few composition layers that draw the same information or geometry twice"
  confirming_evidence:
    - "80 deterministic on-device RGB565 captures cover four themes, seven resting states, three source fences, six feedback states, sync, two menu rows, and panel 4"
    - "all four menus clip the footer; Signal Edge and Ledger also clip METER+LAMPS at the right edge"
    - "Signal Edge EMPTY draws its dash through NO AGENT; Ledger and Instrument repeat terminal feedback words"
    - "Ledger's Unicode null marker renders as blank; Beacon's panel-4 hatch escapes the dial; Beacon's eight solid radial bands form a bullseye"
    - "Signal Edge and Ledger place five-character since values beyond x=127"
  falsification_test: "passed - the post-fix 80-scene matrix plus the four affected Instrument ring recaptures contain no confirmed clipping, overlap, duplicate feedback copy, missing null marker, bullseye field, or leaking hatch"
  fix_rationale: "ASCII-only bounded copy, one semantic label per screen region, right-bounded time fields, clipped/dithered geometry, and a compact menu footer now fit the 4 px safe inset"
  blind_spots: "framebuffer captures do not prove physical brightness, viewing angle, or LED appearance"
  candidate_causes:
    - "menu footer is 25 UTF-8 bytes and over 120 display pixels; the bitmap font renders the punctuation as substitute glyphs"
    - "fixed x positions assume shorter values than the longest allowed theme, grammar, and since strings"
    - "some renderers compose a feedback word in both the primary state line and the reserved detail line"
    - "Beacon uses solid concentric fills and unclipped diagonal lines"
  and_gate: "yes - bounded 128 by 128 geometry combines with unbounded or duplicated composition choices"
bug_class: deterministic rendering defect
test: repeat 80-scene on-device framebuffer matrix and inspect themed contact sheets
expecting: every relevant rendering remains inside safe bounds, preserves one copy of each semantic label, and matches its intended composition
next_action: none

## Symptoms

expected: every relevant keypad screen and theme has a polished composition, no overlap or clipping, and renders as intended
actual: deterministic captures show clipped menu copy and time values, overlapping empty-state geometry, duplicated feedback words, missing null markers, and rough or leaking Beacon geometry
errors: none reported
reproduction: build and upload current firmware, drive every reachable theme and screen state, capture each 128 by 128 framebuffer, and inspect the resulting contact sheets
started: current Phase 02.2 implementation review

## Eliminated

## Evidence

- timestamp: 2026-08-20T13:17:17+02:00
  checked: 80-scene on-device RGB565 rendering matrix generated through the bounded diagnostic capture seam
  found: four menu footers clip; two menu value columns clip; one empty-state label overlaps its glyph; Signal Edge and Ledger since fields reach past x=127; Ledger and Instrument repeat failure words; Ledger null markers disappear; Beacon radial bands form a bullseye and panel-4 hatching crosses the dial boundary
  implication: the defects are deterministic renderer geometry and copy-budget errors, not panel optics or USB transport

- timestamp: 2026-08-20T13:29:29+02:00
  checked: post-fix 80-scene device matrix, four final Instrument ring recaptures, and four live Herdr-backed panel captures
  found: menu copy and longest values fit; empty geometry is separated; terminal feedback and sync copy appear once; all time fields fit; Ledger N/A markers render; Beacon field and dial are contained; Instrument ring styles remain structurally distinct; live Signal Edge panels render current working, idle, empty, and Codex-unavailable states cleanly
  implication: the complete logical framebuffer surface now meets the rendering contract; physical brightness and viewing-angle properties remain outside framebuffer proof

- timestamp: 2026-08-20T13:29:29+02:00
  checked: selected-usb build/upload and native-agent-projection regression suite
  found: firmware build and hardware upload succeeded; 39 of 39 native renderer/projection tests passed, including the new no-duplicate feedback and sync-copy regression
  implication: the visual fixes compile for the real target and preserve projection, theme, menu, feedback, animation, settings, and LED contracts

## Resolution

root_cause: "Fixed-coordinate text placement did not budget the longest allowed values; UTF-8 menu/null glyphs exceeded the bitmap font contract; Signal Edge EMPTY layered text over its dash; Ledger and Instrument repeated feedback words; Beacon used visible solid rings and unclipped hatch lines; Instrument diagonal gap masks missed the ring."
fix: "Added deterministic on-device theme/scene capture controls, bounded and centered shared text geometry, ASCII menu and N/A copy, one-copy feedback/sync composition, separated Signal Edge empty geometry, dithered Beacon field and clipped dial hatch, and true dashed/dotted Instrument rings."
verification:
  device_matrix: { result: pass, captures: 80 }
  affected_final_recaptures: { result: pass, captures: 4 }
  live_panels: { result: pass, captures: 4 }
  selected_usb_build_upload: { result: pass }
  native_agent_projection: { result: pass, tests: 39 }
oracle_type: specified
files_changed: [".agents/skills/screen-capture-flow/SKILL.md", ".planning/phases/02.2-firmware-themes-led-bars-and-device-selection-menu/02.2-UI-SPEC.md", "firmware/src/app/agent_projection.cpp", "firmware/src/app/agent_projection.h", "firmware/src/main.cpp", "firmware/src/ui/theme_beacon.cpp", "firmware/src/ui/theme_common.h", "firmware/src/ui/theme_instrument.cpp", "firmware/src/ui/theme_ledger.cpp", "firmware/src/ui/theme_signal_edge.cpp", "test/test_agent_projection/stubs/TKeyboardS3Pro.h", "test/test_agent_projection/test_main.cpp", "tools/capture_panel.py"]
