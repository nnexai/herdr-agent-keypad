---
status: awaiting_human_verify
trigger: "Investigate native Rust bridge ready status with a physically blank paired keypad."
created: 2026-08-30T00:00:00Z
updated: 2026-08-30T10:10:00Z
---

## Current Focus

bug_class: Bohrbug
hypothesis: "Three deterministic host defects formed an AND-gate: Linux discarded transient tty enumeration before resolving the exact stable by-id alias; native Herdr requests used envelopes incompatible with installed Herdr 0.8.2; native snapshot diagnostics used sentinels rejected by the device. Status independently masked the first two boundaries."
test: "Run focused RED/GREEN regressions, then start the fixed release against the exact paired device and compare a safe outbound snapshot summary with the exact correlated device ACK."
expecting: "The fixed bridge opens the stable exact device, sends the populated current generation, receives accepted=true with the same epoch/revision/source, and reports readiness only after that ACK."
next_action: "Await physical observation; host wire delivery and device commit ACK are verified."

reasoning_checkpoint:
  hypothesis: "Linux discovery, Herdr envelope incompatibility, and invalid diagnostic sentinels prevent the live snapshot from reaching device commit, while lifecycle-derived status falsely reports readiness."
  confirming_evidence:
    - "Before the fixes, the live process had no serial FD and no outbound snapshot while status reported ready."
    - "Herdr 0.8.2 rejected numeric request IDs, and native rejected its response envelopes without jsonrpc."
    - "After discovery and Herdr fixes, populated snapshots were transmitted but not accepted until UNKNOWN/NONE changed to the Python/device UNAVAL sentinel."
    - "After all fixes, the device returned accepted=true/reason=committed with exact epoch, revision, and source correlation."
  falsification_test: "An accepted correlated ACK before a fix, or failure to obtain one after all three fixes, would falsify or show the hypothesis incomplete."
  fix_rationale: "Each change repairs the first divergent boundary: exact stable endpoint resolution, installed Herdr request/response parity, device-valid snapshot diagnostics, and status derived from coordinator truth."
  blind_spots: "Physical pixels cannot be observed while the user is unavailable; device commit ACK proves protocol admission and commit, not optical panel output."
  candidate_causes:
    - "code: Linux endpoint resolution, Herdr envelope handling, diagnostic sentinel emission, and status wiring"
    - "environment: serialport exposes /dev/ttyACM0 while stable authority is a by-id symlink; installed Herdr 0.8.2 has a string-ID envelope contract"
    - "data: one current working agent and current sparse Codex values exercise non-empty projection admission"
  and_gate: "yes; discovery and Herdr fixes enable transmission, while the sentinel fix is additionally required for device commit; status masking independently hid the failures."

## Symptoms

expected: Exact paired keypad 0000fccb0deabf8c receives and commits the current Herdr projection.
actual: Keypad showed no live content while native status reported ready.
errors: No explicit initial error.
reproduction: Start the installed native bridge with the exact production plugin environment and inspect status, serial ownership, safe outbound projection summary, and correlated ACK.
started: Newly installed native Rust bridge.

## Eliminated

- hypothesis: Staged plugin binary differed from current source.
  evidence: Pre-fix staged and current-source hashes matched byte-for-byte.
  timestamp: 2026-08-30T09:15:00Z
- hypothesis: A correct acknowledged snapshot reached the device and only physical flush remained.
  evidence: Initial process had no serial FD/outbound snapshot; after partial fixes it transmitted but received no accepted ACK.
  timestamp: 2026-08-30T09:30:00Z

## Evidence

- timestamp: 2026-08-30T09:15:00Z
  checked: Pre-fix staged versus current-source release
  found: Both SHA-256 hashes were 892f6736179a64f5ce54354f7d1eb429b4daca07a7aaea32b8a70e213e61d080.
  implication: Stale deployment was not the initial cause.
- timestamp: 2026-08-30T09:25:00Z
  checked: Linux live serial discovery and status
  found: Rust enumerated exact USB metadata at /dev/ttyACM0, but production rejected it as transient despite the exact if01 by-id alias; status still reported ready.
  implication: Native could not open the exact device and readiness was lifecycle-derived rather than ACK-derived.
- timestamp: 2026-08-30T09:45:00Z
  checked: Installed Herdr 0.8.2 request envelope
  found: Numeric ID produced invalid_request; string IDs are required, responses omit jsonrpc, and Python already follows this contract.
  implication: Native could not form the live projection even after USB discovery was repaired.
- timestamp: 2026-08-30T10:00:00Z
  checked: Populated outbound snapshot before sentinel correction
  found: One working agent titled phase 4 implemented and current Codex values were transmitted repeatedly but not accepted; native emitted UNKNOWN/NONE where Python/device require UNAVAL.
  implication: Device snapshot admission rejected invalid diagnostic sentinels.
- timestamp: 2026-08-30T10:05:00Z
  checked: Corrected exact live wire pair
  found: Outbound host-957203 revision 115 source current contained one working agent titled phase 4 implemented and Codex current with primary null, secondary 21, reset WEEK 6D12H1M, age 0M, reached_limit null, and empty error; device ACK returned accepted true, reason committed, and the identical epoch/revision/source.
  implication: Host projection, USB transmission, device admission, and commit ACK are now proven end to end.
- timestamp: 2026-08-30T10:10:00Z
  checked: Clean final deployment
  found: Focused tests passed 36/36; instrumentation was absent; staged and built SHA-256 matched at 5cfd1d50230c2050b98072e150856157d4509af281069b926ad12beeb1482a12; PID 964038 reported running/device ready/Herdr running/Codex ready and owned serial FD 9 resolving to /dev/ttyACM0; no Python bridge process existed.
  implication: The clean staged native release is active on the exact production boundary.

## Resolution

root_cause: "Linux serial discovery rejected serialport's transient tty name without resolving the unique exact if01 by-id alias; native Herdr used numeric IDs and required jsonrpc although installed Herdr 0.8.2 requires string IDs and omits that response field; native diagnostics emitted UNKNOWN/NONE rather than device-valid UNAVAL; coordinator status exposed lifecycle defaults rather than USB ACK and complete Herdr snapshot truth."
fix: "Resolve exactly one canonical if01 by-id alias and fail closed on ambiguity; gate device status on a connected USB session plus accepted exact snapshot ACK; use Herdr string IDs and accept an absent-but-validate-if-present jsonrpc field; derive Herdr status from successful coordinator projection; emit UNAVAL diagnostics sentinels."
verification:
  red_green:
    linux_discovery: "RED 0 candidates vs 1; GREEN 1 exact stable candidate and duplicate alias rejected"
    readiness: "RED ready without USB ACK; GREEN device_unavailable"
    herdr_envelope: "RED InvalidShape; GREEN installed-envelope parity"
    sentinel: "RED live populated snapshot not accepted; GREEN accepted exact ACK"
  focused_tests: "36 passed across lib, herdr_parity, production_surface, usb_platform"
  live_ack: "accepted=true, reason=committed, exact epoch/revision/source match"
  final_hash: "5cfd1d50230c2050b98072e150856157d4509af281069b926ad12beeb1482a12"
  final_pid: 964038
  final_status: "running/device ready/Herdr running/Codex ready"
  python_production: absent
  guardrail_verdict: accepted
oracle_type: specified
files_changed:
  - host/herdr_keypad/native/src/platform/linux.rs
  - host/herdr_keypad/native/src/core/orchestrator.rs
  - host/herdr_keypad/native/src/ports/herdr.rs
  - host/herdr_keypad/native/tests/usb_platform.rs
  - host/herdr_keypad/native/tests/production_surface.rs
  - host/herdr_keypad/native/tests/herdr_parity.rs
