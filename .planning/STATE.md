---
gsd_state_version: 1.0
milestone: v1.0
current_phase: 5
current_phase_name: Independent Recovery and Actual-Device Acceptance
status: planning
stopped_at: Phase 04 complete, ready to plan Phase 5
last_updated: "2026-08-30T08:01:34.613Z"
last_activity: 2026-08-30
last_activity_desc: Phase 04 complete, transitioned to Phase 5
state_head: 519f0d03101363b0eedcc019e7ad08527faf51cf
progress:
  total_phases: 9
  completed_phases: 8
  total_plans: 63
  completed_plans: 63
milestone_name: milestone
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-20)

**Core value:** The device must make agents that need attention immediately visible and let the user switch to the right herdr agent with one physical keypress.
**Current focus:** Phase 5 — Independent Recovery and Actual-Device Acceptance

## Current Position

Phase: 5 — Independent Recovery and Actual-Device Acceptance
Plan: Not started
Status: Planning
Last activity: 2026-08-30 - Completed quick task 260830-t2s: Alternating Codex and Copilot hardware usage tile

Progress: [██████████] 100% (63/63 existing plans; 8/9 phases complete)

## Performance Metrics

**Velocity:**

- Total plans completed: 63
- Average duration: 14 min
- Total execution time: 0.2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 1 | 8 | 14 min |
| 02.2 | 5 | - | - |
| 3 | 9 | - | - |
| 03.1 | 8 | - | - |
| 04 | 10 | - | - |

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
| Phase 03.1 P04 | 15min | 2 tasks | 8 files |
| Phase 03.1 P05 | 12min | 2 tasks | 10 files |
| Phase 03.1 P06 | 12min | 2 tasks | 7 files |
| Phase 03.1 P07 | 17min | 3 tasks | 386 files |
| Phase 03.1 P08 | 1h 20m | 2 tasks | 8 files |
| Phase 03.2 P01 | 25min | 2 tasks | 8 files |
| Phase 03.2 P02 | 5min | 2 tasks | 5 files |
| Phase 03.2 P02 | 5min | 2 tasks | 5 files |
| Phase 03.2 P04 | 18min | 2 tasks | 5 files |
| Phase 03.2 P03 | 35min | 2 tasks | 6 files |
| Phase 03.2 P05 | 20min | 2 tasks | 6 files |
| Phase 03.2 P06 | 35min | 2 tasks | 11 files |
| Phase 03.2 P07 | 30min | 2 tasks | 7 files |
| Phase 03.2 P08 | 35 | 2 tasks | 156 files |
| Phase 03.2 P09 | debug continuation | 2 tasks | final qualification artifacts |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Current roadmap decisions:

- [Phase 1]: Select exactly one v1 transport from connected-device evidence; USB remains preferred and hybrid is out of scope.
- [Phase 2]: Installed `herdr-agent-inbox` order is authoritative; actions bind opaque identity plus host epoch and snapshot revision, never a numeric slot.
- [Phase 2]: Native Herdr focus may change seen/manual-unread state; keypad focus cannot settle, dismiss, reply, approve, or invoke arbitrary actions.
- [Phase 3]: Codex credentials and interpretation stay on the host; absent values remain unavailable and source freshness is independent.
- [Phase 5]: Release acceptance requires real hardware, installed accounts, and visible recovery rather than mock-only evidence.
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
- [Phase ?]: Represent physical press as a per-slot RenderState presentation flag so it cannot become protocol state or imply host acknowledgement.
- [Phase ?]: Keep pending cadence in AgentProjection at a fixed 300 ms step independent of ambient theme cadence and degradation.
- [Phase ?]: Clear impulse and pending timing markers on exact result admission so success and named failures assert immediately.
- [Phase ?]: MenuController remains authoritative; immediate mutations start only bounded presentation metadata.
- [Phase ?]: Fixed 120 ms open/close and 200 ms slide/detail bounds replace reversed phases without momentum.
- [Phase ?]: Each theme moves only its rail, record stripe, beacon marker, or bezel cue while semantic copy stays stable.
- [Phase ?]: LedEvents now carries bounded semantic event kind, epoch, and grammar-neutral phase while Codex truth remains in committed RenderState.
- [Phase ?]: LedEngine owns immediate SYNC/all-off resolution; four grammars retain independent phase and physical-zone choreography.
- [Phase ?]: Use a closed production-renderer capture vocabulary with Full, Half, Static, and bounded phases so logical evidence is deterministic and state-safe.
- [Phase ?]: Require exact-pair fresh boot/session identity plus uploaded selected-usb binary hash in one immutable deployment lock before any capture.
- [Phase ?]: Keep framebuffer and LED rows machine-only; physical LED, optical, smoothness, brightness, feel, and latency claims remain deferred to Plan 08.
- [Phase ?]: Accepted exact paired-keypad deployment 875577d8ec63c0917d4244ab9ecf5d8163601a16a2e2a800516d728140612d6e with logical manifest 624a23b01e65092049021278220907768603f83b06df26b6f8476142bc2e1094 and 25/25 physical rows pass.
- [Phase ?]: Preserved failed physical attempts immutably; current defect ledger has zero defects and zero open dispositions.
- [Phase 03.2]: Plan 03.2-01 uses the immutable Plan 00 measured shared 550 ms threshold from the debounced physical edge.
- [Phase 03.2]: Plan 03.2-01 reuses AgentProjection applyFocusResult success as the sole local HID authorization and adds no protocol field or host API.
- [Phase 03.2]: Plan 03.2-01 keeps one fixed Space owner with no transfer and retains same-poll chord lockout until a complete all-up frame.
- [Phase 03.2]: BoardAdapter remains the sole physical truth provider: one official board_.update() sample supplies press, current-down, and release facts with no competing debounce or raw hardware path.
- [Phase 03.2]: Press latches preserve the earliest pending physical edge timestamp until consumption, while release masks are scoped to the current sampled update.
- [Phase 03.2]: Readiness or verified physical-map failure clears lifecycle state and fails closed; BoardAdapter exposes no candidate, ownership, focus, HID, or presentation policy.
- [Phase 03.2]: The restored frozen composite binary and immutable validator PASS remain Plan 00 prerequisite evidence only, not new product qualification.
- [Phase 03.2]: Plan 03.2-04 freezes composite CDC discovery at VID/PID 0x303a:0x1001, serial 8C:BF:EA:0D:CB:FC, CDC interface 01, while application hello and fresh session remain authorization.
- [Phase 03.2]: Plan 03.2-04 keeps the v2 wire at exactly agent_snapshot, snapshot_ack, focus_intent, and focus_result; fixed Space hold authority remains local after exact admitted focus_result.
- [Phase 03.2]: HoldController clears authority before every lifecycle release attempt and requires empty completion plus all-keys-up before rearm.
- [Phase 03.2]: Hold safety failures remain boot-monotonic while bounded diagnostic counters and timing maxima reset explicitly.
- [Phase 03.2]: RenderState carries only value-only hold facts; action IDs, bindings, sessions, keycodes, timers, and mutation paths remain outside the normalized view.
- [Phase 03.2]: A threshold-qualified candidate remains visible after the ordinary bounded Success cue expires, while named failure feedback never admits candidate or owner presentation.
- [Phase 03.2]: Source fences, projection sync, lifecycle blocks, and incomplete empty reports suppress passive hold facts before a complete output frame; only HoldController can clear physical authority.
- [Phase 03.2]: The active-owner cue remains tied to the physical owner slot through another-slot focus and generation replacement when that slot remains occupied.
- [Phase 03.2]: Beacon places the shared allocation-free mic at center (64,52), Instrument inside the ring at (64,54), while existing semantic copy remains visible.
- [Phase 03.2]: Solid mic presentation is admitted only for active physical-owner truth; candidate mic remains outlined or restrained pulsing and shared source/failure/sync/lifecycle gates suppress both otherwise.
- [Phase 03.2]: Six bounded hold capture scenes use tokens j/k/q/v/x/z and production RenderState fixtures; capture never mutates active theme, bindings, NVS, controller, or HID authority.
- [Phase 03.2]: Framebuffer capture remains logical-only RGB565/PNG evidence with dimensions, deployment identity, and hashes; physical clarity, LED, brightness, mapping, and optics claims remain deferred.
- [Phase 03.2]: Four LED grammars keep candidate and active-owner cues on mapped physical zones; active ownership never transfers across focus changes.
- [Phase 03.2]: Slot-tagged hold segments let LedEngine fence source, failure, health, SYNC, lifecycle, all-off, and dim states without hue-based classification.
- [Phase 03.2]: Cancellation remains one bounded LED-only event with fixed grammar-specific durations and ordinary pending feedback after expiry.
- [Phase 03.2]: Plan 08 locks logical hold evidence to the current selected-usb deployment and exact fresh boot/session lineage.
- [Phase 03.2]: Plan 08 keeps framebuffer and LED evidence machine-only; physical brightness, clarity, mapping, feel, latency, and optics remain deferred to Plan 09.

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Complete under the current-setup scope. Endpoint renumbering and self-restarting the active qualification utility are explicitly non-applicable and remain excluded from the archived profile.
- [Phase 3]: Installed Codex schema/account buckets, nullability, sparse updates, authentication behavior, and freshness threshold require mandatory research.
- [Phase 5]: Recovery and soak thresholds depend on the transport and physical measurements selected in Phase 1.
- [Phase 02.1]: Bounded live-sync smoke evidence and exact-device physical checkpoint passed; no long qualification rerun.
- [Phase 03.2]: Post-gate quick-tap correction changed firmware and bridge hashes. Focused suites plus exact-device six-tap and hold/release checks pass, but the prior full qualification artifact remains bound to its recorded deployment and must not be cited for the new binary.

### Roadmap Evolution

- Phase 02.1 inserted after Phase 2: Reliable Live Synchronization, Focus, and Flicker-Free Rendering (URGENT)
- Phase 02.2 inserted after Phase 02.1: Firmware Themes, LED Bars, and Device Selection Menu (URGENT)
- Phase 03.1 inserted after Phase 3: High-Fidelity Animation and Interaction Polish (URGENT)
- Phase 03.2 inserted after Phase 3: Production Rust Herdr Bridge (URGENT)
- Phase 03.2 inserted after Phase 03.1: Focus-Then-Hold USB Keyboard; comparative exploration gate required before composite USB commitment (URGENT)
- Phase 03.2 edited: composite CDC + HID is the sole feasibility target; alternative backends are explored only after a recorded composite failure
- Phase 4 and Phase 5 reordered: Production Rust Host Bridge now precedes Independent Recovery and Actual-Device Acceptance

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | Additional providers, expansion modules, broader actions, standalone service, ambient LEDs, and richer presentation/diagnostics | Deferred | Project initialization |

## Quick Tasks Completed

| Task | Date | Status |
|------|------|--------|
| Archive two design-study HTML pages in `.planning/research/` | 2026-08-17 | complete |
| [260820-sp6 — Fix bridge automatic recovery after USB CDC communication reset](./quick/260820-sp6-fix-bridge-automatic-recovery-after-usb-/) | 2026-08-20 | complete — `db5c880` |
| [260822-abq — Align OMP agent routing with Codex definitions](./quick/260822-abq-align-omp-agents-markdown-definitions-wi/) | 2026-08-22 | complete — `1d09810` |
| [260830-rfd - Add Copilot AI-credit usage and monthly limits](./quick/260830-rfd-implement-copilot-usage-support-alongsid/) | 2026-08-30 | complete - `7c5ea32` |
| [260830-t2s - Alternate Codex and Copilot on panel 4](./quick/260830-t2s-display-codex-and-copilot-usage-on-the-f/) | 2026-08-30 | complete - `713bef4` |

## Session Continuity

**Resume file:** .planning/ROADMAP.md

Last session: 2026-08-30T08:01:34.613Z
Stopped at: Phase 04 complete, ready to plan Phase 5
