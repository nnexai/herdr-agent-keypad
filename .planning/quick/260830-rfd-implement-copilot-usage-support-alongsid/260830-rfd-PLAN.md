---
status: planned
created: 2026-08-30
mode: quick
quick_id: 260830-rfd
autonomous: true
files_modified:
  - host/herdr_keypad/native/Cargo.toml
  - host/herdr_keypad/native/Cargo.lock
  - host/herdr_keypad/native/src/ports/copilot.rs
  - host/herdr_keypad/native/src/ports/mod.rs
  - host/herdr_keypad/native/src/ports/status.rs
  - host/herdr_keypad/native/src/core/orchestrator.rs
  - host/herdr_keypad/native/tests/copilot_parity.rs
  - host/herdr_keypad/native/tests/lifecycle_resource.rs
  - host/herdr_keypad/native/tests/production_surface.rs
---

# Add truthful Copilot AI-credit status alongside Codex in the Rust host

<objective>
Add a host-only GitHub Copilot collector that reports the active account's current monthly AI-credit usage, included limit, overage allowance, reset, and freshness through the native bridge's read-only status surface. The collector uses the first-party Rust SDK to own CLI startup and `connect` protocol negotiation, but deserializes the raw `account.getQuota` result so the current-AIC discriminator is not discarded.

Purpose: Make current Copilot AI-credit allowance observable beside the existing Codex collector without spending credits, scraping a terminal, changing device protocol v2, changing firmware, or weakening the host credential boundary.

Output: A pinned and compatibility-gated Copilot SDK/CLI collector, provider-labelled host status, focused collector/runtime regressions, and a non-billable live smoke check against the already-authenticated normal Copilot subscription.
</objective>

<context>
@AGENTS.md
@.planning/STATE.md
@.planning/quick/260830-rfd-implement-copilot-usage-support-alongsid/260830-rfd-RESEARCH.md
@host/herdr_keypad/native/Cargo.toml
@host/herdr_keypad/native/rust-toolchain.toml
@host/herdr_keypad/native/src/lib.rs
@host/herdr_keypad/native/src/ports/codex.rs
@host/herdr_keypad/native/src/ports/mod.rs
@host/herdr_keypad/native/src/ports/status.rs
@host/herdr_keypad/native/src/ports/control.rs
@host/herdr_keypad/native/src/core/orchestrator.rs
@host/herdr_keypad/native/src/protocol/v2.rs
@host/herdr_keypad/native/tests/codex_parity.rs
@host/herdr_keypad/native/tests/lifecycle_resource.rs
@host/herdr_keypad/native/tests/production_surface.rs
@host/herdr_keypad/native/tests/protocol_parity.rs

The current device surface cannot truthfully display Copilot AIC under the locked constraints: protocol v2 exposes a `codex` object with `primary` and `secondary`, and firmware labels that tile `CODEX` with `5H` and `WEEK` rows. A monthly Copilot allowance therefore remains a provider-labelled host status object in this quick task. `RuntimeCoordinator::payload_for`, `protocol::v2::Codex`, all protocol fixtures, and firmware remain unchanged; the device continues to receive only the existing `CodexCollector` view.

The observed current-AIC contract is `quotaSnapshots.premium_interactions` with snapshot-level `tokenBasedBilling: true`. On the authenticated subscription it matched the independent UI result at `usedRequests=1500`, `entitlementRequests=1500`, and `remainingPercentage=0`. The historical-looking map key is not sufficient by itself. A missing or false `tokenBasedBilling` fails closed rather than being relabelled as AI credits.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add the compatibility-gated Copilot AI-credit collector</name>
  <files>host/herdr_keypad/native/Cargo.toml, host/herdr_keypad/native/Cargo.lock, host/herdr_keypad/native/src/ports/copilot.rs, host/herdr_keypad/native/src/ports/mod.rs, host/herdr_keypad/native/tests/copilot_parity.rs</files>
  <read_first>host/herdr_keypad/native/Cargo.toml, host/herdr_keypad/native/rust-toolchain.toml, host/herdr_keypad/native/src/ports/codex.rs, host/herdr_keypad/native/src/ports/mod.rs, host/herdr_keypad/native/tests/codex_parity.rs, .planning/quick/260830-rfd-implement-copilot-usage-support-alongsid/260830-rfd-RESEARCH.md</read_first>
  <behavior>
    - `CopilotCollector` starts the selected `copilot` executable through `github-copilot-sdk` `Client::start` with `Transport::Stdio`. SDK startup must perform `connect {}` and verify `ok`, protocol version 3, and the qualified CLI version before quota. Preserve the SDK's ping fallback only for `connect` method-not-found. Do not copy the observed raw framing shortcut or send Codex-style `initialize`/`initialized` messages.
    - Pin `github-copilot-sdk` exactly to `=1.0.13-preview.2` and retain the Cargo lockfile. The repository toolchain is Rust 1.98.0 and satisfies the crate's Rust 1.94.0 minimum. Use the same installed CLI executable for qualification and the SDK child, qualify the observed `1.0.81` pair, and return unavailable for a missing executable, unqualified CLI version, absent negotiated protocol, or protocol mismatch. Do not silently switch to a different bundled runtime when the selected installed CLI cannot be qualified.
    - Before quota collection, ask the SDK account namespace for current auth only to establish that an active account exists and derive a bounded hash marker for the effective host/account. Immediately discard login, token, auth errors, and the raw auth object; none may enter `Debug`, evidence, status, logs, cache files, or device payloads. Missing auth is `auth_required`, not zero usage.
    - Preserve Copilot CLI host/auth precedence. Do not set a host, endpoint, or token: `COPILOT_GH_HOST` may override `GH_HOST`, stored `copilot login --host` auth remains authoritative, and existing `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, or `GITHUB_TOKEN` behavior remains inside the CLI/SDK boundary. The collector works for github.com and GitHub Enterprise Cloud data-residency hosts selected by that context. An explicit first-party unsupported-host result is unavailable; other failures remain unavailable rather than guessing that a custom hostname is GHES. No fallback account or endpoint is allowed.
    - Retrieve quota with the public raw SDK seam `Client::call("account.getQuota", Some(json!({})))`, not the lossy generated `account().get_quota()` result. Deserialize only the bounded `quotaSnapshots.premium_interactions` object and require `tokenBasedBilling == true`. Preserve and validate `hasQuota`, `entitlementRequests`, `usedRequests`, `remainingPercentage`, `resetDate`, `isUnlimitedEntitlement`, `usageAllowedWithExhaustedQuota`, `overage`, `overageEntitlement`, and `overageAllowedWithExhaustedQuota`; ignore `chat` and `completions` for monthly AIC.
    - Normalize current AIC into a provider-specific `CopilotView` with named AIC fields: source state, used credits, included-credit limit, used percent, overage used/limit/permitted, reset text, observation age, unlimited, reached-limit, and a closed failure reason. Accept only finite, non-negative, integral counts within a documented bound and a finite percentage in 0..=100. Do not infer a reset, clamp malformed input, or derive counts from percentages when counts are absent.
    - `hasQuota=false` is not missing data in token-based mode. For a finite entitlement, exhaustion is current with `reached_limit=true`; retain separate usage/overage-permitted facts so exhausted-but-allowed is not presented as hard-blocked. For `isUnlimitedEntitlement=true` or the documented unlimited sentinel, keep used credits if valid but set limit and percent absent, set unlimited true, and never fabricate 0% or 100% usage.
    - Mirror `CodexCollector`'s bounded 15-second collection deadline, five-minute poll cadence, and 15-minute stale transition. Cache only the normalized view and host/account hash marker; an account-marker change clears prior values before accepting a new baseline. A failed refresh may retain a last value only as stale, never current.
    - The production path calls only SDK connection/auth/quota/shutdown APIs. It never creates a session, submits a prompt, executes `/usage`, passes `-p`, reads `--usage-output-file`, calls a REST billing report, or issues an undocumented HTTP request.
  </behavior>
  <action>
Write focused tests first using the existing `codex_parity.rs` fake-factory/clock style, with an async SDK transport seam that returns raw `serde_json::Value` fixtures and records requested operations. Cover the exact observed token-billing response, zero/exhausted allowance with overage, non-exhausted allowance, unlimited, missing bucket, false/missing AIC discriminator, malformed/non-finite/fractional/oversized values, absent auth, active-account change, timeout, missing CLI, CLI/protocol drift, stale age, and secret/redaction invariants. Assert a GHEC-style active host flows through inherited CLI context without a hardcoded github.com request and assert no model/session method can be emitted.

Then implement `CopilotCollector`, `CopilotView`, a closed `CopilotFailureReason`, the production SDK transport, strict raw-response normalization, bounded cache, and freshness logic in `ports/copilot.rs`; export the module from `ports/mod.rs`. Use the approved first-party crate only at the exact audited version. Do not add an HTTP client, OAuth/PAT handling, terminal scraper, generic provider framework, or second credential store.
  </action>
  <verify>
    <automated>cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test copilot_parity -- --nocapture</automated>
  </verify>
  <done>The collector returns current, provider-labelled AIC counts only for a strictly valid token-based monthly snapshot from the active account; every auth, host, CLI, version, bucket, discriminator, unlimited, malformed, timeout, and stale boundary is explicit and contains no credential or fabricated quota.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Run Copilot beside Codex without publishing it as a Codex window</name>
  <files>host/herdr_keypad/native/src/ports/status.rs, host/herdr_keypad/native/src/core/orchestrator.rs, host/herdr_keypad/native/tests/lifecycle_resource.rs, host/herdr_keypad/native/tests/production_surface.rs</files>
  <read_first>host/herdr_keypad/native/src/ports/status.rs, host/herdr_keypad/native/src/ports/control.rs, host/herdr_keypad/native/src/core/orchestrator.rs, host/herdr_keypad/native/src/ports/copilot.rs, host/herdr_keypad/native/tests/lifecycle_resource.rs, host/herdr_keypad/native/tests/production_surface.rs, host/herdr_keypad/native/tests/codex_parity.rs, host/herdr_keypad/native/tests/protocol_parity.rs</read_first>
  <behavior>
    - `RuntimeCoordinator` owns both `CodexCollector` and `CopilotCollector`, performs one bounded Copilot collection at startup, and advances an independent Copilot deadline in the existing event-driven `tokio::select!` loop. Copilot polling must not block Herdr focus, USB recovery, Codex cadence, cancellation, or control status replies.
    - Add a closed, bounded, provider-labelled `copilot_usage` object to host `StatusSnapshot` and advance that host status schema deliberately. It exposes only normalized AIC fields and closed state/reason enums from Task 1; it contains no raw response, hostname, login, account identifier, path, token, prompt, transcript, or arbitrary error text.
    - A missing, unauthenticated, unsupported, stale, or incompatible Copilot source changes only `copilot_usage`. It does not alter `StatusSnapshot.codex_state`, acknowledged Codex display state, aggregate keypad readiness, focus authorization, Herdr generation, USB publication, or `last_error` precedence used by existing production behavior.
    - Copilot refreshes never call `publish_snapshot`. `RuntimeCoordinator::payload_for` continues to source `protocol::v2::Codex` exclusively from `self.codex.view()`, with existing `primary`/`secondary` Codex windows and diagnostics unchanged. No Copilot count or percentage enters `agent_snapshot`, `diagnostics.codex_*`, firmware, a protocol fixture, or the device.
    - The stopped/no-baseline host status contains a complete unavailable Copilot object. Current/stale/auth-required/unavailable transitions remain independently observable through the existing read-only `status` command, including on github.com or a GHEC host, without making Copilot availability a prerequisite for existing Codex functionality.
  </behavior>
  <action>
Add red coordinator/status tests before wiring production. Extend `StatusSnapshot` with a provider-specific bounded value type and update its encode/decode/duplicate-key/size validation plus targeted lifecycle fixtures. Add an injected fake Copilot transport to coordinator tests and production-surface fake executable setup so tests cannot contact a real account.

Wire `CopilotCollector` into `RuntimeCoordinator::with_config`, startup collection, its own timer branch, shutdown, and `status()`. Keep the Codex collection/publication path semantically unchanged: do not replace it with a provider selector, fallback from Codex to Copilot, rotate providers on the device, map monthly AIC into `primary` or `secondary`, or refactor the v2 payload. Extend the production status test to prove both sources coexist and a Copilot failure leaves the existing Codex status/payload path unchanged.
  </action>
  <verify>
    <automated>cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test lifecycle_resource --test production_surface --test codex_parity --test protocol_parity -- --nocapture</automated>
  </verify>
  <done>The native runtime polls Copilot and Codex independently; `status` reports labelled Copilot AIC truth; all existing Codex, readiness, focus, USB, and v2 payload behavior remains unchanged; and no firmware or device protocol artifact is modified.</done>
</task>

<task type="auto">
  <name>Task 3: Prove the authenticated current-AIC path without spending credits</name>
  <files>host/herdr_keypad/native/tests/copilot_parity.rs</files>
  <precondition>The machine has the confirmed normal Copilot subscription logged into the intended github.com or GitHub Enterprise Cloud host, and the qualified Copilot CLI executable is available to the SDK child.</precondition>
  <action>
Add one ignored live test, `live_authenticated_copilot_reports_current_ai_credits_without_model_call`, that constructs the production collector, uses inherited CLI host/auth state, runs only SDK `connect`/current-auth/`account.getQuota`/shutdown, and prints a redaction-checked JSON object containing only the normalized Copilot view plus safe compatibility facts. The smoke asserts protocol 3, qualified CLI 1.0.81, `tokenBasedBilling=true`, valid used and included AIC counts, a valid reset or explicit reset-unavailable value, and a current source state for this confirmed subscription. It also asserts the host operation allowlist contains no session creation, model request, prompt, slash command, ACP usage request, or REST request.

Run the ignored live test once against the confirmed subscription. Do not compare by invoking interactive `/usage`, do not use `-p '/usage'`, and do not send a harmless-looking model prompt: the proof is the non-model account RPC itself. If active auth, host support, discriminator, or version compatibility fails, preserve safe normalized output and fail the smoke rather than changing host, logging in another account, falling back to github.com, or weakening the gate.

Finally run the focused collector/runtime/Codex/protocol tests and verify device/firmware protocol sources have no diff. This task does not modify firmware or protocol files.
  </action>
  <verify>
    <automated>cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test copilot_parity live_authenticated_copilot_reports_current_ai_credits_without_model_call -- --ignored --exact --nocapture &amp;&amp; cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test copilot_parity --test lifecycle_resource --test production_surface --test codex_parity --test protocol_parity -- --nocapture &amp;&amp; git diff --exit-code -- protocol firmware host/herdr_keypad/native/src/protocol/v2.rs</automated>
  </verify>
  <done>The real authenticated subscription returns its current token-based monthly AIC usage/limit through `account.getQuota` without a model invocation, the result is safely normalized for the active supported host, focused regressions pass, and device protocol plus firmware remain untouched.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|---|---|
| Rust host → first-party SDK/CLI child | The host starts an experimental local protocol pair; executable/version/protocol compatibility must fail closed. |
| CLI auth manager/environment → active account | Stored auth and inherited host/token variables choose one account; the bridge must not override, persist, log, or fall back from that context. |
| CLI JSON-RPC result → normalized AIC view | Raw values and historically named bucket keys are untrusted until bounded and guarded by `tokenBasedBilling=true`. |
| Host status → local operator | Status may expose bounded AIC facts but no token, login, hostname, raw upstream object, or arbitrary error. |
| Host → device | Protocol v2 remains Codex-only; Copilot data must not cross this boundary under the current labels/schema. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|---|---|---|---|---|---|
| T-RFD-01 | Spoofing | Active GitHub account/host | high | mitigate | Inherit CLI auth/host precedence, hash only effective identity for cache replacement, never hardcode/fallback, and treat auth mismatch as auth-required/unavailable. |
| T-RFD-02 | Information disclosure | Raw auth and quota responses | high | mitigate | Extract allowlisted fields inside `ports/copilot.rs`, discard raw auth immediately, close status serialization, and run redaction tests against token/login/host/path/error-shaped keys. |
| T-RFD-03 | Tampering | `premium_interactions` semantic mapping | high | mitigate | Require snapshot-level `tokenBasedBilling=true`; reject missing/false guard and malformed counts rather than labelling legacy request quota as current AIC. |
| T-RFD-04 | Denial of service | CLI child/RPC deadline | medium | mitigate | One bounded collection per cadence, 15-second deadline, SDK-owned shutdown, independent timer, stale cache, and no impact on Codex/readiness/focus. |
| T-RFD-05 | Tampering | Provider-to-device adapter | high | mitigate | Keep `payload_for` Codex-only and prove no diff in protocol/firmware; Copilot is exposed only through labelled host status. |
| T-RFD-SC | Tampering | Cargo/CLI supply chain | high | mitigate | Use the package-legitimacy-audited first-party SDK at exact `=1.0.13-preview.2`, retain `Cargo.lock`, qualify the selected CLI 1.0.81/protocol 3 pair, and use SDK `--no-auto-update`. |
</threat_model>

<verification>
1. Run dedicated `copilot_parity` tests for current-AIC guarding, active-account/host behavior, strict normalization, failure states, freshness, redaction, version compatibility, and the no-model operation allowlist.
2. Run focused runtime/status production tests together with `codex_parity` and `protocol_parity` to prove coexistence without changing Codex or device behavior.
3. Run the ignored production-collector smoke against the confirmed authenticated subscription using only `connect`, current-auth, and `account.getQuota`; require the observed current-AIC discriminator and real monthly counts.
4. Assert no change under `protocol/`, `firmware/`, or `host/herdr_keypad/native/src/protocol/v2.rs`.
</verification>

<success_criteria>
- The Rust host reports current Copilot AI-credit usage and monthly included/overage limits only when `premium_interactions.tokenBasedBilling` proves the current AIC regime.
- github.com and GitHub Enterprise Cloud data-residency accounts follow the user's active CLI host/auth context; no endpoint or credential is hardcoded or separately stored, and unsupported GHES remains unavailable.
- Missing auth, CLI, bucket, discriminator, reset, unlimited limit, malformed response, timeout, stale data, and SDK/CLI mismatch are distinguishable without fabricated zeroes or percentages.
- Copilot and Codex run side by side, but Copilot failure cannot degrade or replace existing Codex collection, device publication, runtime readiness, or focus.
- The live smoke performs no model/prompt/session request and consumes no AI credits.
- Firmware and device protocol v2 remain unchanged.
</success_criteria>

## Source Coverage Audit

| Source | Item | Coverage |
|---|---|---|
| GOAL | Current Copilot AI-credit usage/monthly limits beside existing Codex in Rust host | Tasks 1-3 |
| CONTEXT | Implement in Rust; preserve Codex behavior | Tasks 1-2 |
| CONTEXT | No device protocol or significant firmware change | Provider policy, Tasks 2-3, final diff gate |
| CONTEXT | Truthful provider semantics; no Copilot monthly AIC labelled as Codex 5H/WEEK | Provider policy and Task 2 |
| CONTEXT | Missing auth/CLI/bucket/unlimited/version mismatch remain truthful | Task 1 tests and normalization |
| CONTEXT | Pinned/compatibility-gated first-party strategy when toolchain supports it | Task 1 exact SDK pin, selected CLI qualification, Cargo lock |
| RESEARCH | Use SDK-owned `connect` then `account.getQuota` without a model call | Tasks 1 and 3 |
| RESEARCH | Require snapshot-level `tokenBasedBilling=true`; SDK typed quota drops required fields | Task 1 raw `Client::call` path |
| RESEARCH | Preserve active github.com/GHEC host/account; GHES unsupported | Tasks 1 and 3 |
| RESEARCH | Do not use interactive/ACP usage, prompt mode, REST reports, or undocumented HTTP | Tasks 1 and 3 |
| RESEARCH | Current/stale/auth-required/unavailable semantics and 15-second/15-minute conventions | Tasks 1-2 |
| REQ | No roadmap requirement IDs apply to this quick task | Excluded by quick-mode scope |

No requested or contracted item is deferred or omitted.
