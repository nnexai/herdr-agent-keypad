---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 01
current_phase_name: physical-keypad-and-proven-transport
status: executing
stopped_at: Phase 1 UI-SPEC approved
last_updated: "2026-08-16T07:54:12.566Z"
last_activity: 2026-08-16
last_activity_desc: Initial vertical-MVP roadmap created with 26/26 v1 requirements mapped.
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 8
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-16)

**Core value:** The device must make agents that need attention immediately visible and let the user switch to the right herdr agent with one physical keypress.
**Current focus:** Phase 01 — physical-keypad-and-proven-transport

## Current Position

Phase: 01 (physical-keypad-and-proven-transport) — EXECUTING
Plan: 1 of 8 complete; next is 2 of 8
Status: Plan 01-01 complete; Phase 01 Wave 2 is ready
Last activity: 2026-08-16 — Real PANEL-1/key-0 USB tracer run completed

Progress: [█░░░░░░░░░] 12.5%

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

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Current roadmap decisions:

- [Phase 1]: Select exactly one v1 transport from connected-device evidence; USB remains preferred and hybrid is out of scope.
- [Phase 2]: Installed `herdr-agent-inbox` order is authoritative; actions bind opaque identity plus host epoch and snapshot revision, never a numeric slot.
- [Phase 2]: Native Herdr focus may change seen/manual-unread state; keypad focus cannot settle, dismiss, reply, approve, or invoke arbitrary actions.
- [Phase 3]: Codex credentials and interpretation stay on the host; absent values remain unavailable and source freshness is independent.
- [Phase 4]: Release acceptance requires real hardware, installed accounts, and visible recovery rather than mock-only evidence.

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

Last session: 2026-08-16T08:35:00Z
Stopped at: Plan 01-01 complete after real PANEL-1/key-0 USB CDC tracer evidence; ready to advance to Wave 2.
Resume file: None; Python 3.11 remains an explicit reproducibility concern.
