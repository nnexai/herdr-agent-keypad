---
phase: 04-production-rust-host-bridge
plan: "01"
subsystem: native-host-bridge
tags: [rust, tokio, serde, herdr, focus, usb, tracing]

requires: []
provides:
  - "Bounded BridgeEvent, BridgeEffect, Generation, Clock, Deadline, Cancellation, and boundary-port contracts."
  - "Authoritative Herdr snapshot normalization with fixed three-slot projection and matching snapshot-ACK readiness."
  - "Exact identity/session-bound focus revalidation and correlated focus result with no host HID effect."
  - "Thin native process entrypoint wired only to the maintained core::RuntimeCoordinator."
affects: [04-02, 04-03, 04-04, 04-05, 04-06, 04-07, native-host-bridge]

current-authority:
  amendment: "WR-01 accepted clean-cutover supersession"
  production-composition: "host/herdr_keypad/native/src/core/orchestrator.rs#RuntimeCoordinator"
  proof:
    - "host/herdr_keypad/native/tests/black_box_parity.rs#python_oracle_export_is_byte_identical_to_checked_in_corpus"
    - "host/herdr_keypad/native/tests/black_box_parity.rs#every_protocol_trace_matches_public_rust_admission_contract"
    - "host/herdr_keypad/native/tests/black_box_parity.rs#session_trace_fences_duplicate_stale_and_foreign_authority"
    - "host/herdr_keypad/native/tests/black_box_parity.rs#projection_traces_match_python_observable_views"
    - "host/herdr_keypad/native/tests/projection_focus_parity.rs#focus_policy_revalidates_exact_identity_and_allows_one_retry"
    - "host/herdr_keypad/native/tests/projection_focus_parity.rs#focus_policy_maps_fences_and_failures_without_other_effects"
    - "host/herdr_keypad/native/tests/herdr_parity.rs#correlated_subscribe_ack_admits_only_typed_invalidation_events"
    - "host/herdr_keypad/native/tests/herdr_parity.rs#complete_reads_correlate_ids_and_focus_is_the_only_write"
    - "host/herdr_keypad/native/tests/usb_platform.rs#exact_hello_then_snapshot_ack_gates_readiness_and_close_clears_focus"
    - "host/herdr_keypad/native/tests/usb_platform.rs#same_boot_id_reconnects_with_fresh_host_session_and_rejects_old_frames"
    - "host/herdr_keypad/native/tests/production_surface.rs#production_binary_start_status_stop_owns_control_socket_for_authority_lifetime"

actuals:
  tokens: 18099
  tasks: 2
  commits: 3

tech-stack:
  added: ["Rust 1.98.0", "Tokio 1.53.1", "Serde 1.0.229", "Serde JSON 1.0.151", "tokio-serial 5.5.0", "serialport 4.10.0", "tracing 0.1.44", "tracing-subscriber 0.3.23", "toml 1.1.4", "sha2 0.11.0", "fs2 0.4.3"]
  patterns: ["bounded event-driven select loop", "complete-read then snapshot-ACK generation fence", "exact identity revalidation before sole agent.focus write", "typed shutdown without HID authority"]

key-files:
  created:
    - host/herdr_keypad/native/Cargo.toml
    - host/herdr_keypad/native/Cargo.lock
    - host/herdr_keypad/native/rust-toolchain.toml
    - host/herdr_keypad/native/src/lib.rs
    - host/herdr_keypad/native/src/main.rs
    - host/herdr_keypad/native/tests/production_tracer.rs
  modified: []
  current:
    - host/herdr_keypad/native/src/core/orchestrator.rs
    - host/herdr_keypad/native/tests/black_box_parity.rs
    - host/herdr_keypad/native/tests/projection_focus_parity.rs
    - host/herdr_keypad/native/tests/herdr_parity.rs
    - host/herdr_keypad/native/tests/usb_platform.rs
    - host/herdr_keypad/native/tests/production_surface.rs

key-decisions:
  - "Pin the currently available verified stable compiler, Rust 1.98.0, because the research-era workstation Rust 1.82.0 cannot parse the maintained direct dependency set (notably sha2/toml transitive edition requirements)."
  - "Keep Herdr authority and process lifetime explicit; only exact agent.focus is represented at the Herdr boundary and no HID/keyboard effect exists in the public contract."
  - "Use independent explicit capacities for Herdr events, device frames, effects, pending focus, and Herdr/device line lengths; no fixed-rate wakeup is introduced."

requirements-completed: [RUST-01, RUST-02, RUST-03]

coverage-scope: "Historical completion evidence from the original task commits; current authority is the WR-01 composed proof above."

coverage:
  - id: D1
    description: "Complete authoritative Herdr read publishes three slots and matching snapshot ACK gates exact focus."
    requirement: RUST-01
    verification:
      - kind: e2e
        ref: "host/herdr_keypad/native/tests/production_tracer.rs#tracer_authoritative_snapshot_ack_then_exact_focus"
        status: pass
    human_judgment: false
  - id: D2
    description: "Herdr authority cancellation exits cleanly and emits no keyboard/HID effect."
    requirement: RUST-02
    verification:
      - kind: integration
        ref: "host/herdr_keypad/native/tests/production_tracer.rs#tracer_herdr_authority_cancellation_clears_pending_work"
        status: pass
    human_judgment: false
  - id: D3
    description: "Native crate metadata resolves from the committed lockfile on the pinned Linux x86-64 toolchain."
    requirement: RUST-03
    verification:
      - kind: other
        ref: "RUSTUP_TOOLCHAIN=1.98.0 cargo metadata --manifest-path host/herdr_keypad/native/Cargo.toml --locked --format-version 1"
        status: pass
    human_judgment: false

---

# Phase 04 Plan 01: Production Rust Host Bridge Summary

**Locked Rust native bridge crate with bounded Herdr authority, complete snapshot-ACK readiness, exact focus revalidation, and cancellation-safe process entrypoint.**

## Current-state amendment: WR-01 clean-cutover supersession

This summary preserves the original Plan 04-01 task and commit history. The first execution introduced a root `Coordinator` and `tests/production_tracer.rs`; the completion evidence below accurately records what existed at those commits.

The Phase 04 closure review later resolved WR-01 by removing that duplicate coordinator, its unsafe unbounded Herdr socket reader, and the coupled tracer. `src/main.rs` now constructs only `core::RuntimeCoordinator`. Restoring the deleted path would recreate a second production composition root and break the clean cutover.

Current verification authority is the maintained composed proof:

| Original contract segment | Maintained path and exact test |
|---|---|
| Frozen Python parity and closed protocol/session/projection admission | `black_box_parity.rs`: `python_oracle_export_is_byte_identical_to_checked_in_corpus`, `every_protocol_trace_matches_public_rust_admission_contract`, `session_trace_fences_duplicate_stale_and_foreign_authority`, `projection_traces_match_python_observable_views` |
| Committed projection binding and exact focus behavior | `projection_focus_parity.rs`: `focus_policy_revalidates_exact_identity_and_allows_one_retry`, `focus_policy_maps_fences_and_failures_without_other_effects` |
| Typed Herdr invalidation, complete authoritative read, and sole `agent.focus` write | `herdr_parity.rs`: `correlated_subscribe_ack_admits_only_typed_invalidation_events`, `complete_reads_correlate_ids_and_focus_is_the_only_write` |
| Fresh USB authority and matching snapshot-ACK readiness | `usb_platform.rs`: `exact_hello_then_snapshot_ack_gates_readiness_and_close_clears_focus`, `same_boot_id_reconnects_with_fresh_host_session_and_rejects_old_frames` |
| Production composition and Herdr-owned process lifetime | `src/main.rs` to `core/orchestrator.rs#RuntimeCoordinator`; `production_surface.rs`: `production_binary_start_status_stop_owns_control_socket_for_authority_lifetime` |

Together, these authorities cover the original Herdr invalidation to complete read, projection, USB session and snapshot ACK, exact focus revalidation, sole Herdr write, correlated focus result, and lifecycle contract through the maintained production boundaries. This amendment accepts that composed proof. It does not claim a rerun of the removed tracer or alter the original task commits.

## Performance

- **Duration:** 31 minutes (first task commit through final task commit)
- **Started:** 2026-08-30T02:47:28+02:00
- **Completed:** 2026-08-30T03:18:20+02:00
- **Tasks:** 2
- **Files modified:** 6 created

## Original accomplishments

The entries in this section describe the initial task commits:

- Added the locked native Cargo crate and thin `main.rs` entrypoint around the initial reusable coordinator API.
- Implemented complete Herdr `session.snapshot`/`agent.list`/`workspace.list` reads, rank ordering, fixed three-slot projection, explicit line bounds, and typed boundary contracts.
- Enforced matching host epoch, snapshot revision, boot/session authority, slot, entry, and immutable agent identity before one revalidation and the sole `agent.focus` write.
- Added cancellation and bounded-channel behavior that clears pending focus work and exposes only `AuthorityEnded`; no HID or keyboard effect is representable.
- Added the focused black-box tracer and cancellation test, with a local Unix socket Herdr endpoint and bounded device-frame ingress.

## Original task commits

1. **Task 1: Carry one exact focus path through every production layer** - `89e7462` (test RED), `e4fbccd` (feat GREEN)
2. **Task 2: Pin the compiler and freeze downstream interface ownership** - `25a0994` (chore)

## Original files created/modified

- `host/herdr_keypad/native/Cargo.toml` - approved direct dependency manifest and explicit Tokio capabilities.
- `host/herdr_keypad/native/Cargo.lock` - locked direct and transitive dependency resolution.
- `host/herdr_keypad/native/rust-toolchain.toml` - Rust 1.98.0 and `x86_64-unknown-linux-gnu` target pin.
- `host/herdr_keypad/native/src/lib.rs` - durable domain, generation, boundary-port, framing, coordinator, and shutdown contracts.
- `host/herdr_keypad/native/src/main.rs` - thin bundled process entrypoint invoking `Coordinator`.
- `host/herdr_keypad/native/tests/production_tracer.rs` - Herdr socket tracer and authority cancellation proof.

## Original decisions

- Rust 1.98.0 is pinned after an actual stable-toolchain probe and successful locked build/test/metadata runs; the locally preinstalled 1.82.0 compiler cannot parse the maintained dependency graph. This supersedes the research workstation observation without adding a prerelease or unsupported target.
- The public effect enum is intentionally closed to `PublishSnapshot`, `FocusResult`, and `AuthorityEnded`; there is no host HID authority and no generic Herdr method forwarding.
- Snapshot publication is not action readiness: a complete projection is published first, then matching device ACK plus generation/identity equality permits exact focus.

## Original deviations from plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Resolved compiler compatibility for the maintained dependency set**
- **Found during:** Task 1 dependency bootstrap and Task 2 toolchain pin
- **Issue:** The workstation's preinstalled Cargo/Rust 1.82.0 rejected edition-2024 transitive manifests pulled by the researched maintained direct crates.
- **Fix:** Probed and installed the current stable Rust 1.98.0 toolchain, pinned it in `rust-toolchain.toml`, and regenerated the lockfile with the researched direct versions.
- **Files modified:** `host/herdr_keypad/native/Cargo.lock`, `host/herdr_keypad/native/rust-toolchain.toml`
- **Verification:** Locked `cargo test`, `cargo build`, and `cargo metadata` all pass with `RUSTUP_TOOLCHAIN=1.98.0`.
- **Committed in:** `25a0994`

**2. [Plan boundary] Kept the tracer's device ingress typed and bounded**
- **Found during:** Task 1 tracer integration
- **Issue:** A direct PTY fixture could not be made reliable on this host without introducing an unapproved native/PTY dependency or a test-only runtime wrapper; Plan 05 owns concrete USB/platform PTY adapters.
- **Fix:** The tracer crosses the real Herdr Unix socket and the same public coordinator through bounded `DeviceFrame` ingress; reusable bounded `encode_device_line`/`decode_device_line` helpers are present for the downstream USB adapter.
- **Files modified:** `host/herdr_keypad/native/src/lib.rs`, `host/herdr_keypad/native/tests/production_tracer.rs`
- **Verification:** Named tracer and cancellation tests pass under the locked crate.
- **Committed in:** `e4fbccd`

---

**Total deviations:** 2 (one blocking compatibility fix, one scoped adapter-boundary adjustment)
**Impact on plan:** The complete authoritative snapshot-ACK-to-exact-focus seam is proven without adding a runtime, shell wrapper, HID operation, protocol action, or unsupported dependency. Concrete PTY/USB I/O remains isolated for Plan 05 as specified by the ownership contract.

## Issues Encountered

- Rustup initially had only Cargo/Rust 1.82.0 active; the actual current stable channel was probed and verified as 1.98.0 before pinning.
- No unrelated source, planning state, formatter, linter, project-wide suite, UAT, or physical validation was run.

## User Setup Required

None - no external service configuration required.

## Original downstream readiness

- Plans 03-06 can consume the stable root `BridgeEvent`, `BridgeEffect`, `Generation`, `Clock`, `Deadline`, `Cancellation`, bounded-capacity constants, and Herdr/Device port contracts without redefining process or HID authority.
- Plan 03 owns strict v2 protocol/domain additions; Plan 04 owns concrete Herdr/Codex ports; Plan 05 owns USB/platform PTY adapters; Plan 06 owns lifecycle/config/control/status/logging; Plan 07 alone owns shared root integration.
- `STATE.md` and `ROADMAP.md` were intentionally not modified in this isolated executor worktree per wave contract.

---
*Phase: 04-production-rust-host-bridge*
*Completed: 2026-08-30*

## Original self-check: passed at completion

- At the original completion commit, all six planned native artifacts and this SUMMARY existed.
- Task commits `89e7462`, `e4fbccd`, `25a0994`, and summary commit `4f573ee` exist.
- The WR-01 amendment replaces current authority with the maintained paths listed above; it does not assert that the deleted tracer still exists.
