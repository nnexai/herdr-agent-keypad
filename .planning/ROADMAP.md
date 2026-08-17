# Roadmap: Herdr Agent Keypad

## Overview

Herdr Agent Keypad reaches its first usable release through four vertical, real-device capabilities: prove the delivered hardware and one reliable host link; project and focus the installed herdr inbox safely; add truthful Codex capacity plus secondary diagnostics and brightness controls; then prove independent recovery and the complete personal workflow on the connected keypad. Each phase preserves host authority, identity-bound focus, explicit freshness, and the rule that keypad focus may have Herdr's native seen/manual-unread effects but never settles, dismisses, replies, approves, or invokes arbitrary actions.

## Phases

**Phase Numbering:** Sequential integer phases are planned milestone work; decimal phases are reserved for urgent insertions.

- [x] **Phase 1: Physical Keypad and Proven Transport** - The connected unit has a verified physical map and a scoped, reliable, bounded USB host link.
- [x] **Phase 2: Authoritative Agent Projection and Exact Focus** - Three keys mirror the installed inbox and focus only the exact rendered target with truthful outcomes.
- [ ] **Phase 3: Truthful Codex Capacity and Device Menu** - The fourth key reports both Codex windows truthfully while the encoder exposes diagnostics and persistent brightness.
- [ ] **Phase 4: Independent Recovery and Actual-Device Acceptance** - Every boundary recovers through authoritative resynchronization and the full workflow passes on the real setup.

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

**Goal:** As a user of the delivered keypad, I want live Herdr changes to converge to one ACKed authoritative generation with exact focus fenced during refresh and each tile painted as one composed image, so that the physical inbox stays current, safe, and visually stable.
**Requirements:** TBD — no requirement IDs are assigned to this inserted phase; Phase 2, Phase 3, and Phase 4 requirement ownership remains unchanged.
**Depends on:** Phase 2

**Success Criteria** (what must be TRUE):

  1. Typed Herdr lifecycle events are invalidation signals only: bursts coalesce into complete authoritative three-slot reads, and equivalent normalized state does not advance the visible generation or redraw.
  2. The host is ready for focus only after the exact current snapshot ACK; source, session, ACK, and refresh failures publish stale/offline state and fence focus without silently discarding or replaying an intent.
  3. Firmware composes each SYNC, tile, and feedback state completely in one reused bounded buffer, flushes panels sequentially through `BoardAdapter`, and activates bindings only after all three panels succeed.
  4. Installed inbox rank/sequence order, opaque generation-bound identity, three fixed agent slots, stale/offline distinction, and `FocusExecutor` as the sole `agent.focus` path remain unchanged; panel 4, Codex/menu, and full recovery remain outside this phase.
  5. Focused host/native checks, the selected USB build/metrics, and one bounded exact-device smoke prove a real Herdr change reaches a higher ACKed revision as complete images and the changed tile still focuses only its exact pane.

**Plans:** 3/3 plans executed
Plans:

**Wave 1**

- [x] 02.1-01-PLAN.md — Carry typed Herdr invalidations through coalesced complete projection, exact ACK/readiness fencing, and once-only same-session interleaved focus handling.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02.1-02-PLAN.md — Compose every firmware tile off-screen, flush each panel once, clear generation-scoped feedback, and prove resource bounds through focused native tests and selected build metrics.

**Wave 3** *(blocked on Wave 1 completion)*

- [x] 02.1-03-PLAN.md — Run one hard-deadline exact-device live-change/render/focus smoke and archive hash-addressed bounded evidence.

### Phase 3: Truthful Codex Capacity and Device Menu

**Goal:** The user can trust the dedicated Codex tile and inspect device health or adjust brightness without disrupting direct agent selection.
**Mode:** mvp
**Depends on:** Phase 02.1
**Requirements:** CODEX-01, CODEX-02, CODEX-03, CODEX-04, SYNC-03, SAFE-01, MENU-01, MENU-02, MENU-03, MENU-04
**Research flag:** Mandatory installed-Codex research must generate and inspect the active app-server schema, account authentication mode, available primary and secondary buckets, nullable fields, reset and reached-limit fields, first-read and sparse-update behavior, and an evidence-based freshness policy before the tile is declared truthful.
**Success Criteria** (what must be TRUE):

  1. The fourth display stays read-only and shows both primary and secondary Codex usage-window percentages, nearest relevant reset information, and reached-limit state exactly when the installed account supplies them.
  2. Missing or null values appear unavailable rather than zero, and current, stale, unavailable, authentication-failed, and host-offline states plus observation age are visibly distinct.
  3. Clicking the encoder opens and closes a secondary menu while all three agent keys remain direct, non-modal selection paths.
  4. The menu independently reports link, Herdr, and Codex health; last full synchronization and Codex observation; bounded troubleshooting identifiers; and firmware/protocol versions without credentials, prompts, transcripts, or host paths.
  5. The user can change and persist display brightness from the menu without changing authoritative inbox order, rendered target identity, or focus semantics.

**Plans:** TBD

Plans:

- [ ] 03-01: TBD during phase planning

**UI hint:** yes

### Phase 4: Independent Recovery and Actual-Device Acceptance

**Goal:** The user can rely on the complete keypad workflow after real component failures, restarts, and reconnections on the actual Herdr setup.
**Mode:** mvp
**Depends on:** Phase 3
**Requirements:** HARD-02, SYNC-01, SYNC-04, E2E-01
**Research flag:** Planning must turn the selected transport and measured device behavior into physical recovery and soak thresholds; acceptance evidence must come from the connected unit and installed Herdr/Codex accounts, not mocks.
**Success Criteria** (what must be TRUE):

  1. Device, bridge, Herdr, Codex, and link startup or reconnection show deterministic booting, empty, stale, unavailable, or offline states until a complete authoritative four-tile snapshot arrives.
  2. Agent keys remain disabled before that full snapshot, and disconnected or uncertain keypresses are never queued, replayed, or optimistically retried after reconnection.
  3. Link health, inbox freshness, and Codex freshness can fail and recover independently without old entries or expired usage remaining visible as current.
  4. On the actual connected device, a real highest-priority entry renders with correct identity/state, its key focuses that exact pane under documented native semantics, both real Codex windows render truthfully, and a real disconnect or restart visibly converges to current state.

**Plans:** TBD

Plans:

- [ ] 04-01: TBD during phase planning

**UI hint:** yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Physical Keypad and Proven Transport | 10/13 | In Progress|  |
| 2. Authoritative Agent Projection and Exact Focus | 4/5 | In Progress|  |
| 3. Truthful Codex Capacity and Device Menu | 0/TBD | Not started | - |
| 4. Independent Recovery and Actual-Device Acceptance | 0/TBD | Not started | - |
