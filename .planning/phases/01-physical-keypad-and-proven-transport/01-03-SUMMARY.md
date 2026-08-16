---
phase: 01-physical-keypad-and-proven-transport
plan: 03
subsystem: physical-bringup
tags: [python, usb-cdc, t-keyboard-s3-pro, physical-map, immutable-evidence, terminal-ui]

# Dependency graph
requires:
  - phase: 01-physical-keypad-and-proven-transport
    provides: 01-02 complete Pro-only stimulus surface, fixed renderer, and explicit delivered-unit proof boundary
provides:
  - Exact guided Identify-through-Selection host sequence with bounded 80x24 UI behavior
  - Machine-only batch observations and explicit step/run-bound physical confirmation records
  - Hash-addressed delivered-unit physical map with preserved failure and replacement history
affects: [01-04 pairing and recovery, 01-05 protocol semantics, 01-06 USB qualification, 01-08 final archive]

# Actuals (#2632)
actuals:
  tokens: 29615
  tasks: 2
  commits: 19

# Tech tracking
tech-stack:
  added: []
  patterns: [pinned venv module invocation, step/run-bound confirmation, immutable hash-addressed evidence, bounded 80x24 terminal UI]

key-files:
  created:
    - tools/phase1_bringup/src/phase1_bringup/guide.py
    - tools/phase1_bringup/src/phase1_bringup/protocol.py
    - tools/phase1_bringup/src/phase1_bringup/ui.py
  modified:
    - tools/phase1_bringup/src/phase1_bringup/__main__.py
    - tools/phase1_bringup/src/phase1_bringup/evidence.py
    - firmware/src/main.cpp
    - firmware/src/ui/bringup_renderer.h

decisions:
  - "Physical input naming is KEY-1..KEY-4 with raw library indices 0..3; encoder click is ENCODER-CLICK at raw index 4 and is an observation-only, BOOT0-safe input."
  - "The latest machine-only run is evidence input, never physical PASS; each gate requires an explicit Y tied to the visible stable step and source run."
  - "The centered bounded renderer fix (1b95a5f) is part of the accepted proof; prior failed and surprising runs remain immutable rather than being overwritten."
  - "Pair, Recover, Traffic, and Selection remain visibly not started; D-04 archival is deferred to Plan 01-08."

key-decisions:
  - "Physical input naming is KEY-1..KEY-4 with raw library indices 0..3; encoder click is ENCODER-CLICK at raw index 4 and is an observation-only, BOOT0-safe input."
  - "The latest machine-only run is evidence input, never physical PASS; each gate requires an explicit Y tied to the visible stable step and source run."
  - "The centered bounded renderer fix (1b95a5f) is part of the accepted proof; prior failed and surprising runs remain immutable rather than being overwritten."
  - "Pair, Recover, Traffic, and Selection remain visibly not started; D-04 archival is deferred to Plan 01-08."

patterns-established:
  - "GuidedRun exposes one stable visible step at a time and rejects Enter or unbound confirmation as physical proof."
  - "Machine observations retain literal unavailable values and step/run IDs; typed replacement links old and new records instead of mutating history."
  - "The host UI is invoked only through tools/phase1_bringup/.venv/bin/python -m phase1_bringup."

requirements-completed: [HARD-01, HARD-03]

coverage:
  - id: D1
    description: "Production guided host workflow presents the fixed Identify, Displays, Keys, Encoder, LEDs, Brightness, Reboot, Pair, Recover, Traffic, Selection order with bounded 80x24 UI and safe confirmation behavior."
    requirement: HARD-03
    verification:
      - kind: automated_ui
        ref: "tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --ui --guided-order"
        status: pass
      - kind: other
        ref: "tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --evidence-schema --physical-confirmation"
        status: pass
    human_judgment: false
  - id: D2
    description: "Delivered-unit physical map records machine facts plus explicit human confirmation for Identify through Reboot while preserving unavailable, failed, and replaced history."
    requirement: HARD-01
    verification:
      - kind: other
        ref: "tools/phase1_bringup/.venv/bin/python -m phase1_bringup verify-evidence artifacts/phase1/confirmed-20260816T133300Z-f81cd8-e6c1b4 --require physical-map"
        status: pass
      - kind: other
        ref: "sha256sum -c SHA256SUMS for latest, prior machine, prior failed, and prior Displays=N artifacts"
        status: pass
      - kind: manual_procedural
        ref: "confirm-batch ... --groups IDENTIFY=Y,DISPLAYS=Y,KEYS=Y,ENCODER=Y,LEDS=Y,BRIGHTNESS=Y,REBOOT=Y"
        status: pass
    human_judgment: true
    rationale: "Display orientation, physical key identity, encoder behavior, LED visibility, brightness, and reboot behavior require observation of the delivered unit; machine acknowledgements cannot substitute for the operator's explicit Y responses."

# Metrics
duration: closeout
completed: 2026-08-16
status: complete
---

# Phase 1 Plan 3: Physical Keypad and Proven Transport Summary

**The production tracer now records a complete, hash-addressed delivered-unit physical map from machine evidence plus explicit human confirmation, with the corrected centered renderer and immutable failure history preserved.**

## Performance

- **Duration:** Closeout of the already-executed implementation and physical checkpoint
- **Started:** 2026-08-16T13:12:00Z (first preserved Plan 01-03 runtime artifact)
- **Completed:** 2026-08-16
- **Tasks:** 2 plan tasks completed
- **Files modified by the plan:** 7 source files; this summary adds one planning artifact

## Accomplishments

- Expanded the production tracer into the fixed eleven-gate guided order: Identify, Displays, Keys, Encoder, LEDs, Brightness, Reboot, Pair, Recover, Traffic, Selection. The host UI keeps one visible stable step, bounded copy, elapsed bounded-operation state, and inactive panels at WAIT.
- Added machine-only capture and explicit `confirm-batch` physical confirmation. The latest machine run `artifacts/phase1/20260816T133300Z-f81cd8` completed all seven physical gates with all fourteen LED stimuli acknowledged; the confirmed run `artifacts/phase1/confirmed-20260816T133300Z-f81cd8-e6c1b4` records Y for every gate and `physical_status: pass` for all thirty source observations.
- Established the physical naming decision: physical `KEY-1` through `KEY-4` map to raw indices `0` through `3`; `ENCODER-CLICK` maps to raw index `4` and is a click observation only, explicitly BOOT0-safe. The confirmed evidence retains key events for all five raw inputs.
- Accepted the renderer centering correction in `1b95a5f`; the user's earlier clipping caveat is resolved by the later physical confirmation. The older failed machine-only run (`20260816T131225Z-f89a7b`, invalid stimulus during the LED sequence) and the earlier `Displays=N` confirmed run (`confirmed-20260816T132346Z-3aebb2-d6bc76`) remain present, hash-verified, and are not overwritten.
- Kept dependent gates Pair, Recover, Traffic, and Selection visibly not started. D-04 archival remains a final Plan 01-08 action, and no later plan was started here.

## Task Commits

The two plan tasks were implemented through the following atomic commits (including corrective commits discovered during proof):

1. **Task 1: Expand the production tracer into the exact guided host UI** — `510a3af`, `46019b8`, `19d92c8`, `5d9d426`, `03f737f`, `3a009da`, `df8c9d0`.
2. **Task 2: Record and verify the complete human-confirmed physical map** — `34a3d22`, `6bffb4a`, `30a2b05`, `a4d9434`, `c7716d1`, `e9ef034`, `4449179`, `d2d729a`, `0bd0685`, `c3cc002`, `1b95a5f`.

The closeout metadata commit is created after this summary and the GSD STATE/ROADMAP tracking updates.

## Files Created/Modified

- `tools/phase1_bringup/src/phase1_bringup/guide.py` - Eleven-gate guided sequence, stable-step checks, raw key validation, and BOOT0-safe encoder-click semantics.
- `tools/phase1_bringup/src/phase1_bringup/protocol.py` - Production tracer protocol/session boundary used by the guided run.
- `tools/phase1_bringup/src/phase1_bringup/ui.py` - Bounded terminal UI with exact step/result screens and 80x24-safe behavior.
- `tools/phase1_bringup/src/phase1_bringup/__main__.py` - Self-check, machine-only, batch-confirm, and evidence-verification command surfaces.
- `tools/phase1_bringup/src/phase1_bringup/evidence.py` - Atomic machine/human rows, unavailable sentinels, linked replacements, finalization, and hash/schema verification.
- `firmware/src/main.cpp` - Physical stimulus naming and observation-only encoder-click mapping.
- `firmware/src/ui/bringup_renderer.h` - Fixed bounded renderer with centered payloads and one active panel.

## Decisions Made

- Machine acknowledgements alone never produce physical PASS. The accepted run proves every delivered-unit gate through a stable-step Y response tied to the source run.
- `KEY-1..KEY-4` are the physical labels even though the board library reports raw indices `0..3`; encoder click is raw index `4`, not a reset/BOOT0 action.
- The renderer's centered bounded payloads are required for the accepted physical proof. Historical failures, surprising observations, and replacement lineage remain immutable evidence.
- This closeout does not claim exact Python 3.11 reproducibility: `tools/phase1_bringup/.venv` is Python 3.14.7 and `python3.11` is unavailable. The venv satisfies the declared `>=3.11` floor, but exact 3.11 remains an explicit environment deviation.

## Deviations from Plan

### Environment deviation

**1. Exact Python 3.11 remains unavailable**
- **Found during:** closeout verification
- **Issue:** The declared exact Python 3.11 reproducibility environment is not installed.
- **Handling:** Verification used the project venv's Python 3.14.7, which satisfies the declared `>=3.11` floor; this does not mark exact 3.11 reproducibility as resolved.
- **Impact:** No source or evidence scope change; exact 3.11 remains an open reproducibility concern for later tracking.

### Auto-fixed Issues

**2. [Rule 1 - Bug] Corrected the physical key and encoder-click mapping**
- **Found during:** Task 2 machine/physical proof
- **Issue:** Earlier batch evidence exposed zero-based `KEY-0..KEY-4` naming and ambiguous encoder-click semantics.
- **Fix:** Renamed the operator-facing rows to `KEY-1..KEY-4`, retained raw indices `0..3`, and made encoder click raw index `4` an observation-only BOOT0-safe event.
- **Files modified:** `tools/phase1_bringup/src/phase1_bringup/guide.py`, `tools/phase1_bringup/src/phase1_bringup/__main__.py`, `firmware/src/main.cpp`
- **Verification:** Focused batch key-event self-check and confirmed artifact show raw indices `0,1,2,3,4`.
- **Committed in:** `c3cc002`

**3. [Rule 1 - Bug] Corrected the bounded renderer centering after physical review**
- **Found during:** delivered-unit visual proof
- **Issue:** The earlier renderer left large payloads clipped or insufficiently centered.
- **Fix:** Centered bounded bring-up payloads while preserving the fixed 80x24/safe-inset contract.
- **Files modified:** `firmware/src/ui/bringup_renderer.h`, `firmware/src/main.cpp`
- **Verification:** Renderer contract self-check passed and later physical confirmation passed all seven batch gates.
- **Committed in:** `1b95a5f`

**4. [Rule 1 - Bug] Expanded LED stimulus handling to the complete fourteen-LED range**
- **Found during:** machine-only batch proof
- **Issue:** The first preserved machine-only run stopped at an invalid stimulus during the LED sequence.
- **Fix:** Accepted and recorded LED-0 through LED-13 in the bounded stimulus surface; preserved the failed run as immutable history.
- **Files modified:** `tools/phase1_bringup/src/phase1_bringup/__main__.py`, firmware stimulus implementation
- **Verification:** Latest machine-only artifact records all fourteen LED acknowledgements; SHA-256 and evidence verification pass.
- **Committed in:** `0bd0685`

**5. [Rule 1 - Tracking artifact bug] Corrected phase labels added by state decision helper**
- **Found during:** GSD state update
- **Issue:** `state.add-decision` emitted the supplied `[Phase 1]` text under an outer `[Phase ?]` prefix.
- **Fix:** Replaced the three malformed decision rows with canonical `[Phase 1]` entries.
- **Files modified:** `.planning/STATE.md`
- **Verification:** STATE.md decisions now carry exactly one Phase 1 label.
- **Committed in:** closeout metadata commit

**Total deviations:** 4 auto-fixed correctness/tracking issues, plus 1 documented environment deviation. **Impact:** Corrections were required to make the delivered-unit proof and tracking truthful and auditable; no later-plan scope was started and no historical artifact was replaced.

## Issues Encountered

- The initial machine-only artifact was intentionally retained as a failed run rather than rewritten after the LED-range fix.
- The earlier centered-renderer physical run retained `Displays=N`; the corrected renderer was flashed and confirmed in a new run. Both histories remain hash-verified.
- Exact Python 3.11 was unavailable; no claim of exact 3.11 reproducibility is made.

## Verification Evidence

Narrow post-closeout checks passed without hardware activity or a broad suite:

- `tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --ui --guided-order` — passed bounded UI and fixed guided order.
- `tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --evidence-schema --physical-confirmation` — passed machine/human field, unavailable, linked-replacement, and ACK-rejection contracts.
- `tools/phase1_bringup/.venv/bin/python -m phase1_bringup verify-evidence` — passed for latest confirmed, latest machine-only, prior `Displays=N`, and prior failed artifacts; latest confirmed also passed `--require physical-map`.
- `sha256sum -c SHA256SUMS` — passed for all four preserved artifacts (`manifest.json: OK`, `result.json: OK` each).
- Hardware flash and the physical `confirm-batch` run were completed before closeout; no hardware run was started for this closeout.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 01-03 is complete with the corrected physical proof and immutable evidence lineage.
- Plan 01-04 may begin pairing/recovery work from the confirmed physical map, but Pair, Recover, Traffic, and Selection are intentionally not started in this plan.
- Plan 01-08 remains responsible for D-04 archival after the transport plans establish the final selected transport and complete proof.

---
*Phase: 01-physical-keypad-and-proven-transport*
*Completed: 2026-08-16*

## Self-Check: PASSED

- Summary file created and contains required frontmatter, coverage, deviations, exact Python 3.14 deviation, and preserved-artifact references.
- Focused UI, evidence-schema, verifier, and SHA-256 checks passed.
- No hardware run, broad suite, later plan, or artifact overwrite was performed during closeout.
