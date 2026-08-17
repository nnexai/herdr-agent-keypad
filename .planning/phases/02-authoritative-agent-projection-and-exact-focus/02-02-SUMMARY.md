---
phase: 02-authoritative-agent-projection-and-exact-focus
plan: 02
subsystem: host-authoritative-projection-and-focus
tags: [herdr, projection, ordering, identity, focus]
requires:
  - phase: 02-authoritative-agent-projection-and-exact-focus
    plan: 01
    provides: "v2 protocol/session seam and exact identity-bound tracer"
provides:
  - "Installed Herdr public socket adapter and source-pinned ordered projection"
  - "Fixed three-position normalized entries with explicit empty and stale/offline states"
  - "Typed focus-only executor with exact identity and generation revalidation"
affects: [02-03, 02-04]
tech-stack:
  added: ["Python standard-library Unix socket Herdr adapter"]
  patterns: ["rank ascending/state_change_seq descending", "fail-closed unavailable projection", "single agent.focus capability"]
key-files:
  created:
    - host/herdr_keypad/src/herdr_keypad/herdr.py
    - host/herdr_keypad/src/herdr_keypad/projection.py
    - host/herdr_keypad/src/herdr_keypad/focus.py
    - host/herdr_keypad/tests/test_projection.py
    - host/herdr_keypad/tests/test_focus.py
  modified:
    - host/herdr_keypad/src/herdr_keypad/bridge.py
decisions:
  - "Use the installed checkout HEAD 78b243279b4da55150b58dc2cc3cffcdc2fd6a04 as the pinned inbox authority; missing rank or identity is unavailable, never guessed."
  - "Keep lifecycle events as invalidation triggers; freeze the last identity as stale/offline until a complete refresh commits."
  - "FocusExecutor performs one agent.list revalidation followed by at most one agent.focus request and never exposes generic Herdr actions."
actuals:
  tokens: 25900
  tasks: 2
  commits: 5
  duration: 1h
  completed: 2026-08-17
status: complete
---

# Phase 2 Plan 2: Host authoritative projection and exact focus Summary

**The host now mirrors the installed inbox's exact order and exposes only a generation-bound, identity-revalidated `agent.focus` capability.**

## Accomplishments

- Added a bounded public Herdr Unix-socket adapter for `session.snapshot`, `agent.list`, `workspace.list`, event subscription, and `agent.focus`; no private plugin state or second transport was introduced.
- Implemented `InboxProjection`: validates the required pane/terminal/workspace/tab/status/focused/revision fields and literal plugin rank tokens, sorts only by `(rank ascending, state_change_seq descending)`, keeps exactly three positions, and appends explicit `NO AGENT` empties.
- Added bounded title/plugin-title/agent-label fallback and workspace/repository discriminator handling without sending raw paths to the device.
- Missing/malformed rank, identity, schema, or plugin revision raises `ProjectionUnavailable`; lifecycle invalidation freezes existing identities as stale/offline/unavailable and disables focus until a complete refresh.
- Implemented `FocusExecutor` as the only action dispatcher. It rejects wrong generation, slot, pane, terminal, workspace/tab, session, and source revision before Herdr I/O; revalidates current `agent.list`; sends only `agent.focus({target: pane_id})`; and accepts success only from a matching focused AgentInfo.
- Added focused projection/focus regressions covering fixed positions, source-array independence, equal-rank recency, null/bounded metadata, stale invalidation, spy-socket allowlisting, vanished/timeout/mismatch outcomes, and no pre-dispatch I/O.

## Verification Evidence

- `PYTHONPATH=host/herdr_keypad/src tools/phase1_bringup/.venv/bin/python -m unittest host.herdr_keypad.tests.test_projection host.herdr_keypad.tests.test_focus host.herdr_keypad.tests.test_protocol` — passed, 14 tests.
- `tools/phase1_bringup/.venv/bin/python tools/phase2_herdr_focus_fixture.py --verify-only --phase1-handoff artifacts/phase2/phase1-handoff.json --output-root artifacts/phase2 --installed-plugin /home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262` — passed; immutable focus-effects and contract artifacts remain baseline-compatible.
- The accepted Phase 1 handoff gate was re-opened with its documented arguments and reports only the already-accepted mutable `.pio` selected-usb binary hash mismatch; no source or contract drift was introduced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed plugin object override retained**
- **Found during:** precondition verification
- **Issue:** The planned plugin object `de409f683262` is unavailable; the active checkout is HEAD `78b243279b4da55150b58dc2cc3cffcdc2fd6a04`.
- **Fix:** All projection authority checks use the actual installed revision already released by Plan 02-00; no fallback revision or priority model was added.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/projection.py`
- **Commit:** `89c1972`

**2. [Rule 1 - Bug] Kept bridge-owned entry IDs bounded**
- **Found during:** final focused host regression
- **Issue:** Combining workspace and pane IDs could exceed the v2 identifier bound even though each source field was individually valid.
- **Fix:** Use the opaque pane ID as the bounded bridge-owned entry ID; workspace and tab remain separate identity fields for revalidation.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/projection.py`
- **Commit:** `b2a29da`

## Auth Gates

None.

## Known Stubs

None. No placeholder data, skipped focused tests, or unrun plan verification remains in the host path.

## Self-Check: PASSED

- Host adapter, projection, focus executor, and both focused test modules exist.
- Task commits `a563ea7`, `89c1972`, `d325789`, and `c09975b` are present.
- Targeted projection, focus, and protocol checks passed.
