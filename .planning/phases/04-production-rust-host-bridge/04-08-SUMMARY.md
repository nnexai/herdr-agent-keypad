---
phase: 04-production-rust-host-bridge
plan: "08"
subsystem: plugin-cutover
tags: [rust, herdr, lifecycle, packaging, privacy, native]

# Dependency graph
requires:
  - phase: 04-production-rust-host-bridge
    provides: Integrated native runtime and closed startup/lifecycle/status/repair/re-pair command surface from Plan 07
provides:
  - Bundled ordinary-user lifecycle, removal, update-activation, and failed-update recovery procedure
  - Direct target-scoped native Herdr startup and explicit action manifest
  - Machine-enforced lifecycle, manifest, privacy, and legacy-authority cutover checks
affects: [04-09-native-release, herdr-keypad-production-launch, native-plugin-packaging]

# Actuals (#2632)
actuals:
  tokens: 5584
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Direct bundled executable argv for Herdr startup and explicit lifecycle actions
    - Ordered procedure parsing for stop-before-removal and manual known-release recovery
    - Bounded symbolic lifecycle/privacy checks that reject machine-specific and sensitive content

key-files:
  created:
    - host/herdr_keypad/LIFECYCLE.md
    - host/herdr_keypad/native/tests/plugin_cutover.rs
  modified:
    - host/herdr_keypad/herdr-plugin.toml
    - host/herdr_keypad/scripts/ensure-bridge.sh (removed)

key-decisions:
  - "Require Herdr 0.8.2 and expose Linux plus macOS target entries using the same bundled bin/herdr-keypad path."
  - "Keep status as a separate global read-only action with direct status argv and no mutation authority."
  - "Require successful explicit stop before disable, unlink, or removal, and use manual known-release reinstall for failed-update recovery."

patterns-established:
  - "Lifecycle documentation is a machine-checked ordered contract, not a prose-only operational suggestion."
  - "Production manifest commands contain only direct native executable argv; Python, shell, event watchdog, and service authorities are absent."

requirements-completed: [RUST-05, RUST-06, RUST-07, RUST-08]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Bundled lifecycle procedure covers symbolic install, explicit start/status/stop/restart, stop-before-disable/unlink/remove, restart-or-next-start update activation, and manual known-release recovery."
    requirement: RUST-05
    verification:
      - kind: integration
        ref: "cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test plugin_cutover lifecycle_document_"
        status: pass
    human_judgment: false
  - id: D2
    description: "Herdr manifest directly invokes target-bundled native startup and the exact six-action surface, includes the lifecycle document, and removes the legacy launcher authority."
    requirement: RUST-07
    verification:
      - kind: integration
        ref: "cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test plugin_cutover manifest_cutover_"
        status: pass
    human_judgment: false

# Metrics
duration: 13min
completed: 2026-08-30
status: complete
---

# Phase 04 Plan 08: Production Plugin Cutover Summary

**The Herdr package now documents and machine-checks explicit native lifecycle/recovery behavior while invoking only the target-bundled Rust executable.**

## Performance

- **Duration:** 13 min (approximate execution window)
- **Started:** 2026-08-30T05:05:00Z (approximate)
- **Completed:** 2026-08-30T05:17:41Z
- **Tasks:** 2
- **Files modified:** 4 (including the intentional launcher removal)

## Accomplishments

- Bundled `LIFECYCLE.md` gives ordinary users zero-config Herdr installation, explicit start/status/stop/restart operation, explicit stop-before-disable/unlink/removal safety, restart-or-next-start update activation, and deterministic manual known-release failed-update recovery.
- Replaced the Linux shell startup/event hooks with Herdr 0.8.2 startup and six direct native actions for Linux and macOS, with status clearly isolated as read-only and no event watchdog.
- Added Rust integration tests that parse required headings and ordered normative steps, enforce symbolic/privacy bounds, validate exact manifest targets/argv/action metadata, and prove the removed launcher is not part of the production package.

## Task Commits

Each task followed the required TDD red/green sequence:

1. **Task 1: Bundle and enforce the lifecycle and recovery procedure** - `8cc4dae` (test), `b768d97` (feat)
2. **Task 2: Cut the Herdr plugin to direct native startup** - `53e3a61` (test), `18613dc` (feat)

The execution summary metadata commit follows after this file is self-checked.

## Files Created/Modified

- `host/herdr_keypad/LIFECYCLE.md` - symbolic ordinary-user install, lifecycle, removal, update, recovery, configuration, and bounded diagnostics procedure.
- `host/herdr_keypad/herdr-plugin.toml` - Herdr 0.8.2 manifest with Linux/macOS target entries and direct `bin/herdr-keypad` startup/action argv.
- `host/herdr_keypad/native/tests/plugin_cutover.rs` - lifecycle content/privacy and manifest cutover integration contracts.
- `host/herdr_keypad/scripts/ensure-bridge.sh` - intentionally deleted obsolete shell/PID/proc/venv production launcher.

## Decisions Made

- Set the minimum Herdr version to 0.8.2, matching the verified one-shot startup and explicit action surface.
- Reused `bin/herdr-keypad` for the target-selected package path; target artifacts remain the release plan's responsibility.
- Kept the lifecycle document symbolic and bounded to Herdr-provided directories, with no host-specific paths, credentials, conversation data, or diagnostic payloads.
- Kept Python modules and their tests available as parity-oracle material only; they are not referenced by the production manifest.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Expected TDD red gates failed on the absent lifecycle document and legacy manifest before their corresponding implementations; both locked green cutover checks passed after implementation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The production plugin cutover is ready for Plan 09 release packaging. Release automation must materialize exactly one target-native `bin/herdr-keypad` alongside this manifest and `LIFECYCLE.md`, while retaining the direct argv and privacy contracts verified here. No UAT, physical validation, formatter, linter, or repository-wide suite was run.

## Self-Check: PASSED

- Summary file exists at the required phase path.
- Lifecycle and plugin-cutover test files, manifest, and bundled document exist.
- The obsolete launcher is absent.
- Task commits `8cc4dae`, `b768d97`, `53e3a61`, and `18613dc` exist in repository history.
- Both required locked plugin-cutover test filters passed.

---
*Phase: 04-production-rust-host-bridge*
*Completed: 2026-08-30*
