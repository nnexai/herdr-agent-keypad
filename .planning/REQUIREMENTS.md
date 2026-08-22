# Requirements: Herdr Agent Keypad

**Defined:** 2026-08-16
**Core Value:** The device must make agents that need attention immediately visible and let the user switch to the right herdr agent with one physical keypress.

## v1 Requirements

Requirements for the initial release. Each maps to exactly one roadmap phase.

### Physical Device

- [x] **HARD-01**: The user can run the firmware on the connected LILYGO T-Keyboard S3 Pro with all four displays, their matching keys, the rotary encoder click, orientation, brightness control, reboot behavior, and the selected host link verified against a recorded physical map.
- [ ] **HARD-02**: The user sees deterministic booting, empty, stale, and offline screens; removed entries and expired Codex values never remain displayed as current data.
- [x] **HARD-03**: The connected device and host exchange bounded, versioned messages reliably over the transport selected by physical bring-up, with USB preferred unless measured behavior disqualifies it.

### Agent Inbox

- [x] **INBX-01**: The user sees zero to three current agent entries in exactly the order supplied by the installed `herdr-agent-inbox`, without firmware or bridge-side reprioritization.
- [x] **INBX-02**: The user sees a short session title and workspace or repository discriminator on each occupied agent key.
- [x] **INBX-03**: The user can distinguish blocked, finished/unseen, working, idle, settled, and unknown agent states through herdr-consistent color on each display key, optionally reinforced by physically mapped key-backlight or above-key LEDs, with an icon or text cue so color is never the only signal.
- [x] **INBX-04**: The user sees an explicit empty state on each unoccupied agent key rather than stale content from a removed or reordered entry.

### Agent Focus

- [x] **FOCS-01**: Pressing an occupied agent key focuses the exact herdr pane represented by the pixels the user pressed, using an opaque target identity plus host epoch and snapshot revision rather than a numeric slot.
- [x] **FOCS-02**: Pressing an empty, stale, vanished, incompatible, or offline binding visibly rejects the action and never focuses whichever agent later occupies that slot.
- [x] **FOCS-03**: The user sees focus success only after herdr acknowledges the exact target, and sees a distinct rejected, failed, or uncertain result when success cannot be established.
- [x] **FOCS-04**: Focusing from the keypad may apply Herdr's documented native seen/manual-unread effects, but it does not settle, dismiss, reply to, approve for, or invoke arbitrary actions on the agent.

### Focus-Then-Hold Input

- [x] **HOLD-01**: A short press on an occupied agent key retains the existing immediate exact-focus behavior and never emits a Space keyboard event.
- [x] **HOLD-02**: A deliberate hold emits USB HID Space-down only after Herdr has acknowledged exact focus for the same action, opaque binding, host epoch, snapshot revision, and USB session, and only while that physical key remains held.
- [x] **HOLD-03**: Release before focus acknowledgment cancels the pending hold; stale identity, late result, focus failure, unavailable source, or disconnected host never emits Space.
- [x] **HOLD-04**: Once Space-down is active, it behaves like a physical system keyboard across later focus changes and ends on physical release or USB-device removal; controlled reset and suspend paths release all keys.
- [ ] **HOLD-05**: The exact keypad passes fresh composite CDC + HID qualification for USB identity, pairing, bounded NDJSON transport, reconnect, suspend/resume, flashing, boot recovery, input latency, and stuck-key behavior before recovery acceptance begins.

### Codex Usage

- [x] **CODEX-01**: The fourth display remains dedicated to read-only Codex subscription usage and shows both primary and secondary usage-window percentages when the installed account supplies them.
- [x] **CODEX-02**: The fourth display shows the nearest relevant reset information and a reached-limit indication when those values are supplied.
- [x] **CODEX-03**: The fourth display preserves absent or null usage fields as unavailable rather than zero and visibly distinguishes current, stale, unavailable, authentication-failed, and host-offline data.
- [x] **CODEX-04**: The fourth display shows observation age or equivalent last-updated information so cached subscription usage cannot appear live.

### Synchronization and Safety

- [ ] **SYNC-01**: After device, bridge, herdr, Codex, or link startup or reconnection, the user receives a complete authoritative four-tile snapshot before any agent key is enabled.
- [x] **SYNC-02**: The device replaces snapshots atomically so the rendered pixels of any *actionable* key binding always represent exactly one logical host epoch and revision. Bindings deactivate at stage time and activate only after every panel has flushed; ordinary refreshes may reveal per panel (old complete frame to new complete frame, sequential, target ≤ 250 ms total) during which no binding is actionable. Boot, session reset, and failure paths retain the all-panel SYNC presentation. *(Amended 2026-08-18, Phase 02.2 — per-panel progressive reveal per 02.2-CONTEXT D-16 and 02.2-RESEARCH R-2; original all-panel pixel atomicity superseded, safety intent preserved.)*
- [x] **SYNC-03**: Agent-inbox freshness, Codex freshness, and device-link health are tracked and rendered independently.
- [ ] **SYNC-04**: A keypress made while disconnected or against an uncertain result is never queued, replayed, or optimistically retried after reconnection.
- [x] **SAFE-01**: Herdr and Codex credentials remain on the host; firmware receives only bounded normalized display data, opaque identities, freshness metadata, and focus results.
- [x] **SAFE-02**: The device can request only typed focus for its currently displayed binding and, after an acknowledged exact focus action, emit only the fixed USB HID Space hold defined by HOLD-01 through HOLD-04; it cannot invoke arbitrary Herdr methods, host commands, configurable keys, macros, text, or provider APIs.

### Rotary Menu

- [x] **MENU-01**: Clicking the rotary encoder opens and closes a secondary device menu without making encoder navigation part of the three direct agent-selection paths.
- [x] **MENU-02**: The rotary menu shows device-host link state, independent herdr and Codex source health, last full synchronization, and last Codex observation.
- [x] **MENU-03**: The rotary menu shows bounded troubleshooting identifiers and the installed firmware and protocol versions without exposing credentials, transcripts, raw prompts, or host filesystem paths.
- [x] **MENU-04**: The user can change and persist display brightness from the rotary menu without changing inbox ordering or key-action semantics.

### End-to-End Acceptance

- [ ] **E2E-01**: On the actual connected device, a real highest-priority Herdr entry appears with correct identity and state, its short physical keypress focuses that exact pane, a deliberate hold produces and releases the fixed system-wide Space input only after acknowledged focus, both Codex usage windows render truthfully, and the display visibly converges after a real disconnect or restart.

## v2 Requirements

Deferred capabilities tracked for later releases; they are not part of the current roadmap.

### Presentation

- **PRES-01**: The user can enable a physically validated, low-brightness ambient LED policy for blocked or unseen attention.
- **PRES-02**: The user can select a physically validated compact or large text scale from the rotary menu.
- **PRES-03**: The user can open richer diagnostic counters and hardware test views when minimum v1 diagnostics are insufficient.

### Expansion

- **EXPN-01**: The user can view additional provider subscription limits through separately validated host-side collectors.
- **EXPN-02**: The user can attach supported magnetic expansion modules to display more entries while preserving authoritative ordering.
- **EXPN-03**: The device can support additional bounded actions through an explicit authorization and configuration model.
- **EXPN-04**: The device protocol can be served by a standalone non-herdr bridge on additional host operating systems.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Arbitrary replies, AskUserQuestion choices, or approvals | Four small keys cannot safely present arbitrary context or consequences; interaction continues inside herdr. |
| Settle, dismiss, mark-read/unread, or acknowledgement commands on agent keys | v1 navigation permits only Herdr's documented native focus effects; explicit triage remains in herdr. |
| Independent firmware or bridge priority rules | The installed herdr inbox remains the sole authority for agent order and lifecycle semantics. |
| Encoder-required browsing for the core three agents | It would remove direct one-press selection and make visible key bindings modal. |
| Generic configurable macros | The fixed focus-authorized Space hold in HOLD-01 through HOLD-04 is the sole exception; arbitrary keys, text, commands, and macros remain excluded. |
| Copilot, Anthropic, or other provider collectors in v1 | Each provider requires separate API, authentication, null, and freshness validation. |
| Standalone public server or broad hook ecosystem in v1 | Personal herdr integration must be proven before extracting a general service boundary. |
| Credentials, raw prompts, transcripts, chain-of-thought, or host paths on firmware | These are unnecessary for selection, unreadable on 128x128 panels, and violate the host-side security boundary. |
| Queued or replayed keypresses | The visible target may change during an outage, making replay unsafe. |
| Hybrid transport, battery portability, or expansion modules in v1 | They add authority, power, provisioning, or discovery work unrelated to validating the connected Linux/herdr loop. |
| Unbudgeted decorative animation | Motion can obscure stale/error states. *(Amended 2026-08-18, Phase 02.2 — per 02.2-CONTEXT D-13/D-14 and 02.2-RESEARCH R-1, theme-specific ambient motion is permitted under a measured animation budget: complete compose-then-flush frames only, total animation flush time ≤ 30 % of loop wall time measured on device, degradation to half cadence then static frames, semantic states/fences/feedback always preempt, no per-frame allocation. The blanket exclusion is superseded; unbudgeted or semantics-obscuring motion remains out of scope.)* |

## Traceability

Every v1 requirement maps to exactly one roadmap phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| HARD-01 | Phase 1 | Complete |
| HARD-02 | Phase 4 | Pending |
| HARD-03 | Phase 1 | Complete |
| INBX-01 | Phase 2 | Complete |
| INBX-02 | Phase 2 | Complete |
| INBX-03 | Phase 2 | Complete |
| INBX-04 | Phase 2 | Complete |
| FOCS-01 | Phase 2 | Complete |
| FOCS-02 | Phase 2 | Complete |
| FOCS-03 | Phase 2 | Complete |
| FOCS-04 | Phase 2 | Complete |
| HOLD-01 | Phase 03.2 | Complete |
| HOLD-02 | Phase 03.2 | Complete |
| HOLD-03 | Phase 03.2 | Complete |
| HOLD-04 | Phase 03.2 | Complete |
| HOLD-05 | Phase 03.2 | Pending |
| CODEX-01 | Phase 3 | Complete |
| CODEX-02 | Phase 3 | Complete |
| CODEX-03 | Phase 3 | Complete |
| CODEX-04 | Phase 3 | Complete |
| SYNC-01 | Phase 4 | Pending |
| SYNC-02 | Phase 2 | Complete |
| SYNC-03 | Phase 3 | Complete |
| SYNC-04 | Phase 4 | Pending |
| SAFE-01 | Phase 3 | Complete |
| SAFE-02 | Phase 03.2 | Complete |
| MENU-01 | Phase 3 | Complete |
| MENU-02 | Phase 3 | Complete |
| MENU-03 | Phase 3 | Complete |
| MENU-04 | Phase 3 | Complete |
| E2E-01 | Phase 4 | Pending |

**Coverage:**

- v1 requirements: 31 total
- Mapped to phases: 31
- Unmapped: 0

---
*Requirements defined: 2026-08-16*
*Last updated: 2026-08-21 — Phase 03.2 adds focus-authorized system-wide USB HID Space hold requirements and narrows SAFE-02's fixed-input exception.*
*Previous amendment: 2026-08-18 — Phase 02.2 amendments to SYNC-02 and the decorative-animation exclusion (R-1/R-2).*
