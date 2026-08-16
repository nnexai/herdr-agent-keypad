# Feature Research

**Domain:** Dedicated physical AI-agent inbox and focus control surface
**Device/workflow:** LILYGO T-Keyboard S3 Pro; personal Linux/herdr setup
**Researched:** 2026-08-16
**Confidence:** MEDIUM

## Scope and Product Principle

The useful product is not a miniature chat client or a generic macro deck. It is an ambient, four-tile projection of an already-authoritative herdr inbox: up to three physical display keys show the current highest-priority agents, and the fourth key shows read-only Codex subscription limits. Pressing an agent tile performs one bounded action—focus that exact agent in herdr—and does not settle, dismiss, mark read, reply, approve, or otherwise mutate inbox state.

The installed `herdr-agent-inbox` already defines the queue semantics: blocked → finished/unseen → working → idle → settled, with recency tie-breaking described by the plugin. The keypad must consume that ordered result rather than reconstruct the lifecycle from raw agent events. This is both a scope boundary and a correctness property.

Complexity below includes firmware, host bridge/plugin behavior, and proving the behavior on the connected device. Dependencies name prerequisite features, not technology choices.

## Feature Landscape

### Table Stakes (Users Expect These)

Missing any P1 item makes the physical inbox misleading, unsafe, or slower than focusing an agent in herdr directly.

| Feature | Why Expected | Complexity | Dependencies / Notes |
|---------|--------------|------------|----------------------|
| **Authoritative top-three projection** | The device is useful only if its one to three agent tiles match the installed inbox's current highest-priority entries and order. | MEDIUM | Depends on ordered inbox snapshot and stable pane identities. Render 0–3 entries; unused tiles must visibly say empty rather than retain an old agent. Never implement a second priority calculation in firmware or the bridge. |
| **Glanceable agent identity** | A title alone can collide across repositories; a color alone is not identity. The user must choose correctly without opening herdr first. | MEDIUM | Depends on normalized display fields. Each 128×128 tile should prioritize a short session title, then a compact workspace/repository discriminator. Truncate deterministically; do not shrink text below legibility. |
| **Redundant agent state and attention tier** | The user needs to distinguish blocked, finished/unseen, working, idle, and settled at a glance. Color-only encoding fails under glare, peripheral viewing, and color-vision differences. | MEDIUM | Depends on authoritative ordered snapshot and identity layout. Use herdr-compatible color plus an icon/word; optionally add age or time-in-state only if it remains readable. Settled entries appear only when they truly occupy a top-three slot. |
| **Atomic tile-to-agent binding** | A tile can be repainted between glance and press. Focusing whichever agent now occupies “slot 1” would select the wrong conversation. | HIGH | Depends on stable pane identity, snapshot revision, and host validation. A press carries the opaque identity/revision bound to the pixels currently shown; the host focuses that target or rejects the stale binding. Display and binding change as one logical update. |
| **Direct one-press focus** | The core value is faster switching. Requiring encoder navigation or a mode menu defeats it. | HIGH | Depends on atomic binding and a supported herdr focus operation. Keys 1–3 focus their displayed agents directly. Focus is the only semantic effect; no implicit settle, unread clearing, acknowledgement, dismissal, or reply. Empty keys are safe no-ops with visible feedback. |
| **Focus outcome feedback** | Physical input without confirmation causes duplicate presses and uncertainty, especially during host lag or disconnects. | MEDIUM | Depends on focus request/response correlation. Show a brief accepted/focused confirmation only after host acknowledgement; show a distinct rejection/offline indication on failure. Feedback must not falsely claim that focus occurred. |
| **Dedicated truthful Codex limits tile** | The fourth display is reserved for capacity, and quota data is operationally useful only when its meaning and freshness are clear. | HIGH | Depends on a host-side Codex collector and normalized timestamps. Prefer a compact primary/secondary-window summary using `usedPercent`, reset time, and reached state. Preserve `null` as unavailable—not zero—and never infer a subscription limit from token counts. Read-only in v1. |
| **Current / stale / unavailable truth states** | A plausible old value is worse than no value. Agent and quota data can age independently. | MEDIUM | Depends on observation timestamps, freshness policy, and connection state. Visually distinguish current, stale cached, unavailable/no sample, and host/device offline. Show age or last-observed time on quota; dim/mark cached inbox tiles. Do not let transport connectivity alone imply provider freshness. |
| **Cold-start and reconnect full resynchronization** | USB cables, Wi-Fi, firmware, the plugin, herdr, and Codex collection can restart independently. Recovery must require no manual tile repair. | HIGH | Depends on handshake, version compatibility, full snapshot, and atomic binding. On reconnect fetch/push a full current snapshot before accepting focus; do not rely on missed deltas. Replace cached state atomically and never replay button presses queued while disconnected. |
| **Deterministic empty, booting, and offline screens** | Blank or leftover pixels look like valid assignments on a display-key device. | LOW | Depends on renderer state model. Every tile has an explicit state: booting, empty, current entry, stale entry, offline, or diagnostic. Clear removed entries and old quota values deliberately. |
| **Physical key/display/LED bring-up** | The purchased device is the acceptance surface; simulator-only correctness cannot establish panel order, key mapping, orientation, brightness, debounce, or LED correspondence. | MEDIUM | Prerequisite for all interaction features. Exercise all four 128×128 host displays independently, all five keys, encoder motion/click if present, 14 RGB LEDs, backlight, reboot, and the actual data link. Record the verified logical-to-physical map. |
| **On-device connection and protocol diagnostics** | A desk appliance needs to explain “nothing happened” without attaching a debugger first. | MEDIUM | Depends on bring-up and handshake. An infrequent encoder/boot-chord diagnostics surface may show device/firmware protocol versions, host link state, last full sync, last Codex observation, last focus result, and key/display test. It must not be required for normal selection. |
| **Host-side credential boundary** | The device is physically accessible and firmware storage is not the right home for herdr/Codex account credentials. | MEDIUM | Depends on host bridge boundary. Firmware receives only normalized display data, opaque agent IDs, revisions, and bounded focus results. No raw OAuth tokens, provider cookies, transcripts, or arbitrary host commands. |
| **Actual-device end-to-end operation** | v1 is only validated when a real top-ranked inbox agent appears on the connected keypad and its key focuses the same pane. | HIGH | Depends on all P1 data, rendering, binding, link, and focus features. The scenario must also demonstrate a quota tile and visible recovery after at least one real disconnect/restart. |

### Differentiators (Competitive Advantage)

These features make the product meaningfully better for this particular workflow rather than merely reproducing a generic macro pad.

| Feature | Value Proposition | Complexity | Dependencies / Notes |
|---------|-------------------|------------|----------------------|
| **Herdr-native attention order, not fixed shortcuts** | The three keys continuously become the three agents most deserving attention across workspaces; no manual profiles or per-agent key setup. | MEDIUM | Depends on authoritative top-three projection. The installed inbox remains the single policy owner. **v1 differentiator.** |
| **Identity + state on the key itself** | Unlike printed caps or RGB-only agent keys, each key can explain who it represents and why it is prominent. | MEDIUM | Depends on legible identity/state layout and actual panel readability testing. Title, workspace discriminator, state symbol, and restrained age cue should form a consistent visual grammar. **v1 differentiator.** |
| **Focus-only safety contract** | A physical press is reversible navigation, not hidden triage mutation. This reduces fear of using an always-on surface. | MEDIUM | Depends on a dedicated focus command and host-side action allowlist. Audit focus results, not user conversation contents. **v1 differentiator.** |
| **Quota alongside attention without a mode switch** | The fourth always-visible tile answers “can I keep using Codex?” while the other three answer “which agent needs me?” | HIGH | Depends on truthful Codex tile and four-panel renderer. Keep the fourth assignment fixed; do not rotate it with inbox slots. **v1 differentiator.** |
| **Race-safe dynamic reassignment** | Rapid inbox reordering remains trustworthy: a press applies to the identity the user saw, or fails visibly. | HIGH | Depends on atomic tile binding, revisioned snapshots, and host revalidation. This is more important than ornamental animation. **v1 differentiator.** |
| **Ambient, restrained LED escalation** | Peripheral light can reveal that a blocked/unseen agent exists without reading tiny screens constantly. | MEDIUM | Depends on authoritative state and verified LED mapping. Use a small, documented palette and low brightness; displays remain the source of identity. Avoid continuous decorative effects. **v1 candidate if bring-up is stable; otherwise v1.x.** |
| **Self-explaining field diagnostics** | The same four panels can identify link, mapping, freshness, and version problems, materially improving a one-off personal hardware integration. | MEDIUM | Depends on diagnostics and explicit renderer states. Access through the secondary encoder/boot chord so direct keys remain direct. **v1.x unless needed to complete bring-up.** |
| **Local presentation preferences** | Brightness and perhaps compact text scale can be tuned for the user's desk without changing inbox semantics. | LOW | Depends on verified display/LED control and persisted non-sensitive settings. Encoder is appropriate because this is infrequent. **v1.x.** |
| **Expansion-board awareness** | Later magnetic modules could display more agents without changing source ordering. | HIGH | Depends on stable v1 protocol, board discovery, power validation, and a defined overflow layout. Additional modules are not needed to validate the four-key core. **v2+.** |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Avoided Complexity | Alternative |
|---------|---------------|-----------------|-------------------|-------------|
| **Settle/dismiss/mark-read on agent press** | It appears to combine focus and triage into one fast action. | It violates focus-only semantics, can lose an unread/blocked signal, and makes accidental presses destructive. | HIGH | Press focuses only. Perform settle/unread actions in herdr, where context and existing controls are visible. |
| **Independent keypad priority rules** | Firmware-local sorting may appear faster or more customizable. | It creates two inboxes that disagree and cannot faithfully reproduce plugin settle/unread policy. | HIGH | Consume the installed inbox's ordered output and project the first three entries exactly. |
| **Encoder-required browsing for the core three agents** | It accommodates more than three agents on four displays. | It removes direct key selection and makes the visible tile-to-key relationship modal. | MEDIUM | Keep direct keys bound to the current top three; use herdr for the complete queue. Revisit overflow only after v1 validation. |
| **Arbitrary replies, AskUserQuestion choices, or approvals** | A “complete” agent console sounds more capable. | Four tiny keys cannot safely present arbitrary context or consequences; prompt forms vary and stale choices are hazardous. | VERY HIGH | Focus the agent, then interact in herdr. The keypad is a navigator, not a conversation client. |
| **General-purpose configurable macros** | Display-key decks commonly launch workflows and shortcuts. | Configuration, action authorization, profiles, and failure semantics would dilute the attention loop and expand the attack surface. | HIGH | Ship one enumerated action: focus displayed agent. Consider macros only after the inbox loop is proven. |
| **Copilot/Anthropic/other provider collectors** | A unified quota dashboard is attractive. | Account types, APIs, permissions, and limit meanings differ; one 128×128 quota tile cannot truthfully normalize them in v1. | HIGH per provider | Reserve the fourth tile for Codex only and design explicit unavailable fields; add providers as separately validated follow-ons. |
| **Standalone server or broad hook ecosystem** | It promises reuse beyond herdr. | It adds deployment, authentication, persistence, and public API design before the personal workflow is validated. | VERY HIGH | Implement the host side as a herdr plugin/bridge for the current machine, with a small device protocol boundary that can later be extracted. |
| **Credentials or direct Codex login on firmware** | It removes the host process from the data path. | It exposes durable secrets, couples firmware to changing auth, and makes account recovery/rotation difficult. | HIGH | Keep authenticated Codex access on the host; send normalized limits and timestamps to the device. |
| **Optimistic stale display** | Showing the last value without warnings looks cleaner. | It represents unknown state as current and can lead to selecting a vanished agent or trusting an expired quota. | MEDIUM | Keep cached content only with unmistakable stale/offline treatment; reject stale focus bindings. |
| **Queued/replayed presses after reconnect** | It seems to preserve intent through brief outages. | The target ordering may have changed, so replay can focus an agent the user no longer sees. | MEDIUM | Fail immediately and visibly while offline; after a full resync, require a fresh press. |
| **Raw prompts, transcripts, paths, or chain-of-thought on tiles** | More context may seem to improve selection. | It is unreadable at 128×128, leaks sensitive information on a desk, and turns the bridge into a content collector. | HIGH | Send short local titles, a compact workspace discriminator, state, and age only. |
| **Animated dashboards and decorative LED effects** | They showcase the hardware. | Motion competes for attention, increases redraw traffic, and can obscure stale/error states. | MEDIUM | Use static layouts, brief outcome pulses, and restrained state lighting. |
| **Battery/portable operation, module chaining, or broad OS support in v1** | They make the device feel productized. | Each introduces power, discovery, packaging, or compatibility work unrelated to validating the connected Linux/herdr loop. | HIGH | Use wired power and the actual Linux host; preserve boundaries for later expansion without implementing it now. |

## Detailed Feature Semantics

### Agent Tile Information Hierarchy

A 128×128 tile cannot show the full sidebar row. The recommended order is:

1. **State/attention mark** — redundant icon or short label plus herdr-compatible color.
2. **Short session title** — the primary identity, limited to a predictable number of lines.
3. **Workspace/repository discriminator** — enough to disambiguate duplicate titles.
4. **Age/time-in-state** — only if it fits at a legible size.

Do not show aggregate counts in place of an agent on keys 1–3. Do not use tiny scrolling text for required identity. Long titles need deterministic ellipsis and must not cause the other fields to move unpredictably.

### Direct-Key Selection Contract

For each visible agent tile, the rendered pixels and action binding represent one tuple:

`(opaque pane identity, snapshot revision, short title, workspace discriminator, state)`

On press, the host validates that identity and revision against a focus-safe target. Success means herdr accepted focus for that exact pane. If the pane disappeared or the binding is obsolete, the result is a visible rejection followed by resynchronization—not fallback to the agent now occupying the same numeric slot. No inbox state mutation is bundled with success.

### Codex Tile Truth Model

The official Codex app-server exposes `account/rateLimits/read` and sparse `account/rateLimits/updated` notifications. Documented fields include primary/secondary windows, `usedPercent`, `windowDurationMins`, `resetsAt`, a reached-limit classification, optional monthly credit information, spend-control state, and optional earned reset metadata. Sparse updates cannot safely be treated as complete replacements.

For one 128×128 tile, v1 should show the operational subset:

- Codex label and current/stale/unavailable status;
- primary and secondary used percentages when present;
- the next relevant reset time/countdown;
- a clear reached-limit cue;
- observation age or last-updated time.

`null`, absent, and empty values retain their documented “unavailable/not supplied” meanings. The host supplies observation time and freshness classification; the firmware must not invent them. Credits and reset-credit redemption are not keypad actions.

### Reconnect and Cached-State Behavior

- **Boot:** show deterministic boot/link states; do not preload an unmarked old assignment.
- **Handshake:** establish compatible device/host protocol state before enabling focus.
- **Initial sync:** transfer a complete ordered inbox projection and complete quota snapshot/status.
- **Brief loss:** optionally retain the last screen only with explicit stale/offline treatment; disable focus.
- **Recovery:** replace all four tile states and bindings from one full snapshot, then re-enable valid agent keys.
- **Never:** replay presses, infer successful focus, or clear a stale marker merely because the transport reconnected.

Agent freshness and Codex freshness are independent. For example, herdr can be current while Codex authentication is unavailable; only the fourth tile should show that provider failure.

### Device Feedback and Diagnostics

Normal feedback should remain quiet: a short highlight or low-brightness LED pulse after confirmed focus; a distinct brief failure cue on rejection; persistent visual treatment only for blocked/unseen attention, stale state, or offline state. Diagnostics are secondary and may use the encoder click/hold or a boot chord. Minimum useful diagnostics are physical key number, panel number/orientation, LED mapping, host-link status, protocol compatibility, last full snapshot age, last focus result, and Codex observation age/error category. Avoid exposing credentials, raw exceptions containing secrets, or host filesystem paths.

## Feature Dependencies

```text
[Physical key/display/LED bring-up]
    ├──requires before──> [Legible four-tile renderer]
    ├──requires before──> [Verified direct-key mapping]
    └──requires before──> [Actual-device end-to-end operation]

[Authoritative ordered inbox snapshot]
    ├──requires for──> [Authoritative top-three projection]
    │                     ├──requires for──> [Glanceable identity + redundant state]
    │                     └──requires for──> [Atomic tile-to-agent binding]
    │                                            └──requires for──> [Direct one-press focus]
    │                                                                   └──requires for──> [Focus outcome feedback]
    └──enhances──> [Restrained ambient LED escalation]

[Host-side Codex collector]
    └──requires for──> [Normalized quota snapshot + observed time]
                           └──requires for──> [Truthful Codex limits tile]

[Connection/freshness state model]
    ├──requires for──> [Current / stale / unavailable rendering]
    ├──requires for──> [Cold-start and offline screens]
    └──requires for──> [Reconnect full resynchronization]
                           └──requires for──> [Safe re-enable of direct focus]

[Host-side credential boundary]
    ├──constrains──> [Codex collector]
    └──constrains──> [Device protocol and diagnostics]

[Independent priority rules] ──conflicts with──> [Authoritative inbox projection]
[Queued press replay] ──conflicts with──> [Atomic binding and focus-only safety]
[Encoder-required navigation] ──conflicts with──> [Direct one-press focus]
[Inbox mutation on focus] ──conflicts with──> [Focus-only safety contract]
```

### Dependency Notes

- **Bring-up precedes UI conclusions:** panel order, orientation, key numbering, debounce, brightness, and LED mapping are physical facts, not safe assumptions from a simulator.
- **Ordered snapshot precedes rendering:** the bridge/plugin must expose the already-ordered queue and stable pane identities before firmware can render or bind keys correctly.
- **Atomic binding precedes focus:** direct selection is unsafe until pixels, target identity, and snapshot revision move together.
- **Focus acknowledgement precedes success feedback:** a detected key press is not evidence that herdr focused the pane.
- **Codex collection precedes quota UX:** the device cannot distinguish zero usage from unavailable data without normalized host semantics and observation time.
- **Freshness model precedes caching/reconnect:** caching is acceptable only after expiry and stale rendering are defined.
- **Diagnostics depend on the same truth model:** diagnostics must report known/unknown states rather than offer an optimistic green “connected.”

## MVP Definition

### Launch With (v1)

- [ ] **Verified physical mapping on the connected T-Keyboard S3 Pro** — all four displays, agent keys, fourth quota tile, LEDs used by v1, reboot, and chosen data link work on the actual unit.
- [ ] **Exact top-three projection from `herdr-agent-inbox`** — including 0–3 entries, authoritative ordering, stable identities, and explicit empty tiles.
- [ ] **Legible identity and redundant state** — short title, workspace discriminator, and non-color-only blocked/unseen/working/idle/settled treatment proven readable on 128×128 panels.
- [ ] **Atomic direct-key focus** — keys 1–3 focus the exact displayed pane with host acknowledgement; stale/empty targets fail safely; no inbox mutation occurs.
- [ ] **Truthful fixed Codex tile** — primary/secondary usage and reset/reached information when available, plus explicit current/stale/unavailable state and observation age.
- [ ] **Deterministic boot, offline, and reconnect behavior** — full resync before input, no queued press replay, stale cache visibly marked, and independent agent/Codex freshness.
- [ ] **Minimal device feedback and diagnostics** — confirmed focus/failure cue plus enough connection, version, mapping, and last-sync information to support the real installation.
- [ ] **Host-only credentials and bounded protocol** — normalized snapshots and focus requests only.
- [ ] **One actual end-to-end scenario** — a real highest-priority herdr agent appears, its physical key focuses that pane, Codex limits render truthfully, and a disconnect/restart recovers visibly.

This is the minimum that validates the core claim: the hardware makes the right agent immediately visible and switches to it safely with one press.

### Add After Validation (v1.x)

- [ ] **Refined ambient LED policy** — add only after display semantics are proven and the user can identify a useful peripheral-attention signal without distraction.
- [ ] **Persistent brightness/text preferences** — add when desk lighting shows the defaults are inadequate; keep them local and non-semantic.
- [ ] **Richer diagnostics screen** — add protocol counters or categorized collector errors if field failures cannot be resolved with the v1 minimum.
- [ ] **More nuanced quota presentation** — expose monthly credit/spend-control detail only if the account supplies it and the user demonstrates a need beyond the two windows.

### Future Consideration (v2+)

- [ ] **Additional provider quota collectors** — each requires separate API/auth/semantics validation and must preserve explicit unavailable states.
- [ ] **Expansion-module display of more ordered agents** — only after power, multi-board performance, and overflow interaction are physically validated.
- [ ] **General macro/action framework** — only if a concrete post-inbox workflow justifies the authorization and configuration burden.
- [ ] **Standalone non-herdr bridge/server and broader OS support** — extract only after the personal herdr integration has a stable, proven contract.

Still excluded unless project scope is explicitly changed: arbitrary replies, AskUserQuestion choices, approvals, automatic settle/dismiss/unread mutation, and battery portability.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Physical bring-up and verified mapping | HIGH | MEDIUM | P1 |
| Authoritative top-three projection | HIGH | MEDIUM | P1 |
| Glanceable identity and redundant state | HIGH | MEDIUM | P1 |
| Atomic tile-to-agent binding | HIGH | HIGH | P1 |
| Direct focus-only keypress | HIGH | HIGH | P1 |
| Confirmed focus/failure feedback | HIGH | MEDIUM | P1 |
| Truthful Codex limits tile | HIGH | HIGH | P1 |
| Stale/offline/unavailable states | HIGH | MEDIUM | P1 |
| Full reconnect resynchronization | HIGH | HIGH | P1 |
| Minimal diagnostics | MEDIUM | MEDIUM | P1 |
| Ambient LED escalation | MEDIUM | MEDIUM | P2 |
| Brightness/text preferences | MEDIUM | LOW | P2 |
| Rich quota detail | LOW | MEDIUM | P2 |
| More provider collectors | MEDIUM | HIGH | P3 |
| Expansion modules | LOW | HIGH | P3 |
| Macro framework | LOW for core workflow | HIGH | P3 |
| Standalone server | LOW for v1 | HIGH | P3 |

**Priority key:** P1 = required for launch; P2 = add after the core loop is validated; P3 = deferred and not part of current scope.

## Competitor and Adjacent-Product Feature Analysis

| Feature | OpenAI Codex Micro | Elgato Stream Deck SDK ecosystem | Installed `herdr-agent-inbox` | Herdr Agent Keypad approach |
|---------|--------------------|----------------------------------|-------------------------------|-----------------------------|
| Live agent state | Dedicated Agent Keys use live RGB for thinking, running, waiting, and done. | Plugins can update key title, image, and state dynamically; semantics are plugin-defined. | Defines blocked, finished/unseen, working, idle, settled, and closed states. | Render the inbox's exact state on each 128×128 agent key using text/icon plus restrained color. |
| Agent identity | Agent Keys and active-chat controls are emphasized; physical caps are action-oriented rather than per-key text displays. | Dynamic titles and images can identify an action or context. | Derives session titles and supplies workspace/pane context and age. | Put short title and workspace discriminator directly on the currently bound key. |
| Physical agent control | Provides tactile agent/workflow controls plus actions such as accept/reject and workflow launching. | Key down/up events support arbitrary plugin actions and multi-state keys. | Enter/double-click focuses; separate keys settle, mark unread, and clear flags. | One safe action only in v1: focus the exact displayed agent. Keep triage mutation in herdr. |
| Dynamic assignment | Product emphasizes active chats and status; public page does not specify herdr-style attention ordering. | Profiles/plugins determine assignment; generic platform does not supply agent priority. | Already owns the personal attention ordering. | Continuously mirror only the first three authoritative inbox entries with revision-safe bindings. |
| Disconnect/reconnect | Public product page does not document behavior. | Official SDK exposes device connect/disconnect events; plugins can refresh visible dynamic state. | Daemon/watchdog and socket-based state live on the host. | Explicit boot/offline/stale states, full snapshot resync, no queued press replay, and safe input re-enable. |
| Quota/capacity | Public Codex Micro page emphasizes agent state and commands, not subscription-limit display. | Possible through custom plugins; no Codex semantics provided. | Does not claim provider subscription-limit collection. | Reserve tile 4 for a read-only, host-collected Codex limits summary with observation age. |
| Hardware fit | 13 mechanical switches, touch sensor, encoder, joystick, RGB; no four 128×128 per-key displays described. | Varies by device; display keys are a mature convention. | Desktop TUI/sidebar, not physical hardware. | Exploit exactly four independent 128×128 displays, direct keys, LEDs, and secondary encoder diagnostics on the owned unit. |

The adjacent products validate two expectations: live state belongs on the physical control, and dynamic display keys should refresh when device state changes. The distinctive opportunity here is not more commands; it is a faithful, race-safe physical projection of the user's existing attention queue plus truthful quota context.

## Sources

All web sources retrieved **2026-08-16**.

### Primary / Official

- [Herdr Agent Keypad project definition](../PROJECT.md) — project constraints, active requirements, and explicit out-of-scope items. Local authoritative project source.
- Installed [`herdr-agent-inbox` README](file:///home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/README.md) — ordering, state legend, focus vs triage actions, titles, ages, pane identity, public herdr socket integration, and daemon behavior. Local authoritative workflow source.
- [OpenAI Supply Co. × Work Louder Codex Micro](https://openai.com/supply/co-lab/work-louder/) — live RGB agent states; tactile agent, workflow, and command controls; hardware summary.
- [Elgato Stream Deck SDK: Keys](https://docs.elgato.com/streamdeck/sdk/guides/keys/) — dynamic key states, titles, images, and key-down behavior.
- [Elgato Stream Deck SDK: Devices](https://docs.elgato.com/streamdeck/sdk/guides/devices/) — connected-device state and connect/disconnect events.
- [LILYGO T-Keyboard S3 Pro product page](https://lilygo.cc/products/t-keyboard-s3-pro) — display-key, encoder, RGB, chaining, and device hardware claims.
- [Official LILYGO T-Keyboard S3 Pro library README](https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library) — four independent host displays, five keys, RGB controls, encoder, board discovery, brightness, examples, and one-panel-at-a-time display behavior.
- [OpenAI Codex app-server README: account rate limits](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md#account-rate-limits) — `account/rateLimits/read`, sparse updates, quota-window fields, null semantics, credit/spend-control metadata, and reset data.

### Contextual, Not Authoritative

- [Preliminary Hermes research note](file:///home/nnex/vault/general/_Hermes/Research/LILYGO%20T-Keyboard%20S3%20Pro%20-%20physical%20Hermes%20AI%20inbox.md), dated 2026-08-15 — used only as leads for host-side credentials, stale/offline truthfulness, bounded actions, and physical validation; recommendations that conflict with the current project (encoder navigation, acknowledgement/snooze, multi-provider tiles, standalone service) were rejected.

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Herdr ordering and focus-only product semantics | HIGH | Defined by the project and installed plugin documentation. |
| Device feature feasibility | MEDIUM | Official hardware/library sources support the necessary panels, keys, LEDs, and discovery, but the exact connected revision and mapping still require physical bring-up. |
| Dynamic-key and reconnect expectations | MEDIUM | Grounded in official Stream Deck SDK conventions and the project's truthfulness requirement; exact protocol behavior remains to be implemented and validated. |
| Codex limits presentation | MEDIUM | Official app-server fields and sparse-update semantics are documented, but account-specific availability and the best 128×128 layout require real-account testing. |
| MVP prioritization | MEDIUM | Strongly aligned with stated core value and constraints, but usefulness and glanceability remain unvalidated until exercised on the actual desk setup. |

---
*Feature research for: Herdr Agent Keypad*
*Researched: 2026-08-16*
