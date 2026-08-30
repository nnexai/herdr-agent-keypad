---
phase: 04-production-rust-host-bridge
reviewed: 2026-08-30T07:04:37Z
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
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 04: Code Review Report

**Reviewed:** 2026-08-30T07:04:37Z  
**Depth:** deep; narrow closure check of CR-01, CR-02, and WR-01  
**Files Reviewed:** 51  
**Status:** clean

## Summary

Review scope was computed from all ten `04-*-SUMMARY.md` artifacts and cross-checked against `git diff 89e7462^..HEAD`; the latter includes the native control-socket lifecycle fix. Phase context, plans, research, and the frozen Python oracle informed the original review. Hosted release execution and GitHub Actions runs remain intentionally outside the Phase 04 blocker boundary.

The narrow closure review inspected only the merged implementations and regression coverage for the three prior findings. All three findings are resolved. The focused merged suite is reported by the integration owner as 50/50 passing, `cargo check` passes, and live deployment proved a same-config restart replaced PID `699375` with `700051`, exited the old process, recreated `bridge.sock`, and returned running status. No UAT or hardware action is required for this closure.

## Narrative Findings (AI reviewer)

## Resolved Findings

### CR-01: Resolved — restart crosses a real process boundary and reloads startup configuration

**Evidence:** `LifecycleOwner::request_restart` now accepts the requested identity and marks the current authority for shutdown (`host/herdr_keypad/native/src/ports/lifecycle.rs:195-217`). Once the `restarted` reply has been sent, `RuntimeCoordinator::run` invokes `shutdown_for_restart` and exits (`host/herdr_keypad/native/src/core/orchestrator.rs:220-233`), closing ingress and dropping authority before the replacement binary starts. `production_binary_restart_replaces_pid_reloads_config_and_reopens_socket` proves changed-config and same-config restart paths: replacement PID, old-process exit, socket recreation, changed configuration identity, and subsequent stop (`host/herdr_keypad/native/tests/production_surface.rs:128-215`). Current live deployment corroborates the same-config PID replacement and running control socket/status.

### CR-02: Resolved — a same-boot keypad reconnects through a fresh host session

**Evidence:** `UsbPort` no longer stores or rejects `previous_device_boot` (`host/herdr_keypad/native/src/ports/usb.rs:370-392,487-494,548-553`). Each hello still creates a fresh host session and requires it in the acknowledgement (`host/herdr_keypad/native/src/ports/usb.rs:458-490`); post-hello receive admission continues to require exact current boot/session identity and strictly increasing sequence. The added regression `same_boot_id_reconnects_with_fresh_host_session_and_rejects_old_frames` exercises a reconnect with unchanged device boot ID, verifies a fresh session, and rejects stale-session frames (`host/herdr_keypad/native/tests/usb_platform.rs:230-308`).

### WR-01: Resolved — obsolete public coordinator and unsafe Herdr socket path were removed

**Evidence:** `host/herdr_keypad/native/src/lib.rs` is now the 204-line domain/port contract module. The duplicate public `Coordinator` and `HerdrSocket` implementation, including its unbounded `read_until` path, are absent; production wiring remains through `core::RuntimeCoordinator`. The merged diff removes 926 lines from the obsolete path, and the associated obsolete tracer test was removed in the follow-up cleanup commit.

---

_Reviewed: 2026-08-30T07:04:37Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: deep closure review_
