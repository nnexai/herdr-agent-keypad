---
status: complete
quick_id: 261018-x6c
type: planning-only
created: 2026-10-19
---

# Rust runtime / Python diagnostics cleanup planning

## Deliverable

`261018-x6c-PLAN.md` is the implementation plan. Implementation has not started. No bridge source, firmware, installed plugin, configuration, or historical evidence was changed during this task.

## Findings and direction

- Production startup and actions already invoke the Rust executable directly.
- Delete the obsolete Python bridge only after detaching its qualification-tool consumers and freezing the existing Python-derived Rust test corpora, preserving their provenance.
- Keep screenshot capture and shared pairing/protocol/discovery/serial tools as Python developer diagnostics. Retain stdlib Python release/evidence utilities separately; removing the Python bridge does not mean removing Python from the repository.
- Replace the screenshot workflow's deleted launcher and obsolete lock namespace with the existing Rust authority lock, held by a tools-only runner.
- Fix Rust stop ordering before using that lock as the diagnostic handoff: source inspection shows authority is currently dropped and the reply sent before `close_boundaries()` closes USB.
- Preserve historical artifacts and phase records. Amend current requirements to describe the deliberately retired executable Python oracle and frozen behavioral corpus.

## Verification actually exercised

1. `tools/phase1_bringup/.venv/bin/python3 tools/capture_panel.py --help` succeeded and listed current panels, themes, scenes, levels, and phases.
2. A throwaway in-memory Python smoke loaded `tools/capture_panel.py` without adding the Python bridge to its import path. RGB565 red/green/blue inputs decoded to the exact RGB primaries and the P6 128×128 payload had the expected length.
3. Repository research mapped runtime, tooling, test-oracle, release/CI, and qualification consumers. A plan-checker review identified corrections for libtest filter syntax, state-dir discovery before stopping, descendant/lease cleanup, the release-Python exception, and current user-owned screenshot instructions. The plan was revised to address these, with targeted content verification by the parent. It also specifies interpreter invocation and describes the lock as cooperative exclusion, not authentication. No second checker PASS is claimed.

No serial device was opened. No tests/builds of Rust or firmware were run. No plugin action, capture on hardware, flash, or physical acceptance was performed. The plan's commands and device gates are future execution criteria, not passing evidence.

## Scope boundary

This quick task completes planning only. Phase 5 remains unplanned and unaccepted. Actual cleanup and real-device handoff/capture validation are not completed by this planning record.
