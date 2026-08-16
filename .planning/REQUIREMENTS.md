# Requirements: Herdr Agent Keypad

**Defined:** 2026-08-16
**Core Value:** The device must make agents that need attention immediately visible and let the user switch to the right herdr agent with one physical keypress.

## v1 Requirements

Requirements for the initial release. Each maps to exactly one roadmap phase.

### Physical Device

- [ ] **HARD-01**: The user can run the firmware on the connected LILYGO T-Keyboard S3 Pro with all four displays, their matching keys, the rotary encoder click, orientation, brightness control, reboot behavior, and the selected host link verified against a recorded physical map.
- [ ] **HARD-02**: The user sees deterministic booting, empty, stale, and offline screens; removed entries and expired Codex values never remain displayed as current data.
- [ ] **HARD-03**: The connected device and host exchange bounded, versioned messages reliably over the transport selected by physical bring-up, with USB preferred unless measured behavior disqualifies it.

### Agent Inbox

- [ ] **INBX-01**: The user sees zero to three current agent entries in exactly the order supplied by the installed `herdr-agent-inbox`, without firmware or bridge-side reprioritization.
- [ ] **INBX-02**: The user sees a short session title and workspace or repository discriminator on each occupied agent key.
- [ ] **INBX-03**: The user can distinguish blocked, finished/unseen, working, idle, settled, and unknown agent states through herdr-consistent color on each display key, optionally reinforced by physically mapped key-backlight or above-key LEDs, with an icon or text cue so color is never the only signal.
- [ ] **INBX-04**: The user sees an explicit empty state on each unoccupied agent key rather than stale content from a removed or reordered entry.

### Agent Focus

- [ ] **FOCS-01**: Pressing an occupied agent key focuses the exact herdr pane represented by the pixels the user pressed, using an opaque target identity plus host epoch and snapshot revision rather than a numeric slot.
- [ ] **FOCS-02**: Pressing an empty, stale, vanished, incompatible, or offline binding visibly rejects the action and never focuses whichever agent later occupies that slot.
- [ ] **FOCS-03**: The user sees focus success only after herdr acknowledges the exact target, and sees a distinct rejected, failed, or uncertain result when success cannot be established.
- [ ] **FOCS-04**: Focusing from the keypad may apply Herdr's documented native seen/manual-unread effects, but it does not settle, dismiss, reply to, approve for, or invoke arbitrary actions on the agent.

### Codex Usage

- [ ] **CODEX-01**: The fourth display remains dedicated to read-only Codex subscription usage and shows both primary and secondary usage-window percentages when the installed account supplies them.
- [ ] **CODEX-02**: The fourth display shows the nearest relevant reset information and a reached-limit indication when those values are supplied.
- [ ] **CODEX-03**: The fourth display preserves absent or null usage fields as unavailable rather than zero and visibly distinguishes current, stale, unavailable, authentication-failed, and host-offline data.
- [ ] **CODEX-04**: The fourth display shows observation age or equivalent last-updated information so cached subscription usage cannot appear live.

### Synchronization and Safety

- [ ] **SYNC-01**: After device, bridge, herdr, Codex, or link startup or reconnection, the user receives a complete authoritative four-tile snapshot before any agent key is enabled.
- [ ] **SYNC-02**: The device replaces snapshots atomically so the rendered pixels and key bindings always represent one logical host epoch and revision despite sequential panel updates.
- [ ] **SYNC-03**: Agent-inbox freshness, Codex freshness, and device-link health are tracked and rendered independently.
- [ ] **SYNC-04**: A keypress made while disconnected or against an uncertain result is never queued, replayed, or optimistically retried after reconnection.
- [ ] **SAFE-01**: Herdr and Codex credentials remain on the host; firmware receives only bounded normalized display data, opaque identities, freshness metadata, and focus results.
- [ ] **SAFE-02**: The device can request only the typed focus action for its currently displayed binding and cannot invoke arbitrary herdr methods, host commands, or provider APIs.

### Rotary Menu

- [ ] **MENU-01**: Clicking the rotary encoder opens and closes a secondary device menu without making encoder navigation part of the three direct agent-selection paths.
- [ ] **MENU-02**: The rotary menu shows device-host link state, independent herdr and Codex source health, last full synchronization, and last Codex observation.
- [ ] **MENU-03**: The rotary menu shows bounded troubleshooting identifiers and the installed firmware and protocol versions without exposing credentials, transcripts, raw prompts, or host filesystem paths.
- [ ] **MENU-04**: The user can change and persist display brightness from the rotary menu without changing inbox ordering or key-action semantics.

### End-to-End Acceptance

- [ ] **E2E-01**: On the actual connected device, a real highest-priority herdr entry appears with correct identity and state, its physical key focuses that exact pane under the documented native focus semantics, both Codex usage windows render truthfully, and the display visibly converges after a real disconnect or restart.

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
| Generic configurable macros | Configuration, authorization, and failure semantics would dilute the physical inbox and expand its attack surface. |
| Copilot, Anthropic, or other provider collectors in v1 | Each provider requires separate API, authentication, null, and freshness validation. |
| Standalone public server or broad hook ecosystem in v1 | Personal herdr integration must be proven before extracting a general service boundary. |
| Credentials, raw prompts, transcripts, chain-of-thought, or host paths on firmware | These are unnecessary for selection, unreadable on 128x128 panels, and violate the host-side security boundary. |
| Queued or replayed keypresses | The visible target may change during an outage, making replay unsafe. |
| Hybrid transport, battery portability, or expansion modules in v1 | They add authority, power, provisioning, or discovery work unrelated to validating the connected Linux/herdr loop. |
| Decorative animation | Motion can obscure stale/error states and compete with the device's ambient attention purpose. |

## Traceability

Roadmap creation assigns every v1 requirement to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|

**Coverage:**
- v1 requirements: 26 total
- Mapped to phases: 0
- Unmapped: 26

---
*Requirements defined: 2026-08-16*
*Last updated: 2026-08-16 after research-based v1 scoping*
