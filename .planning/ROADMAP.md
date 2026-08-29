# Roadmap: Herdr Agent Keypad

## Overview

Herdr Agent Keypad reaches its first usable release through nine roadmap phases: prove the delivered hardware and one reliable host link; project and focus the installed herdr inbox safely; keep live synchronization stable and flicker-free; deliver selectable firmware display themes and LED grammars; add truthful Codex capacity plus device controls; raise animation and interaction quality to a measured high-fidelity bar; prove focus-then-hold behavior through a real composite USB keyboard; replace the development Python bridge with an efficient, portable Rust host executable; then prove independent recovery and the complete personal workflow on the connected keypad. Each phase preserves host authority, identity-bound focus, explicit freshness, and the rule that keypad focus may have Herdr's native seen/manual-unread effects but never settles, dismisses, replies, or approves. The sole additional host-input capability is a fixed Space hold authorized by an acknowledged exact focus action.

## Phases

**Phase Numbering:** Sequential integer phases are planned milestone work; decimal phases are reserved for urgent insertions.

- [x] **Phase 1: Physical Keypad and Proven Transport** - The connected unit has a verified physical map and a scoped, reliable, bounded USB host link.
- [x] **Phase 2: Authoritative Agent Projection and Exact Focus** - Three keys mirror the installed inbox and focus only the exact rendered target with truthful outcomes.
- [ ] **Phase 02.1: Reliable Live Synchronization, Focus, and Flicker-Free Rendering** - Live Herdr changes converge to complete ACKed generations and composed panel images without unsafe focus or black flashes.
- [x] **Phase 02.2: Firmware Themes, LED Bars, and Device Selection Menu** - All four proposed display languages and LED grammars are implemented in firmware and selectable from the encoder menu without weakening direct agent focus. (completed 2026-08-20)
- [x] **Phase 3: Truthful Codex Capacity and Device Menu** - The fourth key reports both Codex windows truthfully while the encoder exposes diagnostics and persistent brightness. (completed 2026-08-21)
- [x] **Phase 03.1: High-Fidelity Animation and Interaction Polish** - Smooth and stable motion, transitions, and feedback are measured and refined on the actual keypad without weakening semantic clarity, input responsiveness, or focus safety. (INSERTED) (completed 2026-08-21)
- [x] **Phase 03.2: Focus-Then-Hold USB Keyboard** - A short agent-key press remains focus-only, while a deliberate hold first focuses the exact rendered pane and then behaves as a real held Space key through composite USB HID. (INSERTED) (completed 2026-08-22)
- [ ] **Phase 4: Production Rust Host Bridge** - A dependency-free native Rust bridge preserves the Python bridge's end-user behavior across Linux and macOS with an event-driven portable core.
- [ ] **Phase 5: Independent Recovery and Actual-Device Acceptance** - Every boundary recovers through authoritative resynchronization and the full workflow passes on the real setup.

## Phase Details

### Phase 1: Physical Keypad and Proven Transport

**Goal:** As a user of the delivered T-Keyboard S3 Pro, I want to operate it through a verified physical map and a host link selected from real measurements, so that later keypad behavior rests on the exact unit and a proven transport.
**Mode:** mvp
**Depends on:** Nothing (first phase)
**Requirements:** HARD-01, HARD-03
**Research flag:** Mandatory physical research records the delivered PCB/STM32 revision, official-library and ButtonSense compatibility, display/key/encoder/LED/orientation mapping, brightness and reboot behavior, USB identity/permissions/re-enumeration, sustained framed traffic, and hash-bound final-binary evidence selecting USB. Endpoint renumbering on a single connected device and active utility self-restart are explicitly non-applicable in the current setup; hybrid transport is not selected.

**Success Criteria** (what must be TRUE):

  1. On the connected unit, the user can identify all four displays and matching keys, open the encoder input path, change brightness, and observe correct orientation and deterministic reboot behavior against a recorded physical map.
  2. The device and Linux host complete a bounded, versioned bidirectional message exchange over USB.
  3. After reset, unplug, or supported link interruption, the same physical unit re-establishes the USB link without requiring an unrecorded port or board assumption.
  4. The user can see measured evidence that USB is suitable for v1; unsupported single-device endpoint renumbering and active utility self-restart are recorded as explicit scope exclusions rather than fabricated passes.

**Plans:** 13/13 plans executed

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Prove the production walking-skeleton USB tracer, pinned src-layout host environment, and real atomic evidence write/reopen verification.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Expand firmware into the complete bounded Pro-only physical stimulus and renderer surface.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Complete the exact guided host UI and immutable human-confirmed physical map.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — Pair the exact keypad and prove narrow ordinary-user fresh-session recovery across all D-12 interruptions.

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-05-PLAN.md — Freeze bounded protocol semantics and run the explicit PlatformIO native production-code golden-fixture harness.

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 01-06-PLAN.md — Run the frozen USB qualification and emit the initial immutable eligibility lock.

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 01-07-PLAN.md — Retire the conditional Wi-Fi branch after the recorded USB pass without creating Wi-Fi credentials or source.

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 01-08-PLAN.md — Resolve, select, build, and archive the initial selected-usb composition.

**Gap-closure Wave 9** *(blocked on Wave 8 completion)*

- [x] 01-09-PLAN.md — Route the flashed runtime through one production codec/session, bounded queue/I/O, and fail-closed physical readiness/map.

**Gap-closure Wave 10** *(blocked on Wave 9 completion)*

- [x] 01-10-PLAN.md — Reproduce exact Python 3.11 and prove standards-valid schema plus adversarial host/native/runtime parity.

**Gap-closure Wave 11** *(blocked on Wave 10 completion)*

- [x] 01-11-PLAN.md — Generate fresh boot/session identity and produce action-specific recovery plus non-fabricable physical proof locks.

**Gap-closure Wave 12** *(blocked on Wave 11 completion)*

- [x] 01-12-PLAN.md — Reopen the existing USB qualification under an explicit current-setup scope, enforce all applicable strict gates, and archive the unsupported actions as non-applicable.

**Gap-closure Wave 13** *(blocked on Wave 12 completion)*

- [x] 01-13-PLAN.md — Recompute scoped selection/build/archive lineage, actual object/ELF composition, and secret-free closure.

**UI hint:** yes

### Phase 2: Authoritative Agent Projection and Exact Focus

**Goal:** As a user of the delivered keypad, I want to see the installed inbox's three highest entries and focus the exact displayed Herdr pane with one safe physical press, so that I can switch to the agent needing attention without unsafe triage actions.
**Mode:** mvp
**Depends on:** Phase 1
**Requirements:** INBX-01, INBX-02, INBX-03, INBX-04, FOCS-01, FOCS-02, FOCS-03, FOCS-04, SYNC-02, SAFE-02
**Research flag:** Mandatory installed-Herdr research must generate and inspect the active schema, pin or establish the supported ordered-projection seam, verify identity across pane lifecycle changes, and record before/after focus behavior for seen, manual-unread, order, settled, and lifecycle state before live focus is accepted.
**Success Criteria** (what must be TRUE):

  1. The three agent keys show zero to three entries in exactly the installed `herdr-agent-inbox` order, with explicit empty tiles and no bridge or firmware reprioritization.
  2. Each occupied key is distinguishable at a glance by short title, workspace or repository discriminator, Herdr-consistent color on the display and any validated supporting LEDs, plus an icon or text cue for blocked, finished/unseen, working, idle, settled, or unknown state.
  3. Pressing an occupied key during normal operation focuses the exact pane represented by its pixels and reports success only after Herdr acknowledges that opaque identity, host epoch, and snapshot revision.
  4. Empty, stale, vanished, incompatible, offline, or reassigned bindings reject visibly; sequential panel updates never pair one generation's pixels with another generation's action.
  5. A keypad press can request only typed focus: documented native seen/manual-unread effects may occur, while settle, dismiss, reply, approval, and arbitrary Herdr or host actions remain impossible.

**Plans:** 5/5 plans executed

Plans:

- [x] 02-00-PLAN.md
- [x] 02-01-PLAN.md
- [x] 02-02-PLAN.md
- [x] 02-03-PLAN.md
- [x] 02-04-PLAN.md

- [x] 02-01: TBD during phase planning

**UI hint:** yes

### Phase 02.1: Reliable Live Synchronization, Focus, and Flicker-Free Rendering (INSERTED)

**Goal:** As a user of the delivered keypad, I want live Herdr changes to converge to one ACKed authoritative generation while every press remains bound to the exact pane represented by its pixels, without refresh downtime or partial tile painting.
**Requirements:** TBD — no requirement IDs are assigned to this inserted phase; Phase 2, Phase 3, and Phase 5 requirement ownership remains unchanged.
**Depends on:** Phase 2

**Success Criteria** (what must be TRUE):

  1. Typed Herdr lifecycle events are invalidation signals only: bursts coalesce into complete authoritative three-slot reads, and equivalent normalized state does not advance the visible generation or redraw.
  2. Newly rendered bindings become actionable only after their complete snapshot ACK. An intent already emitted for prior pixels remains queued and is revalidated against live immutable pane identity; source, session, ACK, and refresh failures publish stale/offline state and fence focus without silent discard or replay.
  3. Firmware composes each SYNC, tile, and feedback state completely in one reused bounded buffer, flushes panels sequentially through `BoardAdapter`, and activates bindings only after all three panels succeed.
  4. Installed inbox rank/sequence order, opaque rendered-binding identity, three fixed agent slots, stale/offline distinction, and `FocusExecutor` as the sole `agent.focus` path remain unchanged; mutable ordering/status churn cannot invalidate an otherwise live exact pane, while pane, terminal, workspace, tab, or agent-session mismatch still rejects.
  5. Focused host/native checks, the selected USB build/metrics, and one bounded exact-device smoke prove a real Herdr change reaches a higher ACKed revision as complete images and the changed tile still focuses only its exact pane.

**Plans:** 3/3 plans executed
Plans:

**Wave 1**

- [x] 02.1-01-PLAN.md — Carry typed Herdr invalidations through coalesced complete projection, exact ACK/readiness fencing, and once-only same-session interleaved focus handling.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02.1-02-PLAN.md — Compose every firmware tile off-screen, flush each panel once, clear generation-scoped feedback, and prove resource bounds through focused native tests and selected build metrics.

**Wave 3** *(blocked on Wave 1 completion)*

- [x] 02.1-03-PLAN.md — Run one hard-deadline exact-device live-change/render/focus smoke and archive hash-addressed bounded evidence.

### Phase 02.2: Firmware Themes, LED Bars, and Device Selection Menu (INSERTED)

**Goal:** As a Herdr user, I want to select any of four complete display themes and LED grammars from the keypad encoder, so that I can customize presentation without weakening authoritative snapshots, direct focus, freshness fencing, or compose-then-flush rendering.
**Mode:** mvp
**Depends on:** Phase 02.1
**Requirements:** TBD — this inserted phase is an initial design scope; requirement IDs and exact acceptance thresholds will be established during discussion and planning.
**Research flag:** Mandatory firmware and hardware research must inventory the existing renderer/`BoardAdapter`, the verified 14-pixel LED map, encoder event semantics, memory and frame-time limits, and the persistence boundary before implementation. The design proposal is the behavioral source for the four display themes, four LED grammars, state/feedback/health coverage, motion rules, and menu affordance; host authority and focus semantics remain unchanged.
**Success Criteria** (initial scope; refine during discussion):

  1. Agent displays implement selectable Signal Edge, Ledger, Beacon, and Instrument themes. Each theme renders the complete shared vocabulary: working, idle, blocked, unseen, settled, unknown, empty, pending, focused, named focus failures, stale/offline fencing, and sync transitions without color-only meaning.
  2. The panel-4 surface implements each theme's Codex/health composition and the encoder-menu surface, including truthful unavailable, stale, offline, authentication-failed, and limit-reached states; no theme invents missing values or changes host-owned semantics.
  3. Four selectable LED grammars drive the real 14-pixel strip: Rail Echo, Exception Channel, Field Extension, and Meter + Lamps. Each grammar covers per-key state, usage/health, menu-open, focus feedback, blocked motion, brightness/dim/all-off policy, and the documented physical index zones without exceeding the global power/brightness budget.
  4. Encoder click opens and closes the menu; encoder rotation navigates bounded menu rows; click selects display theme and LED theme independently. Menu rendering may be a panel-4 overlay initially, while the three agent keys remain direct, non-modal focus paths throughout.
  5. Theme and LED selections persist across reboot within the approved device-settings boundary, reject invalid or unavailable values safely, and never alter inbox ordering, generation-bound identities, freshness fencing, or `agent.focus` authorization.
  6. Every visible state is composed into the existing bounded frame buffer and flushed without black flashes or partial-generation frames; persistent BLOCKED motion and transient feedback use bounded discrete frames and remain synchronized between displays and LEDs.
  7. Focused native checks plus an exact-device smoke exercise every theme/LED combination, menu selection, reboot persistence, stale/offline fencing, and focus feedback on the connected keypad; evidence records the final physical mapping and resource bounds.

**Plans:** 5/5 plans complete

Plans:

**Wave 1**

- [x] 02.2-01-PLAN.md — Theme seam + Signal Edge, per-panel reveal amendment, feedback timing split, NVS settings store, contract amendments recorded.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02.2-02-PLAN.md — Ledger, Beacon, and Instrument themes plus the bounded measured-budget animation scheduler.
- [x] 02.2-03-PLAN.md — Four LED grammars and the policy-enforcing LED engine over the verified 14-pixel map.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02.2-04-PLAN.md — Panel-4 encoder menu: clamped navigation, preview-then-confirm, live LED preview, persistence wiring.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02.2-05-PLAN.md — Exact-device smoke: 16 combinations, persistence/fallback, fencing/feedback/LED sightings, hardware-question observations.

**UI hint:** yes

### Phase 3: Truthful Codex Capacity and Device Menu

**Goal:** The user can trust the dedicated Codex tile and inspect device health or adjust brightness without disrupting direct agent selection.
**Mode:** mvp
**Depends on:** Phase 02.2
**Requirements:** CODEX-01, CODEX-02, CODEX-03, CODEX-04, SYNC-03, SAFE-01, MENU-01, MENU-02, MENU-03, MENU-04
**Research flag:** Mandatory installed-Codex research must generate and inspect the active app-server schema, account authentication mode, available primary and secondary buckets, nullable fields, reset and reached-limit fields, first-read and sparse-update behavior, and an evidence-based freshness policy before the tile is declared truthful.
**Success Criteria** (what must be TRUE):

  1. The fourth display stays read-only and shows both primary and secondary Codex usage-window percentages, nearest relevant reset information, and reached-limit state exactly when the installed account supplies them.
  2. Missing or null values appear unavailable rather than zero, and current, stale, unavailable, authentication-failed, and host-offline states plus observation age are visibly distinct.
  3. Clicking the encoder opens and closes a secondary menu while all three agent keys remain direct, non-modal selection paths.
  4. The menu independently reports link, Herdr, and Codex health; last full synchronization and Codex observation; bounded troubleshooting identifiers; and firmware/protocol versions without credentials, prompts, transcripts, or host paths.
  5. The user can change and persist display brightness from the menu without changing authoritative inbox order, rendered target identity, or focus semantics.

**Plans:** 9/9 plans complete

Plans:

**Wave 1**

- [x] 03-01-PLAN.md — Trace the installed Codex success or typed failure through PermanentBridge, sole v2 protocol, staged firmware, and Signal Edge.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — Complete the known-full sparse merge, account invalidation, fixed freshness policy, and independent host clocks.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-03-PLAN.md — Freeze the closed host/native protocol and one staged shared RenderState.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 03-04-PLAN.md — Render the complete truthful Codex state matrix in all four themes.

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 03-05-PLAN.md — Map Codex usage and source health through all four existing LED grammars.

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 03-06-PLAN.md — Extend the one menu controller and settings store for non-modal direct keys and persistent local brightness.

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 03-07-PLAN.md — Render the six-row root, previews, HEALTH, and ABOUT in all four themes.

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 03-08-PLAN.md — Complete the acceptance matrix, contact sheets, and strict pending exact-device evidence.

**Wave 9** *(blocked on Wave 8 completion)*

- [x] 03-09-PLAN.md — Close the blocking exact-paired-device 10% long-text and interaction checkpoint.

**UI hint:** yes

### Phase 03.1: High-Fidelity Animation and Interaction Polish (INSERTED)

**Goal:** The keypad feels responsive and polished rather than stop-motion: animation, transitions, and interaction feedback are smooth, stable, and intentional across the four display themes and LED grammars, while semantic states remain immediately legible and direct agent focus remains unchanged.
**Mode:** mvp
**Depends on:** Phase 3
**Requirements:** TBD — establish animation-quality requirements during discussion and planning.
**Research flag:** Mandatory exact-device profiling must measure frame time, reveal timing, input latency, dropped/degraded frames, memory/power headroom, and behavior under concurrent Herdr/Codex updates before animation budgets are finalized.
**Success Criteria** (what must be TRUE):

  1. Existing ambient motion, menu transitions, brightness previews, focus feedback, blocked motion, stale/offline fences, and sync transitions are inventoried and assigned explicit motion behavior or an intentional static treatment.
  2. On the connected keypad, animation remains smooth and stable within measured resource and timing budgets: no tearing, black flashes, mixed generations, unsafe binding windows, unbounded allocation, or input starvation.
  3. Encoder and agent-key interactions remain responsive during animation; direct agent keys 1–3 retain their immediate focus-only path in every menu and animation state.
  4. Motion improves hierarchy and feedback without making state meaning depend on movement, color, timing, or animation completion; reduced/degraded/static modes remain truthful and visually coherent.
  5. All four themes and four LED grammars receive exact-device visual checks under normal refresh, rapid interaction, live data changes, stale/offline transitions, and reconnect/reset conditions, with measured evidence for the accepted quality bar.

**Plans:** 8/8 plans complete

Plans:
**Wave 1**

- [x] 03.1-01-PLAN.md — Measure the exact-device baseline and lock cadence/resource budgets

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03.1-02-PLAN.md — Prove the shared scheduler and Signal Edge transition tracer

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03.1-03-PLAN.md — Complete distinct motion systems for all four themes

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 03.1-04-PLAN.md — Deliver immediate focus feedback and truthful outcomes

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 03.1-05-PLAN.md — Polish menu navigation and immediate brightness response

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 03.1-06-PLAN.md — Synchronize all four LED grammars with semantic display events

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 03.1-07-PLAN.md — Build, flash, hash-lock, and capture the completed firmware's logical evidence

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 03.1-08-PLAN.md — Validate the current deployment and complete exact-device physical acceptance

**Cross-cutting constraints:**

- UI-LONG-TEXT: At the exact device's lowest accepted 10% brightness, every theme keeps the 8 px metadata floor, ASCII ellipsis, and 4 px safe inset without clipping, overlap, ticker motion, or bezel collision.

**UI hint:** yes

### Phase 03.2: Focus-Then-Hold USB Keyboard (INSERTED)

**Goal:** As a user of the keypad, I want a deliberate agent-key hold to focus the exact displayed Herdr pane and then behave as a real held Space key, so that any application using ordinary keyboard hold behavior can receive system-wide input without CLI-specific integration.
**Mode:** mvp
**Depends on:** Phase 03.1
**Requirements:** HOLD-01, HOLD-02, HOLD-03, HOLD-04, HOLD-05, SAFE-02
**Research flag:** Mandatory composite-USB feasibility must precede permanent migration. The exploration run prototypes only TinyUSB composite CDC + HID on the exact board and measures focus-to-HID ordering, short-click separation, key-repeat behavior, release and stuck-key failure modes, USB identity/pairing, CDC framing and throughput, reconnect, suspend/resume, flashing, and boot recovery. A passing result commits Phase 03.2 to composite CDC + HID and ends transport exploration. Only a recorded composite failure may return the decision for explicit reconsideration of Herdr pane key-repeat, per-OS virtual-keyboard injection, or an explicit Herdr key-state API.

**Success Criteria** (what must be TRUE):

  1. A bounded exploration run records reproducible exact-device evidence that proves or rejects composite CDC + HID before implementation replaces the proven USB stack; alternative paths are not explored after a passing result.
  2. A short press retains the existing immediate exact-focus behavior and never emits Space; crossing a physically validated hold threshold arms only local firmware gesture state correlated to the existing generation-, binding-, action-, and session-bound focus result.
  3. Firmware emits HID Space-down only after Herdr acknowledges exact focus and only while the same physical key remains held; release-before-ack, stale identity, late result, focus failure, unavailable source, or disconnected host never emits Space.
  4. Once HID Space-down is active, later focus changes do not cancel it; the input behaves like a physical keyboard and ends on physical release or USB-device removal, with controlled reset and suspend paths releasing all keys.
  5. The fixed Space hold adds no configurable key, macro, text, command, provider, or arbitrary Herdr-action surface, and pending, active, cancelled, and failed hold states remain visibly distinct.
  6. Fresh exact-device evidence requalifies composite USB identity, pairing, bounded NDJSON CDC exchange, reconnect, suspend/resume, flashing, recovery, input latency, and stuck-key behavior before Phase 5 acceptance begins.

**Planning gate:** Phase planning must schedule the composite CDC + HID feasibility run and exact-device decision record before any production transport, firmware, or host migration plan. It must also test whether the existing correlated `focus_result` is sufficient authorization so the hold path does not add protocol messages without need. Alternative backends remain out of scope unless this gate records a composite failure and the direction is explicitly reconsidered.

**Plans:** 9/10 plans executed

Plans:
**Wave 1**

- [x] 03.2-00-PLAN.md — Run the isolated exact-device composite CDC plus fixed-Space feasibility gate and freeze the terminal decision

**Wave 2** *(requires a checksum-valid 03.2-00 PASS)*

- [x] 03.2-01-PLAN.md — Migrate production and deliver the immediate-focus, authorized-hold tracer with all overlap rules

**Wave 3** *(requires Wave 2; plans have no file overlap)*

- [x] 03.2-02-PLAN.md — Freeze one-poll BoardAdapter press, down, release, and same-poll chord truth
- [x] 03.2-04-PLAN.md — Migrate exact composite discovery/udev identity and prove the four-frame protocol remains closed

**Wave 4** *(requires Plan 02)*

- [x] 03.2-03-PLAN.md — Centralize controller/HID lifecycle release and bounded safety metrics

**Wave 5** *(requires Plan 03's completed lifecycle contract)*

- [x] 03.2-05-PLAN.md — Normalize passive candidate, active-owner, failure, and lifecycle-cleared presentation

**Wave 6** *(requires Plan 05)*

- [x] 03.2-06-PLAN.md — Render truthful mic states in all four themes and extend the closed capture vocabulary

**Wave 7** *(requires Plan 06)*

- [x] 03.2-07-PLAN.md — Implement pending, active-owner, and cancellation semantics in all four LED grammars

**Wave 8** *(requires controller, identity, display, and LED plans)*

- [x] 03.2-08-PLAN.md — Lock the final deployment and complete deployment-linked logical evidence

**Wave 9** *(requires every production and evidence plan)*

- [x] 03.2-09-PLAN.md — Requalify the final exact device and publish the strict Phase 5 release gate

**UI hint:** yes

### Phase 4: Production Rust Host Bridge

**Goal:** As a keypad user, I want the production host bridge to provide the same inbox projection, exact focus, truthful Codex capacity, freshness/error states, reconnect behavior, and authorized focus-then-hold workflow as the Python bridge, but as one efficient native Rust executable that runs on Linux and macOS without a separately installed language runtime or bridge dependency.
**Mode:** mvp
**Depends on:** Phase 03.2
**Requirements:** TBD — establish Rust migration requirements during discussion and planning.
**Research flag:** Mandatory migration research must inventory the Python bridge's observable contract, freeze protocol and identity compatibility, select a maintained Rust stack with no runtime dependency, and verify Linux/macOS seams for serial discovery, USB I/O, Herdr socket/process integration, Codex app-server supervision, configuration/state paths, single-instance locking, signals, and packaging. Production and developer surfaces must be separated before implementation; polling is permitted only for explicit timers or when push/event intake is unavailable.

**Success Criteria** (what must be TRUE):

  1. A black-box parity matrix proves the Rust executable preserves every end-user behavior of the Python bridge: authoritative three-entry projection and ordering, exact generation/session-bound focus, focus-only action authorization, truthful current/stale/unavailable/offline/authentication-failed states, Codex primary and secondary windows, diagnostics, reconnect/resynchronization, and the existing composite CDC + HID hold authorization path.
  2. The Rust bridge keeps the closed v2 device protocol and all existing firmware semantics compatible, including bounded frames, fresh sessions, ACK/readiness fencing, identity-bound focus results, no replay after interruption, and no new arbitrary Herdr or keyboard-action surface.
  3. The implementation has a platform-independent core containing protocol validation, normalized domain state, projection and focus state machines, freshness/error policy, bounded queues, reconnect timers, and orchestration contracts; Linux and macOS adapters contain only OS-specific device discovery/I/O, Herdr endpoint/process integration, filesystem/config paths, locking, signals, and packaging concerns.
  4. Normal operation is event-driven and resource-bounded: serial and Herdr/Codex streams wake the core only on input, timers cover only reconnect/freshness/explicit refresh deadlines, fallback polling is used only when the installed Herdr interface cannot provide push events, and no fixed-rate busy loop or unnecessary polling remains.
  5. Release builds produce a native Linux executable and a native macOS executable that require no Python, Node, JVM, shared bridge package, or separately installed Rust runtime; all application dependencies are compiled into the binary, with only documented operating-system facilities and permissions remaining.
  6. The production launch path contains no tracer, fixture, acceptance harness, debug-only command, developer filesystem assumption, credential output, transcript/path leakage, or test fallback; bounded user-facing health/error diagnostics and structured logs required for operation remain redacted and explicitly limited.
  7. Linux and macOS installation and lifecycle behavior are documented and exercised: ordinary-user startup, exact keypad discovery/reconnect, Herdr and Codex child-process/socket failure recovery, clean shutdown, single-instance enforcement, configuration/state placement, and removal of the Python launcher from the supported production path.
  8. Focused native tests and end-to-end smoke checks compare Rust against the frozen Python contract with malformed/oversized frames, duplicate messages, stale identities, reconnects, missing optional Codex fields, unavailable push events, and sustained idle/traffic resource measurements; the final release artifacts are reproducible, versioned, and free of development-only dependencies.

**Plans:** TBD

Plans:

- [ ] 04-01: TBD (run $gsd-plan-phase 4 to break down)

### Phase 5: Independent Recovery and Actual-Device Acceptance

**Goal:** The user can rely on the complete keypad workflow after real component failures, restarts, and reconnections on the actual Herdr setup.
**Mode:** mvp
**Depends on:** Phase 4
**Requirements:** HARD-02, SYNC-01, SYNC-04, E2E-01
**Research flag:** Planning must turn the selected transport and measured device behavior into physical recovery and soak thresholds; acceptance evidence must come from the connected unit and installed Herdr/Codex accounts, not mocks.
**Success Criteria** (what must be TRUE):

  1. Device, bridge, Herdr, Codex, and link startup or reconnection show deterministic booting, empty, stale, unavailable, or offline states until a complete authoritative four-tile snapshot arrives.
  2. Agent keys remain disabled before that full snapshot, and disconnected or uncertain keypresses are never queued, replayed, or optimistically retried after reconnection.
  3. Link health, inbox freshness, and Codex freshness can fail and recover independently without old entries or expired usage remaining visible as current.
  4. On the actual connected device, a real highest-priority entry renders with correct identity/state, its short keypress focuses that exact pane, its deliberate hold produces and releases fixed system-wide Space only after focus acknowledgment, both real Codex windows render truthfully, and a real disconnect or restart visibly converges to current state.

**Plans:** TBD

Plans:

- [ ] 05-01: TBD (run $gsd-plan-phase 5 to break down)

**UI hint:** yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Physical Keypad and Proven Transport | 10/13 | In Progress|  |
| 2. Authoritative Agent Projection and Exact Focus | 4/5 | In Progress|  |
| 02.1 Reliable Live Synchronization, Focus, and Flicker-Free Rendering | 3/3 | Complete | 2026-08-17 |
| 02.2 Firmware Themes, LED Bars, and Device Selection Menu | 5/5 | Complete    | 2026-08-20 |
| 3. Truthful Codex Capacity and Device Menu | 9/9 | Complete    | 2026-08-21 |
| 03.1 High-Fidelity Animation and Interaction Polish | 8/8 | Complete    | 2026-08-21 |
| 03.2 Focus-Then-Hold USB Keyboard | 10/10 | Complete | 2026-08-22 |
| 4. Production Rust Host Bridge | 0/TBD | Not started | - |
| 5. Independent Recovery and Actual-Device Acceptance | 0/TBD | Not started | - |

