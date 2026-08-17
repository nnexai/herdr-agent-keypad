---
status: resolved
trigger: "Investigate the blank panels after Phase 2 firmware flash. Reproduce with the selected-usb firmware path and inspect firmware/src/main.cpp, firmware/src/app/agent_projection.*, board adapter/display initialization, protocol/session startup, and the host USB handshake. Determine whether the app fails before renderer initialization, clears panels without a committed generation, or uses an invalid display path. Implement the minimal fix in the source, run targeted native/selected-usb checks, and flash/retest the paired device if the exact USB path is available. Do not mask the failure with a mock or host-only fallback."
created: 2026-08-17T11:52:39+02:00
updated: 2026-08-17T13:20:00+02:00
---

## Current Focus

bug_class: bohrbug
reasoning_checkpoint:
  hypothesis: "PermanentBridge keeps the device's original authoritative generation after Herdr AgentInfo.revision advances, so exact focus revalidation rejects every press as source_revision_changed and never provides a new binding."
  confirming_evidence:
    - "Two physical key-1 focus_intents carried displayed source_revision 525005 and both produced source_revision_changed before agent.focus."
    - "Live agent.list had advanced to revision 525727 while pane w14:p1, terminal term_65928fc24750d1, and agent_session remained identical."
  falsification_test: "If publishing a complete current snapshot after the stale result still leaves the fresh binding on 525005 or the next matching press is rejected without another intervening revision, the hypothesis is wrong."
  fix_rationale: "Return the exact stale_target for the old intent, then bootstrap and commit a new authoritative generation. This preserves pane/terminal/session/revision fail-closed safety instead of focusing through drift, while giving the next press a current binding."
  blind_spots: "The current environment has one already-focused agent, so an actual pane switch cannot be observed until a second agent exists; FOCUSED device feedback remains the physical acceptance signal."
  candidate_causes:
    - "code: bridge omits authoritative refresh after expected source revision drift"
    - "data: Herdr output/status changes advance AgentInfo.revision without changing pane occupant identity"
  and_gate: "yes — volatile authoritative revision data plus the missing refresh path produce permanent stale rejection"
next_action: Resolved and archived after human physical acceptance.

## Symptoms

expected: The exact Phase 2 selected-usb image starts all four keypad panels with the prior default wait/idle tiles, emits serial hello, and acknowledges a v2 snapshot from the host.
actual: After flashing the Phase 2 selected-usb image, all four keypad panels are blank and the host smoke cannot obtain v2 snapshot acknowledgement.
errors: "serial read failed; stale descriptor closed"
reproduction: Build and flash the Phase 2 selected-usb firmware to the paired keypad device, then run the host USB smoke that waits for hello and sends a v2 snapshot.
started: Regression began after Phase 2 firmware integration; Phase 1 default wait/idle tiles previously rendered.

## Eliminated

- hypothesis: BoardAdapter uses an invalid display path in selected-usb.
  evidence: BoardAdapter::begin enables the official Pro display abstraction, displayAt maps through the verified complete PhysicalMap, and the historical renderer uses the same path; setup bypasses rendering after successful begin.
  timestamp: 2026-08-17T12:01:00+02:00

- hypothesis: Unthrottled BoardAdapter::update polling causes the v2 acknowledgement failure.
  evidence: Reintroducing the exact historical 50000 us guard, rebuilding, flashing, and rerunning the same 8-second smoke still timed out; the experimental change was removed from source.
  timestamp: 2026-08-17T12:12:00+02:00

## Evidence

- timestamp: 2026-08-17T11:54:00+02:00
  checked: Phase 0 semantic memory recall and .planning/debug knowledge-base fallback
  found: No project debug knowledge base exists and semantic recall found no matching Phase 2 resolution; it only surfaced older physical bring-up context including a prior reboot/polling regression.
  implication: Treat reboot/poll timing as one candidate but do not assume it; establish current source and runtime evidence independently.

- timestamp: 2026-08-17T12:00:00+02:00
  checked: firmware/src/main.cpp setup and loop
  found: setup initializes USB, physical map, board, session, and brightness, then explicitly calls board.clearDisplays(TFT_BLACK); it never calls render(BringupState::Wait). loop only calls agentProjection.tick(), which returns until a snapshot has committed.
  implication: A successful board startup deterministically leaves all four panels black until host snapshot commit; this directly explains the visual regression without an invalid display path.

- timestamp: 2026-08-17T12:00:00+02:00
  checked: BringupRenderer and BoardAdapter display path
  found: BringupRenderer::render traverses all four logical panels through BoardAdapter::displayAt and draws WAIT/IDLE for a Wait request. BoardAdapter enables the official Pro display abstraction and maps logical-to-library indices through the verified physical map.
  implication: The established valid display path still exists; selected-usb setup bypasses it by clearing instead of rendering.

- timestamp: 2026-08-17T12:00:00+02:00
  checked: AgentProjection startup and commit path
  found: AgentProjection starts with committed_=false and syncing_=true; tick is a no-op until commit. commitSnapshot(board) renders only the three agent slots, while the fourth panel is outside kSlotCount=3.
  implication: No committed generation can restore the legacy four-panel wait screen at boot, and even a successful snapshot leaves panel four unchanged unless startup rendered it.

- timestamp: 2026-08-17T12:00:00+02:00
  checked: Host UsbDeviceSession v1 hello and v2 request flow plus acceptance artifact
  found: connect uses the Phase 1 exact-binding hello/session, then request_v2 writes agent_snapshot and waits for snapshot_ack. The recorded failure is an I/O stale-descriptor closure rather than a parsed protocol rejection or timeout.
  implication: The acknowledgement failure likely reflects device reset/disconnect or lower-level serial instability; it is not explained by the missing wait render alone and needs direct paired-device observation.

- timestamp: 2026-08-17T12:01:00+02:00
  checked: Git history and pre-PhysicalMap startup
  found: The last startup implementation that displayed the default state ended setup with render(boardReady ? BringupState::Wait : BringupState::LinkLost, 0). Commit 00afeb4 replaced that with a guarded black clear and never restored the renderer call.
  implication: Differential debugging confirms the exact behavior removed from the working startup path; restoring the same renderer dispatch is the smallest source fix.

- timestamp: 2026-08-17T12:01:00+02:00
  checked: Exact paired USB endpoint and pre-fix host smoke
  found: The stored device_id 0000fccb0deabf8c is reachable at /dev/ttyACM0 via the stable Espressif by-id path and repeatedly acknowledges v1 hello with boot_id 0000fccb0deabf8c-fcf2be92. A live 847-byte v2 agent_snapshot received no acknowledgement within the bounded window; standard smoke timed out.
  implication: Firmware is reaching protocol startup, so the blank state is not a pre-renderer crash. The v2 acknowledgement remains a distinct runtime symptom to retest after the startup fix, per the minimal-change experiment.

- timestamp: 2026-08-17T12:03:00+02:00
  checked: Targeted native and selected-usb build gates after the startup change
  found: PlatformIO native protocol tests passed all 5 cases; selected-usb compiled and linked successfully with image size 461635 bytes and 15.3% RAM usage.
  implication: The one-line renderer restoration preserves protocol behavior and produces a valid exact-target image ready for physical flash.

- timestamp: 2026-08-17T12:05:00+02:00
  checked: Exact-target flash and post-flash smoke after startup-render-only change
  found: firmware.bin sha256 1ccfa2d4917194a70be74e1ef6e04cc287bb557cd915ca3c752d7d8bebc55330 flashed successfully to the USB-Serial/JTAG device with MAC 8c:bf:ea:0d:cb:fc and verified on write. The paired v1 hello succeeded inside smoke, but v2 agent_snapshot still timed out after 8 seconds.
  implication: The renderer fix is isolated from the acknowledgement fault as predicted; continue the independent runtime investigation rather than expanding the startup patch.

- timestamp: 2026-08-17T12:05:00+02:00
  checked: Git differential for BoardAdapter polling
  found: Commit 5d081d9 explicitly added lastBoardUpdateAt and a 50000 us throttle to fix runtime stack overflow on this hardware. Commit c021be2, whose purpose was moving ProtocolSession::Result off the loop stack, simultaneously deleted that throttle and restored board.update() on every approximately 1 ms loop; current source still contains the accidental revert.
  implication: This is a specific, falsifiable high-probability cause for serial instability under the heavier v2 render/dispatch path; restore the known hardware-safe poll interval and retest without changing protocol semantics.

- timestamp: 2026-08-17T12:12:00+02:00
  checked: Poll-throttle falsification flash
  found: The image with the exact historical 50000 us BoardAdapter::update guard built, flashed, and still timed out on the same v2 snapshot acknowledgement.
  implication: The polling hypothesis is false for this symptom; the guard was removed again so it is not bundled into the fix.

- timestamp: 2026-08-17T12:12:00+02:00
  checked: Post-failure firmware metrics and Arduino-ESP32 3.3.11 HWCDC implementation
  found: Device metrics after the failed 847-byte frame showed parser_high_water 607 and watchdog_reset 0. HWCDC defaults RX to 256 bytes and its ISR breaks/drops remaining packet bytes when xQueueSendFromISR fails; UsbCdcLink never calls setRxBufferSize.
  implication: The firmware transport capacity is smaller than the accepted protocol line and truncates the live v2 frame before LF, so dispatch cannot send snapshot_ack.

- timestamp: 2026-08-17T12:18:00+02:00
  checked: Buffered image flash, smoke, metrics, and raw snapshot_ack
  found: Enlarging HWCDC RX to sizeof(inputFrame) raised parser_high_water from 607 to 852 and eliminated firmware rejection, but host immediately reported digest_mismatch. Raw ack capture proves its wire digest was computed over noncanonical insertion order; the independently canonical digest differs.
  implication: RX truncation was one real cause of the earlier timeout. The now-visible third defect is the device's noncanonical v2 outbound payload order, not transport or snapshot staging.

- timestamp: 2026-08-17T12:25:00+02:00
  checked: Final exact selected-usb image and paired-device acknowledgement
  found: firmware.bin sha256 8984944ecfab0a040d1850757b52f14cb40d889d18daa0f0e902d65c0b463984 flashed and verified on MAC 8c:bf:ea:0d:cb:fc. The paired device returned v1 hello for device_id 0000fccb0deabf8c and accepted an 856-byte current snapshot with snapshot_ack accepted=true, reason=committed, and matching epoch/revision/source_status.
  implication: The device product path now receives, commits, and acknowledges the real v2 generation; no mock or host fallback participated.

- timestamp: 2026-08-17T12:25:00+02:00
  checked: Final targeted regression gates
  found: All 5 native protocol tests and 19 herdr_keypad protocol/projection/focus/integration tests passed. The final selected-usb build succeeded. The aggregate --smoke command progressed past the fixed USB acknowledgement but then failed during the subsequent Herdr subscription with unrelated Herdr response; direct exact-session acknowledgement was independently captured.
  implication: Firmware and host v2 contracts are green; the remaining full-smoke failure is after USB snapshot acknowledgement and outside this firmware regression, likely shared live Herdr socket activity.

- timestamp: 2026-08-17T12:32:00+02:00
  checked: Installed Herdr events.subscribe request schema and live error
  found: EventsSubscribeParams requires subscriptions; each Subscription is a public discriminated object such as {type: pane.created}. Current HerdrClient sends {events: [...]} and permits wildcard, producing missing field subscriptions.
  implication: The full smoke's post-ack unrelated Herdr response is a deterministic host adapter schema bug; fix the public request boundary without altering firmware or focus authority.

- timestamp: 2026-08-17T12:40:00+02:00
  checked: Correct typed subscription shape against installed schema
  found: Global lifecycle events accept {type: event}; pane.agent_status_changed requires a pane_id, so PermanentBridge now emits explicit global subscriptions plus one status subscription per current projected pane. Wildcard and empty subscriptions fail locally.
  implication: The bridge preserves required lifecycle invalidation using only the public installed schema and no wildcard.

- timestamp: 2026-08-17T12:40:00+02:00
  checked: Final host tests, full live smoke, and guarded bridge startup
  found: All 20 targeted host tests passed. Full herdr_keypad --smoke passed with snapshot acknowledged for epoch host-431465-1786961846 revision 1 slots 3. ensure-bridge is running under its flock guard as process phase2-herdr-bridge.
  implication: Exact hello, v2 commit/ack, installed events.subscribe, and permanent bridge startup now pass end-to-end; only human-visible panels and physical key focus remain.

- timestamp: 2026-08-17T13:02:00+02:00
  checked: Live Herdr focus API and current key-1 projection
  found: Current key 1 binds the sole agent w14:p1 at source revision 525005. Herdr agent.list already reports that pane focused. Direct agent.focus returns type agent_info with focused true and exact identity; immediate and 3-second delayed FocusExecutor calls both return accepted.
  implication: The Herdr focus method and exact identity revalidation work live. Because the sole target is already focused, no pane switch can be visually observed, but firmware still must receive accepted focus_result and render FOCUSED.

- timestamp: 2026-08-17T13:02:00+02:00
  checked: Instrumented exact USB bridge readiness
  found: focus-diagnostic bootstrapped the exact paired device and current snapshot, and remains READY while logging each raw focus_intent, host outcome, and exception. No frame has arrived because no physical press occurred during the armed capture window.
  implication: Root cause of the reported persistent PENDING cannot be distinguished further without one physical key transition; the running diagnostic removes all other observability blockers.

- timestamp: 2026-08-17T13:12:00+02:00
  checked: Instrumented physical focus intents against live authoritative identity
  found: Two key-1 frames carried pane w14:p1, terminal term_65928fc24750d1, session herdr:omp:omp:path, and displayed source_revision 525005. Both host outcomes were source_revision_changed. Live agent.list had revision 525727 with the same pane/terminal/session.
  implication: Exact identity safety is working; AgentInfo.revision legitimately drifted, but the permanent bridge left the keypad bound to the old generation and made every retry permanently stale.

- timestamp: 2026-08-17T13:12:00+02:00
  checked: Targeted stale-rebind regression
  found: A stale intent now emits stale_target without agent.focus, publishes snapshot revision 2 with current source_revision 2, and a retry using that fresh binding returns accepted and calls agent.focus exactly once. All 21 protocol/projection/focus/integration tests pass.
  implication: The minimal host fix refreshes only the authoritative source-revision drift path and does not weaken pane, terminal, session, generation, or stale-intent rejection.

- timestamp: 2026-08-17T13:20:00+02:00
  checked: Final exact-device human acceptance and instrumented focus log
  found: After stale generations refreshed from snapshot revisions 1 and 2, a physical key-1 intent on snapshot revision 3/source revision 527416 returned accepted with agent.focus acknowledged, focused true, and exact pane/terminal/session. The user observed WAIT/IDLE startup, safe empty position-2 rejection, position 1 PENDING, target-tab switch, terminal FOCUSED feedback, and restoration to the authoritative BLOCKED tile.
  implication: The original blank-panel and missing-v2-ack regression plus the follow-on stale-focus loop are resolved end-to-end on the exact paired hardware; BLOCKED after FOCUSED is the intended two-second terminal feedback transition, not a failure.

## Resolution

root_cause: "Five defects in the reported product path: (1) main.cpp omitted the established four-panel Wait render and cleared black; (2) UsbCdcLink kept HWCDC's 256-byte RX queue despite 4096-byte protocol lines; (3) device v2 payloads were noncanonical; (4) HerdrClient used obsolete subscription params; (5) Herdr AgentInfo.revision advanced from the displayed 525005 to 525727 while pane/terminal/session stayed stable, and PermanentBridge rejected the exact stale intent but never published a fresh authoritative generation, making every retry permanently stale."
fix: "Restored startup Wait rendering; sized HWCDC RX; canonicalized device v2 payloads; used installed typed Herdr subscriptions; and after a source_revision_changed focus outcome, now sends stale_target then bootstraps and commits a complete fresh snapshot/rebind before the next key press."
verification:
  oracle_type: specified
  target_test: {result: pass, detail: "human observed WAIT/IDLE, safe empty rejection, PENDING, exact tab switch, FOCUSED, then authoritative BLOCKED; diagnostic log captured accepted focus with focused=true"}
  mutation_check: {result: skipped, reason_if_skipped: "no Python mutation runner configured", mutant_killed: false}
  no_op_deletion: {result: pass, deletion_justified_by_rca: false}
  adjacent_tests: {result: pass, suites_run: ["PlatformIO native 5 cases", "herdr_keypad 21 tests", "selected-usb build/flash", "full live snapshot smoke", "live focus API"]}
  revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true, detail: "before fix two live presses stayed on source revision 525005 and were rejected after authoritative revision reached 525727; regression proves fixed path publishes revision 2 and accepts its retry"}
  guardrail_verdict: accepted
  manual_physical_check: "passed"
files_changed: [firmware/src/main.cpp, firmware/src/app/agent_projection.cpp, firmware/src/transport/link.h, firmware/src/transport/usb_cdc.cpp, host/herdr_keypad/src/herdr_keypad/herdr.py, host/herdr_keypad/src/herdr_keypad/bridge.py, host/herdr_keypad/tests/test_integration.py]
commits: [db323fe, b3f172e, 8a6d557]

## Prevention

- Startup rendering branch: Phase 2 replaced the prior terminal WAIT render with a raw clear; review and native protocol tests did not exercise physical boot pixels. Recurrence guard: exact-device human startup observation plus the retained `render(BringupState::Wait, 0)` product path.
- Transport branch: the protocol line bound grew to 4096 bytes while HWCDC stayed at its 256-byte default RX queue; selected-usb compilation could not expose device queue truncation. Recurrence guard: configure RX from `sizeof(inputFrame)` and retain a live snapshot larger than 256 bytes in acceptance.
- Digest branch: ArduinoJson preserves insertion order while the host validates canonical JSON; fake/native payloads were already canonical. Recurrence guard: lexical device payload construction and live digest-validated snapshot/focus messages.
- Herdr adapter branch: tests accepted the obsolete subscription request shape because FakeHerdr did not enforce the installed schema. Recurrence guard: typed-subscription parameter assertions including pane-scoped status and live full-smoke coverage.
- Focus freshness branch: exact revision rejection was tested, but no test required recovery from legitimate AgentInfo revision drift, so a correct rejection became permanent. Recurrence guard: `test_source_revision_drift_rebinds_before_fresh_retry` proves no stale focus call, a complete fresh generation, and one accepted retry without weakening pane/terminal/session safety.
- Why not caught: build, type, and protocol gates covered isolated seams but no preexisting gate exercised startup pixels, a >256-byte physical CDC frame, installed subscription validation, and stale-to-fresh physical focus as one exact-device path.
