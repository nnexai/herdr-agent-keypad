---
phase: 04-production-rust-host-bridge
reviewed: 2026-08-30T06:48:53Z
depth: deep
files_reviewed: 51
files_reviewed_list:
  - .github/workflows/native-release.yml
  - host/herdr_keypad/LIFECYCLE.md
  - host/herdr_keypad/bundle/manifest.schema.json
  - host/herdr_keypad/herdr-plugin.toml
  - host/herdr_keypad/native/Cargo.lock
  - host/herdr_keypad/native/Cargo.toml
  - host/herdr_keypad/native/rust-toolchain.toml
  - host/herdr_keypad/native/src/core/focus.rs
  - host/herdr_keypad/native/src/core/mod.rs
  - host/herdr_keypad/native/src/core/model.rs
  - host/herdr_keypad/native/src/core/orchestrator.rs
  - host/herdr_keypad/native/src/core/projection.rs
  - host/herdr_keypad/native/src/lib.rs
  - host/herdr_keypad/native/src/main.rs
  - host/herdr_keypad/native/src/platform/linux.rs
  - host/herdr_keypad/native/src/platform/macos.rs
  - host/herdr_keypad/native/src/platform/mod.rs
  - host/herdr_keypad/native/src/ports/codex.rs
  - host/herdr_keypad/native/src/ports/config.rs
  - host/herdr_keypad/native/src/ports/control.rs
  - host/herdr_keypad/native/src/ports/herdr.rs
  - host/herdr_keypad/native/src/ports/lifecycle.rs
  - host/herdr_keypad/native/src/ports/logging.rs
  - host/herdr_keypad/native/src/ports/mod.rs
  - host/herdr_keypad/native/src/ports/status.rs
  - host/herdr_keypad/native/src/ports/usb.rs
  - host/herdr_keypad/native/src/protocol/mod.rs
  - host/herdr_keypad/native/src/protocol/v2.rs
  - host/herdr_keypad/native/tests/black_box_parity.rs
  - host/herdr_keypad/native/tests/codex_parity.rs
  - host/herdr_keypad/native/tests/fixtures/codex.json
  - host/herdr_keypad/native/tests/fixtures/lifecycle.json
  - host/herdr_keypad/native/tests/fixtures/macos-serial.json
  - host/herdr_keypad/native/tests/fixtures/projection-focus.json
  - host/herdr_keypad/native/tests/fixtures/protocol.json
  - host/herdr_keypad/native/tests/herdr_parity.rs
  - host/herdr_keypad/native/tests/lifecycle_resource.rs
  - host/herdr_keypad/native/tests/plugin_cutover.rs
  - host/herdr_keypad/native/tests/production_surface.rs
  - host/herdr_keypad/native/tests/production_tracer.rs
  - host/herdr_keypad/native/tests/projection_focus_parity.rs
  - host/herdr_keypad/native/tests/protocol_parity.rs
  - host/herdr_keypad/native/tests/python_oracle_fixture.rs
  - host/herdr_keypad/native/tests/release_bundle.rs
  - host/herdr_keypad/native/tests/resource_bounds.rs
  - host/herdr_keypad/native/tests/usb_platform.rs
  - host/herdr_keypad/release/collect_phase4_evidence.py
  - host/herdr_keypad/release/test_collect_phase4_evidence.py
  - host/herdr_keypad/release/verify_bundle.py
  - host/herdr_keypad/scripts/ensure-bridge.sh
  - host/herdr_keypad/tests/export_rust_oracle.py
findings:
  critical: 2
  warning: 1
  info: 0
  total: 3
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-08-30T06:48:53Z  
**Depth:** deep  
**Files Reviewed:** 51  
**Status:** issues_found

## Summary

Review scope was computed from all ten `04-*-SUMMARY.md` artifacts and cross-checked against `git diff 89e7462^..HEAD`; the latter additionally includes the current native control-socket lifecycle fix. Phase context, plans, research, and the frozen Python oracle were used to assess the Rust cutover contract. Hosted release execution and GitHub Actions runs are intentionally not reviewed as Phase 04 blockers.

The direct startup/control smoke test covers `start → status → stop`, but two core lifecycle paths remain observably incorrect: `restart` does not restart the process or adopt a changed configuration, and a routine USB disconnect is permanently rejected until the device reboots. The crate also retains a second public, pre-cutover coordinator with materially weaker socket safety, creating an unsupported production-capable path beside `RuntimeCoordinator`.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `restart` acknowledges success without restarting or applying the requested configuration

**File:** `host/herdr_keypad/native/src/ports/lifecycle.rs:149-157`, `host/herdr_keypad/native/src/core/orchestrator.rs:220-228`

**Issue:** A `restart` control request whose `config_identity` differs from the running process is always converted to `RestartRequired` at `LifecycleOwner::handle_control`; no pending configuration is installed and no replacement process is started. For an identity that matches, `restart_with_pending()` only mutates in-memory lifecycle flags (`active`, `herdr_alive`, `sessions_valid`, and `session_epoch`). The coordinator then continues its existing Herdr event stream, Codex state, USB session, and startup-derived configuration. It sends a `restarted` reply at line 222 without a process restart or resource reinitialization.

This violates the explicit lifecycle command contract: configuration is startup-only, so a changed config must take effect through `restart`; a same-config restart must still actually recreate the runtime boundary. The current `production_binary_start_status_stop_owns_control_socket_for_authority_lifetime` test never invokes `restart`, so it cannot detect this false-success path.

**Fix:** Make restart a process-boundary operation. After replying (or with an acknowledgement/hand-off protocol), request coordinator shutdown and let the Herdr action start a new native process with freshly loaded `StartupConfig`; do not manufacture `Restarted` from `LifecycleOwner` alone. If the existing action model cannot launch a replacement, return a bounded rejection such as `restart_required` and document/implement the explicit `stop` then `start` sequence instead. Add an integration test that changes `config.toml`, invokes `restart`, and proves the replacement PID/config identity and reopened control socket; also test same-config restart reinitializes the runtime.

### CR-02: USB reconnects to the same still-booted keypad are rejected forever

**File:** `host/herdr_keypad/native/src/ports/usb.rs:489-491`, `host/herdr_keypad/native/src/ports/usb.rs:553-556`

**Issue:** Every disconnect/error calls `reset_link`, which saves the connected device's `device_boot_id` in `previous_device_boot`. On the next `connect`, `perform_hello` rejects the exact same boot ID with `SessionMismatch`. A normal cable/CDC reset or host-side reconnect does not reboot the keypad, so its boot ID remains unchanged. The coordinator consequently backs off and retries indefinitely, never restoring the USB session, snapshots, or keypress focus path until the physical device is rebooted.

This directly contradicts the required fresh-session-on-reconnect behavior. The host already creates a new opaque `host_session` for every hello (lines 460-464), so the previous host session's sequence/ACK authority is fenced without treating a stable device boot ID as invalid.

**Fix:** Remove the `previous_device_boot` rejection (and the state whose sole purpose is that comparison), while retaining the new host session ID and strict boot/session equality checks in `receive_v2`. Add a regression test that completes hello, closes the transport without changing the fixture device boot ID, then reconnects and successfully publishes/ACKs a fresh snapshot; verify frames from the old session remain rejected.

## Warnings

### WR-01: Obsolete public coordinator retains an unsafe alternate Herdr implementation after production cutover

**File:** `host/herdr_keypad/native/src/lib.rs:623-982`

**Issue:** `lib.rs` still exports the older public `Coordinator`/`HerdrSocket` implementation alongside the actual `core::RuntimeCoordinator`. It has a different projection/focus protocol and an unbounded `BufReader::read_until` allocation before its length check (`lib.rs:886-893`), while its socket operations have no I/O deadline. This is not merely unused test scaffolding: `Coordinator` is public and callable by any crate consumer, so it preserves a reachable alternate bridge path that can hang on a silent socket or allocate beyond `HERDR_LINE_LIMIT`. Maintaining two coordinator implementations also defeats the intended Python-to-Rust clean cutover and makes future fixes prone to landing on the wrong behavior.

**Fix:** Delete the superseded `Coordinator`, `HerdrSocket`, and their legacy boundary types if they have no remaining caller. If a portable coordinator is intentionally retained, make it private/test-only and refactor it to use the bounded, timeout-enforced `ports::herdr::HerdrClient` contract; do not expose both production paths.

---

_Reviewed: 2026-08-30T06:48:53Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: deep_
