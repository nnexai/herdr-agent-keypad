---
status: awaiting_human_verify
trigger: "User reports live physical focus switching still does not work and Codex limits show unavailable while native status reports ready. This is ground truth: runtime is not stable or production-ready."
created: 2026-08-30T12:29:01Z
updated: 2026-08-30T13:14:53Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "confirmed — RuntimeCoordinator authorized physical focus against transient InboxProjection.current instead of the exact snapshot the device ACKed and still displayed; invalidation and pending refresh therefore changed authorization ownership before display ownership changed."
  confirming_evidence:
    - "RED ordinary-invalidation case returned Stale instead of Accepted for the exact displayed binding; GREEN after explicit acknowledged-snapshot authorization."
    - "RED newer-unacknowledged-generation case returned WrongRevision instead of Accepted; GREEN while all exact identity fences remained enabled."
    - "RED ACKed-Codex case returned Unavailable instead of Ready after only an unrelated pending generation advanced; GREEN after status ownership moved to the full ACKed view."
    - "RED current Codex collection retained CodexUnavailable and unchanged ACK/Codex churn evicted FocusRejected; both GREEN after corrected assignment and state-change-only recording."
  falsification_test: "Any focused regression returning Stale/WrongRevision for the retained displayed view, any negative fence accepting a changed identity, or ordinary churn evicting FocusRejected would falsify the fix."
  fix_rationale: "PendingPublication now owns the exact projection and displayed Codex state sent on the wire; only an exact accepted ACK installs that full view, and FocusExecutor requires it as its authorization snapshot while still performing a complete live identity read."
  blind_spots: "The tested release is now deployed with sole native serial authority, but no post-deploy physical focus gesture has occurred. One human key press remains the final behavioral oracle."
  candidate_causes:
    - "code/state: transient refreshed/invalidation projection and exact displayed projection were conflated."
    - "environment/timing: Herdr invalidation and Codex cadence interleaved between device ACK and intent."
    - "data/status: successful Codex collection assigned CodexUnavailable, while unchanged ACK/republication events flooded the bounded transition ring."
  and_gate: "yes — valid displayed data plus intervening current-generation churn triggered focus rejection; independent Codex assignment and transition-recording defects explained the inconsistent status and lost evidence."
next_action: "Human presses exactly one agent key once for the pane Herdr should focus, does not retry or use menu, encoder, another key, firmware, or probe, and reports whether focus changed; Main then performs the bounded read-only follow-up."

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

- timestamp: 2026-08-30T12:59:16Z
  checked: user multi-key focus attempt and bounded post-attempt status supplied as ground truth
  found: "The user pressed multiple agent keys and none focused. Latest status is aggregate stale with device ready, Herdr stale, Codex unavailable, and last_error=focus_rejected. The bounded transition ring no longer retains the actionable focus outcome because snapshot_acknowledged/codex_connected churn overwrote it."
  implication: "The deployed readiness proof did not repair physical focus execution. Investigation must bind intent and status to the exact ACKed/displayed projection, keep Herdr source health independently truthful, correct Codex error clearing, and preserve actionable focus evidence against ordinary ACK/republication churn. No further user gesture is permitted before a source fix is deployed."

- timestamp: 2026-08-30T13:02:58Z
  checked: five deterministic focused regression cases before source changes
  found: "RED: ordinary invalidation returned FocusStatus::Stale instead of Accepted; newer unacknowledged projection returned WrongRevision instead of Accepted; ACKed displayable Codex became Unavailable instead of Ready when only a pending Herdr generation advanced; successful current Codex collection retained Some(CodexUnavailable); 36 repeated unchanged exact ACK/Codex publications evicted FocusRejected from the 32-entry transition ring."
  implication: "The root causes are confirmed at the acknowledged-view ownership, Codex error assignment, and transition recording seams. These are deterministic state-management Bohrbugs triggered by live event ordering, not protocol schema mismatches."

- timestamp: 2026-08-30T13:09:22Z
  checked: focused GREEN and held-out regression fences after acknowledged-view cutover
  found: "GREEN: core::orchestrator::tests 19/19; production_surface 7/7; projection_focus_parity 10/10; herdr_parity different_structured_session_remains_rejected 1/1; codex_parity sparse_invalid_shapes_are_transactional_and_account_reset_discards_cache 1/1. The exact five former RED cases are included and pass."
  implication: "Acknowledged focus/Codex ownership, current Codex error clearing, bounded transition retention, and all existing epoch/revision/slot/entry/pane/terminal/session/source-revision plus selection-only fences hold deterministically. No live/deploy/commit/archive action was taken."

- timestamp: 2026-08-30T13:14:53Z
  checked: final acknowledged-view integration validation and atomic source/test commit
  found: "Focused locked suites passed 19 orchestrator + 7 production_surface + 10 projection_focus_parity + 1 structured-session fence + 1 Codex transaction fence = 38 tests. Full cargo test --locked passed 126 tests across 15 suites with 1 ignored. The four native source/test files were committed atomically as 9e25f95."
  implication: "The displayed-view ownership fix and its held-out identity, production, projection, and Codex fences are committed and deterministically GREEN."

- timestamp: 2026-08-30T13:14:53Z
  checked: clean locked release build and byte-identical installed-plugin staging
  found: "cargo clean followed by cargo build --locked --release succeeded. target/release/herdr-keypad-native and /home/nnex/.local/share/herdr/plugins/herdr-keypad/bin/herdr-keypad both have SHA-256 c96d726868d97d6c62d85c5092f1f24b59134095a97884b8d7a7b213870a1d3c, and cmp reported exact identity."
  implication: "The enabled Herdr plugin contains exactly the tested release bytes."

- timestamp: 2026-08-30T13:14:53Z
  checked: exactly one Herdr-managed restart and sole native production authority
  found: "Herdr action plugin-log-69 is the sole valid restart dispatch. One malformed CLI argument-order attempt exited 2 before action dispatch and caused no restart. Old native PID 1399642 exited; sole new native PID 1502977 runs the staged bin/herdr-keypad restart authority, owns FD 9 -> /dev/ttyACM0, and fuser reports only 1502977. The Python keypad-runtime process scan returned no rows."
  implication: "Exactly one managed authority replacement activated the staged Rust release; it is the sole serial owner and Python remains absent."

- timestamp: 2026-08-30T13:14:53Z
  checked: single post-startup read-only status and human-verification boundary
  found: "The only post-deploy status action, plugin-log-70, succeeded with state=stale, device_state=ready, herdr_state=running, codex_state=ready, reconnect_attempt=0, backoff_ms=0, last_error=null. Its transitions are bridge_started@0, codex_connected@1, snapshot_acknowledged@2, codex_unavailable@3, codex_connected@4; no focus outcome exists. No firmware, probe, menu, encoder, key, or synthetic focus stimulus was used."
  implication: "Startup, acknowledged display ownership, Codex recovery, and truthful pre-gesture stale state are live. The checkpoint stays active and unresolved pending exactly one ordinary agent-key press."

## Resolution

root_cause:
  - "Focus authorization had two competing owners: the device emitted an intent from its exact ACKed/displayed projection, but FocusExecutor compared it with InboxProjection.current. Ordinary Herdr invalidation immediately manufactured and published a newer stale revision, and a fully refreshed but not-yet-ACKed generation also replaced current; both made every still-visible binding fail before any live identity/focus call."
  - "PendingPublication retained only epoch/revision/source plus a Codex boolean, and acknowledged state retained only a tuple. Status therefore compared ACK evidence and focus proof with transient current and the live Codex collector instead of the exact displayed generation."
  - "A successful current Codex collection assigned Some(CodexUnavailable) instead of clearing it."
  - "Every exact ACK and every Codex republication appended transitions even when no state changed. Alternating snapshot_acknowledged/codex_connected events could evict the actionable focus_rejected evidence from the fixed 32-entry ring."
fix:
  - "PendingPublication now owns PublishedProjection: the full exact ProjectionSnapshot plus the displayed Codex BridgeStatus derived from the serialized payload. Only a matching accepted ACK installs it as acknowledged_projection."
  - "FocusExecutor now requires an explicit acknowledged ProjectionSnapshot. RuntimeCoordinator authorizes epoch/revision/slot/entry/pane/terminal/session/source-revision against that displayed view, then performs the existing complete live read and selection-only agent.focus acknowledgement checks."
  - "Ordinary Herdr invalidation only marks refresh dirty and coalesces. A successful complete refresh publishes only a material change; actual read/normalization failure still marks Herdr unhealthy, creates stale/offline/unavailable source truth, publishes it, and schedules recovery."
  - "Codex and focus readiness are computed from acknowledged_projection, independent of unrelated current/pending Herdr generations. Herdr health remains computed from current complete-refresh truth."
  - "Current Codex collection clears CodexUnavailable. Collector transitions and ACK/display transitions are emitted only when their corresponding state changes; repeated ACK/republication churn no longer consumes the bounded ring."
state_invariants:
  - "current is the latest successfully completed Herdr projection, or explicit stale/offline/unavailable truth after a real failure; ordinary invalidation alone never changes or publishes it."
  - "pending_publication is the one exact serialized view awaiting ACK; later changes set publication_dirty without changing pending ownership."
  - "acknowledged_projection is the last full exact view accepted by an exact reply-to/epoch/revision/source-status ACK and is never replaced by collection, refresh, invalidation, or an unacknowledged publication."
  - "focus authorization and proof, device displayability, and Codex status share acknowledged_projection ownership; Herdr health remains an independent current-source signal."
  - "focus remains selection-only and fail-closed across device session, host epoch, revision, slot, entry, pane, terminal, agent session, source revision, live disappearance/reuse, malformed response, timeout, offline, and unsuccessful focused acknowledgement."
  - "transition memory remains bounded at 32 SafeCode-only entries, but ordinary unchanged ACK/republication cadence does not overwrite actionable focus evidence."
verification:
  oracle_type: specified
  red:
    - "displayed_binding_survives_ordinary_herdr_invalidation_until_refresh_finishes: Stale != Accepted"
    - "displayed_binding_survives_newer_unacknowledged_projection: WrongRevision != Accepted"
    - "acknowledged_codex_remains_ready_while_unrelated_generation_is_pending: Unavailable != Ready"
    - "successful_current_codex_collection_clears_unavailable_error: Some(CodexUnavailable) != None"
    - "ordinary_ack_republication_churn_retains_actionable_focus_evidence: FocusRejected absent after unchanged churn"
  green:
    - "cargo test --lib core::orchestrator::tests — 19 passed"
    - "cargo test --test production_surface — 7 passed"
    - "cargo test --test projection_focus_parity — 10 passed"
    - "cargo test --test herdr_parity different_structured_session_remains_rejected — 1 passed"
    - "cargo test --test codex_parity sparse_invalid_shapes_are_transactional_and_account_reset_discards_cache — 1 passed"
  guardrail_verdict: "accepted for deterministic native behavior and deployed with sole native authority; awaiting one ordinary physical gesture"
  live_disposition: "The acknowledged-view release is deployed as source commit 9e25f95 and installed SHA-256 c96d726868d97d6c62d85c5092f1f24b59134095a97884b8d7a7b213870a1d3c on native PID 1502977. Pre-gesture status is truthfully stale with device ready, Herdr running, Codex ready, and no last_error."
  next_gesture: "Press exactly one agent key once for the pane Herdr should focus; do not retry or use menu, encoder, another key, firmware, or probe; report whether focus changed."
deployment:
  source_commit: "9e25f95"
  native_tests: "focused 38 passed; full cargo test --locked 126 passed across 15 suites, 1 ignored"
  build_stage_sha256: "c96d726868d97d6c62d85c5092f1f24b59134095a97884b8d7a7b213870a1d3c"
  restart_count: 1
  restart_log: "plugin-log-69"
  old_pid: 1399642
  new_pid: 1502977
  serial_fd: "9 -> /dev/ttyACM0, sole owner"
  python_runtime: "absent"
  post_deploy_status: "plugin-log-70: stale/ready/running/ready, reconnect_attempt=0, backoff_ms=0, last_error=null"
  transitions: "bridge_started@0, codex_connected@1, snapshot_acknowledged@2, codex_unavailable@3, codex_connected@4; no focus outcome"
  disposition: "awaiting_human_verify; active checkpoint retained in place"
  human_verification: "Press exactly one agent key once for the pane Herdr should focus; do not retry or use menu, encoder, another key, firmware, or probe; report whether focus changed."
files_changed:
  - host/herdr_keypad/native/src/core/orchestrator.rs
  - host/herdr_keypad/native/src/core/focus.rs
  - host/herdr_keypad/native/tests/herdr_parity.rs
  - host/herdr_keypad/native/tests/projection_focus_parity.rs
  - .planning/debug/native-ready-but-physically-unusable.md
