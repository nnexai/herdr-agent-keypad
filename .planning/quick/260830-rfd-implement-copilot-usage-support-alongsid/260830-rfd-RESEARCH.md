# Copilot CLI AI-Credit Usage and Limits Research

**Researched:** 2026-08-30
**Domain:** Current GitHub Copilot AI-credit allowance from a Rust host, including GitHub Enterprise Cloud host selection
**Confidence:** HIGH for the installed RPC response and official terminology; MEDIUM for long-term compatibility because the quota RPC is marked experimental.

## User Constraints

- Use primary sources only: installed `copilot` CLI behavior/help, official GitHub documentation, and first-party GitHub/copilot-cli source or network/API evidence.
- Research current AI-credit usage and monthly limits, not legacy premium-request semantics.
- Support the GitHub host/account currently logged into, including GitHub Enterprise Cloud, without hardcoding `github.com`, a hostname, or separate credentials.
- Clearly distinguish supported public CLI/API behavior from undocumented endpoints.
- Do not change the device protocol or make significant firmware changes.
- Write only this research artifact; do not edit source code, firmware, protocol, `STATE.md`, `ROADMAP.md`, or other planning artifacts.
- Skip formatters, linters, builds, and tests. Do not spend AI credits through a model prompt.

## Summary

**Yes, current AI-credit allowance is machine-readable through the local Copilot CLI server RPC, but not through a standalone CLI usage command.** On 2026-08-30, the installed authenticated CLI (`GitHub Copilot CLI 1.0.81`) accepted a direct framed JSON-RPC call to `account.getQuota` without a model prompt. The result contained `quotaSnapshots` keys `chat`, `completions`, and `premium_interactions`. The `premium_interactions` snapshot reported `tokenBasedBilling: true`, `entitlementRequests: 1500`, `usedRequests: 1500`, and `remainingPercentage: 0`; the interactive `/usage` screen independently displayed `1,500 / 1,500 AIC`. `[VERIFIED: direct local copilot --server --stdio account.getQuota probe and installed interactive /usage probe, 2026-08-30]`

The key name is historical-looking, but current runtime evidence explicitly marks that snapshot `tokenBasedBilling: true`, and its values matched the current AI-credit display. Therefore the implementation may use the `premium_interactions` bucket **only after requiring `tokenBasedBilling == true` (and validating the fields)**; it must not describe or process the bucket as legacy premium-request billing when that flag is true. If the flag is absent/false, reject the mapping as unsupported rather than guessing. `[VERIFIED: direct local account.getQuota response, 2026-08-30]` The official SDK documentation currently documents `account.getQuota` as the account quota operation and names `premium_interactions` as a common runtime key, while current billing docs define the product allowance as GitHub AI Credits. `[CITED: https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing]` `[CITED: https://docs.github.com/en/copilot/concepts/billing/usage-based-billing-for-individuals]`

**Primary recommendation:** add a host-only collector that invokes `account.getQuota` through the pinned first-party Rust SDK/CLI server pair, reads the current AI-credit bucket only when `tokenBasedBilling` is true, preserves the active CLI host/account, and keeps the existing device protocol unchanged. Do not scrape `/usage`, parse `--usage-output-file`, call `-p '/usage'`, or invent a raw HTTP endpoint. `[VERIFIED: first-party SDK and local CLI evidence cited above]`

## Current Monthly AIC Limits

GitHub's current plans page expresses paid-plan allowances as GitHub AI Credits: Copilot Pro has 1,500 total monthly credits, Pro+ 7,000, Max 20,000, Business 1,900 per user per month, and Enterprise 3,900 per user per month. `[CITED: https://docs.github.com/en/copilot/get-started/plans]` The verified local `entitlementRequests: 1500` therefore matches the published Pro total, but a collector must display the returned account value rather than infer a plan from the count. `[VERIFIED: direct local account.getQuota probe; CITED: official plans page]`

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Start Copilot runtime and authenticate | Host Rust | Copilot CLI | Credentials stay on the host; the project explicitly requires host-side credentials and truthful offline/unavailable/stale states. `[VERIFIED: AGENTS.md:20-21]` |
| Resolve active GitHub host/account | Host Rust + inherited CLI environment/auth state | Copilot CLI auth manager | `GH_HOST` and `COPILOT_GH_HOST` select host behavior; default CLI auth is account-scoped. Do not hardcode `github.com`. `[CITED: official CLI command reference]` |
| Retrieve current monthly AI-credit allowance | Host Rust | Local Copilot server | Direct `account.getQuota {}` returns the quota snapshot without a model call. `[VERIFIED: local framed-RPC probe, 2026-08-30]` |
| Normalize and expose status | Host Rust | Existing protocol adapter | Existing `CodexSnapshot` has optional percentages and explicit state/error fields; reuse only at the final adapter boundary. `[VERIFIED: host/herdr_keypad/native/src/lib.rs:98-120]` |
| Render status | Device firmware | Host protocol | Existing protocol field list is fixed for this phase; no firmware/protocol expansion. `[VERIFIED: host/herdr_keypad/native/src/protocol/v2.rs:31-34,197-223]` |

## Public and Observed Surfaces

| Surface | Current evidence | AIC/limit suitability |
|---|---|---|
| Interactive `/usage` | Installed CLI displayed session activity and `Plan ... 1,500 / 1,500 AIC`. `[VERIFIED: installed CLI 1.0.81 interactive probe, 2026-08-30]` | Human-only rendering; no stable machine schema. |
| `--usage-output-file <file>` | Installed help says it writes final usage statistics as JSON. `[VERIFIED: installed copilot --help, 2026-08-30]` | No official account-quota schema; do not parse as plan allowance. |
| ACP `/usage` | Official ACP docs say informational slash commands can run without a model call. `[CITED: https://docs.github.com/en/copilot/reference/copilot-cli-reference/acp-server]` Installed ACP returned only session `AI Units`/request text, no account entitlement/reset fields. `[VERIFIED: installed CLI 1.0.81 ACP probe, 2026-08-30]` | Session usage only, not monthly account allowance. |
| `-p '/usage'` | Installed noninteractive mode treated `/usage` as model input and attempted a model call (the exhausted account returned HTTP 402 `quota_exceeded`). `[VERIFIED: installed CLI 1.0.81 JSON-output probe, 2026-08-30]` | Unsafe and potentially billable; reject. |
| `account.getQuota {}` | Direct local CLI server call returned machine-readable `quotaSnapshots` with current `tokenBasedBilling: true` and AIC-matching counts. `[VERIFIED: direct framed JSON-RPC probe, 2026-08-30]` | Supported implementation path, with experimental API/version caveat. |
| GitHub REST billing reports | Official REST paths include `/users/{username}/settings/billing/ai_credit/usage` and organization equivalents. `[CITED: https://docs.github.com/en/rest/billing/usage]` | Historical reports, not the local account entitlement snapshot; require different identity/scope and should not replace `account.getQuota`. |

## Exact Current RPC Contract (No Model Call)

### Request envelope and ordering

The local probe launched:

```text
/home/linuxbrew/.linuxbrew/bin/copilot --server --stdio --no-auto-update --no-color
```

The process uses Content-Length-framed JSON-RPC over stdin/stdout. The observed envelopes were:

```http
Content-Length: 55\r\n
\r\n
{"jsonrpc":"2.0","id":1,"method":"connect","params":{}}
```

The installed server returned:

```json
{"jsonrpc":"2.0","id":1,"result":{"ok":true,"protocolVersion":3,"version":"1.0.81"}}
```

The SDK source says `Client::start` automatically calls `verify_protocol_version`; that sends `connect` first, forwards a transport connection token when applicable, and falls back to `ping` only when `connect` returns JSON-RPC `-32601 MethodNotFound`. `[VERIFIED: first-party SDK lib.rs:2108-2210]` For this installed CLI, `connect` succeeded, so neither `ping` nor ACP/JSON-RPC `initialize` is needed for the SDK path. `[VERIFIED: direct local CLI 1.0.81 framed-RPC probe, 2026-08-30]`

After the successful `connect`, the quota request envelope was:

```http
Content-Length: 64\r\n
\r\n
{"jsonrpc":"2.0","id":2,"method":"account.getQuota","params":{}}
```

The successful response envelope was:

```json
{"jsonrpc":"2.0","id":2,"result":{"quotaSnapshots":{...}}}
```

The same CLI also accepted `account.getQuota` without a preceding handshake; an `initialize` request returned `{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"Unhandled method initialize"}}`, followed by a successful quota result. `[VERIFIED: direct local CLI 1.0.81 framed-RPC probe, 2026-08-30]` This raw shortcut is not the SDK contract: production code must use the SDK's `connect`/version verification and then call the typed RPC.

The relevant observed `quotaSnapshots` keys were exactly `chat`, `completions`, and `premium_interactions`. `[VERIFIED: direct local account.getQuota probe, 2026-08-30]`

### Snapshot-level fields

`tokenBasedBilling` and `hasQuota` were fields **inside the `premium_interactions` snapshot object**, not result-level fields. The observed current AIC snapshot was:

```json
{
  "entitlementRequests": 1500,
  "hasQuota": false,
  "isUnlimitedEntitlement": false,
  "overage": 100,
  "overageAllowedWithExhaustedQuota": false,
  "overageEntitlement": 100,
  "remainingPercentage": 0,
  "resetDate": "2026-08-30T18:07:54.832Z",
  "tokenBasedBilling": true,
  "usageAllowedWithExhaustedQuota": false,
  "usedRequests": 1500
}
```

`[VERIFIED: direct local account.getQuota probe, 2026-08-30]` The response's exact field set is runtime evidence, not a promise that every field is stable. In particular, `hasQuota`, `overageEntitlement`, and `tokenBasedBilling` are not all represented in the Rust SDK's `AccountQuotaSnapshot` type described below; preserve unknown fields if using a raw response value or require an SDK type update before relying on them. `[VERIFIED: local response compared with first-party SDK source]`

The installed result also contained `chat` and `completions` snapshot objects with `tokenBasedBilling: true`, `isUnlimitedEntitlement: true`, `remainingPercentage: 100`, and `usedRequests: 0`; those are not the current premium-model AIC allowance. `[VERIFIED: direct local account.getQuota probe, 2026-08-30]`

**Current-AIC equivalence rule:** use `quotaSnapshots["premium_interactions"]` as the AIC monthly bucket only when the response's snapshot-level `tokenBasedBilling == true`. The local response's `usedRequests == 1500`/`entitlementRequests == 1500` and the UI's `1,500 / 1,500 AIC` agree for this authenticated subscription, but no explicit `aiCreditsUsed` or `aiCreditsLimit` field exists in the response. `[VERIFIED: local RPC/UI probes]` Treat the relationship as a current runtime contract guarded by the billing flag, not as a timeless meaning of the key. If `tokenBasedBilling` is false or absent, **reject the old premium-interactions mapping** and report the AIC value unavailable.

### Supported contract versus observed current-AIC extension

The official SDK page publicly documents `account.getQuota`, the dynamic `quotaSnapshots` map, common key `premium_interactions`, and four stable-looking fields: `entitlementRequests`, `usedRequests`, `remainingPercentage`, and `resetDate`. It does **not** document an explicit `aiCreditsUsed`/`aiCreditsLimit` field or the `tokenBasedBilling` discriminator. `[CITED: https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing]` The installed CLI 1.0.81 nevertheless returns `tokenBasedBilling`, `hasQuota`, and `overageEntitlement` inside each snapshot, and the current AIC display matched the guarded premium snapshot. `[VERIFIED: direct local account.getQuota and /usage probes, 2026-08-30]` Plan the collector as “supported account.getQuota method + version-pinned observed AIC discriminator,” not as a guaranteed raw AIC-named public field.

## Standard Stack / Dependency Decision

| Library/runtime | Version | Purpose | Recommendation |
|---|---:|---|---|
| GitHub Copilot CLI | `1.0.81` observed | Local server, auth state, quota RPC | Use the CLI selected by the user's installation; do not hardcode host or credentials. `[VERIFIED: installed CLI probes]` |
| `github-copilot-sdk` | `1.0.13-preview.2` observed in crates.io | First-party Rust JSON-RPC client | Pin exact version and pair with a verified CLI. Its generated quota RPC is explicitly experimental. `[VERIFIED: cargo info and first-party SDK source]` |

The first-party Rust SDK exposes `Client::start`, `Transport::Stdio`, and `client.rpc().account().get_quota().await`; it spawns the CLI with `--server --stdio --no-auto-update`. `[VERIFIED: first-party SDK lib.rs:135-152,1060-1073,1813-1835 and generated/rpc.rs:244-297]` The quota RPC source explicitly warns that this wire surface may change and says to pin both SDK and CLI. `[VERIFIED: generated/rpc.rs:253-257]`

**Candidate dependency (not installed into the project during research):**

```bash
cargo add github-copilot-sdk@=1.0.13-preview.2
```

The package legitimacy check returned `OK`; `cargo info` reported the official repository `github.com/github/copilot-sdk`, Rust 1.94.0 minimum, and no postinstall script. `[VERIFIED: gsd package-legitimacy check and cargo info, 2026-08-30]`

## Host and GitHub Enterprise Cloud Behavior

Official CLI documentation states:

- `--host HOST` selects a GitHub host and defaults to `https://github.com`; the documented non-default example is GitHub Enterprise Cloud data residency (`https://example.ghe.com`). `[CITED: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference]`
- `GH_HOST` selects the GitHub hostname for GitHub CLI and Copilot CLI, defaulting to `github.com`; `COPILOT_GH_HOST` overrides `GH_HOST` for Copilot CLI only. `[CITED: official CLI command reference]`
- `copilot login --host https://example.ghe.com` authenticates a GitHub Enterprise Cloud data-residency host. `[CITED: official CLI command reference]`
- GitHub's plans page says Copilot is **not currently available for GitHub Enterprise Server (GHES)**; Copilot Enterprise is for GitHub Enterprise Cloud. `[CITED: https://docs.github.com/en/copilot/get-started/plans]`

The local SDK has no separate `github_host` option in `ClientOptions`; it inherits the child process environment and Copilot CLI's stored auth manager. `[VERIFIED: first-party SDK lib.rs:248-265,690-765]` The SDK's auth-provider documentation passes the effective host into token-provider callbacks, confirming that host is runtime context rather than a hardcoded SDK constant. `[CITED: https://raw.githubusercontent.com/github/copilot-sdk/main/docs/auth/authenticate.md]`

**Effective host/auth precedence supported by first-party docs:**

1. An explicit `--host` on `copilot login` selects the host whose credentials are stored by the CLI. `[CITED: official CLI command reference]`
2. For a running CLI, `COPILOT_GH_HOST` overrides `GH_HOST` for Copilot; otherwise `GH_HOST` selects the host; if neither is set, the CLI defaults to `github.com`. `[CITED: official CLI command reference]`
3. Token environment variables take precedence as documented by CLI help: `COPILOT_GITHUB_TOKEN`, then `GH_TOKEN`, then `GITHUB_TOKEN`; do not create a separate credential store. `[VERIFIED: installed copilot login --help/help environment, 2026-08-30]`
4. The SDK child inherits these settings unless the host application deliberately supplies/removes environment variables through `ClientOptions`; the no-argument `account.getQuota {}` resolves the current server authentication context and has no host parameter. `[VERIFIED: SDK lib.rs:712-730; generated/rpc.rs:260-266; direct RPC probe]`

Implementation requirements:

- Do not hardcode `https://github.com`, `api.github.com`, or a `*.ghe.com` host.
- Start the CLI with inherited environment and stored auth so the user's current supported host/account is used.
- If explicit host selection is needed, pass the user-selected value through the SDK environment option or the documented CLI login flow; never silently override an existing host.
- Support GitHub Enterprise Cloud data-residency hosts. Report GHES unsupported/unavailable because GitHub documents Copilot unavailable there; do not call an undocumented GHES endpoint.
- This requirement is about one active local account, not multi-tenant routing. For a shared service, GitHub's SDK docs recommend per-session tokens for quota checks; that design is out of scope here. `[CITED: https://docs.github.com/en/copilot/how-tos/copilot-sdk/setup/multi-tenancy]`

No GitHub Enterprise Cloud login was attempted during this research; GHEC support is therefore documentation-based, while the direct RPC result was verified against the currently authenticated host on this machine. `[VERIFIED: local probe scope; CITED: official CLI reference and plans page]`

### Active-host acceptance check

Before polling, record only a redacted host identity (hostname, never token) from the effective CLI environment/auth context and verify the quota request succeeds against that context. The collector must not infer host from a hardcoded default, and a host/auth mismatch must produce `auth_required` or `unavailable`, not a quota from another account.

## Architecture Pattern

```text
Host poll scheduler
    -> SDK Client::start (Transport::Stdio), inherited CLI env/auth
    -> local copilot --server --stdio
    -> JSON-RPC account.getQuota {}
    -> quotaSnapshots["premium_interactions"]
    -> require snapshot tokenBasedBilling == true (current AIC guard)
    -> validate entitlement/used/remaining/reset/overage fields
    -> host cache + current/stale/auth_required/unavailable state
    -> existing normalized device payload (unchanged protocol)
```

## Authentication and Security

- The CLI stores authentication state under its normal configuration/keychain flow; official docs identify `~/.copilot` as the default config/state directory and `COPILOT_HOME` as its override. `[CITED: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference]`
- The installed CLI help supports `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, and `GITHUB_TOKEN`; `COPILOT_GH_HOST` can select the Copilot host independently of `GH_HOST`. `[VERIFIED: installed CLI help environment; CITED: official CLI reference]`
- The SDK's explicit token option passes a token to the child only through `--auth-token-env COPILOT_SDK_AUTH_TOKEN`. `[VERIFIED: first-party SDK lib.rs:762-766]` Keep it host-only and never log or serialize it.
- V2/V3/V4 ASVS concerns apply to auth, account selection, and token scope; V5 applies to untrusted RPC response validation; V6 requires no custom cryptography. Use CLI/SDK auth and TLS rather than hand-rolled credential or crypto code.

## Failure and Staleness Policy

| Condition | Host state | Required behavior |
|---|---|---|
| CLI missing, server cannot start, protocol mismatch, RPC timeout | `unavailable` | No fabricated AIC values; keep protocol-valid unavailable payload. |
| No active auth or host/account mismatch | `auth_required` | Do not query a fallback host or account; do not treat absence as zero. |
| GHES host | `unavailable` | GitHub documents Copilot unavailable on GHES; do not use private endpoints. `[CITED: official plans page]` |
| Missing `premium_interactions` | `unavailable` | No AIC value is verified. |
| Snapshot `tokenBasedBilling` absent or false | `unavailable` | Reject the legacy premium-interactions mapping; this guard is mandatory for current-AIC interpretation. |
| Malformed/non-finite counts or percentage | `unavailable` | Reject response; do not coerce invalid data. |
| Valid current response older than freshness threshold | `stale` | Keep value only as stale and expose age; never label current. `[VERIFIED: host/herdr_keypad/native/src/ports/codex.rs:387-399]` |
| `hasQuota=false`, non-unlimited, overage not permitted | current + `reached_limit=true` | Show exhausted AIC allowance. |
| SDK/CLI drift | startup failure/unavailable | Pin versions and run a focused RPC smoke check; SDK marks `account.getQuota` experimental. `[VERIFIED: SDK generated/rpc.rs:253-257]` |

## Common Pitfalls

1. **Calling the AIC bucket “legacy premium requests.”** Current runtime response has `tokenBasedBilling: true` and the UI reports AIC; use the key only under that guard. `[VERIFIED: local RPC/UI probes]`
2. **Expecting an `aiCreditsUsed` field.** The current machine response exposes request-named fields (`usedRequests`, `entitlementRequests`, `remainingPercentage`) plus the billing discriminator; no explicit AIC-named count was observed. `[VERIFIED: local RPC response and SDK source]`
3. **Parsing interactive output.** `/usage` and `--usage-output-file` are not the account quota RPC. `[VERIFIED: local probes and installed help]`
4. **Using ACP `/usage` for plan limits.** ACP probe returned session usage only, even though it avoided a model call. `[VERIFIED: local ACP probe; CITED: official ACP docs]`
5. **Sending `-p '/usage'`.** It invokes the prompt/model path and can fail as a quota-exceeded model call. `[VERIFIED: local JSON probe]`
6. **Hardcoding github.com.** `GH_HOST`/`COPILOT_GH_HOST` and stored CLI auth determine supported host context; preserve them. `[CITED: official CLI reference]`
7. **Claiming GHES support.** GitHub currently says Copilot is unavailable on GHES; only GitHub Enterprise Cloud data-residency hosts are documented here. `[CITED: official plans and CLI reference]`
8. **Confusing session caps with account allowance.** `--max-ai-credits` limits one session/objective; it does not report the monthly account allowance. `[CITED: https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/set-session-limit]`

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|---|---|---:|---:|---|
| Copilot CLI | Local account quota server | Yes | 1.0.81 | Surface unavailable/auth-required if missing on another host |
| Rust compiler | Host collector | Yes | 1.98.0 | None identified |
| Cargo | SDK dependency | Yes | 1.98.0 | None identified |
| GitHub account auth | Account AIC quota | Yes, current CLI auth accepted RPC | active host selected by CLI context | Never use separate fallback credentials |
| GitHub Enterprise Cloud data-residency host | GHEC support | Documented via `--host`, `GH_HOST`, `COPILOT_GH_HOST` | host-dependent | Preserve selected host; no hardcoded URL |
| GitHub Enterprise Server | Copilot | No; GitHub docs say Copilot unavailable | — | Report unsupported/unavailable |

## Validation Architecture

Validation is omitted because `.planning/config.json` sets `workflow.nyquist_validation` to `false`. `[VERIFIED: .planning/config.json:96-101]` The implementation plan should still include a focused, non-billable host smoke check using only `account.getQuota {}` (no model prompt): verify active github.com/GHEC host resolution, exact AIC guard/field mapping, malformed/missing/false guard, auth/timeout, stale behavior, and unchanged protocol serialization.

## Assumptions Log

| # | Claim | Risk if wrong |
|---|---|---|
| A1 | The deployed host can pin a compatible first-party SDK/CLI pair. `[ASSUMED: deployment policy not inspected]` | The collector may need a bundled or user-installed CLI prerequisite. |
| A2 | The existing screen can communicate provider context without changing protocol. `[ASSUMED: full UI semantics not traced]` | Mapping AIC into the fixed Codex-shaped view could mislead users. |

## Open Questions for Planning

1. **How should host identity be displayed or diagnosed?** The collector must preserve the active context, but device fields currently have no provider/host field; decide host-side presentation without protocol expansion.
2. **Which exact CLI release is paired with `github-copilot-sdk` `1.0.13-preview.2`?** The local `1.0.81` RPC worked, but the method is experimental; pin and smoke-test the exact pair.
3. **Should AIC display counts, percentage, or both?** The current device schema has percentage slots but no count fields; avoid implying that a monthly account allowance is a Codex rate-limit window.
4. **How should a token-based subscription with a non-`premium_interactions` key be handled?** Current observed key is `premium_interactions`; runtime keys are not guaranteed by the typed RPC, so missing/renamed buckets should be unavailable until an explicit current mapping is verified.

## Final Recommendation

Implement a host-only Copilot collector using the first-party SDK's `account.getQuota` JSON-RPC over the local CLI server. Preserve the currently logged-in host/account via inherited `GH_HOST`/`COPILOT_GH_HOST` and CLI auth state; do not require separate credentials or hardcode github.com. Interpret `quotaSnapshots["premium_interactions"]` as current AIC allowance only when the snapshot's `tokenBasedBilling` is true, with strict field validation; otherwise reject the old premium mapping and show unavailable. Support GitHub Enterprise Cloud data-residency hosts through the user's active CLI context, and explicitly report GHES unsupported because GitHub documents Copilot unavailable there. Keep firmware and the device protocol unchanged, and use current/stale/auth-required/unavailable semantics rather than fallback scraping or undocumented endpoints.
