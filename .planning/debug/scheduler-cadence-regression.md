---
status: awaiting_human_verify
trigger: "Investigate firmware scheduler metrics: allocation_stable=0; animation_duty_max_percent=316; compose_flush_max_us=107587; max_display_flush_us=140342; max_key_poll_gap_us=225914; frame_count=1422; full=0 half=1 static=1421; level_changes=2843; loop_wall_max_us=225902. Build a deterministic host regression at the main-loop cadence seam, fix bounded cadence accounting and Static recovery oscillation, keep polling within 120ms or expose hard failure, pass focused native tests and selected-usb build, commit source and test atomically, and do not deploy or edit physical evidence."
created: 2026-08-21T00:00:00Z
updated: 2026-08-21T16:05:00Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: current frame cost is divided by a prior pre-frame cadence interval, and timer-only Static recovery promotes without performance evidence; outer-loop-only poll and heap baselines measure the wrong seams
  confirming_evidence:
    - focused native regression deterministically reports 322% for a 107,587us frame at the production 33,334us cadence
    - exact device level_changes=2843 is two changes per 1422 frames, matching Static-to-Half timer promotion followed by Half-to-Static cost rejection
    - production snapshot code polls between panels but main records only loop-start polls, while allocation_stable compares unrelated loop-wide heap states
  falsification_test: if completion-to-completion windows still exceed 100%, Static changes more than twice under eight 107,587us frames, actual BoardAdapter poll gaps still span multi-panel work, or equal before/after frame heap samples report unstable, the hypothesis is wrong
  fix_rationale: use completed-frame timestamps and bounded duty arithmetic, recover Static only from a measured cheap frame, measure polling at BoardAdapter.update and allocations across the frame transaction, and bound serial admission to one frame before optional decoration
  blind_spots: exact panel timings and allocator behavior require the orchestrator's later rebuild/upload capture; this task verifies native behavior and selected-usb compilation only
  candidate_causes:
    - code: mismatched cadence timestamps, unconditional timer recovery, and metrics attached above the actual poll/allocation seams
    - environment: 100-140ms physical multi-panel SPI cost exposes arithmetic and starvation paths hidden by zero-cost native display stubs
  and_gate: yes; the regression requires the code-accounting defects plus physical frame cost exceeding the 33,334us nominal cadence, and all accounting defects must be corrected
next_action: orchestrator rebuilds/uploads commit 92320a78f23252074e5d41574d4c0051fa52d35b and captures exact-device metrics; no deployment or evidence change was performed here

## Symptoms

expected: ordinary 100-140ms complete frames select a sustainable degradation level, duty never exceeds 100%, animation quality does not toggle every frame, allocation remains stable, and input polling remains within 120ms unless a real hard failure is surfaced
actual: allocation_stable=0; animation_duty_max_percent=316; compose_flush_max_us=107587; max_display_flush_us=140342; max_key_poll_gap_us=225914; frame_count=1422; full=0 half=1 static=1421; level_changes=2843; loop_wall_max_us=225902
errors: exact-device runtime metrics violate cadence, allocation stability, and input responsiveness ceilings despite native tests and build passing
reproduction: ordinary operation followed by logical capture on the attached keypad running binary 380878...
started: post-review regression in the current deployed binary

## Eliminated

## Evidence

- timestamp: 2026-08-21T15:35:00Z
  checked: MemPalace recall and .planning/debug/knowledge-base.md
  found: no prior resolved scheduler/cadence regression matched the reported metrics
  implication: proceed from current code and exact metric behavior rather than assuming a known pattern

- timestamp: 2026-08-21T15:47:00Z
  checked: firmware/src/main.cpp loop and AnimationScheduler call ordering
  found: main passes the loop-start timestamp to observeFlushCostAt after the frame completes; the scheduler divides the current frame cost by the interval between prior loop starts and can pair unlike frames
  implication: the numerator and denominator do not describe the same completed interval, so a single-threaded frame can report impossible duty above 100%

- timestamp: 2026-08-21T15:47:00Z
  checked: Static recovery state transition
  found: advanceCadence promotes Static to Half after one 33,334us base period without a measured low-cost frame, and the following 107,587us frame immediately returns Half to Static
  implication: the exact 2843 level changes for 1422 frames are the deterministic two-transition recovery oscillation

- timestamp: 2026-08-21T15:47:00Z
  checked: snapshot and animation panel flush loops
  found: AgentProjection already polls BoardAdapter between snapshot panels, but main measures only outer-loop board.update timestamps; animation multi-panel flushes do not poll between panels
  implication: max_key_poll_gap_us=225914 is not the actual hardware polling seam and can both over-report existing inter-panel polls and miss the need to interleave animation panel flushes

- timestamp: 2026-08-21T15:47:00Z
  checked: ProofMetrics allocation_stable derivation
  found: every loop heap sample is compared forever with the first post-reset sample, so protocol JSON and other non-frame runtime activity latch allocation_stable=0
  implication: the metric does not test the UI-SPEC invariant of equal heap before and after each composed frame

- timestamp: 2026-08-21T15:50:00Z
  checked: pio test -e native-agent-projection with the new cadence regression
  found: test_main_loop_cadence_bounds_duty_and_does_not_oscillate_static failed deterministically because max duty was 322%, while 96 adjacent tests passed
  implication: the regression is red-capable at the production scheduler seam and directly reproduces the impossible-duty symptom

- timestamp: 2026-08-21T16:01:00Z
  checked: focused native suite after the fix
  found: native-agent-projection passed 98 of 98 tests, including cadence and allocation metric regressions
  implication: bounded duty, stable Static selection, frame allocation pairing, and adjacent presentation/input contracts are green

- timestamp: 2026-08-21T16:01:00Z
  checked: selected-usb production compile
  found: selected-usb completed successfully with a 521871-byte image and no compile/link errors
  implication: the firmware integration, ESP heap probes, and BoardAdapter poll tracking compile for the selected device target

## Resolution

root_cause: pre-frame/cross-frame cadence accounting and timer-only recovery combine with physical frame cost to oscillate Static; poll and allocation metrics are attached to outer-loop state instead of their actual BoardAdapter/frame transaction seams
fix: observe frames at completion with duty bounded by the non-overlapping frame cost; recover Static only from measured cheap work; pair heap samples around each animation frame; track gaps inside BoardAdapter.update, poll after every panel flush, dispatch input after admission, and process at most one serial frame before optional decorative work
verification:
  target_test: {result: pass}
  mutation_check: {result: skipped, reason_if_skipped: no Stryker or C++ mutation runner is configured; the original implementation served as the killed pre-fix mutant}
  no_op_deletion: {result: pass, deletion_justified_by_rca: true}
  adjacent_tests: {result: pass, suites_run: [native-agent-projection 98/98, selected-usb compile]}
  revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true}
  guardrail_verdict: accepted
files_changed: [firmware/src/main.cpp, firmware/src/ui/animation.h, firmware/src/metrics/proof_metrics.h, firmware/src/board/board_adapter.h, firmware/src/board/board_adapter.cpp, firmware/src/app/agent_projection.cpp, test/test_agent_projection/test_main.cpp]
