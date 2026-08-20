# Phase 3: Truthful Codex Capacity and Device Menu - Context

**Gathered:** 2026-08-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement the host-owned Codex capacity collector and normalized fourth-tile projection, independent link/Herdr/Codex freshness, and the encoder-operated device menu for health, diagnostics, and persistent brightness. Preserve the existing three direct generation-bound agent focus paths, the Phase 02.2 theme and LED settings, bounded protocol admission, and the host-only credential boundary.

</domain>

<decisions>
## Implementation Decisions

### Codex tile presentation
- **D-01** Render fixed primary and secondary usage rows with integer used percentages. Missing or null windows render `N/A`, never `0%`.
- **D-02** Show the nearest supplied future reset across primary and secondary, labeled by its window. If neither window supplies a reset, render `RESET N/A`.
- **D-03** Show a dominant theme-equivalent `LIMIT` alert only when Codex supplies a reached-limit field. Missing or null reached state is unknown and must not produce an `OK` cue.
- **D-04** Keep the last complete values under an unmistakable `STALE` or `OFFLINE` veil with observation age. If no complete observation exists, show only the state and `N/A` fields.

### Freshness and failure semantics
- **D-05** Poll for a full Codex rate-limit snapshot every 5 minutes. Mark the observation stale after 15 minutes without a valid full read or valid sparse merge.
- **D-06** A validated sparse `account/rateLimits/updated` notification may refresh observation age only after it merges into a known full snapshot. A sparse update can never establish the first current state.
- **D-07** Render `AUTH REQUIRED` only for observed account or authentication failures. Classify Codex process, JSONL, or request failures as `CODEX OFFLINE`; classify a lost device-to-host session as `HOST OFFLINE`. Never infer authentication failure from a timeout.
- **D-08** Clear cached capacity values immediately after an account or authentication change and require a new full limits read before presenting current values.

### Menu structure and interaction
- **D-09** Extend the existing menu into one bounded root list: `THEME`, `LEDS`, `BRIGHTNESS`, `HEALTH`, `ABOUT`, `CLOSE`. Rotation remains clamped, and the panel shows a three-row window around the cursor.
- **D-10** Encoder click opens the menu, enters the selected row, confirms an edited value, returns from a read-only detail page, or activates `CLOSE`. Do not add long-press or double-click behavior.
- **D-11** Agent keys 1-3 focus their exact displayed agents immediately while the menu remains open. The menu never intercepts these keys; focus feedback remains on the agent tile and mapped LED zone.
- **D-12** Close the menu after 30 seconds without encoder activity and discard any unconfirmed preview. Live health updates do not move the cursor or reset the inactivity timer.

### Brightness and diagnostics
- **D-13** Preview display brightness live in 10% steps from 10% through 100%, beginning at the stored value. Encoder click confirms. Closing or timing out reverts an unconfirmed preview. Exclude 0% so the device cannot appear unpowered.
- **D-14** Read existing schema-v1 theme and LED settings unchanged, use 80% brightness in memory, and write schema v2 only after explicit setting confirmation. Do not write migration data during boot.
- **D-15** `HEALTH` shows independent link, Herdr, and Codex states, last full synchronization age, last Codex observation age, and one bounded error code. `ABOUT` shows firmware, protocol, and bridge versions plus short device, session, and revision suffixes. Never expose account identity, credentials, host paths, raw errors, prompts, or transcripts.
- **D-16** Apply and persist brightness entirely on-device through `SettingsStore` and `BoardAdapter`. Brightness works while the host is disconnected and never changes snapshot generation, inbox order, target identity, or focus state.

### the agent's Discretion
- **D-17** Choose exact typography, abbreviations, theme-specific geometry, safe bounded identifier lengths, timeout mechanics, Codex request timeout, retry backoff, and protocol field encoding while preserving the decisions above and the existing 4096-byte framed-message bound.
- **D-18** Choose whether a valid sparse update triggers an immediate full refetch in addition to its accepted merge, provided it cannot establish the first snapshot or clear omitted fields.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `host/herdr_keypad/src/herdr_keypad/bridge.py` already owns permanent Herdr snapshot publication and the USB device session; Phase 3 should extend this bridge rather than add a second daemon.
- `firmware/src/app/agent_projection.{h,cpp}` owns staged generation state, four-panel rendering, binding fencing, and panel-4 dispatch.
- `firmware/src/app/menu_controller.{h,cpp}` already implements the closed, row-select, and value-cycle menu state machine with explicit confirmation and revert-on-close behavior.
- `firmware/src/app/settings_store.{h,cpp}` is the device-only NVS boundary for confirmed theme and LED settings. `BoardAdapter::setBrightness()` is the accepted display-brightness hardware seam.
- `firmware/src/ui/theme_*.cpp` contains four deliberate Codex `N/A`/`UNAVAILABLE` panel-4 placeholders and the existing theme-specific menu renderers to replace with normalized data, not a second rendering stack.
- The Phase 1 host and firmware codecs, `ProtocolSession`, `UsbDeviceSession`, schema fixtures, canonical digest, and 4096-byte line limit remain the sole wire-admission path.

### Established Patterns
- The host owns provider authentication, interpretation, source timestamps, and normalized snapshots. Firmware receives bounded device-scoped values only.
- Herdr ordering and opaque focus identities remain authoritative and generation-bound. Direct keys 1-3 dispatch before menu polling and remain independent of encoder state.
- Firmware stages complete render state, flushes panels sequentially through `BoardAdapter`, and only then enables bindings.
- Settings persist only after explicit confirmation. Missing or invalid settings fall back in memory without boot-time write-back.
- Theme and LED grammars consume shared normalized state; panel 4 and health LEDs must not invent separate provider semantics.

### Integration Points
- Add a supervised Codex app-server collector beneath the permanent host bridge, with full-read baseline, presence-aware sparse merge, independent freshness, and redacted error classification.
- Extend the closed v2 host projection, protocol schema, host validator, firmware codec/session dispatch, and fixtures with normalized Codex and bounded diagnostic state. Do not bypass the existing framing or snapshot commit path.
- Extend `RenderState` and `ThemeRenderer::composePanel4()` for current, stale, unavailable, authentication-required, Codex-offline, and host-offline capacity states.
- Extend `MenuController`, `MenuState`, theme menu renderers, and `SettingsStore` schema migration for brightness, health, about, close, and inactivity behavior.
- Preserve `firmware/src/main.cpp::reportAgentKey()` ahead of USB/menu polling. Extend `pollMenu()` and `refreshMenuPresentation()` without routing keys 1-3 through menu state.

</code_context>

<specifics>
## Specific Ideas

Use fixed primary and secondary rows, nearest-reset labeling, a dominant reached-limit cue, and visible observation age across all four existing display languages. Keep one flat six-row root menu with three visible rows, local brightness preview and confirmation, read-only health/about pages, and no new encoder gesture grammar.

</specifics>

<deferred>
## Deferred Ideas

- Other subscription providers remain deferred to v2.
- Display-off brightness, richer diagnostic counters, raw upstream errors, and host-managed brightness remain out of scope.

</deferred>
