# Phase 04: Production Rust Host Bridge - Context

**Gathered:** 2026-08-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the current Python host bridge with one production Rust executable bundled into the Herdr plugin. Preserve the Python bridge's complete observable contract: authoritative inbox projection, exact generation/session-bound focus, truthful Codex and freshness states, closed v2 device protocol, independent boundary recovery, and the device-owned focus-authorized HID Space workflow. The executable must use an event-driven portable core, isolate Linux and macOS integration behind platform adapters, run without a separately installed language runtime or bridge dependency, and become the sole supported production path. This phase does not add device actions, protocol capabilities, providers, a standalone public server, or Phase 5 physical acceptance.

</domain>

<decisions>
## Implementation Decisions

### Launch and lifecycle
- **D-01:** Herdr owns the production bridge lifecycle through the bundled plugin. The ordinary user does not install or manage a separate OS service and does not need to launch a foreground bridge command.
- **D-02:** Once Herdr starts it, the bridge remains alive through Herdr server exit, restart, and temporary API unavailability. It marks Herdr unavailable, keeps the last known agent entries under an unmistakable offline veil, disables every agent action, reconnects with bounded backoff, and requires a complete authoritative resynchronization before actions become available again.
- **D-03:** Starting before Herdr is ready or before the exact paired keypad is connected is not fatal. The process remains alive, reports each unavailable boundary independently, and reconnects when that exact source or device appears.
- **D-04:** Plugin disable/removal, an explicit stop command, and user logout intentionally stop the bridge. An ordinary Herdr restart does not.
- **D-05:** A repeated start with the same effective configuration is idempotent: it reports the active instance and succeeds without disturbing live USB, Herdr, or Codex sessions.
- **D-06:** There is only one Herdr instance and one bridge authority. If a later Herdr invocation supplies changed plugin settings, the active bridge reconfigures live: fence current authority first, adopt the new effective configuration atomically, and establish fresh source/device sessions before publishing current state. Never start a second bridge.
- **D-07:** Herdr automatically restarts the bridge after a process crash. Repeated crashes continue retrying with capped backoff and expose one bounded persistent diagnostic; they must not form a hot restart loop or permanently lock the product out.
- **D-08:** The same bridge process recovers after host suspend/resume. It invalidates pre-suspend USB and source sessions, reconnects each boundary, and publishes a fresh complete snapshot before restoring actionability.
- **D-09:** HID Space is owned by firmware after the device asserts it. Bridge stop, crash, reconfiguration, or replacement must not synthesize Space-up or assume keyboard authority. Physical owner release, device removal/reset, or USB suspend ends the HID state through the existing firmware contract.

### Install and upgrades
- **D-10:** Bundle the correct native executable inside the Herdr plugin. Installing the plugin installs the whole production integration; no standalone bridge package, runtime, or package-manager dependency is required.
- **D-11:** Phase 4 release targets are Linux x86-64 and macOS Apple Silicon. Intel macOS and ARM64 Linux artifacts are not required for this phase.
- **D-12:** A plugin update activates its bundled bridge through a controlled immediate restart. The old process authority ends before the new executable establishes fresh USB, Herdr, and Codex sessions and restores current data. No live state handoff between bridge versions.
- **D-13:** Automatic rollback is not required. Recovery from a failed update is a documented manual reinstall of a known plugin release.

### Configuration and migration
- **D-14:** Reuse the existing `~/.config/herdr/keypad-binding.json` exact-device binding in place. The Rust bridge validates and reads the frozen format without rewriting or silently migrating it, so the paired device remains authoritative across the cutover.
- **D-15:** An ordinary plugin installation requires zero configuration. Use Herdr-provided runtime information, the existing exact-device binding, the installed Codex command, and platform-native defaults.
- **D-16:** Advanced overrides live only in one validated Herdr plugin settings surface. Do not create competing environment-variable, standalone config-file, and CLI configuration authorities.
- **D-17:** Malformed or incompatible binding/settings state fails closed and remains unchanged on disk. The bridge stays alive, exposes a bounded diagnostic, never connects to a different device or guesses values, and requires an explicit repair or re-pair action.

### Diagnostics surface
- **D-18:** Herdr plugin status is the primary operational diagnostic surface. The existing device `HEALTH` page remains the bounded on-device truth for link, Herdr, and Codex health but is not expected to diagnose plugin installation or startup failures.
- **D-19:** Default status shows current device-link, Herdr, and Codex states; active bridge version and bounded effective-configuration identity; reconnect/backoff state; one last bounded error; and a small bounded list of recent state transitions/error codes. It does not expose verbose protocol or request traces.
- **D-20:** The bridge emits structured, redacted operational events to Herdr's plugin logging facility. It does not own a second rotating-file log system or divergent journald/macOS unified-log user contract.
- **D-21:** Status is read-only. Explicit plugin start, stop, restart, repair, and re-pair operations remain separate and auditable; observing status cannot mutate bridge, pairing, source, focus, or HID authority.
- **D-22:** Existing privacy limits remain absolute across status and logs: no credentials, account identity, prompts, transcripts, raw upstream errors, host filesystem paths, or developer evidence payloads. Only bounded operational codes, short safe identities, versions, state transitions, and timings needed to operate the bridge may appear.

### the agent's Discretion
- Select the maintained Rust crates, async runtime, serialization strategy, serial/device discovery APIs, locking/IPC mechanism, and platform adapter boundaries after mandatory migration and platform research.
- Define exact capped-backoff schedules, bounded transition-history size, status/config identity encoding, structured event schema, and reconfiguration handshake while preserving D-01 through D-22.
- Choose reproducible build, signing/notarization, and plugin-bundle mechanics required for the two selected release targets. Do not expand the architecture matrix or distribution channels.
- Decide how Herdr's verified plugin APIs implement automatic restart, read-only status, logging, live reconfiguration, and explicit lifecycle commands. If an assumed Herdr facility does not exist, research must surface the gap before planning rather than silently introducing an OS service.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product scope and fixed migration contract
- `.planning/PROJECT.md` — core direct-focus value, host/device authority boundary, fixed Space-only exception, truthfulness, current compatibility target, and explicit v1 exclusions.
- `.planning/REQUIREMENTS.md` — closed v1 behavior that Rust must preserve, especially FOCS-01 through FOCS-04, HOLD-01 through HOLD-05, SYNC-01 through SYNC-04, SAFE-01/02, CODEX-01 through CODEX-04, and E2E-01 ownership by Phase 5.
- `.planning/ROADMAP.md` §Phase 4 — mandatory Python-contract inventory, Linux/macOS portable-core boundary, event-driven/resource-bounded operation, production/developer separation, packaging, parity evidence, and success criteria.

### Prior locked behavior
- `.planning/phases/03.2-focus-then-hold-usb-keyboard/03.2-CONTEXT.md` — focus-authorized held Space semantics, device-owned HID authority, exact focus correlation, no authority replay, fresh composite USB sessions, and lifecycle safety.
- `.planning/phases/03.1-high-fidelity-animation-and-interaction-polish/03.1-CONTEXT.md` — semantic preemption, immediate feedback, source-fence presentation, and bounded motion/resource behavior the bridge must not regress.
- `.planning/phases/03-truthful-codex-capacity-and-device-menu/03-CONTEXT.md` — Codex normalization, freshness/error classification, independent source health, bounded diagnostics, and direct-key independence.

### Frozen Python parity oracle and current lifecycle
- `host/herdr_keypad/src/herdr_keypad/bridge.py` — current `PermanentBridge` orchestration, v2 snapshot/focus conversion, reconnect and freshness behavior, diagnostics normalization, and development/evidence code that must not enter production.
- `host/herdr_keypad/src/herdr_keypad/projection.py` — installed inbox rank/order authority, bounded normalization, opaque identity, revisions, freshness, and binding construction.
- `host/herdr_keypad/src/herdr_keypad/herdr.py` — current bounded public Herdr socket adapter, event invalidation stream, complete-read behavior, and sole `agent.focus` write.
- `host/herdr_keypad/src/herdr_keypad/codex.py` — installed Codex app-server supervision, full/sparse limit normalization, freshness, authentication/offline classification, and redaction.
- `host/herdr_keypad/src/herdr_keypad/usb.py` — exact paired-device CDC discovery, fresh session/sequence fencing, bounded transport, reconnect, and focus-result transmission.
- `host/herdr_keypad/src/herdr_keypad/__main__.py` — current production and developer commands mixed in one Python entrypoint; migration must preserve production behavior while removing tracer/fixture/evidence modes from the release surface.
- `host/herdr_keypad/herdr-plugin.toml` — current Linux-only Herdr startup/event invocation that Phase 4 replaces with a bundled cross-platform native executable contract.
- `host/herdr_keypad/scripts/ensure-bridge.sh` — current Linux `/proc`, `flock`, PID-file, source-checkout, venv/PYTHONPATH, and acceptance-guard assumptions that must not survive as the production cross-platform lifecycle.

### Protocol and parity verification
- `protocol/schema/v2.json` — canonical closed device protocol and bounded message schemas; Rust must remain firmware-compatible without adding message or action types.
- `host/herdr_keypad/tests/test_integration.py` — current lifecycle, exact USB session, Herdr event, protocol admission, and publication contracts to lift into a black-box parity matrix.
- `host/herdr_keypad/tests/test_protocol.py` — host framing, validation, duplicate, sequence, and bounded-line behavior.
- `host/herdr_keypad/tests/test_projection.py` — inbox normalization, ordering, identity, and freshness behavior.
- `host/herdr_keypad/tests/test_focus.py` — exact target/result correlation and failure vocabulary.
- `host/herdr_keypad/tests/test_codex.py` — Codex full/sparse normalization, nullability, freshness, failure classification, and redaction behavior.

No external specification was named during discussion. Mandatory research must verify the current Herdr plugin lifecycle/status/logging/config APIs, maintained Rust serial and async I/O stacks, macOS USB serial discovery and permissions, Apple Silicon packaging/signing requirements, and reproducible cross-target release mechanics before planning.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The Python modules form a separable behavioral oracle: `projection.py`, `focus.py`, `herdr.py`, `codex.py`, and `usb.py` already divide normalization and boundary concerns even though `PermanentBridge` centralizes orchestration.
- `protocol/schema/v2.json` and the Phase 1 codec/session fixtures provide the canonical language-independent wire contract. Rust should generate or implement against this schema rather than port Python parser quirks.
- The focused Python test suites and native firmware protocol tests provide an existing parity corpus for differential/black-box tests. Preserve observable behavior, not Python object structure.
- The existing exact binding file, USB pairing records, short diagnostic codes, freshness states, and firmware ACK/session fencing are migration inputs that can be frozen and reused without introducing a second authority.

### Established Patterns
- Herdr events invalidate; complete authoritative reads determine ordering and slots. The bridge never reprioritizes entries and `agent.focus` remains the only Herdr write.
- Codex and Herdr health are independent. Missing/null provider data never becomes zero/current, sparse Codex updates cannot establish the initial snapshot, and credentials remain host-only.
- Every USB interruption creates fresh session authority. Bounded frames, sequence/reply correlation, exact pairing, snapshot ACK readiness, and generation-bound focus fail closed; actions are never queued or replayed.
- The device, not the host bridge, owns an asserted HID Space state. The bridge only supplies exact focus results over the existing CDC protocol.
- Current Python production code is entangled with source-checkout paths, Phase 1 Python imports, developer smoke/evidence commands, a venv fallback, Linux `/proc`, shell `flock`, and a Linux-only plugin manifest. These are migration liabilities and explicit clean-cutover targets, not patterns to reproduce in the portable core.

### Integration Points
- Replace `herdr-plugin.toml` startup/event shell invocations and `scripts/ensure-bridge.sh` with direct bundled-binary lifecycle commands backed by one cross-platform single-instance/reconfiguration control seam.
- Port `PermanentBridge` orchestration into a platform-independent core with explicit ports for time, Herdr events/requests, Codex app-server supervision, exact USB transport, lifecycle control, status/log events, configuration, and persistence.
- Implement Linux and macOS adapters only for serial discovery/I/O, Herdr endpoint/process integration, per-user runtime/config paths, locking/control IPC, signals/session logout, packaging, and permissions.
- Freeze the Python behavior through shared protocol fixtures and a black-box parity matrix before cutover; keep Python runnable only as the test oracle during migration, then remove its launcher and runtime from the supported plugin path.
- Reuse `~/.config/herdr/keypad-binding.json` as the exact pairing authority and add live plugin-settings reconfiguration without allowing configuration changes to bypass session and snapshot fences.
- Publish Herdr plugin status and structured redacted logs from normalized core health/state transitions, keeping read-only diagnostics separate from lifecycle and repair commands.

</code_context>

<specifics>
## Specific Ideas

- Herdr server restart should look like a recoverable source outage: last agent entries remain visible under an offline veil, actions are fenced, and a full fresh snapshot restores them without restarting the bridge process.
- Repeated matching plugin starts should feel idempotent. A changed invocation represents the single Herdr instance changing settings and should atomically reconfigure the active bridge rather than create or replace competing authorities.
- Plugin installation should feel like one product install: the correct Linux x86-64 or macOS Apple Silicon binary is already inside the plugin.
- Herdr plugin status should be the first operational view and include a bounded recent transition history, while device HEALTH remains glanceable source truth.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within the Phase 4 Rust migration, lifecycle, packaging, configuration, and diagnostics boundary.

</deferred>

---

*Phase: 04-Production Rust Host Bridge*
*Context gathered: 2026-08-29*
