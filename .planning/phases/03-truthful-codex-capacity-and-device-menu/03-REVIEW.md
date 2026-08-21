---
phase: 03-truthful-codex-capacity-and-device-menu
reviewed: 2026-08-21T03:25:42Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - firmware/src/app/agent_projection.cpp
  - firmware/src/app/agent_projection.h
  - firmware/src/main.cpp
  - firmware/src/ui/theme_beacon.cpp
  - firmware/src/ui/theme_common.h
  - firmware/src/ui/theme_instrument.cpp
  - firmware/src/ui/theme_ledger.cpp
  - firmware/src/ui/theme_signal_edge.cpp
  - host/herdr_keypad/src/herdr_keypad/bridge.py
  - host/herdr_keypad/src/herdr_keypad/codex.py
  - host/herdr_keypad/src/herdr_keypad/__main__.py
  - host/herdr_keypad/src/herdr_keypad/usb.py
  - host/herdr_keypad/tests/test_codex.py
  - host/herdr_keypad/tests/test_integration.py
  - test/test_agent_projection/test_main.cpp
  - tools/phase1_bringup/src/phase1_bringup/phase3_smoke.py
  - tools/phase1_bringup/src/phase1_bringup/protocol.py
  - tools/phase1_bringup/test_phase3_smoke.py
  - host/herdr_keypad/scripts/ensure-bridge.sh
findings:
  critical: 0
  warning: 1
  info: 1
  total: 2
status: issues_found
verdict: ISSUES — non-blocking Phase 03.1 polish deferred
---

# Phase 03: Code Review Report

**Reviewed:** 2026-08-21T03:25:42Z  
**Depth:** standard, with focused cross-file re-review of applied fixes  
**Files Reviewed:** 19  
**Verdict:** **ISSUES — non-blocking Phase 03.1 polish deferred**

## Summary

The re-review confirmed the applied corrections for the prior two blockers, evidence-finalization warning, and CLI duplicate-import info finding:

- `codex.py` now rejects explicit rate-limit windows whose duration is neither 300 nor 10,080 minutes; the normalizer reports the closed unavailable view rather than falsely labelling the value 5H or WEEK. `test_codex.py:174-190` covers unsupported 60/1,440-minute and conflicting-duration inputs.
- `PermanentBridge.run()` now encloses initial bootstrap in its recovery boundary and fences/schedules retry for transport/bootstrap failures, while preserving terminal behavior for contract drift. `test_integration.py:578-598` covers an initially unavailable USB endpoint recovering to an acknowledged publication.
- Evidence finalization now rejects boolean/negative snapshot revisions and empty boot/session identities at finalization and strict revalidation. `test_phase3_smoke.py:148-169` covers those malformed receipt cases.
- The duplicate CLI imports/constants were removed from `__main__.py`.

No remaining **BLOCKER** or security finding is actionable for the completed exact binary. The two findings retained below are explicitly deferred because changing firmware would invalidate the completed exact-device binary/evidence package; they are Phase 03.1 polish work, not a Phase 03 ship blocker.

## Warnings

### WR-01 [DEFERRED TO PHASE 03.1]: Signal Edge renders a permitted discriminator without width bounding

**File:** `firmware/src/ui/theme_signal_edge.cpp:168-171`  
**Contract source:** `firmware/src/app/agent_projection.h:124-129`; `firmware/src/app/agent_projection.cpp:431-434`

**Issue:** The projection accepts a printable discriminator of up to 32 characters (`Tile::discriminator[33]`), but Signal Edge sends it directly to `drawString()` at x=15. At the shared 6-pixel glyph-cell geometry, a 32-character accepted value needs 192 pixels and is clipped beyond the 128-pixel panel. The other theme renderers ellipsize comparable fields. This can hide the identifying context for a live agent despite the input being protocol-valid.

**Deferral rationale:** Correcting firmware would change the accepted exact binary and invalidate the completed physical-evidence package. Carry this as a Phase 03.1 renderer-polish task.

**Fix:** Copy through `ellipsize()` into a local row sized for the available width before drawing, and add a native rendering assertion for a 32-character discriminator in Signal Edge.

```cpp
char discriminator[19] = {};
ellipsize(discriminator, sizeof(discriminator), tile.discriminator);
sprite.drawString(discriminator, 15, 32);
```

## Info

### IN-02 [DEFERRED TO PHASE 03.1]: Obsolete panel-gauge helper is retained without a call site

**File:** `firmware/src/ui/theme_instrument.cpp:138-149`

**Issue:** `drawUsageGauge()` is not called by the Instrument theme. Panel 4 uses the shared `drawCodexRowsText()`/`drawCodexTrack()` path at lines 238-246, making this helper dead code with a separate stale gauge vocabulary.

**Deferral rationale:** Removing firmware code would change the exact accepted binary and invalidate Phase 03's completed physical evidence. Clean it up with the next firmware-evidence cycle in Phase 03.1.

**Fix:** Delete `drawUsageGauge()` rather than retain an unused rendering path.

## Resolved Findings

- **CR-01 — Resolved:** `host/herdr_keypad/src/herdr_keypad/codex.py:193-205` now rejects unsupported explicit durations; corresponding normalization tests are present at `host/herdr_keypad/tests/test_codex.py:174-190`.
- **CR-02 — Resolved:** `host/herdr_keypad/src/herdr_keypad/bridge.py:1077-1100` now routes initial bootstrap transport failures into reconnect fencing; coverage is present at `host/herdr_keypad/tests/test_integration.py:578-598`.
- **WR-02 — Resolved:** `tools/phase1_bringup/src/phase1_bringup/phase3_smoke.py:140-145,705-711,848-863` validates positive non-boolean revisions and non-empty publication identities; malformed-receipt coverage is present at `tools/phase1_bringup/test_phase3_smoke.py:148-169`.
- **IN-01 — Resolved:** duplicate imports and duplicated `ROOT`/`DEFAULT_BINDING` declarations were removed from `host/herdr_keypad/src/herdr_keypad/__main__.py`.

---

_Re-reviewed: 2026-08-21T03:25:42Z_  
_Reviewer: gsd-code-reviewer_  
_Depth: standard; validation commands intentionally not run_
