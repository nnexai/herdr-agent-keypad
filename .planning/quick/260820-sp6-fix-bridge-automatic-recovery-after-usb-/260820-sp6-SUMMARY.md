---
phase: 260820-sp6
plan: 260820-sp6
subsystem: host-bridge
tags: [usb-cdc, reconnect, herdr, focus, snapshot-ack, tdd]
requires:
  - phase: Phase 1 bring-up
    provides: exact paired UsbDeviceSession.connect() and reconnect_exact() seam
provides:
  - bounded automatic PermanentBridge recovery after USB CDC disconnect/re-enumeration
  - fail-closed cross-session focus fencing and authoritative snapshot-ACK readiness
  - deterministic reconnect, identity, event-stream, and recovery regression coverage
affects: [host bridge runtime, USB recovery, focus semantics]
tech-stack:
  added: []
  patterns:
    - monotonic one-attempt reconnect schedule with capped exponential backoff
    - shared bootstrap/recovery Herdr subscription and focus-executor construction
key-files:
  created: []
  modified:
    - host/herdr_keypad/src/herdr_keypad/bridge.py
    - host/herdr_keypad/tests/test_integration.py
decisions:
  - Preserve the host epoch and snapshot revision across transport loss when authoritative content is unchanged.
  - Reuse UsbDeviceSession.connect() unchanged so PairingStore/reconnect_exact/application hello enforce exact identity.
  - Keep readiness and focus fenced until a complete three-slot snapshot receives an exact ACK.
requirements-completed: []
coverage:
  - id: D1
    description: Live bridge reconnects with capped backoff, exact identity, rebuilt Herdr authority, and complete snapshot ACK before readiness.
    verification:
      - kind: integration
        ref: host.herdr_keypad.tests.test_integration.PluginLifecycleTests.test_alive_bridge_reconnects_and_acks_complete_snapshot_before_ready
        status: pass
      - kind: integration
        ref: host.herdr_keypad.tests.test_integration.PluginLifecycleTests.test_usb_reconnect_backoff_is_single_attempt_and_capped
        status: pass
      - kind: integration
        ref: host.herdr_keypad.tests.test_integration.PluginLifecycleTests.test_recovery_rebuilds_event_stream_and_discards_old_focus_intake
        status: pass
      - kind: integration
        ref: host.herdr_keypad.tests.test_integration.ExactUsbSessionTests.test_reenumerated_usb_keeps_exact_stored_device_identity
        status: pass
    human_judgment: false
  - id: D2
    description: Actual paired keypad survives a physical Espressif CDC reset without bridge restart.
    verification: []
    human_judgment: true
    rationale: Physical reset/re-enumeration and post-recovery keypress require the orchestrator's live-device check; no bridge restart or user input was automated here.
metrics:
  duration: not tracked
  completed: 2026-08-20
  status: complete
---

# Quick Task 260820-sp6 Summary

**PermanentBridge now recovers the exact paired USB session with bounded backoff, rebuilds Herdr/event-stream authority, and gates focus on an acknowledged complete snapshot.**

## Accomplishments

- Added deterministic RED regressions for the missing reconnect path; the pre-change focused run failed specifically because a disconnected live bridge never attempted reconnect.
- Implemented one-at-a-time monotonic reconnect scheduling with explicit 0.5-second initial and 8-second maximum delays, resetting only after acknowledged recovery.
- Reused `UsbDeviceSession.connect()` unchanged for every retry, preserving `PairingStore`/`reconnect_exact()` and fresh application-hello identity checks.
- Shared initial bootstrap and recovery runtime construction, closed/rebuilt Herdr event streams, preserved host epoch and unchanged snapshot revision, and forced publication of all three slots before exact ACK readiness.
- Fenced old USB pending focus, deferred intents, and in-flight result delivery across session generations.

## Verification

Focused RED evidence before production edits:

```text
3 focused tests (2 reconnect tests): FAIL
- alive bridge remained connected after simulated stale descriptor
- reconnect attempt count remained unchanged at the first due deadline
- exact identity regression passed
```

Focused GREEN verification:

```text
PYTHONPATH=host/herdr_keypad/src:tools/phase1_bringup/src tools/phase1_bringup/.venv/bin/python -m unittest \
  host.herdr_keypad.tests.test_integration.PluginLifecycleTests.test_alive_bridge_reconnects_and_acks_complete_snapshot_before_ready \
  host.herdr_keypad.tests.test_integration.PluginLifecycleTests.test_recovery_rebuilds_event_stream_and_discards_old_focus_intake \
  host.herdr_keypad.tests.test_integration.PluginLifecycleTests.test_usb_reconnect_backoff_is_single_attempt_and_capped \
  host.herdr_keypad.tests.test_integration.ExactUsbSessionTests.test_reenumerated_usb_keeps_exact_stored_device_identity -v

Ran 4 tests in 0.012s
OK
```

Relevant host lifecycle verification:

```text
PYTHONPATH=host/herdr_keypad/src:tools/phase1_bringup/src tools/phase1_bringup/.venv/bin/python -m unittest \
  host.herdr_keypad.tests.test_integration.PluginLifecycleTests \
  host.herdr_keypad.tests.test_integration.ExactUsbSessionTests \
  host.herdr_keypad.tests.test_integration.HerdrEventContractTests -v

Ran 20 tests in 0.040s
OK
```

Task 3 reachable, read-only prerequisite checks:

```text
binding=present
pidfile=present
bridge_pid_alive=yes
herdr_socket=present
```

The live CDC reset/re-enumeration, unchanged bridge PID confirmation after the reset, and one physical post-recovery focus remain for the orchestrator's actual-device check. The bridge was not restarted or stopped as a substitute.

Live same-process transport-loss smoke after loading `db5c880`:

```text
bridge PID before descriptor invalidation: 526560
bridge PID after bounded recovery:          526560
recovered serial endpoint:                  /dev/ttyACM0 (fd 3)
```

The live bridge's serial descriptor was closed externally while the process was paused, then the same process was resumed. It detected the stale descriptor, fenced the session, and reacquired `/dev/ttyACM0` within the bounded recovery window. This exercises the production error/reconnect path without rebooting the keypad or restarting the supervisor. A kernel-level CDC remove/add was not forced because USB reset and driver unbind require elevated host privileges.

## Commit

- `db5c880` — `fix(260820-sp6): recover bridge after USB CDC disconnect`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserve unchanged projection generations across USB transport loss**
- **Found during:** Task 2 recovery implementation
- **Issue:** Invalidating the projection on transport loss changed the snapshot revision and prevented a materially unchanged authoritative projection from being republished at its original revision.
- **Fix:** Added a transport-only readiness/focus/event-stream fence that closes USB state without invalidating the authoritative projection; recovery still forces a fresh complete publication and exact ACK.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/bridge.py`, `host/herdr_keypad/tests/test_integration.py`
- **Verification:** Recovery regression asserts the host epoch and snapshot revision remain stable while the complete three-slot publication is ACKed.
- **Committed in:** `db5c880`

**2. [Rule 1 - Bug] Rebuild authoritative projection after an unavailable recovery snapshot**
- **Found during:** Task 2 recovery implementation
- **Issue:** `InboxProjection` can retain an offline snapshot while its prior projection key remains current, causing a retry with unchanged rows to return offline state.
- **Fix:** Clear only the projection's committed current snapshot before recovery bootstrap when it is not current, allowing the shared authoritative bootstrap to commit the restored current generation.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/bridge.py`
- **Verification:** Focused and 19-test relevant host suites pass, including recovery readiness.
- **Committed in:** `db5c880`

**Total deviations:** 2 auto-fixed (Rule 1)
**Impact on plan:** Both fixes are required for correct fail-closed recovery and remained within the existing bridge/projection/session seams; no dependency, transport abstraction, firmware, ROADMAP, or STATE changes were made.

## Issues Encountered

- No project-wide formatter, linter, firmware build, or unrelated test suite was run, per scope.
- Physical CDC reset verification requires the paired keypad and remains explicitly delegated to the orchestrator.

## Self-Check: PASSED

- Source/test commit `db5c880` exists.
- Both modified source files are present.
- Quick summary exists at the contracted path.
- `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified by this task.
