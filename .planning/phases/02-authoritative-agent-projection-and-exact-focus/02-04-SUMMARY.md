---
phase: 02-authoritative-agent-projection-and-exact-focus
plan: 04
subsystem: herdr-plugin-usb-integration
status: complete
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

**Startup-only herdr-keypad packaging owns one exact paired USB session, restores the four-panel startup surface, acknowledges complete v2 snapshots, and focuses only the exact rendered Herdr target with correlated physical feedback.**

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
3. **Task 3: Verify the delivered three-tile projection and exact physical focus** - `db323fe`, `b3f172e`, `8a6d557`

## Verification Evidence

- `PYTHONPATH=host/herdr_keypad/src:tools/phase1_bringup/src ... -m unittest host.herdr_keypad.tests.test_protocol host.herdr_keypad.tests.test_projection host.herdr_keypad.tests.test_focus host.herdr_keypad.tests.test_integration` — **21 tests passed**.
- `sh -n host/herdr_keypad/scripts/ensure-bridge.sh` and TOML manifest parse/restriction assertions — **passed**.
- `tools/phase1_bringup/.venv/bin/pio run -e selected-usb` — **passed**; image SHA-256 `8984944ecfab0a040d1850757b52f14cb40d889d18daa0f0e902d65c0b463984` was flashed and verified on the exact paired ESP32-S3.
- `... -m herdr_keypad --inspect --binding /home/nnex/.config/herdr/keypad-binding.json --timeout 5` — **passed**, reporting source current and fixed positions 1–3.
- `... -m herdr_keypad --smoke-ui-bounds --evidence /tmp/herdr-keypad-ui-evidence.json` — **passed** without invoking focus.
- `... -m herdr_keypad --smoke ... --timeout 8` — **passed**, reporting `snapshot acknowledged` for one current three-slot generation.
- Physical acceptance — **passed**: startup WAIT/IDLE returned, empty position 2 rejected safely, occupied position 1 showed PENDING, switched to the exact target tab, showed terminal FOCUSED feedback, then restored its authoritative BLOCKED state.

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

**3. [Rule 1 - Bug] Repaired the selected-USB startup, v2 acknowledgement, and stale focus rebind path**
- **Found during:** Task 3 actual-device acceptance
- **Issue:** Startup cleared all panels instead of rendering WAIT; HWCDC truncated valid v2 snapshots; device response digests used noncanonical payload order; the bridge used obsolete Herdr subscription parameters and never rebound an advanced AgentInfo source revision.
- **Fix:** Restore WAIT rendering, size HWCDC RX to the protocol line bound, canonicalize device payloads, use installed typed subscriptions, and publish a complete fresh generation after an exact source-revision rejection.
- **Files modified:** `firmware/src/main.cpp`, `firmware/src/app/agent_projection.cpp`, `firmware/src/transport/link.h`, `firmware/src/transport/usb_cdc.cpp`, `host/herdr_keypad/src/herdr_keypad/herdr.py`, `host/herdr_keypad/src/herdr_keypad/bridge.py`, `host/herdr_keypad/tests/test_integration.py`
- **Verification:** Selected-usb build/flash, live snapshot acknowledgement, 21 host tests, raw physical focus-intent capture, accepted `agent.focus` with `focused=true`, and user-observed terminal feedback.
- **Committed in:** `db323fe`, `b3f172e`, `8a6d557`

## Known Stubs

None.

## Human Acceptance

The required Task 3 physical checkpoint passed on the exact paired selected-USB keypad. The user observed restored WAIT/IDLE startup tiles, safe rejection on empty position 2, and position 1 transitioning PENDING → FOCUSED while Herdr switched to the exact target tab, then returning to the target's authoritative BLOCKED tile after the existing two-second terminal feedback hold.

## Next Phase Readiness

Phase 2 is complete. Host packaging, exact USB selection, public Herdr bootstrap, typed subscriptions, complete snapshot acknowledgement, stale-generation rebind, focus-only allowlisting, and actual-device focus feedback are verified. Phase 3 may consume this projection without widening transport or action authority.

---
*Phase: 02-authoritative-agent-projection-and-exact-focus*
*Plan: 04*
*Status: complete*
*Completed: 2026-08-17*
