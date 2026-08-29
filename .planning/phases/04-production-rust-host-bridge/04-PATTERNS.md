# Phase 04: Production Rust Host Bridge — Pattern Map

**Mapped:** 2026-08-30  
**Files analyzed:** 30 planned, modified, retired, or release-owned paths  
**Analogs found:** 25 / 30 (the five unmatched paths are new Rust/release seams)

This map is an implementation reference, not a plan. The current repository has no Rust host crate. The Python bridge and focused firmware/native tests are the behavioral oracle; the Phase 04 implementation must copy their observable boundaries, not their Python object layout or their developer-only launch machinery.

## File Classification

| New/modified/retired file | Role | Data flow | Closest current analog | Match quality |
|---|---|---|---|---|
| `host/herdr_keypad/native/Cargo.toml` | build/config | dependency/build metadata | `platformio.ini:6-36` | role-match |
| `host/herdr_keypad/native/Cargo.lock` | build/lock | reproducible dependency resolution | `platformio.ini:7-36` pinned URLs/versions | partial |
| `host/herdr_keypad/native/rust-toolchain.toml` | build/config | compiler target selection | `platformio.ini:7-21` pinned platform/board | partial |
| `host/herdr_keypad/native/src/main.rs` | entrypoint/lifecycle | request-response + long-lived event loop | `bridge.py:498-688,859-1095`; `__main__.py:27-338` | role-match (cutover) |
| `native/src/core/{mod,state,projection,focus,orchestrator,health}.rs` | portable core | event-driven transform/state machine | `projection.py:127-386`; `focus.py:33-140`; `bridge.py:219-273,580-688` | exact behavior |
| `native/src/protocol/{mod,v2}.rs` | protocol/codec | bounded framed request-response | `tools/phase1_bringup/.../protocol.py:358-623`; firmware `protocol.h:8-103` | exact contract |
| `native/src/ports/herdr.rs` | adapter port | NDJSON request + invalidation stream | `herdr.py:26-319` | exact boundary |
| `native/src/ports/codex.rs` | adapter port | child JSONL request-response + sparse event | `codex.py:325-674` | exact boundary |
| `native/src/ports/usb.rs` | adapter port | serial framed request-response + device events | `usb.py:33-249` | exact boundary |
| `native/src/ports/clock.rs` | port | timer/freshness time source | `bridge.py:522-561,690-750`; `codex.py:331-391` | role-match |
| `native/src/ports/config.rs` | port | validated settings/binding file I/O | `pairing.py:28-85`; `usb.py:41-63` | role-match |
| `native/src/ports/control.rs` | port | bounded local control IPC | `ensure-bridge.sh:44-92` (lock assumptions only) | partial; no safe IPC analog |
| `native/src/ports/status.rs` | diagnostic port | read-only normalized status | `bridge.py:690-718`; `protocol.py:341-355` diagnostics | role-match |
| `native/src/ports/logging.rs` | diagnostic port | default-off bounded redacted stderr tracing | `codex.py:677-688`; `bridge.py:1098-1276` evidence redaction | partial |
| `native/src/ports/lifecycle.rs` | lifecycle port | Herdr process monitoring + explicit actions | `bridge.py:597-615,834-878`; launcher traps | partial; Herdr v0.8.2 semantics replace supervision |
| `native/src/platform/linux.rs` | platform adapter | Linux serial/path/lock/signal I/O | `discovery.py:68-111`; `99-herdr-keypad.rules:1-4`; launcher | role-match |
| `native/src/platform/macos.rs` | platform adapter | macOS serial/path/signal I/O | `discovery.py:68-139` | partial; no macOS implementation exists |
| `native/tests/protocol_parity.rs` | test | fixture transform/validation | `test_protocol.py:14-116`; `test/protocol/test_main.cpp:132-195` | exact test shape |
| `native/tests/projection_focus_parity.rs` | test | black-box state/action traces | `test_projection.py:17-88`; `test_focus.py:37-112`; integration tests | exact test shape |
| `native/tests/codex_parity.rs` | test | child protocol/normalization traces | `test_codex.py:49-377` | exact test shape |
| `native/tests/lifecycle_resource.rs` | test | event/reconnect/resource transitions | `test_integration.py:188-685`; bridge loop | exact test shape |
| `native/tests/fixtures/v2-golden.json` (or referenced root fixture) | test fixture | canonical wire vectors | `protocol/fixtures/v2-golden.json`; `test/protocol/test_main.cpp:149-166` | exact |
| `host/herdr_keypad/herdr-plugin.toml` | plugin manifest | installation/startup/event invocation | current manifest lines 1-13 | role-match, semantics replaced |
| `host/herdr_keypad/scripts/ensure-bridge.sh` | retired launcher | shell lifecycle/lock/Python runtime | itself lines 44-106 | anti-pattern to remove from production |
| `host/herdr_keypad/src/herdr_keypad/__main__.py` | retired/migration oracle | production vs developer commands | itself lines 27-338 | anti-pattern to remove from bundle |
| `protocol/schema/v2.json` | canonical protocol schema | closed wire contract | itself; firmware `protocol.h` | preserve unchanged |
| `protocol/fixtures/v2-golden.json` | canonical parity fixture | accepted/rejected wire vectors | itself; native protocol test | preserve unchanged |
| `host/udev/99-herdr-keypad.rules` | Linux install/permission metadata | exact CDC admission | itself lines 1-4 | exact platform analog |
| `bundle/linux-x86_64/...`, `bundle/macos-aarch64/...` | plugin packaging | target artifact selection | `herdr-plugin.toml:1-13`; `platformio.ini:6-36` | partial |
| `.github/workflows/native-release.yml` (new) | release automation/CI | cross-target build/sign/hash/package | no repository workflow exists; `platformio.ini` is build-only | no analog |

**Path convention:** The `native/src` grouping is the recommended structure from `04-RESEARCH.md`; exact Rust module splitting is discretionary. Keep the ownership seams below even if modules are named differently.

## Pattern Assignments

### Portable core and entrypoint

#### `host/herdr_keypad/native/src/main.rs` (entrypoint, long-lived event-driven lifecycle)

**Analogs:** `host/herdr_keypad/src/herdr_keypad/bridge.py`, `host/herdr_keypad/src/herdr_keypad/__main__.py`.

**Composition and dependency injection** — `bridge.py:516-561` constructs one `PermanentBridge` from client, USB, projection, clock, and optional Codex collector, then tracks readiness, health ages, focus generation, and reconnect deadlines. Preserve that dependency direction: `main.rs` wires platform adapters into a portable coordinator; policy does not enter platform modules.

**Boundary coordinator behavior** — `bridge.py:1023-1070` consumes a bounded number of push events, polls only when push is unavailable, drains device frames, polls Codex only at its explicit deadline, and refreshes only when dirty. Its production replacement should use Tokio `select!`/bounded channels and timers, not reproduce `time.sleep(0.1)` from `bridge.py:1072-1095`.

**Startup and process-bound recovery** — Herdr's one-shot startup hook launches the executable. While that Herdr process remains alive, temporary socket/API failure or a missing paired device marks only that boundary unavailable and enters bounded reconnect. The executable monitors the Herdr socket/process boundary and exits on Herdr shutdown. It does not survive Herdr restart or auto-restart after its own crash (D-01 through D-08).

**Production/developer separation** — `__main__.py:27-338` currently mixes `--run-bridge`, smoke, inspect, live-sync, and evidence paths. Use it only as a migration inventory. `main.rs` exposes startup mode plus explicit start, stop, restart, status, repair, and re-pair action modes. No fixture, tracer, evidence, shell, source-checkout, or credential-output path belongs in the shipped binary.

#### `native/src/core/state.rs`, `orchestrator.rs`, `health.rs` (portable state machine)

**Analog:** `bridge.py:597-688,690-750`.

- `_fence_disconnected` sets link offline, clears readiness/focus, and closes the event stream (`bridge.py:597-615`).
- `_mark_unavailable` retains a stale/offline projection, disables actionability, and may publish that truthful veil (`bridge.py:644-657`).
- `_publish_snapshot` requires an accepted matching snapshot ACK and a complete current projection before `ready = true` (`bridge.py:659-687`).
- `_diagnostics` emits bounded statuses, ages, firmware/device/session/revision suffixes and allowlisted error code only (`bridge.py:690-718`).

Core owns source/device/Codex state, freshness, readiness, safe diagnostic normalization, generation/session fences, and publication ordering. Adapters only transport. Codex health must remain independent of Herdr/link health (`test_integration.py:346-360`). Do not let a source outage become an empty/current snapshot or let a link outage relabel Codex authentication.

#### `native/src/core/projection.rs` (authoritative inbox projection)

**Analog:** `projection.py:127-190,232-335,337-386`; tests `test_projection.py:17-88`.

**Normalization:** `_normalize` requires identity fields and `tokens.rank`, maps the installed literal rank 0..5, bounds text, and creates an opaque identity (`projection.py:154-190`). Missing rank is an unavailable source, never a locally invented priority.

**Ordering and fixed capacity:** `_project_entries` sorts `(rank, -state_change_seq)`, truncates to `MAX_SLOTS`, fills explicit empty entries, and stabilizes the source revision for a logically unchanged entry (`projection.py:232-290`). Preserve three slots and the installed order exactly. `test_projection.py:18-35` is the compact expected ordering/tie/empty trace.

**Revision and invalidation:** `refresh` increments only on material projection changes (`projection.py:300-335`); `invalidate` increments, preserves identity, marks entries stale/offline, and makes `binding()` return `None` (`projection.py:347-386`). Events invalidate; a complete authoritative read restores current order. Never move ordering policy into USB, firmware, or the Herdr transport adapter.

#### `native/src/core/focus.rs` (exact focus authorization)

**Analog:** `focus.py:33-140`; tests `test_focus.py:43-112`.

`FocusExecutor.execute` rejects missing/stale source, wrong host/device epoch, invalid slot, or mismatched pane identity before any write (`focus.py:75-105`). It re-reads `agent.list`, compares pane/terminal/workspace/tab/session identity, then calls only `client.focus(pane_id)` (`focus.py:95-122`). A response must be an AgentInfo with matching identity and `focused=true`; one unfocused acknowledgement may be retried (`focus.py:123-140`).

This is the sole Herdr write seam. Preserve status vocabulary (`vanished`, `uncertain`, `pane_reused`, `session_changed`, `rejected`, `accepted`, etc.), exact host epoch/snapshot revision/session binding, and the prohibition on settle/unread/clear/arbitrary actions. The test explicitly asserts only `agent.list` then `agent.focus` and no triage calls (`test_focus.py:43-48,99-112`).

### Closed protocol and firmware compatibility

#### `native/src/protocol/v2.rs` (Rust protocol codec)

**Analogs:** `tools/phase1_bringup/src/phase1_bringup/protocol.py:358-504,518-623`, `firmware/src/protocol/protocol.h:8-103`, and `test/protocol/test_main.cpp:149-195,286-395`.

**Closed payloads:** `validate_v2_payload` requires exactly the four product types, exactly three agent slots, bounded identities/text, nullable Codex values, and allowlisted diagnostic codes (`protocol.py:358-428`). It rejects unknown fields, invalid shape, out-of-range percentages, and non-allowlisted errors; preserve the distinction between null and zero from `test_protocol.py:53-99`.

**Envelope/admission:** `validate_v2_frame`, `encode_v2_frame`, and `classify_v2_line` enforce closed envelope, v2, positive uint32 sequence/reply, canonical digest, 4096-byte line cap, LF, duplicate-key and nesting policy (`protocol.py:453-504`). Firmware’s equivalent fixed buffers and rejection vocabulary are in `protocol.h:8-71`.

**Session fencing:** `ProtocolSession` resets boot/session/sequence authority, rejects mismatched boot/session, duplicate and out-of-order frames, and bounds pending frames at 16 (`protocol.py:518-623`). Firmware mirrors this with `ProtocolSession::reset`, `accept`, `complete`, and bounded sequence memory (`protocol.h:74-103`). Rust should share root golden vectors rather than fork Python or firmware parsing rules.

#### `native/src/ports/usb.rs` (exact paired USB adapter)

**Analogs:** `usb.py:33-185,201-249`, `discovery.py:32-139`, `pairing.py:28-85`, and Linux rule `host/udev/99-herdr-keypad.rules:1-4`.

- Read the frozen binding in place. `PairingBinding.from_dict` requires `schema_version: 1`, opaque non-`host` device ID, protocol 1, and non-empty firmware; `PairingStore.load` does not rewrite malformed state (`pairing.py:28-63`).
- Enumerate measured VID/PID/serial/interface candidates, then require exact application hello identity. Descriptor/path/first-match is not authorization (`discovery.py:99-139`). The current expected tuple and interface gate are exercised by `test_integration.py:686-723`; wrong serial/interface must never reach hello (`test_integration.py:724-751`).
- On each connect, clear pending focus, create a fresh boot/session/sequence authority, verify hello device/firmware/protocol, and close on mismatch (`usb.py:81-113`).
- Device v2 requests must match boot/session, reject stale sequence, correlate `reply_to`, queue at most 16 interleaved focus intents, and clear pending work on errors/close (`usb.py:124-169,208-240`). Snapshot publication is the only readiness gate; focus results are fire-and-forget validated v2 frames (`usb.py:171-185`).

`usb.rs` owns serial frame transport and exact-device admission only. Core owns action authorization and generation policy. Firmware remains the HID Space owner; the bridge must not synthesize Space-up on stop/crash/reconfigure (D-09).

#### Firmware protocol and board analogs (do not modify for Phase 04)

`firmware/src/main.cpp:147-181` shows the existing bounded payload scratch buffers, protocol version selection, digest encoding, complete-write accounting, and sequence increment only after a successful write. `firmware/src/board/board_adapter.cpp:191-215,288-309` shows the hardware adapter’s readiness guard, input latch behavior, and sequential panel ownership. These are compatibility references, not host Rust implementation targets. `test/test_agent_projection/test_main.cpp:225-299,303-375` demonstrates compose/flush commit, failed panel fallback, diagnostics, and fenced bindings; the Rust bridge must preserve the wire/readiness semantics that these firmware tests assume.

### Herdr, Codex, and lifecycle adapters

#### `native/src/ports/herdr.rs` (Herdr request/event adapter)

**Analog:** `herdr.py:26-122,124-319`.

`HerdrClient.request` uses one bounded NDJSON JSON-RPC response per connection, validates method text, caps reads at 65,536 bytes, correlates response IDs, and maps malformed/error/missing results to `HerdrError` (`herdr.py:40-78`). The adapter exposes `session.snapshot`, `agent.list`, `workspace.list`, typed `events.subscribe`, and the sole `agent.focus` transport (`herdr.py:80-122`).

`HerdrEventStream` opens a separate persistent socket, sends typed subscriptions, admits push only after a correlated subscribe ACK, caps lines, validates `{event,data}`, and falls back to bounded polling on timeout/EOF/malformed stream (`herdr.py:124-319`). Core treats events as invalidation triggers; it never derives ordering from event payloads. The push ACK/event behavior is covered by `test_integration.py:910-963`.

#### `native/src/ports/codex.rs` (Codex app-server adapter)

**Analog:** `codex.py:183-303,325-674`; tests `test_codex.py:68-231,302-377`.

Spawn the direct argv child `codex app-server --stdio`, send exactly `initialize`, `initialized`, `account/read`, then `account/rateLimits/read` (`codex.py:608-650`). Cap lines at 4096 bytes and map timeout, EOF, malformed JSON, auth evidence, and process errors to bounded states/codes (`codex.py:531-572,653-670`). Stop/kill the child in bounded time without retaining raw stderr/stdout (`codex.py:582-606`).

Normalize only top-level `rateLimits`; null is not zero, unsupported/conflicting durations are unavailable, and a sparse update cannot establish a baseline (`codex.py:285-303,401-516`). Account changes clear the cache (`codex.py:518-529`). Freshness is computed from observation age and explicit polling deadlines (`codex.py:364-391`). Redaction recursively rejects sensitive keys without exposing their values (`codex.py:677-688`). The detailed edge matrix is in `test_codex.py:124-190,302-377`.

The adapter owns child process I/O and schema-shaped parsing; core owns independent Codex health, freshness, and publication. It must not leak account identity, credentials, prompts, paths, provider responses, or raw child errors.

#### `native/src/ports/lifecycle.rs` and `native/src/ports/control.rs` (single authority)

**Closest legacy analog:** `scripts/ensure-bridge.sh:44-106` and lifecycle portions of `bridge.py:597-615,834-878`; these are migration liabilities, not patterns to copy literally.

The shell launcher holds `flock` across `exec`, uses PID/`/proc` checks, and launches Python through source/venv/PYTHONPATH (`ensure-bridge.sh:44-106`). Rust replaces these Linux-only assumptions with an exclusive cross-platform lock plus bounded same-user local control IPC under Herdr's plugin state directory. A stale socket/PID is not proof of ownership. Same-effective-config start returns active/idempotent. Changed settings return restart-required; only explicit restart replaces authority. Status is read-only.

**Verified Herdr v0.8.2 contract:** v0.8.2 is the latest stable release, published 2026-08-19. Its immutable release notes, exact tagged source, and installed generated schema show direct-argv startup/event/action commands and invocation logs. They show no supervised child, crash restart/backoff, timeout/cancel/kill, disable/unlink stop, logout hook, first-class status publication, streaming log ingestion, or live settings callback. Plugin commands spawn and wait; disable changes registry state; unlink explicitly leaves panes running. These are supported constraints, not a capability gate. `[CITED: https://github.com/herdrdev/herdr/releases/tag/v0.8.2; https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/runtime.rs#L100-L143; https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/mod.rs#L113-L136; https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/mod.rs#L613-L640; VERIFIED: installed Herdr 0.8.2 generated schema lines 5712-5830]`

Lifecycle follows that contract. Startup launches the executable. The executable monitors the Herdr socket/process boundary and exits on Herdr shutdown. A crash stays stopped until an explicit idempotent start/restart action or the next Herdr start. Disable/removal instructions require explicit stop first. No OS service, background shell daemon, watchdog, or second runtime is allowed. Plugin updates activate on explicit restart or the next Herdr start.

#### `native/src/ports/status.rs` and `logging.rs` (diagnostic surfaces)

**Analogs:** bridge diagnostics `bridge.py:690-718`, protocol diagnostic schema `protocol.py:341-355`, and bounded evidence/redaction helpers `bridge.py:1098-1276`, `codex.py:677-688`.

Status derives from normalized core state only and is served by bounded same-user local IPC to a read-only Herdr `status` action. It reports device-link, Herdr, and Codex states; version; short safe identity/config prefix; reconnect/backoff; one safe error code; and a bounded transition ring. Operational tracing is disabled by default. When enabled through validated plugin config, it writes bounded structured redacted events to stderr for Herdr command-log capture. Do not add file logging, rotation, journald, unified-log ownership, or a streaming log contract. Do not copy `write_acceptance_evidence` or tracer outputs into production.

### Platform and configuration seams

#### `native/src/platform/linux.rs` and `macos.rs` (OS-only adapters)

**Linux analogs:** `discovery.py:68-111`, `host/udev/99-herdr-keypad.rules:1-4`, and launcher path setup `ensure-bridge.sh:4-11`. The udev rule deliberately matches tty/USB, measured VID/PID/serial, interface `01`, `MODE=0660`, `dialout`, and `uaccess`, while refusing broad `ttyACM*` or mode 0666. Preserve exact-device matching; do not use transient `/dev/ttyACM*` order.

**macOS:** no existing repository implementation. Keep native metadata lookup, `/dev/cu.*` opening, per-user paths, signal/suspend handling, and any permissions behind this adapter. The Python candidate normalization (`discovery.py:68-82`) is the portable shape; the exact composite-interface property mapping requires target-native verification. Do not add macOS logic to core or claim local Linux evidence as macOS proof.

#### `native/src/ports/config.rs` (binding and one settings authority)

**Analog:** `pairing.py:28-85`, `usb.py:50-63`, and `projection.py:130-139`.

The existing `~/.config/herdr/keypad-binding.json` is authoritative and frozen. Read/validate it without rewriting or migrating (D-14). Invalid/incompatible state stays unchanged, produces a bounded diagnostic, and never falls back to another device. Ordinary install uses Herdr runtime paths and platform defaults. Advanced overrides live only under `HERDR_PLUGIN_CONFIG_DIR`, validate at startup, and apply only after explicit restart (D-15/D-16). Do not watch config, preserve old developer environment variables from `__main__.py`, or add another external TOML/env/CLI authority.

### Plugin packaging and release automation

#### `host/herdr_keypad/herdr-plugin.toml` (manifest cutover)

**Current analog:** lines 1-13 contain metadata, `min_herdr_version`, Linux-only `platforms`, a shell startup command, and a pane event command. The production replacement selects a bundled native executable for Linux x86-64 and macOS Apple Silicon, with direct argv and no Python/venv/source path. Its startup hook launches the long-running binary; actions expose start, stop, restart, status, repair, and re-pair. Do not infer supervision or automatic disable/unlink stop from `[[startup]]`; process/socket monitoring and explicit actions implement the approved v0.8.2 lifecycle.

#### `bundle/...` (target artifacts)

**Partial analogs:** `platformio.ini:6-36` pins immutable pioarduino/LILYGO/ButtonSense/LovyanGFX/ArduinoJson inputs; firmware test environments at `platformio.ini:69-140` show isolated native test/build filters. Reuse the principle of explicit target/dependency pinning, but do not put firmware artifacts or Python runtime files in the host plugin bundle. Bundle exactly one executable selected for each required target plus static manifest metadata. No Intel macOS or ARM64 Linux artifact is required by D-11.

#### `.github/workflows/native-release.yml` (new; no current analog)

No `.github/workflows` exists in this repository and no release workflow is present. The only build automation analog is PlatformIO configuration. The release seam therefore has no copyable CI implementation: create target jobs that pin Rust/toolchain/Cargo.lock, run `cargo build --release --locked`, inspect dynamic dependencies, compare unsigned SHA-256 outputs from clean runs, and separately perform macOS Apple Silicon signing/notarization/stapling. Keep signing timestamps out of byte-reproducibility claims. This is release automation only; it must not become a runtime service or a second packaging authority.

## Parity and Test Assignments

### Protocol vectors — `native/tests/protocol_parity.rs`

Copy the fixture-driven structure from Python `test_protocol.py:24-42` and firmware `test/protocol/test_main.cpp:149-166`: load root `protocol/fixtures/v2-golden.json`, classify every accepted/rejected line, compare reason and dispatch, and exercise the 4096-byte boundary. Add the closed-field/null-zero/diagnostic matrix from `test_protocol.py:44-116`; preserve the root schema/fixture hash checks rather than generating a second protocol fixture.

### Projection/focus — `native/tests/projection_focus_parity.rs`

Use pure black-box traces from `test_projection.py:18-88` (order, rank ties, empty fill, invalid rank/identity, bounded non-path labels, invalidation, raw-revision churn) and `test_focus.py:43-112` (revalidation, one retry, exact identity, stale rejection, vanished/timeout distinction). Integration traces in `test_integration.py:376-511` prove sole `agent.focus`, deferred focus only after matching ACK, and mutable projection churn behavior.

### Lifecycle/resource — `native/tests/lifecycle_resource.rs`

Lift the event/reconnect cases from `test_integration.py:512-685`: old USB session is replaced, complete snapshot ACK precedes readiness, event stream is rebuilt, deferred focus is discarded across disconnect, reconnect attempts are capped/backoff is deterministic, and transient errors do not spin. Add event-driven idle/resource assertions from the research matrix, but do not turn tests into physical Phase 5 acceptance.

### Codex — `native/tests/codex_parity.rs`

Use `FakeProcess`/injected process-factory shape from `test_codex.py:22-66`, then port the handshake, zero/null, sparse baseline, unsupported duration, auth/offline, child exit, bounded line, freshness, account-change, and redaction assertions (`test_codex.py:68-377`). Tests must observe normalized outputs and child lifecycle, never Python internals.

### Firmware/native compatibility

`test/protocol/test_main.cpp:286-395` is the firmware-side closed-v2 and session-fence oracle. `test/test_agent_projection/test_main.cpp:225-299,303-375,480-535,698-780` proves staged commit, one-push-per-panel ordering, diagnostics, fenced bindings, focus outcomes, and device-owned hold state. Phase 04 should exercise host behavior against these existing wire/state contracts; it must not add a protocol message for HID hold or change firmware authority.

## Shared Patterns

### One source-of-truth projection

**Sources:** `projection.py:154-190,232-335`; `test_projection.py:18-35`.  
**Apply to:** core projection, Herdr adapter, USB snapshot publication, parity tests.  
Events only invalidate. Complete `agent.list`/`workspace.list` reads establish order and slots. No adapter, firmware, or test helper may implement a competing priority algorithm.

### Independent boundary health and freshness

**Sources:** `bridge.py:690-750,777-878`; `codex.py:364-432`; `test_integration.py:346-360`.  
**Apply to:** core health, Herdr/Codex/USB ports, status/logging.  
Preserve current/stale/unavailable/offline/auth-required distinctions. A stale/offline veil retains orientation but disables actions; only complete current projection plus device ACK restores readiness.

### Generation/session/identity fencing

**Sources:** `bridge.py:580-688,916-989`; `usb.py:124-169,208-240`; `protocol.py:518-623`; `focus.py:75-140`.  
**Apply to:** core, USB, focus, explicit restart, suspend, tests.  
Every USB reconnect, explicit restart, or surviving-process suspend/resume creates fresh authority. Clear pending focus, reject old result/session/revision/identity, and never replay a disconnected press. Keep pending/concurrent focus bounded at 16.

### Strict bounded admission

**Sources:** `protocol.py:358-504`; `herdr.py:40-78,212-237`; `codex.py:531-580`; firmware `protocol.h:8-71`.  
**Apply to:** every external line/control payload.  
Check byte length before allocation, enforce closed fields, duplicate/nesting/identifier limits, sequence/reply correlation, and fixed error vocabulary. Keep device (4096), Herdr (65536), Codex (4096), and control/status (recommended 16 KiB) limits separate.

### Redacted bounded diagnostics

**Sources:** `bridge.py:690-718,1098-1276`; `codex.py:677-688`; `test_codex.py:254-300`.  
**Apply to:** status, logs, lifecycle errors, parity assertions.  
Expose only allowlisted codes, versions, short safe suffixes/identities and timings. Never expose credentials, account identity, prompts, transcripts, paths, raw upstream errors, child streams, or developer evidence payloads.

### Device-owned HID authority

**Sources:** Phase 04 decisions D-09; firmware hold/projection tests `test/test_agent_projection/test_main.cpp:698-780`; firmware `main.cpp:70-89`.  
**Apply to:** USB result path, shutdown/reconfigure/suspend, lifecycle tests.  
Host sends exact focus results only. Once firmware asserts Space, bridge stop/crash/replacement does not synthesize key-up or assume ownership; physical release/device removal/reset/suspend follows the existing firmware contract.

## Ownership and Shared-File Conflict Boundaries

Use these boundaries when splitting implementation waves; avoid concurrent edits to the same seam:

| Shared file/seam | Single owner | Other waves may consume, but must not redefine |
|---|---|---|
| `protocol/schema/v2.json`, `protocol/fixtures/v2-golden.json` | protocol-contract wave | Rust codec, firmware tests, parity tests |
| `native/src/core/*` domain models/state | portable-core wave | Herdr/Codex/USB adapters, status, platform code |
| `native/src/protocol/*` | protocol wave | core and adapters call it; no new device types |
| `native/src/ports/herdr.rs` | Herdr adapter wave | core supplies policy; lifecycle wave supplies capability result |
| `native/src/ports/codex.rs` | Codex adapter wave | core owns state/freshness; no raw diagnostic forwarding |
| `native/src/ports/usb.rs` + platform discovery | USB/platform wave | core owns generation/actionability; Linux/macOS own only OS I/O |
| `native/src/ports/lifecycle.rs` + `control.rs` | lifecycle/control wave | manifest and status consume the verified Herdr v0.8.2 contract |
| `native/src/ports/status.rs` + `logging.rs` | diagnostics wave | core emits normalized state; status uses read-only IPC; optional stderr tracing is default-off |
| `herdr-plugin.toml` | packaging/cutover wave | consumes bundled binary paths and the fixed startup/action contract |
| `.github/workflows/native-release.yml`, `bundle/` | release wave | consumes Cargo target/toolchain decisions; cannot alter runtime behavior |
| Existing Python modules/tests | parity-oracle wave | remain unchanged as behavioral oracle until cutover evidence is complete |
| Firmware `firmware/src/*`, native PlatformIO tests | compatibility owner (prior phases) | Phase 04 host work must preserve their wire and HID assumptions |

## No Analog Found

| Path/capability | Why no close analog | Planner implication |
|---|---|---|
| `native/src/platform/macos.rs` | No macOS host adapter exists in the repository | Define an explicit native-runner checkpoint for serial metadata/open/permissions; do not infer from Linux. |
| `native/src/ports/control.rs` | Existing launcher has only Linux `flock`/PID/`/proc`; no bounded cross-platform control IPC | Use an exclusive lock plus bounded same-user local IPC for explicit actions/status; prove peer checks on each target. |
| `native/src/ports/lifecycle.rs` | No Herdr-supervised child exists | Use verified v0.8.2 startup plus Herdr process/socket monitoring. Crash recovery is explicit action or next Herdr start; stop before disable/removal. No service or watchdog. |
| `native/src/ports/status.rs`/`logging.rs` Herdr sinks | Existing bridge diagnostics are device payload/evidence, not action output or command-log tracing | Implement the accepted read-only status action and default-off redacted stderr tracing; do not invent first-class publication or streaming ingestion. |
| `.github/workflows/native-release.yml` and signed bundles | No repository CI/release workflow or native host bundle exists | Build/sign/notarize on appropriate runners; compare unsigned artifacts and separately record signing/ticket evidence. |

## Metadata

**Analog search scope:** `host/herdr_keypad/src/herdr_keypad`, `host/herdr_keypad/tests`, `host/herdr_keypad/scripts`, `host/udev`, `tools/phase1_bringup/src/phase1_bringup`, `test/protocol`, `test/test_agent_projection`, `firmware/src`, root `platformio.ini`, plugin manifest, and repository workflow paths.  
**Files scanned:** 26 existing source/test/config analogs plus root protocol/build metadata.  
**Primary evidence:** local source files and focused test fixtures; Herdr capability status uses the latest stable v0.8.2 release metadata, exact tagged source, and installed generated schema.  
**Non-goals honored:** no source implementation, plan, protocol expansion, OS service, shell daemon, second runtime/config/log authority, UAT, physical qualification, formatter/linter, project-wide build, or project-wide test run.
