---
status: resolved
trigger: "Quick agent-key taps do not focus; a slightly held press focuses, while a longer hold correctly triggers the microphone Space behavior."
created: 2026-08-22T18:32:00Z
updated: 2026-08-22T18:50:24Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: resolved
  confirming_evidence:
    - the live six-tap trace received every device focus_intent
    - one intent was deferred while bridge.ready was false and then discarded when the snapshot generation advanced
    - alternating intents reached FocusExecutor but returned source_revision_changed before agent.focus
    - accepted intents called agent.focus and visibly switched focus
  falsification_test: six quick alternating taps plus one deliberate hold on the exact device
  candidate_causes:
    - resolved: bridge refresh downtime and whole-projection freshness rejection
    - hardened but not causal: key polling and ButtonSense admission latency
    - eliminated: release cancels an already emitted focus intent
  and_gate: yes
next_action: none

## Symptoms

expected: a natural quick tap immediately focuses its displayed agent; only a deliberate 550 ms hold emits Space
actual: quick taps intermittently did nothing; holding briefly but below the mic threshold focused
errors: failed focus intents were silently deferred/discarded or returned source_revision_changed
reproduction: alternate quick taps between two occupied agent keys while inbox refresh events are active
started: immediately after Phase 03.2 final qualification and bridge restoration

## Eliminated

- ButtonSense debounce was not the end-to-end cause: one-sample admission still missed focus on the exact device.
- Poll starvation was not the end-to-end cause: the 2 ms raw STM32 poller still reproduced visible misses, while the live bridge trace received every tap.
- Firmware release handling was not cancelling focus: focus_intent frames existed for the missed taps.

## Evidence

- timestamp: 2026-08-22T18:32:00Z
  checked: BoardAdapter, ButtonSense, and final exact-device metrics
  found: ButtonSense required a second sample and product-loop key poll gaps reached 47.913 ms
  implication: the input seam needed hardening, but this did not explain the remaining delivery loss

- timestamp: 2026-08-22T18:43:00Z
  checked: exact-device behavior after one-sample admission and then a dedicated 2 ms raw STM32 key poller
  found: quick focus still missed in both builds
  implication: input-only hypotheses were falsified; the bridge path required direct observation

- timestamp: 2026-08-22T18:46:00Z
  checked: live bridge trace across USB intake, focus queueing, snapshot publication, and Herdr execution
  found: every tap produced focus_intent; a ready=false intent was discarded across revision 21 to 22, and alternating live intents returned source_revision_changed because prior focus events changed mutable projection fields
  implication: deliberate refresh downtime and whole-projection equality checks dropped valid exact-target focus requests

- timestamp: 2026-08-22T18:49:00Z
  checked: focused regression suites after bridge correction
  found: bridge/focus tests passed 42/42, native-board-adapter passed 9/9, native-hold-controller passed 23/23, and selected-usb built and uploaded successfully
  implication: pending focus survives current-source refresh, immutable live target identity remains fail-closed, complete between-loop taps are latched, and the 550 ms hold contract is unchanged

- timestamp: 2026-08-22T18:50:24Z
  checked: exact-device six-tap alternating focus check and deliberate hold/release
  found: user confirmed all six quick taps switched focus and the hold activated then released correctly
  implication: the original end-to-end reproduction is green

## Resolution

root_cause: normal inbox refreshes temporarily set the bridge not-ready, cleared queued focus, and rejected exact live panes when mutable projection fields such as state_change_seq changed after a prior focus
fix: preserve focus intake across current-source snapshot refreshes; drain deferred intents across generation changes; authorize each intent against live immutable pane, terminal, workspace, tab, and agent-session identity rather than whole-projection equality; retain stale/offline and identity mismatch rejection. Firmware now also latches raw STM32 key edges from a bounded 2 ms poll task so display flushes cannot hide complete taps.
verification: bridge/focus 42/42; native-board-adapter 9/9; native-hold-controller 23/23; selected-usb build/upload passed; exact device passed six quick alternating taps and one hold/release
files_changed: [firmware/src/board/board_adapter.cpp, firmware/src/board/board_adapter.h, host/herdr_keypad/src/herdr_keypad/bridge.py, host/herdr_keypad/src/herdr_keypad/focus.py, host/herdr_keypad/tests/test_focus.py, host/herdr_keypad/tests/test_integration.py, test/test_board_adapter/stubs/TKeyboardS3Pro.h, test/test_board_adapter/test_main.cpp]
