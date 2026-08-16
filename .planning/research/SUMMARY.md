# Project Research Summary

**Project:** Herdr Agent Keypad
**Domain:** USB-connected ESP32-S3 display keypad with a local herdr/Codex host bridge
**Researched:** 2026-08-16
**Confidence:** MEDIUM

## Executive Summary

Herdr Agent Keypad is a dedicated physical projection of an existing, authoritative agent inbox—not a miniature chat client, generic macro deck, or second inbox implementation. Experts should build it as a host-authoritative system with a deliberately small device surface: the Linux bridge consumes the installed `herdr-agent-inbox` ordering, keeps Codex authentication and rate-limit interpretation on the host, publishes complete normalized snapshots, and permits exactly one device-originated action. Firmware renders three dynamically assigned agent tiles and one fixed, read-only Codex limits tile, reports identity-bound keypress intents, and makes stale, unavailable, booting, and offline states explicit.

The recommended baseline is Arduino-ESP32 3.3.11 with the official LILYGO T-Keyboard-S3-Pro Library 0.1.0, built with pinned PlatformIO Core 6.1.19 and pioarduino platform-espressif32 55.03.311. A Python 3.11+ herdr plugin/bridge should use the public herdr 0.8.x Unix-socket API, `pyserial` 3.5, and a separately supervised Codex 0.147.0 app-server collector. Native USB CDC carrying bounded, versioned newline-delimited JSON is the leading v1 transport because the device is already USB-powered and this avoids Wi-Fi provisioning, LAN authentication, and split-brain links. That recommendation remains contingent on a real-device gate covering enumeration, stable identity, reset/reflash recovery, framing, and sustained bidirectional traffic; Wi-Fi is the measured fallback, while hybrid transport is explicitly deferred.

The dominant risks are semantic and physical rather than throughput-related. A press must name the exact identity and snapshot revision displayed, snapshots and bindings must commit atomically despite sequential panel drawing, and independent herdr/Codex/link freshness must remain truthful through restarts. Most importantly, the public `agent.focus` path is **not yet proven compatible with the required no-inbox-mutation promise**: herdr focus marks a tab seen, and the installed inbox implementation also clears a manual unread flag on focus outside its guard window. This is a blocking product/API decision for the live focus vertical slice. It must be resolved by defining the allowed before/after state vector or providing device-safe upstream focus semantics—not by compensating writes, private state-file manipulation, or quietly weakening acceptance.

## Key Findings

### Recommended Stack

The stack should stay narrow, pinned, and host-heavy. The official board abstraction is essential because an STM32G030F6 controls display chip selects, keys, and LEDs; the four 128×128 GC9107 panels share SPI and must be addressed one at a time. Firmware should use LovyanGFX only through the LILYGO objects, ArduinoJson for bounded device messages, and the board library's ButtonSense APIs rather than raw pin/I²C assumptions. On the host, standard-library `asyncio` is sufficient for herdr and Codex JSONL, while a dedicated blocking `pyserial` worker is the conservative serial integration.

The bridge must generate and inspect schemas from the installed herdr and Codex binaries rather than treating documentation from `main` as timeless. The installed inbox's `tokens.rank` plus descending `state_change_seq` is the verified current projection rule, but it is installation-specific rather than a promised stable cross-plugin API. Missing rank metadata is an incompatibility/unavailable state, not permission to create another priority algorithm.

**Core technologies:**
- **LILYGO T-Keyboard-S3 Pro host hardware:** four agent/quota display keys, encoder, LEDs, and keys — use the official host abstraction and confirm the delivered PCB/STM32 revision physically.
- **Arduino-ESP32 3.3.11 / ESP-IDF 5.5.5:** firmware framework and native USB support — required by the current official board library.
- **LILYGO T-Keyboard-S3-Pro Library 0.1.0:** board support — encapsulates the STM32-mediated one-panel-at-a-time display selection, input, brightness, encoder, and LEDs.
- **PlatformIO Core 6.1.19 + pioarduino platform-espressif32 55.03.311:** reproducible firmware build — pins Arduino-ESP32 3.3.11 where official PlatformIO currently lags on Arduino 2.x.
- **LovyanGFX 1.2.26 and ArduinoJson 7.4.3:** bounded rendering and protocol parsing — no LVGL or second panel driver is justified for four fixed tiles.
- **ButtonSense:** key semantics through the board library — the manifest/tag mismatch must be resolved to an immutable artifact before implementation.
- **Python 3.11+ and pyserial 3.5:** host bridge and stable Linux serial access — align with the installed plugin ecosystem and keep the bridge inspectable.
- **herdr public API 0.8.x:** authoritative snapshot/events/focus boundary — generate the installed schema and pin `<0.9` until compatibility is established.
- **Codex app-server 0.147.0:** host-only subscription-limit collector — use stable stdio JSONL and `account/rateLimits/read`, preserving optional/null fields and sparse-update semantics.
- **USB CDC with bounded versioned NDJSON:** recommended v1 device link — select only after the physical USB gate; Wi-Fi remains a fallback adapter, not a parallel authority.

### Expected Features

The launch product is the smallest trustworthy physical attention loop. Keys 1–3 mirror the exact top-three entries from the installed inbox, including explicit empty slots; each tile combines deterministic identity, workspace discrimination, and redundant state cues. A press either focuses the exact entry that was rendered and receives an acknowledged result, or fails visibly as stale/offline—not whatever later occupies the same slot. Tile 4 remains a fixed, read-only Codex capacity view whose percentages, reset information, source status, and observation age never confuse unavailable with zero.

**Must have (table stakes):**
- **Verified physical map:** all four panels, matching keys, encoder/BOOT behavior, LEDs used by v1, brightness, orientation, reboot, and the selected link are exercised on the connected unit.
- **Authoritative top-three projection:** 0–3 entries match the installed inbox's rank and recency ordering; absent rank or source failure is visible, and removed entries clear deterministically.
- **Glanceable identity and redundant attention state:** short title plus repository/workspace discriminator, and text/icon plus restrained color for blocked, unseen/unread, working, idle, settled, and unknown states.
- **Atomic display-to-target binding:** pixels, opaque identity, pane target token, host epoch, and snapshot revision move as one logical generation despite sequential panel flushing.
- **Direct focus with truthful outcome:** keys 1–3 emit one identity-bound intent; success appears only after host/herdr acknowledgement; empty, stale, vanished, and offline targets reject safely.
- **Truthful fixed Codex tile:** primary/secondary usage and reset/reached cues when supplied, with independent current/stale/unavailable/auth/offline status and observation age.
- **Full cold-start/reconnect convergence:** handshake and full snapshot replacement precede input; no queued press replay or missed-delta repair is allowed.
- **Deterministic boot/offline/diagnostic states:** no blank or leftover pixels can masquerade as current assignments.
- **Host credential and data-minimization boundary:** no provider tokens, raw transcripts, arbitrary herdr methods, or host filesystem paths cross to firmware.
- **Actual-device end-to-end evidence:** one real authoritative entry is displayed and selected safely, real Codex state is rendered truthfully, and a disconnect/restart recovers through full resynchronization.

**Should have (competitive):**
- **Herdr-native dynamic attention keys:** the hardware follows the existing queue rather than fixed shortcuts or profiles.
- **Identity and state on each physical key:** this is the core advantage over RGB-only controls.
- **Race-safe reassignment:** churn causes explicit rejection rather than wrong-pane focus.
- **Minimal, restrained focus/failure feedback:** useful confirmation without animation noise.
- **Ambient LED escalation:** candidate only after display semantics, brightness, and physical LED mapping are proven; defer to v1.x if it distracts or destabilizes bring-up.
- **Self-explaining diagnostics and local brightness/text preferences:** add after the core loop unless the minimum diagnostics are needed to complete physical validation.

**Anti-features:**
- Do not bundle settle, dismiss, mark-read/unread, clear, acknowledgement, reply, approval, or arbitrary command behavior with a keypress.
- Do not recreate inbox priority in the bridge or firmware, read/write the plugin's private `state.json`, or depend on undocumented control messages as the durable seam.
- Do not focus by numeric slot, replay queued actions after reconnect, or optimistically retry an ambiguous focus timeout.
- Do not put Codex credentials, direct provider calls, raw prompts/transcripts, or a generic herdr/socket proxy on the device.
- Do not build encoder-required browsing, a generic macro system, a miniature chat/approval UI, decorative animation, LVGL, a standalone public server, hybrid transport, battery portability, or expansion-module support into v1.

**Defer (v2+):**
- Additional provider quota collectors — each requires separately validated API, authentication, null, and freshness semantics.
- Expansion modules and overflow navigation — require power, discovery, redraw, and physical interaction validation.
- General macro/action framework — expands authorization and failure semantics beyond the proven inbox loop.
- Standalone non-herdr service and broad OS support — extract only after the local plugin contract and protocol are stable.

### Architecture Approach

Use two independently testable systems joined by a small transport-neutral protocol. The host owns all upstream truth and publishes complete replaceable snapshots containing a random host epoch, monotonic revision, bounded display fields, and independent health/observation/expiry metadata for agent and Codex sources. The device validates and atomically swaps a complete snapshot, renders it, ages it using a monotonic clock, and submits only a typed `FocusIntent` bound to the displayed entry. Full snapshots are preferable to patches for four tiles: they make boot, missed-frame recovery, reconnect, host restart, and future transport changes converge without a replicated event log or second database.

**Major components:**
1. **Board support layer** — initializes and polls official panel, key, encoder, brightness, and LED APIs behind one verified physical mapping.
2. **Firmware snapshot cache and renderer** — stages bounded immutable snapshots, commits display and bindings logically together, and renders agent/quota/freshness/outcome states one panel at a time.
3. **Firmware input and protocol session** — captures the currently displayed identity, frames/deduplicates intents, correlates results, negotiates version/epoch, and never executes domain policy.
4. **USB CDC transport adapter** — handles link lifecycle, bounded framing, corruption recovery, and stable peer selection without interpreting messages; Wi-Fi implements the same interface only if selected by the gate.
5. **Inbox adapter** — obtains authoritative herdr/plugin ranking, titles, states, and live identities without reranking or touching triage persistence.
6. **Codex quota collector** — supervises app-server, initializes once per connection, obtains complete rate-limit observations, merges sparse updates only into known state or refetches, and classifies freshness independently.
7. **Snapshot assembler and device session manager** — normalizes both sources, assigns epoch/revision, publishes full replacements, tracks acknowledgement/heartbeat, and keeps only bounded in-memory derived state.
8. **Focus executor** — revalidates `(entry_id, pane_ref, epoch, revision)` and exposes only an allowlisted `agent.focus` path; stale identities reject and trigger a fresh snapshot.
9. **Herdr plugin lifecycle wrapper** — starts, supervises, and reconnects the proven bridge without making packaging the source of domain behavior.

Key invariants are host authority, full replacement, epoch plus revision, identity-bound actions, independent source health, and no durable duplicate inbox store. Transport liveness never implies upstream freshness. A timeout never proves focus failed, so the result is uncertain and requires a deliberate new press rather than automatic replay.

### Critical Pitfalls

1. **Assuming `agent.focus` is inbox-neutral** — treat this as a blocking semantic decision before the live focus slice. Measure core `seen`, status/rank/order, plugin `settled`, plugin/manual `unread`, pane identity, and terminal identity before and after focus. Do not compensate by writing flags back.
2. **Focusing by a changed slot** — bind actions to the exact rendered identity, host epoch, and snapshot revision; revalidate on the host and reject rather than substitute the current slot occupant.
3. **Publishing a torn four-panel generation** — validate into staging state, derive buffers/bindings from one immutable snapshot, and commit bindings only at a defined point after sequential rendering (or suppress presses while updating).
4. **Reimplementing lifecycle/order** — consume the installed inbox's supported derived rank/order seam; if the seam is insufficient, extend or pin it rather than copying policy or reading private persistence.
5. **Showing stale Codex values as current** — preserve null/absence, attach bridge-owned observation and source status, distinguish auth/offline/unavailable/stale, and perform a full read after reconnect before declaring current.
6. **Crossing the credential/content boundary** — keep upstream authentication and sensitive content on Linux; permit only normalized bounded snapshots and a typed focus intent.
7. **Declaring success from mocks** — require real-device gates for mapping, transport, legibility, redraw/input timing, focus semantics, quota truthfulness, outages, and soak behavior.

## Implications for Roadmap

Research supports a six-phase coarse structure. These are dependency/risk groupings for later roadmap and requirements work, **not approval of requirements or acceptance criteria**. The unresolved focus semantics can change the scope or viability of Phase 3 and therefore must be decided before that phase is committed.

### Phase 1: Physical Bring-Up, Toolchain Pinning, and Transport Characterization
**Rationale:** Every later assumption depends on the delivered board, one-panel-at-a-time behavior, physical mapping, memory headroom, and an operational data path.
**Delivers:** A reproducible official-library build; recorded PCB/library/core versions; verified panel/key/encoder/LED/orientation map; USB IDs and permissions; redraw/key-scan/memory baselines; and the shared minimal transport scenario measured over USB, with a narrow Wi-Fi comparison if needed.
**Addresses:** Physical key/display/LED bring-up and the evidence needed for legible rendering and direct key mapping.
**Avoids:** Wrong board generation, copied pin maps, five-host-panel assumptions, premature USB lock-in, hard-coded `/dev/ttyACM0`, and simulation-only completion.
**Gate:** Run `Hello → full synthetic snapshot → identity-bound key intent → result → reset/unplug/reconnect → full snapshot` on the actual unit. Select USB for v1 if it meets reliability and recovery needs; choose Wi-Fi only from measured evidence. Do not select hybrid in this phase.

### Phase 2: Protocol Contract and Offline Hardware Projection
**Rationale:** Rendering truth and race safety must exist before upstream integration can safely drive a key.
**Delivers:** Versioned bounded schemas and golden fixtures for Hello, full snapshot, per-source freshness, epoch/revision, `FocusIntent`, and `ActionResult`; a firmware snapshot cache; three-agent/one-quota renderer; deterministic empty/boot/offline/stale states; and atomic display-binding behavior on the real panels.
**Uses:** Arduino-ESP32, the official board library, LovyanGFX, ArduinoJson, and the transport selected by Phase 1.
**Implements:** Board layer, protocol session, immutable snapshot cache, renderer, input binding, and selected link adapter against a host simulator.
**Avoids:** Torn snapshots, slot-only actions, unchecked frames, per-update allocation, stale displays that look current, and key handlers reading mutable global inbox state.
**Gate:** Press-during-refresh, malformed/oversized frame, out-of-order revision, new-host epoch, source-expiry, and reconnect scenarios must preserve the visible identity/binding invariant on physical hardware.

### Phase 3: Authoritative Inbox Contract and Focus Vertical Slice
**Rationale:** This is the core product value, but it cannot proceed as an ordinary implementation phase until the focus/no-mutation conflict is resolved explicitly.
**Delivers:** A supported/pinned read-only ordered projection from the installed inbox, schema-verified herdr bootstrap/events/reconnect, top-three publishing, stable identity revalidation, one allowlisted focus path, acknowledged/rejected feedback, and a real physical key focusing the exact displayed agent.
**Addresses:** Authoritative top-three projection, glanceable identity/state, race-safe direct selection, focus outcome feedback, and focus-only safety.
**Avoids:** Priority reimplementation, plugin private-file access, stale-slot focus, generic herdr dispatch, and compensating unread/seen writes.
**Blocking semantic decision:** Public herdr `agent.focus` marks the target seen, while the installed inbox `_on_focus()` can clear manually set unread state. Before implementation acceptance, requirements must choose one of two evidence-backed outcomes: (a) permit and precisely document native focus-induced attention changes, revising the strict non-mutation promise; or (b) require an upstream/plugin device-safe focus capability that preserves the agreed state vector. The phase must not be approved on the assumption that public focus is mutation-free.
**Gate:** Capture the full before/after state vector across blocked, finished/unseen, working, idle, unknown, settled, and manually unread entries. During delayed reorder/close/move tests, the press must focus the displayed target or reject; it must never focus the replacement slot.

### Phase 4: Truthful Codex Capacity Tile
**Rationale:** Quota is independent of the focus loop and should be added after the device projection is stable so provider complexity cannot compromise selection.
**Delivers:** A pinned, schema-generated Codex app-server client; initialize/initialized lifecycle; full rate-limit reads; sparse-update merge/refetch; normalized primary/secondary windows; reached/reset cues; source-owned observation/freshness policy; and fixed tile-4 current/stale/unavailable/auth/offline states.
**Uses:** Python 3.11+ subprocess/JSON support and Codex app-server 0.147.0 with host-resident authentication.
**Avoids:** Scraping the TUI, direct backend calls, null-to-zero coercion, treating window duration as freshness TTL, trusting the first stale read, and copying account credentials to firmware.
**Gate:** Exercise the installed account's real schema and buckets, offline startup, authentication failure/recovery, sparse updates, repeated reads, expired observations, and absent optional fields on the physical tile.

### Phase 5: Resilience, Diagnostics, and Resource Hardening
**Rationale:** Independent restarts and source failures are the likely operational bottleneck; hardening follows only after both real upstream paths exist.
**Delivers:** Full resynchronization after device/host/herdr/Codex/link restart; explicit independent health; bounded retries and action dedupe; malformed-frame containment; uncertain-timeout behavior; minimum field diagnostics; and measured memory, redraw, key latency, watchdog, and long-soak behavior.
**Addresses:** Current/stale/unavailable truth states, cold-start/reconnect convergence, on-device diagnostics, and safe focus re-enable.
**Avoids:** Connected-equals-current assumptions, queued/replayed presses, dead Wi-Fi sockets if Wi-Fi was selected, hot retry loops, heap fragmentation, redraw starvation, hidden collector failures, and false success feedback.
**Gate:** On the connected unit, exercise cable/AP loss as applicable, bridge restart/new epoch, herdr restart, Codex logout/offline start, malformed input, stale target, lost result, host suspend/resume, repeated all-panel updates, and a soak with capability-specific heap and latency measurements.

### Phase 6: Plugin Packaging and Actual-Device Release Acceptance
**Rationale:** Package only a proven executable core; lifecycle convenience must not hide domain or transport failure.
**Delivers:** Herdr plugin startup/watchdog/configuration, stable least-privilege device discovery, bounded/redacted operational logs, release pins, and the complete personal-workflow acceptance scenario.
**Addresses:** Deterministic appliance behavior, host-only credentials, minimal diagnostics, and actual-device end-to-end operation.
**Avoids:** Packaging-first architecture, silent fallback priority, ambiguous multiple-device matching, leaked payloads, broad command surfaces, and release claims based on mocks.
**Gate:** The physical device displays the installed inbox's top three and real Codex status, safely focuses the displayed pane under the semantic contract chosen for Phase 3, proves non-target inbox fields remain as specified, and visibly converges after at least one real disconnect/restart.

### Phase Ordering Rationale

- Physical facts and transport recovery precede protocol commitment because panel mapping, native USB behavior, sequential redraw, and memory constraints can invalidate desktop-only assumptions.
- The normalized full-snapshot/action contract precedes upstream integration so firmware and host share race, freshness, epoch, bounds, and error semantics before real actions are enabled.
- Offline rendering precedes focus because atomic display-binding safety can be proven without exposing a live inbox to wrong-target actions.
- The authoritative inbox read path and focus contract form one vertical slice, but the `agent.focus`/manual-unread and core-seen conflict is a hard semantic prerequisite, not a later polish item.
- Codex collection follows the focus loop because it is operationally independent and should fail only the fourth tile.
- Resilience follows both integrations so failures are exercised at real boundaries rather than against mocks; packaging follows resilience so watchdogs do not conceal defects.
- Physical gates recur rather than appearing only in Phase 1: mapping, legibility, transport, focus, quota truthfulness, resource headroom, and outage recovery all require the connected unit.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Exact delivered hardware revision, ButtonSense lock, native USB identity/mode/re-enumeration, debug/protocol coexistence, Wi-Fi comparison, redraw/input timing, and memory/power data are unresolved physical facts.
- **Phase 3:** **Mandatory focused research/decision.** The installed herdr schema, stable identity across pane lifecycle, supported ordered-projection seam, and device-safe focus semantics must be established before requirements approve the live focus slice.
- **Phase 4:** The installed Codex schema, auth mode, available limit buckets, first-read behavior, sparse updates, and defensible product freshness threshold are account/version-specific.
- **Phase 5:** Soak thresholds and failure recovery depend on the transport and physical measurements selected earlier.

Phases with standard patterns (skip research-phase unless earlier gates change assumptions):
- **Phase 2:** Full snapshot replacement, epoch/revision, bounded framing, immutable rendering state, and golden fixtures are well-understood patterns; execution still requires real hardware verification.
- **Phase 6:** Plugin lifecycle packaging, least-privilege serial discovery, bounded logging, and release pinning are conventional once the executable core and semantic contract are proven.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Official board/core/library and Codex/herdr sources support the recommendation, but pioarduino is community-maintained, ButtonSense has a version discrepancy, and the exact board/build/runtime have not been exercised. |
| Features | MEDIUM | Product scope and anti-features are clear, and adjacent products support dynamic display-key expectations; real-panel legibility, desk usefulness, and the strict focus-only promise remain unvalidated. |
| Architecture | MEDIUM | Host authority, full snapshots, identity-bound intents, independent freshness, and transport separation are strong standard patterns; the authoritative inbox seam, stable identity, and physical transport are installation-specific. |
| Pitfalls | MEDIUM | Critical risks are grounded in official documentation and installed source, including the verified focus conflict; frequency, timing, resource margins, and recovery behavior require the connected setup. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Blocking focus semantics:** Decide whether native seen/unread changes are allowed or obtain device-safe upstream focus behavior before approving Phase 3; never compensate by restoring flags.
- **Authoritative inbox seam:** Establish a supported, versioned way to consume exact order/title/flags without private-file access or copied ranking; pin the inbox revision if necessary.
- **Stable action identity:** Verify which combination of entry, terminal, agent, and pane identity survives move, rename, closure, plugin restart, and herdr restart while remaining safe for focus.
- **Installed schemas and versions:** Generate herdr and Codex schemas from the actual binaries, verify compatibility ranges, auth mode, optional limit buckets, and sparse-update behavior.
- **Delivered hardware map:** Record PCB/STM32 revision, flash/PSRAM settings, four-panel orientation/order, keys, encoder, LEDs, KEY5/BOOT, and official-library compatibility.
- **USB operational proof:** Measure CDC mode, connector, VID/PID/serial stability, permissions, reset/reflash/re-enumeration, full-duplex reliability, maximum frame, and coexistence with diagnostics; retain Wi-Fi only as the tested fallback.
- **Dependency pins:** Resolve ButtonSense's manifest/tag mismatch and capture immutable firmware dependency artifacts.
- **Physical UX/performance:** Validate title discrimination, state legibility, glare/viewing distance, sequential redraw latency, press timing, DMA/internal/PSRAM headroom, LED power, brownouts, and soak stability.
- **Freshness policy:** Define product TTL/expiry semantics independently for herdr and Codex from observed account/update behavior; transport connectivity cannot set either current.
- **Wi-Fi/hybrid scope:** If USB fails its gate, validate Wi-Fi provisioning, authentication, AP/DHCP/host-suspend recovery, and memory cost. Hybrid remains out of scope unless measurements establish a concrete need and deterministic authority.

## Sources

### Primary (HIGH confidence)
- [Project definition](../PROJECT.md) — local authoritative product goal, constraints, focus-only intent, and exclusions.
- Installed `herdr-agent-inbox` README and source at revision `de409f683262` — authoritative for this machine's rank/title/settle/unread behavior, TUI ordering, focus handling, and the verified manual-unread mutation conflict; not assumed stable across future revisions.

### Secondary (MEDIUM confidence)
- [Official LILYGO T-Keyboard-S3-Pro Library](https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library) and [library guide](https://wiki.lilygo.cc/products/other/t-keyboard-s3-pro/library.html) — four host panels, STM32-mediated selection, key/encoder/LED APIs, sequential panel access, and Arduino 3.x requirement.
- [Official LILYGO hardware repository](https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro) — PCB/component evidence, legacy build flags, USB CDC baseline, and older examples requiring physical reconciliation.
- [Arduino-ESP32 3.3.11](https://github.com/espressif/arduino-esp32/releases/tag/3.3.11), [USB CDC](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/usb_cdc.html), and [ESP32-S3 USB device documentation](https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_device.html) — pinned firmware core and native USB behavior.
- [pioarduino platform-espressif32 55.03.311](https://github.com/pioarduino/platform-espressif32/releases/tag/55.03.311) — packaged Arduino-ESP32 3.3.11/ESP-IDF 5.5.5 pair; community-maintained and therefore pinned immutably.
- [LovyanGFX 1.2.26](https://github.com/lovyan03/LovyanGFX/releases/tag/1.2.26) and [ArduinoJson 7.4.3](https://github.com/bblanchon/ArduinoJson/releases/tag/v7.4.3) — rendering and bounded protocol dependencies.
- [herdr 0.8.0 Socket API](https://herdr.dev/docs/socket-api/) and [CLI reference](https://herdr.dev/docs/cli-reference/) — schema generation, snapshots/events, public focus, lifecycle, and focus-marks-seen behavior.
- [OpenAI Codex app-server protocol](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md), [v2 account schema](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/account.rs), and [Codex 0.147.0](https://github.com/openai/codex/releases/tag/rust-v0.147.0) — initialization, full rate-limit reads, sparse updates, nullable fields, and version-specific schema generation.
- [Espressif Wi-Fi driver](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/wifi-driver/overview.html), [ESP-TLS/security](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/protocols/esp_tls.html), [external RAM](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/external-ram.html), and [heap allocator](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/mem_alloc.html) — reconnect, authentication, PSRAM/DMA, and capability-specific measurement constraints.
- [OpenAI Codex issue #26789](https://github.com/openai/codex/issues/26789) and [issue #33897](https://github.com/openai/codex/issues/33897) — current reports of offline-start and first-read/stale-limit failures; evidence of risks, not universal behavior.
- [Elgato Stream Deck SDK keys](https://docs.elgato.com/streamdeck/sdk/guides/keys/) and [devices](https://docs.elgato.com/streamdeck/sdk/guides/devices/) — adjacent dynamic-key and reconnect expectations.
- [OpenAI Codex Micro](https://openai.com/supply/co-lab/work-louder/) — adjacent evidence for live physical agent state and tactile controls, not this project's semantics.
- [pyserial 3.5](https://pypi.org/project/pyserial/) — conservative Python serial integration baseline; target-host behavior still needs proof.

### Tertiary (LOW confidence)
- ButtonSense [`library.json`](https://github.com/lbuque/ButtonSense/blob/master/library.json) and [tags](https://github.com/lbuque/ButtonSense/tags) — required API is supported by the board library, but the 1.0.0 manifest versus 0.1.0 tag discrepancy prevents a reproducible pin until resolved.
- Preliminary local note, *LILYGO T-Keyboard S3 Pro - physical Hermes AI inbox* (2026-08-15) — used only for leads and cross-checks; conflicting proposals such as encoder navigation, mutations, multi-provider tiles, and a standalone service were rejected.

---
*Research completed: 2026-08-16*
*Ready for roadmap: yes — subject to explicit focus-semantics resolution before the focus vertical slice*
