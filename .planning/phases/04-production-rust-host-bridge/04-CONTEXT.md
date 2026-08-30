# Phase 04: Production Rust Host Bridge - Context

**Gathered:** 2026-08-29
**Status:** Complete

<domain>
## Phase Boundary

Replace the current Python host bridge with one production Rust executable bundled into the Herdr plugin. Preserve the Python bridge's complete observable contract: authoritative inbox projection, exact generation/session-bound focus, truthful Codex and freshness states, closed v2 device protocol, independent boundary recovery, and the device-owned focus-authorized HID Space workflow. The executable must use an event-driven portable core, isolate Linux and macOS integration behind platform adapters, run without a separately installed language runtime or bridge dependency, and become the sole supported production path. This phase does not add device actions, protocol capabilities, providers, a standalone public server, or Phase 5 physical acceptance. It closes on local automated implementation and bundle-contract proof plus the installed Linux native bridge; hosted GitHub Actions target execution and release publication remain outside Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Launch and lifecycle
- **D-01:** Herdr owns the production bridge session through the bundled plugin's one-shot startup hook. The hook launches the executable directly. The ordinary user does not install or manage an OS service, background shell daemon, separate runtime, or foreground bridge command. This relaxes the earlier assumption that Herdr supervises the child after launch.
- **D-02:** The bridge monitors both the Herdr socket and Herdr process boundary. It may recover from temporary socket/API unavailability while the launching Herdr session remains alive, but it exits when Herdr shuts down. A later Herdr start launches a fresh bridge. This replaces the earlier guarantee that one bridge survives a Herdr exit or restart.
- **D-03:** Herdr launches the bridge after its startup boundary. A temporarily unavailable socket or missing exact paired keypad is not fatal while that Herdr process remains alive: the bridge reports each boundary independently, reconnects with bounded backoff, and requires complete authoritative resynchronization before actions become available.
- **D-04:** Herdr shutdown and an explicit stop action intentionally stop the bridge. Herdr 0.8.2 disable and unlink do not stop an already running process, so the documented disable/removal procedure requires an explicit stop first and makes no automatic-stop claim. User logout is covered only when it terminates Herdr or the bridge process, not by a nonexistent plugin logout hook.
- **D-05:** Explicit start and restart actions use same-user local control IPC and are idempotent. Starting an active bridge with the same effective configuration reports the active instance and succeeds without disturbing live USB, Herdr, or Codex sessions; restart deliberately replaces its authority.
- **D-06:** There is one bridge authority. Settings exist only under `HERDR_PLUGIN_CONFIG_DIR`, validate at startup, and take effect only through an explicit restart or the next Herdr start. A start request with changed settings must report that restart is required rather than reconfigure the active process or start a second bridge. This relaxes live atomic reconfiguration.
- **D-07:** Herdr 0.8.2 does not restart the bridge after a crash in the same Herdr session. Recovery is an explicit idempotent start/restart action or the next Herdr start. No shell watchdog, OS service, second runtime, or hidden retry daemon may restore the removed automatic-restart guarantee.
- **D-08:** If the launching Herdr process remains alive across host suspend/resume, the same bridge invalidates pre-suspend USB and source sessions, reconnects each boundary, and publishes a fresh complete snapshot before restoring actionability. If Herdr exits, D-02 applies and the next Herdr start launches a fresh bridge; no separate supervisor keeps it alive.
- **D-09:** HID Space is owned by firmware after the device asserts it. Bridge stop, crash, reconfiguration, or replacement must not synthesize Space-up or assume keyboard authority. Physical owner release, device removal/reset, or USB suspend ends the HID state through the existing firmware contract.

### Install and upgrades
- **D-10:** Bundle the correct native executable inside the Herdr plugin. Installing the plugin installs the whole production integration; no standalone bridge package, runtime, or package-manager dependency is required.
- **D-11:** Phase 4 release targets are Linux x86-64 and macOS Apple Silicon. Intel macOS and ARM64 Linux artifacts are not required for this phase.
- **D-12:** A plugin update activates its bundled bridge on an explicit restart or the next Herdr start. The old process authority ends before the updated executable establishes fresh USB, Herdr, and Codex sessions and restores current data. There is no live state handoff or hidden immediate lifecycle hook. This relaxes immediate update activation.
- **D-13:** Automatic rollback is not required. Recovery from a failed update is a documented manual reinstall of a known plugin release.

### Configuration and migration
- **D-14:** Reuse the existing `~/.config/herdr/keypad-binding.json` exact-device binding in place. The Rust bridge validates and reads the frozen format without rewriting or silently migrating it, so the paired device remains authoritative across the cutover.
- **D-15:** An ordinary plugin installation requires zero configuration. Use Herdr-provided runtime information, the existing exact-device binding, the installed Codex command, and platform-native defaults.
- **D-16:** Advanced overrides live only in validated files under `HERDR_PLUGIN_CONFIG_DIR`. The bridge validates them at startup, never watches or reloads them live, and applies changes only after explicit restart. Do not create competing environment-variable, standalone external config-file, or CLI configuration authorities. This replaces the unavailable Herdr settings surface and live callback with the directory Herdr 0.8.2 provides.
- **D-17:** Malformed or incompatible binding/settings state fails closed and remains unchanged on disk. The bridge stays alive, exposes a bounded diagnostic, never connects to a different device or guesses values, and requires an explicit repair or re-pair action.

### Diagnostics surface
- **D-18:** A read-only Herdr plugin `status` action is the primary operational diagnostic surface. The action queries the active bridge through bounded same-user local control IPC and reports it as stopped/unreachable when no process answers. Herdr 0.8.2 has no first-class plugin status publication API; this accepted action replaces that earlier guarantee. The device `HEALTH` page remains the bounded on-device truth for link, Herdr, and Codex health.
- **D-19:** Default status shows current device-link, Herdr, and Codex states; active bridge version and bounded effective-configuration identity; reconnect/backoff state; one last bounded error; and a small bounded list of recent state transitions/error codes. It does not expose verbose protocol or request traces.
- **D-20:** Operational logging is disabled by default. When explicitly enabled through validated plugin configuration, the bridge emits bounded, structured, redacted `tracing` events to standard error, which Herdr captures in command invocation logs. The bridge owns no file logger, rotating-log system, journald integration, macOS unified-log integration, streaming ingestion contract, or default-on trace stream. This replaces the unavailable dedicated Herdr plugin logging facility.
- **D-21:** Status is read-only. Explicit plugin start, stop, restart, repair, and re-pair operations remain separate and auditable; observing status cannot mutate bridge, pairing, source, focus, or HID authority.
- **D-22:** Existing privacy limits remain absolute across status and logs: no credentials, account identity, prompts, transcripts, raw upstream errors, host filesystem paths, or developer evidence payloads. Only bounded operational codes, short safe identities, versions, state transitions, and timings needed to operate the bridge may appear.

### Phase completion and future release
- **D-23:** Keep the implemented GitHub release and aggregation workflow as production release machinery, but close Phase 4 without dispatching it. Phase 4 acceptance is the 18 focused Rust tests, 8 collector tests, local aggregation-contract verification, and the built, installed, restarted Linux x86-64 native Herdr bridge. Actual hosted Linux/macOS execution, artifact publication, signing, notarization, and release upload belong to a later, not-yet-planned release phase. No Phase 4 artifact may claim those operations ran.

### the agent's Discretion
- Select the maintained Rust crates, async runtime, serialization strategy, serial/device discovery APIs, locking/IPC mechanism, and platform adapter boundaries after mandatory migration and platform research.
- Define exact capped-backoff schedules, bounded transition-history size, status/config identity encoding, optional stderr event schema, and restart handshake while preserving D-01 through D-23.
- Keep the reproducible build and plugin-bundle mechanics for Linux x86-64 and macOS Apple Silicon per D-23. Hosted target execution, signing, notarization, artifact publication, and release upload are outside Phase 4 acceptance.
- Implement the verified Herdr 0.8.2 contract directly: one-shot startup, process/socket-bound exit, explicit idempotent lifecycle actions, status over same-user local IPC, restart-applied config under `HERDR_PLUGIN_CONFIG_DIR`, optional stderr tracing, and update activation on restart or next Herdr start. Do not wait for unavailable supervision, stop hooks, status publication, log ingestion, or live settings APIs, and do not replace them with an OS service or daemon.

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

No external specification was named during discussion. Research verified Herdr v0.8.2, released 2026-08-19 and marked latest stable, against its immutable release notes, tagged source, and generated schema. Those sources establish the supported lifecycle/config/status/log contract above and confirm the absence of supervision, stop/logout hooks, first-class status publication, structured log ingestion, and live settings APIs. Mandatory implementation research still covers maintained Rust serial and async I/O stacks, macOS USB serial discovery and permissions, Apple Silicon packaging/signing requirements, and reproducible cross-target release mechanics.

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
- Replace `herdr-plugin.toml` startup/event shell invocations and `scripts/ensure-bridge.sh` with a direct bundled-binary startup command plus explicit start/stop/restart/status actions backed by one cross-platform single-instance control seam. The bridge monitors Herdr and exits with it.
- Port `PermanentBridge` orchestration into a platform-independent core with explicit ports for time, Herdr events/requests, Codex app-server supervision, exact USB transport, lifecycle control, status, optional stderr tracing, configuration, and persistence.
- Implement Linux and macOS adapters only for serial discovery/I/O, Herdr endpoint/process monitoring, Herdr plugin runtime/config/state paths, locking/control IPC, signals/suspend, packaging, and permissions.
- Freeze the Python behavior through shared protocol fixtures and a black-box parity matrix before cutover; keep Python runnable only as the test oracle during migration, then remove its launcher and runtime from the supported plugin path.
- Reuse `~/.config/herdr/keypad-binding.json` as the exact pairing authority. Read advanced settings only from `HERDR_PLUGIN_CONFIG_DIR`, validate them at startup, and require explicit restart to apply changes.
- Expose read-only status through a Herdr action backed by same-user local control IPC. Keep operational tracing off by default; when enabled, send bounded redacted events to stderr for Herdr command-log capture.

</code_context>

<specifics>
## Specific Ideas

- Temporary Herdr socket failure while the launching Herdr process remains alive is a recoverable source outage: last agent entries remain visible under an offline veil, actions are fenced, and a full fresh snapshot restores them. Herdr shutdown ends the bridge process.
- Repeated matching plugin starts are idempotent. Changed configuration requires an explicit restart; it never creates competing authorities or triggers live reconfiguration.
- Plugin installation remains one product install: the correct Linux x86-64 or macOS Apple Silicon binary is already inside the plugin. An update activates on restart or the next Herdr start.
- The read-only status action is the first operational view and includes a bounded recent transition history. Device HEALTH remains glanceable source truth. Optional stderr tracing is disabled by default.
- The Linux x86-64 native bridge is the locally exercised production installation. The macOS Apple Silicon adapter and release bundle remain covered by portable tests and the deterministic workflow contract until a later hosted release run.

</specifics>

<deferred>
## Future release work outside Phase 4

Run the retained hosted Linux and macOS GitHub Actions jobs, publish their aggregate evidence and target artifacts, perform any selected signing/notarization, and upload a public release. This is not an incomplete Phase 4 task, and no numbered release phase exists yet.

</deferred>

---

*Phase: 04-Production Rust Host Bridge*
*Context updated: 2026-08-30 after D-23 closed Phase 4 on local Linux deployment and release-contract readiness*
