---
phase: 04-production-rust-host-bridge
plan: "06"
subsystem: native-host-bridge
tags: [rust, lifecycle, config, control-ipc, status, tracing, privacy]

# Dependency graph
requires:
  - phase: 04-production-rust-host-bridge
    provides: "Plan 01 bounded clock/cancellation/event and boundary-port contracts."
  - phase: 04-production-rust-host-bridge
    provides: "Plan 02 deterministic lifecycle/resource oracle fixtures and privacy bounds."
provides:
  - "Startup-only EffectiveConfig and frozen PairingBinding validation with one Herdr config authority."
  - "Lock-authoritative same-user bounded control IPC and Herdr v0.8.2 explicit lifecycle owner."
  - "Read-only bounded StatusSnapshot, allowlisted SafeEvent vocabulary, transition ring, and default-off stderr tracing."
affects: [04-07, native-host-bridge, lifecycle, diagnostics, control]

# Actuals (#2632)
actuals:
  tokens: 14159
  tasks: 2
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Startup-only closed TOML settings under HERDR_PLUGIN_CONFIG_DIR with deterministic SHA-25 identity."
    - "fs2 exclusive lock as the sole local authority, with stale endpoint cleanup only after lock ownership."
    - "Kernel same-user UDS credential checks and 16 KiB pre-parse request/reply admission."
    - "Closed allowlisted safe-code vocabulary shared by a 32-record status transition ring and optional tracing."

key-files:
  created:
    - host/herdr_keypad/native/src/ports/config.rs
    - host/herdr_keypad/native/src/ports/control.rs
    - host/herdr_keypad/native/src/ports/lifecycle.rs
    - host/herdr_keypad/native/src/ports/status.rs
    - host/herdr_keypad/native/src/ports/logging.rs
    - host/herdr_keypad/native/tests/lifecycle_resource.rs
  modified: []

key-decisions:
  - "Use only Herdr-supplied runtime paths plus one fixed config.toml below HERDR_PLUGIN_CONFIG_DIR; no environment, CLI, external-file, or live-reload authority is introduced."
  - "Treat lock ownership, not PID or socket existence, as the one bridge authority; stale control artifacts are removable only after acquiring that lock."
  - "Model Herdr exit, crash, stop, and restart as explicit process-boundary transitions without a watchdog, service, detached child, or automatic recovery."
  - "Compute the config identity dynamically from public effective fields so accidental field edits cannot leave a stale authority hash."
  - "Keep status structurally read-only and diagnostics restricted to safe codes, bounded states, versions, identities, backoff, and transition timestamps."

patterns-established:
  - "LifecycleOwner fences sessions on suspend/resume and never synthesizes device HID release authority."
  - "Status and control decode check payload bytes before deserialization and reject duplicate JSON object keys."
  - "SafeLogger emits no output unless validated startup config enables it and writes only bounded structured safe events."

requirements-completed: [RUST-03, RUST-05, RUST-07, RUST-08]

# Coverage metadata
coverage:
  - id: D1
    description: "Startup config, frozen binding, exclusive authority, explicit lifecycle transitions, stale artifact handling, and suspend/session fencing."
    requirement: RUST-05
    verification:
      - kind: unit
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test lifecycle_resource lifecycle_control_"
        status: pass
      - kind: unit
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test lifecycle_resource lifecycle_config_"
        status: pass
    human_judgment: false
  - id: D2
    description: "Bounded read-only status, privacy-safe allowlisted transitions, default-off logging, and idle resource metrics."
    requirement: RUST-07
    verification:
      - kind: unit
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test lifecycle_resource status_logging_resource_"
        status: pass
    human_judgment: false
  - id: D3
    description: "Full focused lifecycle resource test module passes serially with no project-wide validation."
    requirement: RUST-08
    verification:
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test lifecycle_resource -- --test-threads=1"
        status: pass
    human_judgment: false

# Metrics
duration: 55 min
completed: 2026-08-30
status: complete
---

# Phase 04 Plan 06: Lifecycle, control, status, and logging summary

**Herdr v0.8.2 one-shot lifecycle with startup-only settings, one lock authority, bounded read-only status, and default-off redacted stderr tracing.**

## Performance

- **Duration:** approximately 55 minutes
- **Started:** 2026-08-30T03:45:00Z (approximate; executor start was not externally timestamped)
- **Completed:** 2026-08-30T04:40:18Z
- **Tasks:** 2/2
- **Files modified:** 6 created

## Accomplishments

- Added closed startup configuration and frozen pairing validation. Missing ordinary settings use platform defaults; malformed settings or binding remain unchanged and become safe unavailable diagnostics. Effective settings are hashed to a short deterministic identity and are never watched or reloaded.
- Added the lock-authoritative control seam with private state permissions, stale endpoint cleanup after lock acquisition, kernel same-user checks, closed versioned requests/replies, duplicate-key rejection, and a 16 KiB cap before parsing.
- Added explicit Herdr-bound lifecycle transitions for matching starts, changed-config restart-required responses, restart-applied settings, stop, Herdr exit, crash-stopped state, and suspend/resume session invalidation. No supervisor, service, detached process, or HID release effect is represented.
- Added read-only independent device/Herdr/Codex status, a 32-record safe transition ring, safe event validation, default-off optional stderr tracing through `tracing-subscriber`, privacy filtering, and deterministic idle metrics.

## Task Commits

Each task was committed atomically (with the required TDD red gate):

1. **Task 1: Implement startup-only config and one-authority lifecycle control**
   - `7a9ba52` — `test(04-06): add lifecycle and resource contract tests` (RED)
   - `65f01e1` — `feat(04-06): add startup config and lifecycle authority` (GREEN)
2. **Task 2: Implement read-only status, default-off tracing, and resource bounds**
   - `670a88b` — `feat(04-06): add read-only status and safe tracing` (GREEN)
   - `45e2219` — `fix(04-06): normalize lifecycle test permissions`

**Plan metadata:** summary commit follows after self-check.

## Files Created/Modified

- `host/herdr_keypad/native/src/ports/config.rs` — fixed settings-file authority, canonical effective config identity, and frozen binding parser.
- `host/herdr_keypad/native/src/ports/control.rs` — versioned bounded control protocol, exclusive lock, private socket, and same-user peer admission.
- `host/herdr_keypad/native/src/ports/lifecycle.rs` — explicit lifecycle owner, process/Herdr boundary handling, session fencing, and idle metrics seam.
- `host/herdr_keypad/native/src/ports/status.rs` — closed status model, safe code/event vocabulary, duplicate-safe decode, and transition ring.
- `host/herdr_keypad/native/src/ports/logging.rs` — inert-by-default safe logger and scoped `tracing-subscriber` stderr installation.
- `host/herdr_keypad/native/tests/lifecycle_resource.rs` — focused lifecycle, config, control, status, privacy, logging, and resource checks.

## Decisions Made

- Runtime paths are constructor inputs supplied by Herdr; no source in this plan reads configuration from environment variables, CLI arguments, or arbitrary paths.
- A lock file held for the owner lifetime is the authority proof. A stale PID or endpoint cannot block a new owner after lock acquisition and cannot authorize a request.
- Lifecycle does not restart itself after a crash. Herdr shutdown ends the process state, and explicit start/restart or a later Herdr start is required for recovery.
- Status has no mutating command fields and is serialized only from normalized state. Tracing is configured only when startup settings opt in and emits safe operational codes to stderr.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Recomputed config identity from public effective fields**
- **Found during:** Task 1 GREEN verification
- **Issue:** A caller mutating the public `logging_enabled` field could leave a stored config identity unchanged, incorrectly making changed settings appear idempotent.
- **Fix:** Removed the cached identity field; `identity()` now computes the canonical SHA-25 prefix from the current validated fields.
- **Files modified:** `host/herdr_keypad/native/src/ports/config.rs`
- **Verification:** Lifecycle changed-config start test now returns `restart_required`, and restart reports the new identity.
- **Committed in:** `65f01e1`

**2. [Rule 2 - Missing Critical] Added strict duplicate-key and pre-allocation payload admission**
- **Found during:** Task 2 resource/privacy hardening
- **Issue:** Ordinary Serde decoding accepts duplicate JSON members and an unbounded `read_until` could allocate a large local control line before the cap check.
- **Fix:** Added recursive duplicate-key admission for status/control payloads, bounded endpoint reads to 16 KiB plus one byte, validated reply fields, and included the newline in encoded size checks.
- **Files modified:** `host/herdr_keypad/native/src/ports/status.rs`, `host/herdr_keypad/native/src/ports/control.rs`
- **Verification:** Focused lifecycle/control and status/resource tests pass.
- **Committed in:** `670a88b`

**3. [Rule 1 - Bug] Corrected generated test executable mode**
- **Found during:** Task 2 worktree cleanup
- **Issue:** The test creation tool marked the Rust integration test executable.
- **Fix:** Restored normal source-file mode 0644.
- **Files modified:** `host/herdr_keypad/native/tests/lifecycle_resource.rs`
- **Verification:** Clean worktree after commit.
- **Committed in:** `45e2219`

---

**Total deviations:** 3 auto-fixed (2 Rule 1, 1 Rule 2); no architecture or dependency changes.
**Impact on plan:** All fixes strengthen the planned lifecycle, bounded admission, and privacy contracts without adding a runtime authority or changing shared integration ownership.

## Issues Encountered

- The focused test command initially exposed test-fixture syntax and identity expectation errors; these were corrected in the owned test and implementation before the final focused runs.
- Root module registration and shared integration files were intentionally left to Plan 04-07 as required by the wave ownership contract.
- No formatter, linter, project-wide suite, UAT, firmware build, or physical validation was run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04-07 can register `config`, `control`, `lifecycle`, `status`, and `logging` under `ports` and map the existing Plan 01/core boundaries into `LifecycleOwner` and `StatusSnapshot`.
- Plan 04-07 should route Herdr-provided runtime paths into `RuntimePaths`, map explicit control commands, and preserve read-only status/action separation.
- Repair and re-pair command handling remains an explicit integration seam for Plan 04-07; this plan does not create a second pairing authority.

---
*Phase: 04-production-rust-host-bridge*
*Plan: 06*
*Completed: 2026-08-30*
## Self-Check: PASSED

- All six owned source/test artifacts and this SUMMARY exist.
- Task commits `7a9ba52`, `65f01e1`, `670a88b`, and `45e2219` resolve to committed objects.
- Final focused lifecycle, control, config, status, logging, privacy, and idle-resource checks passed.
- STATE.md and ROADMAP.md were not modified because Plan 04-07 owns shared wave bookkeeping.
