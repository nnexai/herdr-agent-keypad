# Herdr Agent Keypad

## What This Is

Herdr Agent Keypad is dedicated companion hardware for a personal AI-agent workflow. A LILYGO T-Keyboard S3 Pro presents Herdr's live agent inbox on its four display keys: up to three keys represent the agents currently highest in the inbox, while the fourth shows Codex subscription-limit information. A short agent-key press focuses that exact agent. A deliberate hold first requires the same exact focus acknowledgment and then behaves as a fixed system-wide held Space key through USB HID; deeper interaction remains in the focused application.

The initial product consists of firmware for the keypad and a host-side bridge implemented as a herdr plugin. It starts with the user's current Linux/herdr setup, while keeping the protocol and firmware boundaries clean enough to later become a reusable firmware, device library, herdr integration, and standalone server for hook-based integrations.

## Core Value

The device must make agents that need attention immediately visible and let the user switch to the right herdr agent with one physical keypress.

## Requirements

### Validated

- [x] The connected keypad shows the authoritative one-to-three highest-priority Herdr inbox entries. Validated through Phases 2, 02.1, and 02.2.
- [x] Each agent tile communicates identity, state, source health, and focus feedback on the physical device. Validated through Phases 2 and 02.2.
- [x] Each agent display key focuses only its exact generation-bound Herdr agent. Validated through Phases 2, 02.1, and 02.2.
- [x] Four display themes and four LED grammars are selectable from a non-modal encoder menu without weakening direct focus or freshness fencing. Validated in Phase 02.2.

### Active

- [ ] The fourth display shows current Codex subscription-limit information and makes unavailable or stale data explicit.
- [ ] The firmware and herdr plugin/bridge communicate reliably and recover visibly from disconnects or stale data.
- [ ] The physical device works end to end on the user's actual herdr setup.
- [ ] A short agent-key press remains focus-only, while a deliberate hold emits and releases a real system-wide Space key only after exact focus acknowledgment.
- [ ] The exact keypad passes a composite CDC + HID feasibility gate before replacing the proven CDC/JTAG transport.

### Out of Scope

- Responding to prompts, choosing AskUserQuestion options, approving changes, or performing other deep agent interaction on the keypad — the fixed held Space input is the sole interaction exception; the application receiving that ordinary keyboard input owns its meaning.
- A general-purpose configurable macro system — the Phase 03.2 Space hold is fixed and focus-authorized; arbitrary keys, text, commands, and macros remain out of scope.
- Copilot, Anthropic, and other provider subscription collectors — planned follow-on integrations after the Codex display is proven.
- A standalone non-herdr server and hook-integration ecosystem — future generalization, not part of the personal-first v1.
- Hosted GitHub Actions execution, public artifact or release publication, signing, notarization, and release upload. Phase 4 keeps the release workflow and aggregation machinery ready for this later release work, but no numbered release phase exists yet.
- Battery operation or portability — the connected device can remain USB powered for v1.

## Context

- The physical LILYGO T-Keyboard S3 Pro is already in hand and connected.
- The usable interaction surface is four 128x128 display keys, RGB LEDs, and a clickable rotary encoder. The encoder is less pleasant to use and should expose secondary or infrequent functionality rather than the primary selection flow.
- The installed `herdr-agent-inbox` plugin already provides the desired source ordering and semantics: blocked agents first, then finished/unseen, working, idle, and settled. Device entries must remain dynamic and mirror that ordering rather than implement a competing priority model.
- The installed inbox already tracks session titles, state, runtimes, workspace rollups, settle/unread flags, and pane identity through herdr's public socket API. The new bridge should build on those supported interfaces.
- The fourth display is dedicated to Codex subscription limits in v1, rather than aggregate agent counts or rotating ambient pages.
- Work Louder's Codex Micro is interaction inspiration: physical controls reflect live agent state and make high-frequency agent actions tactile. The S3 Pro design must adapt that idea to a much smaller four-key surface.
- The preliminary Hermes research note is input, not a final plan. Its useful principles include host-side credentials, normalized device data, truthful stale/offline states, bounded actions, and validating the real hardware early.
- The longer-term direction is a separable firmware, reusable device library, herdr plugin, and potentially a standalone bridge/server. v1 may remain tailored to this machine as long as it does not unnecessarily prevent that evolution.
- Phase 4 closes on the implemented Rust release-automation and bundle contracts plus a locally built, installed, and restarted Linux native bridge. No hosted Linux or macOS GitHub Actions job or public release ran; those operations remain later release work.

## Constraints

- **Hardware**: Four display keys, RGB LEDs, and a clickable encoder on the connected LILYGO T-Keyboard S3 Pro — the primary workflow must fit this exact surface.
- **Interaction**: Agent selection must be a direct keypress — the encoder and multi-step navigation cannot be required for the core loop.
- **Source of truth**: Agent entries and their order come from the existing herdr inbox — the device must not invent a separate lifecycle.
- **Selection semantics**: A short press focuses its agent pane only. A deliberate hold may emit only fixed USB HID Space after that exact focus is acknowledged. Neither gesture automatically settles, dismisses, acknowledges, responds, or approves.
- **Transport**: USB remains the selected wired transport. Phase 03.2 first tests and requalifies composite CDC + HID on the exact board. A pass commits that direction without exploring alternatives; only a recorded failure permits explicit reconsideration of another hold backend.
- **Credentials**: Provider credentials and authenticated Codex access stay on the host — the firmware receives only device-scoped, normalized data.
- **Truthfulness**: Offline, unavailable, and stale agent or usage data must be visibly distinguishable from current data.
- **Compatibility**: v1 targets the user's current Linux/Herdr installation, while the fixed Space hold must use ordinary USB HID semantics rather than CLI-specific integration so the device input itself remains operating-system portable.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Make the product an agent inbox first | Missing or overlooking agents needing attention is the primary problem; broad control would dilute the core loop | — Pending |
| Mirror `herdr-agent-inbox` ordering | The existing inbox already embodies the user's preferred triage semantics and should remain authoritative | — Pending |
| Use up to three keys as dynamic agent entries | Direct key-to-agent mapping provides glanceable state and one-press selection on the four-key device | — Pending |
| Reserve the fourth display for Codex limits | Remaining subscription capacity is valuable ambient information and does not require encoder navigation | — Pending |
| Keep deeper interaction inside herdr | Detecting and safely reproducing arbitrary agent prompts on four keys adds complexity without improving the primary selection workflow | — Pending |
| Keep general macros out; permit one fixed Space hold | A system-wide physical Space hold covers the desired push-to-talk gesture without creating configurable keys, text, commands, or CLI-specific integrations | **Selected for Phase 03.2**, gated on acknowledged exact focus |
| Prefer USB while researching transport | The device is already wired for power, but the exact USB class composition must be proven on real hardware | **Hardware CDC/JTAG validated in Phase 1; composite CDC + HID is the sole Phase 03.2 feasibility target, with alternatives considered only after a recorded failure** |
| Require physical end-to-end validation for v1 | A simulated bridge or renderer alone does not establish that the companion hardware is useful or reliable | **Phase 1 is the original hardware baseline; Phase 03.2 must add exact-device composite-input evidence before Phase 5 acceptance** |
| Preserve the long baseline; qualify the changed composition separately | Repeating an unchanged 30-minute profile adds operator cost, but replacing the USB class composition invalidates transport assumptions | Do not rerun the legacy profile as if unchanged; run a bounded Phase 03.2 composite CDC + HID qualification covering the new risks |
| Separate implementation readiness from hosted release publication | The native Linux deployment and deterministic cross-target release machinery can be proven locally without fabricating macOS or public-release results | **Phase 4 complete; hosted Linux/macOS execution and publication parked for a later release phase** |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-30 after closing Phase 4 on local Linux deployment and release-contract readiness while parking hosted publication*
