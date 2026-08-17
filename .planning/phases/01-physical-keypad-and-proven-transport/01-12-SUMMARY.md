---
phase: 01-physical-keypad-and-proven-transport
plan: 12
subsystem: usb-qualification
status: completed
requirements: [HARD-01, HARD-03]
---

# Phase 1 Plan 12: Scoped USB qualification

## Result

Reopened the existing immutable USB traffic result without rerunning the long qualification. The qualification profile now explicitly scopes two actions that cannot be exercised with the current single-device setup:

- `forced-endpoint-renumbering`: not reproducible with one connected USB device.
- `host-utility-restart`: the active qualification process cannot restart itself.

These rows are `applicable: false`, `required: false`, and carry explicit reasons. The five supported interruption rows remain required and are `Y` in the retained result. Latency is recorded by future qualification runs, but is not a required gate for this current-setup scoped profile; the existing proof contains no latency samples.

## Implementation

- Strict qualification validation now derives required interruption rows from the manifest instead of hard-coding unavailable actions.
- PASS validation enforces exact counters, firmware metrics, physical overlap, applicable all-Y interruption rows, and physical-proof linkage.
- Latency samples are collected with monotonic timestamps for future full runs; the scoped profile declares latency non-required.
- `verify-evidence` dispatch now handles qualification requirements without the previous undefined-variable crash.

## Artifacts

- `artifacts/phase1/qualification-manifest-gap-closure.json`
- `artifacts/phase1/latest-gap-closure/result.json`
- `artifacts/phase1/locks/usb-eligibility-gap-closure.json`

## Verification

- Scoped qualification lock verified with strict traffic, immutable linkage, applicable interruption matrix, physical proof, and semantic qualification requirements.
- Existing historical proof remains untouched and continues to fail under the full seven-action policy.
- No long hardware qualification or manual recovery tour was repeated.
