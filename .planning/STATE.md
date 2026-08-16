---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 01
current_phase_name: physical-keypad-and-proven-transport
status: executing
stopped_at: Completed 01-05-PLAN.md after host/firmware golden parity and native fixture harness
last_updated: "2026-08-16T14:31:24.390Z"
last_activity: 2026-08-16
last_activity_desc: Initial vertical-MVP roadmap created with 26/26 v1 requirements mapped.
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 8
  completed_plans: 5
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-16)

**Core value:** The device must make agents that need attention immediately visible and let the user switch to the right herdr agent with one physical keypress.
**Current focus:** Phase 01 — physical-keypad-and-proven-transport

## Current Position

Phase: 01 (physical-keypad-and-proven-transport) — EXECUTING
Plan: 5 of 8
Status: Ready to execute
Last activity: 2026-08-16 — Phase 01 execution started

Progress: [██████░░░░] 63%

## Performance Metrics

**Velocity:**

- Total plans completed: 1
- Average duration: 14 min
- Total execution time: 0.2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 1 | 8 | 14 min |

**Recent Trend:**

- Last 5 plans: 01-01 (14 min)
- Trend: Initial execution

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P02 | 3 min | 2 tasks | 5 files |
| Phase 01 P03 | closeout | 2 tasks | 7 files |
| Phase 01 P04 | execution-window | 2 tasks | 9 files |
| Phase 01 P05 | execution-window | 2 tasks | 10 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Current roadmap decisions:

- [Phase 1]: Select exactly one v1 transport from connected-device evidence; USB remains preferred and hybrid is out of scope.
- [Phase 2]: Installed `herdr-agent-inbox` order is authoritative; actions bind opaque identity plus host epoch and snapshot revision, never a numeric slot.
- [Phase 2]: Native Herdr focus may change seen/manual-unread state; keypad focus cannot settle, dismiss, reply, approve, or invoke arbitrary actions.
- [Phase 3]: Codex credentials and interpretation stay on the host; absent values remain unavailable and source freshness is independent.
- [Phase 4]: Release acceptance requires real hardware, installed accounts, and visible recovery rather than mock-only evidence.
- [Phase 1]: Plan 01-02 preserves the Pro-only adapter and fixed renderer as the implementation boundary; no checkpoint workaround was needed.
- [Phase 1]: Plan 01-02 records only the user's explicit delivered-unit proof scope and does not infer physical facts beyond that evidence.
- [Phase 1]: Physical input naming is KEY-1..KEY-4 with raw library indices 0..3; encoder click is raw index 4 and remains an observation-only BOOT0-safe input.
- [Phase 1]: Machine acknowledgements never produce physical PASS; the accepted map requires explicit Y tied to the stable step and source run, with failed and replaced history immutable.
- [Phase 1]: The centered renderer correction is included in the accepted proof; Pair, Recover, Traffic, and Selection remain later-plan work and D-04 archival remains Plan 01-08.
- [Phase 1]: Pairing trusts only the exact fresh physical challenge plus application hello device_id; USB descriptors and transient paths remain discovery-only.
- [Phase 1]: Every D-12 interruption creates a fresh session and discards uncertain IDs; endpoint renumbering is explicitly unavailable rather than passed.
- [Phase 1]: Operator-run recovery tour owns physical Y/N/R/U confirmation and utility restart resumes from an immutable checkpoint.
- [Phase 1]: Plan 01-05 froze a closed v1 envelope at 4096 bytes including LF with canonical FNV-1a-64 payload digest and typed rejection codes.
- [Phase 1]: Plan 01-05 consolidated firmware FrameCodec and ProtocolSession with fresh reset/discard, sequence/deduplication, and bounded queue semantics.

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Plan 01-01 measured PANEL-1/key-0 and USB CDC recovery on the delivered unit; remaining full four-panel map, interruption matrix, and Python 3.11 reproducibility evidence are still required.
- [Phase 2]: Installed Herdr schema, supported order seam, stable pane identity, and exact native focus effects require mandatory research before live focus acceptance.
- [Phase 3]: Installed Codex schema/account buckets, nullability, sparse updates, authentication behavior, and freshness threshold require mandatory research.
- [Phase 4]: Recovery and soak thresholds depend on the transport and physical measurements selected in Phase 1.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | Additional providers, expansion modules, broader actions, standalone service, ambient LEDs, and richer presentation/diagnostics | Deferred | Project initialization |

## Session Continuity

Last session: 2026-08-16T14:31:24.380Z
Stopped at: Completed 01-05-PLAN.md after host/firmware golden parity and native fixture harness
Resume file: None
