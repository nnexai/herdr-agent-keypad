---
status: resolved
trigger: "Fix the confirmed Phase 4 native bridge lifecycle bug: start acquires/holds bridge.lock but never creates/binds bridge.sock, so status falsely reports stopped and stop cannot control the running native authority."
created: 2026-08-30T08:30:05+02:00
updated: 2026-08-30T08:42:25+02:00
---

## Current Focus

bug_class: bohrbug
reasoning_checkpoint:
  hypothesis: RuntimeCoordinator holds LifecycleOwner's AuthorityLock but never binds or serves its existing ControlEndpoint, so clients cannot reach the only authority and main.rs falls back to synthetic stopped/stop replies.
  confirming_evidence:
    - The real-binary regression left bridge.lock in the isolated state directory while bridge.sock was absent.
    - Repository-wide callsite search found no production caller of bind_control, accept_same_user, or receive_request.
    - The locked coordinator contract assigns control requests to RuntimeCoordinator's Tokio select.
  falsification_test: A production caller that binds bridge.sock and dispatches requests against RuntimeCoordinator's LifecycleOwner would disprove the hypothesis; no such caller exists, and adding that path should make the exact RED test pass.
  fix_rationale: Bind the endpoint from LifecycleOwner, serve it in RuntimeCoordinator's existing select, dispatch requests through LifecycleOwner, exit on stop, and unlink the endpoint while AuthorityLock still owns the lock.
  blind_spots: The regression runs on Linux only; the same UnixListener API is compiled for the supported macOS target but is not executed here.
  candidate_causes:
    - code: The integration phase omitted the control branch from RuntimeCoordinator despite implementing the transport.
    - config: A wrong HERDR_PLUGIN_STATE_DIR could place the endpoint elsewhere, but the isolated failed sandbox contained bridge.lock in the expected state directory.
    - environment: A stale endpoint or permission failure could prevent binding, but the failed sandbox had no bridge.sock and the state directory was created with the expected lock.
  and_gate: no; the missing production callsite alone explains the deterministic absence under an isolated valid configuration.
next_action: None; automated production lifecycle and locked adjacent suites passed, and the fix is ready to commit.

## Symptoms

expected: A successful start owns bridge.lock and bridge.sock; status reaches the authority and reports running; stop ends the authority; later status reports stopped.
actual: start acquires and holds bridge.lock but never creates bridge.sock, so status reports stopped and stop cannot control the running authority.
errors: No control endpoint exists after successful start.
reproduction: Launch the real native binary with isolated HERDR_PLUGIN_CONFIG_DIR, STATE_DIR, HERDR_SOCKET_PATH, HERDR_BIN_PATH, and HOME; run start, inspect bridge.sock, then run status and stop.
started: Confirmed during Phase 4 native bridge validation.

## Eliminated

- hypothesis: HERDR_PLUGIN_STATE_DIR points clients at a different directory than the authority.
  evidence: The failed isolated sandbox contained bridge.lock in the exact configured state directory and no bridge.sock anywhere under that sandbox.
  timestamp: 2026-08-30T08:37:25+02:00

- hypothesis: A stale socket or filesystem permission error prevents binding.
  evidence: No production code attempted bind_control, and the isolated state directory contained no stale bridge.sock.
  timestamp: 2026-08-30T08:37:25+02:00

## Evidence

- timestamp: 2026-08-30T08:33:17+02:00
  checked: Real binary production_surface lifecycle regression with isolated config, state, socket, binary, PID, and HOME.
  found: The start child remained alive for five seconds, but state/bridge.sock never appeared; the exact test failed at \"successful start never created bridge.sock\".
  implication: The reported missing endpoint is deterministic and reproduced through the production binary, not a unit-only path.

- timestamp: 2026-08-30T08:33:17+02:00
  checked: Repository callsites for AuthorityLock::bind_control and ControlEndpoint request methods.
  found: bind_control, accept_same_user, and receive_request have no production callsite; only request_control exists in main.rs.
  implication: The transport was implemented but never connected to the production authority.

- timestamp: 2026-08-30T08:37:25+02:00
  checked: Failed integration sandbox filesystem.
  found: The configured state directory contained bridge.lock and no bridge.sock.
  implication: The process acquired the intended authority lock, ruling out wrong-path configuration and confirming the missing bind step.

- timestamp: 2026-08-30T08:37:25+02:00
  checked: Locked Phase 04-07 coordinator contract.
  found: RuntimeCoordinator's Tokio select is required to handle bounded control requests.
  implication: Adding orchestrator.rs is a necessary, approved scope expansion rather than a second control-service design.

- timestamp: 2026-08-30T08:42:25+02:00
  checked: Exact real-binary regression after the fix.
  found: 1 test passed in 0.03s; start created bridge.sock, status reported running with bounded source states, stop returned success, the authority exited, the socket disappeared, and final status reported stopped.
  implication: The original production symptom is fixed through the shipped binary without hardware.

- timestamp: 2026-08-30T08:42:25+02:00
  checked: Locked lifecycle_resource and production_surface suites.
  found: 15 tests passed across 2 suites in 0.51s with zero failures.
  implication: The changed lifecycle, control transport, and production entrypoint behavior retain their adjacent contracts.

- timestamp: 2026-08-30T08:42:25+02:00
  checked: Revert-and-reconfirm guardrail.
  found: Reversing only the three production source diffs restored the exact missing-bridge.sock failure after five seconds; reapplying them restored the 0.03s pass.
  implication: The source fix, rather than a weakened test or environmental change, removes the bug.

## Resolution

root_cause: RuntimeCoordinator omitted the production control endpoint binding and request branch, leaving its LifecycleOwner reachable only in-process while main.rs clients depended on bridge.sock.
fix: RuntimeCoordinator now binds LifecycleOwner's control endpoint, serves bounded same-user requests in its Tokio select, dispatches lifecycle policy through LifecycleOwner, and exits after stop; AuthorityLock unlinks bridge.sock before releasing exclusivity.
verification:
  target_test: {result: pass}
  mutation_check: {result: skipped, reason_if_skipped: no Rust mutation runner is configured for this crate, mutant_killed: false}
  no_op_deletion: {result: pass, deletion_justified_by_rca: false}
  adjacent_tests: {result: pass, suites_run: [lifecycle_resource, production_surface]}
  revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true}
  guardrail_verdict: accepted
oracle_type: specified
files_changed: [host/herdr_keypad/native/src/core/orchestrator.rs, host/herdr_keypad/native/src/ports/control.rs, host/herdr_keypad/native/src/ports/lifecycle.rs, host/herdr_keypad/native/tests/lifecycle_resource.rs, host/herdr_keypad/native/tests/production_surface.rs, .planning/debug/native-control-socket-startup.md]
