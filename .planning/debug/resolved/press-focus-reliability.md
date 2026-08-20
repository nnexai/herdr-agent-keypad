---
status: resolved
trigger: "Investigate the intermittent physical press-to-focus path in the current repository. Trace device focus_intent emission, USB framing/session polling, bridge readiness/generation checks, FocusExecutor invocation, and focus_result feedback. Look specifically for dropped input, debounce/queue timing, polling cadence, stale-generation fencing, or interleaving races introduced by Phase 02.1. Use the existing tests/evidence as anchors. Implement a minimal fix plus deterministic regression only if a concrete root cause is proven; otherwise return a checkpoint requesting the smallest specific symptom needed. Do not run long qualification/recovery or physical tests. Report root cause, evidence, focused verification, files, and commit."
created: 2026-08-17T16:43:53+02:00
updated: 2026-08-20T16:15:00Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "The guided smoke blocks in input() while the device remains live, so a focus_intent can age in the serial queue before the scenario is armed; wait_for_type then answers that expired action, while the operator's current press becomes a second unanswered intent and ends UNCERTAIN."
  confirming_evidence:
    - "The answered action device-3208169987 and unanswered action device-3230836995 differ by 22,667,008 us, over seven times the firmware's 3,000,000 us pending deadline."
    - "The host wrote the first focus_result completely (453/453 bytes); immediate metrics showed malformed=0, digest_mismatch=0, rejected=0, and firmware emitted the second focus_intent before metrics_ack."
  falsification_test: "If clearing both DeviceSession's buffered bytes and pyserial's queued input after the readiness ENTER still returns a pre-arm intent or a single post-arm press still produces an unanswered successor, the sequencing hypothesis is false."
  fix_rationale: "Make readiness and arming explicit: after ENTER, discard only pre-arm input at the serial boundary, then print ARMED and wait for the next exact focus_intent. This preserves protocol, framing, buffering during active reads, and timeouts while preventing stale physical actions from crossing scenario boundaries."
  blind_spots: "The final post-arm visual FOCUSED transition still requires one physical confirmation after the deterministic sequencing regression."
  candidate_causes:
    - "code: input() pauses serial consumption without a pre-arm drain, so wait_for_type cannot distinguish queued stale intents from the requested physical action."
    - "environment/data: operator coordination latency exceeded the device's 3s pending deadline, leaving an otherwise valid same-generation action queued for 22.7s."
  and_gate: "yes — failure requires a pre-arm queued intent plus a later real press; answering the first after expiry and ignoring the second produces the observed PENDING-to-UNCERTAIN terminal state."
bug_class: bohrbug
test: "Replay a stale complete/partial buffered intent before arming, discard it, feed a fresh intent, and require the exact fresh action; assert the guided driver calls discard immediately after readiness input."
expecting: "Only the post-arm action reaches focus_result; pre-arm bytes cannot leak into the scenario."
next_action: "Independent verifier FixDuplicateFocusIntent runs the 10 narrow host replays, selected-usb build, and one corrected explicit-ARMED KEY-1 checkpoint from commit 53d8dc6."

## Symptoms

expected: pressing a displayed keypad tile focuses the exact displayed Herdr agent reliably
actual: routine poll-mode refresh shows UPDATING/SYNC about once per second; physical key 1 cannot focus its displayed agent while keys 2 and 3 work; one bounded smoke focused stable slot 2, while an earlier smoke timed out with no focus result
errors: prior smoke reported changed_generation_focus_timeout; no protocol error is displayed to the user
reproduction: run the permanent bridge in poll mode and press key 1 on the first, actively changing agent tile; keys 2/3 remain focusable
started: observed after Phase 02.1 made each source revision change a full composed snapshot commit

## Eliminated


- hypothesis: "6bc68ce still loses ordinary fragmentation, CRLF, back-to-back frames, boot chatter, invalid UTF-8/non-JSON, or stale probe ACKs."
  evidence: "The deterministic serial-boundary replay passes all seven variants and returns the byte-for-byte exact v2 focus_intent."
  timestamp: 2026-08-20T17:07:31+02:00

- hypothesis: "Firmware emits a focus_intent schema/version that DeviceSession rejects."
  evidence: "Firmware emits all nine required v2 payload fields and LF; DeviceSession performs no schema/digest/version rejection and the replay returns the exact envelope and payload."
  timestamp: 2026-08-20T17:07:31+02:00

- hypothesis: "A stale probe ACK or unrelated valid frame causes wait_for_type to stop before the target."
  evidence: "Back-to-back and multiply fragmented stale probe_ack plus target replay skips the ACK and returns the exact target."
  timestamp: 2026-08-20T17:07:31+02:00

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


- timestamp: 2026-08-20T17:01:07+02:00
  checked: /tmp/phase22-guided-fixed.json and prior guided artifacts
  found: the latest and guided-2 reruns show every snapshot revision 1 through 11 rejected under host_epoch phase22-smoke-epoch; the first guided run accepted all revisions and received one success intent before timing out on a later scenario
  implication: reuse of the same epoch with reset revisions is a deterministic rerun defect and prevents the host from establishing the generation it believes it is testing, but prior receipt of one intent proves the focus schema can traverse this session path

- timestamp: 2026-08-20T17:01:07+02:00
  checked: firmware AgentProjection::captureFocusIntent, FrameCodec::encode, v2 payload parser, and DeviceSession
  found: PENDING is set only after a binding is captured, immediately before sendFrame; firmware emits an LF-terminated v2 dict with exactly action_id, agent_session, entry_id, host_epoch, pane_id, slot, snapshot_revision, source_revision, terminal_id, while DeviceSession accepts any UTF-8 JSON dict and the caller filters only type == focus_intent
  implication: the observed PENDING proves the device path captured an actionable old binding; schema rejection cannot occur in the current host reader, so the remaining timeout is either lost raw bytes/device TX or a byte-stream parsing boundary

- timestamp: 2026-08-20T17:05:54+02:00
  checked: exact /dev/ttyACM0 hello, fresh-epoch revision-1 snapshot, and metrics probe
  found: hello activated session host-session-3da1eb29fc4e; firmware accepted and committed revision 1 under phase22-probe-c363d9e5fc16c17e; malformed, digest_mismatch, duplicate, out_of_order, and rejected metrics were all zero
  implication: a fresh epoch is sufficient to restore low-revision admission on the real device, confirming the hardcoded epoch/revision reset root cause without any firmware or timeout change

- timestamp: 2026-08-20T17:07:31+02:00
  checked: red/green fresh-epoch regression and seven-case DeviceSession serial-boundary replay
  found: the epoch regression failed on 6bc68ce with TypeError because host_epoch was hardcoded, then passed after injection; all narrow smoke tests pass, including fragmentation at 1/63/255 bytes, LF/CRLF, back-to-back lines, boot chatter, invalid UTF-8/non-JSON, stale probe ACK, and exact v2 schema/version assertions
  implication: the corrected host setup is deterministic and the known parser/filter variants do not reproduce the remaining live loss; tagged live boundary evidence is now required

- timestamp: 2026-08-20T17:12:42+02:00
  checked: first corrected tagged live nominal run and user-visible panel state
  found: all fresh-epoch snapshots were accepted; KEY-1 produced one complete 417-byte LF v2 focus_intent with all nine exact fields and DeviceSession parsed it, but the panel transitioned BLOCKED -> PENDING -> UNCERTAIN -> BLOCKED after the host sent nominal focus_result
  implication: host RX buffering/schema/filter hypotheses are eliminated for this run; the defect is now isolated to outbound focus_result delivery, protocol admission, or device semantic application

- timestamp: 2026-08-20T17:14:23+02:00
  checked: bounded result-seam trace preparation
  found: the first armed attempt timed out because no physical key arrived in its 10-second window; replacement supervised process phase22-result-checkpoint is persistent, connected, and paused safely at the pre-arm ENTER prompt with [DEBUG-PHASE22-FRAME] TX/RX/write-count and post-result metrics probes loaded in memory
  implication: every non-human probe is exhausted; one synchronized physical KEY-1 is now the minimal action that will distinguish write/admission rejection from semantic apply rejection without another setup race

- timestamp: 2026-08-20T17:24:47+02:00
  checked: exact result-seam trace chronology and firmware pending deadline
  found: first action device-3208169987 was answered with a complete admitted 453-byte result; second action device-3230836995 arrived 22.667008s later before metrics_ack and was unanswered; the first action was already more than 3s old when answered
  implication: the user made one current press, but the driver first consumed a stale pre-arm action accumulated while blocked in input(); this is a deterministic guided-driver sequencing defect, not a schema, transport, or 23-second debounce defect

- timestamp: 2026-08-20T17:28:27+02:00
  checked: agent-authored red/green pre-arm and unmatched-request replays
  found: before the fix, the driver-level setup replay recorded discard_counts [0,0] and the metrics-request replay permanently dropped focus_intent then timed out; after the fix, all 10 narrow smoke tests pass, including clearing complete/partial stale bytes, preserving a queued focus intent across an unrelated reply, and selecting the exact fresh action
  implication: both deterministic loss mechanisms from the live trace are closed without changing frame schema, timeout, or firmware input semantics
## Resolution

root_cause: "Two Phase 02.2 guided-driver causes were confirmed: reruns reset snapshot revisions under a reused host_epoch so firmware rejected every setup snapshot; input() then paused serial consumption without an arming boundary, allowing an expired pre-arm focus_intent to be answered while the operator's current intent was ignored. Request also dropped unmatched valid focus_intent frames while waiting for replies."
fix: "Generate one fresh opaque host_epoch per run; retain up to 16 focus_intents across unrelated request replies; immediately after readiness ENTER clear queued/internal/OS pre-arm input and print an explicit ARMED instruction before waiting for the next exact intent."
verification:
  target_test: { result: pass, tests: ["test_device_run_uses_one_fresh_epoch_per_process", "test_pre_arm_discard_removes_stale_complete_and_partial_intents", "test_request_preserves_unmatched_focus_intent_for_later_wait"] }
  mutation_check: { result: pass, mutant_killed: true, details: "Repeated-epoch mutant and removal of pre-arm discard/preservation each reproduce the red assertions." }
  no_op_deletion: { result: pass, deletion_justified_by_rca: false }
  adjacent_tests: { result: pass, suites_run: ["10 narrow Phase 02.2 smoke tests via project venv manual runner"] }
  revert_and_reconfirm: { result: pass, bug_returned_on_revert: true, fixed_on_reapply: true, details: "Both agent-authored tests were observed red before their source changes and green after." }
  guardrail_verdict: pass
  commit: "53d8dc6"
  physical_confirmation: "After the explicit ARMED prompt, one KEY-1 press showed PENDING then FOCUSED. The corrected driver preserved the matching focus intent/result path."
oracle_type: specified
files_changed: ["tools/phase1_bringup/src/phase1_bringup/phase22_smoke.py", "tools/phase1_bringup/test_phase22_smoke.py"]
