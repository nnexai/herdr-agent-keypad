---
phase: 01-physical-keypad-and-proven-transport
plan: 11
subsystem: bringup-evidence
tags: [usb-cdc, esp32-s3, recovery, physical-map, evidence, sha256]
requires:
  - phase: 01-10
    provides: closed protocol schema and host/native parser parity
provides:
  - hardware-random firmware boot identifiers
  - typed fail-closed recovery-action and bounded resume validation
  - canonical physical evidence reopening and source hash binding
  - physical-proof-gap-closure.json
  - historical ineligible recovery-proof-gap-closure.json
  - halted status pending fresh exact-device D-12 action evidence
affects: [phase-01-12, phase-01-13, recovery, physical qualification]
actuals:
  tokens: 27000
  tasks: 3
  commits: 3
tech-stack:
  added: []
  patterns: [hardware RNG boot freshness, closed recovery state, canonical history derivation, reopened source hash linkage]
key-files:
  created:
    - artifacts/phase1/locks/physical-proof-gap-closure.json
    - artifacts/phase1/locks/recovery-proof-gap-closure.json
  modified:
    - firmware/src/main.cpp
    - tools/phase1_bringup/src/phase1_bringup/serial_link.py
    - tools/phase1_bringup/src/phase1_bringup/__main__.py
    - tools/phase1_bringup/src/phase1_bringup/guide.py
    - tools/phase1_bringup/src/phase1_bringup/evidence.py
key-decisions:
  - "Use ESP32 hardware RNG for every boot nonce while retaining the eFuse-derived device_id as a separate stable identity."
  - "Reject forged recovery state, label-only interruption claims, unavailable required rows, and non-canonical physical PASS; preserve historical evidence without upgrading it."
  - "Do not rerun physical or long transport actions; the existing recovery tour is ineligible because it repeats one boot_id and contains endpoint-renumber U evidence."
patterns-established:
  - "Recovery action validation requires action-specific pre/post device, boot, session, endpoint, and discarded-ID facts."
  - "Physical PASS is derived from the complete canonical 30-row history and reopened machine-run manifest/result/checksum hashes."
requirements-completed: []
coverage:
  - id: D1
    description: "Firmware boot IDs use a hardware-random nonce while stable device identity remains unchanged."
    requirement: HARD-03
    verification:
      - kind: integration
        ref: "pio run -e selected-usb"
        status: pass
    human_judgment: false
  - id: D2
    description: "Physical proof lock reopens canonical machine source and validates immutable 30-row evidence."
    requirement: HARD-01
    verification:
      - kind: integration
        ref: "phase1_bringup verify-evidence artifacts/phase1/locks/physical-proof-gap-closure.json --require physical-map --require canonical-history --require reopened-machine-source"
        status: pass
    human_judgment: false
  - id: D3
    description: "A strict recovery proof lock could not be issued from the existing historical tour without new exact-device observations."
    requirement: HARD-01
    verification: []
    human_judgment: true
    rationale: "Existing authoritative tour evidence repeats boot_id 0000fccb0deabf8c-2365 across reset, flash/reset, port move, and utility restart; endpoint-renumber is U; same-port and reset-unplug action facts are absent."
duration: 35min
completed: 2026-08-17
status: halted
---

# Phase 1 Plan 11: Recovery and physical proof gap closure Summary

**Fail-closed recovery and canonical physical evidence hardening is implemented; the historical recovery tour remains explicitly ineligible until fresh action-specific D-12 observations exist.**

## Performance

- **Tasks:** 3 implementation areas completed in code; plan halted at the recovery-proof eligibility gate.
- **Files modified:** 7 plan-owned source/artifact files plus this summary.
- **Human actions:** none repeated; no long qualification or physical tour was run.

## Accomplishments

- Firmware boot IDs now combine the stable eFuse identity with an ESP32 hardware-random nonce generated before session setup.
- Recovery action facts have a closed vocabulary and typed validation for boot/session/device/endpoint transitions and discarded uncertain IDs. Resume IDs are bounded, state schema is closed, and progress is derived from reopened artifacts rather than a trusted cursor.
- Physical evidence validators require the canonical 30-row order, derive PASS from rows/history, reject incomplete or ACK-only PASS, reopen the machine source, and bind manifest/result/checksum hashes. The physical proof lock verifies successfully.
- Required focused self-checks and the selected-usb build passed.

## Task Commits

1. **Recovery and physical validator implementation** - `7ee01d2`
2. **Historical recovery proof lock** - `c2287ec`
3. **Reopened canonical physical proof lock** - `8746ad0`

## Verification Evidence

- `phase1_bringup self-check --serial-reconnect --recovery-action-matrix --udev-rule host/udev/99-herdr-keypad.rules` — passed.
- `phase1_bringup self-check --evidence-schema --physical-confirmation --physical-confirmation-adversarial --board-readiness` — passed.
- `phase1_bringup self-check --recovery-resume-integrity --recovery-required-no-unavailable` — passed.
- `phase1_bringup verify-evidence artifacts/phase1/locks/physical-proof-gap-closure.json --require physical-map --require canonical-history --require reopened-machine-source` — passed.
- `tools/phase1_bringup/.venv/bin/pio run -e selected-usb` — passed; firmware image built, not flashed.

## Recovery Proof Blocker

The existing authoritative tour at `artifacts/phase1/recovery-tours/tour-20260816T140523Z-9c33d6/` is preserved in `recovery-proof-gap-closure.json` as historical/non-eligible evidence. It cannot satisfy the new strict lock because:

- `boot_id` is identical (`0000fccb0deabf8c-2365`) for reset, normal-flash-reset, port-move, and utility-restart rows.
- Endpoint-renumber is an explicit `U`/unavailable result.
- No action-specific pre/post boot/session/endpoint facts exist.
- Same-port reconnect, forced endpoint renumber, and reset-unplug are not each independently evidenced with typed transitions.

The validator rejects these facts rather than upgrading them. A qualifying recovery lock requires fresh exact-device observations after flashing the RNG-enabled firmware; this is the one intentionally unrun human-owned gate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Closed evidence checksum coverage**
- **Found during:** physical evidence hardening
- **Issue:** Extra evidence files were not covered by SHA256SUMS and source evidence was not reopened.
- **Fix:** Checksum every declared evidence file and reopen the source machine manifest/result/checksum set before PASS.
- **Verification:** physical confirmation adversarial self-check and physical lock verification passed.
- **Committed in:** `7ee01d2`

**2. [Rule 1 - Bug] Terminal N confirmation semantics**
- **Found during:** physical confirmation hardening
- **Issue:** A failed observation could immediately be followed by Y without explicit fresh restimulation.
- **Fix:** N is terminal; only a typed R clears the failure and requires a new stimulus.
- **Verification:** focused physical confirmation checks passed.
- **Committed in:** `7ee01d2`

## Known Stubs

None. The recovery lock is intentionally marked `status: incomplete` and `eligible: false`, not treated as a qualifying proof.

## Next Phase Readiness

Physical evidence is ready and verified by `physical-proof-gap-closure.json`. Recovery qualification remains blocked until a future operator-owned run records all seven required action-specific transitions with fresh boot/session semantics; no existing historical row should be relabeled or reused.

---
*Phase: 01-physical-keypad-and-proven-transport*
*Completed: 2026-08-17*
## Self-Check: PASSED

- Summary file exists at the required path.
- Task commits `7ee01d2`, `c2287ec`, and `8746ad0` are present in git history.
- Physical proof lock verification passed.
- Recovery lock is explicitly ineligible; no false completion is claimed.
