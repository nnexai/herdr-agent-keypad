---
phase: 04-production-rust-host-bridge
plan: "04"
subsystem: native-host-bridge
tags: [rust, tokio, herdr, codex, ndjson, parity]

# Dependency graph
requires:
  - phase: 04-production-rust-host-bridge
    provides: "Bounded native boundary contracts from Plan 01 and deterministic Python oracle corpora from Plan 02."
provides:
  - "Bounded Herdr public request client and event invalidation stream."
  - "Direct-argv Codex app-server child adapter with truthful full/sparse normalization and freshness state."
  - "Focused Herdr and Codex parity suites covering transport, lifecycle, redaction, and failure boundaries."
affects: [04-07, native-host-bridge, herdr, codex, differential-parity]

# Actuals (#2632)
actuals:
  tokens: 19497
  tasks: 2
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One-request-per-connection bounded Herdr NDJSON reads with correlated JSON-RPC IDs."
    - "Persistent Herdr subscription admitted only after a correlated ACK; events become typed invalidations."
    - "Direct argv Codex child process seam with bounded worker-fed JSONL lines and bounded shutdown."
    - "Presence-aware Codex full baseline and transactional sparse merge with coalesced refetch."

key-files:
  created:
    - host/herdr_keypad/native/src/ports/herdr.rs
    - host/herdr_keypad/native/src/ports/codex.rs
    - host/herdr_keypad/native/tests/herdr_parity.rs
    - host/herdr_keypad/native/tests/codex_parity.rs
  modified: []

key-decisions:
  - "Herdr adapters expose complete public reads and exact focus only; event payloads are discarded and represented as HerdrInvalidated."
  - "Codex account identity is reduced to an in-memory change marker and never appears in normalized views, evidence, or diagnostics."
  - "The standard Codex process factory uses Command::new with app-server --stdio and stderr null; no shell or raw child stream is retained."

patterns-established:
  - "Separate source line caps: 65,536 bytes for Herdr and 4,096 bytes for Codex, checked before line growth exceeds the cap."
  - "Fixed allowlisted Codex failure codes E-2400 through E-2409 and independent auth/offline/stale/current states."

requirements-completed: [RUST-01, RUST-03, RUST-08]

# Coverage metadata
coverage:
  - id: D1
    description: "Herdr public reads, correlated subscription ACK, typed invalidation, malformed/EOF/oversized recovery, and exact focus transport."
    requirement: RUST-01
    verification:
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test herdr_parity"
        status: pass
    human_judgment: false
  - id: D2
    description: "Codex handshake, direct argv child lifecycle, full/sparse/null/zero/duration normalization, freshness, account reset, auth/offline classification, and recursive redaction."
    requirement: RUST-03
    verification:
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test codex_parity"
        status: pass
    human_judgment: false
  - id: D3
    description: "Focused source parity tests exercise bounded resource and independent-recovery contracts without exposing upstream payloads."
    requirement: RUST-08
    verification:
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test herdr_parity --test codex_parity"
        status: pass
    human_judgment: false

# Metrics
duration: 112 min
completed: 2026-08-30
status: complete
---

# Phase 04 Plan 04: Source Adapter Summary

**Bounded Herdr Unix-socket invalidations and direct-argv Codex app-server normalization with focused parity evidence.**

## Performance

- **Duration:** approximately 112 minutes (implementation, focused tests, and task commits)
- **Started:** 2026-08-30T02:50:00Z
- **Completed:** 2026-08-30T04:42:31Z
- **Tasks:** 2/2
- **Files modified:** 4 (all four plan-owned artifacts created)

## Accomplishments

- Implemented `HerdrClient` with bounded request/response NDJSON framing, per-request correlation, shape validation, safe typed errors, complete `session.snapshot`/`agent.list`/`workspace.list` reads, typed subscriptions, and the sole exact `agent.focus` operation.
- Implemented `HerdrEventStream` with a persistent independently reconnectable socket, correlated subscription ACK admission, bounded read-ahead, payload-free `HerdrInvalidated` events, healthy idle behavior, and fallback state on EOF, malformed, timeout-before-ACK, and line-bound failures.
- Implemented `CodexCollector` with direct `codex app-server --stdio` argv, exact initialize/initialized/account/read/rateLimits handshake, bounded JSONL child I/O, deadline-aware correlation, auth/process/offline mapping, and bounded terminate/kill cleanup.
- Implemented presence-aware Codex normalization: only top-level `rateLimits` establishes a baseline; sparse updates preserve omitted values and explicit nulls, reject ambiguous shapes transactionally, coalesce refetch, clear on account change, distinguish stale/current/unavailable/auth/offline, and hash-only bucket manifests.
- Added focused parity suites for complete/failure Herdr traces and full/sparse/failure/redaction Codex traces. Both named adapter suites pass.

## Task Commits

Each task was committed atomically, with TDD RED and GREEN commits:

1. **Task 1: Port bounded Herdr requests and push invalidation**
   - `9224ef4` — `test(04-04): add failing Herdr adapter parity test` (RED)
   - `c6dbe67` — `feat(04-04): add bounded Herdr event adapter` (GREEN)
   - `7cbdb56` — `fix(04-04): preserve buffered Herdr push events` (post-task correctness fix)
2. **Task 2: Port Codex app-server lifecycle and truthful normalization**
   - `62d26b4` — `test(04-04): add failing Codex adapter parity test` (RED)
   - `285b0b5` — `feat(04-04): add bounded Codex app-server adapter` (GREEN; includes bounded unrelated-response deadline fix)

**Plan metadata:** Summary commit is intentionally left to the phase orchestrator because this isolated wave worktree owns no shared state files.

## Files Created/Modified

- `host/herdr_keypad/native/src/ports/herdr.rs` - Bounded public Herdr client, complete-read port implementation, persistent ACK-gated invalidation stream, and safe error vocabulary.
- `host/herdr_keypad/native/src/ports/codex.rs` - Codex process seam, direct standard child factory, bounded line worker, full/sparse normalization, freshness, account fence, and redaction.
- `host/herdr_keypad/native/tests/herdr_parity.rs` - Local Unix-socket tests for complete reads, correlation, exact focus, ACK/events, buffering, idle push, malformed, oversized, and EOF cases.
- `host/herdr_keypad/native/tests/codex_parity.rs` - Fake-child parity tests for normalization, sparse merge, deadlines, freshness, auth/offline, child exit, redaction, and argv.

## Decisions Made

- Herdr push data is intentionally not returned to the core: every valid `{event,data}` envelope becomes `BridgeEvent::HerdrInvalidated`; complete reads remain the only source of authority for projection/order.
- The Codex adapter's public normalized surface contains no account object, bucket names, raw errors, stdout, stderr, credentials, or paths. Bucket IDs are represented only by bounded SHA-256 prefixes in a manifest.
- The default child factory writes to a direct `Command::new` process with `app-server --stdio`, captures only bounded stdout lines through a worker channel, discards stderr, and performs bounded cleanup.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved read-ahead from combined Herdr ACK/event writes**
- **Found during:** Task 1 focused stream parity test
- **Issue:** A socket read can contain the subscribe ACK and first event in one kernel chunk; a single-line helper discarded bytes after the first newline, silently losing the invalidation.
- **Fix:** Added a bounded persistent read-ahead buffer for `HerdrEventStream`, and a same-packet ACK/event regression test.
- **Files modified:** `host/herdr_keypad/native/src/ports/herdr.rs`, `host/herdr_keypad/native/tests/herdr_parity.rs`
- **Verification:** Focused `herdr_parity` suite passes, including the same-packet event case.
- **Committed in:** `7cbdb56`

**2. [Rule 1 - Bug] Applied one total deadline across unrelated Codex responses**
- **Found during:** Task 2 response-correlation implementation
- **Issue:** Recursive skipping of unrelated child messages restarted the per-message timeout and could exceed the configured collection deadline under an unbounded stream.
- **Fix:** Replaced recursion with an iterative loop using one absolute response deadline and bounded remaining waits.
- **Files modified:** `host/herdr_keypad/native/src/ports/codex.rs`
- **Verification:** Focused `codex_parity` suite passes; the collector retains the configured deadline for every handshake stage.
- **Committed in:** `285b0b5`

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes directly enforce the planned bounded event/child contracts; no architectural or dependency scope changed.

## Issues Encountered

- The isolated base crate does not yet register `ports` modules or wire a Codex port into orchestration; Plan 04-07 owns those root exports and cross-slice integrations. The adapter files expose public types and `HerdrPort` implementation for that wiring.
- No formatter, linter, project-wide Rust/Python suite, UAT, firmware build, or physical validation was run, per the Wave 2 ownership contract.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04-07 should register `ports::herdr` and `ports::codex`, consume `HerdrClient` as the bounded `HerdrPort`, and use `HerdrEventStream::connect`/`next_event` to feed invalidation events.
- Plan 04-07 should invoke `CodexCollector::collect` only at explicit full-refresh/refetch deadlines (or wrap `collect_async` in its event-driven scheduling seam); no adapter fixed-rate wakeup exists.
- Existing root `CodexSnapshot` can be produced via `CodexView::as_snapshot`; no upstream response type needs to cross the core boundary.

---
*Phase: 04-production-rust-host-bridge*
*Plan: 04-04*
*Completed: 2026-08-30*

## Self-Check: PASSED

- `host/herdr_keypad/native/src/ports/herdr.rs`, `codex.rs`, and both focused parity test files exist.
- Task commits `9224ef4`, `c6dbe67`, `7cbdb56`, `62d26b4`, and `285b0b5` resolve on branch `worktree-agent-p04-04-wave2`.
- Required focused adapter checks passed: Herdr 4 tests and Codex 8 tests.
- Generated `host/herdr_keypad/native/target/` was removed; working tree is clean before summary commit.
