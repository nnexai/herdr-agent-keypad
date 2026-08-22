---
status: awaiting_human_verify
trigger: "Fix the remaining WR-05 host regression: one bad-digest or mismatched boot/session metrics response is accepted instead of timing out."
created: 2026-08-20T18:27:29+02:00
updated: 2026-08-20T18:30:13+02:00
---

## Current Focus

reasoning_checkpoint:
  hypothesis: The other-boot subcase is accepted because the test bypasses hello(), leaving _device_boot_id unset; _read_frame therefore treats the mismatched metrics_ack as the first identity-bearing frame.
  confirming_evidence:
    - DeviceSession._read_frame assigns frame boot_id when _device_boot_id is None, before comparing it.
    - The targeted test sets only session_id, while DeviceSession.hello is the production path that binds _device_boot_id from hello_ack.
    - Canonical classify_line rejects the bad digest, and the explicit session comparison rejects other-session before boot adoption.
  falsification_test: A source trace showing the test calls hello() or initializes _device_boot_id before the other-boot response would disprove the hypothesis.
  fix_rationale: Make the fixture perform a valid hello/hello_ack before every invalid metrics response, preserving pre-hello boot discovery while exercising the required post-hello identity enforcement.
  blind_spots: No validation command will be run by explicit assignment; the orchestrator will execute the 15-test manual gate.
  candidate_causes:
    - code: DeviceSession post-hello validation might omit the bound boot comparison.
    - data: The regression fixture might omit the hello/hello_ack identity-binding precondition.
  and_gate: no; the fixture omission alone explains the accepted other-boot frame, while source inspection disproves the code-guard branch.
next_action: Orchestrator reruns the 15-test Phase 02.2 manual gate and confirms the post-hello rejection test passes.

## Symptoms

expected: After hello binds device boot ID and host session ID, bad-digest, other-boot-ID, and other-session-ID responses cannot satisfy request() and each causes TimeoutError.
actual: A fresh manual run passed 14/15 smoke tests; test_session_rejects_bad_digest_and_mismatched_identity did not raise TimeoutError for one subcase.
errors: "Failed: DID NOT RAISE <class 'TimeoutError'>"
reproduction: Run tools/phase1_bringup/test_phase22_smoke.py::test_session_rejects_bad_digest_and_mismatched_identity against fresh imports; subcases are bad digest, other boot ID, and other session ID.
started: Observed after commit 97e90b0 in the Phase 02.2 manual gate.

## Eliminated


## Evidence



- timestamp: 2026-08-20T18:28:24+02:00
  checked: Knowledge base and semantic recall
  found: No matching prior DeviceSession identity-validation resolution; the only related KB entry concerns device payload digest canonicalization.
  implication: Treat the current regression as a fresh deterministic protocol-fixture issue.
- timestamp: 2026-08-20T18:28:24+02:00
  checked: protocol.classify_line and validate_frame
  found: A bad canonical payload digest is rejected before DeviceSession sees a frame, and a different session_id is rejected at DeviceSession._read_frame line 184.
  implication: Bad digest and other-session cannot satisfy request().
- timestamp: 2026-08-20T18:28:24+02:00
  checked: DeviceSession._read_frame, hello, and the targeted test fixture
  found: _read_frame intentionally adopts the first accepted frame boot_id while _device_boot_id is None so hello_ack can establish identity; hello() then stores that boot ID. The test sets session_id directly but never calls hello(), so the other-boot metrics_ack becomes the adopted identity and satisfies reply_to/type checks.
  implication: Exactly the other-boot subcase is accepted; the fixture does not establish the precondition named in the test contract.
- timestamp: 2026-08-20T18:29:07+02:00
  checked: Commit 97e90b0 diff
  found: The commit introduced the regression test with direct session_id assignment but no hello exchange; the production run still calls session.hello() before later requests.
  implication: The regression test, not the DeviceSession production validation path, violates the stated post-hello precondition.
## Resolution

root_cause: The regression fixture skipped hello/hello_ack, so _device_boot_id remained unset and the intentional pre-hello binding branch adopted the other-boot metrics response as the session identity.
fix: The targeted regression fixture now performs a canonical valid hello/hello_ack exchange before each bad-digest, other-boot, or other-session metrics response. Post-hello requests use sequence/reply_to 2.
verification: Complete diff and commit-scope inspection confirmed canonical hello binding, fresh metrics sequence/reply_to 2, and a one-file commit. No validation commands run by explicit assignment constraint; orchestrator will rerun the 15-test manual gate. Commit c0c4f99.
files_changed: [tools/phase1_bringup/test_phase22_smoke.py]
