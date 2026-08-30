---
phase: 04-production-rust-host-bridge
plan: "03"
subsystem: native-host-bridge
tags: [rust, serde, protocol, projection, focus, parity]

# Dependency graph
requires:
  - phase: 04-production-rust-host-bridge
    provides: "Locked native boundary contracts and exporter-independent protocol/projection-focus fixtures from Plans 01-02."
provides:
  - "Strict bounded v2 protocol codec with duplicate/nesting/closed-field/digest/session admission."
  - "Portable fixed-three-slot installed-inbox projection with material revision and stale/offline fencing."
  - "Exact focus authorization policy with immutable identity revalidation and one unfocused acknowledgement retry."
affects: [04-07, rust-host-bridge, protocol, projection, focus]

# Actuals (#2632)
# 89701 changed-file/patch bytes over the owned implementation and tests / 4.
actuals:
  tokens: 22426
  tasks: 2
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bounded serde_json preflight visitor for duplicate-member and nesting rejection before typed dispatch."
    - "Canonical sorted-key payload JSON with FNV-1a64 compatibility digest and closed four-frame enum."
    - "Installed literal rank ordering, fixed slot arrays, and material-equality revision stabilization."
    - "Pure focus port exposing only complete agent reads and exact agent.focus writes."

key-files:
  created:
    - host/herdr_keypad/native/src/protocol/v2.rs
    - host/herdr_keypad/native/src/core/model.rs
    - host/herdr_keypad/native/src/core/projection.rs
    - host/herdr_keypad/native/src/core/focus.rs
    - host/herdr_keypad/native/tests/protocol_parity.rs
    - host/herdr_keypad/native/tests/projection_focus_parity.rs
  modified: []

key-decisions:
  - "Keep Plan 03 modules self-contained and unregistered; Plan 07 owns root exports, module registries, and integration wiring."
  - "Use typed fixed arrays for the three agent slots and a fixed 16-frame ProtocolSession queue; reset clears all sequence and pending authority."
  - "Keep richer projection/focus identity values separate from the existing bootstrap root declarations until Plan 07 performs the shared integration cutover."

patterns-established:
  - "Protocol admission checks line size, LF, UTF-8, duplicate keys, nesting, closed fields, types/ranges, digest, and only then session state."
  - "Projection events do not reorder entries: complete reads alone apply the installed rank then descending state-change sequence."
  - "Invalidation retains occupied identity for truthful stale/offline display while making every binding non-actionable."
  - "Focus performs one complete live read, compares immutable pane/terminal/workspace/tab/session/source identity, then emits only agent.focus (retrying once when unfocused)."

requirements-completed: [RUST-01, RUST-02, RUST-03, RUST-08]

coverage:
  - id: D1
    description: "Closed v2 protocol frames match committed fixtures, including canonical digest, nullability, duplicate/nesting, exact line bound, and unknown-field rejection."
    requirement: RUST-01
    verification:
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test protocol_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "ProtocolSession preserves boot/session, sequence, duplicate, fixed queue, completion, and reset fences."
    requirement: RUST-02
    verification:
      - kind: integration
        ref: "protocol_parity::session_rejects_stale_duplicate_and_queue_overflow_then_resets_authority"
        status: pass
    human_judgment: false
  - id: D3
    description: "Projection parity preserves installed rank order, explicit empty slots, bounded non-path labels, material revision rules, and stale/offline identity fencing."
    requirement: RUST-03
    verification:
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test projection_focus_parity"
        status: pass
    human_judgment: false
  - id: D4
    description: "Focus parity authorizes exact agent.focus only after complete live revalidation, maps frozen failure outcomes, and allows one unfocused retry."
    requirement: RUST-08
    verification:
      - kind: integration
        ref: "projection_focus_parity::focus_policy_revalidates_exact_identity_and_allows_one_retry"
        status: pass
      - kind: integration
        ref: "projection_focus_parity::focus_policy_maps_fences_and_failures_without_other_effects"
        status: pass
    human_judgment: false

# Metrics
duration: 191min
completed: 2026-08-30
status: complete
---

# Phase 04 Plan 03: Authoritative Rust protocol, projection, and focus summary

**Closed v2 wire admission plus installed-inbox projection and exact focus policy are ported as portable Rust modules with focused fixture parity tests.**

## Performance

- **Duration:** 191 minutes wall-clock from execution start to final focused verification.
- **Started:** 2026-08-30T01:28:17Z
- **Completed:** 2026-08-30T04:39:29Z
- **Tasks:** 2/2
- **Files modified:** 6 owned implementation/test files (all new except no shared files)

## Accomplishments

- Added typed serde v2 frames for exactly `agent_snapshot`, `snapshot_ack`, `focus_intent`, and `focus_result`; canonical sorted-key FNV-1a64 digesting; 4096-byte admission; duplicate-key and nesting preflight; closed fields; and complete three-slot/Codex/diagnostics payloads.
- Added a fixed-capacity (16) ProtocolSession with boot/session fencing, duplicate/out-of-order rejection, pending completion/discard, and authority-clearing reset semantics.
- Added portable model/projection values that normalize the installed plugin's literal rank and sequence ordering, preserve stable source revisions across raw revision churn, fill empty slots explicitly, and retain stale identity without actionability after invalidation.
- Added pure exact-focus authorization that performs one complete live read and only `agent.focus`, verifies immutable identity/source/device/session fences, retries one unfocused acknowledgement, and maps failures to bounded statuses.
- Added fixture-driven integration tests for both committed protocol corpora and all projection/focus parity traces; the two required suites pass (14 tests total).

## Task Commits

Each task was committed atomically with TDD red/green commits:

1. **Task 1: Implement strict protocol and domain admission**
   - `f40172a` — `test(04-03): add protocol parity admission tests` (RED)
   - `d19dc16` — `feat(04-03): implement closed v2 protocol and domain model` (GREEN)
   - `7e443a6` — `fix(04-03): correct model helper lifetimes` (blocking compile correction)
2. **Task 2: Port authoritative projection and exact focus**
   - `17579ba` — `test(04-03): add projection and focus parity traces` (RED)
   - `672a721` — `feat(04-03): port authoritative projection and exact focus` (GREEN)

**Plan metadata:** pending summary commit.

## Files Created/Modified

- `host/herdr_keypad/native/src/protocol/v2.rs` — strict bounded codec, canonical digest, typed payloads, duplicate/nesting preflight, and session admission.
- `host/herdr_keypad/native/src/core/model.rs` — bounded normalized identities, entries, fixed snapshots, bindings, focus values, and inbox row parsing.
- `host/herdr_keypad/native/src/core/projection.rs` — installed rank projection, material revisions, complete-read replacement, and invalidation fencing.
- `host/herdr_keypad/native/src/core/focus.rs` — sole exact focus policy and closed Herdr port interface.
- `host/herdr_keypad/native/tests/protocol_parity.rs` — root golden/exporter fixture admission and session checks.
- `host/herdr_keypad/native/tests/projection_focus_parity.rs` — projection and focus frozen-trace checks.

## Decisions Made

- Kept all new modules unregistered from `lib.rs`; Plan 07 alone owns shared module declarations, public exports, and coordinator wiring.
- Kept the protocol enum closed and its payloads typed, with no extension map, generic payload, hold action, HID field, provider field, or arbitrary Herdr operation.
- Made source revision stabilization depend on material projection equality, so raw source revision churn cannot cause a publication generation change while a material change advances it.
- Preserved occupied stale/offline identity for display orientation but return no binding, ensuring invalidated entries cannot authorize focus.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Nested closed-field errors were initially classified as invalid shape**
- **Found during:** Task 1 protocol parity verification.
- **Issue:** Typed serde deserialization ran before nested agent/Codex/diagnostics field-set checks, so golden vectors containing `selected_key` or credential fields returned `invalid_shape` instead of the required `unknown_field`.
- **Fix:** Added nested object-set preflight before typed deserialization, preserving the frozen rejection vocabulary and oracle order.
- **Files modified:** `host/herdr_keypad/native/src/protocol/v2.rs`
- **Verification:** `protocol_parity` passes all committed corpus and golden-vector cases.
- **Committed in:** `d19dc16`

**2. [Rule 1 - Bug] Material revision stabilization compared unassigned slots**
- **Found during:** Task 2 projection parity verification.
- **Issue:** Candidate entries used a temporary max slot until after logical-equality comparison, causing raw `revision` churn to advance snapshot revision.
- **Fix:** Assign fixed slots before stabilization and preserve the prior source revision only for materially equal entries.
- **Files modified:** `host/herdr_keypad/native/src/core/projection.rs`
- **Verification:** `raw_revision_churn_does_not_advance_material_generation` passes.
- **Committed in:** `672a721`

**3. [Rule 3 - Blocking] Corrected helper lifetimes for Rust compilation**
- **Found during:** Task 2 focused test compilation.
- **Issue:** Borrowed bounded text helper return types needed explicit lifetimes because both input and name parameters were borrowed.
- **Fix:** Tied helper returns explicitly to their value input lifetime without changing behavior.
- **Files modified:** `host/herdr_keypad/native/src/core/model.rs`
- **Verification:** Both focused parity suites compile and pass on pinned Rust 1.98.0.
- **Committed in:** `7e443a6`

**4. [Plan boundary] Adapted fixture harness dispatch/boundary representations**
- **Found during:** Task 1 parity test implementation.
- **Issue:** Root golden vectors record dispatch after session admission while `classify_line` is intentionally pre-session and the exporter stores the exact-boundary case as a byte length only.
- **Fix:** The test drives valid golden vectors through a ProtocolSession and reconstructs the recorded 4096-byte padded line from the committed valid frame; production schema and fixtures remain untouched.
- **Files modified:** `host/herdr_keypad/native/tests/protocol_parity.rs`
- **Verification:** `protocol_parity` passes all vectors and boundary cases.
- **Committed in:** `d19dc16`

---

**Total deviations:** 4 (3 auto-fixed issues, 1 test-harness boundary adjustment)
**Impact on plan:** All changes stayed within owned modules/tests, retained the closed schema and authority boundaries, and introduced no dependency or integration-surface change. Shared manifests, root exports, `STATE.md`, and `ROADMAP.md` were intentionally left to Plan 07/orchestrator ownership.

## Issues Encountered

- Focus parity initially modeled timeout/not-found errors on the write path while the frozen traces model those as complete-read failures; the test spy was corrected to represent the fixture boundary, and all required calls/statuses now match.
- Cargo created a local `target/` directory during focused checks; it was removed before summary creation so the worktree remains clean.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 07 can register `protocol::v2` and `core::{model,projection,focus}` and adapt the existing root boundary contracts to these typed values.
- Integration must preserve the module-local typed protocol/session and exact-focus effect restrictions; no root/shared manifest or registry was modified here.
- `STATE.md` and `ROADMAP.md` remain untouched per the wave's merge-safe ownership contract.

---
*Phase: 04-production-rust-host-bridge*
*Plan: 03*
*Completed: 2026-08-30*

## Self-Check: PASSED

- `04-03-SUMMARY.md` exists at the required phase path.
- Task commits `f40172a`, `d19dc16`, `17579ba`, `672a721`, and `7e443a6` resolve in git history.
- Focused protocol/projection-focus suites passed 14 tests total.
- No generated target directory or untracked file remains.
