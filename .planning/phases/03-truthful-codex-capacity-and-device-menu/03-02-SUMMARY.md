---
phase: 03-truthful-codex-capacity-and-device-menu
plan: 02
subsystem: host-synchronization
tags: [codex, sparse-merge, freshness, diagnostics, projection, focus-safety]

requires:
  - phase: 03-01
    provides: bounded Codex app-server collector, typed outcomes, top-level-only normalization, and PermanentBridge tracer path
provides:
  - Full-response Codex baseline with presence-aware sparse merge, account invalidation, exact poll/stale clocks, and coalesced refetch
  - Redacted rateLimitsByLimitId manifest with bounded counts and unique hashed key prefixes; only documented top-level rateLimits supplies capacity
  - Immutable projection health fields and PermanentBridge joins for independent Herdr, Codex, sync, and link/session clocks
  - Codex-only publication path that preserves agent bytes, bindings, pending focus, and focus authorization semantics
affects: [03-03, 03-04, Codex tile, health diagnostics, host synchronization]

actuals:
  tokens: 11314
  tasks: 2
  commits: 6

tech-stack:
  added: []
  patterns:
    - Full reads establish the sole known baseline; sparse notifications merge transactionally only after a known baseline
    - Provider failures retain bounded cached values behind an independent source state and observation age
    - Complete immutable publications join independent source health without changing generation-bound agent identities

key-files:
  created: []
  modified:
    - host/herdr_keypad/src/herdr_keypad/codex.py
    - host/herdr_keypad/src/herdr_keypad/projection.py
    - host/herdr_keypad/src/herdr_keypad/bridge.py
    - host/herdr_keypad/tests/test_codex.py
    - host/herdr_keypad/tests/test_projection.py
    - host/herdr_keypad/tests/test_integration.py

key-decisions:
  - "A valid documented top-level rateLimits object is the only selectable capacity source; map-only, absent, malformed, and unusable shapes remain unavailable with E-2401 and internal bucket_unavailable."
  - "Sparse metadata nulls preserve the last documented metadata value, while explicit null primary/secondary windows clear only that usage field; omitted fields remain unchanged."
  - "Codex-only refreshes reuse the complete Herdr generation and preserve pending focus intake rather than fencing an unchanged binding."

patterns-established:
  - "Bounded manifest: hash opaque map keys before discarding upstream maps, deduplicate prefixes, cap count and prefixes, and never retain raw keys or values."
  - "Independent clocks: Herdr observation, Codex observation, complete sync publication, and USB link health are represented separately and joined only at publication."

requirements-completed: [CODEX-03, CODEX-04, SYNC-03, SAFE-01]

coverage:
  - id: D1
    description: "Codex full normalization and bounded rateLimitsByLimitId manifest"
    requirement: CODEX-03
    verification:
      - kind: unit
        ref: "host.herdr_keypad.tests.test_codex"
        status: pass
    human_judgment: false
  - id: D2
    description: "Known-full sparse merge, exact freshness edges, account clear, and recovery state machine"
    requirement: CODEX-04
    verification:
      - kind: unit
        ref: "host.herdr_keypad.tests.test_codex.CodexCollectorTests"
        status: pass
    human_judgment: false
  - id: D3
    description: "Independent Herdr/Codex/sync/link health joined through PermanentBridge without focus mutation"
    requirement: SYNC-03
    verification:
      - kind: integration
        ref: "host.herdr_keypad.tests.test_projection and host.herdr_keypad.tests.test_integration"
        status: pass
    human_judgment: false
  - id: D4
    description: "Credential-safe Codex diagnostics and unchanged host-owned focus authorization"
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: "PluginLifecycleTests.test_codex_only_refresh_preserves_agents_bindings_and_focus_allowlist"
        status: pass
    human_judgment: false

# Metrics
duration: 16min
completed: 2026-08-20
status: complete
---

# Phase 03 Plan 02: Truthful Codex cache and independent host clocks summary

**Known-full Codex capacity now merges sparse updates truthfully and publishes through independent Herdr, Codex, synchronization, and USB-link clocks without disturbing direct focus bindings.**

## Performance

- **Duration:** approximately 16 min of implementation and targeted verification
- **Started:** 2026-08-20T21:30:00Z
- **Completed:** 2026-08-20T21:46:26Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added a single in-memory Codex cache: complete top-level reads establish the baseline, sparse notifications merge only known fields, omitted fields preserve values, explicit null windows become unavailable, metadata nulls do not clear documented values, and supplied zero remains zero.
- Implemented exact 300-second polling and 900-second stale edges with injected clocks, account/auth invalidation, bounded coalesced refetch requests, process-restart recovery, structured auth evidence, and fixed allowlisted error codes.
- Closed all six full-response shape classes. `rateLimitsByLimitId` is observation-only: raw keys and bucket values are discarded after bounded unique SHA-256 prefixes are produced; no map key is selected.
- Extended immutable projection health and PermanentBridge publication with independent Herdr, Codex, sync, and link/session ages and states. Codex-only refreshes preserve agent entries, opaque identities, generation bindings, pending focus, and focus-only authorization.
- Added deterministic fake-clock, scripted-JSONL, redaction, sparse-transaction, account-clear, source-independence, and focus-invariance coverage.

## Task Commits

Each task was committed atomically, with TDD red/green commits and bounded corrective fixes:

1. **Task 1: Complete the known-full sparse merge and recovery state machine** - `59348f5` (test), `00ed822` (feat), `144f24c` (fix)
2. **Task 2: Join independent source clocks without changing focus state** - `d3e964a` (test), `1690e29` (feat), `d505f74` (fix)

## Files Created/Modified

- `host/herdr_keypad/src/herdr_keypad/codex.py` - full baseline, sparse merge, bounded manifest, freshness, refetch, account clear, and classification state machine.
- `host/herdr_keypad/src/herdr_keypad/projection.py` - immutable bounded independent health fields alongside Herdr entries and generation identity.
- `host/herdr_keypad/src/herdr_keypad/bridge.py` - independent-clock join, Codex refresh/sparse/account hooks, link state, and focus-safe Codex-only publication.
- `host/herdr_keypad/tests/test_codex.py` - fake-clock and sparse/full state-machine coverage.
- `host/herdr_keypad/tests/test_projection.py` - immutable health default coverage.
- `host/herdr_keypad/tests/test_integration.py` - independent-source and focus-invariance integration coverage.

## Decisions Made

- Only the documented top-level `rateLimits` object can provide capacity. A map-only or unusable shape yields no percentages, reset, or reached claim and uses internal `bucket_unavailable` with device code `E-2401`.
- Sparse notifications are transactional and baseline-gated. An invalid or ambiguous event changes neither cache nor age; accepted events update observation age and set one coalesced immediate full refetch.
- Account/auth changes clear all capacity and observation timestamps without retaining account identity. Authentication-required is emitted only for structured auth evidence; process, JSONL, request, and timeout failures remain Codex offline.
- A Codex-only publication does not clear pending focus or alter the Herdr generation because no agent identity or authorization fact changed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserve a known baseline when an unusable full response arrives**
- **Found during:** Task 1 verification
- **Issue:** An unusable map-only/full shape could discard a previously complete cache, violating the stale/offline veil requirement.
- **Fix:** Preserve the prior normalized cache while classifying the new shape unavailable; only an initial unusable response has no baseline.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/codex.py`, `host/herdr_keypad/tests/test_codex.py`
- **Verification:** Codex state-machine suite passed, including map-only/unusable normalization and account-clear cases.
- **Committed in:** `144f24c`

**2. [Rule 1 - Bug] Prevent Codex-only refresh from fencing unchanged focus intake**
- **Found during:** Task 2 integration verification
- **Issue:** The existing complete-publication helper cleared pending USB focus on every publication, including same-generation Codex-only updates.
- **Fix:** Added an explicit same-generation preserve-focus publication path used only by Codex refresh, sparse merge, and account-change updates.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/bridge.py`, `host/herdr_keypad/tests/test_integration.py`
- **Verification:** Integration invariant confirms byte-identical agents, binding, and pending focus across Codex-only current/auth transitions.
- **Committed in:** `d505f74`

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes directly protected the required stale-data and focus-safety semantics. No second cache, bridge loop, parser, thread, or authority was introduced.

## Issues Encountered

- Existing generated build and Python cache artifacts were already modified in the working tree; they were preserved and excluded from all plan commits.
- The targeted suite emits the pre-existing bounded-smoke diagnostic text while testing rejection behavior; the tests pass and no project-wide validation was run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The host now exposes deterministic full/sparse Codex state and independent health metadata for the next projection/wire and device presentation work.
- The existing CodexCollector/PermanentBridge/projection path remains the only authority and transport path.

---
*Phase: 03-truthful-codex-capacity-and-device-menu*
*Completed: 2026-08-20*

## Self-Check: PASSED

- Targeted host tests passed: 46 tests across `test_codex`, `test_projection`, and `test_integration`.
- Task commits `59348f5`, `00ed822`, `144f24c`, `d3e964a`, `1690e29`, and `d505f74` exist.
- All six plan-listed source/test files are present and targeted-file status is clean before planning metadata updates.
