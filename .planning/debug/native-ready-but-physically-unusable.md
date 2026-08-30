---
status: awaiting_human_verify
trigger: "User reports live physical focus switching still does not work and Codex limits show unavailable while native status reports ready. This is ground truth: runtime is not stable or production-ready."
created: 2026-08-30T12:29:01Z
updated: 2026-08-30T13:18:00Z
---

## Current Focus

hypothesis: confirmed — readiness used live collector/link lifecycle rather than acknowledged display state and successful action-path evidence
test: after deployment, use one ordinary agent-key press to exercise the current-generation focus path once; then inspect bounded read-only status evidence without retries or other device stimulus
expecting: ready remains false while action_path is untested/rejected or the exact acknowledged Codex payload is unavailable; only an accepted focus result for the current host epoch/revision plus an ACKed displayable current Codex window can make ready
next_action: human presses exactly one agent key once for the pane Herdr should focus, does not retry or use menu/encoder/other keys, and reports whether focus changed; Main then reads status to capture the resulting focus_accepted or focus_rejected/device_unavailable evidence

## Symptoms

expected: pressing an agent key focuses that exact Herdr pane; Codex tile shows current normalized limits; status ready means both are usable
actual: physical focus switching fails and Codex tile shows unavailable while status reports fully ready
errors: no runtime error is exposed; last_error is null
reproduction: already supplied by user on the currently deployed native PID 1248978; do not ask for or rerun the physical gestures merely to reconfirm
started: after deployment of host ACK/readiness fixes

## Eliminated

- Host process absence: PID 1248978 remains the sole native runtime.
- Python authority conflict: previous deployment verification found no Python keypad runtime.
- Pure transport readiness as acceptance: exact ACK and serial ownership coexist with unusable physical behavior.

## Evidence

- `herdr plugin log list --plugin herdr-keypad --limit 20`: latest status logs 62/63 report ready, but contain only `bridge_started`; no focus or Codex usability outcomes.
- Process scan: PID 1248978 runs staged `bin/herdr-keypad restart` runtime.
- Semantic recall candidate: a prior fix preserved structured Herdr `agent_session` values across `agent.list` and `agent.focus`; because the current deployed failure persists, this is evidence that result transport/readiness or another production schema mismatch remains and must be differentiated.
- Native source map: Codex ownership is `ports/codex.rs`; Herdr/focus ownership is `ports/herdr.rs` plus `core/focus.rs`; projection/readiness ownership is `core/projection.rs` and `core/orchestrator.rs`; status persistence is `ports/status.rs`; focused integration tests already exist for Codex, Herdr, projection/focus, production surface, and lifecycle.
- Installed Codex 0.151.0 generated schema requires top-level `rateLimits`; `primary`/`secondary` windows contain required `usedPercent` and optional `resetsAt`/`windowDurationMins`; `rateLimitsByLimitId` is optional. The production adapter matches this schema exactly.
- Installed Herdr 0.8.2 bundled schema defines `agent.focus` params as `{"target": string}` and success as `{"type":"agent_info","agent":AgentInfo}`. Tagged Herdr source calls `focus_pane_in_workspace` and returns that AgentInfo; the native method, target, and response extraction match.
- `RuntimeCoordinator::status()` derives Codex readiness from the collector's latest in-memory view, not from the Codex fields in the exact device-ACKed publication. `PendingPublication` retains only Herdr source identity.
- `RuntimeCoordinator::drain_focus()` discards the FocusOutcome after sending the result and records no SafeCode transition or readiness proof. Thus rejected/failed/lost operational attempts cannot affect ready or last_error.
- Native `FocusResultPayload` and firmware v2 payload parser agree on all eleven fields and accepted implies focused. Schema serialization is not the identified source defect.
- RED `cargo test --lib collector_ready_cannot_override_acknowledged_unavailable_codex_projection`: failed deterministically with `left: Ready`, `right: Stale` before the fix.
- RED `cargo test --lib snapshot_ack_without_confirmed_successful_focus_result_is_not_ready`: failed deterministically with `left: Ready`, `right: Stale` before the fix.
- GREEN `cargo test --lib core::orchestrator::tests`: 14 passed, 0 failed after the fix.
- GREEN `cargo test --test production_surface`: 7 passed, 0 failed; production status now proves Codex collection separately but remains non-ready until the displayable payload is ACKed.
- Held-out negative fences: `different_structured_session_remains_rejected` passed; `focus_policy_maps_fences_and_failures_without_other_effects` passed; `sparse_invalid_shapes_are_transactional_and_account_reset_discards_cache` passed.
- timestamp: 2026-08-30T12:50:47Z
  checked: source and test integration against the checkpoint contract
  found: "Focused GREEN suites passed 14 orchestrator tests and 7 production-surface tests; held-out negative fences passed 1+1+1; full native cargo test --locked passed 121 tests across 15 suites with 1 ignored. Source and tests were committed atomically as 3970d60."
  implication: "The aggregate cannot become ready from collector/link health alone, and existing identity, focus-policy, and Codex transaction fences remain intact."
- timestamp: 2026-08-30T12:50:47Z
  checked: clean locked release build and installed-plugin staging
  found: "cargo clean followed by cargo build --locked --release succeeded. Built target/release/herdr-keypad-native and staged /home/nnex/.local/share/herdr/plugins/herdr-keypad/bin/herdr-keypad both have SHA-256 8e6c3921a4b1219d67727f748b1ef03ce132a9bed7b8f9f60c51647f421ad800, and cmp reports exact byte identity."
  implication: "The installed Herdr plugin contains the tested release bytes."
- timestamp: 2026-08-30T12:50:47Z
  checked: exactly one Herdr-managed host restart and production authority replacement
  found: "Herdr restart action plugin-log-66 is the sole dispatched restart. Old native PID 1248978 exited; sole new native PID 1399642 runs the staged bin/herdr-keypad restart authority. A malformed CLI argument-order attempt exited 2 before Herdr action dispatch and caused no restart."
  implication: "Exactly one host authority transition activated the staged release."
- timestamp: 2026-08-30T12:50:47Z
  checked: serial ownership and Python production absence
  found: "PID 1399642 alone owns /dev/ttyACM0 through FD 9; fuser reports only 1399642. The python.*herdr[_-]keypad and herdr[_-]keypad.*python process scan returned no rows."
  implication: "The deployed Rust authority is the sole serial owner and no Python keypad bridge is active."
- timestamp: 2026-08-30T12:50:47Z
  checked: single bounded post-deploy read-only status action
  found: "plugin-log-67 succeeded with state=stale, device_state=ready, herdr_state=running, codex_state=unavailable, reconnect_attempt=0, backoff_ms=0, last_error=null. Its 32-entry bounded transition ring alternates snapshot_acknowledged and codex_connected at_ms 512 through 543, with snapshot_acknowledged on even values and codex_connected on odd values. No focus transition exists."
  implication: "The live bridge truthfully withholds aggregate readiness before current-generation focus proof. The observed status does not claim physical focus success or an ACKed current-generation Codex display at that instant."
- timestamp: 2026-08-30T12:50:47Z
  checked: human-verification boundary
  found: "No firmware, probe, menu, encoder, key, or synthetic focus stimulus was used during validation or deployment."
  implication: "The active checkpoint remains awaiting_human_verify. One normal agent-key press is now required to produce the bounded focus-path evidence."

## Resolution

root_cause:
  - "Codex: status consumed the collector's latest in-memory `current` view while the physical device displayed the last exact ACKed payload. PendingPublication did not retain whether that payload had a displayable current primary/secondary window, so collector success could report ready over an ACKed unavailable tile."
  - "Focus: snapshot/link ACK was treated as sufficient action readiness. RuntimeCoordinator discarded FocusOutcome after transmission and retained no generation-scoped success proof or rejection/transmit evidence, so untested, rejected, failed, or lost focus operations could coexist with ready and last_error null."
  - "The installed Codex 0.151.0 and Herdr 0.8.2 schemas match the production adapters; focus target, method, response extraction, and native/firmware result field serialization are not the diagnosed mismatches."
fix:
  - "Pending publications now carry a boolean derived from the exact serialized Codex payload: source_state=current and at least one non-null primary/secondary window. Exact snapshot ACK commits this display evidence for the same host epoch/revision; collector health alone cannot promote Codex or aggregate readiness."
  - "A successful exact FocusOutcome whose focus_result write succeeds records generation-scoped focus proof. Rejection or unavailable outcome clears it; transmit/link failure clears it through the existing fail-closed USB reset."
  - "Bounded TransitionRing evidence records only SafeCode values (`codex_connected`, `codex_unavailable`, `snapshot_acknowledged`, `focus_accepted`, `focus_rejected`, and existing device failures). No identity, path, raw provider payload, or arbitrary error text is persisted."
  - "Aggregate ready now requires device ready, Herdr running/current actionable projection, acknowledged displayable Codex for that current generation, and proven focus path for the same host epoch/revision."
verification:
  oracle_type: specified
  red:
    - "collector_ready_cannot_override_acknowledged_unavailable_codex_projection: failed Ready != Stale"
    - "snapshot_ack_without_confirmed_successful_focus_result_is_not_ready: failed Ready != Stale"
  green:
    - "cargo test --lib core::orchestrator::tests — 14 passed"
    - "cargo test --test production_surface — 7 passed"
    - "cargo test --test herdr_parity different_structured_session_remains_rejected — 1 passed"
    - "cargo test --test projection_focus_parity focus_policy_maps_fences_and_failures_without_other_effects — 1 passed"
    - "cargo test --test codex_parity sparse_invalid_shapes_are_transactional_and_account_reset_discards_cache — 1 passed"
  guardrail_verdict: accepted for deterministic native behavior; live physical subtype intentionally unverified until controlled deployment
  deployment:
    source_commit: "3970d60"
    native_tests: "focused 14+7+1+1+1 passed; full locked suite 121 passed across 15 suites, 1 ignored"
    build_stage_sha256: "8e6c3921a4b1219d67727f748b1ef03ce132a9bed7b8f9f60c51647f421ad800"
    restart_count: 1
    restart_log: "plugin-log-66"
    old_pid: 1248978
    new_pid: 1399642
    serial_fd: "9 -> /dev/ttyACM0, sole owner"
    python_runtime: "absent"
    post_deploy_status: "plugin-log-67: stale/ready/running/unavailable, reconnect_attempt=0, backoff_ms=0, last_error=null"
    transitions: "32 entries: snapshot_acknowledged/codex_connected alternating at_ms 512..543; no focus evidence"
    disposition: "awaiting_human_verify; active checkpoint retained in place"
    human_verification: "Press exactly one agent key once for the pane Herdr should focus; do not retry or use menu, encoder, or another key; report whether focus changed."
files_changed:
  - host/herdr_keypad/native/src/core/orchestrator.rs
  - host/herdr_keypad/native/tests/production_surface.rs
  - .planning/debug/native-ready-but-physically-unusable.md
