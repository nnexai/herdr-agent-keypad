---
status: awaiting_human_verify
trigger: "Installed native Rust bridge reports codex_state: unavailable even though Codex 0.151.0 is installed and visible in the bridge process PATH."
created: 2026-08-30T00:00:00Z
updated: 2026-08-30T08:20:00Z
---

## Current Focus

reasoning_checkpoint:
  hypothesis: "The control status is permanently unavailable because RuntimeCoordinator delegates Status directly to LifecycleOwner, whose active snapshot hardcodes codex_state instead of consulting CodexCollector."
  confirming_evidence:
    - "The sanitized installed 0.151 exchange completed all four stages and supplied a normalizable primary window."
    - "The deterministic production regression timed out with codex_state unavailable even though its 0.151 fixture completed the same successful handshake."
    - "Code tracing shows device payloads read self.codex.view(), while control Status bypasses that path and receives LifecycleOwner's hardcoded unavailable value."
  falsification_test: "If routing a status snapshot through the collector view does not turn the same deterministic production test green, the wiring hypothesis is false or incomplete."
  fix_rationale: "Overlaying the lifecycle snapshot's Codex field from the already-authoritative normalized collector state makes the read-only control surface report the same source health without changing transport, cache, privacy, or lifecycle semantics."
  blind_spots: "The real Herdr process and physical device are intentionally not exercised; the live collector and production control socket are exercised independently."
  candidate_causes:
    - "code: control status bypasses CodexCollector and retains a hardcoded unavailable field"
    - "environment: installed Codex 0.151 could have changed request/response shapes or exceeded line bounds"
    - "data: account/read may report requiresOpenaiAuth true alongside a present account and sparse secondary limits"
  and_gate: "no; protocol/environment/data candidates were reproduced successfully, while the unconditional status assignment alone fully explains the symptom."
bug_class: Bohrbug
next_action: Await integration-owner confirmation after the committed RED and fix are merged; no additional repository action is required.

## Symptoms

expected: The bridge reports a truthful normalized Codex state, current when the authenticated account supplies rate limits, with primary and secondary percentages when available.
actual: The installed bridge reports codex_state unavailable.
errors: No bounded stage/code captured yet; Codex 0.151.0 is installed and is in the bridge process PATH.
reproduction: Invoke the native collector in the installed environment or replay the exact 0.151.0 app-server protocol shape through a deterministic fixture.
started: Observed with installed Codex 0.151.0; compatibility baseline was built around 0.147-era optional/null/sparse fixtures.

## Eliminated

- hypothesis: Codex 0.151 changed the stable request parameter schema.
  evidence: Generated 0.151 schema accepts the collector's account/read object and null rate-limits params; the live exchange completed both methods.
  timestamp: 2026-08-30T08:05:00Z
- hypothesis: The installed app-server is unavailable, unauthenticated, or returns oversized/malformed data.
  evidence: The bounded live exchange completed with an account-present result, one allowed notification, and a 1355-byte normalizable rate-limit response.
  timestamp: 2026-08-30T08:05:00Z

## Evidence

- timestamp: 2026-08-30T00:00:00Z
  checked: User-reported environment
  found: Codex 0.151.0 exists at the configured executable location and is visible through the bridge process PATH.
  implication: A simple missing-binary explanation is contradicted; protocol, transport, auth, and wiring remain candidates.


- timestamp: 2026-08-30T07:50:00Z
  checked: Installed Codex 0.151.0 generated stable schema
  found: The stable request schema still requires `account/read` params and accepts null `account/rateLimits/read` params; the rate-limits response retains top-level `rateLimits`, `rateLimitsByLimitId`, and `rateLimitResetCredits`.
  implication: The collector request parameter shapes are version-compatible; a changed request schema is eliminated.
- timestamp: 2026-08-30T07:50:00Z
  checked: Bounded read-only live stdio exchange
  found: initialize returned a result in 211 bytes; account/read returned after one allowed notification in 124 bytes with account present and requiresOpenaiAuth true; account/rateLimits/read returned a 1355-byte result with top-level rateLimits and one supplied window while the other was null.
  implication: Codex access, auth, interleaving, line bounds, and the documented 0.151 response shape all succeed without exposing identity or raw provider data.
- timestamp: 2026-08-30T07:50:00Z
  checked: Runtime coordinator and lifecycle status wiring
  found: The coordinator collects Codex and publishes its normalized view to device snapshots, but every control status request delegates to LifecycleOwner whose active status hardcodes codex_state to unavailable.
  implication: The reported bridge status cannot reflect any successful collection; status wiring is the leading deterministic root-cause hypothesis.
- timestamp: 2026-08-30T08:05:00Z
  checked: Agent-authored production-surface regression
  found: The exact 0.151 fixture regression failed deterministically because status never reflected the successful Codex collection.
  implication: The hardcoded status path reproduces the user-visible failure independently of host auth and provider data.

- timestamp: 2026-08-30T08:20:00Z
  checked: Fixed collector and control status
  found: The live Rust collector completed initialize, initialized, account/read, and account/rateLimits/read with no bounded error code; its redacted normalized result was current with primary null and secondary 15. The fixed production status regression reported ready.
  implication: The collector is compatible with installed 0.151, and the corrected control surface now reflects the authoritative normalized state.
- timestamp: 2026-08-30T08:20:00Z
  checked: Focused verification and guardrail
  found: codex_parity passed 9 tests with 1 live diagnostic ignored by default; production_surface passed 7 tests; cargo check passed with only pre-existing dead-code warnings; a current-to-unavailable mutant made the driving regression fail.
  implication: The regression detects the fix site, adjacent native surfaces remain compatible, and compilation succeeds.

## Resolution

root_cause: RuntimeCoordinator delegated control Status directly to LifecycleOwner, whose active status unconditionally set codex_state to unavailable and never observed CodexCollector.
fix: RuntimeCoordinator now overlays active lifecycle status with the bounded CodexCollector source state and handles control Status through that coordinator snapshot; current maps to ready, stale to stale, Codex offline to codex_unavailable, and other non-current states remain unavailable.
verification:
  target_test: { result: pass }
  mutation_check: { result: pass, reason_if_skipped: null, mutant_killed: true }
  no_op_deletion: { result: pass, deletion_justified_by_rca: false }
  adjacent_tests: { result: pass, suites_run: [codex_parity, production_surface, cargo_check] }
  revert_and_reconfirm: { result: pass, bug_returned_on_revert: true, fixed_on_reapply: true }
  guardrail_verdict: accepted
  live_diagnostic:
    handshake: [initialize, initialized, account/read, account/rateLimits/read]
    source_state: current
    primary: null
    secondary: 15
    error_code: ""
    redaction: pass
files_changed:
  - host/herdr_keypad/native/src/core/orchestrator.rs
  - host/herdr_keypad/native/tests/codex_parity.rs
  - host/herdr_keypad/native/tests/production_surface.rs
  - .planning/debug/live-codex-unavailable.md
oracle_type: specified
