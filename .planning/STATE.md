---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 03.1
current_phase_name: High-Fidelity Animation and Interaction Polish
status: executing
stopped_at: Completed 03.1-03-PLAN.md
last_updated: "2026-08-21T09:42:43.265Z"
last_activity: 2026-08-21
last_activity_desc: Completed Phase 03 Plan 08 exact-device capture and pending evidence
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 43
  completed_plans: 38
---

Total Phases: 6
---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 03
current_phase_name: Truthful Codex Capacity and Device Menu
status: Ready to execute
stopped_at: Completed 03-08-PLAN.md
last_updated: "2026-08-21T01:20:00Z"
last_activity: 2026-08-21
last_activity_desc: "Completed Phase 03 Plan 08 exact-device capture and pending evidence"
progress:[█████████░] 88%
  total_phases: 7
  completed_phases: 4
  total_plans: 35
  completed_plans: 34
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-20)

**Core value:** The device must make agents that need attention immediately visible and let the user switch to the right herdr agent with one physical keypress.
**Current focus:** Phase 03.1 — High-Fidelity Animation and Interaction Polish

## Current Position

Phase: 03.1 (High-Fidelity Animation and Interaction Polish) — EXECUTING
Plan: 4 of 8
Status: Ready to execute
Last activity: 2026-08-21 — Phase 03.1 execution started

Progress: [██████████] 97%

## Performance Metrics

**Velocity:**

- Total plans completed: 15
- Average duration: 14 min
- Total execution time: 0.2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 1 | 8 | 14 min |
| 02.2 | 5 | - | - |
| 3 | 9 | - | - |

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
| Phase 01 P09 | execution window | 3 tasks | 12 files |
| Phase 01 P10 | 133 | 3 tasks | 9 files |
| Phase 02 P00 | 25min | 3 tasks | 6 files |
| Phase 02 P01 | 180 | 2 tasks | 12 files |
| Phase 02 P02 | 3600 | 2 tasks | 5 files |
| Phase 02 P03 | 3600 | 2 tasks | 3 files |
| Phase 02.1 P01 | 35min | 3 tasks | 6 files |
| Phase 02.1 P02 | 25min | 2 tasks | 7 files |
| Phase 02.2 P05 | 15min | 2 tasks | 6 files |
| Phase 03 P01 | 120 | 3 tasks | 9 files |
| Phase 03 P02 | 16min | 2 tasks | 6 files |
| Phase 03 P03 | 3min | 2 tasks | 11 files |
| Phase 03 P04 | 30min | 1 task | 9 files |
| Phase 03 P05 | 28min | 1 task | 8 files |
| Phase 03 P06 | 11min | 2 tasks | 10 files |
| Phase 03 P07 | 10min | 1 task | 8 files |
| Phase 03 P09 | multi-session | 3 tasks | 19 files |
| Phase 03.1 P01 | 55 | 2 tasks | 10 files |
| Phase 03.1 P02 | 34min | 2 tasks | 8 files |
| Phase 03.1 P03 | 1min | 2 tasks | 8 files |

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
- [Phase 1]: Plan 01-06 is the sole long physical qualification; later plans must consume its immutable USB eligibility lock and use only bounded targeted checks.
- [Phase ?]: 01-09: Every complete firmware input line is admitted through the consolidated FrameCodec/ProtocolSession path before typed dispatch.
- [Phase ?]: 01-09: Protocol queue high-water reports bounded pending frame units and explicit completion restores capacity.
- [Phase ?]: 01-09: Board readiness and PhysicalMap lookups fail closed without raw-index fallback.
- [Phase ?]: Keep supported Python range >=3.11,<3.15 with hash-locked pyserial/jsonschema dependencies; do not require an older interpreter.
- [Phase ?]: Classify non-string frame discriminants as unknown_type before membership checks for host/native parity.
- [Phase ?]: Reject duplicate JSON keys and over-limit nesting before dispatch.
- [Phase 1]: Current-setup scope excludes endpoint renumbering and active utility self-restart as non-applicable; the archived USB profile requires all remaining applicable interruption rows and records the exclusions explicitly.
- [Phase ?]: Phase 2 Wave 0 pins installed herdr-agent-inbox at actual HEAD 78b243279b4da55150b58dc2cc3cffcdc2fd6a04 because planned de409f683262 object is unavailable.
- [Phase ?]: 02-00 Herdr artifacts are baseline-compatible; agent.focus is the sole device action and host epoch/snapshot revision remain bridge-owned.
- [Phase ?]: V2 preserves the Phase 1 FrameCodec/ProtocolSession envelope and uses exactly three staged/committed slots with opaque identity plus bridge-owned host epoch and snapshot revision.
- [Phase ?]: Only canonical key slots 0..2 emit typed focus_intent; key/panel 4 and encoder remain unbound.
- [Phase ?]: Installed Herdr HEAD 78b243279b4da55150b58dc2cc3cffcdc2fd6a04 remains the only accepted ordering authority; malformed rank or identity fails closed.
- [Phase ?]: Physical keys 0..2 are exact generation-bound focus-only actions; panel/key 4 and encoder remain unbound.
- [Phase ?]: Firmware renders a global SYNC veil before sequential three-panel staging and commits active bindings only after all draws succeed.
- [Phase 2]: Actual-device acceptance passed on the exact selected-USB keypad: complete snapshot acknowledgement, explicit empty rejection, exact target focus, terminal FOCUSED feedback, and authoritative state restoration are verified by commits `db323fe`, `b3f172e`, and `8a6d557`.
- [Phase ?]: Plan 02.1-01 requires ACK-plus-typed-event proof for push; installed socket selected bounded polling.
- [Phase ?]: Typed Herdr events invalidate only; complete authoritative reads determine all slots and ordering.
- [Phase ?]: Firmware uses one reusable PSRAM-preferred 128x128 RGB565 composition sprite and sequential BoardAdapter flushes.
- [Phase ?]: Generation replacement clears pending action/deadline/feedback state; complete composed flush is measured by existing ProofMetrics.
- [Phase 02.2]: Ambient/continuous animation is permitted under a measured budget (R-1): complete composed frames only, degradation to static, semantic states always dominant; amends the decorative-animation exclusion.
- [Phase 02.2]: SYNC-02 amended (R-2): bindings stay all-panel atomic; pixels may reveal per panel (≤250 ms, keys fenced during reveal); SYNC veil retained for boot/reset/failure.
- [Phase 02.2]: Theme/LED grammar persistence uses NVS Preferences with schema version; invalid values fall back to Signal Edge + Rail Echo without write-back.
- [Phase 02.2]: Grammar B (Exception Channel) gets a minimal bounded press blink to satisfy D-08 while keeping its darkness philosophy.
- [Phase ?]: Plan 05 accepted under the user's explicit waiver: fresh-erase or invalid/missing stored-settings fallback to Signal Edge + Rail Echo, including no-write-back physical proof, was not run and remains deferred/open.
- [Phase ?]: 02.2 device evidence uses accepted-with-deferred overall disposition while retaining the fallback sighting as pending/deferred rather than a physical pass.
- [Phase ?]: Exact fresh hello matched stored device and firmware identity; tracer records the committed snapshot ACK.
- [Phase ?]: Installed E-2406 request failure is CODEX OFFLINE without quota claims; bucket maps remain redacted manifest-only.
- [Phase ?]: Only documented top-level rateLimits supplies capacity; map-only and unusable shapes remain unavailable with E-2401.
- [Phase ?]: Sparse updates require a known baseline, preserve omissions and metadata nulls, and schedule one coalesced full refetch.
- [Phase ?]: Codex-only publications preserve Herdr generation, identities, bindings, pending focus, and focus authorization.
- [Phase ?]: Closed v2 agent_snapshot now requires complete Codex and diagnostics objects with E-2401 allowlisted bucket-unavailable semantics.
- [Phase ?]: Firmware stages complete Codex and diagnostics into a local Generation candidate and exposes one committed shared RenderState.
- [Phase 3]: All four panel-4 renderers share bounded Codex truth semantics while retaining theme-owned geometry; staged snapshot reveal frames read one staged Generation.
- [Phase 3]: All four LED grammars consume the committed Codex RenderState directly; current-only primary usage owns the established usage zones, source failures use health overlays, and focus feedback retains precedence.
- [Phase 3]: ProductInputRouter is the sole pure frame-ordering seam; production and native tests execute it with all agent slots emitted before click and rotation.
- [Phase 3]: Settings schema v2 stores only theme, LED grammar, and 10%-step brightness; valid v1 loads at 80% with no boot migration write.
- [Phase ?]: Keep metrics bounded and preserve focus/snapshot authority outside metrics_ack.
- [Phase ?]: Record the human smoothness failure and measured resource gaps as blocking quality evidence.
- [Phase ?]: Use UI-SPEC ceilings as target limits while retaining measured resource headroom.
- [Phase ?]: Plan 03.1-02 uses a four-phase, 200 ms presentation transition and immediately interrupts it for newer generations or urgent source fences.
- [Phase ?]: Animation duty is measured from complete compose/flush time over measured loop wall time; Static cancels queued decorative progress while retaining semantic frames.
- [Phase ?]: Keep one shared scheduler and expose bounded ambient phase through RenderState; themes map it to distinct rail, record, field, and gauge primitives.
- [Phase ?]: Use measured cadences: Signal Edge/Ledger/Instrument 33334 us and Beacon 66668 us; Half advances every second phase and Static stays neutral.
- [Phase ?]: Keep EMPTY/NO AGENT, null Codex, and source fences truth-bearing static frames; only approved accents move.

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Complete under the current-setup scope. Endpoint renumbering and self-restarting the active qualification utility are explicitly non-applicable and remain excluded from the archived profile.
- [Phase 3]: Installed Codex schema/account buckets, nullability, sparse updates, authentication behavior, and freshness threshold require mandatory research.
- [Phase 4]: Recovery and soak thresholds depend on the transport and physical measurements selected in Phase 1.
- [Phase 02.1]: Bounded live-sync smoke evidence and exact-device physical checkpoint passed; no long qualification rerun.

### Roadmap Evolution

- Phase 02.1 inserted after Phase 2: Reliable Live Synchronization, Focus, and Flicker-Free Rendering (URGENT)
- Phase 02.2 inserted after Phase 02.1: Firmware Themes, LED Bars, and Device Selection Menu (URGENT)
- Phase 03.1 inserted after Phase 3: High-Fidelity Animation and Interaction Polish (URGENT)
- Phase 03.2 inserted after Phase 3: Production Rust Herdr Bridge (URGENT)

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | Additional providers, expansion modules, broader actions, standalone service, ambient LEDs, and richer presentation/diagnostics | Deferred | Project initialization |

## Quick Tasks Completed

| Task | Date | Status |
|------|------|--------|
| Archive two design-study HTML pages in `.planning/research/` | 2026-08-17 | complete |
| [260820-sp6 — Fix bridge automatic recovery after USB CDC communication reset](./quick/260820-sp6-fix-bridge-automatic-recovery-after-usb-/) | 2026-08-20 | complete — `db5c880` |

## Session Continuity

**Resume file:** None

Last session: 2026-08-21T09:42:43.251Z
Stopped at: Completed 03.1-03-PLAN.md
