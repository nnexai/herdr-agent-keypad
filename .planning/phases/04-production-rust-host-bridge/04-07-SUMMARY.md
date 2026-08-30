---
phase: 04-production-rust-host-bridge
plan: "07"
subsystem: native-runtime
tags: [rust, tokio, herdr, codex, usb, lifecycle, production-cli]
# Dependency graph
requires:
  - phase: 04-production-rust-host-bridge
    provides: Plans 03-06 portable core, Herdr/Codex/USB adapters, platform serial implementations, and lifecycle/config/status contracts
provides:
  - One bounded Tokio runtime coordinator joining Herdr, Codex, USB, projection, focus, lifecycle, and safe logging
  - Closed native production command surface for startup, lifecycle, status, repair, and re-pair
  - Target-gated Linux/macOS platform and native adapter module registries
  - Protocol module registration and a lock-verified native dependency graph
affects: [04-08-plugin-manifest-cutover, native-host-runtime, keypad-production-launch]

# Actuals (#2632)
actuals:
  tokens: 9916
  tasks: 2
  commits: 6

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Tokio select-driven orchestration with independent boundary health and explicit reconnect/Codex deadlines
    - Dirty complete-refresh coalescing after Herdr invalidation, with ACK-gated USB actionability
    - Closed direct-argv production parser using Herdr-provided runtime paths and fixed pairing authority
    - Target-gated platform module selection and explicit native protocol/port registries

key-files:
  created:
    - host/herdr_keypad/native/src/core/mod.rs
    - host/herdr_keypad/native/src/core/orchestrator.rs
    - host/herdr_keypad/native/src/platform/mod.rs
    - host/herdr_keypad/native/src/ports/mod.rs
    - host/herdr_keypad/native/src/protocol/mod.rs
  modified:
    - host/herdr_keypad/native/src/lib.rs
    - host/herdr_keypad/native/src/main.rs

key-decisions:
  - "Keep Plans 03-06 adapter and lifecycle APIs unchanged; integrate them through registries and a coordinator-owned policy tier."
  - "Use only Herdr-injected runtime paths plus the validated config file under HERDR_PLUGIN_CONFIG_DIR; keep pairing at ~/.config/herdr/keypad-binding.json with no CLI or environment override."
  - "Treat Herdr authority termination as an orderly coordinator exit, while transport outages schedule independent bounded recovery."
  - "Alias the crate as herdr_keypad_native so completed adapter modules can retain their shared public-boundary imports without introducing a second crate surface."

patterns-established:
  - "Source updates enter through bounded events or explicit deadlines; healthy operation has no fixed-rate source poll."
  - "A snapshot is not actionable until the USB device accepts the complete publication; invalidation fences stale focus work before refresh."

requirements-completed: [RUST-01, RUST-02, RUST-03, RUST-04, RUST-05, RUST-07]

coverage:
  - id: D1
    description: "Integrated bounded coordinator and native module tree"
    requirement: RUST-01
    verification:
      - kind: integration
        ref: "cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test production_tracer --test lifecycle_resource --test projection_focus_parity -- --test-threads=1"
        status: pass
      - kind: other
        ref: "cargo build --locked --manifest-path host/herdr_keypad/native/Cargo.toml"
        status: pass
    human_judgment: false
  - id: D2
    description: "Closed production startup/lifecycle/status/repair/re-pair command surface"
    requirement: RUST-07
    verification:
      - kind: unit
        ref: "cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --bin herdr-keypad-native"
        status: pass
      - kind: integration
        ref: "cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test lifecycle_resource production_command_surface_"
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-08-30
status: complete
---

# Phase 04 Plan 07: Production Runtime Integration Summary

**A lock-verified Rust native bridge now joins all completed boundary adapters behind an event/deadline coordinator and exposes only the approved production lifecycle command surface.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-30T04:53:00Z (execution window, approximate)
- **Completed:** 2026-08-30T05:05:40Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Registered the closed protocol, core, port, and target-gated platform modules and integrated the Wave 2 APIs without moving adapter policy into `main` or platform code.
- Implemented `RuntimeCoordinator` with bounded Tokio event intake, independent Herdr/Codex/USB deadlines, coalesced complete refresh, focus revalidation, ACK-gated readiness, suspend/cancellation cleanup, and clean Herdr authority exit.
- Replaced the broad development-oriented binary argument surface with direct startup/run and explicit start, stop, restart, status, repair, and re-pair commands backed by Herdr runtime paths and the fixed pairing file.
- Confirmed the native crate's locked build and all native integration targets pass: 65 tests across 10 integration suites.

## Task Commits

Each task was committed atomically (with subsequent correctness fixes kept as focused commits):

1. **Task 1: Integrate modules and event-driven orchestration** - `63c1312`, `b8b5882`, `c4850d2`, `8a46354`
2. **Task 2: Close the production command and module surface** - `795b1f3`

The execution summary metadata commit follows after this file is self-checked.

## Files Created/Modified

- `host/herdr_keypad/native/src/core/orchestrator.rs` - bounded runtime coordinator joining lifecycle, Herdr, Codex, projection/focus, USB, and safe logging.
- `host/herdr_keypad/native/src/core/mod.rs` - core module registration and coordinator export.
- `host/herdr_keypad/native/src/protocol/mod.rs` - closed v2 protocol registration/re-export.
- `host/herdr_keypad/native/src/ports/mod.rs` - native adapter registry.
- `host/herdr_keypad/native/src/platform/mod.rs` - Linux/macOS target-gated platform registry.
- `host/herdr_keypad/native/src/lib.rs` - public module registration and shared crate alias for adapter imports.
- `host/herdr_keypad/native/src/main.rs` - production command parser, runtime-path loading, and lifecycle control client.

`Cargo.toml` and `Cargo.lock` already contained the approved dependency versions and features, so no dependency graph changes were necessary.

## Decisions Made

- Preserved the completed Plans 03-06 public APIs and kept core policy in `RuntimeCoordinator` rather than duplicating it in adapters, platform modules, or `main`.
- Used Herdr-injected paths for runtime/config/state and the frozen `~/.config/herdr/keypad-binding.json` pairing authority; competing CLI, environment, and external-file overrides are rejected.
- Kept Herdr, Codex, and USB failure/recovery deadlines independent and made authority termination terminal rather than silently supervising or restarting the bridge.
- Used crate self-aliasing for existing adapter imports instead of changing Wave 2-owned files or adding a second production crate boundary.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Invalidations did not trigger a complete refresh**
- **Found during:** Task 1 (Integrate modules and event-driven orchestration)
- **Issue:** The first coordinator wiring marked projection state stale but did not schedule the required dirty complete Herdr read.
- **Fix:** Added a coalesced dirty-refresh wake, preserved stale publication/actionability fencing, and ran the complete refresh through the existing Herdr adapter.
- **Files modified:** `host/herdr_keypad/native/src/core/orchestrator.rs`
- **Verification:** Focused integration suites passed (22 tests), followed by all native integration suites (65 tests).
- **Committed in:** `b8b5882`

**2. [Rule 1 - Bug] Herdr authority termination surfaced as an error**
- **Found during:** Task 1 (Integrate modules and event-driven orchestration)
- **Issue:** The initial event handler returned a protocol error after authority shutdown, rather than ending the runtime cleanly at the Herdr boundary.
- **Fix:** Handle authority-ended events at the select boundary, close owned resources, and return an orderly success result.
- **Files modified:** `host/herdr_keypad/native/src/core/orchestrator.rs`
- **Verification:** Focused integration suites and locked native build passed.
- **Committed in:** `c4850d2`

**3. [Rule 1 - Correctness cleanup] Deadline helper used a fully qualified future trait despite importing the trait**
- **Found during:** Task 1 (native locked build)
- **Issue:** The coordinator built successfully but emitted an avoidable unused-import warning.
- **Fix:** Use the imported `Future` trait in deadline helper return types.
- **Files modified:** `host/herdr_keypad/native/src/core/orchestrator.rs`
- **Verification:** Focused integration suites passed with the warning removed.
- **Committed in:** `8a46354`

No dependency installation, architectural change, authentication gate, or out-of-scope repair was required.

**Total deviations:** 3 auto-fixed (Rule 1)
**Impact on plan:** All fixes directly strengthened the planned freshness, lifecycle, and build correctness contracts; no scope creep.

## Issues Encountered

- The existing adapter files retain a small set of dead-code warnings because their public APIs are consumed by future runtime paths and test harnesses; the locked build succeeds and no warning suppression was added.
- The plan's approved dependency set was already present in `Cargo.toml` and `Cargo.lock`; the lockfile therefore remained unchanged.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The integrated native crate and closed command surface are ready for the dependent plugin-manifest cutover in Plan 08. The runtime preserves Herdr v0.8.2 authority boundaries and leaves legacy launcher retirement to that dependent plan.

## Self-Check: PASSED

- Summary file exists at the required phase path.
- Task commits `63c1312`, `b8b5882`, `795b1f3`, `c4850d2`, and `8a46354` exist in repository history.
- Locked native build, focused plan suites, command-surface filter, and complete native integration suites passed.

---
*Phase: 04-production-rust-host-bridge*
*Completed: 2026-08-30*
