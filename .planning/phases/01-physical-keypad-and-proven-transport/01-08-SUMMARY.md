---
phase: 01-physical-keypad-and-proven-transport
plan: 08
subsystem: transport-selection
status: complete
tags: [usb, selection, firmware-composition, immutable-evidence, archive]

# Dependency graph
requires:
  - phase: 01-physical-keypad-and-proven-transport
    provides: strict USB qualification lock and retired Wi-Fi fallback
provides:
  - Immutable selected-usb decision bound to the exact qualification result
  - Selected USB firmware binary with no Wi-Fi source, object, or symbol
  - Secret-free Phase 1 archive marker bound to selection, build, manifest, result, and traffic hashes
affects: [phase-2 host bridge and device protocol]

# Actuals (#2632)
actuals:
  tokens: 9000
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns: [immutable selection lock, compile-time single-adapter composition, hash-bound archive marker]

key-files:
  created:
    - tools/phase1_bringup/ARCHIVED
    - .planning/phases/01-physical-keypad-and-proven-transport/01-08-SUMMARY.md
  modified:
    - platformio.ini
    - tools/phase1_bringup/src/phase1_bringup/__main__.py
    - tools/phase1_bringup/src/phase1_bringup/evidence.py

key-decisions:
  - "USB is selected for v1 because every frozen qualification gate passed on the exact paired device."
  - "The selected-usb PlatformIO environment is the default and explicitly excludes transport/wifi_tls.cpp."
  - "The final build and archive consume concrete hash-bound locks; mutable latest evidence is used only once by the resolver and never by selection, build, or archive verification."
  - "The long physical qualification was not repeated; Plan 01-06's immutable pass remains the acceptance evidence."

patterns-established:
  - "Selection reopens candidate, USB, manifest, result, traffic, and source hashes before writing a decision."
  - "Build proof records source, main, PlatformIO, binary, selection, and manifest hashes plus explicit unselected-adapter absence."
  - "Archive verification rejects mutable latest paths and secret-bearing fields."

requirements-completed: [HARD-01, HARD-03]

coverage:
  - id: D1
    description: "Selection resolves the qualification pointer once, validates the concrete immutable USB result, and emits selected-usb."
    requirement: HARD-03
    verification:
      - kind: integration
        ref: "verify-evidence artifacts/phase1/locks/selection.json --require immutable-selection --require complete-interruption-matrix"
        status: pass
    human_judgment: false
  - id: D2
    description: "The selected firmware compiles exactly UsbCdcLink while Wi-Fi source, object, and symbol remain absent."
    requirement: HARD-03
    verification:
      - kind: build
        ref: "build-selected --selection-lock artifacts/phase1/locks/selection.json"
        status: pass
      - kind: integration
        ref: "self-check --firmware-composition-lock artifacts/phase1/locks/final-build.json --exactly-one-adapter --unselected-source-object-symbol-absent"
        status: pass
    human_judgment: false
  - id: D3
    description: "The archive binds the final binary to the preserved exact-device physical and USB qualification evidence without mutable latest consumption."
    requirement: HARD-01
    verification:
      - kind: integration
        ref: "verify-evidence tools/phase1_bringup/ARCHIVED --require archived-source --require exact-manifest-hash --require immutable-linkage --require no-secret-output"
        status: pass
    human_judgment: false

# Metrics
duration: execution window
completed: 2026-08-16
---

# Phase 1 Plan 8: Selected USB Build and Archive Summary

**The exact paired keypad's strict USB pass now drives one immutable `selected-usb` decision, one USB-only firmware binary, and one hash-bound Phase 1 archive marker.**

## Accomplishments

- Added selection commands and verification for exact candidate, USB eligibility, manifest, result, traffic, and adapter-source hashes.
- Resolved `artifacts/phase1/latest/result.json` once into `artifacts/phase1/locks/selection-candidate.json`; all dependent operations consume concrete locks.
- Emitted `artifacts/phase1/locks/selection.json` with the frozen rationale: `USB selected for v1: every frozen qualification gate passed.`
- Renamed the firmware environment to `selected-usb`, made it the default, and explicitly excluded `transport/wifi_tls.cpp`.
- Built `.pio/build/selected-usb/firmware.bin`; binary SHA-256 is `280e8250b733abd0f534fab89e9578d2cd1a7b51b862e7451a8f3007ca82dbcb`.
- Verified the build contains no Wi-Fi source, object, or symbol and records the composition in `artifacts/phase1/locks/final-build.json`.
- Created and verified `tools/phase1_bringup/ARCHIVED`, bound to the selected build and Plan 01-06 qualification lock.
- Did not repeat the 30-minute hardware qualification.

## Commits

| Task | Commit | Description |
|---|---|---|
| Task 1 | `eaf1b31` | Select from exact frozen hash-validated qualification artifacts |
| Task 2 | `5e56a4a` | Compose, prove, and archive exactly the selected adapter |

## Evidence

- Selection candidate: `artifacts/phase1/locks/selection-candidate.json`
- Selection: `artifacts/phase1/locks/selection.json`
- Final build: `artifacts/phase1/locks/final-build.json`
- Qualification: `artifacts/phase1/locks/usb-eligibility.json`
- Archive: `tools/phase1_bringup/ARCHIVED`
- Selected binary: `.pio/build/selected-usb/firmware.bin`

## Verification

- Selection exact-path/hash/asymmetry self-check passed.
- Immutable selection verification passed.
- `selected-usb` PlatformIO build passed.
- Exactly-one-adapter and unselected-source/object/symbol absence check passed.
- Strict traffic, complete interruption matrix, and immutable qualification linkage passed.
- Archive source, exact manifest hash, immutable linkage, and no-secret-output verification passed.

## Deviations from Plan

- `selected-wifi` was not defined or referenced. Plan 01-07 was correctly retired after strict USB success, and its locked assumption prohibits opening or creating absent Wi-Fi source on the selected USB branch.
- No additional physical run was performed. The plan explicitly requires reuse of the one-time Plan 01-06 qualification.

## Self-Check: PASSED

- Both tasks completed and were committed atomically.
- `01-08-SUMMARY.md` records concrete commits and evidence.
- Selection, build, qualification, and archive validators all pass.
- The final firmware environment contains only the USB adapter.
- No actionable work remains in Phase 1 execution.

---
*Phase: 01-physical-keypad-and-proven-transport*
*Completed: 2026-08-16*
