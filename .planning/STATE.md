---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 1
current_phase_name: Physical Keypad and Proven Transport
status: executing
stopped_at: Phase 1 UI-SPEC approved
last_updated: "2026-08-16T07:52:17.054Z"
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
**Current focus:** Phase 1 — Physical Keypad and Proven Transport

## Current Position

Phase: 1 of 4 (Physical Keypad and Proven Transport)
Plan: 0 of TBD in current phase
Status: Ready to execute
Last activity: 2026-08-16 — Initial vertical-MVP roadmap created with 26/26 v1 requirements mapped.

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: No execution data yet

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

- [Phase 1]: Delivered hardware revision, ButtonSense artifact, physical map, USB identity/recovery, and redraw/input/resource behavior require measurement.
- [Phase 2]: Installed Herdr schema, supported order seam, stable pane identity, and exact native focus effects require mandatory research before live focus acceptance.
- [Phase 3]: Installed Codex schema/account buckets, nullability, sparse updates, authentication behavior, and freshness threshold require mandatory research.
- [Phase 4]: Recovery and soak thresholds depend on the transport and physical measurements selected in Phase 1.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | Additional providers, expansion modules, broader actions, standalone service, ambient LEDs, and richer presentation/diagnostics | Deferred | Project initialization |

## Session Continuity

Last session: 2026-08-16T06:29:51.631Z
Stopped at: Phase 1 UI-SPEC approved
Resume file: .planning/phases/01-physical-keypad-and-proven-transport/01-UI-SPEC.md
