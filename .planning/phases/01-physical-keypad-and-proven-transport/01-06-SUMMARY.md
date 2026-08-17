---
phase: 01-physical-keypad-and-proven-transport
plan: 06
subsystem: transport-testing
tags: [usb, qualification, evidence, metrics, recovery]

# Dependency graph
requires:
  - phase: 01-physical-keypad-and-proven-transport
    provides: frozen protocol envelope, exact pairing, and firmware proof metrics
provides:
  - Strict passing USB qualification on the exact paired keypad
  - Immutable result, traffic hash, manifest linkage, pointer, and USB eligibility lock
  - Complete interruption matrix with explicit unavailable reasons
affects: [01-08 selection and archive]

# Actuals (#2632)
actuals:
  tokens: 1800
  tasks: 2
  commits: 0

# Tech tracking
tech-stack:
  added: []
  patterns: [immutable qualification pointer resolution, strict traffic/resource verification]

key-files:
  created:
    - artifacts/phase1/latest/result.json
    - artifacts/phase1/locks/usb-eligibility.json
    - .planning/phases/01-physical-keypad-and-proven-transport/01-06-SUMMARY.md
  modified:
    - tools/phase1_bringup/src/phase1_bringup/qualification.py
    - tools/phase1_bringup/src/phase1_bringup/evidence.py
    - tools/phase1_bringup/src/phase1_bringup/__main__.py

key-decisions:
  - "USB is the qualified v1 transport: the exact paired device passed the frozen profile with strict counter equality and zero strict failures."
  - "The forced endpoint-renumbering scenario is explicitly unavailable because no secondary USB device exists; it is recorded as U with a reason, never inferred as pass."
  - "The host utility restart row is explicitly unavailable because restarting the active qualification process would terminate the run; it is recorded as U with a reason."
  - "Qualification results must include measured resource metrics and the frozen manifest hash before evidence linkage can pass."

patterns-established:
  - "Qualification pointers resolve once to concrete non-symlink paths and emit a hash-bound lock."
  - "Strict evidence verification reopens manifest, result, traffic, and interruption IDs rather than trusting mutable latest summaries."

requirements-completed: [HARD-01, HARD-03]

coverage:
  - id: D1
    description: "Exact paired USB transport passes the frozen qualification profile with 3,800 expected/sent/received/acknowledged frames and zero strict failures."
    requirement: HARD-03
    verification:
      - kind: integration
        ref: "verify-evidence artifacts/phase1/locks/usb-eligibility.json --require strict-traffic --require immutable-linkage --require complete-interruption-matrix"
        status: pass
    human_judgment: false
  - id: D2
    description: "All display, LED, brightness, key, and encoder preflight cues were visually confirmed by the operator."
    requirement: HARD-01
    verification: []
    human_judgment: true
    rationale: "Display and LED correctness cannot be established from serial acknowledgements; the operator confirmed the complete cue sweep."
  - id: D3
    description: "Recovery rows establish fresh exact-device sessions and record unavailable scenarios with explicit reasons."
    requirement: HARD-03
    verification: []
    human_judgment: true
    rationale: "The operator performed reset, flash/reset, same-port, different-port, and unplug/replug recovery; endpoint renumbering and utility restart were unavailable and reasoned."

# Metrics
duration: execution window
completed: 2026-08-16
status: complete
---

# Phase 1 Plan 6: Frozen USB Qualification Summary

**The paired LILYGO T-Keyboard S3 Pro passed the frozen USB qualification profile and produced a hash-validated eligibility lock for downstream selection.**

## Accomplishments

- Ran the real 30-minute product-shaped USB profile on the exact paired device.
- Confirmed visual preflight cues and machine-validated physical key/encoder interactions.
- Recorded 3,800 expected, sent, received, and acknowledged traffic frames.
- Recorded zero digest mismatches, duplicates, out-of-order frames, malformed frames, rejections, or watchdog resets.
- Captured resource metrics including heap, parser/queue high-water marks, display flush time, and key-poll gap.
- Executed the interruption matrix. Endpoint renumbering and host utility restart were preserved as explicit unavailable rows with reasons.
- Added measured metrics and manifest linkage to result artifacts; verified immutable result/traffic linkage.
- Resolved the concrete result pointer into `artifacts/phase1/locks/usb-eligibility.json` and verified strict traffic, immutable linkage, and complete interruption coverage.

## Evidence

- Result: `artifacts/phase1/20260816T190217Z-cc059b/result.json`
- Traffic: `artifacts/phase1/20260816T190217Z-cc059b/traffic.json`
- Pointer: `artifacts/phase1/latest/result.json`
- Lock: `artifacts/phase1/locks/usb-eligibility.json`
- Manifest: `artifacts/phase1/qualification-manifest.json`

## Verification

```text
tools/phase1_bringup/.venv/bin/python -m phase1_bringup verify-qualification artifacts/phase1/qualification-manifest.json artifacts/phase1/20260816T190217Z-cc059b/result.json --traffic artifacts/phase1/20260816T190217Z-cc059b/traffic.json

 tools/phase1_bringup/.venv/bin/python -m phase1_bringup verify-evidence artifacts/phase1/locks/usb-eligibility.json --require strict-traffic --require immutable-linkage --require complete-interruption-matrix
```

Both commands passed.

## Next Phase Readiness

USB is the selected v1 transport candidate. The conditional Wi-Fi fallback remains unnecessary because USB passed strict qualification. Plan 01-08 can consume the concrete USB eligibility lock for final selection/build/archive.

---
*Phase: 01-physical-keypad-and-proven-transport*
*Completed: 2026-08-16*
