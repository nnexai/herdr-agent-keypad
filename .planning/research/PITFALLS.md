# Pitfalls Research

**Domain:** ESP32-S3 multi-display companion hardware integrated with live coding-agent state
**Project:** Herdr Agent Keypad
**Researched:** 2026-08-16
**Confidence:** MEDIUM

Confidence is high for documented board, ESP32-S3, Herdr, and Codex behavior, but the overall rating remains **MEDIUM** because the exact connected unit, installed Herdr/Codex versions, transport behavior, display orientation, and end-to-end timing have not yet been exercised. The phase names below are roadmap topics, not final requirements.

## Severity Model

| Priority | Meaning for this project |
|----------|--------------------------|
| **P0 — Critical** | Can focus the wrong agent, mutate inbox state, expose credentials, or make old data look current; must be prevented in the first vertical slice. |
| **P1 — High** | Can make the physical device unreliable or force a firmware/transport rewrite; must be resolved during bring-up or resilience work. |
| **P2 — Moderate** | Usually recoverable without redesign but can degrade trust, performance, or maintenance if deferred. |

## Critical Pitfalls

### Pitfall 1 (P0): Treating “focus” as a mutation-free Herdr operation

**What goes wrong:**
A keypad press calls `agent.focus` and is described as “selection only,” yet Herdr documents that `agent focus` and `pane focus` mark the target tab as **seen**. For a finished-unseen agent, this changes the underlying `done`/unseen presentation and can change its position in the inbox even though settle/unread flags were not touched. The product can therefore violate the intended “focus only; do not mutate inbox state” promise while apparently using the correct public method.

**Why it happens:**
The installed inbox separates plugin-owned settle/unread state from Herdr’s core seen state, while product language tends to call all of these “inbox state.” The existing TUI focuses by pane ID and inherits Herdr’s seen transition. It is easy to verify only that no `settle` action was called and miss the core state transition. [S3][S4]

**Consequences:**
The selected item may leave the finished-unseen tier, reorder immediately, or appear acknowledged. A user cannot tell whether attention state changed because of their desktop focus or because the bridge performed an unintended triage action. Implementing around this late may require a Herdr API change or revised interaction contract.

**How to avoid:**
Before the focus vertical slice, define and observe the exact before/after state vector: core status, `seen`, plugin `settled`, plugin `unread`, rank, pane ID, and terminal ID. Use only Herdr’s public focus surface, but do not claim it is state-neutral until the installed version is proven. If strict no-mutation semantics are non-negotiable and the public method always marks seen, flag the incompatibility for roadmap/requirements resolution rather than silently writing state back afterward; compensating writes would introduce more races.

**Warning signs:**
- A finished-unseen tile moves or changes color immediately after a press.
- `agent.list` changes `done` to `idle` after focus.
- Plugin `state.json` is unchanged, so a narrow settle/unread test passes despite visible reordering.
- Documentation or tests use “focus” and “acknowledge” interchangeably.

**Recovery:**
Stop accepting device focus actions, refresh authoritative Herdr/plugin state, and remove any bridge-side attempt to restore previous flags. Reproduce on the installed Herdr schema and decide at the roadmap/requirements boundary whether the product permits Herdr’s native seen transition or requires a new upstream mutation-free selection capability.

**Phase to address:**
**Host contract and semantics**, before **live focus vertical slice**.

---

### Pitfall 2 (P0): Focusing by slot after the priority order has changed

**What goes wrong:**
The device shows agent A in key 1, the inbox reorders, and the press reaches the host after key 1 now means agent B. If the action carries only `slot: 1`, a display index, or a freshly looked-up “current top item,” the bridge focuses the wrong agent.

**Why it happens:**
Inbox ordering is dynamic: blocked, finished-unseen/unread, working, idle, and settled tiers can change at any time, with recent state changes used as a tie-breaker. USB buffering, Wi-Fi latency, sequential panel refresh, Herdr events, pane moves, and user focus all widen the interval between observation and action. [S3][S4]

**Consequences:**
A physical control performs a confident but incorrect action. This is more dangerous than a visible error because the user may begin typing in the wrong agent pane. Retrying by slot can repeat the mistake.

**How to avoid:**
Bind every rendered key to an immutable snapshot generation plus the exact opaque target identity captured in that generation. The device action should echo both; it must never mean “whatever is in this slot now.” The host must verify that the target still resolves to the same live agent and reject a stale or vanished target rather than substituting the new slot occupant. Validate the best version-specific identity across pane moves: the inbox persists by `terminal_id`, while Herdr focus accepts a live agent name or pane ID and documents pane-ID alias behavior after moves. Do not assume these identities are interchangeable.

**Warning signs:**
- Protocol actions contain only a key number.
- The host resolves the target after receiving the press instead of using the displayed binding.
- Rapid synthetic reorder tests occasionally focus a neighboring entry.
- Logs cannot correlate a press with a snapshot revision and target ID.

**Recovery:**
Reject the action visibly, fetch a fresh snapshot, redraw, and require a new press. Never auto-retry a stale selection against the current slot. If a wrong focus occurred, surface the failure in logs and inspect Herdr’s resulting seen transition; do not mutate settle/unread state to “repair” it.

**Phase to address:**
**Protocol and snapshot contract**, verified in **live focus vertical slice**.

---

### Pitfall 3 (P0): Publishing a torn snapshot across four sequential displays

**What goes wrong:**
Some panels show generation N while others show generation N+1, or the key-binding table switches before its label is drawn. A press then targets data that does not match what the user sees. The fourth panel may combine a new percentage with an old reset time or freshness badge.

**Why it happens:**
The official library says host panels share one SPI bus and STM32-controlled chip selects, must be drawn one at a time, and cannot reliably select multiple panels simultaneously. Network callbacks, parsing, rendering, and key polling are often interleaved in one loop. “Atomic update” must therefore be a logical protocol/UI property, not assumed simultaneous pixels. [S1]

**Consequences:**
Wrong-agent focus, inconsistent quota presentation, flicker, and intermittent bugs that disappear in a host simulator. A partial parse or disconnect can overwrite a valid snapshot with half-new data.

**How to avoid:**
Receive and validate a complete bounded snapshot into a staging model; render all affected panel buffers from that immutable model; then switch the active key bindings to its generation only at a defined commit point. During the short sequential physical flush, either retain old bindings until all agent labels are complete or suppress presses with an explicit updating state. Never patch independent fields directly from asynchronous callbacks. Reject out-of-order generations and preserve the last complete snapshot separately from transport status.

**Warning signs:**
- Each panel owns mutable network state.
- Key handlers read global “current inbox” data rather than committed bindings.
- Panel 4’s timestamp changes independently of its values.
- Presses during refresh are not tested.
- A malformed/truncated frame partially changes the screen.

**Recovery:**
Discard the staging generation, keep or restore the last complete render, mark transport data stale/offline as appropriate, and request a full snapshot. If binding/render divergence is detected, disable agent presses until a complete generation is committed.

**Phase to address:**
**Protocol and offline renderer**, before **live focus vertical slice**.

---

### Pitfall 4 (P0): Reimplementing Herdr lifecycle and inbox priority in the bridge

**What goes wrong:**
The keypad’s top three differ from the installed `herdr-agent-inbox`, especially for settled, manually unread, unknown, or recently changed agents. A bridge based only on raw `agent.list` statuses cannot reproduce the plugin’s complete priority model, titles, and persisted flags.

**Why it happens:**
Herdr’s public lifecycle uses `idle`, `working`, `blocked`, `done`, and `unknown`. The installed plugin adds persisted `settled` and `unread` flags, derives ranks, and sorts by state-change sequence. Its README documents a control socket for its own actions/TUI, not a stable public device snapshot contract. Copying the current Python constants or reading `state.json` creates a private second implementation that can drift. [S2][S3][S4]

**Consequences:**
The physical queue stops mirroring the trusted inbox, settled work resurfaces, or unseen work is hidden. Every plugin update becomes a compatibility hazard, and recovery can require replacing both sides of the bridge.

**How to avoid:**
Make the installed inbox’s derived order authoritative through a supported integration seam owned by the plugin/bridge. Carry the already-derived rank/order, title, stable identity, and freshness in the device snapshot; firmware must not infer lifecycle. Pin and inspect the installed Herdr API schema and plugin version during development. Treat unknown states as explicit unknown, not idle. Avoid direct reads/writes of plugin persistence files or undocumented control messages as a durable contract.

**Warning signs:**
- Bridge code contains a second rank table.
- Device order is computed from status strings alone.
- `settled` and `unread` are inferred from color or core `seen`.
- Updating the inbox plugin changes device behavior without a protocol-version failure.
- The bridge reads `state.json` while the daemon may be writing it.

**Recovery:**
Disable actions, refresh from the authoritative plugin seam, and show an incompatible/offline state if schema/version checks fail. Remove copied lifecycle logic rather than adding special cases for newly observed statuses.

**Phase to address:**
**Host contract and semantics**.

---

### Pitfall 5 (P0): Presenting cached Codex limits as current truth

**What goes wrong:**
The fourth key shows plausible percentages and reset times after the collector has failed, authentication has expired, the app-server started offline, or a sparse notification was mistaken for a complete snapshot. “0%,” a frozen value, or an old reset time looks authoritative.

**Why it happens:**
Codex documents `account/rateLimits/read` as the full ChatGPT rate-limit snapshot and `account/rateLimits/updated` as a **sparse rolling update** that must be merged or followed by a refetch. `windowDurationMins` is the quota-window length, not a data freshness TTL. Current open Codex issues report missing limits after an offline startup prefetch and stale data on the first `/status` invocation. [S5][S6][S7]

**Consequences:**
The device’s ambient promise becomes harmful: the user may start work believing capacity is available, or treat a collector/auth failure as exhaustion. A stale value can remain convincing for hours.

**How to avoid:**
The host collector must attach its own `observed_at`, collection outcome, source/auth status, and explicit freshness classification to a complete normalized snapshot. Keep `current`, `stale`, `unavailable`, `auth-required`, and `offline` distinct. Merge sparse updates only into a known full snapshot, respecting documented nullable semantics, or refetch. Never synthesize zero on null/error. Make staleness policy explicit and independent of `windowDurationMins`; show observation age on the tile. Credentials and token refresh remain inside Codex on the host.

**Warning signs:**
- Device schema has percentages but no observation timestamp/status.
- `null` becomes `0` or an empty progress ring.
- “15 minutes” is copied from `windowDurationMins` as a cache TTL without a product policy.
- Collector starts offline and never retries.
- A first read differs immediately from a second read.

**Recovery:**
Retain the last value only with a prominent stale age, then perform a bounded full refetch after connectivity/auth recovery. If freshness cannot be established, replace numbers with unavailable/auth-required rather than restarting in a loop or scraping a private backend.

**Phase to address:**
**Codex collector and truthful-state resilience**.

---

### Pitfall 6 (P0): Letting host credentials or sensitive agent data cross into firmware

**What goes wrong:**
ChatGPT tokens, Codex auth files, Herdr session socket access, raw transcripts, filesystem paths, or a general-purpose command channel are copied to the ESP32 or exposed over an unauthenticated LAN endpoint/serial command protocol.

**Why it happens:**
Direct device-to-provider calls appear simpler, and a “trusted home LAN” is treated as an authorization boundary. Debug logging may dump complete host responses. Firmware extraction, serial access, backups, and local network peers then inherit privileges far beyond “display three entries and focus one.”

**Consequences:**
Provider/session compromise, transcript and path disclosure, arbitrary Herdr control, and an unsafe firmware update path. Rotating one leaked secret may disrupt the user’s whole development environment.

**How to avoid:**
Keep provider authentication and Herdr authority on the host. Send only display-bounded normalized fields and opaque device targets. Expose only enumerated read-snapshot and focus-intent operations; no shell text, arbitrary Herdr method, settle/unread action, or raw socket proxy. For Wi-Fi, authenticate the device and verify the host’s TLS identity; Espressif warns against disabling server verification. For USB serial, treat device-node access and framing as a security boundary, set restrictive host permissions, and ensure debug output cannot be parsed as control frames. Redact payloads in logs. [S8]

**Warning signs:**
- Firmware configuration contains OpenAI tokens or `$CODEX_HOME` material.
- Device messages include raw transcript text or host paths.
- Any LAN client can invoke focus.
- Transport exposes a generic `{method, params}` pass-through.
- Serial logs and protocol frames share an unframed stream.

**Recovery:**
Disconnect/revoke the device credential, stop the bridge listener, rotate any exposed upstream credential, purge sensitive device storage/logs, and reflash from a trusted image. Restore with a new least-privilege device identity; do not merely hide the offending UI field.

**Phase to address:**
**Protocol security boundary**, designed before transport implementation and rechecked at release hardening.

---

### Pitfall 7 (P0): Declaring v1 complete from simulation or bench mocks

**What goes wrong:**
A desktop renderer, fake serial endpoint, or mocked Herdr/Codex feed passes while the connected keypad has reversed panels, missed keys, boot-key side effects, USB re-enumeration, brownouts, unreadable typography, slow refresh, or reconnect failures.

**Why it happens:**
Simulation is faster and deterministic. This board’s architecture is unusually specific: four host panels plus an encoder occupying CS5, an STM32 co-processor controlling chip selects/keys/LEDs, shared SPI, and KEY5 reused as BOOT. These constraints are poorly represented by generic ESP32 or single-display tests. [S1]

**Consequences:**
The primary acceptance criterion—actual connected hardware working end to end—remains unproven. Hardware discoveries arrive after protocol and UI choices harden, forcing rewrites.

**How to avoid:**
Make real-device evidence a gate in every relevant phase: official examples on the exact unit; labeled panel/key/encoder/LED map; chosen transport across reset and host restart; one real installed-inbox entry displayed and focused; real Codex stale/unavailable behavior; and an outage/soak scenario. Simulation remains useful for deterministic races and malformed input, but can never substitute for the physical path.

**Warning signs:**
- Screenshots come only from a browser/canvas mock.
- No record of board revision, USB IDs, firmware build flags, or physical mapping exists.
- Tests use a generic ESP32-S3 dev board.
- “End to end” stops at a pseudo-terminal or HTTP client.

**Recovery:**
Reopen the affected phase, return to official hardware examples, record the real mapping and limits, then rerun the smallest host-to-keypad vertical slice before adding features. Remove assumptions contradicted by the unit rather than adding per-simulator exceptions.

**Phase to address:**
**Physical bring-up**, then repeated in **vertical slice**, **resilience**, and **release acceptance**.

## High and Moderate Pitfalls

### Pitfall 8 (P1): Using the wrong T-Keyboard generation, board revision, or library contract

**What goes wrong:**
Code targets the original T-Keyboard-S3, the old branch’s five-screen assumptions, or generic direct GPIO chip-selects instead of the Pro host’s STM32-mediated four-panel arrangement. Arduino core 2.x examples and the newer library’s 3.x requirement are mixed.

**Why it happens:**
The official hardware repository says the Pro adds a fifth screen position, while the newer official library clarifies that the host’s fifth position is the encoder and exposes only `display1`…`display4`; expansion modules have five panels. The old examples live on a version-specific branch. Product naming and repository layout invite accidental cross-generation reuse. [S1]

**How to avoid:**
Inventory the exact H734/unit PCB revision, firmware version, USB IDs, host-versus-expansion role, Arduino core, library commit, and dependency versions before application code. Prove the official library’s basic display/key/encoder/RGB examples on that pinned combination. Do not copy original-board pin definitions.

**Warning signs:**
Five host display objects, direct ESP32 key/CS GPIO reads, unexplained I2C failures, or code copied from `arduino-esp32-libs_V2.0.14` while building against an unpinned 3.x core.

**Recovery:**
Return to a minimal official example, erase conflicting board definitions, repin the known-working toolchain/library commit, and rebuild the mapping artifact from the actual unit.

**Phase to address:**
**Physical bring-up and toolchain pinning**.

---

### Pitfall 9 (P1): Assuming visual panel order equals key index order

**What goes wrong:**
The label above one physical switch is bound to another key, a panel is rotated/mirrored, or an encoder/BOOT key is accidentally treated as one of the four agent/quota keys. The UI appears plausible but actions are spatially wrong.

**Why it happens:**
Library indices, STM32 key bits, CS numbers, physical left-to-right order, connector orientation, and display rotation are separate mappings. The five keys do not imply five host displays. Mechanical assembly or revision changes may invalidate a photo-derived map.

**How to avoid:**
On the unit, draw a unique panel/CS/index label and light one LED at a time; press and hold each physical switch while recording raw key transitions; test encoder directions and push if present; reboot while holding KEY5 to observe BOOT behavior. Store one explicit physical-layout mapping consumed by both renderer and key dispatcher. Validate the user-facing map, not only raw indices.

**Warning signs:**
A mapping table is inferred solely from source constants, display rotation is patched per screen, or a press test asserts “some key event” rather than the label directly above it.

**Recovery:**
Disable focus actions, rerun the mapping diagnostic, correct the single mapping source, redraw all panels, and revalidate each label-to-action pair physically.

**Phase to address:**
**Physical bring-up**, reverified in **live focus vertical slice**.

---

### Pitfall 10 (P1): Locking USB serial before proving USB mode and recovery behavior

**What goes wrong:**
The firmware is configured for TinyUSB DFU, HID, or a different native USB mode and loses CDC logging/bridge traffic; flashing resets or re-enumeration orphan the host plugin’s file descriptor; protocol and debug text collide; holding KEY5 during reset unexpectedly enters download mode.

**Why it happens:**
ESP32-S3 supports several USB personalities. Espressif documents that DFU cannot simultaneously serve serial logging, while Arduino CDC on ESP32-S3 uses `USB CDC On Boot: Enabled` with `UART0 / Hardware CDC`. The board uses native USB and KEY5 doubles as BOOT. A USB connection that powers the board does not prove the selected application data path is stable. [S1][S9]

**How to avoid:**
If USB serial is evaluated, pin all USB build flags and record VID/PID/interface behavior. Use framed protocol messages with explicit version, length, checksum, generation, and separate logging channel or unambiguous framing. The host must reopen by stable device identity after reset and fail visibly when multiple matching devices exist. Compare this proved behavior with Wi-Fi and hybrid; do not select transport from generic ESP32 capability alone.

**Warning signs:**
`/dev/ttyACM*` is hard-coded, firmware logs are valid-looking protocol JSON, bridge hangs after flash/reset, or changing USB mode makes the serial port vanish.

**Recovery:**
Close the stale descriptor, rediscover the exact device/interface, re-handshake protocol/version, and request a full snapshot. If firmware cannot expose bridge CDC and the required USB personality together, return to transport comparison rather than adding timing sleeps.

**Phase to address:**
**Physical transport proof**.

---

### Pitfall 11 (P1): Treating Wi-Fi association as recovered connectivity

**What goes wrong:**
After router restart, host suspend, DHCP renewal, or AP roaming, the display remains frozen and the client keeps a dead TCP socket. Rapid retries starve rendering or flood the host. A hybrid design may show USB power as “connected” while Wi-Fi data is unavailable.

**Why it happens:**
Espressif documents that `WIFI_EVENT_STA_DISCONNECTED` tears down the station netif and can invalidate sockets; applications should recreate them and wait for `IP_EVENT_STA_GOT_IP`, not merely association. Reconnect policy is application responsibility beyond connection-attempt retries. [S10]

**How to avoid:**
Model Wi-Fi, IP, bridge session, snapshot freshness, and host availability as separate states. On disconnect, close application sockets; reconnect with bounded exponential backoff/jitter; after GOT_IP, establish a new authenticated bridge session and request a complete snapshot. Keep key polling/rendering responsive during outage. For hybrid transport, define deterministic authority and failover so USB and Wi-Fi cannot both deliver conflicting generations.

**Warning signs:**
The reconnect handler only calls `WiFi.begin`, old sockets are reused, retry is a tight loop, association icon is shown as end-to-end online, or two transports can update the model concurrently.

**Recovery:**
Invalidate the bridge session and bindings as policy requires, preserve the last complete view only as visibly stale, rebuild sockets after IP acquisition, reauthenticate, and accept only a fresh full generation.

**Phase to address:**
**Connectivity and reconnect resilience**, after transport proof.

---

### Pitfall 12 (P2, can escalate to P1): Spending internal/DMA memory as if 8 MB PSRAM were interchangeable RAM

**What goes wrong:**
Four displays work with mock data, then TLS, JSON, fonts, images, Wi-Fi, or repeated updates cause allocation failures, fragmentation, watchdog resets, flicker, or dropped input. Full-screen redraws monopolize the shared bus.

**Why it happens:**
Four RGB565 128×128 buffers alone are about 128 KiB; double buffering doubles that before assets and networking. ESP-IDF distinguishes external PSRAM from internal DMA-capable memory, and total free heap does not reveal the largest allocatable block. The official display library selects one panel at a time and uses a shared 20 MHz SPI bus on a single board. [S1][S11][S12]

**How to avoid:**
Measure the exact firmware, not generic capacity. Allocate long-lived frame/asset buffers once in appropriate memory, retain internal DMA-capable headroom for display/network stacks, bound snapshot/string sizes, reuse parse/render buffers, and update only changed tiles where that improves measured behavior. Track minimum free heap and largest free block by capability, display-flush latency, key-scan latency, and watchdog margin during TLS reconnect and all-panel redraw. Avoid per-frame dynamic allocation.

**Warning signs:**
Only total heap is logged; largest free block shrinks over time; key presses are missed during redraw; a network reconnect coincides with reset; strings/images allocate each refresh; or all four panels redraw for an unchanged snapshot.

**Recovery:**
Fall back to a minimal static offline screen, stop accepting oversized snapshots, capture capability-specific memory/latency diagnostics, then reduce/reuse buffers and assets at the source. Do not hide resets with an automatic reboot loop.

**Phase to address:**
Baseline in **physical bring-up/offline renderer**; prove with **resilience soak and release hardening**.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Read inbox `state.json` directly | Quick access to flags | Races, private schema coupling, bypassed daemon semantics | Never as the durable bridge contract |
| Copy the plugin rank table | Fast mock ordering | Semantic drift and two sources of truth | Only in an isolated UI mock that cannot drive actions |
| Send slot numbers | Tiny protocol | Wrong-agent focus after reorder | Never |
| Mix debug logs and control JSON on CDC | Easy development | Parser ambiguity and accidental commands | Never without robust independent framing |
| Use a hard-coded `/dev/ttyACM0` | Fast local demo | Breaks after reset/reorder or second device | Only for a throwaway manual experiment |
| Show last quota without age/status | Attractive demo | Misrepresents stale data | Never |
| Store provider token on device | Avoids bridge collector | Credential leakage and firmware/upstream coupling | Never |
| Full redraw and dynamic allocation every poll | Simple renderer | Latency, fragmentation, flicker | Only in a short offline prototype with measurements, then remove |
| Treat simulation as release evidence | Fast iteration | Misses the product’s core physical contract | Never |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `herdr-agent-inbox` | Reconstruct order from raw status | Consume an authoritative derived snapshot from a supported plugin/bridge seam |
| Herdr focus | Assume focus does not alter attention | Measure core `seen` plus plugin flags; resolve the semantic conflict explicitly |
| Herdr identity | Focus “current slot” or stale pane blindly | Bind generation to stable target; validate liveness; reject rather than substitute |
| Codex app-server | Treat sparse `updated` as full or 15-minute window as TTL | Base UI on full reads plus bridge-owned observation/freshness metadata |
| USB CDC | Assume power/flash/serial/protocol coexist automatically | Pin USB mode, frame protocol, rediscover and handshake after re-enumeration |
| Wi-Fi | Reuse socket after reconnect | Close on disconnect; wait for GOT_IP; recreate/authenticate/request full snapshot |
| T-Keyboard library | Drive all panel CS simultaneously | Use official one-panel-at-a-time API and prove physical mapping |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Four unconditional full-screen RGB565 redraws | Visible sweep/flicker, delayed key scan | Immutable model, dirty panels/regions, measured flush budget | High-frequency updates or animated/network-heavy states |
| Per-update JSON/string/image allocation | Largest block falls while free heap looks adequate | Bounded schema, fixed/reused buffers, allocation metrics | Long soak, variable titles, reconnect churn |
| Blocking network/TLS in input/render loop | Frozen keys and stale animations | Separate state machines/tasks with bounded queues | Host/AP outage or TLS handshake delay |
| Unlimited title/payload size | Parse failure, layout overflow, heap spike | Host-side normalization and strict byte/codepoint limits | One pathological session title is enough |
| Retry without backoff | Hot loop, UI starvation, host flood | Bounded exponential backoff with jitter | Any sustained outage |
| Concurrent USB/Wi-Fi writers | Generations regress or bindings diverge | One transport authority and monotonic generation arbitration | First failover or duplicate connection |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Provider credentials in firmware/NVS | Extracted token grants account access | Keep all upstream auth in host processes; device gets only least-privilege identity |
| Unauthenticated LAN bridge | Any peer can observe data or focus agents | Bind narrowly; authenticate device; verify host TLS identity; authorize each bounded action |
| Generic Herdr/socket proxy | Device compromise becomes arbitrary agent control | Explicit snapshot and focus-intent methods only |
| Raw transcripts/paths in snapshot or logs | Sensitive prompt/project disclosure | Host-side minimization, truncation/redaction, no raw transcript transport |
| Unframed serial commands mixed with logs | Debug text can become control input | Versioned length-delimited frames and strict parser; separate logging if possible |
| Silent TLS verification bypass | Device can accept an impostor bridge | Pin/trust a local CA or supported host identity and plan credential rotation [S8] |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Old data looks live | False confidence in agent priority/quota | Always display current/stale/offline/unavailable distinctly, with observation age |
| Color-only status | Ambiguous on tiny displays and inaccessible | Pair color with icon/text and reserve stable semantics |
| Label changes while key remains active | Wrong selection | Commit display and binding as one generation; suppress presses during divergence |
| Truncated agents become indistinguishable | User cannot choose safely | Preserve unique identity cues; reject ambiguous focus rather than guess |
| Offline screen still accepts focus | User believes action succeeded | Disable or visibly reject actions without a valid committed host session |
| Success feedback before host acknowledgment | Masks failed focus | Confirm only after Herdr response; otherwise show failure and refresh |

## “Looks Done But Isn’t” Checklist

- [ ] **Physical mapping:** Every actual panel, switch, encoder direction/push, LED, and KEY5/BOOT interaction has been recorded on the connected unit.
- [ ] **Transport:** Reset, flash, cable reconnect, host restart, and multiple-device ambiguity recover through a new handshake.
- [ ] **Inbox authority:** Device top-three order exactly matches the installed plugin for blocked, unseen/unread, working, idle, unknown, and settled cases.
- [ ] **Focus semantics:** Before/after evidence includes Herdr `seen` and plugin settle/unread state—not merely “focus returned OK.”
- [ ] **Race safety:** Reorder/close/move between display and press rejects or focuses the displayed target, never the new slot occupant.
- [ ] **Atomic display:** Presses during a four-panel refresh cannot use bindings inconsistent with visible labels.
- [ ] **Codex truthfulness:** Fresh, stale, unavailable, auth-required, offline-start, and sparse-update scenarios are visibly distinct.
- [ ] **Reconnect:** Router restart, host suspend/resume, bridge restart, and USB re-enumeration recover without stale sockets or hidden frozen data.
- [ ] **Memory/performance:** A real-device soak records minimum/largest capability-specific heap, panel flush time, key latency, and resets.
- [ ] **Credential boundary:** Firmware, wire captures, and logs contain no provider token, raw transcript, arbitrary Herdr method, or host filesystem path.
- [ ] **Actual v1:** One real inbox item is displayed and focused, and real Codex limit data is shown on the physically connected device.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Focus altered seen state | HIGH | Disable action, capture before/after state, resolve contract/API conflict; do not compensate with flag rewrites |
| Stale slot focused wrong agent | HIGH | Reject stale generations, refresh, require new press; audit any seen-state side effect |
| Torn display/binding generation | MEDIUM | Disable presses, discard staging state, redraw last complete or fresh snapshot |
| Lifecycle/order drift | HIGH | Stop copied ranking, restore authoritative plugin seam, version-gate compatibility |
| Stale quota shown as live | MEDIUM | Mark unavailable/stale immediately, full refetch after auth/network recovery |
| Credential leakage | HIGH | Stop bridge, revoke/rotate, purge/reflash, issue least-privilege device identity |
| Wrong board/library assumption | MEDIUM | Return to official examples on exact unit and repin the toolchain/mapping |
| USB mode conflict | MEDIUM | Re-enter download mode if needed, restore known CDC/transport build, rediscover/re-handshake |
| Wi-Fi dead socket | LOW | Close, wait for GOT_IP, reconnect/authenticate, request full generation |
| Heap/performance collapse | MEDIUM | Minimal static fallback, collect metrics, bound/reuse allocations and redraws |
| Simulation-only completion | HIGH | Reopen phase and repeat vertical slice/resilience acceptance on actual hardware |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Wrong board/revision/toolchain | Physical bring-up | Official examples run on recorded unit/library/core combination |
| Panel/key/encoder mapping | Physical bring-up | Unique labels and presses prove every physical mapping and orientation |
| USB mode/serial conflict | Physical transport proof | Reset/flash/re-enumeration plus bridge handshake recover on Linux |
| Credential leakage | Protocol security boundary | Wire/log/firmware inspection shows only normalized data and bounded methods |
| Lifecycle semantic drift | Host contract and semantics | Device order matches installed inbox across every tier/flag |
| Accidental seen/inbox mutation | Host contract + focus vertical slice | Full before/after state vector establishes actual focus semantics |
| Focus target race | Protocol + focus vertical slice | Reorder/close/move during delayed press never focuses replacement slot |
| Torn snapshot/update | Offline renderer + vertical slice | Press-during-refresh and malformed-frame scenarios preserve generation consistency |
| Misleading stale/offline UI | Offline renderer + resilience | Disconnect at each layer changes status/age without erasing last known value incorrectly |
| Wi-Fi reconnect | Connectivity resilience | AP/router restart and host suspend recreate socket/session and fetch full snapshot |
| Stale Codex quota | Codex collector resilience | Offline start, failed auth, sparse update, stale first read, and recovery are truthful |
| Memory/performance | Renderer baseline + release hardening | Real-device soak captures heap blocks, flush/key latency, watchdog/brownout behavior |
| Simulation-only validation | Every physical gate + release acceptance | Actual connected device completes inbox-to-focus and quota flows end to end |

## Hands-On Validation Gaps

These facts remain unresolved by documentation and must be answered on the actual setup; they are research flags, not selected requirements:

1. Exact PCB/hardware revision, USB VID/PID/interfaces, STM32 firmware, installed encoder arrangement, and whether the delivered host exactly matches the newer four-panel library contract.
2. Physical left-to-right panel/CS/index orientation, key bit/index mapping, encoder direction/push behavior, LED map, and KEY5/BOOT behavior during normal presses and reset.
3. Whether the current official Arduino 3.x library commit works with the chosen installed core and all four displays, keys, encoder, and LEDs without patching; the hardware repository’s older examples target core 2.0.14.
4. Native USB behavior under the exact build flags: CDC availability, debug/protocol coexistence, re-enumeration identity, Linux device permissions, host restart, flash/reset recovery, and whether a hybrid transport is materially more reliable.
5. Measured four-panel full/partial redraw time, visual tearing, minimum key-scan latency, internal DMA heap headroom, largest PSRAM block, TLS/Wi-Fi memory peak, LED power/brownout behavior, and long-soak stability.
6. Installed Herdr version’s generated API schema and exact `agent.focus` before/after behavior for blocked, done/unseen, working, idle, unknown, settled, and manually unread agents.
7. The supported seam by which a new bridge can consume the installed plugin’s exact derived order/title/flags without reading private files or copying rank logic.
8. Which identity remains safe across pane moves, renames, agent closure/restart, plugin restart, and Herdr server restart; and how stale target rejection is surfaced.
9. Installed Codex app-server schema/version, authentication mode, number/names of limit buckets, first-read freshness, offline-start recovery, token refresh behavior, and a defensible product staleness threshold.
10. Real desk Wi-Fi RSSI and recovery after AP restart, DHCP change, host suspend/resume, bridge restart, and simultaneous USB power with Wi-Fi data loss.
11. Tiny-display legibility and whether three dynamic identities can remain unambiguous under real title truncation, glare, and normal viewing distance.

## Sources

All web sources retrieved **2026-08-16**. Official primary documentation/repositories are preferred; open issues are treated as current failure reports, not guaranteed universal behavior.

- **[S1]** LILYGO, [official T-Keyboard-S3-Pro library](https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library) and [hardware repository](https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro) — four host panels versus five expansion panels, STM32-mediated CS/keys/LEDs, shared SPI, key/BOOT detail, hardware revisions. Source confidence: MEDIUM overall until confirmed on the unit.
- **[S2]** Installed `herdr-agent-inbox` README and source inspected locally — authoritative rank semantics, persisted settle/unread flags, terminal-ID persistence, control socket, pane-ID focus. Source confidence: HIGH for the installed copy, but its undocumented internals are not a stable external contract.
- **[S3]** Herdr, [Socket API](https://herdr.dev/docs/socket-api/) — public agent/pane/event/plugin methods and version-specific schema guidance.
- **[S4]** Herdr, [CLI reference](https://herdr.dev/docs/cli-reference/) — `done`/unseen lifecycle and explicit statement that pane/agent focus marks a tab seen.
- **[S5]** OpenAI, [Codex app-server protocol README](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md) — initialization, `account/read`, full rate-limit read, sparse update, field meanings, and version-generated schemas.
- **[S6]** OpenAI Codex issue [#26789: offline startup does not recover usage limits](https://github.com/openai/codex/issues/26789), opened 2026-06-06 — current failure report; MEDIUM confidence as an open issue.
- **[S7]** OpenAI Codex issue [#33897: first `/status` can show stale limits](https://github.com/openai/codex/issues/33897), opened 2026-07-17 — current failure report; MEDIUM confidence as an open issue.
- **[S8]** Espressif, [ESP-TLS](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/protocols/esp_tls.html) and [security overview](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/security/security.html) — certificate verification and embedded secret protections.
- **[S9]** Espressif, [Arduino ESP32 USB CDC and DFU flashing](https://docs.espressif.com/projects/arduino-esp32/en/latest/tutorials/cdc_dfu_flash.html) and [ESP32-S3 USB device stack](https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_device.html) — CDC/DFU modes, setup, and serial limitations.
- **[S10]** Espressif, [ESP32-S3 Wi-Fi driver overview](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/wifi-driver/overview.html) — disconnect/IP event behavior and invalidated sockets.
- **[S11]** Espressif, [ESP32-S3 external RAM guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/external-ram.html) — PSRAM allocation and cache/DMA constraints.
- **[S12]** Espressif, [ESP32-S3 heap allocator](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/mem_alloc.html) — capability-specific free/minimum/largest-block diagnostics.
- Preliminary local research note, *LILYGO T-Keyboard S3 Pro as a physical Hermes AI inbox* (2026-08-15), used only as leads and cross-checked against the sources above.

---
*Pitfalls research for: Herdr Agent Keypad*
*Researched: 2026-08-16*
