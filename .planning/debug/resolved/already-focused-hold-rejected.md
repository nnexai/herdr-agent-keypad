---
status: resolved
trigger: "board is saying rejected, when agent is already focused this means hold to speak does not work"
created: 2026-08-30T09:45:23Z
updated: 2026-08-30T10:05:13Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: HerdrClient::focus_pane turns Herdr 0.8.2's structured agent_session acknowledgement into None, while the complete-read projection canonicalizes the same object to a non-None token; FocusExecutor therefore rejects the exact current already-focused target as SessionChanged.
  confirming_evidence:
    - Live agent.list and idempotent agent.focus returned matching exact pane/terminal/workspace/tab and matching structured agent_session with focused=true.
    - The minimized production-shape socket-to-HerdrClient-to-FocusExecutor regression failed deterministically with left SessionChanged and right Accepted.
    - Source inspection shows focus_pane uses Value::as_str on agent_session, while the complete-read side accepts object sessions through session_token.
  falsification_test: Preserve the raw focus acknowledgement session object; the exact-current test must become Accepted with focused=true, while a different structured session must remain SessionChanged and every stale/vanished/wrong-target/offline/malformed/uncertain case must remain rejected.
  fix_rationale: Carry the raw JSON session value in HerdrFocusAck and let the existing single session_token implementation canonicalize it at the authorization fence. This removes the lossy narrowing without weakening or bypassing any identity check.
  blind_spots: The native regression cannot observe the physical keypad or HID device because firmware and deployment are forbidden; focused Rust protocol/coordinator suites cover the host result mapping.
  candidate_causes:
    - code: HerdrClient narrows structured session identity to Option<String> and silently produces None.
    - environment: Installed Herdr 0.8.2 returns valid structured session objects rather than legacy strings.
    - data: Complete-read and focus envelopes contain matching source/agent/kind identity fields.
  and_gate: Yes. The bug requires the structured Herdr response and the lossy client conversion; neither condition alone produces rejection.
bug_class: Bohrbug
test: Integrated host-side verification, clean release staging, and live runtime restoration complete.
expecting: Resolved. Automated real-seam proof is sufficient because accepted plus focused is the exact native authorization contract consumed by the unchanged device hold state machine.
next_action: none

## Symptoms

expected: pressing and deliberately holding the key for an agent that is already focused treats focus as successfully established, then authorizes and holds USB HID Space until release
actual: the keypad displays REJECTED and hold-to-speak does not activate when the selected agent is already focused
errors: device presentation reports REJECTED; no held Space is emitted
reproduction: focus an agent, then deliberately hold that same agent key past the hold threshold
started: observed after the production native Rust bridge cutover

## Eliminated
- hypothesis: The subprocess/socket reader stops before the complete already-focused response.
  evidence: Herdr 0.8.2 returned one well-formed correlated result envelope with result.agent.focused=true and all observed identity fields; the CLI exited successfully.
  timestamp: 2026-08-30T09:52:12Z
- hypothesis: Already-focused is represented as an error/status branch that the coordinator rejects before identity checks.
  evidence: The live response contains result.agent with focused=true, not an error or distinct status.
  timestamp: 2026-08-30T09:52:12Z
- hypothesis: Local Herdr configuration emits malformed or offline output.
  evidence: herdr --version reports 0.8.2; agent.list and idempotent agent.focus both returned valid successful JSON envelopes.
  timestamp: 2026-08-30T09:52:12Z


## Evidence



- timestamp: 2026-08-30T09:47:49Z
  checked: Initial symptom checkpoint
  found: The report is deterministic at one state transition—holding the key after that exact agent is already focused produces REJECTED and no held Space.
  implication: Treat as a Bohrbug and reproduce at the native focus authorization seam before changing source.
- timestamp: 2026-08-30T09:48:20Z
  checked: Diagnosing-bugs skill
  found: A correct fix requires a fast deterministic red-capable loop at the real authorization seam, minimization, regression test before source change, and cleanup of all diagnostics.
  implication: The first repository goal is a focused native Rust test command that catches the exact already-focused rejection.
- timestamp: 2026-08-30T09:48:50Z
  checked: Mandatory GSD debugger references and common-pattern map
  found: The strongest matching categories are deterministic data-shape/API-contract mismatch and invalid state-transition handling; no evidence yet supports timing or concurrency.
  implication: Prioritize the exact installed-Herdr envelope and the native mapping branch while preserving fail-closed identity and freshness guards.
- timestamp: 2026-08-30T09:49:08Z
  checked: Project and configured debugger skills
  found: No task-specific project rule applies under host/herdr_keypad/native, and the gsd-debugger has no extra configured skill block beyond its supplied role.
  implication: Follow the native crate's existing Rust patterns and the focused scientific/TDD contract without adding a second convention.
- timestamp: 2026-08-30T09:49:26Z
  checked: MemPalace semantic recall and .planning/debug/knowledge-base.md
  found: No prior resolution matches already-focused rejection. The only nearby entry concerns stale source revisions, transport truncation, and obsolete subscription parameters.
  implication: Keep stale-source failure as a required negative fence, but do not treat that older multi-cause incident as this root cause.
- timestamp: 2026-08-30T09:49:50Z
  checked: Native focus source and test symbol map
  found: FocusCoordinator::execute authorizes only when the Herdr response yields agent.focused=true after exact identity matching; HerdrFocusPort converts HerdrFocusAck into a reduced agent object; HerdrClient::focus_pane parses the installed response; orchestrator maps outcome.success() to protocol focused.
  implication: The smallest real seam spans Herdr response decoding through FocusCoordinator::execute, with projection_focus_parity.rs and herdr_parity.rs as the existing focused suites.
- timestamp: 2026-08-30T09:50:37Z
  checked: FocusExecutor, HerdrClient, BlockingHerdr, and focused parity tests
  found: Existing Herdr parity covers only result.agent.focused=true. The coordinator checks complete-read identity before focusing and preserves accepted as focused=true, but it has no representation or test for a valid already-focused variant. The request reader consumes one bounded newline-terminated correlated response.
  implication: Probe the installed response before deciding whether parsing, error mapping, or coordinator policy is at fault; the regression must include the actual envelope shape.
- timestamp: 2026-08-30T09:52:12Z
  checked: Installed Herdr 0.8.2 live agent.list and already-focused agent.focus w17:p1
  found: Both envelopes report the same focused pane w17:p1 and terminal term_65a35e22690671 with focused=true. Both carry agent_session as an object containing source, agent, kind, and value. HerdrClient::focus_pane accepts only string sessions and therefore silently converts that exact object to None, while the complete-read projection canonicalizes the object into a non-None token.
  implication: The same immutable session identity becomes unequal on opposite sides of the authorization check. The failure requires Herdr's structured session data plus the lossy code path; raw identity is current and valid.
- timestamp: 2026-08-30T09:53:11Z
  checked: Reduced live Herdr envelopes and existing session-fence tests
  found: The reduced complete read and focus result match pane w17:p1, terminal term_65a35e22690671, workspace w17, tab w17:t1, focused=true, state_change_seq=124, and agent_session source/agent/kind. Only revision advanced. Existing focused tests use agent_session=null and have no wrong-session negative.
  implication: The minimal failing equivalence class is a focused exact target with a structured non-null agent session. Add a wrong structured-session neighbor after the RED seam is established.
- timestamp: 2026-08-30T09:54:14Z
  checked: First composite RED run
  found: The test failed PaneReused versus Accepted because its direct projection binding retained workspace/tab, while production accept_focus_payload deliberately leaves those two optional acknowledgement fields blank.
  implication: That RED was an adjacent test-construction mismatch, not the reported bug. Remove only those optional fields and rerun before treating the regression as valid.
- timestamp: 2026-08-30T09:54:45Z
  checked: Minimized composite RED at the production authorization seam
  found: cargo test --test herdr_parity already_focused_structured_session_is_authorized -- --exact --nocapture failed in 0.00s with 0 passed, 1 failed, 4 filtered out; FocusStatus was SessionChanged instead of Accepted.
  implication: The fast deterministic regression now reproduces the reported rejection for the exact Herdr 0.8.2 structured-session envelope and is red-capable at the real native seam.
- timestamp: 2026-08-30T09:55:21Z
  checked: Fix-acceptance and repro-hardening rules
  found: The specified oracle must assert Accepted plus focused=true, a wrong structured-session boundary neighbor must remain rejected, focused adjacent suites must pass, and revert/reconfirm must prove causality. No Rust mutation framework is configured in this crate.
  implication: Preserve rather than bypass the session fence, record mutation as skipped, and run a manual fix-site mutant plus revert/reconfirm if practical.
- timestamp: 2026-08-30T09:57:07Z
  checked: Initial GREEN and structured-session boundary neighbor
  found: The exact already-focused test passed 1/1 with 5 filtered; the different structured session test passed 1/1 with 5 filtered and asserted SessionChanged plus focused=false.
  implication: Preserving raw session JSON fixes the target while keeping the immutable agent-session fence fail-closed.
- timestamp: 2026-08-30T09:57:48Z
  checked: Coordinator focus-result mapping
  found: The filtered binary test passed 1/1 with 2 filtered, asserting Accepted maps to focused=true and SessionChanged maps to Rejected with focused=false.
  implication: Hold authorization remains tied to the accepted focus result rather than merely receiving a Herdr response.
- timestamp: 2026-08-30T09:58:40Z
  checked: Focused adjacent Rust suites
  found: herdr_parity passed 6/6; projection_focus_parity passed 10/10; black_box_parity protocol admission passed 1/1 with 7 filtered; session duplicate/stale/foreign-authority fences passed 1/1 with 7 filtered.
  implication: Herdr envelopes, focus identity/freshness failures, coordinator result mapping, and protocol admission remain green without a project-wide run.
- timestamp: 2026-08-30T09:59:27Z
  checked: Manual fix-site mutation and revert/reconfirm
  found: Replacing raw session preservation with the old string-only behavior made the exact test fail SessionChanged versus Accepted with 0 passed, 1 failed, 5 filtered. Restoring the raw clone made it pass 1/1 with 5 filtered.
  implication: The regression kills the fix-site mutant and the source change is causally necessary and sufficient for the observed native authorization behavior.
- timestamp: 2026-08-30T10:00:08Z
  checked: Scoped diff and cleanup
  found: The four native files contain 180 insertions and 3 replacements/deletions; production behavior only widens HerdrFocusAck session transport from Option<String> to raw JSON and preserves the response value. No DEBUG, dbg!, println!, eprintln!, TODO, FIXME, temporary mutant, Python production, firmware edit, or throwaway file remains.
  implication: The guardrail accepts the fix; the only grep match was the sanitized fixture path inside the permanent regression.
- timestamp: 2026-08-30T10:04:45Z
  checked: Session-manager integration and release staging
  found: herdr_parity passed 6/6, projection_focus_parity passed 10/10, coordinator accepted-and-focused authorization passed 1/1, and the native-only production cutover passed 1/1. A clean locked release build was staged byte-identically with SHA-256 42b938e65afd43d361f0697cfba1206dbd0883e45788cc1dfd24ca0f924e8b26.
  implication: The fixed real seam authorizes the exact current already-focused target without weakening identity fences, and the installed executable is the verified Rust release build.
- timestamp: 2026-08-30T10:05:13Z
  checked: Live bridge restoration
  found: Native PID 1041804 runs the staged bin/herdr-keypad, holds /dev/ttyACM0, and reports state=running, device_state=ready, herdr_state=running, codex_state=ready with no last error. No Python production bridge process is present.
  implication: The host-only fix is active on the real production bridge; no firmware or physical UAT is needed to establish the accepted-and-focused authorization contract.
## Resolution

root_cause: Herdr 0.8.2 returns agent_session as a structured object in both agent.list and agent.focus. The complete-read projection canonicalizes it, but HerdrClient::focus_pane accepts only strings and silently changes the focus acknowledgement to None. FocusExecutor compares Some(canonical-token) to None and emits SessionChanged, which the coordinator maps to rejected with focused=false.
oracle_type: specified
fix: HerdrFocusAck now carries the raw agent_session JSON value, and HerdrClient::focus_pane clones that value instead of narrowing it to a string. BlockingHerdr passes it unchanged to the existing FocusExecutor session_token fence.
verification:
  target_test: {result: pass}
  mutation_check: {result: pass, reason: manual fix-site mutant used because no Rust mutation framework is configured, mutant_killed: true}
  no_op_deletion: {result: pass, deletion_justified_by_rca: false}
  adjacent_tests: {result: pass, suites_run: [herdr_parity 6/6, projection_focus_parity 10/10, coordinator_focus_payload 1/1, black_box_protocol 1/1, black_box_session_fences 1/1]}
  revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true}
  guardrail_verdict: accepted
red:
  command: "cargo test --test herdr_parity already_focused_structured_session_is_authorized -- --exact --nocapture"
  result: "FAILED: left SessionChanged, right Accepted; 0 passed, 1 failed, 4 filtered"
green:
  - "target exact: 1 passed, 5 filtered"
  - "different structured session: 1 passed, 5 filtered"
  - "herdr_parity: 6 passed"
  - "projection_focus_parity: 10 passed"
  - "coordinator focus payload mapping: 1 passed, 2 filtered"
  - "black-box protocol focus admission: 1 passed, 7 filtered"
  - "black-box session authority fences: 1 passed, 7 filtered"
behavioral_proof: Exact current structured pane/terminal/agent-session identity produces FocusStatus::Accepted and FocusResult.focused=true; a different structured agent session produces SessionChanged and focused=false.
live_probe: Installed Herdr 0.8.2 returned complete successful agent.list and idempotent agent.focus envelopes for the same focused pane, with matching pane/terminal/workspace/tab, focused=true, and matching structured source/agent/kind session identity.
negative_fences: Existing tests retained rejection for stale projection, pane reuse/wrong target, vanished pane, timeout/uncertain result, malformed acknowledgement, not found/offline behavior, duplicate/stale/foreign protocol authority, and the new different-session neighbor.
cleanup: Temporary fix-site mutant removed; no diagnostics or throwaway files remain; firmware and Python production untouched.
files_changed:
  - host/herdr_keypad/native/src/lib.rs
  - host/herdr_keypad/native/src/ports/herdr.rs
  - host/herdr_keypad/native/tests/herdr_parity.rs
  - host/herdr_keypad/native/src/core/orchestrator.rs

## Prevention

blameless_why:
  code: HerdrFocusAck narrowed an open JSON identity field to a legacy string before the existing canonical identity fence.
  environment_and_data: Herdr 0.8.2 validly returns the same immutable agent session as a structured object, so the two correct components interacted through a lossy boundary.
  test_gate: Existing focus tests used null or string sessions and did not cross the production socket-to-FocusExecutor seam with the installed structured envelope.
why_not_caught: no gate existed for a structured non-string agent_session at the real Herdr socket-to-focus-authorization seam
recurrence_guard: host/herdr_keypad/native/tests/herdr_parity.rs tests already_focused_structured_session_is_authorized and different_structured_session_remains_rejected
