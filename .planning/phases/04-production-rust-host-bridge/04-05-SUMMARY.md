---
phase: 04-production-rust-host-bridge
plan: "05"
subsystem: native-host-bridge
status: complete
tags: [rust, usb, serial, linux, macos, tokio, pairing, fixtures]

# Dependency graph
requires:
  - phase: 04-production-rust-host-bridge
    provides: "Plan 01 bounded native bridge contracts and Plan 02 fixture/privacy conventions"
provides:
  - "Exact paired async CDC session with frozen binding, fresh hello/session fencing, v2 framing, snapshot ACK readiness, and bounded focus intake."
  - "Linux USB descriptor normalization and stable by-id serial opening behind PlatformSerial."
  - "Portable macOS registry normalization, safe permission/error mapping, cu-device opening seam, and process-local suspend notification."
affects: [04-07, 04-09, native-host-bridge, usb-transport]

# Actuals (#2632)
actuals:
  tokens: 16062
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Descriptor facts narrow candidates; frozen binding and fresh application hello authorize one session."
    - "Bounded NDJSON framing reads at most 4096 bytes and clears session/pending focus authority on interruption."
    - "OS-specific serial enumeration/opening stays behind PlatformSerial; macOS registry fixtures are path- and identity-free."

key-files:
  created:
    - host/herdr_keypad/native/src/ports/usb.rs
    - host/herdr_keypad/native/src/platform/linux.rs
    - host/herdr_keypad/native/src/platform/macos.rs
    - host/herdr_keypad/native/tests/usb_platform.rs
    - host/herdr_keypad/native/tests/fixtures/macos-serial.json
  modified: []

key-decisions:
  - "UsbPort owns application hello, sequence, boot/session, ACK readiness, and pending-focus capacity; platform adapters only return normalized descriptors and async byte streams."
  - "Linux accepts only stable /dev/serial/by-id/ endpoints and discovers the composite interface from the kernel sysfs attribute rather than tty enumeration order."
  - "macOS portable registry cases intentionally omit host paths and application identity; target-native Apple Silicon build/execution remains Plan 04-09."
  - "Malformed binding JSON, duplicate keys, unknown fields, wrong schema/protocol, or invalid identities are read-only failures and have no write/migration path."

patterns-established:
  - "PlatformSerial::enumerate() -> Result<Vec<DeviceCandidate>, UsbError>"
  - "PlatformSerial::open(&DeviceCandidate) -> Result<SerialConnection, UsbError>"
  - "UsbPort::new(Box<dyn PlatformSerial>, binding_path), connect(), publish_snapshot(Value), send_focus_result(Value), poll(), close()"
  - "MacRegistryRecord -> normalize_registry_snapshot() -> safe codes exact, wrong_interface, lookalike, ambiguous, permission_denied, disconnected"

requirements-completed: [RUST-02, RUST-03, RUST-04, RUST-08]

# Coverage metadata
coverage:
  - id: D1
    description: "Linux normalization rejects lookalike serials, wrong composite interface, ambiguous/transient endpoints, and preserves the exact measured CDC descriptor tuple."
    requirement: RUST-02
    verification:
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test usb_platform -- --skip macos_"
        status: pass
    human_judgment: false
  - id: D2
    description: "USB session requires the unchanged frozen binding and matching fresh application hello, fences boot/session/sequence, gates readiness on matching snapshot ACK, and clears pending focus on close/reconnect."
    requirement: RUST-04
    verification:
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test usb_platform -- --skip macos_"
        status: pass
    human_judgment: false
  - id: D3
    description: "Portable macOS fixtures cover exact, wrong-interface, lookalike, ambiguous, permission-denied, and disconnect normalized mappings without host paths or application identity."
    requirement: RUST-08
    verification:
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test usb_platform macos_fixture_"
        status: pass
    human_judgment: false

# Metrics
duration: 55 min
completed: 2026-08-30
---

# Phase 04 Plan 05: Exact USB and narrow platform adapters Summary

**Exact paired CDC transport with fresh application/session authority, stable Linux composite discovery, and path-free macOS fixture coverage.**

## Performance

- **Duration:** approximately 55 minutes
- **Started:** 2026-08-30T03:46:00Z (approximate executor start)
- **Completed:** 2026-08-30T04:41:45Z
- **Tasks:** 2/2
- **Files modified:** 5 created

## Accomplishments

- Implemented `UsbPort` with bounded line admission, canonical v1 hello/v2 framing, frozen binding validation, exact descriptor candidate handling, fresh host/device session fencing, sequence checks, snapshot-ACK readiness, bounded pending focus capacity (16), and interruption cleanup. No HID operation is represented.
- Implemented Linux-only normalization of serialport USB metadata plus kernel sysfs interface discovery and stable `/dev/serial/by-id/` opening. Transient tty paths, wrong interfaces, lookalike serials, and ambiguity fail closed before hello authorization.
- Implemented a narrow macOS adapter seam: target-only `/dev/cu.*` enumeration/opening, safe serial error mapping, process-local suspend notification, and registry normalization that can be tested on Linux without claiming Apple Silicon execution.
- Added focused cross-platform tests and committed a normalized macOS fixture containing only descriptor facts and safe outcome codes.

## Task Commits

Each task was committed atomically:

1. **Task 1: Port exact paired CDC session and Linux discovery** - `7a61c25` (`feat`)
2. **Task 2: Implement the macOS adapter with portable fixture coverage** - `fbcf452` (`feat`)

**Plan metadata:** this summary file is the plan metadata commit.

## Files Created/Modified

- `host/herdr_keypad/native/src/ports/usb.rs` - exact paired USB session, framing, ACK/sequence/session gates, focus-intent intake, and binding parser.
- `host/herdr_keypad/native/src/platform/linux.rs` - Linux USB descriptor/sysfs normalization and stable serial open adapter.
- `host/herdr_keypad/native/src/platform/macos.rs` - macOS registry mapping, cu-device serial adapter, permission mapping, and suspend notifier.
- `host/herdr_keypad/native/tests/usb_platform.rs` - focused Linux/USB behavior and portable macOS fixture tests.
- `host/herdr_keypad/native/tests/fixtures/macos-serial.json` - six bounded path-free registry cases.

## Decisions Made

- `UsbPort` is the final application authorization boundary. A candidate must match VID `303a`, PID `1001`, serial `8C:BF:EA:0D:CB:FC`, CDC interface `01`, and a stable endpoint; then the opened stream must acknowledge the frozen binding in a fresh hello. Descriptor/path facts never authorize alone.
- Linux resolves the CDC interface from `/sys/class/tty/<tty>/device/.../bInterfaceNumber`, including by-id symlink resolution, because the pinned serialport API exposes USB VID/PID/serial but not interface number.
- macOS fixture metadata deliberately has no `device` field, host path, account data, credential, firmware, or application identity. Native Apple Silicon compilation and execution are reserved for Plan 04-09.
- `PlatformSerial` is intentionally synchronous at the enumeration/open seam while returning a boxed async `SerialStream`; USB session read/write operations remain async and bounded.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Adapted Linux normalization to the pinned serialport API**
- **Found during:** Task 1 compilation
- **Issue:** `serialport::UsbPortInfo` exposes VID/PID and identity strings but has no interface field.
- **Fix:** Added Linux sysfs interface lookup, resolving stable by-id symlinks to their tty class entry before reading `bInterfaceNumber`; missing or conflicting interface facts remain rejected.
- **Files modified:** `host/herdr_keypad/native/src/platform/linux.rs`
- **Verification:** Scoped Linux USB tests pass.
- **Committed in:** `7a61c25`

**2. [Rule 2 - Missing Critical] Made binding parsing duplicate-key and closed-schema safe**
- **Found during:** Task 1 binding-authority implementation
- **Issue:** Generic serde JSON parsing would otherwise accept duplicate object keys, allowing malformed binding state to be interpreted as a different identity.
- **Fix:** Added a bounded recursive serde visitor that rejects duplicate keys before closed schema and identity validation; no write/migration path was added.
- **Files modified:** `host/herdr_keypad/native/src/ports/usb.rs`
- **Verification:** Scoped USB tests and locked compilation pass.
- **Committed in:** `7a61c25`

**3. [Rule 3 - Blocking] Kept test coverage within owned dependency boundaries**
- **Found during:** Task 1 focused test compilation
- **Issue:** The production manifest is owned by Plan 04-07 and does not include a test-only temporary-directory crate.
- **Fix:** Used a small process-unique standard-library temporary directory helper in the owned integration test rather than editing Cargo manifests or adding a dependency.
- **Files modified:** `host/herdr_keypad/native/tests/usb_platform.rs`
- **Verification:** Scoped Linux and macOS-fixture commands pass.
- **Committed in:** `7a61c25`

---

**Total deviations:** 3 auto-fixed (1 Rule 2, 2 Rule 3)
**Impact on plan:** All changes preserve the requested ownership boundaries and make the exact-device and malformed-state gates stricter; no manifest, root module registry, binding file, udev rule, state, or roadmap file was changed.

## Issues Encountered

- The pinned `serialport` version did not carry the interface field used by the Python discovery analog; Linux sysfs lookup is now the sole source for that missing descriptor fact.
- The first scoped compile exposed only test harness dependency/API mismatches; these were corrected without changing the production dependency graph.
- Target-native Apple Silicon build/test was not run by design; Plan 04-09 owns that release-CI proof.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04-07 can register `ports::usb`, `platform::linux`, and `platform::macos`, then adapt the explicit DTOs/contracts above into coordinator events/effects without moving session or HID authority into the platform layer.
- Plan 04-09 can compile and execute the macOS adapter on its pinned Apple Silicon runner; the portable `macos_fixture_` seam is available now.
- `STATE.md` and `ROADMAP.md` were intentionally not modified in this isolated Wave 2 worktree; the orchestrator owns shared planning-state updates.

---
*Phase: 04-production-rust-host-bridge*
*Plan: 05*
*Completed: 2026-08-30*

## Self-Check: PASSED

- All five planned implementation/test/fixture artifacts and this SUMMARY exist.
- Task commits `7a61c25` and `fbcf452` resolve to committed objects.
- Focused Linux and portable macOS fixture test commands passed.
- Working tree will be clean after removing generated test output and committing this SUMMARY.
