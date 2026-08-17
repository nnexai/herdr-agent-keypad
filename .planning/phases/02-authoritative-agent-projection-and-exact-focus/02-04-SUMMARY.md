---
phase: 02-authoritative-agent-projection-and-exact-focus
plan: 04
subsystem: herdr-plugin-usb-integration
status: halted
tags: [herdr, plugin, usb, bridge, focus, acceptance]
requires:
  - phase: 02-authoritative-agent-projection-and-exact-focus
    provides: "Hash-bound Phase 1 selected-USB handoff, public Herdr contract, normalized projection, exact focus executor, and firmware v2 renderer"
provides:
  - "Startup-only herdr-keypad plugin manifest and one flock-guarded bridge process"
  - "Exact paired selected-USB runtime adapter reusing Phase 1 discovery, binding, serial, and session seams"
  - "Deterministic plugin/bridge integration tests and hash-bound acceptance evidence"
affects: [phase-2-verification, phase-3]
actuals:
  tokens: 7800
  tasks: 2
  commits: 3
tech-stack:
  added: ["Python stdlib plugin runtime", "pyserial 3.5 via existing Phase 1 environment"]
  patterns: ["single flock owner", "public Herdr-only bootstrap", "closed v2 snapshot/focus wire path", "atomic hash-bound evidence"]
key-files:
  created:
    - host/herdr_keypad/herdr-plugin.toml
    - host/herdr_keypad/scripts/ensure-bridge.sh
    - host/herdr_keypad/src/herdr_keypad/__main__.py
    - host/herdr_keypad/src/herdr_keypad/usb.py
    - host/herdr_keypad/tests/test_integration.py
    - artifacts/phase2/automated-acceptance.json
  modified:
    - host/herdr_keypad/src/herdr_keypad/bridge.py
    - host/herdr_keypad/src/herdr_keypad/herdr.py
    - host/herdr_keypad/src/herdr_keypad/projection.py
    - host/herdr_keypad/src/herdr_keypad/focus.py
key-decisions:
  - "The manifest has startup and pane-agent-detected watchdog hooks only; it exposes no actions, pane, provider collector, menu, Wi-Fi, or private inbox control."
  - "USB identity remains the read-only stored device_id; descriptors only narrow candidates and the Phase 1 application hello selects exactly one paired device."
  - "Structured Herdr agent_session values are normalized to source/agent/kind identity components without sending raw paths to firmware."
requirements-completed: []
coverage:
  - id: D1
    description: "Permanent startup-only Herdr plugin and one exact paired USB bridge owner"
    requirement: SAFE-02
    verification:
      - kind: integration
        ref: "host.herdr_keypad.tests.test_integration.PluginLifecycleTests"
        status: pass
    human_judgment: false
  - id: D2
    description: "Closed focus-only host path with exact identity and lifecycle rejection coverage"
    requirement: FOCS-04
    verification:
      - kind: integration
        ref: "host.herdr_keypad.tests.test_integration.PluginLifecycleTests.test_focus_path_is_exact_and_only_calls_public_focus"
        status: pass
    human_judgment: false
  - id: D3
    description: "Delivered keypad snapshot acknowledgement and physical three-tile/key focus"
    verification: []
    human_judgment: true
    rationale: "Automation reached the connected USB path but did not obtain a v2 snapshot acknowledgement; pixel correspondence and physical focus require the blocking human checkpoint."
duration: 1h
completed: 2026-08-17
---

# Phase 2 Plan 04: Permanent Herdr plugin and exact USB bridge Summary

**Startup-only herdr-keypad packaging now owns one exact paired USB session and preserves the public Herdr/focus-only seams; final device acknowledgement and physical focus remain blocked at the required human checkpoint.**

## Accomplishments

- Added `herdr-keypad` manifest with one startup hook and one ordinary agent-detected ensure hook. The manifest has no plugin actions, pane, provider credentials, Codex collector, Wi-Fi, shell proxy, or inbox-control capability.
- Added a current-user flock guard with ownership-checked `stop-for-acceptance`; duplicate startup exits without creating a second process or serial owner.
- Added `UsbDeviceSession`, built on Phase 1 candidate enumeration, read-only pairing, exact application hello, bounded full I/O, and fresh session behavior. v2 snapshot/focus messages use the existing Phase 1 frame codec/session identifiers.
- Added `PermanentBridge` bootstrap, complete snapshot acknowledgement gate, public `events.subscribe` invalidation seam, typed focus-result conversion, and atomic bounded evidence output.
- Normalized actual installed Herdr JSON-RPC string IDs, wrapped snapshot responses, Unicode terminal titles, and structured optional agent-session identity fields without weakening opaque target validation.
- Added deterministic fake-Herdr/fake-USB integration checks for manifest restrictions, duplicate bootstrap epochs, contract drift, exact focus-only allowlisting, exact candidate/hello selection, v2 snapshot acknowledgement, and closed wire framing.

## Task Commits

1. **Task 1: Start one permanent bridge over the exact paired selected-USB session** - `61a6cdf`
2. **Task 2: Prove the complete focus-only product contract with bounded integration and actual-device smoke** - `90fca6a`, `a08bd2a`, `6292f4d`
3. **Task 3: Verify the delivered three-tile projection and exact physical focus** - blocked at human checkpoint; no source commit

## Verification Evidence

- `PYTHONPATH=host/herdr_keypad/src:tools/phase1_bringup/src ... -m unittest host.herdr_keypad.tests.test_protocol host.herdr_keypad.tests.test_projection host.herdr_keypad.tests.test_focus host.herdr_keypad.tests.test_integration` — **19 tests passed**.
- `sh -n host/herdr_keypad/scripts/ensure-bridge.sh` and TOML manifest parse/restriction assertions — **passed**.
- `tools/phase1_bringup/.venv/bin/pio run -e selected-usb` — **passed**.
- `... -m herdr_keypad --inspect --binding /home/nnex/.config/herdr/keypad-binding.json --timeout 5` — **passed**, reporting source current, one host epoch/revision, and fixed positions 1–3.
- `... -m herdr_keypad --smoke-ui-bounds --evidence /tmp/herdr-keypad-ui-evidence.json` — **passed** without invoking focus.
- `... -m herdr_keypad --smoke ... --timeout 5` — **did not pass**: the connected USB endpoint timed out waiting for `agent_snapshot` acknowledgement (an earlier attempt also rejected a nonmatching application identity). `artifacts/phase2/automated-acceptance.json` records `snapshot_acknowledged: false`, `physical_press_observed: false`, and the source/schema/fixture/firmware-lock hashes; it makes no physical or focus claim.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Accepted installed Herdr JSON-RPC response contract**
- **Found during:** Task 1/2 live smoke
- **Issue:** The active Herdr socket requires string request IDs and wraps `session.snapshot` under `snapshot`; the original adapter sent integer IDs and treated the wrapper as the snapshot object.
- **Fix:** Send string IDs and unwrap the public snapshot response.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/herdr.py`
- **Verification:** Live `session.snapshot`, `agent.list`, and `workspace.list` probes plus inspect succeeded.
- **Committed in:** `90fca6a`

**2. [Rule 1 - Bug] Normalized live terminal labels and structured optional sessions**
- **Found during:** Task 2 live inspect/smoke
- **Issue:** Installed titles contain terminal glyphs and `agent_session` is a structured object, while the bounded device contract accepts ASCII opaque identity fields.
- **Fix:** Strip non-ASCII glyphs only from display titles and derive a bounded source/agent/kind session token; preserve pane/terminal/revision exactness.
- **Files modified:** `host/herdr_keypad/src/herdr_keypad/projection.py`, `host/herdr_keypad/src/herdr_keypad/focus.py`
- **Verification:** 19-test focused host suite and live inspect passed.
- **Committed in:** `90fca6a`

**3. [Rule 3 - Blocking] Recorded actual-device v2 acknowledgement failure without overclaiming**
- **Found during:** Task 2 selected-device smoke
- **Issue:** The connected endpoint did not return a v2 `snapshot_ack` within the bounded timeout; the required physical verification cannot be inferred from host tests.
- **Fix:** Smoke evidence is written atomically with `snapshot_acknowledged: false` and bounded error metadata; no focus or physical claim is recorded.
- **Files modified:** `artifacts/phase2/automated-acceptance.json`
- **Verification:** Artifact reopens and contains contract/effects/schema/fixture/firmware-lock hashes.
- **Committed in:** `a08bd2a`

## Known Stubs

None in the implementation. The actual-device acknowledgement is an unmet verification result, not a stub; it is tracked as the blocking human checkpoint below.

## Checkpoint / Blocker

The required Task 3 human verification cannot be marked approved in this execution: the connected USB endpoint did not acknowledge the v2 complete snapshot, so no physical pixel correspondence or focus-only physical press was attempted. Keep the paired keypad on the selected USB link, ensure the Phase 2 v2 firmware is the delivered image, then rerun the bounded smoke and complete the plan's eight physical verification steps. Do not alter the stored binding or broaden transport/actions.

## Next Phase Readiness

Host packaging, exact USB selection, public Herdr bootstrap, focus-only allowlist, integration checks, selected-usb build, and bounded evidence are ready. Phase 2 remains halted until the human physical checkpoint observes snapshot acknowledgement, three-tile rendering, pending-then-exact focus, and all negative result states.

---
*Phase: 02-authoritative-agent-projection-and-exact-focus*
*Plan: 04*
*Status: halted*
*Completed: 2026-08-17*
