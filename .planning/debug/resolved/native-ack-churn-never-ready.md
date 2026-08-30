---
status: resolved
trigger: "After deploying the cancellation-safe, nonblocking native runtime, the sole bridge owns /dev/ttyACM0 but remains stale/device_unavailable indefinitely; user still requires fresh Codex, focus switching, hold-to-speak, and no autonomous menu openings."
created: 2026-08-30T10:42:02Z
updated: 2026-08-30T11:02:13Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "two coordinator transition defects create an indefinite gate: accepted exact ACKs establish readiness only after publication quiescence, and sent publications have no ACK expiry/recovery deadline"
  confirming_evidence:
    - "isolated invalidation-before-exact-ACK test fails because device_ready remains false while the next coalesced publication is pending"
    - "isolated focus-during-coalescing test fails because pending_focus remains queued after an exact accepted ACK"
    - "isolated no-ACK test observes one open for 500 ms and fails because no reconnect occurs"
  falsification_test: "the hypothesis would be false if current code made all three deterministic cases pass without relaxing the exact ACK predicate or transport session fences"
  fix_rationale: "track authenticated USB link health independently from publication generation usability; exact ACK immediately proves link health, coalescing continues separately, and a per-publication deadline closes the authenticated session and schedules bounded reconnect if no exact ACK arrives"
  blind_spots: "live device timing is intentionally untested by assignment; isolated tests cannot prove which of churn or missing ACK occurred in the deployed process, so both independently proven defects are fixed"
  candidate_causes:
    - "code: one device_ready flag conflates accepted link identity with generation quiescence"
    - "code: PendingPublication and the run loop omit an ACK expiry transition"
    - "environment: continuous Herdr invalidation makes the quiescence requirement unreachable"
    - "data: a missing or mismatched device reply leaves the sent generation unusable"
  and_gate: "no single AND-gate: either coordinator defect independently creates indefinite not-ready when its trigger occurs; the deployed trigger remains unobserved, but both are deterministic root causes within the required acceptance surface"
oracle_type: specified
bug_class: concurrency
next_action: "none for the ACK churn and timeout defects; autonomous menu opening remains outside this fix and requires later passive observation"

## Symptoms

expected: one accepted exact snapshot ACK establishes a usable device path, later coalesced updates continue without starving focus or Codex, and a missing/rejected ACK produces bounded recovery with a useful safe error
actual: after one controlled restart the sole native process owns the serial FD indefinitely but status remains stale/device_unavailable; focus and hold remain unusable
errors: status has last_error null and reconnect_attempt 0 despite persistent device_unavailable
reproduction: start fixed native bridge with live Herdr event churn and observe device_unavailable after serial ownership and snapshot publication
started: immediately after deploying commit 0f97b87

## Eliminated

- hypothesis: live ACK field mismatch is required to explain indefinite not-ready
  evidence: all three indefinite-gate RED cases reproduce with accepted exact ACKs or no reply; five wrong ACK field cases fail closed immediately with payload_rejected
  timestamp: 2026-08-30T10:55:58Z

## Evidence

- timestamp: 2026-08-30T10:46:08Z
  checked: complete RuntimeCoordinator publication, ACK, readiness, focus-drain, and run-loop transitions
  found: exact ACK acceptance is correct, but device_ready becomes true only when publication_dirty is false; invalidation also clears device_ready before and after coalescing
  implication: continuous invalidation can deterministically accept every exact ACK yet never authorize focus draining or report device link ready
- timestamp: 2026-08-30T10:46:08Z
  checked: PendingPublication fields and every run-loop deadline branch
  found: pending publications carry no ACK deadline and the loop has no timeout branch; only Herdr reconnect, USB reconnect, and Codex deadlines exist
  implication: one sent publication with no reply remains pending indefinitely and status retains null last_error with zero reconnect attempts
- timestamp: 2026-08-30T10:46:08Z
  checked: USB SnapshotAck acceptance predicate and transport session validation
  found: reply_to, accepted, host_epoch, snapshot_revision, source_status, device boot/session, monotonic sequence, and digest fences are exact
  implication: recovery must preserve these fences; weakening identity admission is neither necessary nor safe
- timestamp: 2026-08-30T10:49:44Z
  checked: "cargo test core::orchestrator::tests:: --lib -- --nocapture"
  found: "RED: 5 passed, 3 failed; dirty-before-ACK readiness, focus-during-coalescing, and no-ACK bounded reconnect each failed on its specified symptom"
  implication: "both ranked code hypotheses are confirmed; live ACK mismatch is not required to reproduce either indefinite gate"
- timestamp: 2026-08-30T10:55:58Z
  checked: final focused coordinator, resource-bound, USB fence, and production status tests
  found: "GREEN: coordinator 10/10; resource bound 1/1; USB identity/reply fences 2/2; production status surface 1/1"
  implication: "accepted exact ACKs, coalesced generations, focus intents, Codex cadence, bounded timeout recovery, safe status, and negative identity fences progress without weakening admission"
- timestamp: 2026-08-30T10:55:58Z
  checked: temporary diagnostics and mutation tooling
  found: "no new debug logging was added; cargo-mutants is unavailable, so mutation checking is explicitly skipped"
  implication: "the agent-authored RED-before/GREEN-after cases and held-out focused tests provide the available fix guardrail"
- timestamp: 2026-08-30T11:02:13Z
  checked: "session-manager focused GREEN integration and atomic source/test commit"
  found: "coordinator 10/10 and four held-out cases 1/1 each passed; source and tests committed atomically as 4137f14"
  implication: "authenticated ACK readiness, bounded timeout recovery, resource bounds, USB identity/session/reply fences, and the production status surface are preserved by focused executable guards"
- timestamp: 2026-08-30T11:02:13Z
  checked: "clean locked release build, existing-plugin staging, and byte identity"
  found: "cargo clean --release and cargo build --locked --release succeeded; built and staged /home/nnex/.local/share/herdr/plugins/herdr-keypad/bin/herdr-keypad binaries both have SHA-256 32c88f253f6dac46b0633438156f7a10b089f8d39ff9f2bd928fde9378497651 and cmp reports exact identity"
  implication: "the Herdr plugin path contains the verified release bytes before authority replacement"
- timestamp: 2026-08-30T11:02:13Z
  checked: "exactly one Herdr-managed host restart, native process/serial ownership, Python absence, and bounded read-only status"
  found: "herdr plugin action restart count=1; old native PID 1152589 exited; exactly one new native PID 1248978 owns FD 9 -> /dev/ttyACM0; no python.*herdr[_-]keypad process exists; status reports state=ready, device_state=ready, herdr_state=running, codex_state=ready, reconnect_attempt=0, backoff_ms=0, last_error=null"
  implication: "the authenticated exact ACK establishes live device link health under publication churn, the aggregate returns truthfully to ready, and production remains a single native authority"
- timestamp: 2026-08-30T11:02:13Z
  checked: "live-interaction boundary"
  found: "no firmware command, probe, focus action, menu/encoder/key stimulus, or physical UAT was performed"
  implication: "the coordinator readiness defect is resolved, but autonomous menu opening was neither observed nor verified fixed and remains explicitly outside this claim"

## Resolution

root_cause:
  - accepted exact snapshot ACK link health is incorrectly gated on publication_dirty becoming quiescent, so continuous coalescing never establishes readiness or drains focus
  - PendingPublication has no bounded ACK deadline or expiry transition, so a missing ACK remains pending forever without reconnect or safe error evidence
oracle_type: specified
fix:
  - renamed the coordinator state to device_link_ready and made one accepted exact ACK establish authenticated link health before sending any coalesced generation
  - kept Herdr generation usability separate: invalidation publishes the actual stale generation and aggregate readiness stays stale while the USB link can remain ready
  - added a validated per-publication ACK deadline; expiry closes the authenticated USB session, clears session-bound focus work, records device_unavailable, and schedules bounded reconnect
  - made stale/offline focus drain once the authenticated link is usable so FocusExecutor returns a bounded safe result instead of waiting for publication quiescence
  - surfaced bounded USB reconnect_attempt, backoff_ms, and allowlisted last_error evidence; mismatched ACKs report payload_rejected
  - encoded empty-identity slots as empty while preserving stale occupied identities, allowing truthful stale coalesced publications
verification:
  target_test: { result: pass, command: "cargo test core::orchestrator::tests:: --lib -- --nocapture", count: "10 passed" }
  mutation_check: { result: skipped, reason: "cargo-mutants is not installed" }
  no_op_deletion: { result: pass, deletion_justified_by_rca: false }
  adjacent_tests:
    result: pass
    suites_run:
      - "resource_bounds queue_payload_and_timer_limits_are_closed_and_validated: 1 passed"
      - "usb_platform exact_hello_then_snapshot_ack_preserves_focus_and_reply_fences: 1 passed"
      - "usb_platform same_boot_id_reconnects_with_fresh_host_session_and_rejects_old_frames: 1 passed"
      - "production_surface production_binary_start_status_stop_owns_control_socket_for_authority_lifetime: 1 passed"
  revert_and_reconfirm: { result: pass, bug_returned_before_fix: true, fixed_on_reapply: true, red_count: "3 failed", green_count: "10 passed" }
  guardrail_verdict: accepted
files_changed:
  - host/herdr_keypad/native/src/core/orchestrator.rs
  - host/herdr_keypad/native/tests/resource_bounds.rs
  physical_verification: "One Herdr-managed host bridge restart replaced native PID 1152589 with native PID 1248978. The replacement alone owns FD 9 -> /dev/ttyACM0, no Python keypad production process exists, and read-only status converged to running/ready/running/ready with reconnect_attempt=0, backoff_ms=0, and last_error=null. No firmware, device stimulus, focus/menu/encoder action, or physical UAT occurred; autonomous menu opening is not claimed fixed."
postmortem:
  why_not_caught: "No coordinator regression gate independently modeled authenticated ACK link health under endless generation invalidation or expired a sent publication that never receives an ACK."
  recurrence_guard: "The coordinator tests invalidation_before_an_exact_ack_still_establishes_link_readiness, focus_waiting_during_coalesced_publication_gets_a_bounded_result, sent_publication_without_ack_reconnects_within_the_bounded_deadline, mismatched_snapshot_ack_fields_never_establish_link_readiness, and ack_timeout_recovery_surfaces_bounded_safe_status now cover both defects and preserve fail-closed fences."
