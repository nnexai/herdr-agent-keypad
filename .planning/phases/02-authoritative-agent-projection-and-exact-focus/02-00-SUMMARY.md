---
phase: 02-authoritative-agent-projection-and-exact-focus
plan: 00
subsystem: evidence-and-integration-gates
tags: [herdr, focus, usb, evidence, phase1-handoff]

requires:
  - phase: 01-physical-keypad-and-proven-transport
    provides: "Completed selected-USB, final-build, archive, paired-device, and firmware/UI contract evidence"
provides:
  - "Hash-bound Phase 1 to Phase 2 handoff receipt"
  - "Disposable installed-Herdr focus/effects evidence for all mandatory lifecycle rows"
  - "Baseline-compatible Herdr acknowledgement and focus-only ownership contract"
affects: [02-01, 02-02, 02-03, 02-04]

actuals:
  tokens: 14300
  tasks: 3
  commits: 3

tech-stack:
  added: [Python standard library subprocess/JSON evidence runners]
  patterns: [fail-closed immutable artifact verification, disposable public-API fixture, exact opaque identity capture]

key-files:
  created:
    - tools/phase2_handoff_gate.py
    - tools/phase2_herdr_focus_fixture.py
    - artifacts/phase2/phase1-handoff.json
    - artifacts/phase2/herdr-contract.json
    - artifacts/phase2/herdr-focus-effects.json
  modified:
    - .planning/phases/02-authoritative-agent-projection-and-exact-focus/02-00-PLAN.md

key-decisions:
  - "Use selected-usb only and bind the receipt to the final Phase 1 source, UI, archive, and paired-device hashes."
  - "The installed inbox source directory remains the local path ending in de409f683262, but its authoritative checkout revision is 78b243279b4da55150b58dc2cc3cffcdc2fd6a04 because the planned de409f object is unavailable."
  - "Release the observed artifacts as baseline-compatible: Herdr acknowledges AgentInfo identity fields; host epoch and snapshot revision remain bridge-owned correlation fields."

patterns-established:
  - "Every focus observation captures before/request/response/events/immediate/delayed identity and ordering data."
  - "Disposable fixture workspaces are closed and original focus is restored before evidence is accepted."

requirements-completed: [INBX-01, INBX-03, FOCS-01, FOCS-03, FOCS-04, SAFE-02]

coverage:
  - id: D1
    description: "Phase 1 selected-USB handoff is reopened and hash-bound before Phase 2 work."
    requirement: SAFE-02
    verification:
      - kind: integration
        ref: "tools/phase2_handoff_gate.py --verify-only"
        status: pass
    human_judgment: false
  - id: D2
    description: "Installed Herdr focus/effects matrix contains all eight lifecycle and identity rows."
    requirement: INBX-03
    verification:
      - kind: integration
        ref: "tools/phase2_herdr_focus_fixture.py --verify-only"
        status: pass
    human_judgment: false
  - id: D3
    description: "Herdr-versus-bridge acknowledgement ownership and focus-only allowlist are explicit."
    requirement: FOCS-03
    verification:
      - kind: integration
        ref: "artifacts/phase2/herdr-contract.json classification=baseline-compatible"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-08-17
status: complete
---

# Phase 2 Plan 00: Authoritative agent projection and exact focus Summary

**Baseline-compatible installed-Herdr focus evidence and hash-bound Phase 1 release gate, pinned to actual checkout HEAD 78b243279b4da55150b58dc2cc3cffcdc2fd6a04**

## Performance

- **Duration:** 25 min
- **Started:** 2026-08-17T07:00:00Z
- **Completed:** 2026-08-17
- **Tasks:** 3 (including the approved baseline decision)
- **Files modified:** 6 deliverable/plan files

## Accomplishments

- Added a fail-closed artifact-only handoff verifier that reopens selected-USB, final-build, archive, paired-binding, and final runtime/UI contracts without rebuilding, flashing, or opening a transport.
- Captured a disposable Herdr workspace through the public CLI/API surface across working, idle/clear, blocked, finished/unseen, manual-unread, settled, vanished, and reassigned rows. Finished/unseen and settled native changes are recorded as observations, with no compensating triage action.
- Recorded Herdr 0.8.0 protocol 19/schema 1, actual inbox checkout HEAD `78b243279b4da55150b58dc2cc3cffcdc2fd6a04`, opaque pane/terminal/session/revision observations, Herdr-owned acknowledgement fields, bridge-owned epoch/revision fields, and cleanup proof.

## Task Commits

1. **Task 1: Execute the Phase 1 completion and final-contract handoff gate** - `423729b` (feat)
2. **Task 2: Capture the complete installed-Herdr focus and identity matrix** - `03831d5` (feat)
3. **Task 3: Release the observed identity and focus contract** - approved from machine-verified `baseline-compatible` artifacts; no separate source commit

## Files Created/Modified

- `tools/phase2_handoff_gate.py` - reopens immutable Phase 1 evidence, rejects mutable/symlinked inputs, and records exact contract hashes.
- `tools/phase2_herdr_focus_fixture.py` - isolated public-API fixture with cleanup and before/after lifecycle observations.
- `artifacts/phase2/phase1-handoff.json` - cross-phase receipt including redacted device fingerprint and actual Herdr revision override.
- `artifacts/phase2/herdr-contract.json` - active schema, ordering, acknowledgement ownership, and focus-only allowlist.
- `artifacts/phase2/herdr-focus-effects.json` - complete eight-row identity/order/effects matrix and cleanup proof.
- `.planning/phases/02-authoritative-agent-projection-and-exact-focus/02-00-PLAN.md` - records the unavailable planned object and authoritative actual revision.

## Decisions Made

- The planned `de409f683262` Git object is unavailable. The installed source directory at `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262` is retained as the source path, while its verified Git HEAD `78b243279b4da55150b58dc2cc3cffcdc2fd6a04` is the only accepted plugin revision.
- `agent.focus` is the only device-releasable Herdr action. Native seen/unread/order effects are documented, not compensated by settle, unread, or clear calls.
- Herdr's matching `AgentInfo` identity acknowledgement is distinct from bridge-owned `host_epoch` and `snapshot_revision`; neither host field is claimed as Herdr-owned.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reordered disposable pane creation for the reassigned race**
- **Found during:** Task 2
- **Issue:** Closing the original pane before creating the replacement made the public split command target a nonexistent pane.
- **Fix:** Created the replacement pane first, then closed the original for the vanished observation and focused the replacement separately.
- **Files modified:** `tools/phase2_herdr_focus_fixture.py`
- **Verification:** Full fixture generation and verify-only commands passed; cleanup proof reports no disposable pane remains.
- **Committed in:** `03831d5`

**2. [Rule 3 - Blocking] Resolved unavailable planned plugin object without weakening the contract**
- **Found during:** Task 1
- **Issue:** The plan's `de409f683262` object is absent while the installed checkout is at a different authoritative HEAD.
- **Fix:** Pinned and verified the exact installed HEAD `78b243279b4da55150b58dc2cc3cffcdc2fd6a04`, retained the source path, and recorded the explicit override in all Phase 2 evidence.
- **Files modified:** `tools/phase2_handoff_gate.py`, `artifacts/phase2/phase1-handoff.json`, `02-00-PLAN.md`
- **Verification:** Handoff generation and verify-only commands pass; fixture checks the same revision before mutation.
- **Committed in:** `423729b` plus the plan metadata commit.

---

**Total deviations:** 2 auto-fixed (Rule 3: 2)
**Impact on plan:** Both changes preserve the fail-closed identity, focus-only, and authority contracts; no later Phase 2 plan was executed.

## Issues Encountered

- The fixture initially attempted to split a pane after closing it; this was corrected by creating the replacement before the close race. No user panes or records were changed.
- The installed source directory name retains the unavailable planned suffix by filesystem history; evidence records both that path and the actual verified Git HEAD to prevent ambiguity.

## Verification Evidence

- `PYTHONPATH=tools/phase1_bringup/src tools/phase1_bringup/.venv/bin/python tools/phase2_handoff_gate.py ...` — wrote and verified the handoff receipt.
- The same command with `--verify-only` — passed.
- Missing-summary negative check — rejected the gate with `Phase 1 Plan 01-13 summary must be a concrete regular file`.
- `PYTHONPATH=host/herdr_keypad/src tools/phase1_bringup/.venv/bin/python tools/phase2_herdr_focus_fixture.py ...` — captured and verified all eight rows.
- Fixture `--verify-only` — passed.
- Live probes confirmed Herdr `0.8.0`, private socket mode `0600`, and plugin HEAD `78b243279b4da55150b58dc2cc3cffcdc2fd6a04`.

## Next Phase Readiness

- Plan 02-01 may proceed only from these immutable, baseline-compatible artifacts and the pinned actual Herdr revision.
- Exact opaque pane identity, terminal identity, optional session identity, record revision, host epoch/revision correlation, and focus-only allowlisting remain mandatory.
- No later plan was executed in this Wave 0 assignment.

## Self-Check: PASSED

- All six summary/deliverable files exist.
- Task commits `423729b` and `03831d5` are present in Git history.

---
*Phase: 02-authoritative-agent-projection-and-exact-focus*
*Completed: 2026-08-17*