---
status: resolved
trigger: "Pedantically refine the attached keypad against the accepted design document. Signal Edge Codex and settings screens look broken, Instrument Codex looks broken, Signal Edge feedback bands do not align with the side rail, theme switching leaves background artifacts, some empty dashes are off-center, Beacon PENDING looks strange, and filled symbol treatment does not match the design."
created: 2026-08-20T13:46:25+02:00
updated: 2026-08-20T14:00:07+02:00
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "multiple deterministic composition mismatches plus a confirmed theme-change repaint gap"
  confirming_evidence:
    - "existing on-device captures show unlabeled Signal Edge gauge boxes, a menu footer crossing the rail, circular Instrument usage placeholders, and a static undersized Beacon pending ring"
    - "refreshMenuPresentation changes the active renderer but flushes only panel 4, leaving panels 1-3 in the old theme"
    - "Signal Edge empty dash is centered in its content column at x72 rather than the physical panel at x64"
    - "the design document uses stacked linear usage gauges and filled working triangles"
  falsification_test: "passed - 44 native regressions, final target build/upload, 80-scene matrix, two final-touch recaptures, and four live panels all satisfy the corrected contract"
  fix_rationale: "full-width Signal Edge feedback, centered empty geometry, bounded menu rows, design-shaped usage placeholders, filled working symbols, animated Beacon pending takeover, and complete theme repaint remove the confirmed defects"
  blind_spots: "framebuffer capture cannot prove panel optics; direct theme-transition flush ordering will be covered by native push logs"
  candidate_causes:
    - "hardcoded placeholder panel-4 compositions ignore accepted theme geometry"
    - "fixed menu rail/footer geometry consumes or crosses content"
    - "feedback band starts at a fixed x16 while visual rail widths vary"
    - "confirmed theme changes lack an all-agent-panel repaint"
    - "Beacon pending redraws identical static geometry"
  and_gate: "yes - source geometry and repaint ownership independently contribute visible defects"
bug_class: deterministic rendering and transition defects
test: targeted theme geometry logs plus affected on-device framebuffer scenes
expecting: design-faithful, filled and aligned compositions with complete panel repaint on confirmed theme changes
next_action: none

## Symptoms

expected: every affected screen matches the accepted design direction, uses the full 128 by 128 panel cleanly, and switches themes without stale pixels
actual: user reports broken Signal Edge and Instrument usage screens, broken Signal Edge menu and feedback alignment, stale background artifacts on theme change, off-center empty dashes, and strange Beacon pending/symbol rendering
errors: none
reproduction: select affected themes and scenes on the attached keypad, including a confirmed theme change and pending feedback
started: observed on the final Phase 02.2 polish firmware

## Eliminated

## Evidence


- timestamp: 2026-08-20T13:49:58+02:00
  checked: native-agent-projection targeted polish regressions before source fixes
  found: four new tests failed on Signal Edge geometry, Signal/Instrument usage geometry, filled working symbols, and Beacon pending takeover while the existing 39 tests passed
  implication: the feedback loop is red-capable and isolates the reported renderer defects from existing projection, settings, animation, and LED behavior

- timestamp: 2026-08-20T13:49:58+02:00
  checked: refreshMenuPresentation and all theme compose entry points
  found: each composer clears the full sprite, but confirmed theme changes flush only panel 4; agent panels keep prior-theme pixels until later data or animation causes repaint
  implication: background artifacts are stale physical panel contents caused by missing repaint ownership, not incomplete background clears


- timestamp: 2026-08-20T14:00:07+02:00
  checked: native-agent-projection regressions after fixes
  found: all 44 tests passed, including full-width Signal feedback, centered empty dash, Signal/Instrument usage geometry, filled working symbols in all themes, Beacon pending takeover, and three-panel theme redraw ordering
  implication: each deterministic defect is locked to its renderer or repaint seam

- timestamp: 2026-08-20T14:00:07+02:00
  checked: final selected-usb build and upload on the attached ESP32-S3 keypad
  found: build and hardware upload succeeded
  implication: the corrected renderers are running on the real target

- timestamp: 2026-08-20T14:00:07+02:00
  checked: complete 80-scene on-device RGB565 matrix, two final Signal recaptures, and four live Herdr-backed panels
  found: affected Codex screens use labeled theme-specific gauges; Signal menu and feedback bands are bounded and aligned; empty dashes are centered; Beacon pending has a large phase-changing spinner with one reason line; working triangles are filled; no scene shows confirmed overlap or clipping
  implication: logical device pixels match the accepted design direction across every theme and relevant state

## Resolution

root_cause: "Placeholder Codex renderers ignored the accepted usage geometry; Signal menu and feedback used incompatible fixed rails/insets; Signal empty centered within its content column rather than the panel; working triangles were outlines; Beacon pending redrew an undersized static ring; confirmed theme changes repainted only panel 4."
fix: "Rebuilt Signal and Instrument usage screens with labeled N/A gauges, redesigned Signal menu and full-width feedback vehicle, centered empty geometry, filled all working triangles, added a phase-changing 44 px Beacon pending takeover and corrected field/fence layering, and added a projection-level three-panel repaint on confirmed theme changes."
verification:
  pre_fix_regressions: { result: red, failed: 4, existing_passed: 39 }
  native_agent_projection: { result: pass, tests: 44 }
  selected_usb_build_upload: { result: pass }
  device_matrix: { result: pass, captures: 80 }
  final_touch_recaptures: { result: pass, captures: 2 }
  live_panels: { result: pass, captures: 4 }
oracle_type: specified
files_changed: [".planning/phases/02.2-firmware-themes-led-bars-and-device-selection-menu/02.2-UI-SPEC.md", "firmware/src/app/agent_projection.cpp", "firmware/src/app/agent_projection.h", "firmware/src/main.cpp", "firmware/src/ui/theme_beacon.cpp", "firmware/src/ui/theme_instrument.cpp", "firmware/src/ui/theme_ledger.cpp", "firmware/src/ui/theme_signal_edge.cpp", "test/test_agent_projection/stubs/TKeyboardS3Pro.h", "test/test_agent_projection/test_main.cpp"]
