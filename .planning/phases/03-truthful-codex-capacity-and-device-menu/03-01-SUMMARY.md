---
phase: 03-truthful-codex-capacity-and-device-menu
plan: 01
subsystem: testing
tags: [codex, app-server, usb-cdc, exact-pairing, tracer, redaction]

requires:
  - phase: 02.1-reliable-live-synchronization-focus-and-flicker-free-rendering
    provides: PermanentBridge, exact USB session ownership, and focus-safe snapshot publication
provides:
  - Installed Codex app-server collector with bounded handshake, typed outcomes, and redacted bucket manifests
  - Exact fresh USB hello validation against stored device and firmware identity
  - Trap-backed exclusive runner that restores guarded bridge ownership while preserving wrapped status
  - Closed, checksummed installed-outcome tracer with deployment, hello, ACK, timing, child-exit, and redaction facts
affects: [03-02, 03-08, 03-09, Codex capacity, USB acceptance]

actuals:
  tokens: 12374
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - One supervised codex app-server child with bounded JSONL and typed failure classification
    - Exact pairing checks both opaque device identity and stored firmware identity before publication
    - Atomic JSON evidence plus a sibling .json.sha256 sidecar with stable export references

key-files:
  created:
    - host/herdr_keypad/tests/test_codex.py
    - artifacts/phase3/03-CODEX-TRACER.json
    - artifacts/phase3/03-CODEX-TRACER.json.sha256
  modified:
    - host/herdr_keypad/src/herdr_keypad/codex.py
    - host/herdr_keypad/src/herdr_keypad/bridge.py
    - host/herdr_keypad/src/herdr_keypad/__main__.py
    - host/herdr_keypad/src/herdr_keypad/usb.py
    - host/herdr_keypad/tests/test_integration.py
    - host/herdr_keypad/scripts/ensure-bridge.sh

decisions:
  - "Treat the installed app-server request error E-2406 as CODEX OFFLINE because no structured authentication evidence was present."
  - "Treat an explicit null rateLimitsByLimitId map as observed but never selectable; only top-level rateLimits can supply capacity."
  - "Keep framebuffer facts explicitly unavailable in this tracer; the machine-verifiable device fact is the committed snapshot ACK, not an invented pixel claim."

key-decisions:
  - "The uploaded current firmware produced a fresh hello matching the stored exact pair: device 0000fccb0deabf8c, firmware phase1-bringup, protocol 1."
  - "A stale bridge PID was cleared only after bounded /proc and kill checks, then the existing guard reacquired the serial lock."
  - "The exclusive runner must return after verified long-lived guard ownership, not wait for that owner to exit; set -e must not mask wrapped command status."

requirements-completed: [CODEX-01, CODEX-02, CODEX-03, CODEX-04, SYNC-03, SAFE-01]

coverage:
  - id: D1
    description: "Bounded Codex collector classifies success, auth evidence, offline branches, all rate-limit shapes, zero/null values, child exit state, and recursive redaction."
    requirement: CODEX-01
    verification:
      - kind: unit
        ref: "host/herdr_keypad/tests/test_codex.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Exact USB session rejects stale firmware identity and records fresh boot/session identity before the committed snapshot ACK."
    requirement: SAFE-01
    verification:
      - kind: integration
        ref: "host/herdr_keypad/tests/test_integration.py#ExactUsbSessionTests"
        status: pass
      - kind: e2e
        ref: "selected-usb build/upload plus ensure-bridge.sh run-exclusive smoke"
        status: pass
    human_judgment: false
  - id: D3
    description: "Installed tracer artifact is closed, source-labeled, redacted, deployment-bound, and checksum-reopenable."
    requirement: CODEX-04
    verification:
      - kind: unit
        ref: "host/herdr_keypad/tests/test_codex.py#test_closed_installed_artifact_has_stable_exports_and_checksum"
        status: pass
      - kind: other
        ref: "sha256sum -c artifacts/phase3/03-CODEX-TRACER.json.sha256"
        status: pass
    human_judgment: false

# Metrics
duration: 120min
completed: 2026-08-20
status: complete
---

# Phase 03 Plan 01: Truthful Codex capacity tracer summary

**Installed Codex outcome now travels through the existing bridge and exact paired USB path, with bounded classification, fresh firmware identity, committed ACK evidence, and a checksummed secret-free tracer.**

## Performance

- **Duration:** approximately 120 min including bounded hardware recovery and re-upload
- **Started:** 2026-08-20T19:40:00Z
- **Completed:** 2026-08-20T21:28:34Z
- **Tasks:** 3
- **Files modified or created by this plan:** 9 tracked deliverables, plus this summary

## Accomplishments

- Rebuilt and uploaded `selected-usb` through the guarded exclusive runner. The fresh post-upload hello matched the stored binding exactly (`0000fccb0deabf8c`, `phase1-bringup`, protocol 1), and the device returned committed snapshot ACK revision 1.
- Ran the installed Codex app-server path. The live account request returned non-auth evidence-backed failure `E-2406`, so the tracer records `CODEX OFFLINE` with unavailable values rather than inventing quota data.
- Added focused collector and integration coverage for success, auth, timeout/process/JSONL/correlation failures, null versus zero, six map shapes, bounded hashed manifests, recursive redaction, exact firmware pairing, ACK evidence, and closed child-exit state.
- Produced `artifacts/phase3/03-CODEX-TRACER.json` and `artifacts/phase3/03-CODEX-TRACER.json.sha256`; the sidecar reopens successfully and stable references resolve to `/collector/elapsed_ms`, `/collector/child_exit`, and `/redaction/result`.

## Task Commits

1. **Task 1: Extend sole host validator and guarded exclusive runner** - `945ac54`
2. **Task 2: Carry installed Codex outcome to Signal Edge panel 4** - `ccb816c`
3. **Task 3: Seal tracer classification and redaction evidence** - `da216df`
4. **Recovery fix: return after guarded ownership reacquisition** - `34a9767`
5. **Current-firmware ACK refinement: bind tracer to fresh hello and snapshot ACK** - `541d0ae`

The final plan metadata commit is created after STATE/ROADMAP updates below.

## Files Created/Modified

- `host/herdr_keypad/src/herdr_keypad/codex.py` - bounded app-server supervision, typed child lifecycle, top-level-only capacity normalization, explicit-null map presence, and redacted key manifest.
- `host/herdr_keypad/src/herdr_keypad/bridge.py` - closed tracer schema, deployment identity, ACK capture, stable evidence references, atomic JSON and checksum writing.
- `host/herdr_keypad/src/herdr_keypad/__main__.py` - truthful pass/fail result based on the normalized live Codex state and ACK-bound evidence publication.
- `host/herdr_keypad/src/herdr_keypad/usb.py` - exact fresh hello checks for device and stored firmware, plus boot/session evidence.
- `host/herdr_keypad/tests/test_codex.py` - focused collector, shape, lifecycle, redaction, and artifact tests.
- `host/herdr_keypad/tests/test_integration.py` - exact firmware mismatch rejection, hello identity, and exclusive-runner contract coverage.
- `host/herdr_keypad/scripts/ensure-bridge.sh` - bounded cleanup returns after ownership verification and preserves nonzero wrapped status.
- `artifacts/phase3/03-CODEX-TRACER.json` - live installed outcome and current deployment evidence.
- `artifacts/phase3/03-CODEX-TRACER.json.sha256` - checksum for the live tracer.

## Decisions Made

- The live `E-2406` response is `CODEX OFFLINE`, not `AUTH REQUIRED`: the collector only emits auth-required for structured account-null or unauthorized evidence.
- `rateLimitsByLimitId` is manifest-only. Its raw keys never cross the host boundary, and `selected_key` remains null.
- The exact-pair check is now closed over both opaque device identity and firmware identity. A stale hello is rejected before v2 publication.
- The committed snapshot ACK is the machine-verifiable device fact for this tracer. Framebuffer pixel facts remain explicitly unavailable until the later physical capture plans; no visual claim is inferred.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Exclusive cleanup waited forever on the restarted guard**
- **Found during:** Task 2 hardware verification
- **Issue:** Cleanup verified the restarted bridge PID/lock and then waited for that intentionally long-lived process, causing the tracer to hang until its outer timeout and leaving a stale PID file.
- **Fix:** Exit immediately after bounded PID/lock ownership verification while preserving the wrapped status.
- **Files modified:** `host/herdr_keypad/scripts/ensure-bridge.sh`
- **Verification:** bounded `run-exclusive -- sh -c 'exit 0'` returned 0 and ownership was verified through `/proc` and the guard lock.
- **Committed in:** `34a9767`

**2. [Rule 1 - Bug] `set -e` masked a failing wrapped tracer command**
- **Found during:** Task 2 hardware verification
- **Issue:** A Codex-offline smoke returned nonzero, but the EXIT trap ran before `wrapped_status` was assigned and returned 0.
- **Fix:** Disable errexit only around the wrapped command, capture its status, then restore errexit before cleanup.
- **Files modified:** `host/herdr_keypad/scripts/ensure-bridge.sh`
- **Verification:** the current Codex-offline tracer returned status 1 while guard ownership was reacquired.
- **Committed in:** `da216df`

**3. [Rule 1 - Bug] Fresh hello evidence omitted boot/session and did not bind the device ACK**
- **Found during:** Task 3 evidence validation
- **Issue:** The session accepted exact device identity but dropped fresh boot/session fields from the stored hello evidence, and the artifact defaulted to unavailable ACK facts even after a committed snapshot.
- **Fix:** Preserve fresh boot/session identity, enforce stored firmware equality, retain the committed snapshot ACK, and emit truthful tracer failure when live Codex is offline.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/usb.py`, `host/herdr_keypad/src/herdr_keypad/bridge.py`, `host/herdr_keypad/src/herdr_keypad/__main__.py`, `artifacts/phase3/03-CODEX-TRACER.json`
- **Verification:** fresh artifact records boot/session, `device_ack.accepted: true`, revision 1, and checksum passes.
- **Committed in:** `541d0ae`

**4. [Rule 3 - Blocking] Tracer sidecar used a basename that failed the plan command**
- **Found during:** Task 3 checksum verification
- **Issue:** `sha256sum -c artifacts/phase3/03-CODEX-TRACER.json.sha256` could not resolve a basename-only sidecar entry from the repository root.
- **Fix:** Preserve relative evidence paths in the sidecar while keeping absolute temporary test paths bounded.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/bridge.py`, `artifacts/phase3/03-CODEX-TRACER.json.sha256`
- **Verification:** the exact plan checksum command returns `OK`.
- **Committed in:** `541d0ae`

**5. [Rule 3 - Bounded recovery] Recovered a stale guard PID after a timed-out prior run**
- **Found during:** Task 2 hardware verification
- **Issue:** The prior interrupted runner left a PID file pointing to no live process, so `stop-for-acceptance` correctly refused ownership.
- **Fix:** After bounded `kill -0` and `/proc` absence checks, removed only the verified stale PID file, then restarted the existing guard and confirmed its lock FD.
- **Files modified:** runtime-only PID state; no repository source
- **Verification:** guard PID and `/proc/<pid>/fd/9` resolved to `/run/user/1000/herdr-keypad/bridge.lock` before the upload.
- **Committed in:** runtime recovery; no source commit

**Total deviations:** 5 auto-fixed (3 Rule 1, 1 Rule 3, 1 bounded recovery)
**Impact on plan:** All fixes were required to make exact-pair hardware evidence bounded, truthful, and repeatable. No second bridge, codec, parser, or device path was introduced.

## Issues Encountered

- The initially suspected fresh-hello mismatch was not reproduced after the bounded recovery. The fresh current-firmware hello matched the stored device and firmware identity; the actionable fault was stale ownership plus incomplete evidence retention.
- The installed Codex app-server produced a bounded non-auth request failure (`E-2406`). This is recorded as a valid truthful `codex_offline` outcome with no quota claims.
- No framebuffer capture was part of this tracer command, so rendered-frame availability is explicitly false rather than inferred from the wire ACK.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 02 can consume the collector's normalized result and preserve the six shape semantics, independent freshness, and source classification.
- Plan 08/09 can consume the deployment identity, fresh hello, ACK, checksum, and stable tracer references for capture and physical acceptance.
- The guard is currently restored as the sole owner of `/run/user/1000/herdr-keypad/bridge.lock`; later direct USB commands must continue to use `run-exclusive`.

---
*Phase: 03-truthful-codex-capacity-and-device-menu*
*Completed: 2026-08-20*

## Self-Check: PASSED

- Summary file exists at the required phase path.
- Prior task commits `945ac54` and `ccb816c`, recovery commit `34a9767`, Task 3 commit `da216df`, and ACK refinement `541d0ae` all exist.
- Final targeted unit/integration suite passed (34 tests).
- `sha256sum -c artifacts/phase3/03-CODEX-TRACER.json.sha256` passed.
