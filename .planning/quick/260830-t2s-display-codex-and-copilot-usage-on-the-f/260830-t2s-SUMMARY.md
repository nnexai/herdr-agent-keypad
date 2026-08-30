---
phase: quick
autonomous: false
plan: 260830-t2s
subsystem: firmware-host-protocol
tags: [codex, copilot, usage, keypad, exact-device]

# Dependency graph
requires:
  - phase: 260830-rfd
    provides: normalized CopilotView collector and bounded provider truth states
provides:
  - negotiated optional copilot_usage hello capability and bounded Copilot snapshot member
  - equal-duty availability-aware panel-4 provider selection and four-theme rendering
  - focused exact-device smoke driver with checksummed evidence validation
  - pairing-independent protocol, Rust, and firmware regression proof
affects: [panel-4, usage-tile, usb-bridge, exact-device-qualification]

# Tech tracking
tech-stack:
  added: []
  patterns: [optional negotiated protocol member, equal 8-second provider dwell, stage-before-commit rendering, fail-closed exact-device evidence]

key-files:
  created: []
  modified:
    - host/herdr_keypad/native/src/protocol/v2.rs
    - host/herdr_keypad/native/src/ports/usb.rs
    - host/herdr_keypad/native/src/core/orchestrator.rs
    - host/herdr_keypad/tests/test_protocol.py
    - firmware/src/app/agent_projection.cpp
    - firmware/src/ui/render_state.h
    - firmware/src/ui/theme_common.h
    - firmware/src/ui/theme_signal_edge.cpp
    - firmware/src/ui/theme_ledger.cpp
    - firmware/src/ui/theme_beacon.cpp
    - firmware/src/ui/theme_instrument.cpp
    - firmware/src/protocol/protocol.cpp
    - firmware/src/main.cpp
    - tools/capture_panel.py
    - tools/phase1_bringup/src/phase1_bringup/protocol.py
    - tools/phase1_bringup/src/phase1_bringup/phase3_smoke.py
    - tools/phase1_bringup/test_phase3_smoke.py

key-decisions:
  - "Keep Copilot usage optional and capability-gated so legacy hosts and firmware retain the Codex-only wire shape."
  - "Use an even initial snapshot revision so the deterministic neutral tie-break starts the physical cadence on CODEX, then gives both providers equal 8-second dwell."
  - "Use the installed native herdr-keypad binary for bridge lifecycle ownership because the plan's referenced ensure-bridge.sh is absent; never add a second serial owner."
  - "Do not bypass exact pairing or manufacture optical evidence; once the human observed the exact device, record only those supported Y/N confirmations."

patterns-established:
  - "Provider eligibility is based on displayable retained/current capacity, not object presence; unavailable/auth-only data is ineligible."
  - "Provider changes are one staged complete panel-4 composition and one display flush, with menu/focus/input state outside provider selection."
  - "Exact-device evidence records fresh hello identity, firmware digest, capability, snapshot ACKs, capture hashes, and explicit Y/N sightings in one checksum-protected artifact."

requirements-completed: []

coverage:
  - id: D1
    description: "Capability-gated optional Copilot usage snapshot preserves the legacy Codex-only shape and accepts bounded Copilot truth states."
    verification:
      - kind: unit
        ref: "host.herdr_keypad.tests.test_protocol and host.herdr_keypad.tests.test_integration protocol cases"
        status: pass
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test protocol_parity"
        status: pass
      - kind: integration
        ref: "host/herdr_keypad/tests/export_rust_oracle.py --verify-determinism"
        status: pass
    human_judgment: false
  - id: D2
    description: "Panel 4 selects one eligible provider immediately, alternates equal 8-second dwell when both are eligible, and renders truthful stale/neutral states without changing focus or menu ownership."
    verification:
      - kind: unit
        ref: "platformio test -e native-agent-projection (116 cases)"
        status: pass
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --lib core::orchestrator::tests"
        status: pass
    human_judgment: false
  - id: D3
    description: "The flashed selected-usb binary can be driven through the exact-device usage smoke and produce paired captures plus physical sightings."
    verification:
      - kind: unit
        ref: "tools/phase1_bringup/test_phase3_smoke.py -k quick_usage_tile (5 tests)"
        status: pass
      - kind: e2e
        ref: "quick-usage-tile exact paired keypad run"
        status: pass
    human_judgment: true
    rationale: "Exact hello, all three snapshot ACKs, both checksummed captures, and all four supported human Y confirmations passed."

# Metrics
duration: complete
completed: 2026-08-30
status: complete
---

# Phase quick Plan 260830-t2s: Codex and Copilot usage tile Summary

**Capability-negotiated Copilot usage now drives a symmetric, availability-aware panel-4 selector and truthful four-theme rendering; exact-device captures, live native-plugin Copilot values, and human interaction verification are complete.**

## Accomplishments

- Added the smallest additive protocol extension: `copilot_usage` is advertised by capable firmware, retained per live USB session, and an optional closed Copilot usage object is omitted for legacy peers.
- Added bounded provider projection and firmware rendering for current, stale, auth/unavailable, unlimited, allowed-overage, and hard-limit truth states. Provider selection is symmetric, starts Codex on even revision parity, alternates only when both providers are displayable, and preempts cadence on availability loss.
- Preserved direct keys 1-3, the inert usage-tile key, encoder/menu ownership, focus bindings, LEDs, pairing identity, and existing Codex 5H/WEEK semantics. Native projection regressions cover one-push complete-frame behavior and unchanged input/menu contracts.
- Added the `quick-usage-tile` smoke driver. It validates the fresh exact-pair hello, publishes current then Codex-unavailable/Copilot-stale and neutral dual-unavailable states, waits through the two-provider cadence, captures labelled `codex-current` and `copilot-current` scenes, and writes checksummed evidence with explicit pending or Y/N physical-sighting answers.

## Task Commits

1. **Task 1: Negotiate and publish one optional bounded Copilot usage object** - `d5bb3b4`
2. **Task 2: Select, alternate, and render truthful provider views as complete panel-4 frames** - `64e1adf`
3. **Task 2 correctness fix: keep capture tokens closed** - `9b3c567`
4. **Task 3: Bind logical captures and physical interaction sightings to the exact deployed keypad** - `4e53771`
5. **Exact-device protocol and smoke fixes** - `713bef4`

No plan metadata commit was made: this quick-task contract explicitly forbids committing SUMMARY, PLAN, STATE, ROADMAP, generated captures, or device evidence.

## Focused Verification
- `test_phase3_smoke.py -k quick_usage_tile -v`: **5 passed**.
- `host.herdr_keypad.tests.test_protocol -v`: **8 passed**, including closed v1 probe payload coverage and bounded `billing_mode_unsupported`.
- `platformio test -e native-agent-projection`: **116 passed**.
- `platformio test -e native`: **0 collected, command successful** (the environment has no tests registered).
- `cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test protocol_parity`: **4 passed**.
- `cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test usb_platform`: **22 passed**.
- `cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --lib core::orchestrator::tests`: **21 passed**.
- `export_rust_oracle.py --verify-determinism`: **deterministic**, all three synthetic oracle checks passed.
- Selected-usb firmware was rebuilt and uploaded after the hello-digest and nullable-Copilot parser fixes; flash verification hashes passed.
- Fresh exact-device hello after upload: `/dev/ttyACM0`, VID/PID `0x303a/0x1001`, USB serial `8C:BF:EA:0D:CB:FC`, device ID `0000fccb0deabf8c`, firmware `phase1-bringup`, protocol `1`, capability `copilot_usage`.
- Guarded `quick-usage-tile` finalization with the supported interactive Y/N path: **exit 0**, three snapshot ACKs accepted, both labelled 128x128 captures validated at 32,768 RGB565 bytes, and evidence checksum sidecar regenerated with `status: pass` and all four confirmed sightings set to `Y`.
- Current native plugin release was built with `cargo build --release --locked` (binary SHA-256 `7d04558a29cb6bd554bf29cdc4a67dde3b62b038d595e498f3d5921c5be0c749`), passed `release_bundle` (10 tests), staged via `herdr plugin link`, and activated by managed stop plus explicit Herdr restart. The durable linked root is `/home/nnex/.local/share/herdr/plugins/herdr-keypad`.
- Post-durable-activation read-only status (`plugin-log-90`) is schema version 2 with `state: stale`, `device_state: ready`, `herdr_state: running`, `codex_state: ready`, and `copilot_usage.source_state: current`; live values are `github_copilot`, `used_credits: 1500`, `included_credits: 1500`, `used_percent: 100`, `reached_limit: true`, reset timestamp present, and empty failure reason. Human confirmed the live panel-4 Copilot frame shows these real 1500/1500 values and alternates with Codex.
## Issues Encountered

The plan references `host/herdr_keypad/scripts/ensure-bridge.sh`, but that wrapper is absent from this checkout. The repository's native release path was used instead:

- Built `cargo build --release --locked` from `host/herdr_keypad/native`.
- Verified `cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test release_bundle`: 10 passed.
- Staged `herdr-plugin.toml`, `LIFECYCLE.md`, and the current binary in the durable root `/home/nnex/.local/share/herdr/plugins/herdr-keypad`.
- Activated the staged bundle with `herdr plugin link`, then managed `stop` and explicit `herdr plugin action invoke restart --plugin herdr-keypad`.
- Preserved the validated config/state paths and identity (`config_identity: c8c4a35718a5a4245a6f613b6`).

The prior installed binary was stale (2,769,480 bytes, SHA-256 `745358ca...`, and no `copilot_usage` string). The active linked release is 7,233,800 bytes, SHA-256 `7d04558a29cb6bd554bf29cdc4a67dde3b62b038d595e498f3d5921c5be0c749`, and contains the Copilot capability path. Read-only live status after activation is schema version 2 with `device_state: ready`, `herdr_state: running`, `codex_state: ready`, `copilot_usage.source_state: current`, provider `github_copilot`, live `1500/1500` credits, `used_percent: 100`, and no failure reason.

The initial exact-device attempt surfaced a misleading discovery mismatch. Read-only raw probing showed one compatible candidate exactly matching the stored binding. The actual causes were isolated and fixed: the host v1 `new_frame` helper omitted the payload field, firmware hello capability insertion order disagreed with canonical digest order, the host failure-reason bound was too short, firmware rejected nullable Copilot flags, and the smoke runner failed to inherit fd 9 into capture subprocesses. No pairing identity was changed.

## Human Verification

Using the supported interactive smoke finalization path, the exact device evidence now has `status: pass`, a checksum sidecar, and all four physical sightings set to `Y`. The user confirmed readable CODEX/COPILOT alternation with equal dwell, no blank or mixed flash, exact keys 1-3 focus, inert panel-4 key, and neutral/stale behavior. After current native-plugin deployment, the user confirmed panel 4 shows live Copilot `1500/1500` values alternating with Codex. No claim beyond these confirmations is recorded.


## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Kept capture fixture tokens unique**
- **Found during:** Task 2
- **Issue:** Newly added Copilot capture tokens collided with existing closed scene tokens.
- **Fix:** Moved the colliding Copilot/neutral fixtures to unused bounded tokens while preserving the existing vocabulary.
- **Files modified:** `tools/capture_panel.py`, firmware capture-scene/parser files, related fixtures/tests.
- **Verification:** Native projection suite and capture-scene tests passed.
- **Committed in:** `9b3c567`.

**2. [Rule 3 - Blocking] Replaced the unavailable bridge wrapper with the installed lifecycle owner**
- **Found during:** Task 3
- **Issue:** The plan's `ensure-bridge.sh run-exclusive` precondition names a file that does not exist in this checkout.
- **Fix:** Used the installed `herdr-keypad` binary's explicit stop/status/start lifecycle and retained the inherited fd-9 lock requirement in the smoke driver; no Python bridge or second serial owner was introduced.
- **Files modified:** `tools/phase1_bringup/src/phase1_bringup/phase3_smoke.py` and `tools/phase1_bringup/test_phase3_smoke.py`.
- **Verification:** Native owner restored; final status reports running/ready device state.
- **Committed in:** `4e53771`.

**3. [Rule 1 - Bug] Restored the closed v1 probe payload contract**
- **Found during:** exact-device capture
- **Issue:** The host `new_frame` helper omitted `"payload"`, causing every probe request to fail before the paired device could be selected.
- **Fix:** Included the supplied payload in v1 frames and added a closed probe round-trip regression.
- **Files modified:** `tools/phase1_bringup/src/phase1_bringup/protocol.py`, `host/herdr_keypad/tests/test_protocol.py`.
- **Committed in:** `713bef4`.

**4. [Rule 1 - Bug] Matched firmware hello digest insertion order to canonical payload order**
- **Found during:** fresh raw hello diagnosis
- **Issue:** Firmware emitted hello capabilities before identity fields, producing a digest different from the host's canonical sorted payload digest.
- **Fix:** Constructed hello capability output in canonical key order.
- **Files modified:** `firmware/src/main.cpp`.
- **Verification:** Fresh exact hello accepted after upload.
- **Committed in:** `713bef4`.

**5. [Rule 1 - Bug] Accepted nullable Copilot flags and the full bounded failure-reason allowlist**
- **Found during:** neutral unavailable exact-device snapshot
- **Issue:** Firmware rejected legal nullable `reached_limit`/permission fields, while the host rejected the legal 24-character `billing_mode_unsupported` reason.
- **Fix:** Enforced the complete Copilot presence mask while permitting nullable booleans and raised the host reason bound to the protocol's 32-byte capacity with regression coverage.
- **Files modified:** `firmware/src/protocol/protocol.cpp`, `tools/phase1_bringup/src/phase1_bringup/protocol.py`, `host/herdr_keypad/tests/test_protocol.py`.
- **Committed in:** `713bef4`.

**6. [Rule 3 - Blocking] Passed the exclusive bridge lock into capture subprocesses**
- **Found during:** complete exact smoke
- **Issue:** Capture subprocesses did not inherit fd 9, so the lock guard failed and discovery reduced the cause to a misleading mismatch.
- **Fix:** Passed fd 9 and bounded the capture subprocess timeout.
- **Files modified:** `tools/phase1_bringup/src/phase1_bringup/phase3_smoke.py`.
- **Verification:** Complete guarded smoke exited 0 and wrote both captures.
- **Committed in:** `713bef4`.

**Total deviations:** 6 auto-fixed (Rules 1: 4; Rule 3: 2).

## Next Phase Readiness

Complete. The protocol, host publication path, firmware selector/renderers, regression coverage, selected-usb build/upload, exact paired captures, finalized evidence, and live native-plugin activation are verified. The current linked plugin is active at `/home/nnex/.local/share/herdr/plugins/herdr-keypad`; status is device-ready with current live Copilot values. No follow-up gate remains for this quick task.


## Self-Check: PASSED

- Summary file exists at the required quick-task path.
- Commits `d5bb3b4`, `64e1adf`, `9b3c567`, `4e53771`, and `713bef4` resolve in git history.
- Final evidence and checksum sidecar exist; final evidence reports `status: pass` and four `Y` sightings.
- Active durable linked plugin binary matches the rebuilt release SHA-256 `7d04558a29cb6bd554bf29cdc4a67dde3b62b038d595e498f3d5921c5be0c749`.
- No generated PPM/RGB565/evidence, PLAN, STATE, or ROADMAP file was committed.

---
*Phase: quick*
*Completed: 2026-08-30 (implementation and exact-device/live-plugin verification complete)*
