---
phase: 01-physical-keypad-and-proven-transport
plan: 13
subsystem: selection-build-archive
status: completed
requirements: [HARD-01, HARD-03]
---

# Phase 1 Plan 13: Scoped selection, build, and archive

## Result

Generated and independently reopened the selected USB decision, selected-build composition, and complete Phase 1 archive marker from the scoped qualification lineage. USB is the only selected transport; no Wi-Fi adapter, credentials, provisioning, or fallback branch was introduced.
## Artifacts

- `artifacts/phase1/locks/selection-candidate-gap-closure.json`
- `artifacts/phase1/locks/selection-gap-closure.json`
- `artifacts/phase1/locks/final-build-gap-closure.json`
- `tools/phase1_bringup/ARCHIVED`

## Verification

The following all passed:

- Scoped qualification lock: strict traffic, immutable linkage, applicable interruption matrix, physical proof, semantic qualification.
- Selection lock: immutable selection, exact manifest hash, immutable linkage, applicable interruption matrix.
- Final build lock: immutable selection, exactly one USB adapter, qualified binary lineage, absence of unselected adapter source/object/symbol.
- Archive marker: archived source, exact manifest hash, immutable linkage, no-secret output, exactly one adapter, unselected adapter absence.

The selected USB firmware build completed successfully with the pinned PlatformIO/pioarduino environment.
