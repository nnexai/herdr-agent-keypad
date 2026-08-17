---
status: awaiting_human_verify
trigger: "Investigate the intermittent physical press-to-focus path in the current repository. Trace device focus_intent emission, USB framing/session polling, bridge readiness/generation checks, FocusExecutor invocation, and focus_result feedback. Look specifically for dropped input, debounce/queue timing, polling cadence, stale-generation fencing, or interleaving races introduced by Phase 02.1. Use the existing tests/evidence as anchors. Implement a minimal fix plus deterministic regression only if a concrete root cause is proven; otherwise return a checkpoint requesting the smallest specific symptom needed. Do not run long qualification/recovery or physical tests. Report root cause, evidence, focused verification, files, and commit."
created: 2026-08-17T16:43:53+02:00
updated: 2026-08-17T17:07:00+02:00
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "Herdr's raw pane revision is an activity counter, not an opaque target identity version; treating revision-only drift as a new displayed generation causes routine full commits and makes an otherwise exact key-1 intent stale before FocusExecutor can act."
  confirming_evidence:
    - "Four live agent.list samples 1.05s apart kept pane_id, terminal_id, agent_session, rank, state_change_seq, status, and displayed title stable while slot 0 revision advanced 608399 -> 608414 -> 608429 -> 608444; stable slots stayed at 4243 and 72."
    - "The delivered smoke likewise showed slot 0 source_revision 600942 -> 601011 in 5.4s, six full publications, and successful focus only for stable slot index 1."
    - "A deterministic fake reproduced projection snapshot_revision 1 -> 2 and wrong_revision from a revision-only row change."
  falsification_test: "If a revision-only row refresh reuses the committed generation and FocusExecutor accepts the same pane/terminal/workspace/session after full normalized-generation revalidation, while rank/state/session changes still reject, the hypothesis is supported; failure of either side disproves the proposed mechanism/fix."
  fix_rationale: "Carry the committed source_revision binding token across raw-revision-only refreshes, revalidate the entire normalized projection before focus, and remove visible SYNC from the internally fenced compose/commit path. This removes only false generation churn while preserving exact device generation and opaque target checks."
  blind_spots: "No physical rerun is permitted in this assignment; hardware display timing and a genuinely changing workspace label are not exercised."
  candidate_causes:
    - "code: InboxProjection includes volatile raw revision in dataclass equality and FocusExecutor compares it as identity; AgentProjection renders SYNC for every accepted snapshot."
    - "environment/data: the active working pane emits roughly 14-15 Herdr revisions per second while idle panes do not."
    - "transport: USB interleaving and pending-focus queue loss were inspected, but do not explain deterministic slot specificity."
  and_gate: "yes — failure requires both volatile working-pane revision data and code that promotes every raw revision to a generation/identity fence; visible flicker additionally requires the Phase 02.1 SYNC render on every commit."
bug_class: Bohrbug
test: not-ready same-session matching-ACK and changed-generation discard regressions
expecting: deferred intent executes exactly once only for the acknowledged generation
next_action: confirm on the delivered keypad that repeated presses no longer remain stuck after the keypad reacts; keep Phase 02.1 open until confirmed

## Symptoms

expected: pressing a displayed keypad tile focuses the exact displayed Herdr agent reliably
actual: routine poll-mode refresh shows UPDATING/SYNC about once per second; physical key 1 cannot focus its displayed agent while keys 2 and 3 work; one bounded smoke focused stable slot 2, while an earlier smoke timed out with no focus result
errors: prior smoke reported changed_generation_focus_timeout; no protocol error is displayed to the user
reproduction: run the permanent bridge in poll mode and press key 1 on the first, actively changing agent tile; keys 2/3 remain focusable
started: observed after Phase 02.1 made each source revision change a full composed snapshot commit

## Eliminated


## Evidence

- timestamp: 2026-08-17T16:43:53+02:00
  checked: supplied smoke evidence summary
  found: one pass observed revision 1 -> 6 and focus.focused=true; an earlier pass observed 28 publications in 30 seconds, changed revision 28, poll mode, and no focus result
  implication: the path can succeed, but a timing/interleaving-sensitive failure remains plausible

- timestamp: 2026-08-17T16:44:27+02:00
  checked: .planning/debug/knowledge-base.md known resolutions
  found: the only semantic match is phase2-blank-panels; it previously included source-revision rejection without a fresh authoritative generation and is guarded by test_source_revision_drift_rebinds_before_fresh_retry
  implication: stale/fresh generation interleaving is a high-priority candidate, but the prior match is only a hypothesis until the current code path is reproduced

- timestamp: 2026-08-17T16:49:50+02:00
  checked: user-observed slot-specific behavior and artifacts/phase2.1/live-sync-smoke.json
  found: key 1 alone is unfocusable while keys 2/3 work and routine refresh visibly enters UPDATING; the passing smoke focused slot index 1 whose source_revision stayed 4227, while slot index 0 advanced from 600942 to 601011 in 5.4 seconds
  implication: the differentiator is volatile first-pane revision churn, not a global USB/keypad failure; revision-only churn is the leading cause of both flicker and focus rejection

- timestamp: 2026-08-17T16:52:00+02:00
  checked: four bounded live agent.list reads at 1.05-second intervals
  found: active slot 0 revision advanced 608399 -> 608414 -> 608429 -> 608444 while pane_id w14:p1, terminal_id, agent_session, state_change_seq 295, working status, focused state, rank 2, and displayed row title stayed stable; the next slots stayed at revisions 4243 and 72
  implication: raw revision is high-frequency activity data and is not a safe proxy for displayed-target identity or a reason to publish a new generation

- timestamp: 2026-08-17T16:52:00+02:00
  checked: deterministic projection/focus fake with only revision 10 -> 11
  found: current code created snapshot_revision 2 from an otherwise identical row and rejected the original intent as wrong_revision
  implication: the code mechanism exactly reproduces the slot-specific stale fence without USB, debounce, or physical timing

- timestamp: 2026-08-17T16:56:30+02:00
  checked: pre-fix regression runs
  found: host regression failed twice (revision-only refresh created a new snapshot; focus returned source_revision_changed) and native regression failed with Expected 0 Was 6 SYNC/UPDATING draws
  implication: the tests independently reproduce both causal defects and are not vacuous

- timestamp: 2026-08-17T16:56:30+02:00
  checked: post-fix focused verification
  found: 18 host projection/focus/bridge tests passed; 4 native agent-projection tests passed; a read-only live pair 1.05s apart reused snapshot_revision 1 despite active raw revision churn
  implication: the fix closes the deterministic host and visible-render paths while retaining material-change rejection

- timestamp: 2026-08-17T17:02:44+02:00
  checked: post-fix human observation and PermanentBridge.handle_frame
  found: behavior is much better but roughly 1 in 20 presses still misses while the keypad reacts; handle_frame returns immediately for every focus_intent when ready is temporarily false, without feedback or retention
  implication: a valid device event can cross a short ACK/readiness window and be silently lost after the keypad has already entered PENDING

- timestamp: 2026-08-17T17:04:56+02:00
  checked: deterministic not-ready focus_intent regression before and after the bridge change
  found: pre-fix matching ACK left agent.focus count at 0; post-fix it executed once, a repeated ACK did not replay it, and a changed generation discarded the deferred intent without a focus_result
  implication: the residual loss window is closed while session/generation transitions remain fail-closed

- timestamp: 2026-08-17T17:04:56+02:00
  checked: focused PluginLifecycleTests
  found: 9 tests passed in 0.019 seconds
  implication: immediate focus, revision-only reuse, material rebind, not-ready deferral, and generation discard coexist

## Resolution

root_cause: "Two contributing causes were confirmed: volatile Herdr raw pane revisions were promoted to displayed generations/identity fences, producing key-1 churn and SYNC flicker; after that fix, PermanentBridge.handle_frame still silently dropped a valid focus_intent whenever ready was temporarily false during snapshot acknowledgement."
fix: "Stabilize revision-only generations and remove routine visible SYNC as in 726df6d. Additionally retain a bounded, validated same-session focus_intent while temporarily not ready, process it exactly once after the matching snapshot ACK, and clear it on bootstrap/reconnect, unavailable/source transition, or generation mismatch."
verification:
  target_test: { result: pass }
  mutation_check: { result: skipped, reason_if_skipped: "No mutation runner is configured; target regression was observed red before the bridge fix." }
  no_op_deletion: { result: pass, deletion_justified_by_rca: false }
  adjacent_tests: { result: pass, suites_run: ["9 PluginLifecycleTests", "18 earlier host projection/focus/bridge tests", "4 native agent-projection tests"] }
  revert_and_reconfirm: { result: pass, bug_returned_on_revert: true, fixed_on_reapply: true }
  guardrail_verdict: accepted
  commits: ["726df6d", "22c3070"]
oracle_type: specified
files_changed: ["firmware/src/app/agent_projection.cpp", "host/herdr_keypad/src/herdr_keypad/bridge.py", "host/herdr_keypad/src/herdr_keypad/focus.py", "host/herdr_keypad/src/herdr_keypad/projection.py", "host/herdr_keypad/tests/test_focus.py", "host/herdr_keypad/tests/test_integration.py", "host/herdr_keypad/tests/test_projection.py", "test/agent_projection/stubs/TKeyboardS3Pro.h", "test/agent_projection/test_main.cpp", "test/test_agent_projection/test_main.cpp"]
