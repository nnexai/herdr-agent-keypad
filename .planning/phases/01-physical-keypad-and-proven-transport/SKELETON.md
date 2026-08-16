# Walking Skeleton — Herdr Agent Keypad

**Phase:** 1
**Generated:** 2026-08-16

## Capability Proven End-to-End

A user can start one host-guided run, see one bounded stimulus on the delivered keypad, press its matching physical key, explicitly confirm the observation, and complete a versioned acknowledged USB round trip whose evidence is preserved.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Firmware framework | PlatformIO with pioarduino 55.03.311, Arduino-ESP32 3.3.11, and an immutable official T-Keyboard-S3-Pro 0.1.0 source | This is the researched official Pro hardware path and keeps USB personality and library resolution reproducible. |
| Host framework | Reproducible Python 3.11 virtual environment at `tools/phase1_bringup/.venv`, exact `tools/phase1_bringup/.venv/bin/python -m phase1_bringup` invocation, native terminal I/O, standard-library data handling, and pinned pyserial 3.5 | A temporary guided utility needs deterministic keyboard input and evidence capture, not a permanent web/TUI framework; the plan-owned environment prevents ambient import resolution. |
| Data layer | Immutable, schema-versioned JSON manifest/results plus SHA-256 finalization under `artifacts/phase1/<run-id>/` | Phase 1 stores measured evidence rather than application records; atomic files preserve failures and provenance without introducing a database. |
| Identity/authentication | Physically confirmed opaque `device_id`; descriptor data is discovery-only; only an evidence-eligible Wi-Fi branch accepts bounded no-echo station credentials and device-scoped mutual-TLS identity over a fresh confirmed USB session | This ties every secret mutation to the intended unit; encrypted staged generations, update/clear, rollback, AP-auth handling, and zero-secret outputs close the full fallback credential lifecycle. |
| Protocol verification | Frozen `protocol/schema/v1.json` and `protocol/fixtures/v1-golden.json`, matching consolidated `protocol.{h,cpp}`/host codec, and an explicit PlatformIO `native` Unity target in `test/protocol/test_main.cpp` | The native harness loads the exact repository fixture and compiles production firmware code, making cross-language parity runnable before hardware qualification. |
| Transport boundary | One bounded NDJSON v1 session protocol above exactly one compile-time selected `Link` adapter at `firmware/src/main.cpp` | Branch-specific PlatformIO source filters include one implementation and exclude the other; no dormant alternate, hybrid arbitration, failover, or runtime selector can ship. |
| Selection evidence | Frozen manifest with the complete common interruption matrix, resolver-emitted concrete immutable candidate/selection/build/result locks, and SHA-256 cross-references through the final binary | `latest` is resolved once and never consumed directly; the selection lock names exactly `selected-usb` or `selected-wifi`, and ARCHIVED requires a new strict physical result bound to final build and manifest hashes. |
| Deployment target | The delivered T-Keyboard S3 Pro flashed and used over the same physical connection, plus the exact local `tools/phase1_bringup/.venv/bin/python -m phase1_bringup start` host run | Phase 1 acceptance is real-device local operation; no remote deployment can substitute for physical mapping and transport measurements. |
| Directory layout | `firmware/src/{board,ui,protocol,transport,metrics,security}`, `protocol/{schema,fixtures}`, `test/protocol`, isolated `tools/phase1_bringup`, measured `host/udev`, and runtime `artifacts/phase1` | The final layout matches `01-PATTERNS.md`, including deliberate header-only renderer and consolidated protocol/session module. |

## Stack Touched in Phase 1

- [ ] Project scaffold — reproducible firmware environment, Python host package, narrow verification commands
- [ ] Routing — one real `hello → hello_ack → probe → probe_ack/event` protocol route through the selected byte stream
- [ ] Data read/write — one real atomic evidence manifest/result write and subsequent schema/hash verification read
- [ ] UI interaction — one real panel stimulus plus matching physical key and explicit host confirmation
- [ ] Deployment — firmware running on the delivered unit and the local host command exercising the complete path

## Phase 1 Vertical Plan Set

1. `01-01` proves the production tracer, plan-owned Python environment, and real atomic evidence write/reopen verification.
2. `01-02` expands the firmware into the complete bounded physical stimulus/rendering surface.
3. `01-03` makes that surface user-observable through the exact guided UI and immutable human-confirmed map.
4. `01-04` binds evidence to one physical opaque identity and proves unprivileged D-12 recovery.
5. `01-05` freezes protocol semantics and runs the explicit native production-code golden-fixture harness.
6. `01-06` freezes every researched interruption row, runs USB qualification, preserves immutable linkage, and locks its concrete result through the validated pointer resolver.
7. `01-07` is the single security-gated vertical: only the runnable locked remediated-USB result permits complete station/TLS provisioning and Wi-Fi-only qualification against the identical matrix.
8. `01-08` resolves and hash-selects one passing result, builds exactly `selected-usb` or `selected-wifi`, proves the unselected source/object/symbol absent, physically qualifies that exact final binary, and archives only after its build/manifest-bound strict pass.

## Out of Scope (Deferred to Later Slices)

- Installed Herdr inbox projection, opaque pane focus, and native seen/manual-unread effects (Phase 2)
- Codex capacity collection, freshness rendering, diagnostics menu, and persistent brightness preference (Phase 3)
- Full host reboot, suspend/resume, independent component recovery, complete resynchronization, and real-account end-to-end soak (Phase 4)
- Permanent diagnostic mode, bridge maintenance command, hybrid transport, battery portability, expansion modules, ambient LEDs, arbitrary actions, and broader providers

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without replacing its physical map, exact-device identity, bounded protocol, or single selected transport:

- Phase 2: Project the authoritative installed Herdr inbox and focus the exact rendered pane with one safe physical press.
- Phase 3: Render truthful Codex usage and expose bounded diagnostics and brightness control through the encoder menu.
- Phase 4: Prove independent recovery and the complete real-device workflow after component failures and reconnection.
