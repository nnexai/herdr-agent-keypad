---
status: resolved
trigger: "During Phase 03.2 physical qualification, focus stays pending/uncertain and the microphone state never appears."
created: 2026-08-22T12:00:00Z
updated: 2026-08-22T13:42:44Z
---

# Qualification closes CDC bridge

## Symptoms

- expected: While the guided presentation batch runs, pressing and holding an agent key focuses that exact Herdr agent and then shows the active microphone/hold presentation.
- actual: Focus remains pending, then becomes uncertain; no microphone state appears.
- error: The operator truthfully answered `N`; the runner preserved a failed presentation checkpoint and raised `RuntimeError: physical qualification failed at presentation; preserving no PASS`.
- timeline: Observed in the first production exact-device Plan 03.2-09 presentation qualification run.
- reproduction: Run `phase32-qualify` under the exclusive bridge lock, complete threshold calibration, then press/hold an agent key during presentation.

## Current Focus

hypothesis: Confirmed — the qualifier owns the exclusive bridge lock but closes its only UsbDeviceSession before prompts, so no qualifier-owned controller remains to publish snapshots, consume exact focus_intent, or return correlated focus_result.
test: `PYTHONPATH=host/herdr_keypad/src:tools/phase1_bringup/src tools/phase1_bringup/.venv/bin/python3 -m unittest tools.phase1_bringup.test_composite_qualification tools.phase1_bringup.test_phase3_smoke -k phase32`
expecting: GREEN with controlled snapshot admission, exact accepted/stale focus correlation, reconnect/republication, live controller lifetime across all prompts, and failed-checkpoint preservation.
next_action: Run a fresh physical qualification with run ID `20260822T134207Z-controller-fix`; do not reuse or modify the terminal failed checkpoint.
reasoning_checkpoint: Root hypothesis confirmed. The healthy device link plus absent snapshot/focus processing matched the closed-session control flow; a controlled exact responder made the deterministic regression GREEN without Herdr access.
tdd_checkpoint: GREEN — 22 focused phase32 tests passed

## Evidence

- timestamp: 2026-08-22T12:00:00Z
  observation: User reported focus remains pending/uncertain and no mic appears during the presentation batch.
  implication: Presentation cannot be accepted and the `N` result is valid.
- timestamp: 2026-08-22T12:00:00Z
  observation: `run_phase32_qualification()` connects for hello/metrics, closes `UsbDeviceSession`, then begins physical prompts while still requiring the inherited exclusive bridge lock.
  implication: No CDC peer remains to handle the device's `focus_intent` during presentation.
- timestamp: 2026-08-22T13:35:49Z
  observation: The keypad connection/health indicators remained healthy while focus failed, and creating a live Herdr agent did not update the keypad during qualification.
  implication: USB enumeration/link health is not the failing boundary; the exclusive qualifier stopped all host-side snapshot and focus processing.
- timestamp: 2026-08-22T13:35:49Z
  observation: The deterministic runner-level controller regression failed RED because no `phase32_live_bridge` seam exists.
  implication: Current runner control flow cannot keep any snapshot/focus responder alive through prompts.
- timestamp: 2026-08-22T13:42:44Z
  observation: The controlled fixture controller regression processed exact accepted focus intents for all three slots, rejected a stale entry, survived exact-session reconnect, and republished the same controlled snapshot.
  implication: The qualifier now owns the complete snapshot/focus round trip throughout the physical batches without connecting to live Herdr.
- timestamp: 2026-08-22T13:42:44Z
  observation: The focused Phase 03.2 command ran 22 tests in 0.090s with status OK.
  implication: Original runner control flow, checkpoint behavior, exact correlation, reconnect, and final gate regressions are GREEN.
- timestamp: 2026-08-22T13:42:44Z
  observation: The original failed checkpoint remains status `failed`, failure step `presentation`, answer `N`, SHA-256 `cac752ccc08f08a7644892dad041b48a1162b1dba3bf0dc6a4205190916d1c53`; final qualification artifacts remain absent.
  implication: No physical PASS or replacement observation was fabricated.

## Eliminated

- hypothesis: The physical hold threshold alone caused the missing microphone state.
  reason: The threshold batch passed, while focus itself remained pending/uncertain; authorization cannot arrive without a CDC responder.
- hypothesis: USB enumeration or CDC transport failed during presentation.
  reason: Device connection/health indicators remained healthy and initial exact hello/metrics passed.
- hypothesis: A live Herdr projection or focus mutation must be added to qualification.
  reason: Qualification is required to stay isolated from live Herdr; a controlled fixture controller can prove exact protocol/session/focus behavior without mutating production state.

## Resolution

root_cause: The exclusive qualification runner closed its sole exact UsbDeviceSession before physical prompts, leaving healthy USB transport with no host controller to publish snapshots, consume focus_intent, or return focus_result.
fix: Commit `74d6b02` adds a qualifier-owned controlled three-slot snapshot/focus controller that retains exact USB ownership across prompts, returns accepted only for exact fixture identity/session correlation, rejects stale targets, reconnects and republishes after lifecycle loss, machine-gates presentation on accepted round trips for all three slots, and never connects to live Herdr.
verification: RED was `AttributeError: phase32_live_bridge is absent`; GREEN was `Ran 22 tests in 0.090s — OK` using the focused phase32 command. The original failed checkpoint was reopened unchanged and no final physical artifacts exist.
files_changed: tools/phase1_bringup/src/phase1_bringup/phase3_smoke.py; tools/phase1_bringup/test_phase3_smoke.py

## Blameless Postmortem

why_not_caught: No runner-level gate asserted that a host snapshot/focus controller remained alive after preflight while the qualifier retained the exclusive bridge lock.
guard: `Phase32QualificationRunnerTests` now covers controlled snapshot publication, exact accepted/stale focus correlation, reconnect/republication, all-prompt controller lifetime, machine-gated presentation, and terminal checkpoint preservation.

## Fresh Qualification Command

`host/herdr_keypad/scripts/ensure-bridge.sh run-exclusive -- env PYTHONPATH=host/herdr_keypad/src:tools/phase1_bringup/src tools/phase1_bringup/.venv/bin/python3 -m phase1_bringup phase32-qualify --binding "$HOME/.config/herdr/keypad-binding.json" --run-id 20260822T134207Z-controller-fix`
