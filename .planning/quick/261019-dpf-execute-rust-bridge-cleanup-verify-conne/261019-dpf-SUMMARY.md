---
status: complete
quick_id: 261019-dpf
created: 2026-10-19
source_plan: ../261018-x6c-plan-repository-cleanup-separating-rust-/261018-x6c-PLAN.md
---

# Rust bridge cleanup, active plugin update, real-device verification

## Implemented

- Removed the obsolete Python `herdr_keypad` package, exporter and bridge tests, including bytecode inside those retired directories.
- Removed six historical Phase 3 modes and their dead helpers that launched or recreated the Python bridge; preserved independent capture/deployment tools and substantive historical evidence validators.
- Retained the four Python-derived native fixture corpora byte-identically. Removed runtime Python exporter/source-file dependencies and pinned historical lineage plus corpus digests. B0 exporter reproduction passed before removal at parent `c9a9720f64f221225d0364a29f4e6e995066628a`.
- Fixed Rust stop ordering: close USB/Herdr boundaries before releasing authority and sending `Stopped`. Added ordering and real-binary authority-exclusion regressions.
- Added `tools/keypad_lease.py`, using the actual Rust `HERDR_PLUGIN_STATE_DIR/bridge.lock`, bounded child lifetime, inherited fd 9, signal/group cleanup, fresh final authority acquisition and supplementary holder inspection. Routed all retained Python serial opens through one guarded helper.
- Updated tools guide, current requirements, repository capture skill, current-runtime note in AGENTS, and generated-output ignores. Historical phase records and artifacts were not rewritten.

## Deployment

The active plugin is a registered local installation at `/home/nnex/.local/share/herdr/plugins/herdr-keypad`. Rebuilt with `cargo build --locked --release`; stopped through Herdr's public plugin action API, verified previous process exit and lock release, atomically installed the binary plus current manifest/lifecycle document, and started through Herdr again.

- Old executable SHA-256: `7d04558a29cb6bd554bf29cdc4a67dde3b62b038d595e498f3d5921c5be0c749`.
- Installed **and actually loaded** executable SHA-256: `f07cb3cf7206f8d6cd9a136f2fb2d9f6be9a477801f436817842470d43dfe670`.
- Observed final bridge PID: `862691`; owns `/dev/ttyACM0`.
- Rollback copy: `/tmp/herdr-keypad-before-cleanup-4ivdf8i2/`.
- This is a local rebuilt plugin update, not a newly signed/reproducible hosted release. Version remains 0.1.0; content hash proves the update.

## Verification actually run

- Native `cargo test --locked`: **147 passed, 2 ignored**, then optimized release build succeeded. Existing compiler warnings remain; no warning-suppression changes.
- Affected Python diagnostics/evidence tests: **96 passed, 52 subtests passed**. Installed pytest 9.0.2 only in the existing development venv to execute existing pytest-style tests.
- Actual retained self-check succeeded: bootstrap; all **40** Draft 2020-12/codec/session golden vectors; discovery; pairing; bounded serial recovery/D-12 transitions; narrow udev rule. Command includes `--schema protocol/schema/v1.json`.
- Capture, lease, and retained Phase 3 CLI help entrypoints ran successfully.
- Live runner refused entry with exit 75 while the original Rust bridge held authority.
- With the updated bridge stopped, the runner acquired the same actual authority; a concurrent Herdr `start` failed with exit 1 / `AlreadyOwned`, and status remained stopped. Runner then released authority successfully.
- Captured **24 actual USB framebuffers**: four current post-stop panels and four themes × five deterministic scenes (Codex, Copilot, unavailable usage, hold pending, LED menu). Each PPM has the 128×128 header and 49152-byte pixel payload; each `.ppm.rgb565` sidecar is 32768 bytes. Visually inspected the contact sheet.
- Firmware-identity negative capture rejected a temporary altered binding with the expected fresh-hello mismatch and wrote no image. Actual binding unchanged.
- Restored live operation: device ready, Herdr running, Codex ready, no last error. Aggregate status remains stale and Copilot remains unavailable with `cli_version_mismatch`, both already present in baseline.

Evidence and generated images are kept locally, not committed: `artifacts/cleanup-261019/`, including baseline, handoff, identity-fence, final status, verification JSON, captures, and `contact-sheet.png`. Deterministic scene values are firmware fixtures, not live account observations.

## Evidence-driven deviations and repairs

1. Repository `.agents/skills/screen-capture-flow/SKILL.md` is normal project documentation, not a protected global user skill. Updated it in scope, eliminating the planning pass's artificial external-owner gate. No global skills edited.
2. The workstation has same-uid namespace processes with inaccessible `/proc` metadata/fds. Discovery skips unverifiable nonmatching candidates; holder scans explicitly warn about partial visibility. The actual shared authority lock remains mandatory and independently verified; no claim of global absence of arbitrary tty holders is made.
3. Retained self-checks had pre-existing compatibility drift: metrics ACK fixtures lacked current required counters; unsupported-version fixture used now-supported v2; synthetic oversized schema evaluation was misreported; v1 envelope validation lacked identifier/positive-uint32 checks; synthetic reconnect descriptors used pre-composite interface/serial values. Repaired current executable diagnostic fixtures and v1 validation to existing schema/native boundaries. Schemas, firmware, v2 fixtures and the four pinned native corpora remain unchanged.
4. Repaired a stale unit metrics fixture using the existing schema-complete helper. Deleted an incidental release test that asserted workflow source fragments, rather than re-pinning wording. Normal release evidence collection does not invoke that optional standalone source-fragment checker; its old explicit `--check-aggregation-contract` mode remains outside this cleanup.
5. Current Herdr 0.9.5 CLI rejects the documented `--plugin` invocation despite its help text. Used generated-schema public socket `plugin.action.invoke` to dispatch supported lifecycle actions; no private state mutation or alternate launcher.

## Limits

- No firmware source change or upload; unchanged-firmware upload gate not applicable.
- Kernel evdev key-state read was permission denied. No claimed physical keypress/held-key release, LED brightness, optical, or human-focus acceptance. Logical framebuffer and host/USB handoff are proven; physical acceptance is not inferred.
- Direct `current` captures were observed after stopping Rust and retained prior rendered content. No concurrent live capture added to production.
- Pairing, device identity, credentials and installed configuration unchanged. Phase 5 remains unplanned/unaccepted; this is the bounded cleanup and connected-device check, not full Phase 5 qualification.
