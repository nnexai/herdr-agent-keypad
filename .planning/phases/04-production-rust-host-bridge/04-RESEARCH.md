<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
### Launch and lifecycle
- **D-01:** Herdr owns the bridge session through the bundled plugin's one-shot startup hook. The hook launches the executable directly, with no OS service, background shell daemon, separate runtime, or foreground command. Herdr does not supervise the child after launch.
- **D-02:** The bridge monitors the Herdr socket and process boundary, may recover temporary API unavailability while that Herdr process lives, and exits on Herdr shutdown. A later Herdr start launches a fresh bridge.
- **D-03:** A temporarily unavailable socket or missing exact paired keypad is not fatal while the launching Herdr process remains alive. Each boundary reconnects independently, and complete authoritative resynchronization precedes actions.
- **D-04:** Herdr shutdown and explicit stop intentionally stop the bridge. Disable/unlink does not stop it on Herdr 0.8.2, so disable/removal instructions require explicit stop first. No logout hook is claimed.
- **D-05:** Explicit start/restart actions use same-user local control IPC and are idempotent. A matching start reports the active instance without disturbing it; restart deliberately replaces authority.
- **D-06:** One bridge owns authority. Settings exist only under `HERDR_PLUGIN_CONFIG_DIR`, validate at startup, and take effect through explicit restart or the next Herdr start. Changed settings never reconfigure live or start a second bridge.
- **D-07:** A crash does not auto-restart during the same Herdr session. Recovery is explicit idempotent start/restart or the next Herdr start. No watchdog, service, second runtime, or hidden daemon substitutes for supervision.
- **D-08:** If Herdr remains alive across suspend/resume, the same bridge invalidates old sessions and resynchronizes before restoring actions. If Herdr exits, the bridge exits and the next Herdr start launches a fresh process.
- **D-09:** HID Space is owned by firmware after the device asserts it. Bridge stop, crash, reconfiguration, or replacement must not synthesize Space-up or assume keyboard authority. Physical owner release, device removal/reset, or USB suspend ends the HID state through the existing firmware contract.

### Install and upgrades
- **D-10:** Bundle the correct native executable inside the Herdr plugin. Installing the plugin installs the whole production integration; no standalone bridge package, runtime, or package-manager dependency is required.
- **D-11:** Phase 4 release targets are Linux x86-64 and macOS Apple Silicon. Intel macOS and ARM64 Linux artifacts are not required for this phase.
- **D-12:** A plugin update activates on explicit restart or the next Herdr start. The old authority ends before the new executable establishes fresh USB, Herdr, and Codex sessions. There is no live handoff or hidden immediate restart.
- **D-13:** Automatic rollback is not required. Recovery from a failed update is a documented manual reinstall of a known plugin release.

### Configuration and migration
- **D-14:** Reuse the existing `~/.config/herdr/keypad-binding.json` exact-device binding in place. The Rust bridge validates and reads the frozen format without rewriting or silently migrating it, so the paired device remains authoritative across the cutover.
- **D-15:** An ordinary plugin installation requires zero configuration. Use Herdr-provided runtime information, the existing exact-device binding, the installed Codex command, and platform-native defaults.
- **D-16:** Advanced overrides live only in validated files under `HERDR_PLUGIN_CONFIG_DIR`, validate at startup, and apply only after explicit restart. No live callback, environment-variable authority, external standalone config path, or CLI settings authority is allowed.
- **D-17:** Malformed or incompatible binding/settings state fails closed and remains unchanged on disk. The bridge stays alive, exposes a bounded diagnostic, never connects to a different device or guesses values, and requires an explicit repair or re-pair action.

### Diagnostics surface
- **D-18:** A read-only Herdr plugin `status` action is the primary operational diagnostic surface. It queries bounded same-user local control IPC and reports stopped/unreachable if no bridge answers. This accepted action replaces unavailable first-class status publication. Device `HEALTH` remains bounded on-device truth.
- **D-19:** Default status shows current device-link, Herdr, and Codex states; active bridge version and bounded effective-configuration identity; reconnect/backoff state; one last bounded error; and a small bounded list of recent state transitions/error codes. It does not expose verbose protocol or request traces.
- **D-20:** Operational logging is disabled by default. When enabled in validated plugin config, bounded structured redacted tracing goes to standard error for Herdr command-log capture. The bridge owns no files, rotation, journald, unified-log integration, streaming ingestion, or default-on trace stream.
- **D-21:** Status is read-only. Explicit plugin start, stop, restart, repair, and re-pair operations remain separate and auditable; observing status cannot mutate bridge, pairing, source, focus, or HID authority.
- **D-22:** Existing privacy limits remain absolute across status and logs: no credentials, account identity, prompts, transcripts, raw upstream errors, host filesystem paths, or developer evidence payloads. Only bounded operational codes, short safe identities, versions, state transitions, and timings needed to operate the bridge may appear.

### the agent's Discretion
- Select the maintained Rust crates, async runtime, serialization strategy, serial/device discovery APIs, locking/IPC mechanism, and platform adapter boundaries after mandatory migration and platform research.
- Define capped backoff, transition-history bounds, status/config identity encoding, optional stderr event schema, and restart handshake while preserving D-01 through D-22.
- Choose reproducible build, signing/notarization, and plugin-bundle mechanics for the two selected release targets. Do not expand the architecture matrix or distribution channels.
- Implement against verified Herdr v0.8.2 one-shot startup, explicit action, environment-directory, and command-log behavior. Do not wait for unavailable supervision, stop/logout hooks, status publication, log ingestion, or live settings APIs, and do not add an OS service or daemon.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within the Phase 4 Rust migration, lifecycle, packaging, configuration, and diagnostics boundary.
</user_constraints>

# Phase 04: Production Rust Host Bridge — Research

**Researched:** 2026-08-29
**Domain:** Rust native host integration, Herdr plugin lifecycle, USB serial/device boundaries, closed v2 protocol parity, and cross-platform packaging
**Confidence:** HIGH for the current Herdr v0.8.2 capability boundary and Python parity contract; MEDIUM overall until macOS adapter and release mechanics are exercised.

## Project Constraints (from AGENTS.md)

- The product is an agent-inbox companion for the exact LILYGO T-Keyboard S3 Pro; direct key selection is the primary workflow, and the encoder is secondary. `[VERIFIED: AGENTS.md:10-15]`
- The installed Herdr inbox remains source of truth; the bridge must preserve its ordering and semantics rather than implement a competing priority model. `[VERIFIED: AGENTS.md:16-21]`
- Credentials remain host-side, and offline, unavailable, and stale states must remain visibly truthful. `[VERIFIED: AGENTS.md:22-27]`
- Short press is focus-only; hold is the single fixed Space exception after exact focus acknowledgement; arbitrary actions and macros are out of scope. `[VERIFIED: AGENTS.md:28-33]`
- USB remains the selected wired transport and Phase 5 physical acceptance is out of scope for this phase. `[VERIFIED: AGENTS.md:34-38]`
- Project changes normally enter through the repository workflow entrypoint, but this artifact is being produced as the requested GSD phase research deliverable. `[VERIFIED: AGENTS.md:40-49]`
- Do not weaken exact-target focus, generation/session fencing, or the firmware-owned HID authority while changing the host implementation. `[VERIFIED: AGENTS.md:50-68]`

## Summary

The Python bridge is a useful behavioral oracle with separable projection, Herdr, Codex, USB, focus, protocol, and lifecycle seams. The Rust port should preserve observable boundaries, not Python object structure. Complete authoritative reads establish inbox order after invalidation; source and device sessions are independently fenced; only exact generation-bound focus acknowledgement authorizes the result; Codex null/unavailable/stale states remain distinct; and the device owns asserted HID Space. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:32-56,219-273,560-688,859-1095; host/herdr_keypad/src/herdr_keypad/projection.py:232-386; host/herdr_keypad/src/herdr_keypad/focus.py:75-140; host/herdr_keypad/src/herdr_keypad/codex.py:183-674]`

A portable, event-driven Tokio core with explicit ports for Herdr, Codex, USB, time, lifecycle, configuration, status, and optional stderr tracing is the recommended shape. Tokio provides async tasks, channels, timers, Unix sockets, subprocesses, and signals; `tokio-serial` provides async serial streams; Serde provides typed models; and the existing closed JSON schema remains the wire authority. `[CITED: https://tokio.rs/tokio/tutorial; https://docs.rs/tokio/latest/tokio/process/struct.Command.html; https://docs.rs/tokio-serial/latest/tokio_serial/; https://serde.rs/]`

Herdr v0.8.2 is the latest stable release, published 2026-08-19. Its immutable release notes, exact tagged source, and generated API schema show one-shot startup/action commands and invocation logs but no supervised child, crash restart, stop/logout hook, first-class status publication, structured log ingestion, or live settings callback. Those absences are now supported constraints, not blockers. Phase 04 launches the executable from the one-shot startup hook, ties its lifetime to the Herdr socket/process boundary, uses explicit idempotent lifecycle and read-only status actions over same-user local IPC, reads restart-applied config only under `HERDR_PLUGIN_CONFIG_DIR`, keeps stderr tracing off by default, and activates updates on restart or the next Herdr start. `[CITED: https://github.com/herdrdev/herdr/releases/tag/v0.8.2; https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/runtime.rs#L100-L143; https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/mod.rs#L113-L136; https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/mod.rs#L613-L640; VERIFIED: installed Herdr 0.8.2 generated schema lines 5712-5830]`

**Primary recommendation:** Freeze the Python contract and protocol fixtures first, then build one Rust binary around bounded event-driven state machines and the verified Herdr v0.8.2 launch/control/config/log contract. Do not add supervision or lifecycle facilities outside Herdr.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Herdr inbox reads, invalidations, ordering, and sole `agent.focus` write | API / Backend (bridge core) | Herdr socket adapter | The bridge normalizes public Herdr responses and owns freshness/fencing; the adapter only transports requests/events. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/herdr.py:26-319; host/herdr_keypad/src/herdr_keypad/projection.py:337-386]` |
| Codex app-server supervision and limit normalization | API / Backend (bridge core) | Codex process adapter | Credentials and authenticated access stay on the host; the core classifies full/sparse/unavailable/stale data independently. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/codex.py:19-30,104-139,183-303,325-674]` |
| Exact paired USB discovery, CDC I/O, v2 framing, and session fencing | API / Backend (bridge core) | Linux/macOS device adapters | Core owns admission, sequence, ACK, and generation authority; adapters differ only in discovery and native serial I/O. `[VERIFIED: tools/phase1_bringup/src/phase1_bringup/discovery.py:7-11,45-52,99-139; host/herdr_keypad/src/herdr_keypad/usb.py:33-70,81-113,124-169]` |
| Device-owned HID Space | Device / Firmware | Bridge CDC result path | The bridge never emits Space-up or assumes keyboard authority; firmware owns the asserted HID state. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:25; .planning/PROJECT.md:54-58]` |
| Lifecycle, single instance, and control actions | Frontend Server / plugin process | Herdr one-shot startup and action commands | Startup launches the long-lived bridge; the bridge monitors Herdr and exits with it. Explicit same-user IPC-backed actions provide idempotent start/restart/stop without claiming Herdr supervision or automatic disable/unlink stop. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:16-24; CITED: https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/runtime.rs#L100-L143]` |
| Status and optional redacted operational tracing | Frontend Server / plugin process | Herdr action and command logs | The read-only status action queries local IPC. Tracing is disabled by default and, when enabled, emits bounded redacted stderr captured in command logs. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:39-44; installed Herdr 0.8.2 generated schema lines 5712-5830]` |
| Native packaging, signing, and artifact verification | CDN / Static | Herdr plugin installer | The plugin bundle selects one target binary; macOS signing/notarization is a release concern, not runtime bridge logic. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:27-31; CITED: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution]` |

## Standard Stack

### Core

| Library | Version | Purpose | Why standard |
|---|---:|---|---|
| `tokio` | 1.53.1 | Event-driven runtime, bounded channels, timers, Unix sockets, subprocesses, signals | Maintained Rust async runtime with the primitives needed by every bridge boundary. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://tokio.rs/tokio/tutorial; https://docs.rs/tokio/latest/tokio/net/struct.UnixListener.html]` |
| `serde` | 1.0.229 | Typed domain and wire serialization | Derive-based typed models keep protocol fields compiler-checked and make closed contracts explicit. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://serde.rs/]` |
| `serde_json` | 1.0.151 | Bounded JSONL/socket/protocol encoding | Use typed models and a custom bounded deserialization layer for the closed v2 schema. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://docs.rs/serde_json/latest/serde_json/]` |
| `tokio-serial` | 5.5.0 | Async serial stream over the selected CDC port | Keeps serial reads/writes inside Tokio's event loop instead of blocking the core. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://docs.rs/tokio-serial/latest/tokio_serial/]` |
| `serialport` | 4.10.0 | Cross-platform candidate enumeration and serial configuration | Use only in the platform discovery seam; application hello remains the authorization boundary. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://docs.rs/serialport/latest/serialport/]` |

### Supporting

| Library | Version | Purpose | When to use |
|---|---:|---|---|
| `tracing` | 0.1.44 | Structured event/span instrumentation | Emit normalized operational events, never raw upstream payloads. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://docs.rs/tracing/latest/tracing/]` |
| `tracing-subscriber` | 0.3.23 | Bounded stderr event formatting | Enable only through validated plugin config; default logging remains off and output stays redacted. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://docs.rs/tracing/latest/tracing/]` |
| `toml` | 1.1.4+spec-1.1.0 | Parse validated settings under `HERDR_PLUGIN_CONFIG_DIR` | Read only at startup; reject malformed settings and require explicit restart to apply changes. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://docs.rs/toml/latest/toml/]` |
| `sha2` | 0.11.0 | Internal effective-config and artifact identity digest | Hash canonical typed settings; expose only a short safe prefix in status. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://docs.rs/sha2/latest/sha2/]` |
| `fs2` | 0.4.3 | Cross-platform exclusive lock for one bridge authority | Hold the lock for process lifetime and combine it with a bounded local control socket; a stale PID/socket is never authority. `[VERIFIED: crates.io registry/package-legitimacy 2026-08-29; CITED: https://docs.rs/fs2/latest/fs2/]` |

The Rust package versions above were checked against the crates registry on 2026-08-29. The legitimacy gate returned `OK` for every listed crate; published dates, weekly downloads, and source repositories were also returned for all ten packages. `[VERIFIED: package-legitimacy check --ecosystem crates 2026-08-29]`

**Recommended feature posture:** disable serial crate default features if the selected release build confirms that this avoids a runtime `libudev` dependency, then implement Linux descriptor matching in the adapter and verify the result in CI. This is a recommendation, not yet a verified Cargo build result. `[RECOMMENDATION; CITED: https://docs.rs/serialport/latest/serialport/; https://docs.rs/tokio-serial/latest/tokio_serial/]`

**Installation:**

```toml
[dependencies]
tokio = { version = "1.53.1", features = ["rt", "macros", "net", "io-util", "process", "signal", "sync", "time"] }
serde = { version = "1.0.229", features = ["derive"] }
serde_json = "1.0.151"
serialport = { version = "4.10.0", default-features = false }
tokio-serial = { version = "5.5.0", default-features = false }
tracing = "0.1.44"
tracing-subscriber = { version = "0.3.23", features = ["fmt", "json"] }
toml = "1.1.4"
sha2 = "0.11.0"
fs2 = "0.4.3"
```

Every package in this example is listed in the verified standard-stack table. The final executor must resolve any feature incompatibility in a targeted Cargo compile rather than adding unverified crates. `[VERIFIED: package-legitimacy check 2026-08-29; RECOMMENDATION]`

### Alternatives considered

| Instead of | Could use | Tradeoff |
|---|---|---|
| Tokio event loop | A synchronous thread-per-boundary design | Easier local code but risks idle polling, lifecycle races, and duplicated cancellation/fencing logic; not recommended for D-02/D-08 resource behavior. `[RECOMMENDATION; CITED: https://tokio.rs/tokio/tutorial]` |
| `tokio-serial` | Blocking `serialport` in a dedicated thread | Could work as an adapter fallback, but adds thread lifecycle and wakeup overhead; use only if a target-specific async-open issue is demonstrated. `[RECOMMENDATION; CITED: https://docs.rs/serialport/latest/serialport/; https://docs.rs/tokio-serial/latest/tokio_serial/]` |
| Exclusive lock plus local control IPC | PID file alone | PID files cannot prove ownership after crash or PID reuse; retain the lock as authority and use same-user IPC only for bounded actions/status. `[RECOMMENDATION; CITED: https://docs.rs/fs2/latest/fs2/; https://docs.rs/tokio/latest/tokio/net/struct/UnixListener.html]` |
| Existing binding JSON | New Rust pairing database | Violates D-14 and creates split authority; read and validate the frozen file without rewriting it. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:33-37; host/herdr_keypad/src/herdr_keypad/usb.py:41-63]` |
| Default-off stderr tracing | File rotation, journald, unified log, or default-on output | Matches D-20 and Herdr v0.8.2 command-log behavior without creating another retention contract. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:39-44; installed Herdr 0.8.2 generated schema lines 5712-5830]` |

## Package Legitimacy Audit

| Package | Registry | Age / publish date | Weekly downloads | Source repo | Verdict | Disposition |
|---|---|---|---:|---|---|---|
| `tokio` | crates.io | 2016-07-01 | 16,642,501 | github.com/tokio-rs/tokio | OK | Approved |
| `serde` | crates.io | 2014-12-05 | 22,245,611 | github.com/serde-rs/serde | OK | Approved |
| `serde_json` | crates.io | 2015-08-07 | 22,593,070 | github.com/serde-rs/json | OK | Approved |
| `serialport` | crates.io | 2016-12-23 | 260,406 | github.com/serialport/serialport-rs | OK | Approved |
| `tokio-serial` | crates.io | 2017-02-02 | 125,117 | github.com/berkowski/tokio-serial | OK | Approved |
| `tracing` | crates.io | 2017-11-27 | 14,066,008 | github.com/tokio-rs/tracing | OK | Approved |
| `tracing-subscriber` | crates.io | 2019-06-27 | 10,671,972 | github.com/tokio-rs/tracing | OK | Approved |
| `toml` | crates.io | 2014-11-11 | 15,753,991 | github.com/toml-rs/toml | OK | Approved |
| `sha2` | crates.io | 2016-05-06 | 18,246,563 | github.com/RustCrypto/hashes | OK | Approved |
| `fs2` | crates.io | 2015-09-02 | 1,251,965 | github.com/danburkert/fs2-rs | OK | Approved |

All rows are `[VERIFIED: package-legitimacy check --ecosystem crates 2026-08-29]`; versions are `[VERIFIED: cargo search 2026-08-29]`; the official docs links are in the Standard Stack table. No package was flagged `SUS` or `SLOP`; none was removed.

## Architecture Patterns

### System architecture diagram

```text
Herdr one-shot startup/action boundary ─┐
Herdr public socket + process monitor ─┼─> bounded event ingress ──┐
Codex app-server child JSONL ──────────┤                           │
USB discovery + async CDC frames ──────┘                           v
                                       portable Rust core/state machine
       timers: reconnect / freshness / Codex poll / shutdown ──>  │
       config + binding + lock/control IPC ─────────────────────>  │
       generation/session fences ───────────────────────────────>  │
                                                                   v
                 complete projection + device snapshot + status
                    │                         │                 │
                    v                         v                 v
              v2 snapshot/focus       read-only action   optional redacted stderr
                    │
                    v
             exact device CDC/firmware (HID ownership remains device-side)
```

The data flow preserves independent source/device/Codex health: an event invalidates a projection, a complete read establishes authoritative slots, a USB session ACK establishes readiness, and only matching generation/session/identity permits focus results. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:560-688,777-857,859-1095; host/herdr_keypad/src/herdr_keypad/projection.py:337-386; host/herdr_keypad/src/herdr_keypad/usb.py:124-231]`

### Recommended project structure

```text
host/herdr_keypad/
├── native/
│   ├── Cargo.toml          # one production binary and locked dependencies
│   ├── Cargo.lock          # committed release resolution
│   ├── rust-toolchain.toml # pinned compiler/channel used by CI
│   ├── src/
│   │   ├── main.rs         # thin command/lifecycle entrypoint
│   │   ├── core/            # portable state machines and domain models
│   │   ├── protocol/        # closed v2 parser/encoder and golden vectors
│   │   ├── ports/            # Herdr, Codex, USB, clock, config, status, logs
│   │   └── platform/         # linux.rs and macos.rs only
│   └── tests/               # black-box contract/resource tests
├── protocol/schema/v2.json  # existing canonical schema, not copied/extended
├── tests/                   # Python oracle and current behavioral corpus
├── herdr-plugin.toml        # direct bundled binary startup and action manifest
└── bundle/                  # target-specific native artifacts, not Python runtime
```

This is a planning boundary, not a claim about files that already exist: the repository currently contains Python host sources and no Rust production crate. The existing Python modules remain useful as a test oracle during migration; Python must disappear from the supported plugin runtime and bundle. `[VERIFIED: host/herdr_keypad/src/herdr_keypad; host/herdr_keypad/pyproject.toml:1-24; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:69-77]`

### Pattern 1: Event-driven boundary coordinator

**What:** Use one coordinator task with bounded messages from each adapter. Coalesce Herdr invalidations into a dirty flag, run one complete authoritative read, and use `tokio::select!` over adapter events, control requests, cancellation, and explicit timers. `[RECOMMENDATION; CITED: https://tokio.rs/tokio/tutorial/select; https://tokio.rs/tokio/tutorial/channels]`

**When to use:** Always for the long-lived bridge. The Python loop currently has a fixed `time.sleep(0.1)` path; the Rust coordinator must not recreate that periodic wakeup. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:1038-1095]`

```rust
loop {
    tokio::select! {
        Some(event) = herdr_events.recv() => core.on_herdr_event(event).await?,
        Some(frame) = usb_frames.recv() => core.on_usb_frame(frame).await?,
        Some(update) = codex_updates.recv() => core.on_codex_update(update).await?,
        Some(command) = control.recv() => core.on_control(command).await?,
        _ = reconnect_deadline => core.reconnect_due().await?,
        _ = shutdown.cancelled() => break,
    }
}
```

The exact event names above are illustrative, not protocol additions; the only device wire message types remain `agent_snapshot`, `snapshot_ack`, `focus_intent`, and `focus_result`. `[CITED: https://tokio.rs/tokio/tutorial/select; VERIFIED: protocol/schema/v2.json:1-23]`

### Pattern 2: Boundary state machines and generation fencing

**What:** Give Herdr, USB, and Codex independent states and sessions. On disconnect/explicit restart/suspend, invalidate that boundary, retain only truthful stale/offline presentation, reject old results, and require a complete fresh snapshot plus matching device ACK before actionability. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:560-688,859-1095; host/herdr_keypad/src/herdr_keypad/usb.py:81-113; host/herdr_keypad/src/herdr_keypad/focus.py:75-140]`

**When to use:** Every source/device reconnect, explicit bridge restart, host suspend/resume, and updated binary activation. Settings and plugin updates apply through that explicit restart or a later Herdr start. No deferred focus request may cross a generation boundary; the existing USB pending-focus capacity is 16 and remains a hard bound. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/usb.py:50-63; host/herdr_keypad/src/herdr_keypad/bridge.py:945-1000]`

### Pattern 3: Black-box differential parity

**What:** Freeze input traces and expected observable outputs from the Python implementation, then execute the same traces against Rust through an external boundary. Compare wire frames, projection order/revisions, health/error classifications, focus acceptance/rejection, reconnect transitions, and diagnostic redaction. Do not share Python object internals with Rust tests. `[RECOMMENDATION; VERIFIED: host/herdr_keypad/tests/test_integration.py:1-1114; host/herdr_keypad/tests/test_protocol.py; host/herdr_keypad/tests/test_projection.py; host/herdr_keypad/tests/test_focus.py; host/herdr_keypad/tests/test_codex.py]`

**When to use:** Before changing the plugin manifest or deleting the Python launcher. Keep the Python oracle test-only; the release smoke test must run with Python absent from `PATH`. `[RECOMMENDATION; VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:69-77]`

### Pattern 4: Lock-authoritative control IPC

**What:** Acquire one exclusive lock under Herdr's plugin state directory. The winner owns bounded same-user local control IPC. A duplicate start sends a versioned request with the effective configuration identity. Matching configuration returns active/idempotent. Changed configuration returns restart-required; only an explicit restart fences and replaces the active authority. `[RECOMMENDATION; CITED: https://docs.rs/fs2/latest/fs2/; https://docs.rs/tokio/latest/tokio/net/struct.UnixListener.html]`

**When to use:** Start, status, stop, restart, repair, and re-pair actions. Configuration files are read only at process startup, not pushed over IPC for live update. Never use a PID file or socket existence as proof of ownership. `[RECOMMENDATION; VERIFIED: host/herdr_keypad/scripts/ensure-bridge.sh:1-106]`

### Pattern 5: Strict bounded protocol admission

**What:** Check byte length before allocation, reject unknown fields and duplicate keys, enforce the existing nesting/identifier/digest limits, and validate envelope sequence/session correlation before dispatch. Use Serde for typed parsing but a custom visitor or preflight layer where default map behavior does not preserve the Python oracle's duplicate-key policy. `[VERIFIED: protocol/schema/v2.json:25-136; tools/phase1_bringup/src/phase1_bringup/protocol.py:11-16,56-81,114-120,453-623; CITED: https://serde.rs/deserialize-struct.html]`

**When to use:** Every device frame, Herdr socket response/event, Codex child line, and local control request. Device v2 is capped at 4096 bytes; Herdr push/response handling is capped at 65,536 bytes; keep these bounds distinct rather than raising the wire limit globally. `[VERIFIED: protocol/schema/v2.json:25-26; host/herdr_keypad/src/herdr_keypad/herdr.py:26-319]`

### Recommended resource bounds

| Resource | Bound | Policy |
|---|---:|---|
| Device v2 frame | 4096 bytes | Reject before allocation; preserve the canonical schema bound. `[VERIFIED: protocol/schema/v2.json:25-26]` |
| Herdr response/push frame | 65,536 bytes | Reject/close malformed or oversized stream input; preserve the existing client limit. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/herdr.py:26-319]` |
| Pending focus requests | 16 | Never queue beyond this; clear on USB/session invalidation. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/usb.py:50-63; host/herdr_keypad/src/herdr_keypad/bridge.py:945-1000]` |
| Concurrent focus jobs | 16 | Use a bounded semaphore/channel; old-generation results are discarded. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:945-1000]` |
| Codex line/window parsing | 4096-byte lines, 8 buckets | Preserve the Python collector's parser/bucket bounds; use a separate child-stream cap from device frames. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/codex.py:19-30]` |
| Transition/error history | 32 records | Recommended fixed ring of safe codes/timestamps only; never retain raw upstream text. `[RECOMMENDATION; VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:39-44]` |
| Status/control payload | 16 KiB each | Recommended hard cap for read-only status and local control replies; reject larger requests before deserialization. `[RECOMMENDATION; VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:39-44]` |

Backoff should be deterministic and capped for tests (for example, 0.5, 1, 2, 4, 8 seconds with bounded jitter, never exceeding 8 seconds); the exact schedule is delegated by the discretion area in the locked context and must be recorded in parity/resource evidence. `[RECOMMENDATION; VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:32-56,560-688; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:46-50]`

### Anti-patterns to avoid

- **Fixed polling loop:** Recreates the Python `sleep(0.1)` wakeup, burns idle resources, and can race event invalidation. Use event notifications and only explicit reconnect/freshness/Codex deadlines. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:1038-1095; RECOMMENDATION]`
- **Descriptor-only authorization:** VID/PID/path or first-match order cannot authorize the paired device; filter measured descriptors, then require exact application hello identity and protocol. `[VERIFIED: tools/phase1_bringup/src/phase1_bringup/discovery.py:45-52,99-139; host/herdr_keypad/tests/test_integration.py:686-707]`
- **Cross-boundary replay:** Never queue focus across a disconnect, old source revision, generation, or session. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:219-273,945-1000; host/herdr_keypad/src/herdr_keypad/focus.py:75-140]`
- **Second configuration/logging authority:** Do not add environment overrides, config outside `HERDR_PLUGIN_CONFIG_DIR`, rotating files, journald, or macOS unified-log requirements. Validated config is startup-only, and optional redacted stderr tracing is off by default. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:33-44]`
- **Hidden supervisor:** The one-shot startup hook may launch the long-running executable, but neither it nor a shell wrapper may become a watchdog. The bridge monitors Herdr and exits with it; crash recovery remains an explicit action or the next Herdr start. `[CITED: https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/runtime.rs#L100-L143]`
- **Raw diagnostics:** Do not serialize upstream errors, credentials, prompts, transcripts, paths, account IDs, or developer evidence into status/log output. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:39-44; host/herdr_keypad/src/herdr_keypad/codex.py:325-674]`

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| Async scheduling/cancellation | Sleep-based scheduler or custom reactor | Tokio runtime, `select!`, channels, timers | Existing boundaries need cancellation and event-driven wakeups. `[CITED: https://tokio.rs/tokio/tutorial/select]` |
| Typed JSON model handling | String slicing or an entire JSON parser | Serde/serde_json plus a small bounded admission/custom visitor layer | Retains compiler-checked models while preserving closed-schema and duplicate-key rules. `[CITED: https://serde.rs/; VERIFIED: tools/phase1_bringup/src/phase1_bringup/protocol.py:56-81]` |
| Async serial transport | Manual nonblocking fd reactor | `tokio-serial` backed by `serialport` | Cross-platform serial setup and async stream behavior already exist. `[CITED: https://docs.rs/tokio-serial/latest/tokio_serial/; https://docs.rs/serialport/latest/serialport/]` |
| Cryptographic digest | Custom hash or FNV for security | `sha2` for config/artifact identity; retain FNV only where v2 compatibility requires it | FNV in the v2 schema is a compatibility digest, not an authentication primitive. `[VERIFIED: protocol/schema/v2.json:25-26; CITED: https://docs.rs/sha2/latest/sha2/]` |
| Cross-process ownership | PID file and stale-socket heuristics | `fs2` lock plus Tokio Unix socket and same-user peer checks | A held lock proves ownership; control IPC carries bounded intent. `[CITED: https://docs.rs/fs2/latest/fs2/; https://docs.rs/tokio/latest/tokio/net/struct.UnixStream.html]` |
| Operational logging | Rotating file logger and platform-specific adapters | Default-off `tracing` subscriber writing bounded redacted stderr | Matches Herdr v0.8.2 command-log capture and D-20 without another retention system. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:39-44; installed Herdr 0.8.2 generated schema lines 5712-5830]` |
| Inbox priority | A new priority/ranking algorithm | Existing projection rank/order and complete-read semantics | Herdr inbox is authoritative and has tested ordering. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/projection.py:232-335; .planning/PROJECT.md:42-43]` |

**Key insight:** The hard parts are authority transitions and privacy-preserving state, not JSON or serial syntax. Reuse maintained primitives and keep policy in the portable core; otherwise a superficially working port can reconnect, focus, or publish stale data incorrectly.

## Frozen Python Contract to Port

| Boundary | Observable contract to preserve | Source |
|---|---|---|
| Device protocol | Closed four-type v2 protocol: `agent_snapshot`, `snapshot_ack`, `focus_intent`, `focus_result`; identifier length 1–64; frame/payload bounds and FNV1a64 canonical digest; rejection codes are fixed. | `[VERIFIED: protocol/schema/v2.json:1-136]` |
| Slots and revision | `MAX_SLOTS = 3`, `V2 = 2`, `BRIDGE_VERSION = "0.1.0"`; empty slots and source revisions are normalized before publication. | `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:32-56; host/herdr_keypad/src/herdr_keypad/projection.py:10-17]` |
| Agent ordering | Rank states are literal `blocked`, `finished`, `working`, `idle`, `unknown`, `settled`; sorting is rank then descending state-change sequence; output is truncated to three and filled with empty entries. | `[VERIFIED: host/herdr_keypad/src/herdr_keypad/projection.py:10-17,232-335]` |
| Herdr | Bootstrap `session.snapshot`, `agent.list`, and `workspace.list`; subscribe to typed events; events invalidate and complete reads restore authority; sole write remains `agent.focus`. | `[VERIFIED: host/herdr_keypad/src/herdr_keypad/herdr.py:26-319; host/herdr_keypad/src/herdr_keypad/projection.py:337-386]` |
| Focus | Validate current source revision/epoch/slot/entry/pane; re-read `agent.list`; allow at most two focus attempts; accept only an exact focused identity/result. | `[VERIFIED: host/herdr_keypad/src/herdr_keypad/focus.py:75-140]` |
| USB | Exact measured VID/PID/serial/CDC interface gate, then application hello checks `device_id`, firmware, and protocol; fresh session/sequence authority after each reconnect; bounded pending focus (16). | `[VERIFIED: tools/phase1_bringup/src/phase1_bringup/discovery.py:7-11,45-52,99-139; host/herdr_keypad/src/herdr_keypad/usb.py:50-113]` |
| Codex | Spawn exact child command `codex app-server --stdio`; initialize once; use full `account/rateLimits/read` baseline, sparse updates only after a baseline, account changes clear cache, null is not zero, and auth/process failure classes remain distinct. | `[VERIFIED: host/herdr_keypad/src/herdr_keypad/codex.py:19-30,183-303,325-674]` |
| Lifecycle | Source/device/Codex recovery is independent; complete snapshot plus device ACK precedes actionability; disconnect retains stale/offline presentation and fences actions. | `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:560-688,859-1095]` |
| Developer separation | Current `--inspect`, smoke/evidence, live-sync, UI-bound, and environment-driven development paths are not production commands; production must expose only the resolved lifecycle/control surface. | `[VERIFIED: host/herdr_keypad/src/herdr_keypad/__main__.py:27-338]` |

### Exact USB compatibility

The current source of truth measures `EXPECTED_VID = 0x303A`, `EXPECTED_PID = 0x1001`, `EXPECTED_SERIAL = "8C:BF:EA:0D:CB:FC"`, and `EXPECTED_CDC_INTERFACE = "01"`; the descriptor candidate must still pass application hello identity and protocol checks. `[VERIFIED: tools/phase1_bringup/src/phase1_bringup/discovery.py:7-11,45-52,121-139]` The composite test rejects a lookalike serial and the wrong `if00` interface, selecting only the expected `if01` candidate. `[VERIFIED: host/herdr_keypad/tests/test_integration.py:686-707]`

The existing binding model is exactly `{schema_version: 1, device_id: <opaque>, protocol: 1, firmware: <non-empty string>}`; `PairingBinding.from_dict` rejects a missing/wrong schema, invalid identity, non-1 protocol, or empty firmware, and the store atomically replaces the file. `[VERIFIED: tools/phase1_bringup/src/phase1_bringup/pairing.py:28-85]`

### Recommended black-box parity matrix

- Protocol golden vectors: accepted/rejected v2 frames, canonical digest, unknown fields, duplicate keys, nesting and 4096-byte boundary. `[VERIFIED: host/herdr_keypad/tests/test_protocol.py; protocol/schema/v2.json:25-136]`
- Projection traces: empty/partial/full inbox, rank ties, state-change ordering, source invalidation, material revision changes, stale/offline veil, and bounded title/discriminator normalization. `[VERIFIED: host/herdr_keypad/tests/test_projection.py; host/herdr_keypad/src/herdr_keypad/projection.py:83-335]`
- Focus traces: exact current target, source/device generation mismatch, pane/identity churn, retry after unfocused acknowledgement, vanished/timeout/empty response. `[VERIFIED: host/herdr_keypad/tests/test_focus.py; host/herdr_keypad/src/herdr_keypad/focus.py:75-140]`
- Codex traces: zero versus null, full baseline, sparse merge/refetch, duration mapping, reset selection, stale/freshness, auth/process failure, redaction, child exit, account change. `[VERIFIED: host/herdr_keypad/tests/test_codex.py; host/herdr_keypad/src/herdr_keypad/codex.py:183-674]`
- Integration traces: independent Herdr/USB/Codex outage, bounded backoff, event-stream rebuild, reconnect snapshot ACK, exact descriptor/udev admission, single authority, idempotent start/restart/status/stop, Herdr-process exit, restart-applied configuration, and production/developer command separation. `[VERIFIED: host/herdr_keypad/tests/test_integration.py:188-1114; RECOMMENDATION]`
- Resource traces: idle event-driven process, bounded queues/history/diagnostic payloads, reconnect timers, Codex polling only at its explicit deadline, and no source polling wakeups while the event stream is healthy. `[RECOMMENDATION; VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:1038-1095; host/herdr_keypad/src/herdr_keypad/codex.py:19-30]`

## Runtime State Inventory

| Category | Items found | Action required |
|---|---|---|
| Stored data | The existing `~/.config/herdr/keypad-binding.json` exists with the frozen binding shape and values `schema_version: 1`, `protocol: 1`, and firmware `phase1-bringup`; the opaque device identity is intentionally not reproduced here. `[VERIFIED: local runtime inspection 2026-08-29; tools/phase1_bringup/src/phase1_bringup/pairing.py:28-47]` | Code edit only: Rust reads/validates it in place and never rewrites or migrates it. No data migration is authorized by D-14. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:33-37]` |
| Live service config | Herdr 0.8.2 is running; no installed `herdr-keypad` plugin or keypad-specific Herdr config/state directory was found in the local inspection. `[VERIFIED: local Herdr CLI/config inspection 2026-08-29]` | Install/link creates plugin-owned config/state directories. Advanced settings live only under `HERDR_PLUGIN_CONFIG_DIR`, validate at startup, and apply after explicit restart. Do not mutate private inbox state or add another config authority. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:33-37; CITED: https://herdr.dev/docs/plugins/]` |
| OS-registered state | No running bridge process was found. Stale lock files were found under the XDG cache/runtime locations used by the old shell launcher. `[VERIFIED: local process/path inspection 2026-08-29; host/herdr_keypad/scripts/ensure-bridge.sh:1-106]` | Do not migrate stale PID/lock artifacts. The new binary cleans stale control IPC only after acquiring its authority lock. Remove old launcher assumptions and add no OS service or shell daemon. `[RECOMMENDATION; VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:16-24]` |
| Secrets and environment variables | Codex credentials are host-owned; Herdr supplies socket, binary, plugin root, config, state, and context paths. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/codex.py:325-674; CITED: https://herdr.dev/docs/plugins/]` | No secret migration. Keep runtime information from Herdr, but accept advanced settings only from validated files under `HERDR_PLUGIN_CONFIG_DIR`. Do not preserve developer environment variables as settings. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/__main__.py:27-338; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:33-37]` |
| Build artifacts / installed packages | Python `__pycache__`, a Python virtual environment, and developer evidence artifacts exist in the repository workspace; the local Herdr installation has no keypad plugin. `[VERIFIED: local workspace/Herdr inspection 2026-08-29]` | Do not ship these as production dependencies. Python remains test-oracle-only during parity work, then the release bundle contains only the target Rust executable, manifest, and required static metadata. `[RECOMMENDATION; VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:27-31,69-77]` |

**Canonical migration conclusion:** the existing binding file remains the only carried user data. Herdr owns startup/action invocation, config/state paths, and command logs. The Rust process owns its bounded runtime lock/control IPC and exits with Herdr. The old Linux shell/Python lifecycle artifacts do not remain supported authorities. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:16-44; host/herdr_keypad/scripts/ensure-bridge.sh:1-106]`

## Common Pitfalls

### Pitfall 1: Inventing supervision around one-shot startup

**What goes wrong:** Herdr v0.8.2 waits for a spawned command but provides no crash restart, stop hook, or supervisor. A shell watchdog or detached daemon would create an undeclared lifecycle authority. `[CITED: https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/runtime.rs#L100-L143]`

**Why it happens:** The current manifest has startup and event shell commands, so command placement can be mistaken for supervision. `[VERIFIED: host/herdr_keypad/herdr-plugin.toml:1-80]`

**How to avoid:** Launch the executable directly from the startup hook, monitor the Herdr socket/process boundary, and exit on Herdr shutdown. Expose explicit idempotent start/restart/stop actions. A crash remains stopped until one of those actions or the next Herdr start. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:16-24]`

### Pitfall 2: Requiring APIs Herdr v0.8.2 does not have

**What goes wrong:** First-class status publication, streaming log ingestion, live settings callbacks, and disable/unlink stop do not exist in the latest stable release. Treating them as requirements blocks a compatible implementation or encourages hidden substitutes. `[CITED: https://github.com/herdrdev/herdr/releases/tag/v0.8.2; https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/mod.rs#L113-L136; https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/mod.rs#L613-L640; VERIFIED: installed Herdr 0.8.2 generated schema lines 5712-5830]`

**How to avoid:** Use a read-only status action over same-user local IPC. Read validated config under `HERDR_PLUGIN_CONFIG_DIR` only at startup. Keep tracing off by default and send bounded redacted events to stderr only when enabled. Require explicit stop before disable/unlink. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:20-24,33-44]`

### Pitfall 3: Reintroducing polling under a new name

**What goes wrong:** The Python fallback sleeps 0.1 seconds and probes event health; a direct Rust translation would waste idle wakeups and obscure source invalidation semantics. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:777-857,1038-1095]`

**How to avoid:** Event stream is primary; source events set dirty/invalidate state, complete reads determine order, and timers exist only for bounded reconnect/freshness/Codex deadlines. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/herdr.py:124-319; RECOMMENDATION]`

### Pitfall 4: Sparse Codex data becoming a false baseline

**What goes wrong:** A sparse update without a known full baseline can turn absent windows into zero or current data; account changes can leave another account's cached limits visible. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/codex.py:183-303,325-674; host/herdr_keypad/tests/test_codex.py]`

**How to avoid:** Require a full baseline, preserve presence-aware nullability, refetch when required, clear on account identity change, and distinguish process/auth/offline/stale classifications. Do not log raw provider responses. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/codex.py:325-674]`

### Pitfall 5: Descriptor matching that authorizes the wrong device

**What goes wrong:** A lookalike serial, wrong composite interface, or first enumerated path can reach application hello if descriptor checks are incomplete. `[VERIFIED: host/herdr_keypad/tests/test_integration.py:686-707; tools/phase1_bringup/src/phase1_bringup/discovery.py:99-139]`

**How to avoid:** Preserve the measured VID/PID/serial/CDC interface gate, then exact hello identity/firmware/protocol, and fail closed on zero or ambiguous candidates. Keep Linux and macOS discovery differences behind adapters. `[VERIFIED: tools/phase1_bringup/src/phase1_bringup/discovery.py:45-52,121-139; RECOMMENDATION]`

### Pitfall 6: Stale control socket or PID treated as live authority

**What goes wrong:** A crashed bridge leaves a socket/PID artifact; a subsequent process either refuses to start forever or starts a second authority. `[VERIFIED: host/herdr_keypad/scripts/ensure-bridge.sh:1-106]`

**How to avoid:** Acquire the exclusive lock first, remove stale socket only while owning the lock, then bind a bounded UDS and validate same-user peer credentials. `[RECOMMENDATION; CITED: https://docs.rs/fs2/latest/fs2/; https://docs.rs/tokio/latest/tokio/net/struct.UnixListener.html]`

### Pitfall 7: macOS release signed from Linux

**What goes wrong:** This workstation has Linux x86-64 tooling and no Apple signing/notarization tools or Apple Silicon target; a Linux cross-build cannot perform native Developer ID signing/notarization. `[VERIFIED: local toolchain inspection 2026-08-29]`

**How to avoid:** Build, sign, notarize, and staple/package on a macOS Apple Silicon runner. Compare unsigned release hashes for reproducibility, then separately verify signature/notarization because signing timestamps can alter bytes. `[CITED: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution; RECOMMENDATION]`

### Pitfall 8: Privacy regression through “helpful” diagnostics

**What goes wrong:** Process/Herdr/Codex errors often contain paths, account identifiers, prompts, or response bodies; forwarding them violates D-22. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/codex.py:325-674; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:39-44]`

**How to avoid:** Map failures to a fixed code vocabulary, keep one bounded safe detail where explicitly allowed, expose only short safe identities/version/timing, and test redaction at the black-box boundary. `[RECOMMENDATION; VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:690-775; host/herdr_keypad/tests/test_codex.py]`

## Platform and Release Mechanics

### Linux x86-64

Use a native `x86_64-unknown-linux-gnu` or explicitly selected static-compatible target only after Herdr runtime compatibility is verified; pin the target/toolchain and build with `cargo build --release --locked`. The local machine has Rust/Cargo 1.82 and the GNU x86-64 target, but no macOS target. `[VERIFIED: local rustc/cargo/target inspection 2026-08-29; CITED: https://doc.rust-lang.org/cargo/commands/cargo-build.html]`

The plugin must not require Python, a virtual environment, `PYTHONPATH`, source checkout paths, shell `flock`, Linux `/proc`, or a package-manager-installed bridge dependency. OS-provided libc/device facilities are distinct from a separately installed language runtime; verify dynamic dependencies and serial feature selection in release CI. `[VERIFIED: host/herdr_keypad/scripts/ensure-bridge.sh:1-106; host/herdr_keypad/pyproject.toml:1-24; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:27-31; RECOMMENDATION]`

### macOS Apple Silicon

D-11 requires `aarch64-apple-darwin`. Native build/sign/notarization must run on macOS Apple Silicon because this Linux workstation lacks `xcrun`, `codesign`, `pkgbuild`, `notarytool`, and the Apple target. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:27-31; local toolchain inspection 2026-08-29]`

For distribution outside the App Store, Apple requires Developer ID signing, hardened runtime, secure timestamps, and notarization using `notarytool`; the release pipeline should package the plugin directory as a versioned archive/installer after signing its executable and retain notarization evidence. `[CITED: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution]`

Serial discovery should remain an adapter concern. Use the maintained cross-platform serial enumeration where it provides the required descriptor facts, and use native Linux sysfs/udev or macOS IOKit metadata only for the missing interface/location fields; always complete application hello validation. This exact native metadata strategy was not fully validated on macOS in this Linux session and is an implementation checkpoint. `[RECOMMENDATION; CITED: https://docs.rs/serialport/latest/serialport/; https://developer.apple.com/documentation/iokit; ASSUMED]`

For permissions, Apple's `com.apple.security.device.serial` entitlement is documented for sandboxed applications. A Herdr-launched helper should not acquire or advertise that entitlement unless the signed plugin is actually sandboxed; the macOS release smoke test must prove that the selected `/dev/cu.*` device can be opened under the real Herdr launch context and must fail closed with a safe code otherwise. `[CITED: https://developer.apple.com/documentation/bundleresources/entitlements/com_apple_security_device_serial; RECOMMENDATION]`

### Reproducible release evidence

Commit `Cargo.lock` and pin the Rust toolchain. Build each target in a clean environment with `--locked`, record target/compiler/source revision, and compare SHA-256 of unsigned binaries across two clean runs. Then sign/package/notarize in a separate step and record signed artifact hashes and Apple ticket status. `[RECOMMENDATION; CITED: https://doc.rust-lang.org/cargo/commands/cargo-build.html; https://doc.rust-lang.org/cargo/guide/cargo-toml-vs-cargo-lock.html; https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution]`

Do not claim byte-for-byte reproducibility for timestamped signatures without evidence. The acceptance evidence should show reproducible unsigned binaries plus valid per-target signatures/notarization and a manifest-selected bundle. `[RECOMMENDATION; CITED: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution]`

## Environment Availability

| Dependency | Required by | Available | Version / evidence | Fallback |
|---|---|---|---|---|
| Rust/Cargo | Native build and tests | Yes | rustc/cargo 1.82, Linux x86-64 | — `[VERIFIED: local toolchain inspection 2026-08-29]` |
| Linux target | Local release smoke | Yes | `x86_64-unknown-linux-gnu` installed | — `[VERIFIED: local toolchain inspection 2026-08-29]` |
| Python oracle | Differential parity only | Yes | Python 3.14.7; existing venv/source | Keep test-only; never bundle for production `[VERIFIED: local runtime inspection; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:69-77]` |
| Herdr | Plugin launch/control/config/log integration | Yes | Latest stable and installed v0.8.2, released 2026-08-19 | Implement verified one-shot startup, explicit actions, config directory, and command-log semantics; no upstream capability is required `[CITED: https://github.com/herdrdev/herdr/releases/tag/v0.8.2; VERIFIED: installed Herdr 0.8.2 generated schema lines 5712-5830]` |
| Codex CLI | Host-side usage collector | Yes | 0.151.0; no running Codex process during inspection | Report unavailable until installed/authenticated process is available; do not fake current data `[VERIFIED: local runtime inspection; host/herdr_keypad/src/herdr_keypad/codex.py:325-674]` |
| Exact USB serial | Phase 4 adapter smoke only | Yes on this host | Expected ESP32-S3 serial CDC is present | Physical acceptance remains Phase 5; keep device checks black-box `[VERIFIED: local device inspection; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:6-10]` |
| macOS Apple Silicon runner | Native build/sign/notarize | No | No Apple target/signing tools on Linux | Required CI/worker; no honest local fallback for D-11 distribution `[VERIFIED: local toolchain inspection 2026-08-29]` |
| Apple notarization credentials | Distribution release | Not checked / unavailable locally | Requires Apple Developer account credentials | Human/CI secret provisioning; never commit or log credentials `[CITED: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution; RECOMMENDATION]` |

**Missing dependencies with no local fallback:** a macOS Apple Silicon build/sign/notarization worker and Apple credentials for the D-11 release artifact. Herdr v0.8.2 is available and its verified capability boundary supports the approved Phase 04 lifecycle; it is not a blocker. `[VERIFIED: local toolchain and Herdr inspection 2026-08-29; CITED: https://github.com/herdrdev/herdr/releases/tag/v0.8.2]`

## Security Domain

Security enforcement is enabled at ASVS level 1 in project configuration. `[VERIFIED: .planning/config.json:96-125]`

### Applicable ASVS categories

| ASVS category | Applies | Standard control |
|---|---|---|
| V2 Authentication | Yes, local process boundary | No network login; require same-user local control peer and exact paired device/application hello. `[RECOMMENDATION; VERIFIED: tools/phase1_bringup/src/phase1_bringup/discovery.py:121-139; CITED: https://docs.rs/tokio/latest/tokio/net/struct.UnixStream.html]` |
| V3 Session management | Yes | Fresh USB boot/session/sequence authority after reconnect; control requests carry version/config identity and cannot cross an authority epoch. `[VERIFIED: tools/phase1_bringup/src/phase1_bringup/protocol.py:518-623; host/herdr_keypad/src/herdr_keypad/usb.py:81-113]` |
| V4 Access control | Yes | Runtime state/control directory mode 0700, binding mode 0600, same-user UDS peer checks, read-only status separated from mutating lifecycle/repair/re-pair operations. `[RECOMMENDATION; VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:33-44; local binding inspection 2026-08-29]` |
| V5 Input validation | Yes | Strict closed schemas, byte/nesting/identifier bounds, duplicate rejection, exact protocol/session correlation, safe settings parser, no shell interpolation. `[VERIFIED: protocol/schema/v2.json:25-136; tools/phase1_bringup/src/phase1_bringup/protocol.py:11-16,56-81; CITED: https://herdr.dev/docs/plugins/]` |
| V6 Cryptography | Limited but real | Use SHA-256 for internal config/artifact identity; do not treat compatibility FNV1a64 as authentication; do not add credentials to device payloads. `[VERIFIED: protocol/schema/v2.json:25-26; .planning/PROJECT.md:56-58; CITED: https://docs.rs/sha2/latest/sha2/]` |

### Known threat patterns

| Pattern | STRIDE | Standard mitigation |
|---|---|---|
| Lookalike serial/composite device | Spoofing | Exact measured descriptor plus exact hello identity/firmware/protocol; fail closed on zero/ambiguous candidates. `[VERIFIED: tools/phase1_bringup/src/phase1_bringup/discovery.py:45-52,121-139]` |
| Stale socket/PID or duplicate start | Spoofing / Tampering | Exclusive lock authority, bounded UDS, same-user peer credential check, idempotent config identity. `[RECOMMENDATION; CITED: https://docs.rs/fs2/latest/fs2/; https://docs.rs/tokio/latest/tokio/net/struct.UnixStream.html]` |
| Malicious/malformed local frame | Tampering / DoS | Size/nesting/unknown/duplicate validation before allocation and bounded queues. `[VERIFIED: protocol/schema/v2.json:25-136; tools/phase1_bringup/src/phase1_bringup/protocol.py:56-81,518-623]` |
| Old result after reconnect/reconfigure | Tampering / Elevation | Session, generation, source revision, and exact immutable identity fences; never replay deferred focus/HID authority. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/focus.py:75-140; host/herdr_keypad/src/herdr_keypad/bridge.py:945-1000]` |
| Credentials/account/prompts in logs | Information disclosure | Fixed operational codes, redaction before status/log serialization, no raw upstream errors or payloads. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:39-44; host/herdr_keypad/src/herdr_keypad/codex.py:325-674]` |
| PATH/subprocess substitution | Elevation | Resolve Herdr-provided absolute binary paths, direct argv (no shell), verify Codex command identity, and retain child process boundary. `[CITED: https://herdr.dev/docs/plugins/; VERIFIED: host/herdr_keypad/src/herdr_keypad/codex.py:325-360]` |

## Verified Herdr v0.8.2 Capability Contract

The latest stable Herdr release is v0.8.2, published 2026-08-19. Immutable release metadata, exact tagged source, and the installed generated schema establish:

1. Herdr can install/link a plugin, inject `HERDR_SOCKET_PATH`, `HERDR_BIN_PATH`, `HERDR_PLUGIN_ROOT`, `HERDR_PLUGIN_CONFIG_DIR`, `HERDR_PLUGIN_STATE_DIR`, and context, then run direct-argv startup and action commands. `[CITED: https://herdr.dev/docs/plugins/; https://github.com/herdrdev/herdr/releases/tag/v0.8.2]`
2. Plugin commands spawn and wait to completion. There is no supervisor, crash restart/backoff, timeout/cancel/kill lifecycle, or hidden stop/logout hook. `[CITED: https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/runtime.rs#L100-L143]`
3. Disable persists registry state and clears an agent view; unlink removes registry records while explicitly leaving panes running. Neither operation stops a launched bridge. `[CITED: https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/mod.rs#L113-L136; https://github.com/herdrdev/herdr/blob/v0.8.2/src/app/api/plugins/mod.rs#L613-L640]`
4. The schema exposes plugin link/list/unlink/enable/disable, action list/invoke, and invocation-log list. It has no first-class status publication, log-ingestion stream, or live plugin configuration method. `[VERIFIED: installed Herdr 0.8.2 generated schema lines 5712-5830]`

**Planning contract:** Build against those facts. Use startup launch plus Herdr process/socket monitoring, explicit IPC-backed lifecycle/status actions, explicit stop before disable/removal, startup-only configuration under `HERDR_PLUGIN_CONFIG_DIR`, default-off stderr tracing captured by invocation logs, and update activation on explicit restart or next Herdr start. No Herdr capability checkpoint or upstream change blocks Phase 04. `[VERIFIED: .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:16-50]`

## State of the Art

| Old approach | Current approach | When changed | Impact |
|---|---|---|---|
| Python source-checkout launcher, venv/PYTHONPATH, Linux shell `flock`/`/proc` | Bundled native Rust executable and platform adapters | Phase 04 decision, 2026-08-29 | Removes runtime/package-manager dependency from production and makes Linux/macOS bundle selection explicit. `[VERIFIED: host/herdr_keypad/scripts/ensure-bridge.sh:1-106; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:27-31]` |
| Fixed 0.1-second fallback polling | Event-driven stream plus explicit bounded timers | Phase 04 decision, 2026-08-29 | Reduces idle wakeups while retaining reconnect/freshness deadlines. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/bridge.py:1038-1095; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:46-50]` |
| PID/shell lifecycle assumptions | Lock-authoritative local control IPC plus verified Herdr v0.8.2 startup/process boundary | Phase 04 relaxation, 2026-08-30 | Supports one authority, idempotent actions, explicit recovery, and clean Herdr-bound exit without inventing supervision. `[VERIFIED: host/herdr_keypad/scripts/ensure-bridge.sh:1-106; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:16-24]` |
| Linux-only plugin startup | Target-selected Linux x86-64/macOS Apple Silicon bundle | Phase 04 decision, 2026-08-29 | Requires native macOS build/sign/notarization pipeline. `[VERIFIED: host/herdr_keypad/herdr-plugin.toml:1-80; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:27-31]` |

**Deprecated/outdated for the production path:** Python launcher, shell `ensure-bridge.sh`, developer evidence/smoke commands, source-checkout imports, environment-variable configuration authorities, and any OS service workaround. They may remain as migration/test fixtures only where needed to prove parity. `[VERIFIED: host/herdr_keypad/src/herdr_keypad/__main__.py:27-338; host/herdr_keypad/scripts/ensure-bridge.sh:1-106; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:69-77]`

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | Same-user local control IPC and process-boundary monitoring can be implemented on both Linux x86-64 and macOS Apple Silicon without another runtime authority. | Verified Herdr v0.8.2 Capability Contract | Medium: platform-specific peer/process APIs differ; prove start/status/stop/restart and Herdr-exit behavior on each target. `[ASSUMED]` |
| A2 | A maintained native Linux/macOS adapter can expose the exact composite CDC interface metadata required by the frozen descriptor gate. | Platform and Release Mechanics | High: macOS exact-device admission could remain unresolved; prove with target-native adapter tests before packaging. `[ASSUMED]` |
| A3 | Herdr's plugin-owned state directory is the approved location for lock/socket/runtime state on both release targets. | Runtime State Inventory / control IPC | Medium: incorrect path would violate D-15 or create a second config authority; confirm in the resolved Herdr contract. `[ASSUMED]` |
| A4 | The chosen Linux target's libc/device-library policy is acceptable to Herdr's supported Linux x86-64 installations. | Linux x86-64 | Medium: a binary could require an unavailable runtime library; verify release dependency inspection on the support baseline. `[ASSUMED]` |
| A5 | Apple Developer ID credentials and a macOS Apple Silicon CI worker will be provisioned for release. | Environment Availability | High: macOS artifact/signing acceptance cannot complete locally. `[ASSUMED]` |

## Open Questions

The Herdr lifecycle, status, logging, settings, disable/unlink, crash recovery, and update activation questions are resolved by the verified v0.8.2 contract above. They are not planning blockers.

1. **Which native metadata path proves the exact CDC interface on macOS Apple Silicon?** `[ASSUMED]`
   - What we know: the Python oracle requires interface `01` and exact application identity; `serialport` is cross-platform but adapter metadata coverage needs target testing. `[VERIFIED: tools/phase1_bringup/src/phase1_bringup/discovery.py:7-11,45-52; CITED: https://docs.rs/serialport/latest/serialport/]`
   - What's unclear: target-native property names and permissions for the exact composite descriptor.
   - Recommendation: implement and test a macOS adapter on the required runner before deleting Python production discovery. `[RECOMMENDATION]`

2. **Which Linux binary target and baseline satisfy Herdr's x86-64 support without package-manager dependencies?** `[ASSUMED]`
   - What we know: local GNU x86-64 Rust is available; D-10 forbids separately installed bridge packages. `[VERIFIED: local toolchain inspection; .planning/phases/04-production-rust-host-bridge/04-CONTEXT.md:27-31]`
   - What's unclear: supported libc baseline and whether static linking is compatible with the host/plugin environment.
   - Recommendation: choose after dependency inspection and a clean plugin install smoke test on the target baseline. `[RECOMMENDATION]`

## Sources

### Primary / authoritative

- `.planning/phases/04-production-rust-host-bridge/04-CONTEXT.md` — locked D-01 through D-22 and the approved Herdr v0.8.2 lifecycle relaxation. `[VERIFIED: local source]`
- `.planning/PROJECT.md` — product authority, privacy, focus/HID boundary, and v1 exclusions. `[VERIFIED: local source]`
- `protocol/schema/v2.json` — closed device wire contract and bounds. `[VERIFIED: local source]`
- `host/herdr_keypad/src/herdr_keypad/bridge.py`, `projection.py`, `herdr.py`, `codex.py`, `focus.py`, `usb.py` — Python behavioral oracle. `[VERIFIED: local source]`
- `tools/phase1_bringup/src/phase1_bringup/discovery.py`, `pairing.py`, `protocol.py` — measured descriptor, frozen binding, framing/session behavior. `[VERIFIED: local source]`
- `host/herdr_keypad/tests/test_integration.py`, `test_protocol.py`, `test_projection.py`, `test_focus.py`, `test_codex.py` — parity corpus. `[VERIFIED: local source]`
- Herdr authoritative evidence: https://github.com/herdrdev/herdr/releases/tag/v0.8.2; tagged `src/app/api/plugins/runtime.rs` lines 100-143; tagged `src/app/api/plugins/mod.rs` lines 113-136 and 613-640; installed v0.8.2 generated schema lines 5712-5830; plus https://herdr.dev/docs/plugins/, https://herdr.dev/docs/socket-api/, and https://herdr.dev/docs/cli-reference/. These establish latest-stable release status, command lifetime, disable/unlink behavior, exposed APIs, environment paths, actions, and invocation logs. `[CITED; VERIFIED]`
- Tokio documentation: https://tokio.rs/tokio/tutorial, https://docs.rs/tokio/latest/tokio/process/struct.Command.html, https://docs.rs/tokio/latest/tokio/net/struct.UnixListener.html — runtime, process, and local socket primitives. `[CITED]`
- Serde documentation: https://serde.rs/, https://serde.rs/deserialize-struct.html — typed serialization/deserialization patterns. `[CITED]`
- Rust serial documentation: https://docs.rs/serialport/latest/serialport/, https://docs.rs/tokio-serial/latest/tokio_serial/ — enumeration and async stream APIs. `[CITED]`
- Apple documentation: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution — Developer ID, hardened runtime, secure timestamp, notarytool, and distribution workflow. `[CITED]`

### Registry and package audit

- `cargo search` for all ten recommended crates, run 2026-08-29. `[VERIFIED: crates.io registry]`
- `gsd-tools query package-legitimacy check --ecosystem crates tokio serde serde_json serialport tokio-serial tracing tracing-subscriber toml sha2 fs2 directories`, run 2026-08-29; all returned `OK`. `[VERIFIED: package-legitimacy gate]`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for Tokio/Serde/serial crates and registry legitimacy; MEDIUM for exact feature flags until a Rust crate exists and compiles. `[VERIFIED: docs/registry sources cited above]`
- Architecture: HIGH for the Python parity/protocol contract and Herdr v0.8.2 launch/control/config/log boundary; MEDIUM for target-specific process monitoring and local IPC until both release targets run it. `[VERIFIED: local oracle, tagged Herdr source, installed schema, and cited release evidence]`
- Pitfalls: HIGH for session/protocol/privacy/reconnect pitfalls from focused tests; MEDIUM for native macOS descriptor details pending target-runner evidence. `[VERIFIED: local tests and cited platform docs]`

**Research date:** 2026-08-29
**Valid until:** 2026-09-05 for Herdr/Codex/Rust package APIs; 2026-09-28 for stable protocol and migration findings.
