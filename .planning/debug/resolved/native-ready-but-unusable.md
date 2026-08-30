---
status: resolved
trigger: "codex status says age 7m, focus switch is not working (and thus voice input also does not work) so now i do not see this as ready or running"
created: 2026-08-30T10:11:12Z
updated: 2026-08-30T10:38:26Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "Two coordinator/USB ownership defects compound: RuntimeCoordinator synchronously awaits snapshot ACK while UsbPort::poll assembles each frame in a future-local Vec that tokio::select cancellation discards; partial focus/ACK frames are corrupted, forcing reconnect/publication churn, and synchronous publication then starves Codex deadlines and focus results. Aggregate status independently remains running."
  confirming_evidence:
    - "isolated RED: snapshot publication timed out while fake device withheld ACK until focus_result"
    - "UsbPort::read_bounded_line consumes serial bytes into a future-local Vec, while RuntimeCoordinator cancels UsbPort::poll whenever any sibling select branch wins"
    - "receive_v2 resets the entire link on the malformed suffix left after a cancelled partial read"
    - "RuntimeCoordinator::status overwrites component states but leaves lifecycle aggregate state as running"
  falsification_test: "split a valid focus frame, cancel poll after its prefix is consumed, then resume; cancellation-loss is false if the complete focus intent is recovered without reconnect. Publication ownership is false if focus result and Codex cadence progress while ACK is withheld."
  fix_rationale: "persist partial receive bytes in UsbPort across select cancellation, split snapshot send from ACK receipt, preserve reply-to/session/source fences on polled ACK, and derive aggregate readiness from required component liveness"
  blind_spots: "physical menu cannot be reproduced under the hardware freeze; static routing rules out native frames directly invoking menu click, but repeated CDC lifecycle may correlate with an independent physical/library ghost input"
  candidate_causes:
    - "code: cancellation-unsafe partial-frame assembly plus synchronous snapshot ACK wait"
    - "environment/data: split CDC delivery and delayed ACK/focus interleaving exercise both defects"
  and_gate: "yes: split delivery corrupts/reconnects the live link; delayed ACK then monopolizes the coordinator; independent status aggregation reports running"
bug_class: deterministic concurrency/cancellation Bohrbug
live_interaction_authorization: one explicitly authorized host-only plugin restart and read-only status/PID/FD/hash diagnostics were performed; firmware commands, probes, focus/encoder/menu stimuli, and physical UAT remained forbidden
next_action: "none for the coordinator starvation defect; track autonomous periodic menu opening separately because it was neither stimulated nor verified fixed"

## Symptoms

expected: Codex observation age refreshes on schedule, pressing an occupied agent key focuses its exact pane, deliberate hold then authorizes held Space, and ready means all three live paths are usable
actual: Codex display remains at age 7m, focus switching does not work, voice hold cannot work, and the device menu opens autonomously every couple of minutes while the native bridge runs; public status still claims ready/running
errors: no trusted host error is surfaced; device behavior contradicts status
reproduction: leave the native bridge running; every couple of minutes the device menu opens autonomously, Codex age reaches 7m without refresh, then pressing an occupied agent key produces no focus switch and deliberate hold cannot be authorized
started: observed immediately after deploying the already-focused structured-session fix

## Eliminated

- hypothesis: "periodic native snapshot/reconnect traffic directly synthesizes encoder-click/menu input"
  evidence: "the native closed v2 output set contains only agent_snapshot and focus_result; firmware dispatch handles those as projection/focus data, while menuController.click is reachable only from ProductInputRouter EncoderClick populated by board.consumePressed(4)"
  timestamp: 2026-08-30T10:17:41Z
- hypothesis: "bounded Codex or Herdr calls alone explain the 7-minute coupled stall"
  evidence: "Codex collection is deadline-bounded to 15 seconds plus bounded child shutdown and Herdr calls to 2 seconds; the isolated USB ACK/focus cycle reproduces indefinite ownership without either source"
  timestamp: 2026-08-30T10:17:41Z
- hypothesis: "USB reconnect resets or drops codex_due"
  evidence: "codex_due is assigned after collection and cleared only when its own select branch fires; USB connect/disconnect paths do not mutate it"
  timestamp: 2026-08-30T10:17:41Z

## Evidence



- timestamp: 2026-08-30T10:13:04Z
  checked: semantic debug-memory recall
  found: prior structured agent_session narrowing caused focus rejection but does not by itself explain simultaneous Codex timer staleness
  implication: preserve identity fences and test that prior pattern as a lower-ranked competing hypothesis while localizing the shared progression seam

- timestamp: 2026-08-30T10:15:16Z
  checked: production coordinator, USB publication loop, Codex collector bounds, and lifecycle status implementation
  found: RuntimeCoordinator awaits UsbPort::publish_snapshot on the sole event-loop task; that method loops until a matching ACK while consuming and queueing focus intents, so a continued valid stream can postpone return indefinitely; aggregate lifecycle state remains running regardless component states
  implication: H1 and H5 jointly explain coupled staleness plus misleading status and are falsifiable with an isolated continuous-focus/no-ACK harness

- timestamp: 2026-08-30T10:15:16Z
  checked: live-interaction audit after recurring device-menu report
  found: this investigation issued no live device, serial, USB, runtime-status, process-control, build, deploy, firmware, focus, restart, menu, or encoder action
  implication: autonomous physical menu opens were not caused by this debugger; all further work is restricted to static inspection and isolated targeted Rust tests

- timestamp: 2026-08-30T10:17:41Z
  checked: "cargo test --test usb_platform snapshot_publication_does_not_starve_focus_while_ack_is_pending -- --exact"
  found: "RED, 0 passed/1 failed: timed out after 50 ms at tests/usb_platform.rs because publish_snapshot waited for ACK while the fake device waited for the queued focus result"
  implication: "the production USB publication contract creates a deterministic circular wait that monopolizes the coordinator and jointly starves focus handling and Codex scheduling"

- timestamp: 2026-08-30T10:18:30Z
  checked: UsbPort poll cancellation path under RuntimeCoordinator tokio::select
  found: read_bounded_line accumulates consumed bytes in a future-local Vec; cancellation drops that prefix, and the next poll parses only the remaining suffix then reset_link closes the session
  implication: deterministic split-frame cancellation coverage is required; persistent bounded receive state is part of the root fix

- timestamp: 2026-08-30T10:21:34Z
  checked: "cargo test --test usb_platform cancelled_poll_preserves_a_split_focus_frame_for_resume -- --exact"
  found: "GREEN, 1 passed/0 failed after moving the bounded partial-line buffer into UsbPort so select cancellation preserves consumed prefixes"
  implication: "cancellation-safe ingress is confirmed without weakening sequence, session, digest, or line-bound validation"

- timestamp: 2026-08-30T10:30:57Z
  checked: "cargo test --lib core::orchestrator::tests::production_coordinator_advances_codex_cadence_and_focus_together -- --exact"
  found: "GREEN, 1 passed/0 failed in 0.05 s: the real RuntimeCoordinator observed at least two Codex collections, three acknowledged snapshot publications, and one exact accepted focus_result in the same isolated event loop"
  implication: "Codex timer cadence and focus-result handling now coexist after startup and queued publication without weakening Herdr or device identity fences"

- timestamp: 2026-08-30T10:30:57Z
  checked: "cargo test --lib core::orchestrator::tests::readiness_is_false_when_any_required_live_path_is_stalled -- --exact"
  found: "GREEN, 1 passed/0 failed: aggregate state is ready only for device ready + Herdr running + Codex ready and is stale for each independently stalled path"
  implication: "public readiness can no longer remain ready/running while a required live path is stalled"

- timestamp: 2026-08-30T10:30:57Z
  checked: focused adjacent suites
  found: "GREEN: usb_platform 20/20; coordinator unit slice 5/5; resource_bounds 5/5; herdr_parity 6/6; 36 focused tests passed, zero failed"
  implication: "startup/reconnect/session/source/security fences, cancellation resume, nonblocking publication, focus handling, cadence, readiness, and resource bounds remain covered"

- timestamp: 2026-08-30T10:36:28Z
  checked: authorized release build and exact staging
  found: "cargo build --release succeeded; built and installed binaries both hash to 3df1e9210f85b49879e29eafe8963e9b29811de24a713045c25c60bd6eacb355"
  implication: "the installed plugin contains the clean fixed release, but the old mapped process remains active until a Herdr-managed transition"

- timestamp: 2026-08-30T10:36:28Z
  checked: pre-transition process, serial ownership, status, and Python production
  found: "PID 1041804 still owns FD 9 -> /dev/ttyACM0; old runtime reports state=running with device_state=device_unavailable, herdr_state=running, codex_state=ready; no Python herdr-keypad production process exists"
  implication: "the old binary demonstrates the reported status-truthfulness defect and remains the only CDC owner; the unrelated Python github inbox daemon is outside keypad production"

- timestamp: 2026-08-30T10:36:28Z
  checked: supervised restart preflight
  found: "one direct restart preflight exited code 1 before runtime contact because its isolated launch lacked HERDR_PLUGIN_CONFIG_DIR; old PID and serial FD were unchanged and zero CDC lifecycle transitions occurred"
  implication: "the failed preflight did not perform a runtime restart; the only valid transition path is Herdr plugin action invocation, which supplies the required environment"

- timestamp: 2026-08-30T10:38:26Z
  checked: "single authorized Herdr-managed restart, post-transition process ownership, installed hash, and Python production absence"
  found: "old PID 1041804 exited; exactly one new native PID 1152589 owns FD 9 -> /dev/ttyACM0; release and installed plugin SHA-256 both equal 3df1e9210f85b49879e29eafe8963e9b29811de24a713045c25c60bd6eacb355; no Python herdr_keypad process exists"
  implication: "the clean native release is active with one serial owner and no production Python bridge after one actual host authority transition"

- timestamp: 2026-08-30T10:38:26Z
  checked: "post-restart read-only Herdr plugin status"
  found: "status action exited zero and reported state=stale, device_state=device_unavailable, herdr_state=running, codex_state=ready, with bridge_started as its only bounded transition"
  implication: "aggregate readiness now truthfully drops while the required device path is unavailable; the live process is not claimed ready or physically usable under the no-stimulus freeze"
## Resolution

root_cause: "Split CDC delivery plus cancellation-unsafe future-local receive buffering discards partial focus/ACK frames whenever another coordinator select branch wins, causing protocol reset/reconnect churn. Delayed/missing snapshot ACK plus synchronous publish_snapshot ownership then blocks the sole coordinator task, starving queued focus results and codex_due. Aggregate status independently remains running because required liveness is not folded into status.state."
oracle_type: specified
fix: "UsbPort now retains bounded partial line bytes across select cancellation. Snapshot send no longer waits for ACK; RuntimeCoordinator owns one exact pending publication, coalesces later snapshots, and validates ACK reply_to, host_epoch, snapshot_revision, source_status, device session, sequence, and digest before readiness. Aggregate state is ready only when device, Herdr, and Codex paths are live. The obsolete USB focus queue was removed; the bounded queue remains coordinator-owned."
verification:
  target_test: { result: pass }
  mutation_check: { result: skipped, reason_if_skipped: "no Rust mutation runner is configured; Stryker is not applicable", mutant_killed: false }
  no_op_deletion: { result: pass, deletion_justified_by_rca: true }
  adjacent_tests: { result: pass, suites_run: ["usb_platform 20/20", "orchestrator 5/5", "resource_bounds 5/5", "herdr_parity 6/6"] }
  revert_and_reconfirm: { result: pass, bug_returned_on_revert: true, fixed_on_reapply: true, evidence: "both agent-authored regressions failed on the pre-fix source and passed after the targeted source changes" }
  guardrail_verdict: accepted
  physical_verification: "One explicitly authorized host-only plugin restart replaced the old native serial owner with one new native PID. No firmware command, device probe, focus/menu/encoder stimulus, or physical UAT occurred. Status truthfully remained stale while the required device path was unavailable; autonomous periodic menu opening remains separately unresolved and is not claimed fixed."
files_changed:
  - host/herdr_keypad/native/src/ports/usb.rs
  - host/herdr_keypad/native/src/core/orchestrator.rs
  - host/herdr_keypad/native/tests/usb_platform.rs
  - host/herdr_keypad/native/tests/resource_bounds.rs
  - host/herdr_keypad/native/tests/production_surface.rs
postmortem:
  why_not_caught: "No deterministic coordinator seam previously coupled pending publication, split/cancelled USB ingress, Codex cadence, focus completion, and aggregate readiness."
  guard: "Production coordinator regressions now require Codex and exact focus progress together while snapshot ACK is delayed, preserve split frames across cancellation, and force non-ready status for every independently stalled required path."
