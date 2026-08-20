# Phase 3: Truthful Codex Capacity and Device Menu - Research

**Researched:** 2026-08-17  
**Domain:** Installed Codex CLI/app-server account limits, host-authoritative freshness, bounded device protocol, and T-Keyboard S3 Pro encoder/brightness seams  
**Confidence:** HIGH for the installed binary/schema and observed authentication mode; MEDIUM for backend rate-limit availability and the product freshness threshold; MEDIUM for menu integration because the product bridge/menu does not yet exist

## Summary

Phase 3 must use the installed Codex app-server as the only provider boundary. The executable is `/home/linuxbrew/.linuxbrew/bin/codex`, resolving to the Homebrew-managed `@openai/codex` entrypoint, and reports `codex-cli 0.147.0` [VERIFIED: `codex --version`]. Its stable schema generator succeeded without `--experimental` and wrote version-matched JSON Schema files to `/tmp/codex-schema-01470`; the relevant files were hashed before inspection [VERIFIED: `codex app-server generate-json-schema --out /tmp/codex-schema-01470`; SHA-256 values recorded below]. The official app-server protocol requires a JSONL `initialize`/`initialized` handshake before account requests and documents `account/rateLimits/read` as the complete ChatGPT rate-limit snapshot, with `account/rateLimits/updated` explicitly sparse [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md].

A live authenticated app-server probe returned `account.type = "chatgpt"`, `planType = "prolite"`, and `requiresOpenaiAuth = true`; the account email was intentionally not copied into this artifact [VERIFIED: local `codex app-server --stdio` probe, request `account/read`]. The same process accepted `account/rateLimits/read` but produced no response during a 90-second observation window, so this research has **no observed primary/secondary percentages, reset timestamps, credits, or reached-limit values** for the real account. A fresh app-server using an isolated empty Codex home returned `{ "account": null, "requiresOpenaiAuth": true }` for `account/read`, demonstrating the unauthenticated shape but not the reason the authenticated rate-limit call did not complete [VERIFIED: local probes]. The Phase 3 implementation must therefore render quota fields unavailable until a successful full read and must not fill the gap with zeroes or plausible sample values.

The generated installed schema is precise enough to plan normalization: top-level `rateLimits` is required; both `primary` and `secondary` are optional/nullable windows; each supplied window requires `usedPercent` while duration and reset time are nullable; credits, monthly spend-control data, plan, limit-reached classification, multi-bucket data, and earned reset-credit details are optional or nullable. The sparse notification schema says to merge into a known full snapshot or refetch, and it explicitly says nullable metadata in a rolling update does not clear prior values [VERIFIED: `/tmp/codex-schema-01470/v2/GetAccountRateLimitsResponse.json:141-275,277-311`; `/tmp/codex-schema-01470/v2/AccountRateLimitsUpdatedNotification.json:191-201`]. The host bridge must own observation timestamps, source status, retry/refetch, and credential handling; firmware receives only bounded normalized values and freshness metadata.

**Primary recommendation:** Pin and record the installed Codex binary plus generated stable schema, perform a full `account/read` and `account/rateLimits/read` after every app-server session initialization, merge only documented sparse fields into a known full snapshot, keep Codex freshness independent from Herdr/link freshness, and fail closed to explicit unavailable/auth/offline states when the full read has not completed.


## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Codex authentication and app-server lifecycle | API / Backend (host Codex process) | Host bridge collector | Codex owns ChatGPT OAuth/token persistence and refresh; the bridge should request account/limits but never receive or forward secrets. |
| Full quota observation | Host bridge collector | Codex app-server | The bridge owns request timeout, success timestamp, error classification, and the last complete snapshot; app-server owns upstream account semantics. |
| Sparse update merge | Host bridge collector | Codex app-server notifications | The installed notification schema is explicitly sparse; merge/refetch policy must be host-side and never delegated to firmware. |
| Freshness/error projection | Host bridge / snapshot assembler | Firmware clock and renderer | Host records source status and observation age; firmware only displays bounded normalized state and may age a cached observation visibly. |
| Quota tile rendering | Firmware device renderer | Host normalized snapshot | The fourth panel is a fixed read-only surface; host supplies values/status, while the device draws fixed bounded labels and cues. |
| Encoder menu navigation | Firmware board/input/UI layers | Host protocol for persisted setting acknowledgement | Encoder click/direction are physical input; agent keys 1–3 remain direct and must not be routed through menu state. |
| Brightness persistence | Firmware settings storage | BoardAdapter display API | The board adapter applies brightness; a separate bounded settings record must persist only brightness, not inbox bindings or provider data. |
| Diagnostic projection | Host snapshot/diagnostics assembler | Firmware menu renderer | Host can provide bounded versions, source statuses, revisions, and timestamps; it must not expose host paths, prompts, transcripts, or account identifiers. |
| Device protocol admission and atomic snapshot | Existing Phase 1 ProtocolSession | Host codec | Phase 1's sole bounded codec/session boundary must be extended rather than bypassed; complete snapshots must remain atomically paired with bindings. |
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CODEX-01 | The fourth display remains dedicated to read-only Codex subscription usage and shows both primary and secondary usage-window percentages when the installed account supplies them. [VERIFIED: `.planning/REQUIREMENTS.md:30-35`] | Installed stable schema exposes nullable `primary` and `secondary` windows, each with required `usedPercent`; observed account is ChatGPT-backed, but the real rate-limit values were not returned during this research. |
| CODEX-02 | The fourth display shows the nearest relevant reset information and a reached-limit indication when those values are supplied. [VERIFIED: `.planning/REQUIREMENTS.md:30-35`] | Schema exposes nullable `resetsAt`, nullable `rateLimitReachedType`, and optional reset-credit metadata; do not infer a reset or reached state when absent/null. |
| CODEX-03 | The fourth display preserves absent or null usage fields as unavailable and distinguishes current, stale, unavailable, authentication-failed, and host-offline data. [VERIFIED: `.planning/REQUIREMENTS.md:30-35`] | Full and sparse schemas preserve optional/null fields; local authenticated and unauthenticated probes provide distinct account observations, while the project owns the visible freshness/error state model. |
| CODEX-04 | The fourth display shows observation age or equivalent last-updated information. [VERIFIED: `.planning/REQUIREMENTS.md:30-35`] | App-server fields contain quota timestamps (`resetsAt`) but no observation timestamp; bridge must stamp successful full/sparse observations itself. |
| SYNC-03 | Agent-inbox freshness, Codex freshness, and device-link health are tracked and rendered independently. [VERIFIED: `.planning/REQUIREMENTS.md:37-44`] | Existing architecture explicitly separates source statuses and timestamps; Codex request failure must not blank current Herdr tiles. [VERIFIED: `.planning/research/ARCHITECTURE.md:160-179,241-245`] |
| SAFE-01 | Credentials remain on the host; firmware receives only bounded normalized data, opaque identities, freshness metadata, and focus results. [VERIFIED: `.planning/REQUIREMENTS.md:37-44`] | Local auth file is mode `0600`; official app-server owns managed ChatGPT tokens; generated initialize response includes a host path that must never cross the device boundary. |
| MENU-01 | Encoder click opens/closes a secondary menu without making agent keys modal. [VERIFIED: `.planning/REQUIREMENTS.md:46-51`] | Phase 1 physically confirmed encoder click as raw key 4; current runtime only arms click during bring-up probes, so a product menu state machine remains to be added. |
| MENU-02 | Menu shows link, independent Herdr/Codex health, last full sync, and last Codex observation. [VERIFIED: `.planning/REQUIREMENTS.md:46-51`] | Host-side normalized snapshot architecture already calls for independent source status and observed timestamps; firmware menu renderer is not yet implemented. |
| MENU-03 | Menu shows bounded troubleshooting IDs and firmware/protocol versions without credentials, transcripts, raw prompts, or host paths. [VERIFIED: `.planning/REQUIREMENTS.md:46-51`] | Phase 1 hello/metrics path exposes firmware/protocol and bounded counters; Codex initialize exposes `codexHome`, which must be redacted rather than forwarded. |
| MENU-04 | Brightness changes persist without changing inbox order, rendered identity, or focus semantics. [VERIFIED: `.planning/REQUIREMENTS.md:46-51`] | `BoardAdapter::setBrightness()` and verified physical brightness samples exist, but no persistence seam is present in inspected firmware; persistence must be isolated from snapshot/binding state. |

## Project Constraints (from AGENTS.md)

- The device is a four-display-key, RGB-LED, clickable-encoder LILYGO T-Keyboard S3 Pro; direct agent selection cannot require encoder navigation. [VERIFIED: `AGENTS.md:13-22`]
- Herdr remains the inbox authority; the device must not invent lifecycle/order semantics. [VERIFIED: `AGENTS.md:13-22`]
- Provider credentials and authenticated Codex access stay on the host; firmware receives device-scoped normalized data only. [VERIFIED: `AGENTS.md:19-22`]
- Offline, unavailable, and stale data must be visibly distinguishable. [VERIFIED: `AGENTS.md:19-22`]
- Planning consumes this research without changing Phase 1/2 authority: implementation extends the permanent Phase 2 bridge/protocol/rendering seams and keeps Phase 1 hardware/transport evidence intact.

## Standard Stack

### Core

| Component | Version / pin | Purpose | Why Standard |
|---|---|---|---|
| Codex CLI/app-server | `0.147.0` observed | Host-side account and rate-limit boundary | Installed binary provides the stable JSONL app-server and version-matched schema generator. [VERIFIED: `codex --version`; `codex app-server --help`] |
| Codex stable generated JSON Schema | Generated by installed `0.147.0` without `--experimental` | Exact request/response/notification types | The app-server docs state generated output is specific to the binary that produced it; generated `v2` files are the planning source of truth. [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md; VERIFIED: `/tmp/codex-schema-01470`] |
| Python standard library | Project target `>=3.11`; host probe `3.14.7` | Bridge subprocess, JSONL, timers, bounded normalization, persistence | Existing project research selects stdlib Python for Herdr/Codex host glue; no additional package is required for the app-server protocol. [VERIFIED: `.planning/research/STACK.md:40-46`] |
| Existing Phase 1 protocol/session | Protocol v1, 4096 encoded bytes including LF | Transport-neutral framed host/device boundary | Phase 1 froze one bounded codec/session with sequence, digest, and rejection semantics; Phase 3 should add typed normalized messages at this boundary. [VERIFIED: `protocol/schema/v1.json:1-27,79-82`; `.planning/STATE.md:87-93`] |
| Official T-Keyboard S3 Pro board abstraction | Existing pinned board library path | Four displays, encoder, keys, brightness, LEDs | `BoardAdapter` already isolates the official Pro abstraction and prevents raw panel/GPIO paths. [VERIFIED: `firmware/src/board/board_adapter.h:9-35`] |

### Supporting

| Component | Version / pin | Purpose | When to Use |
|---|---|---|---|
| `account/read` | Stable app-server method | Determine current provider account/auth requirement | Call after every app-server initialization and on auth/account change; do not infer ChatGPT subscription from a generic network success. |
| `account/rateLimits/read` | Stable app-server method | Obtain a complete quota snapshot | Call only after initialize/initialized; use a bounded timeout and mark Codex source offline/unavailable on failure. |
| `account/rateLimits/updated` | Stable notification | Receive rolling quota changes | Merge only into an existing full snapshot or trigger a refetch; never treat the notification as a complete replacement. |
| Local app-server stdio JSONL | Default supported transport | Avoid unsupported WebSocket listener dependency | Use one supervised subprocess per bridge lifecycle; parse only bounded JSONL and keep stderr out of the device stream. |
| Firmware `BoardAdapter::setBrightness()` | Existing API seam | Apply current brightness to all board panels through official library | Use from menu setting path; do not duplicate raw panel writes. [VERIFIED: `firmware/src/board/board_adapter.cpp:68-71`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Local app-server JSONL | Direct ChatGPT backend HTTP | Rejected: private backend/auth contract and credentials would move into the bridge/device boundary; app-server is the supported local protocol. [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md] |
| Full read + sparse merge | Treat every `updated` notification as a replacement | Rejected: loses omitted fields and can falsely clear known metadata; official schema explicitly calls updates sparse. [VERIFIED: `/tmp/codex-schema-01470/v2/AccountRateLimitsUpdatedNotification.json:191-201`] |
| Host-owned freshness timestamp | Use `resetsAt` or `windowDurationMins` as TTL | Rejected: reset is provider quota timing, not observation age. D-05 fixes full polling at 300 seconds and staleness at 900 seconds. |
| Fixed firmware menu | Encoder-required browsing for agent tiles | Rejected by Phase 3/PROJECT constraints; agent keys must remain direct and non-modal. [VERIFIED: `.planning/ROADMAP.md:121-125`; `.planning/PROJECT.md:47-56`] |
| Separate brightness settings record | Store brightness in snapshot or bindings | Rejected: couples user preference to authoritative inbox generation and risks changing focus semantics. |

**Installation:** No package installation is recommended for this phase. Use the installed `codex` executable and existing project runtime/toolchain.

**Version verification:** `codex --version` returned `codex-cli 0.147.0`; `codex app-server generate-json-schema --out /tmp/codex-schema-01470` completed successfully. [VERIFIED: local commands]

## Codex Evidence From the Installed Binary

### Binary and schema generation

- `command -v codex` returned `/home/linuxbrew/.linuxbrew/bin/codex`; `readlink -f` resolved it to `/home/linuxbrew/.linuxbrew/lib/node_modules/@openai/codex/bin/codex.js`. [VERIFIED: local command]
- `codex --version` returned exactly `codex-cli 0.147.0`. [VERIFIED: local command]
- `codex app-server --help` reports stdio as the default transport and exposes `generate-json-schema`; WebSocket listener mode is documented as experimental/unsupported in the official README. [VERIFIED: local help; CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md]
- Stable schema generation completed without `--experimental`. Relevant artifact hashes: `GetAccountResponse.json` = `dc770d8377dfe9b93b67e857e22ba7f99726265c8ca5cae63c5ad06e78b70b9d`; `GetAccountRateLimitsResponse.json` = `c67762e486f5a9b081ec42650fce657781669e6b1261c09c47bc8085d8cf2fc1`; `AccountRateLimitsUpdatedNotification.json` = `3187c452ad240a5ba5717f1b2898f38b7607feb4d287636b4206e19ffcc22e31`; `AccountUpdatedNotification.json` = `8fbd02e12546f39a500eb04f9d39bb5529c0f165c9514497cfe5668a52d21aab`; `LoginAccountParams.json` = `68cbb2156f0c9d449af9356915c7c2fb73d2ce1cbce1e6e2e6b6bb3e6fb7f646` [VERIFIED: local `sha256sum` output].

### Authentication mode and account/read observations

The normal local probe sent one `initialize`, then `initialized`, then `account/read` with `refreshToken: false`. The returned result was:

```json
{
  "account": {"type": "chatgpt", "planType": "prolite"},
  "requiresOpenaiAuth": true
}
```

The returned `email` field was present but is deliberately omitted above and must not be sent to the device. [VERIFIED: live local app-server response; redaction is intentional]

The generated account schema has these exact alternatives and fields:

- `Account` alternatives quote `"apiKey"`, `"chatgpt"`, and `"amazonBedrock"`; the ChatGPT variant includes nullable `email` and required `planType`, while the Bedrock variant includes `usesCodexManagedCredentials` [VERIFIED: `/tmp/codex-schema-01470/v2/GetAccountResponse.json:4-69`].

`GetAccountResponse` has optional/nullable `account` and required `requiresOpenaiAuth` [VERIFIED: `/tmp/codex-schema-01470/v2/GetAccountResponse.json:92-111`]. `AccountUpdatedNotification` has nullable `authMode` and nullable `planType`; its installed auth-mode enum quotes `"apikey"`, `"chatgpt"`, `"chatgptAuthTokens"`, `"headers"`, `"agentIdentity"`, `"personalAccessToken"`, and `"bedrockApiKey"` [VERIFIED: `/tmp/codex-schema-01470/v2/AccountUpdatedNotification.json:4-56,79-102`]. Official docs say managed ChatGPT auth owns OAuth flow and refresh tokens, while API-key auth is a separate mode; the quota collector must not label an API-key account as ChatGPT subscription capacity [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md].

### Full rate-limit response shape

The installed schema quotes the top-level response as `GetAccountRateLimitsResponse` with required `"rateLimits"` and nullable `"rateLimitsByLimitId"` and `"rateLimitResetCredits"` [VERIFIED: `/tmp/codex-schema-01470/v2/GetAccountRateLimitsResponse.json:277-311`]. The full snapshot's fields are:

| Field | Installed schema fact | Device implication |
|---|---|---|
| `rateLimits.primary` | Optional and nullable `RateLimitWindow` [VERIFIED: schema `141-193`] | Render primary only when an object and `usedPercent` are supplied; otherwise show `UNAVAILABLE`, never `0%`. |
| `rateLimits.secondary` | Optional and nullable `RateLimitWindow` [VERIFIED: schema `195-214`] | Same rule; absence/null is not an empty or zero secondary bucket. |
| `RateLimitWindow.usedPercent` | Required integer when a window object is present [VERIFIED: schema `225-249`] | Preserve the supplied integer; clamp/reject only if the normalized protocol has a separately frozen bound. |
| `windowDurationMins` | Optional nullable integer [VERIFIED: schema `225-249`] | Do not use as observation age or assume a reset period when absent. |
| `resetsAt` | Optional nullable Unix-seconds integer [VERIFIED: schema `225-249`] | Show a reset only when supplied; calculate a countdown from a host/device clock without claiming a reset when null. |
| `rateLimitReachedType` | Optional nullable enum quoting `"rate_limit_reached"`, `"workspace_owner_credits_depleted"`, `"workspace_member_credits_depleted"`, `"workspace_owner_usage_limit_reached"`, and `"workspace_member_usage_limit_reached"` [VERIFIED: schema `45-53,195-203`] | Show reached-limit cue only for a supplied value; null/missing is `UNAVAILABLE`, not `NOT REACHED`. |
| `planType` | Optional nullable enum quoting `"free"`, `"go"`, `"plus"`, `"pro"`, `"prolite"`, `"team"`, `"self_serve_business_prolite"`, `"self_serve_business_usage_based"`, `"business"`, `"ent26"`, `"enterprise_cbp_automation"`, `"enterprise_cbp_usage_based"`, `"enterprise"`, `"edu"`, and `"unknown"` [VERIFIED: schema `25-43,175-183`] | Use as bounded plan label only when supplied; do not derive a plan from percentages or account email. |
| `credits` | Optional nullable `CreditsSnapshot` with required `hasCredits` and `unlimited`, and nullable string `balance` [VERIFIED: schema `141-152`; `5-23`] | Treat null/missing balance as unavailable; do not convert string balances to guessed percentages. |
| `individualLimit` | Optional nullable `SpendControlLimitSnapshot`; when supplied, `limit`, `used`, `remainingPercent`, and Unix-seconds `resetsAt` are required [VERIFIED: schema `153-161,251-275`] | This is optional monthly/spend-control data, not a replacement for primary/secondary windows. |
| `spendControlReached` | Optional nullable boolean; schema description says null is unavailable [VERIFIED: schema `215-221`] | Preserve unknown/null distinctly from false. |
| `rateLimitsByLimitId` | Nullable object mapping opaque metered limit IDs to snapshots, described as a multi-bucket view; the installed schema does not document a key that Phase 3 may select [VERIFIED: schema `296-305`] | `rateLimits` remains the sole selectable capacity source. Record map presence only through a bounded redacted key manifest. Never select an undocumented map key. A map-only or unusable-map response normalizes capacity unavailable with internal classification `bucket_unavailable` and the allowlisted device/diagnostic code `E-2401`. |
| `rateLimitResetCredits` | Nullable summary with required `availableCount`; `credits` is nullable and may be capped [VERIFIED: schema `112-133,278-286`] | Reset-credit count/details are snapshot-only; display only if supplied and bounded. |

The closed Phase 3 disposition covers six response shapes. A valid top-level `rateLimits` object is authoritative when the map is omitted, null, or also present. A map without a valid top-level object is never searched or guessed; it yields unavailable capacity, internal `bucket_unavailable`, and allowlisted `E-2401`. Neither source yields the same unavailable result under the installed response-shape validator. A non-object, empty, oversized, or otherwise unusable map cannot supply capacity. Evidence may retain only map presence, total observed key count capped to a bounded integer, at most eight sorted SHA-256 key prefixes of twelve lowercase hex characters, a truncation flag, and `selected_key: null`; raw key text and bucket values stay out of logs, protocol, and evidence.

Reset-credit detail rows require opaque `id`, `resetType`, `status`, and `grantedAt`; `expiresAt`, `title`, and `description` are nullable. The installed enums quote `resetType: "codexRateLimits"` or `"unknown"` and `status: "available"`, `"redeeming"`, `"redeemed"`, or `"unknown"` [VERIFIED: `/tmp/codex-schema-01470/v2/GetAccountRateLimitsResponse.json:55-101,134-139`]. Official docs distinguish `credits: null` (only count known) from `credits: []` (details fetched and no available rows), and state that `availableCount` remains authoritative if backend detail rows are capped [CITED: official README URL].

### First-read, sparse update, and observed backend behavior

- The official lifecycle is one `initialize` request, one `initialized` notification, then account requests; the app-server rejects requests made before initialization [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md]. The local probe returned an `initialize` result containing `userAgent`, `codexHome`, `platformFamily`, and `platformOs`; `codexHome` is host metadata and must be redacted from device payloads [VERIFIED: live local app-server response].
- A full `account/rateLimits/read` response requires top-level `rateLimits`, but its nested snapshot properties are optional/nullable. Treat missing and explicit null as unavailable. Do not initialize an empty cache to zeroes [VERIFIED: installed schema cited above; project requirement CODEX-03].
- The installed `AccountRateLimitsUpdatedNotification` description quotes: `Sparse rolling rate-limit update.` and `Clients should merge available values into the most recent account/rateLimits/read response or refetch that snapshot.` It also says nullable account metadata may be unavailable in a rolling update and does not clear a previously observed value [VERIFIED: `/tmp/codex-schema-01470/v2/AccountRateLimitsUpdatedNotification.json:191-201`].
- `rateLimitResetCredits` is present only on the full-read response schema, not the sparse notification schema [VERIFIED: compare `/tmp/codex-schema-01470/v2/GetAccountRateLimitsResponse.json:277-305` with `AccountRateLimitsUpdatedNotification.json:191-201`; CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md]. A sparse event cannot clear or invent reset-credit rows.
- The authenticated local process returned account data but no `account/rateLimits/read` response after 90 seconds. This is an observation about this host/run, not proof that the account lacks limits or that Codex always hangs. Preserve the failed/timeout result as `offline` or `unavailable` according to the host error classification, and retry/refetch under a bounded policy [VERIFIED: local probe transcript; no quota values claimed].
- An isolated empty Codex home returned `{"account":null,"requiresOpenaiAuth":true}` promptly from `account/read`; this is the observed unauthenticated account shape, not a substitute for a real auth-failure test against the user's active account [VERIFIED: isolated local app-server probe].

### Freshness and source-status policy

The project requirements mandate visible `current`, `stale`, `unavailable`, `authentication-failed`, and `host-offline` distinctions [VERIFIED: `.planning/REQUIREMENTS.md:32-35`]. Codex does not supply a product observation timestamp or these product statuses, so the bridge must add them. Use the following prescriptive state machine. Per D-05, poll for a complete limits snapshot every 300 seconds and mark a cached observation stale at 900 seconds without a valid full read or valid sparse merge. These values are product policy, not Codex facts.

| Host state | Entry condition | Allowed display | Recovery |
|---|---|---|---|
| `current` | A complete full read succeeded and bridge-owned observation age is within the chosen threshold. | Show supplied primary/secondary/reset/reached fields plus age. | Continue bounded polling and accept valid sparse merges. |
| `stale` | A previous complete observation exists, but age exceeds the threshold or a refresh is overdue. | Keep values only with an unmistakable stale marker and age; never call them current. | Full `account/rateLimits/read`; sparse event may refresh only after valid merge. |
| `unavailable` | No successful full observation exists, or all requested field(s) are missing/null. | Show `UNAVAILABLE` for each absent field; no fabricated zero/reset/reached value. | Retry full read when app-server is ready. |
| `authentication-failed` | `account/read` reports `account: null` with `requiresOpenaiAuth: true`, a login/auth JSON-RPC error is observed, or a backend response explicitly reports unauthorized. | Show `AUTH REQUIRED`/bounded equivalent; do not expose login URLs, tokens, or email. | Host-only account refresh/re-auth; then perform a new full read. |
| `host-offline` | Bridge cannot spawn/read app-server, the JSONL process exits, transport/read timeout occurs, or local host connectivity is unavailable. | Show `OFFLINE` separately from stale cached values; preserve observation age if a cached value remains. | Restart/reinitialize app-server and require a successful full read before current. |

The `authentication-failed` and `host-offline` categories above are bridge classifications, not Codex enum values. A timeout must not be relabeled as auth failure. The executable classifier admits `authentication-failed` only from `account: null` with `requiresOpenaiAuth: true` or a structured unauthorized response observed by the bounded collector. Process exit, malformed or oversized JSONL, correlation failure, request error without auth evidence, and timeout map to `host-offline`/the device copy `CODEX OFFLINE` with one allowlisted error code. Deterministic fixtures exercise each branch without guessing raw error strings. Open Codex issue reports provide risk evidence that an offline startup prefetch may remain empty after reconnect until restart (#26789) and that a first status read may show stale rate limits (#33897); these reports are not protocol guarantees and motivate the explicit retry/refetch path [CITED: https://github.com/openai/codex/issues/26789; https://github.com/openai/codex/issues/33897].

### Host-only credential boundary

- The active `/home/nnex/.codex/auth.json` is owned by the local user and has mode `0600`; safe metadata inspection showed keys `OPENAI_API_KEY`, `auth_mode`, `last_refresh`, and `tokens` without reading secret values [VERIFIED: local `stat` and key-only probe]. The observed `auth_mode` is `chatgpt` [VERIFIED: local key-only probe].
- Official docs say ChatGPT managed auth persists/refreshes tokens in Codex, while API-key auth is a separate mode [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md]. The bridge should launch/use the local app-server and never read, copy, log, normalize, or serialize token contents.
- Device payloads may include bounded normalized percentages, reset timestamps, plan label if product-approved, reached cue, source status, observation age, bridge epoch/revision suffix, and bounded troubleshooting IDs. They must not include `codexHome`, auth mode details beyond a bounded status, email, tokens, API keys, login URLs/codes, raw JSON-RPC error text, prompts, transcripts, or host filesystem paths [VERIFIED: `.planning/REQUIREMENTS.md:43-44,48-51`; host path observed in initialize response].
- Keep Codex and Herdr source health independent. A healthy USB link says only that the device transport works; it does not certify Codex authentication or quota freshness [VERIFIED: `.planning/REQUIREMENTS.md:39-44`; `.planning/research/ARCHITECTURE.md:176-179`].

## Architecture Patterns

### System Architecture Diagram

```text
Host bridge starts codex app-server --stdio
        |
        v
initialize -> initialized -> account/read
        |                         |
        |                         +--> auth/account classification (host only)
        v
account/rateLimits/read --------------+--> complete known snapshot + observed_at
        ^                              |
        | account/rateLimits/updated   v
        +---- sparse merge/refetch -> freshness/status classifier
                                       |
                   Herdr projection --+--> complete normalized four-tile snapshot
                                       |    (agent source + Codex source + link)
                                       v
                         Phase 1 bounded device protocol/session
                           |                     |
                           v                     v
                    panels 1-3 direct keys   panel 4 read-only Codex tile
                           |                     |
                           +--> encoder click -> secondary diagnostics/menu
                                             |
                                  bounded brightness write -> local settings
```

The diagram is a conceptual data flow, not an existing file layout. The host owns all upstream interpretation; firmware owns bounded rendering/input and must not become a generic app-server or Herdr proxy [VERIFIED: `.planning/research/ARCHITECTURE.md:1-14,75-91`; project constraints above].

### Recommended project structure

Extend the Phase 2 host bridge planned structure rather than creating a second daemon or parser:

```text
host/
├── bridge/                 # one supervised device/session owner
├── collectors/
│   └── codex/              # app-server lifecycle, full read, sparse merge, status
├── projection/             # complete four-tile snapshot + source freshness
├── diagnostics/            # bounded menu/version/identifier projection
└── settings/               # brightness-only local persistence
firmware/src/
├── protocol/               # extend Phase 1 typed schema/session, keep bounds
├── ui/                     # product tile/menu renderer separate from bring-up renderer
├── input/                  # direct agent keys plus encoder menu state
└── settings/               # brightness persistence adapter only
```

These are planning seams, not existing directories; the current repository contains Phase 1 firmware and bring-up tooling but no permanent host bridge/menu implementation [VERIFIED: repository directory inspection; Phase 2 context `.planning/phases/02-authoritative-agent-projection-and-exact-focus/02-CONTEXT.md:60-76`].

### Pattern 1: Full-read baseline plus sparse merge

**What:** Keep a `known_full_snapshot` containing only fields observed from a successful full read. On `account/rateLimits/updated`, merge only fields present in the notification; explicit nullable fields mean unavailable for that field, but an omitted field in a sparse event remains unchanged. If no baseline exists or the update shape is ambiguous, refetch the full snapshot.

**When to use:** Every app-server session, reconnect, auth change, timeout recovery, and sparse notification.

```json
{
  "method": "account/rateLimits/read",
  "id": 7
}
```

The method and request shape are present in the installed `ClientRequest` schema, where `account/rateLimits/read` has null params [VERIFIED: `/tmp/codex-schema-01470/ClientRequest.json:7133-7153`]. Do not copy a response from the current `main` branch as a timeless type; regenerate from the pinned binary on updates [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md].

### Pattern 2: Independent source clocks and atomic publication

**What:** Stamp `codex_observed_at` only after a complete read or valid sparse merge. Keep `herdr_observed_at` and `link_observed_at` separate. Build a complete normalized snapshot off to the side, then publish one host epoch/revision. Firmware stages the complete snapshot and swaps it atomically before enabling/using bindings.

**When to use:** Any source update, source failure, reconnect, or menu setting change.

**Why:** A Codex timeout must not erase current agent tiles, and a menu brightness write must not alter authoritative inbox order or focus identity [VERIFIED: `.planning/research/ARCHITECTURE.md:160-179,241-245`; `.planning/REQUIREMENTS.md:39-51`].

### Pattern 3: Read-only diagnostic/menu capability

**What:** Encoder click toggles a secondary menu state; encoder direction selects a bounded diagnostic row or brightness value only while menu mode is active. Keys 1–3 remain direct focus paths regardless of menu state. The menu is a display/settings surface, not a generic command dispatcher.

**When to use:** Device diagnostics and persistent brightness only.

**Implementation guidance:** Keep menu state local to firmware, but have host provide read-only values and acknowledge brightness changes through a typed, allowlisted protocol message. If the link is down, do not queue a brightness write or replay it after reconnect; show an offline result and require a fresh deliberate action [VERIFIED: `.planning/REQUIREMENTS.md:42,46-51`; queued/replayed presses are out of scope in `.planning/REQUIREMENTS.md:85-87`].

### Pattern 4: Versioned schema and redacted diagnostic payload

**What:** Generate and inspect stable app-server schema at implementation time, then normalize into a small project-owned payload. Include only bounded firmware/protocol versions, host epoch/revision suffixes, link status, Herdr/Codex statuses, observation ages, and safe error codes. Never forward raw upstream objects.

**When to use:** Every device snapshot/menu response.

## Existing Firmware Seams and Risks

### Verified reusable seams

- `BoardAdapter` is the only firmware hardware boundary and exposes `displayAt`, `key`, `wasPressed`, encoder movement/position, `setBrightness`, LEDs, and sequential `clearDisplays` [VERIFIED: `firmware/src/board/board_adapter.h:9-35`; `firmware/src/board/board_adapter.cpp:20-89`].
- The verified physical map contains four display mappings, five raw keys, 14 LEDs, brightness samples `{10, 50, 100}`, and encoder click raw key `4`; Phase 1's accepted evidence labels physical keys `KEY-1..KEY-4` as raw indices `0..3` and encoder click as raw `4` [VERIFIED: `firmware/src/board/physical_map.h:98-169`; `.planning/phases/01-physical-keypad-and-proven-transport/01-03-SUMMARY.md:104-110,131-136`].
- Current setup applies a hardcoded `board.setBrightness(80)` before drawing the initial `WAIT` state [VERIFIED: `firmware/src/main.cpp:404-415`]. Phase 3 must replace this with a settings-backed bounded value without changing physical mapping or snapshot binding.
- Current `reportInput()` reports encoder click only when `armedInput == EncoderClick` and a probe step is active [VERIFIED: `firmware/src/main.cpp:379-400`]. Product menu input needs a separate state path; reusing the bring-up arming logic would make menu click unavailable during normal runtime.
- `BringupRenderer` is a fixed temporary renderer with states `Wait`, `Map`, `Press`, `TurnCw`, `TurnCcw`, `Click`, `Brightness`, `Pair`, `Pass`, `Fail`, and `LinkLost`; it has no product Codex/menu states [VERIFIED: `firmware/src/ui/bringup_renderer.h:7-19`]. Keep permanent product rendering separate from the archived bring-up surface.
- Phase 1 protocol schema currently allows only `hello`, `hello_ack`, `probe`, `probe_ack`, `event`, `error`, `metrics`, and `metrics_ack`; the line bound is 4096 bytes including LF and unknown fields/types reject [VERIFIED: `protocol/schema/v1.json:1-27,79-82`]. Phase 3 must update the authoritative schema/fixtures and both host/native codecs before sending snapshots/menu messages.

### Menu and brightness risks

1. **Direct-key regression:** A global menu/modal flag could accidentally route keys 1–3 into navigation. Keep `reportAgentKey()` immediately after `board.update()` and before USB/menu polling; let `pollMenu()` consume encoder click logical key 4 and encoder delta only. Plan 06 production-loop tests exercise direct focus in every menu state and prove key presses do not alter cursor or deadline [VERIFIED: D-11, D-12; existing `firmware/src/main.cpp` order].
2. **Atomicity regression:** Sequential panel drawing can expose a new Codex panel beside old agent panels if the renderer mutates live state in place. Stage complete snapshots and make the same revision visible to all four panel render calls [VERIFIED: `.planning/research/ARCHITECTURE.md:241-245`; Phase 1 one-panel-at-a-time seam].
3. **Brightness persistence coupling:** Use the existing `SettingsStore` `Preferences` namespace and marker-last record replacement. Read schema version 1 without writing, supply brightness 80% in memory, and write the complete schema-version-2 theme/LED/brightness record only after explicit confirmation. This keeps writes out of boot and preview paths and prevents snapshot, binding, credential, or provider data from entering NVS [VERIFIED: `firmware/src/app/settings_store.{h,cpp}`; D-14].
4. **Offline write replay:** A brightness action sent during disconnect can be stale or duplicated after reconnect. Reject/uncertain states must not auto-replay; require a fresh encoder action [VERIFIED: `SYNC-04` and out-of-scope queued/replayed actions].
5. **Protocol budget:** A verbose menu diagnostic or raw Codex error can exceed the 4096-byte line bound or leak paths. Use bounded enums/codes, short version strings, age seconds, and suffix IDs; reject/clip before allocation [VERIFIED: Phase 1 schema bound].
6. **Null and missing collapse:** Deserializing absent/null into numeric zero would violate CODEX-03. Use presence-aware normalization and separate `has_*`/status fields before device encoding [VERIFIED: installed schemas and CODEX-03].
7. **Reset-vs-observation confusion:** `resetsAt` is provider quota timing, not freshness. Show reset information and bridge observation age separately using the approved fixed rows, bounded copy, and exact-device 10% long-text checkpoint [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md; VERIFIED: `03-UI-SPEC.md:101-144,300-315`].
8. **Plan/account mismatch:** API-key, Bedrock, personal-token, and ChatGPT modes do not all imply ChatGPT subscription windows. Gate the subscription tile on observed account mode and actual full limits response [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md; VERIFIED: installed account schemas].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Codex auth/token handling | Read auth.json tokens or implement OAuth/API login in the bridge/device | Local Codex app-server account boundary | Codex owns managed token persistence/refresh; copying secrets violates SAFE-01 [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md]. |
| Rate-limit schema | Hand-copy a response type from upstream `main` | Generate stable JSON Schema from the installed binary and pin its hash/version | App-server docs promise version-specific generated artifacts; installed schema has nullable/new fields [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md]. |
| Sparse updates | Replace full snapshot with each notification | Presence-aware merge into a known full snapshot or refetch | Omitted fields are not changes; official schema explicitly says sparse [VERIFIED: installed notification schema]. |
| Freshness | Use quota window duration as TTL or infer current from link health | Bridge-owned observed timestamp, explicit source status, 300-second full poll, and 900-second stale boundary | Provider reset semantics and observation freshness are different concepts [VERIFIED: project architecture; D-05]. |
| Provider calls | Call private ChatGPT backend or screen-scrape Codex TUI | Stable app-server stdio JSONL | Private routes/auth and UI text are brittle and leak the credential boundary [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md]. |
| Display driver | Raw GPIO/panel CS or a second display stack | Existing official Pro `BoardAdapter` and sequential panel API | STM32 multiplexing and panel sequencing are already isolated by Phase 1 [VERIFIED: `firmware/src/board/board_adapter.cpp:81-89`]. |
| Menu command routing | Generic `{method, params}` proxy | Typed allowlisted diagnostics/brightness messages | Generic proxy expands device authority and risks credentials/host actions [VERIFIED: `SAFE-01`, `SAFE-02`]. |

## Common Pitfalls

### Pitfall 1: Treating account/read as proof of available quota

**What goes wrong:** `account/read` succeeds with ChatGPT account metadata, but the quota request has not completed; the device displays zero or stale values as current.  
**Prevention:** Keep account/auth status and quota-observation status separate. The live probe returned account metadata but no rate-limit response after 90 seconds.  
**Warning signs:** `planType` appears while both windows are absent, or a host restart shows old percentages without a new full-read timestamp.

### Pitfall 2: Treating sparse updated as a complete replacement

**What goes wrong:** An omitted `secondary`, plan, credits, or reached-limit field clears a known value, or a notification is accepted before any full snapshot.  
**Prevention:** Require a known full baseline; merge present fields only; refetch when no baseline exists.  
**Warning signs:** fields flicker unavailable after every rolling event or reset credits persist after a new full response says they are null.

### Pitfall 3: Collapsing null/missing into zero/false

**What goes wrong:** Null `usedPercent` window, null credits balance, null reset, or null reached state renders as `0%`, “no limit,” or “not reached.”  
**Prevention:** Preserve field presence and nullability through normalization; use literal unavailable cues.  
**Warning signs:** a missing secondary bucket shows `0%`, or `spendControlReached: null` renders green.

### Pitfall 4: Confusing provider reset with data freshness

**What goes wrong:** A long quota window makes an old observation appear current, or a soon reset makes a fresh observation appear stale.  
**Prevention:** Add bridge-owned observation age and an independently frozen threshold; display reset countdown separately.  
**Warning signs:** UI has a reset timestamp but no “observed X ago.”

### Pitfall 5: Conflating offline with authentication failure

**What goes wrong:** A timeout/network failure is shown as “sign in,” or `account: null` is hidden as a generic offline state.  
**Prevention:** Classify only observed auth errors/account-null conditions as auth-failed; classify process/transport/timeouts as host-offline; preserve unknown/unavailable when evidence is insufficient.  
**Warning signs:** reconnecting the USB link changes a Codex auth badge without a new account probe.

### Pitfall 6: Letting menu mode steal direct agent keys

**What goes wrong:** Encoder menu state makes keys 1–3 navigate rows or changes focus target semantics.  
**Prevention:** Keep agent keys direct and independently dispatched; menu owns only encoder input and brightness/diagnostic rendering.  
**Warning signs:** pressing an agent key while menu is open changes a selected row rather than issuing typed focus.

### Pitfall 7: Persisting more than brightness

**What goes wrong:** Device settings storage retains provider data, host paths, snapshot identities, or stale bindings.  
**Prevention:** Persist only bounded brightness preference; clear/reinitialize all authoritative snapshot/binding state on session/epoch changes.  
**Warning signs:** a firmware reboot restores an old agent target before a complete host snapshot.

### Pitfall 8: Exceeding the protocol budget

**What goes wrong:** A verbose menu diagnostic or raw Codex error exceeds the 4096-byte line bound or leaks paths.  
**Prevention:** Use bounded enums/codes, short version strings, age seconds, and suffix IDs; reject/clip before allocation.  
**Warning signs:** schema fixtures pass individually but a complete snapshot plus diagnostics is rejected as `line_too_long`.

## Code Examples

### Initialize and full account/limits read (host-only pseudocode)

```json
{"method":"initialize","id":1,"params":{"clientInfo":{"name":"herdr_keypad_bridge","title":"Herdr Keypad Bridge","version":"0.1.0"}}}
{"method":"initialized"}
{"method":"account/read","id":2,"params":{"refreshToken":false}}
{"method":"account/rateLimits/read","id":3}
```

The first two messages and method names are documented by the official protocol; `refreshToken` is the installed `GetAccountParams` field [CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md; VERIFIED: `/tmp/codex-schema-01470/v2/GetAccountParams.json:3-10`]. Freeze client name as bounded `herdr_keypad_bridge`, title as `Herdr Keypad Bridge`, and derive the bounded version from the installed host package metadata. Protocol tests reject missing, unbounded, or free-form identity fields; no account or host identity is used.

### Normalized device-facing shape (project-owned, not Codex wire schema)

```json
{
  "codex": {
    "status": "current|stale|unavailable|authentication-failed|host-offline",
    "observed_age_seconds": 0,
    "plan": null,
    "primary_used_percent": null,
    "primary_resets_at": null,
    "secondary_used_percent": null,
    "secondary_resets_at": null,
    "reached": null
  },
  "diagnostics": {
    "link": "up|offline",
    "herdr": "current|stale|unavailable|offline",
    "codex": "current|stale|unavailable|authentication-failed|host-offline",
    "last_full_sync_age_seconds": 0,
    "last_codex_observation_age_seconds": 0,
    "firmware_version": "bounded",
    "protocol_version": 1,
    "troubleshooting_id_suffix": "bounded"
  }
}
```

This is a **planning shape**, not an observed Codex wire schema. Phase 3 extends the existing closed project protocol version 2 `agent_snapshot` payload. The protocol fixture task freezes exact enums, integer bounds, presence representation, and rejection parity before broad renderer work; it does not introduce another message family or parser [VERIFIED: `.planning/research/ARCHITECTURE.md:150-179`; D-17].

### Sparse merge rule

```text
if no_known_full_snapshot:
    request_full_rate_limits()
else:
    for each field present in update.rateLimits:
        merge_field(field)          # null remains unavailable for that field
    preserve_fields omitted by update
    update_observed_at()
```

The merge/refetch behavior is directly stated by the installed notification schema and official docs; the pseudo-code is implementation guidance, not a Codex API [VERIFIED: installed notification schema; CITED: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md].

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---:|---|---|
| `codex` executable | Host quota collector/schema generation | ✓ | `codex-cli 0.147.0` | None needed; pin/record binary and regenerate schema on update |
| Codex stable schema generator | Exact app-server contract | ✓ | Same binary | Block implementation if generator no longer emits stable schema |
| Active ChatGPT account | Real account/auth observation | ✓ | `chatgpt`, plan `prolite` observed | Do not fabricate quota; use unavailable state until full read succeeds |
| Authenticated `account/rateLimits/read` backend response | CODEX-01/02 real values | ✗ during this research window | No response after 90 seconds | Bounded timeout, explicit offline/unavailable state, retry/refetch; requires implementation/acceptance re-probe |
| Python runtime | Host bridge | ✓ | `3.14.7` (`>=3.11` project target) | Existing project target; exact 3.11 is not installed per Phase 1 summary |
| PlatformIO via project venv | Firmware build/smoke | ✓ | Core `6.1.19` | Use `tools/phase1_bringup/.venv/bin/pio`; bare `pio` is not on PATH |
| Node.js | Codex npm entrypoint/tooling | ✓ | `v26.7.0` | Existing installed runtime |
| Connected keypad | Device menu/brightness acceptance | Existing Phase 1 USB qualification artifact | Exact hardware baseline recorded in Phase 1 artifacts | Use selected USB lock and real-device acceptance; no mock can close MENU-04 |

**Missing dependencies with no fallback:** None. The bounded production tracer must record either a schema-valid real full-read success or the exact typed, evidence-backed failure observed from the installed account. Backend success is not required to invent or claim live quota values. The connected-device menu and optical checks remain acceptance prerequisites.

## Security Domain

Security enforcement is enabled in `.planning/config.json` (`security_enforcement: true`, ASVS level 1) [VERIFIED: `.planning/config.json:123-125`].

### Applicable ASVS categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | Yes | Use Codex app-server account/read/auth state on the host; never move login/token material to firmware. |
| V3 Session Management | Yes | Fresh app-server/device session IDs, bounded request timeouts, no replay after disconnect, and full-read baseline after reconnect. |
| V4 Access Control | Yes | Device protocol accepts only typed normalized snapshots, diagnostics, brightness, and the existing focus action; never generic host/provider methods. |
| V5 Input Validation | Yes | Validate generated-schema fields, presence/nullability, bounded strings/integers, protocol version, line length, and source status before device encoding. |
| V6 Cryptography | Limited | No new cryptography is needed for local USB provider data; preserve Phase 1 device pairing/transport boundary and do not invent token wrapping. |

### Known threat patterns

| Pattern | STRIDE | Standard mitigation |
|---|---|---|
| Token/API-key leakage over device stream or logs | Information disclosure | Host-only app-server; redacted normalized payload; never log auth JSON. |
| Generic app-server/Herdr method proxy | Elevation of privilege | Typed allowlist; only read quota and diagnostics plus explicitly permitted focus/brightness messages. |
| Stale quota presented as current | Spoofing/information disclosure | Bridge-owned observed age and source status; explicit stale/offline/auth states. |
| Null/missing numeric fields rendered as zero | Tampering/information disclosure | Presence-aware schema normalization and unavailable cues. |
| Replayed brightness/focus after reconnect | Tampering | Discard uncertain in-flight actions and require a fresh user action after full resync. |
| Host path/email/raw error exposure in menu | Information disclosure | Bounded IDs/status codes only; redact `codexHome`, email, URLs, and raw error strings. |

## Assumptions Log

| # | Resolved disposition | Section | Verification consequence |
|---|---|---|---|
| A1 | Poll at 300 seconds and mark stale at 900 seconds per D-05. The bridge clock remains independent of provider reset time. | Freshness policy | Fake-clock tests cover both boundaries and recovery after a later valid observation. |
| A2 | Admit auth failure only from structured account-null/auth evidence. Map every other bounded process, transport, JSONL, correlation, or deadline failure to Codex offline with an allowlisted code. | Freshness policy | Scripted fixtures and the installed tracer record the selected branch without committing raw errors. |
| A3 | Extend only the closed protocol version 2 `agent_snapshot`; reject any normalized snapshot that exceeds the existing 4096-byte including-LF bound. | Code examples/protocol | Host/native golden vectors cover near-limit acceptance and over-limit rejection before renderer expansion. |
| A4 | Store brightness in the existing `Preferences`-backed `SettingsStore` schema version 2. Read version 1 without a boot write; use 80% only in memory; write marker last only on confirmation. | Existing firmware seams | Native persistence tests cover legacy read, invalid/missing fallback, interrupted replacement, and reboot reload. |
| A5 | Do not assume the active account will return quota values. The tracer accepts a schema-valid full response or a typed evidence-backed failure and never fills absent live fields from fixtures. | Environment availability | Live evidence identifies outcome kind; deterministic fixtures prove supplied-value rendering separately. |
| A6 | Use the approved fixed theme/menu geometry and bounded copy in `03-UI-SPEC.md`. The exact paired device at 10% brightness is the blocking optical backstop. | Firmware menu | Framebuffer contacts prove pixels; human observations separately prove long-text legibility, clipping, and bezel clearance. |

## Resolved questions and executable dispositions

1. **Authenticated full-read timeout.** The first production tracer starts the installed `codex app-server --stdio`, completes the correlated initialize/initialized/account handshake, and requests `account/rateLimits/read` under a hard deadline. It records either a schema-valid normalized success or a typed failure code with elapsed time, child-exit state, and redaction result. Raw stderr and JSON-RPC content stay ephemeral and never enter the device or committed evidence. Either outcome passes the integration contract; only a real success may populate live percentages, resets, or reached state.
2. **Single bucket versus `rateLimitsByLimitId`.** The tracer and deterministic matrix cover top-level-only, map-only, both, neither, explicit-null map, and unusable map. Only a valid top-level `rateLimits` object may supply capacity. The collector selects no undocumented map key. Map-only, neither-source, or unusable-map input produces unavailable capacity with internal `bucket_unavailable` and allowlisted diagnostic code `E-2401`. Evidence retains only map presence, capped key count, at most eight sorted twelve-hex SHA-256 key prefixes, truncation, and `selected_key: null`; raw keys and bucket values are forbidden.
3. **Active-account fields and values.** Real primary/secondary windows, duration, reset, credits, spend-control, plan, reached-limit, and reset-credit outcomes remain unknown until the bounded tracer. The normalizer preserves each supplied field, null, and omission independently. Deterministic fixtures prove every rendering branch but are labeled fixture data and cannot satisfy the live-account evidence row.
4. **Auth and transport error taxonomy.** The collector maps `account: null` with `requiresOpenaiAuth: true` and structured unauthorized responses to `AUTH REQUIRED`. Process exit, line overflow, malformed JSONL, ID mismatch, request error without auth evidence, and deadline expiry map to `CODEX OFFLINE` plus an allowlisted `E-####` code. Tests use structured scripted responses, not guessed error text; the tracer records which evidence-backed branch the installed process produced.
5. **Freshness threshold.** Per D-05, request a full snapshot every 300 seconds and mark data stale at 900 seconds without a valid full read or valid sparse merge. Fake-clock tests prove the exact edges. Provider reset timestamps never influence this clock.
6. **Sparse notification before full read.** Before a known full baseline, reject the notification as a publishable observation, leave values and observation age unchanged, and schedule one coalesced immediate full refetch. After a baseline, merge present fields with installed-schema null semantics, preserve omitted fields, update observation age, and schedule the same nonblocking refetch per D-06 and D-18.
7. **Phase 2 protocol extension.** Extend only the existing protocol version 2 `agent_snapshot`, `PermanentBridge`, host validator/codec, firmware `FrameCodec`/`ProtocolSession`, staged `AgentProjection::Generation`, shared `RenderState`, and current renderer family. Golden host/native vectors freeze the closed additions. No parallel framing, snapshot message, parser, projection, or focus path is permitted.
8. **Brightness storage and wear policy.** Extend the existing `Preferences`-backed `SettingsStore`. Load schema version 1 theme/LED unchanged with brightness 80% in memory and zero writes. Preview through `BoardAdapter::setBrightness()`. Write the complete schema version 2 record with the marker last only after explicit confirmation; no boot, rotation, close, timeout, or host update writes NVS.
9. **Physically legible menu layout.** Implement the approved six-row root, three-row viewport, fixed HEALTH/ABOUT rows, title metrics, bounds, and tail ellipsis from `03-UI-SPEC.md`. Generate exact 128x128 contact sheets for all themes and long-text states, then block phase completion on exact-paired-device observations at 10% brightness for legibility, clipping, bezel clearance, direct keys, timeout, brightness, LED, and reboot behavior. Framebuffer captures cannot close optical or interaction rows.

## Sources

### Primary (HIGH confidence)

- Installed `codex-cli 0.147.0`: `codex --version`, `codex app-server --help`, and `codex app-server generate-json-schema --out /tmp/codex-schema-01470` [VERIFIED: local commands].
- Installed generated schemas: `/tmp/codex-schema-01470/v2/GetAccountResponse.json`, `GetAccountRateLimitsResponse.json`, `AccountRateLimitsUpdatedNotification.json`, `AccountUpdatedNotification.json`, `LoginAccountParams.json`, and `ClientRequest.json` [VERIFIED: files read this session].
- Live local app-server account probes: authenticated `account/read` returned ChatGPT/prolite/`requiresOpenaiAuth: true`; isolated empty-home `account/read` returned `account: null`/`requiresOpenaiAuth: true`; authenticated rate-limit call did not answer in a 90-second observation [VERIFIED: supervised stdio probes].
- OpenAI Codex app-server README: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md [CITED: initialization, auth modes, full rate read, sparse update, reset-credit semantics].
- OpenAI Codex v2 account source: https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/account.rs [CITED: Rust source structs/enums; installed generated schema remains the version-specific authority].
- Repository requirements/roadmap/project and Phase 1/2 artifacts [VERIFIED: `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/PROJECT.md`, `.planning/phases/01-physical-keypad-and-proven-transport/01-RESEARCH.md`, `.planning/phases/02-authoritative-agent-projection-and-exact-focus/02-RESEARCH.md`].
- Existing firmware protocol/board/UI source [VERIFIED: `protocol/schema/v1.json`, `firmware/src/main.cpp`, `firmware/src/board/board_adapter.{h,cpp}`, `firmware/src/board/physical_map.h`, `firmware/src/ui/bringup_renderer.h`].

### Secondary (MEDIUM confidence)

- Open Codex issue #26789, offline startup limits remaining hidden until restart: https://github.com/openai/codex/issues/26789 [CITED: observed user report; risk evidence only].
- Open Codex issue #33897, stale first `/status` rate-limit data: https://github.com/openai/codex/issues/33897 [CITED: observed user report against 0.144.5; risk evidence only].
- Existing project architecture/pitfall research [VERIFIED: `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md`, `.planning/research/STACK.md`].

### Tertiary (LOW confidence)

- None used for a required implementation claim. Training knowledge was not used to assert account values or Codex behavior.

## Metadata

**Confidence breakdown:**
- Installed schema and authentication mode: HIGH — generated from the exact local binary and confirmed by a live account/read response.
- Real quota bucket values: LOW/MEDIUM — no authenticated rate-limit response arrived during the bounded probe; schema facts are HIGH but account data is unobserved.
- Sparse-update semantics: HIGH — exact installed schema description and official docs agree.
- Freshness/error policy: MEDIUM — requirements and risk reports establish the need for independent states, but threshold/error taxonomy must be measured and frozen during implementation.
- Menu/brightness seams: MEDIUM — existing BoardAdapter/physical evidence are verified, while permanent product menu and persistence are absent.

**Research date:** 2026-08-17  
**Valid until:** 2026-09-01 for installed Codex behavior and schema; regenerate and re-probe after any Codex upgrade, auth-mode change, or backend protocol change. Hardware/menu findings remain valid only for the accepted device/build.