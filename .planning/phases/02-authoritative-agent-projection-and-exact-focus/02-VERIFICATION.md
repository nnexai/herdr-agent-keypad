---
phase: 02-authoritative-agent-projection-and-exact-focus
verified: 2026-08-17T11:16:29Z
status: passed
score: 13/13 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 13/13
  gaps_closed:
    - "Phase 2 can be canonically verified under its declared MVP mode."
  gaps_remaining: []
  regressions: []
---

# Phase 2: Authoritative Agent Projection and Exact Focus Verification Report

**Phase Goal:** As a user of the delivered keypad, I want to see the installed inbox's three highest entries and focus the exact displayed Herdr pane with one safe physical press, so that I can switch to the agent needing attention without unsafe triage actions.

**Verified:** 2026-08-17T11:16:29Z  
**Status:** passed  
**Re-verification:** Yes — after roadmap metadata correction

## MVP User-Story Gate

`node .codex/gsd-core/bin/gsd-tools.cjs query user-story.validate --story "…"` returned `valid: true` with:

- role: `user of the delivered keypad`
- capability: `see the installed inbox's three highest entries and focus the exact displayed Herdr pane with one safe physical press`
- outcome: `I can switch to the agent needing attention without unsafe triage actions`

The prior sole gap was the former non-User-Story wording. The current ROADMAP goal satisfies the canonical MVP validator without changing scope or source.

## User Flow Coverage

| Step | Expected | Evidence in the codebase and acceptance evidence | Status |
|---|---|---|---|
| See inbox | The three agent keys render the installed inbox's top zero-to-three entries, in its rank/sequence order, with explicit empty tiles. | `projection.py:164-193` sorts only `(rank, -state_change_seq)`, bounds to `MAX_SLOTS`, and fills remaining positions with `ProjectedEntry.empty()`; `agent_projection.cpp:97-149` requires exactly three explicit slots. The selected-device acceptance records an acknowledged three-slot current snapshot. | ✓ VERIFIED |
| Recognize a target | An occupied tile presents bounded title/discriminator and a state-specific visual/non-color cue. | `projection.py:156-162` normalizes bounded display metadata; `agent_projection.cpp` renders title/discriminator, state rail, label, and geometry. The recorded physical observation includes WAIT/IDLE startup, an empty position, and a BLOCKED tile. | ✓ VERIFIED |
| Safely press | Pressing a displayed occupied key first shows pending and submits the committed pane/terminal/session/epoch/revision binding. | `agent_projection.cpp:292-309` copies only the committed binding into `focus_intent` and immediately marks it pending. `focus.py:75-138` rejects stale, empty, changed, vanished, offline, and mismatched targets before the one allowed request. | ✓ VERIFIED |
| Receive truthful result | Success is shown only after exact Herdr acknowledgement; the terminal visual returns to authoritative state, not a replayed/guessed result. | `focus.py:124-138` accepts only matching `AgentInfo` with `focused is True`; `agent_projection.cpp:324-342` requires matching action, identity, epoch, and snapshot revision before rendering FOCUSED. `automated-acceptance.json` records `PENDING → FOCUSED → BLOCKED`, exact target switch, and `focused: true`. | ✓ VERIFIED |
| Outcome | The user can switch to the agent needing attention without unsafe triage actions. | The physical acceptance log records a mapped press switching to the exact target tab. `FocusExecutor` is the sole dispatcher and its contract allowlist is exactly `agent.focus`; excluded triage actions are rejected by `verify_contract_inputs()`. | ✓ VERIFIED |

## Goal Achievement

### Observable Truths and Plan Must-Have Coverage

| # | Merged technical must-have | Status | Evidence |
|---|---|---|---|
| 1 | Phase 2 begins from a verified selected-USB Phase 1 handoff and final hardware/protocol/UI contracts. | ✓ VERIFIED | `phase1-handoff.json` binds selected `usb_cdc`, the paired binding, final build/archive, and final source/UI hashes. Plan 02-00 artifact verification passed 3/3. |
| 2 | Installed Herdr authority, ordering, acknowledgement ownership, and focus-only capability are pinned; drift blocks startup. | ✓ VERIFIED | `herdr-contract.json` pins Herdr 0.8.0/protocol 19 and revision `78b243279b4da55150b58dc2cc3cffcdc2fd6a04`; independent `rev-parse HEAD` returned that same revision. `bridge.py:485-579` rejects drift before USB connection. |
| 3 | The bounded v2 path carries snapshots and correlated focus outcomes through the existing session seam, not a second parser/transport. | ✓ VERIFIED | Closed `v2.json` and v2 fixture exist; `usb.py:116-160` validates and sends v2 frames through the Phase 1 session; `protocol.cpp:474-477,635-637` admits only closed v2 types. Native protocol vectors passed 5/5. |
| 4 | Pixels and bindings commit as one host epoch/revision; no mixed generation is actionable during sequential updates. | ✓ VERIFIED | `agent_projection.cpp:97-190` validates exactly three unique slots, disables bindings, renders SYNC, draws each staged tile, then commits. The targeted fail-closed generation regression passed. |
| 5 | Zero to three entries use installed order and explicit empty records, with no local priority model. | ✓ VERIFIED | `projection.py:164-193` has the only order rule, truncates to three, and appends explicit empties; focused installed-order regression passed. |
| 6 | Occupied and empty tiles are recognizable through bounded metadata, authoritative state, color, label, and non-color cue. | ✓ VERIFIED | `projection.py:130-162` rejects incomplete identity and bounds title/discriminator; firmware renders literal state labels, rails, and state geometry. Exact-device acceptance records startup states, an empty position, and BLOCKED. |
| 7 | Lifecycle, stale, vanished, incompatible, and offline bindings fail closed and cannot be substituted or replayed. | ✓ VERIFIED | `projection.py:205-229` freezes stale/offline bindings and makes them non-actionable. `focus.py:75-129` rejects every identity/generation/lifecycle mismatch before focus; stale-to-fresh regression passed. |
| 8 | A physical press invokes only exact identity-bound `agent.focus`; success needs matching focused AgentInfo and correlation. | ✓ VERIFIED | Firmware sends committed opaque identity plus host epoch/revision (`agent_projection.cpp:292-309`); `focus.py:113-138` revalidates then accepts only matching `focused: true`. Exact-focus regression passed and the acceptance record confirms target switch. |
| 9 | Native seen/manual-unread effects may occur, but keypad paths cannot settle, dismiss, clear, reply, approve, or make arbitrary calls. | ✓ VERIFIED | `FocusExecutor` documents and implements the sole `agent.focus` dispatcher. `herdr-contract.json` has allowlist `["agent.focus"]` and explicitly excludes `settle`, `unread`, `clear`, `reply`, `approval`, and arbitrary methods; contract validation enforces it. |
| 10 | Focus feedback is correlated and distinct; pending, stale, vanished, offline, uncertain, failed, and rejected never become success or retry. | ✓ VERIFIED | `agent_projection.cpp:324-342` accepts only an exact pending result and maps every outcome separately; the focused protocol regression exercises the fail-closed correlation path. |
| 11 | One guarded permanent bridge owns public-Herdr-to-exact-paired-USB, without provider/inbox credentials or unrelated capability. | ✓ VERIFIED | `herdr-plugin.toml` has only startup and `pane.agent_detected` hooks. `usb.py:33-105` uses the read-only pairing binding and Phase 1 `reconnect_exact`; plugin/integration tests cover lifecycle restrictions. |
| 12 | Source-revision drift rejects the old target, publishes a complete fresh binding, then permits exactly one revalidated fresh retry. | ✓ VERIFIED | `bridge.py:640-643` sends the stale outcome then refreshes only `source_revision_changed`; the named regression passed and the resolved debug evidence records the physical stale-to-fresh confirmation. |
| 13 | Exact selected-device acceptance proves acknowledgement, safe empty rejection, exact focus, and authoritative restoration without repeating long qualification. | ✓ VERIFIED | `automated-acceptance.json` records snapshot acknowledgement, empty rejection, focus invocation, `focused: true`, target switch, and feedback restoration. The debug artifact records the final paired-device acknowledgement and physical acceptance. |

**Score:** 13/13 technical must-haves verified (0 present-but-behavior-unverified).

### Roadmap Success Criteria

| # | Roadmap criterion | Status | Evidence |
|---|---|---|---|
| 1 | Three keys show zero to three entries in exactly installed order, with explicit empties and no reprioritization. | ✓ VERIFIED | `projection.py:164-193` has the sole rank/sequence sort and fixed empty fill; firmware consumes supplied slots without sorting. |
| 2 | Occupied keys have title/discriminator, Herdr-consistent color, and a non-color state cue. | ✓ VERIFIED | Host normalization plus state labels, rails, and state-specific geometry in firmware; actual device evidence observed empty, startup, and BLOCKED surfaces. |
| 3 | An occupied press focuses the exact represented pane only after opaque identity, epoch, and revision acknowledgement. | ✓ VERIFIED | Committed intent capture, current canonical binding comparison, matching focused `AgentInfo`, named regression, and physical focus log all agree. |
| 4 | Empty/stale/vanished/incompatible/offline inputs visibly reject, and updates never mix pixels with another generation's action. | ✓ VERIFIED | Fail-closed projection/executor plus SYNC-before-commit renderer, stale-refresh regression, and actual empty-key rejection. |
| 5 | Keypad can request only typed focus; native effects may occur, but triage/arbitrary actions are impossible. | ✓ VERIFIED | Immutable allowlist, explicit exclusions, and the sole production `FocusExecutor` dispatcher. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `artifacts/phase2/phase1-handoff.json` | Hash-bound selected-USB handoff | ✓ VERIFIED | Exists, substantive, and binds paired device, selected transport, locks, archive, and final contract hashes. |
| `artifacts/phase2/herdr-contract.json` | Pinned Herdr authority and focus-only contract | ✓ VERIFIED | Installed checkout HEAD matches pinned revision; contract validation is called before bridge connection. |
| `artifacts/phase2/herdr-focus-effects.json` | Complete installed focus/effects matrix | ✓ VERIFIED | Eight named lifecycle/identity rows, cleanup proof, and source revision are recorded and consumed by regression checks. |
| `protocol/schema/v2.json`, `protocol/fixtures/v2-golden.json` | Closed v2 contract and vectors | ✓ VERIFIED | Substantive closed schema/vectors; current hashes match the acceptance record; native test opens the fixture through `PHASE2_GOLDEN_FIXTURE`. |
| `host/herdr_keypad/src/herdr_keypad/{bridge,projection,focus,usb}.py` | Runtime projection, exact focus, paired USB | ✓ VERIFIED | Substantive production implementations wired through plugin lifecycle, public socket, Phase 1 link/session, and v2 frames. |
| `firmware/src/app/agent_projection.{h,cpp}`, `firmware/src/main.cpp` | Atomic fixed-slot renderer and key capture | ✓ VERIFIED | Substantive staged/committed rendering and focus correlation wired from admitted frames and board keys. |
| `host/herdr_keypad/herdr-plugin.toml` | Single startup bridge registration | ✓ VERIFIED | Only two guarded lifecycle hooks; no action/provider/inbox-credential surface. |
| `artifacts/phase2/automated-acceptance.json` | Hash-bound selected-device acceptance | ✓ VERIFIED | Substantive observed result whose four source artifact hashes match independently computed current hashes. |

`verify.artifacts` passed every declared artifact: Plan 02-00 3/3, 02-01 4/4, 02-02 3/3, 02-03 3/3, and 02-04 3/3.

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| Herdr public socket | `InboxProjection` | `session.snapshot`, `agent.list`, `workspace.list` | ✓ WIRED | `InboxProjection.bootstrap()` reads all three public methods before publication. |
| `InboxProjection` | exact paired USB | v2 snapshot / matching acknowledgement | ✓ WIRED | `UsbDeviceSession.publish_snapshot()` uses validated v2 `agent_snapshot`; bridge requires accepted matching epoch/revision before ready. |
| USB focus intent | `FocusExecutor` | canonical binding comparison and one `agent.focus` | ✓ WIRED | `PermanentBridge.handle_frame()` routes the typed intent through revalidation; executor exposes no generic dispatch. |
| `FocusOutcome` | device feedback | correlated v2 focus result | ✓ WIRED | Firmware accepts only exact pending identity/generation result and renders distinct outcomes. |
| Plugin manifest | bridge owner | flock-guarded startup command | ✓ WIRED | Manifest invokes `ensure-bridge.sh`, which owns the permanent bridge process. |
| v2 golden fixture | native production test | `PHASE2_GOLDEN_FIXTURE` macro | ✓ WIRED | `platformio.ini:39` defines the exact fixture path; `test_main.cpp:121-123,263` opens and executes it. |

All declared links are wired. Mechanical `verify.key-links` returned 14/15 because its literal `v2-golden` search does not follow the macro; the direct macro-to-open-to-`RUN_TEST` trace above proves the remaining link.

### Data-Flow Trace (Level 4)

| Rendered value | Source | Flow | Status |
|---|---|---|---|
| Title, discriminator, state, and installed order | Real installed Herdr public socket | `HerdrClient` → `InboxProjection.refresh()` → v2 snapshot → `UsbDeviceSession.publish_snapshot()` → staged/committed firmware tiles | ✓ FLOWING |
| Exact focus target | Current committed binding | firmware intent → host canonical binding/revalidation → `agent.focus` → matching v2 result | ✓ FLOWING |
| Selected-device observation | Paired USB and Herdr response | bounded acceptance writer records hashes, snapshot metadata, focus outcome, and physical observation | ✓ FLOWING |

`NO AGENT` is an intentional explicit empty state after authoritative zero-to-three projection, not a static fallback.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Installed ordering, exact focus-only dispatch, source-revision rebind/retry, and generation/result fail-closed handling | `PYTHONPATH=host/herdr_keypad/src:tools/phase1_bringup/src tools/phase1_bringup/.venv/bin/python -m unittest …test_fixed_positions_and_installed_order …test_valid_focus_revalidates_then_emits_only_agent_focus …test_source_revision_drift_rebinds_before_fresh_retry …test_generation_and_focus_result_are_fail_closed` | 4 tests ran, `OK` | ✓ PASS |
| Production v1/v2 codec and bounded session vectors | `tools/phase1_bringup/.venv/bin/pio test -e native -f protocol` | 5/5 cases passed in 0.406 s, including `test_v2_fixture_vectors` | ✓ PASS |
| MVP metadata validity | `node .codex/gsd-core/bin/gsd-tools.cjs query user-story.validate --story "…"` | `valid: true`, no errors | ✓ PASS |
| Acceptance-source integrity | `sha256sum` of contract/effects/v2 schema/v2 fixture; installed plugin `rev-parse HEAD` | All four SHA-256 values match `automated-acceptance.json`; installed HEAD matches pinned revision | ✓ PASS |

### Probe Execution

**SKIPPED:** No Phase 2-declared `probe-*.sh` path exists. No long Phase 1 qualification was rerun.

### Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| INBX-01 | ✓ SATISFIED | Installed rank/sequence projection, fixed slots, explicit empty fill, no firmware sorting. |
| INBX-02 | ✓ SATISFIED | Bounded title and workspace/repository discriminator reach renderer. |
| INBX-03 | ✓ SATISFIED | State labels, geometry, and Herdr-consistent colors; physical BLOCKED/empty/startup observation. |
| INBX-04 | ✓ SATISFIED | Explicit non-actionable `NO AGENT` rendering and physical empty-position rejection. |
| FOCS-01 | ✓ SATISFIED | Opaque pane/terminal/session/revision plus bridge epoch/revision bind the displayed target. |
| FOCS-02 | ✓ SATISFIED | Empty, stale, offline, source-revision, vanished, and identity mismatch rejections are distinct and non-substituting. |
| FOCS-03 | ✓ SATISFIED | Success requires matching focused `AgentInfo`; pending/focused/authoritative restoration evidence is recorded. |
| FOCS-04 | ✓ SATISFIED | `agent.focus` allowlist and forbidden-action checks; no compensating triage calls. |
| SYNC-02 | ✓ SATISFIED | SYNC veil, disabled bindings, staging, and post-render commit preserve one logical generation. |
| SAFE-02 | ✓ SATISFIED | Closed typed focus frames and sole focus executor prevent arbitrary Herdr/host/provider actions. |

All ten Phase 2 requirements are declared in Phase 2 plans; none is orphaned.

### Re-verification Evidence and Accepted Caveat

- All five Phase 2 summaries, four Phase 2 JSON evidence artifacts, the resolved `phase2-blank-panels` debug record, and the current ROADMAP were inspected.
- The debug record documents and closes the real selected-device regressions: missing startup WAIT rendering, too-small HWCDC RX capacity, noncanonical v2 payload ordering, obsolete subscription parameters, and stale source-revision rebind omission. Its final physical acceptance records WAIT/IDLE, safe empty rejection, PENDING, exact tab switch, FOCUSED, and intended restoration to BLOCKED.
- The accepted Phase 1 mutable-binary-hash caveat remains unchanged. Phase 2 selected-USB builds necessarily rewrote mutable `.pio/build/selected-usb/firmware.bin`; a later Phase 1 handoff verifier therefore reports the documented historical binary-hash mismatch. This does not reopen Phase 1 or invalidate Phase 2: the pre-build handoff receipt, selected USB, paired binding, archive, and final contract hashes remain the accepted boundary. No long qualification was repeated.

### Anti-Patterns Found

| Scope | Pattern | Severity | Impact |
|---|---|---|---|
| Phase 2 source, firmware, tools, plugin, and focused tests | `TBD` / `FIXME` / `XXX` / `TODO` / `HACK` / placeholder scan | None | No unresolved debt marker or product-path placeholder found. |
| Production action path | forbidden triage/arbitrary action scan | None | Forbidden action names occur only in immutable contract exclusions, not callable dispatch paths. |

## Gaps Summary

None. The previous metadata-only gap is closed by the valid MVP User Story. All 13 technical must-haves, all five roadmap success criteria, artifact/data-flow/key-link checks, targeted regressions, acceptance hashes, and supplied selected-device physical evidence remain supported.

---

_Verified: 2026-08-17T11:16:29Z_  
_Verifier: gsd-verifier_
