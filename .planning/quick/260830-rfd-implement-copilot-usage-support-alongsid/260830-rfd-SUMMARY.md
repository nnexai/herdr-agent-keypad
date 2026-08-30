---
phase: quick
plan: 260830-rfd
subsystem: host-usage
quick_id: 260830-rfd
status: complete
tags: [rust, github-copilot, ai-credits, json-rpc, status]
requires:
  - phase: existing-native-host
    provides: Codex collector, read-only status surface, and event-driven runtime coordinator
provides:
  - Pinned SDK-backed Copilot account/quota collector for current token-based AI credits
  - Bounded provider-labelled Copilot status alongside unchanged Codex/device behavior
  - Focused fake-transport regressions and ignored authenticated non-model smoke test
affects: [native-host, status, usage-telemetry]
tech-stack:
  added: [github-copilot-sdk =1.0.13-preview.2]
  patterns: [SDK-owned stdio connect negotiation, bounded normalized quota view, independent background polling]
key-files:
  created: [host/herdr_keypad/native/src/ports/copilot.rs, host/herdr_keypad/native/tests/copilot_parity.rs]
  modified: [host/herdr_keypad/native/Cargo.toml, host/herdr_keypad/native/Cargo.lock, host/herdr_keypad/native/src/ports/mod.rs, host/herdr_keypad/native/src/ports/status.rs, host/herdr_keypad/native/src/core/orchestrator.rs, host/herdr_keypad/native/tests/lifecycle_resource.rs, host/herdr_keypad/native/tests/production_surface.rs]
key-decisions:
  - "Require quotaSnapshots.premium_interactions.tokenBasedBilling=true before labelling usage as current Copilot AI credits."
  - "Keep Copilot in host status only; protocol v2, device payloads, and firmware remain Codex-only and unchanged."
  - "Inherit the selected Copilot CLI host/auth context and never add host, token, REST, session, prompt, or usage-command fallbacks."
requirements-completed: []
coverage:
  - id: D1
    description: "Current Copilot AI-credit usage, included limits, overage facts, unlimited handling, and freshness are normalized through the pinned SDK collector."
    verification:
      - kind: unit
        ref: "tests/copilot_parity.rs::current_token_billing_snapshot_is_normalized_as_labelled_aic"
        status: pass
      - kind: unit
        ref: "tests/copilot_parity.rs::malformed_nonfinite_fractional_and_oversized_values_fail_closed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Copilot status is provider-labelled and polled independently without entering the Codex/device payload path."
    verification:
      - kind: integration
        ref: "core::orchestrator::tests::copilot_collection_updates_labelled_status_independently_of_codex_state"
        status: pass
      - kind: integration
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test lifecycle_resource --test production_surface --test codex_parity --test protocol_parity -- --nocapture"
        status: pass
    human_judgment: false
  - id: D3
    description: "The authenticated current-AIC production path succeeds through account RPCs without a model invocation and emits only redacted evidence."
    verification:
      - kind: e2e
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test copilot_parity live_authenticated_copilot_reports_current_ai_credits_without_model_call -- --ignored --exact --nocapture"
        status: pass
    human_judgment: false
metrics:
  duration: "approximately 1h"
  completed: 2026-08-30
---

# Quick Task 260830-rfd Summary

**Pinned Rust Copilot SDK account/quota collection now reports current token-based AI-credit usage and monthly limits beside Codex through a bounded host status object, while device protocol and firmware stay untouched.**

## Accomplishments

- Added `CopilotCollector` using `github-copilot-sdk` `1.0.13-preview.2`, SDK-owned `Client::start`/stdio transport, strict protocol 3 and CLI `1.0.81` qualification, inherited auth/host context, and normalized `account.getQuota` data.
- Required `tokenBasedBilling=true`, bounded all counts and percentages, retained overage/unlimited/reset semantics, and fail-closed for missing auth, unsupported/malformed data, timeout, incompatibility, and stale refreshes.
- Added `copilot_usage` to host status schema 2 and independent background polling; Copilot never calls `publish_snapshot` and never enters `protocol::v2::Codex`, firmware, or device payloads.
- Added fake-transport/runtime/status/redaction coverage and ran the authenticated ignored smoke against the installed Copilot CLI using only `connect`, current-auth, quota, and shutdown.

## Task Commits

1. **Task 1 RED: Copilot collector tests** — `792b173` (`test(260830-rfd): add Copilot AIC collector coverage`)
2. **Task 1 GREEN: SDK-backed collector** — `455755e` (`feat(260830-rfd): add guarded Copilot AIC collector`)
3. **Task 2: Runtime/status coexistence** — `93f7613` (`feat(260830-rfd): run Copilot usage beside Codex`)
4. **Task 3: Authenticated smoke coverage** — `7c5ea32` (`test(260830-rfd): prove authenticated Copilot AIC smoke`)

Per the execution contract, this quick-task SUMMARY and planning artifacts remain uncommitted; no metadata commit was made.

## Verification Evidence

- `cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test copilot_parity -- --nocapture`: 12 focused collector tests passed (one ignored live test).
- `cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test copilot_parity live_authenticated_copilot_reports_current_ai_credits_without_model_call -- --ignored --exact --nocapture`: authenticated non-model smoke passed.
- `cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test copilot_parity --test lifecycle_resource --test production_surface --test codex_parity --test protocol_parity -- --nocapture`: 43 tests passed; two required tests remained ignored.
- `git diff --exit-code -- protocol firmware host/herdr_keypad/native/src/protocol/v2.rs`: passed with no protected-surface diff.

## Deviations from Plan

None. The independent Copilot timer uses a bounded background task and channel so a slow SDK/CLI refresh cannot block control, cancellation, USB, Herdr, or Codex handling; this is the required implementation of the plan's independent-polling behavior.

## Issues Encountered

- The initial focused fake fixture helper passed only the nested quota snapshot; it was corrected to pass the complete `quotaSnapshots` response before the Task 1 implementation commit. Final focused tests pass.
- No authentication gate occurred; the installed CLI and active subscription satisfied the live precondition.

## Files and Protected Surfaces

- `host/herdr_keypad/native/src/ports/copilot.rs` — bounded SDK transport seam, normalized AIC view, cache/freshness, and redacted evidence.
- `host/herdr_keypad/native/src/ports/status.rs` — bounded `CopilotUsageStatus` and status schema 2.
- `host/herdr_keypad/native/src/core/orchestrator.rs` — startup collection, independent timer task, and status projection.
- `host/herdr_keypad/native/tests/copilot_parity.rs` — collector fixtures, host-context coverage, and ignored live smoke.
- `host/herdr_keypad/native/tests/lifecycle_resource.rs` and `production_surface.rs` — status schema/redaction and production coexistence assertions.
- No firmware, `protocol/`, or `host/herdr_keypad/native/src/protocol/v2.rs` file was changed.

## Self-Check: PASSED

- Summary file exists at `.planning/quick/260830-rfd-implement-copilot-usage-support-alongsid/260830-rfd-SUMMARY.md`.
- Commits `792b173`, `455755e`, `93f7613`, and `7c5ea32` exist in repository history.
- Focused tests and live smoke passed; protected-surface diff was empty.
