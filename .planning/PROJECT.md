# Herdr Agent Keypad

## What This Is

Herdr Agent Keypad is dedicated companion hardware for a personal AI-agent workflow. A LILYGO T-Keyboard S3 Pro presents herdr's live agent inbox on its four display keys: up to three keys represent the agents currently highest in the inbox, while the fourth shows Codex subscription-limit information. Pressing an agent key tells herdr to focus that agent so the actual conversation and any deeper interaction continue in herdr.

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

### Out of Scope

- Responding to prompts, choosing AskUserQuestion options, approving changes, or performing other deep agent interaction on the keypad — v1 selects the agent; interaction continues inside herdr.
- A general-purpose configurable macro system — useful later for herdr actions, voice input, and other applications, but deferred until the inbox loop works reliably.
- Copilot, Anthropic, and other provider subscription collectors — planned follow-on integrations after the Codex display is proven.
- A standalone non-herdr server and hook-integration ecosystem — future generalization, not part of the personal-first v1.
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

## Constraints

- **Hardware**: Four display keys, RGB LEDs, and a clickable encoder on the connected LILYGO T-Keyboard S3 Pro — the primary workflow must fit this exact surface.
- **Interaction**: Agent selection must be a direct keypress — the encoder and multi-step navigation cannot be required for the core loop.
- **Source of truth**: Agent entries and their order come from the existing herdr inbox — the device must not invent a separate lifecycle.
- **Selection semantics**: Selecting an entry focuses its agent pane only — no automatic settle, dismiss, acknowledge, or response.
- **Transport**: The device requires wired power and USB is preferred, but USB serial versus Wi-Fi or a hybrid must be validated through research and physical bring-up before it is locked.
- **Credentials**: Provider credentials and authenticated Codex access stay on the host — the firmware receives only device-scoped, normalized data.
- **Truthfulness**: Offline, unavailable, and stale agent or usage data must be visibly distinguishable from current data.
- **Compatibility**: v1 targets the user's current Linux host and herdr installation; broader operating-system support is later work.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Make the product an agent inbox first | Missing or overlooking agents needing attention is the primary problem; broad control would dilute the core loop | — Pending |
| Mirror `herdr-agent-inbox` ordering | The existing inbox already embodies the user's preferred triage semantics and should remain authoritative | — Pending |
| Use up to three keys as dynamic agent entries | Direct key-to-agent mapping provides glanceable state and one-press selection on the four-key device | — Pending |
| Reserve the fourth display for Codex limits | Remaining subscription capacity is valuable ambient information and does not require encoder navigation | — Pending |
| Keep deeper interaction inside herdr | Detecting and safely reproducing arbitrary agent prompts on four keys adds complexity without improving the primary selection workflow | — Pending |
| Defer general macros | Voice input and configurable actions are useful, but the physical inbox must first be reliable | — Pending |
| Prefer USB while researching transport | The device is already wired for power, but the best supported data path must be proven on real hardware | **Validated in Phase 1 Plan 01-06** — the exact paired unit passed strict USB qualification |
| Require one physical end-to-end validation for v1 | A simulated bridge or renderer alone does not establish that the companion hardware is useful or reliable | **Validated once in Phase 1 Plan 01-06** — the immutable qualification result is the hardware baseline |
| Do not rerun the long qualification profile | The 30-minute profile establishes a one-time hardware/transport baseline; repeating it adds operator cost without proving later host-only changes | Future work consumes the hash-bound result and uses bounded targeted smoke checks; the long profile is never rerun |

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
*Last updated: 2026-08-20 after Phase 02.2 theme, LED, menu, and exact-device verification*
