---
phase: 01-physical-keypad-and-proven-transport
plan: 04
subsystem: physical-bringup
tags: [python, usb-cdc, pairing, udev, serial-recovery, immutable-evidence]

# Dependency graph
requires:
  - phase: 01-physical-keypad-and-proven-transport
    provides: 01-03 confirmed delivered-unit physical map, bounded UI, and immutable evidence writer
provides:
  - Exact fresh physical challenge pairing with stable opaque device identity
  - Fail-closed measured USB discovery and ordinary-user serial recovery
  - Operator-run D-12 recovery tour with resumable utility-restart checkpoint
  - Hash-addressed pairing and recovery evidence for the delivered unit
affects: [01-05 protocol semantics, 01-06 USB qualification, 01-08 final archive, Phase 4 recovery]

# Actuals (#2632)
actuals:
  tokens: 9608
  tasks: 2
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns: [application hello identity after descriptor-only discovery, exact challenge atomic binding, bounded serial link with fresh sessions, per-step immutable recovery evidence]

key-files:
  created:
    - tools/phase1_bringup/src/phase1_bringup/discovery.py
    - tools/phase1_bringup/src/phase1_bringup/pairing.py
    - tools/phase1_bringup/src/phase1_bringup/serial_link.py
    - host/udev/99-herdr-keypad.rules
  modified:
    - firmware/src/main.cpp
    - protocol/schema/v1.json
    - tools/phase1_bringup/src/phase1_bringup/protocol.py
    - tools/phase1_bringup/src/phase1_bringup/__main__.py
    - tools/phase1_bringup/src/phase1_bringup/guide.py

decisions:
  - "USB descriptors, serial paths, and by-id paths remain candidate facts only; application hello device_id authorizes the exact binding."
  - "The delivered unit's opaque identity is 0000fccb0deabf8c (displayed as suffix bf8c); full identity remains evidence-only."
  - "A fresh host session is mandatory after every interruption; uncertain IDs are discarded and never replayed."
  - "Endpoint renumbering was explicitly recorded unavailable (U), not inferred or passed."
  - "Full host reboot, suspend/resume, cross-component resynchronization, and Phase 4 recovery remain out of scope."

patterns-established:
  - "Pair only one compatible candidate after exact uppercase six-hex challenge entry and explicit physical confirmation; rejected or ambiguous attempts cannot replace the stored binding."
  - "Recovery opens every measured candidate, handshakes each, selects exactly one stored application identity, closes stale descriptors, and records boot/session/discard transitions."
  - "The D-12 tour presents one action/checkpoint at a time and writes immutable evidence for Y, N, and U outcomes; utility restart uses a printed --resume command."

requirements-completed: [HARD-01, HARD-03]

coverage:
  - id: D1
    description: "Only the keypad displaying the fresh challenge is paired to the stable opaque identity; wrong challenge and ambiguity preserve the prior binding."
    requirement: HARD-01
    verification:
      - kind: other
        ref: "tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --schema protocol/schema/v1.json --discovery --pairing"
        status: pass
      - kind: manual_procedural
        ref: "artifacts/phase1/20260816T134827Z-c913ce pairing evidence; user confirmed PAIR/3167DB"
        status: pass
    human_judgment: true
    rationale: "The keypad display and intended delivered unit require direct human observation; firmware ACKs alone are not physical proof."
  - id: D2
    description: "The exact paired unit recovered as fresh ordinary-user sessions through reset, normal flash/reset, USB port move, and utility restart; endpoint renumbering was explicitly unavailable."
    requirement: HARD-03
    verification:
      - kind: other
        ref: "tools/phase1_bringup/.venv/bin/python -m phase1_bringup self-check --schema protocol/schema/v1.json --serial-reconnect --udev-rule host/udev/99-herdr-keypad.rules"
        status: pass
      - kind: manual_procedural
        ref: "artifacts/phase1/recovery-tours/tour-20260816T140523Z-9c33d6/ step-01..05 SHA256SUMS and verify-evidence checks"
        status: pass
    human_judgment: true
    rationale: "Reset, cable movement, endpoint behavior, and utility restart require the operator's direct physical observation; the endpoint-renumber U record is intentionally not a PASS."

# Metrics
duration: execution-window
completed: 2026-08-16
status: complete
---

# Phase 1 Plan 4: Exact Pairing and Measured Recovery Summary

**The delivered keypad is bound by an exact fresh physical challenge and recovers through an operator-run D-12 tour using ordinary-user, exact-identity fresh sessions with immutable evidence.**

## Performance

- **Duration:** execution window; wall-clock duration was not separately measured
- **Completed:** 2026-08-16
- **Tasks:** 2 plan tasks completed
- **Files modified:** 9 source/policy files, plus immutable runtime evidence

## Accomplishments

- Added application-level hello identity (`device_id`, firmware, protocol) while retaining the closed v1 envelope. Firmware derives the opaque identity from the ESP32 eFuse MAC, so normal reset/flash does not change it.
- Added descriptor-only discovery, fail-closed zero/many/mismatch handling, atomic pairing persistence, exact six-hex challenge validation, and explicit physical confirmation. The user paired the delivered keypad after confirming `PAIR / 3167DB`; hash-verified evidence is preserved at `artifacts/phase1/20260816T134827Z-c913ce`.
- Measured the delivered runtime interface as VID `0x303A`, PID `0x1001`, serial `8C:BF:EA:0D:CB:FC`, interface `00`, with stable by-id path `usb-Espressif_USB_JTAG_serial_debug_unit_8C:BF:EA:0D:CB:FC-if00`. Added a narrow udev rule matching those facts, `dialout`, and `uaccess`; runtime checks remained ordinary-user.
- Added bounded `SerialLink` I/O, stale-descriptor closure, exact stored-identity hello, fresh session IDs, discarded uncertain IDs, and recovery transition evidence. Machine-only utility restart recovery is separately preserved at `artifacts/phase1/20260816T135659Z-cc9459`.
- Added the operator-run `recover-tour` CLI. The user completed its resumable tour: reset, normal flash/reset, port move, endpoint-renumber unavailable (`U`), and utility restart. Step artifacts are under `artifacts/phase1/recovery-tours/tour-20260816T140523Z-9c33d6`; available steps record `physical_pass: true`, ordinary-user runtime, paired suffix `bf8c`, and fresh sessions. Endpoint renumber remains explicitly `status: unavailable`, never a fabricated PASS.

## Task Commits

1. **Task 1: Physically pair one stable opaque keypad identity** - `f209de2`, `a00f568`
2. **Task 2: Prove measured unprivileged recovery as fresh exact-device sessions** - `2d9c14b`, `b0e8853`, `a059ef4`

## Files Created/Modified

- `firmware/src/main.cpp` - stable device identity and hello acknowledgement fields.
- `protocol/schema/v1.json` - closed hello acknowledgement identity contract.
- `tools/phase1_bringup/src/phase1_bringup/discovery.py` - descriptor candidate snapshots and exact identity selection.
- `tools/phase1_bringup/src/phase1_bringup/pairing.py` - challenge validation and atomic binding store.
- `tools/phase1_bringup/src/phase1_bringup/serial_link.py` - bounded serial lifecycle and fresh-session recovery.
- `tools/phase1_bringup/src/phase1_bringup/evidence.py` - immutable recovery transition validation and `--require recovery` verification.
- `tools/phase1_bringup/src/phase1_bringup/guide.py` - pairing copy and D-12 tour steps/checkpoints.
- `tools/phase1_bringup/src/phase1_bringup/__main__.py` - `pair`, `recover`, `recover-tour`, and focused self-check surfaces.
- `host/udev/99-herdr-keypad.rules` - measured narrow ordinary-user policy.

## Decisions Made

- Descriptor equality and transient device paths are discovery aids only. The stored trust identity is the application hello `device_id` confirmed by a physical challenge.
- A binding is written only after one candidate, exact challenge text, compatible hello, and explicit human confirmation. Mismatch, ambiguity, incompatible protocol, or no confirmation leaves the old binding unchanged.
- Recovery is always a new session. The tour records discarded IDs and does not replay uncertain in-flight work.
- The endpoint-renumber case had no second ACM candidate available and is recorded `U`/unavailable. This is truthful partial coverage, not a transport PASS.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added identity fields to the hello acknowledgement contract**
- **Found during:** Task 1
- **Issue:** The existing hello acknowledgement exposed no application device identity, making exact pairing impossible and leaving descriptor data as the only candidate discriminator.
- **Fix:** Added stable firmware `device_id` and firmware fields, updated the closed protocol/schema, and made `ProtocolSession.hello()` retain device and boot/session facts.
- **Files modified:** `firmware/src/main.cpp`, `protocol/schema/v1.json`, `tools/phase1_bringup/src/phase1_bringup/protocol.py`
- **Verification:** Protocol self-check and root `pio run` passed.
- **Committed in:** `f209de2`

**2. [Rule 1 - Bug] Restored the firmware payload binding and protocol receive bookkeeping after identity edits**
- **Found during:** Task 1 firmware build
- **Issue:** An edit temporarily dropped the local probe payload declaration; a later protocol edit temporarily dropped receive sequence bookkeeping.
- **Fix:** Restored both declarations/updates before committing the corrected implementation.
- **Files modified:** `firmware/src/main.cpp`, `tools/phase1_bringup/src/phase1_bringup/protocol.py`
- **Verification:** Root `tools/phase1_bringup/.venv/bin/pio run` passed; serial self-check passed.
- **Committed in:** `f209de2`

**3. [Rule 3 - Blocking] Added an operator-run tour after the initial interactive process was rejected**
- **Found during:** Task 2 human verification
- **Issue:** A hub-managed interactive recovery process did not meet the user's requirement that the operator run the tour from their own terminal.
- **Fix:** Added `recover-tour` with one-step Y/N/R/U prompts, immutable per-step evidence, and a resumable utility-restart checkpoint.
- **Files modified:** `tools/phase1_bringup/src/phase1_bringup/__main__.py`, `tools/phase1_bringup/src/phase1_bringup/guide.py`
- **Verification:** Focused self-check, compile, CLI help, and the user's completed tour artifacts passed.
- **Committed in:** `a059ef4`

### Environment Deviation

**4. Exact Python 3.11 remains unavailable**
- **Found during:** focused environment verification
- **Handling:** All checks used `tools/phase1_bringup/.venv/bin/python` 3.14.7, which satisfies the declared `>=3.11` floor; no exact 3.11 claim is made.
- **Impact:** No source or evidence scope change; exact 3.11 reproducibility remains an environment concern.

**Total deviations:** 3 auto-fixed issues plus 1 documented environment deviation.
**Impact on plan:** All source deviations were required for exact identity, correctness, or the requested operator-owned physical gate. No later plan was started and no historical artifact was overwritten.

## Issues Encountered

- `pio run -d firmware` was not a valid build invocation because the PlatformIO manifest is at the repository root; the corrected root `pio run` passed.
- Endpoint renumbering had no available second ACM device. The tour recorded `U` and preserved that limitation explicitly.
- The user-confirmed physical reset evidence remains distinct from the earlier machine-only reset artifact `artifacts/phase1/20260816T135728Z-99648`.

## User Setup Required

One administrator installation is required if the host does not already carry the measured rule:

```text
sudo install -m 0644 host/udev/99-herdr-keypad.rules /etc/udev/rules.d/99-herdr-keypad.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
```

Runtime and all recovery-tour invocations must remain ordinary-user; never run the bridge with sudo.

## Next Phase Readiness

- HARD-01 and HARD-03 pairing/recovery implementation and available D-12 physical evidence are complete for the delivered unit.
- Endpoint renumbering remains an explicitly unavailable evidence row and must not be described as passed.
- Full host reboot, suspend/resume, cross-component product resynchronization, and Phase 4 recovery remain deferred.
- Preserve the pairing artifact, all five tour step directories, the distinct machine-only reset artifact, and prior Plan 01-03 artifacts for Plan 01-08 archival.

---
*Phase: 01-physical-keypad-and-proven-transport*
*Completed: 2026-08-16*

## Self-Check: PASSED

- Summary exists with required frontmatter, coverage, deviations, exact Python 3.11 deviation, and explicit endpoint-unavailable boundary.
- Focused compile, pairing/discovery/recovery/udev self-checks, firmware build, pairing evidence, and all five tour evidence verifications passed.
- SHA-256 manifests passed for all five tour step directories.
- No later plan was started and no historical artifact was rewritten.
