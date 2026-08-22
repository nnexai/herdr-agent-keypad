---
status: resolved
trigger: "Instrument firmware reset diagnostics, rebuild and flash the exact keypad, reproduce the Phase 03.2 qualification USB/HID re-enumeration, identify and fix the root cause, then rerun qualification."
created: 2026-08-22T16:42:00Z
updated: 2026-08-22T18:18:10Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: the confirmed source bug was lifecycle observer logic that treated expected unplug/reset ENODEV as an unexpected interval failure; a separate intermittent same-boot USB protocol/link disturbance remains unresolved below the evidence boundary
  confirming_evidence:
    - the unexpected no-button fault retained one boot_id/reset reason/retained sequence and logged host -EPROTO
    - no cable, connector, USB slot, or host port was changed or reseated before the later 300-second stable non-reproduction window
    - the lifecycle prompt explicitly requires unplug/replug, suspend/resume, reset, and BOOT recovery, so ENODEV and node replacement are expected only during that interval
    - corrected lifecycle capture recorded two verified removals and exact 303a:1001 / 8C:BF:EA:0D:CB:FC remounts with fresh boot/session identities
    - the lifecycle interval ended with KEY_SPACE value 0 and the operator reported the full sequence working with all keys released
  falsification_test: any replacement during threshold/presentation, wrong-identity/no-return lifecycle replacement, unchanged lifecycle boot/session, or final non-UP Space state fails closed; another unattended same-boot -EPROTO event reopens the unresolved low-level disturbance
  fix_rationale: keep threshold/presentation replacement-fatal, but during lifecycle record the old-node teardown, rediscover only the exact device, re-grab the returned node, correlate its admitted boot/session, and continue observing until final UP
  blind_spots: evidence does not distinguish cable, device connector, host controller/port, board PHY/power, or a transient USB stack disturbance
  candidate_causes:
    - unresolved system fault: intermittent USB protocol/link disturbance with host -EPROTO and unchanged MCU boot; physical and software subcauses remain open
    - confirmed code fault: lifecycle observer conflated required device removal with unexpected removal; final builder also incorrectly required mutable boot/session to equal the pre-lifecycle deployment lock
  and_gate: no; the confirmed observer bug independently explains the lifecycle qualification failure, while the earlier unexpected same-boot protocol disturbance is unresolved and was not reproduced in the later bounded window
next_action: none; the final qualification, device evidence, zero-defect ledger, and Phase 4 gate all reopen against the current deployment

## Symptoms

expected: the qualifier owns one stable CDC+HID device for all three batches; Space reports are externally observed without terminal input; normal bridge resumes only after completion
actual: repeated physical gesture batches cause full USB disconnect/re-enumeration; evdev returns ENODEV and the qualifier fails closed
errors: "RuntimeError: Phase 03.2 evdev observer failed for interval presentation: [Errno 19] No such device"
reproduction: run `bash /tmp/phase32-qualify`, complete threshold gestures, then exercise presentation interactions; exact device re-enumerates during the active observer interval
started: post-review Phase 03.2 exact-device qualification on 2026-08-22

## Eliminated

- hypothesis: production bridge takes over between qualification batches
  evidence: run-exclusive retains bridge.lock across the qualifier; bridge PID appears only after Python exits and wrapper cleanup restarts it

- hypothesis: cumulative focus-authorized HID hold or presentation interaction triggers firmware reset
  evidence: the exact ENODEV/re-enumeration reproduced before any button input with zero focus slots and zero Space down/up requests or completions

- hypothesis: qualifier connect, metrics reset, snapshot publish, or EVIOCGRAB deterministically tears down USB
  evidence: each setup stage held devnum 84 for a dedicated 10-second window, and 30 complete CDC setup/close cycles retained devnum 84 and one boot_id

## Evidence

- timestamp: 2026-08-22T16:39:14Z
  checked: kernel journal and bridge.lock/PID ownership
  found: exact device re-enumerated repeatedly at 16:38:59, 16:39:06, and 16:39:13 while qualification owned the lock; production bridge restarted afterward
  implication: remaining fault is device/firmware USB lifecycle, not bridge contention

- timestamp: 2026-08-22T16:40:00Z
  checked: qualification observer with EVIOCGRAB
  found: threshold batch completed without prompt contamination; later device re-enumeration invalidated the grabbed fd and replacement HID node resumed system-wide Space delivery
  implication: EVIOCGRAB fixes prompt feedback only; it intentionally does not mask a device reset

- timestamp: 2026-08-22T14:51:56Z
  checked: retained HID reset journal focused native test
  found: the new interrupted-report/previous-cycle contract failed red because no retained journal existed, then all 3 cases passed after the checksum-protected RTC journal implementation
  implication: the instrumented firmware can distinguish completed prior HID cycles from a reset while a report or lifecycle release was in flight

- timestamp: 2026-08-22T14:51:56Z
  checked: selected-usb instrumented firmware build
  found: PlatformIO selected-usb build completed successfully with reset reason, prior-boot HID report facts, and current hold/lifecycle counters emitted through metrics_ack
  implication: instrumentation is ready to flash to the exact paired device

- timestamp: 2026-08-22T15:02:02Z
  checked: exact-device selected-usb flash and metrics handshake under run-exclusive
  found: firmware uploaded successfully to MAC 8c:bf:ea:0d:cb:fc; metrics_ack returned the expanded typed diagnostic shape; post-flash reset_reason was 11 (ESP_RST_USB), the expected upload baseline
  implication: the exact paired device is running the instrumented production firmware

- timestamp: 2026-08-22T15:02:02Z
  checked: controlled software reset on the exact device
  found: boot_id changed, reset_reason became 3 (ESP_RST_SW), and retained prior-boot facts remained valid with report attempts/completions 36/36, last empty report succeeded, and ControlledReset lifecycle release succeeded
  implication: retained reset telemetry survives a real MCU reboot and accurately locates the final completed lifecycle/report boundary

- timestamp: 2026-08-22T15:02:02Z
  checked: first isolated 90-second physical reproduction window
  found: the controlled fixture and EVIOCGRAB observer stayed stable but captured zero physical events, so the reset could not be reproduced or falsified in that unattended window
  implication: one bounded local human gesture batch remains mandatory; no root-cause source fix is evidence-backed yet

- timestamp: 2026-08-22T15:02:02Z
  checked: bounded local checkpoint command `/tmp/phase32-reset-repro`
  found: command syntax is valid; it owns bridge.lock through run-exclusive, uses the controlled fixture and EVIOCGRAB, prints the exact 12-hold plus encoder batch, captures retained metrics on reconnect, writes no canonical artifacts, and the production bridge is restored afterward
  implication: the next action is a single executable physical checkpoint rather than an open-ended chat prompt

- timestamp: 2026-08-22T15:12:38Z
  checked: no-button exact-device reproduction
  found: observer failed ENODEV and device re-enumerated with accepted_focus_slots empty, Space downs/ups 0/0, current HID request/completion counters all zero, and hid_send_failures zero
  implication: physical gestures, hold threshold, focus authorization, and HID report completion are not triggers

- timestamp: 2026-08-22T15:12:38Z
  checked: post-re-enumeration boot and retained metrics
  found: boot_id remained 0000fccb0deabf8c-2b649ae0, reset_reason remained 3 from the earlier controlled software reset, retained_boot_sequence remained 2, and retained prior-boot report completions remained 36/36
  implication: the MCU did not reset; the USB link disappeared while firmware continued the same boot

- timestamp: 2026-08-22T15:12:38Z
  checked: kernel USB timeline at the no-button fault
  found: disconnect and same-serial re-enumeration included `device descriptor read/64, error -71` (-EPROTO)
  implication: the host directly observed a USB protocol/link disturbance during enumeration, but this does not identify cable, connector, port/controller, board PHY/power, or USB stack as the cause

- timestamp: 2026-08-22T15:12:38Z
  checked: no-button qualifier setup-stage differential
  found: lock-only, CDC connect, metrics reset, snapshot publish, and EVIOCGRAB each remained stable on devnum 84 for 10 seconds
  implication: no individual qualifier setup stage deterministically initiates the teardown

- timestamp: 2026-08-22T15:12:38Z
  checked: repeated CDC/session churn differential
  found: 30 consecutive connect, metrics-reset, snapshot-publish, and close cycles all succeeded on devnum 84 with unchanged boot_id
  implication: CDC control-line churn and protocol setup are not sufficient causes

- timestamp: 2026-08-22T16:55:56Z
  checked: subsequent no-button observation window with no hardware-path change
  found: without changing or reseating the cable, connector, USB slot, or host port, the exact device remained stable for 300 seconds on devnum 84 with one boot_id, zero events, empty observer error, zero Space requests, and zero HID send failures
  implication: the intermittent disturbance did not reproduce in this bounded window; no physical-link fix or low-level root cause is established

- timestamp: 2026-08-22T16:55:56Z
  checked: controlled fresh boot and current-boot safety counters
  found: boot_id advanced to 0000fccb0deabf8c-8b13ee34, retained_boot_sequence advanced to 3, reset_reason was ESP_RST_SW, and current release_all_failures and hid_send_failures were both zero
  implication: prior broken-link safety residue is retained only as prior-boot diagnosis; the qualification boot begins clean

- timestamp: 2026-08-22T16:55:56Z
  checked: fresh-boot no-button setup stability
  found: lock-only, connect, metrics reset, snapshot publish, and EVIOCGRAB each remained stable for 10 seconds on devnum 85 with unchanged boot_id
  implication: every qualifier setup boundary was stable in this bounded fresh-boot observation, without proving a low-level fault correction

- timestamp: 2026-08-22T16:55:56Z
  checked: final-binary deployment and logical lineage refresh
  found: restored the immutable frozen composite prerequisite, wrote deployment 5abd44411450f414a8a611e44adff8d56736ad3007a45d231bd6e6add93b4e36, and captured 72 logical hold frames plus 60 LED rows against the instrumented selected-usb binary
  implication: canonical qualification now targets the actual flashed final binary and current logical evidence

- timestamp: 2026-08-22T16:55:56Z
  checked: canonical qualifier startup
  found: automated preflight passed and the qualifier reached threshold-calibration; no physical events were supplied in the unattended prompt, so it exited without recording a false observation
  implication: only the three fixed human prompts remain; all machine and lineage prerequisites are complete

- timestamp: 2026-08-22T17:35:11Z
  checked: lifecycle-only replacement observer regression
  found: the pre-fix tests were red because lifecycle replacement and non-lifecycle replacement were both accepted by the interval validator; after the fix, Phase32QualificationRunnerTests passed 11/11 and focused strict discovery/final qualification tests passed 11/11
  implication: replacement tolerance is confined to lifecycle and still fails on timeout, wrong/missing serial identity, no return, missing fresh boot/session, or final Space not UP

- timestamp: 2026-08-22T17:35:11Z
  checked: corrected physical lifecycle batch on preserved run 20260822T151500Z-usb-link-fixed
  found: threshold-calibration and presentation remained preserved; lifecycle recorded verified removals followed by exact same-serial remounts at boot/session 0000fccb0deabf8c-86c0e2f8/session-5e85c0bf3e8c2825 and 0000fccb0deabf8c-5ed5eb59/session-beac0966a5ff40a3, then ended with KEY_SPACE value 0; the operator reported every lifecycle action working with keys released
  implication: the corrected lifecycle observer passed the actual exact-device behavior without weakening the other intervals

- timestamp: 2026-08-22T17:35:11Z
  checked: final artifact construction and bridge restoration
  found: lifecycle boot/session lineage now validates against exact remount evidence rather than the intentionally stale deployment boot; finalization then failed closed because `_Phase32FixtureController.measured_evidence()` still returns an empty object, so no final qualification/gate artifact was written; the guarded production bridge was restored and remained running
  implication: USB reset diagnosis and physical lifecycle verification are complete, but Plan 09 cannot close until its pre-existing missing measured-production provider supplies the required 300-case stress, CDC, latency, rows, counters, and zero-defect evidence

- timestamp: 2026-08-22T18:18:10Z
  checked: truthful production measurement provider
  found: the native production probe executed 1,365 HoldController/ProofMetrics/FixedSpaceHid records with zero failures, including the frozen seeded 300-case stress schedule; the exact device completed 2,000 CDC request/ack round trips in each direction after rejecting an overlong frame and accepting the next valid frame, with every strict counter at zero
  implication: Plan 09 rows, counters, latency samples, report reconciliation, and defect derivation now come from executed production code and exact-device traffic rather than synthesized fixtures

- timestamp: 2026-08-22T18:18:10Z
  checked: immutable deployment and final artifact lineage
  found: restored the exact selected-usb binary hash 20bbe16b082af8cc4dfd518eb1321c315912123a363b3ae3392e864e9de8ac65 and frozen feasibility hash 7b4e93ac234c533ea4ee260df30b3a9800a0e4ed7f888e5fffee333cf4b4f4f1; the qualifier reused the preserved all-three-step checkpoint and published qualification a5c0b66c2afc2ba85cca9634e45e4d6cf9fcdcfcf3fa659f253b16224de98a7a plus gate 11f00f604ff1cd658dd8e2f161d72be92be183d4391672bf9ae579068471da03
  implication: no physical batch was repeated or rebound to a different binary

- timestamp: 2026-08-22T18:18:10Z
  checked: final reopen, sidecars, oracle, defects, and bridge restoration
  found: the strict gate validator passed with current deployment, complete qualification, current device evidence, zero open defects, and oracle UP; all six final/deployment/logical SHA-256 sidecars pass `sha256sum -c`; the focused qualification suite passed 21/21, the native probe passed 1/1, and guarded production bridge PID 4010372 remained running after qualification
  implication: Phase 03.2 Plan 09 is complete and production ownership is restored

## Resolution

root_cause: confirmed source bug: the qualifier treated lifecycle's required evdev teardown as an unexpected failure and bound final identity to the obsolete pre-lifecycle boot/session; the earlier intermittent same-boot USB -EPROTO disturbance remains unresolved
fix: qualifier now permits replacement only in lifecycle, rediscovers exact VID/PID/serial, correlates fresh boot/session, re-grabs replacement nodes, requires final KEY_SPACE UP, and binds final identity to measured lifecycle recovery; no cable/port/link fix is claimed
verification: the original no-button ENODEV/-EPROTO evidence retained one MCU boot, a later unchanged-hardware 300-second window did not reproduce it, the preserved physical run completed all three batches with two exact fresh remounts and final Space UP, 1,365 native production observations passed, 4,000 exact-device CDC transactions reconciled with zero strict failures, the focused suite passed 21/21, and the final current-deployment gate reopens with zero defects and oracle UP
files_changed: [firmware/src/metrics/hid_reset_journal.h, firmware/src/metrics/hid_reset_journal.cpp, firmware/src/transport/fixed_space_hid.cpp, firmware/src/app/hold_controller.cpp, firmware/src/main.cpp, protocol/schema/v1.json, tools/phase1_bringup/src/phase1_bringup/protocol.py, test/test_hid_reset_journal/test_main.cpp, tools/phase1_bringup/test_phase22_smoke.py, host/herdr_keypad/tests/test_protocol.py, platformio.ini, tools/phase1_bringup/src/phase1_bringup/phase3_smoke.py, tools/phase1_bringup/src/phase1_bringup/composite_qualification.py, tools/phase1_bringup/test_phase3_smoke.py, tools/phase1_bringup/test_composite_qualification.py, test/test_phase32_measurement/test_main.cpp, artifacts/phase03.2/03.2-FINAL-QUALIFICATION.json, artifacts/phase03.2/03.2-DEVICE-EVIDENCE.json, artifacts/phase03.2/03.2-DEFECT-LEDGER.json, artifacts/phase03.2/03.2-PHASE4-GATE.json]
why_not_caught: lifecycle replacement had no interval-specific regression, final identity validation assumed immutable boot/session, and Plan 09's measured-production provider had never been exercised end to end
guard: focused lifecycle replacement tests plus `03.2-PHASE4-GATE.json`, its current-deployment validator, checkable sidecars, zero-defect ledger, and final KEY_SPACE UP oracle
