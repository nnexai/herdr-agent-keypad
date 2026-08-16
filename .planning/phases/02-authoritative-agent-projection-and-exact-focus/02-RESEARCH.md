# Phase 2: Authoritative Agent Projection and Exact Focus - Research

**Researched:** 2026-08-17  
**Domain:** Installed Herdr 0.8.0 socket API, `herdr-agent-inbox` projection, identity-bound focus, and Phase 1 device seam  
**Confidence:** MEDIUM (active schema and local plugin source are high-confidence for this installation; native focus side effects across every lifecycle state still require a controlled multi-pane fixture)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Each occupied tile shows the agent title plus a compact workspace/repository discriminator so similarly named agents remain distinguishable.
- **D-02:** Tile order is the installed `herdr-agent-inbox` order. The bridge must not invent a second priority model or reorder entries in firmware.
- **D-03:** Keep three physical tile positions stable. When fewer than three entries exist, render explicit empty tiles rather than collapsing or shifting occupied positions.
- **D-04:** Use Herdr-consistent color plus a compact glyph for blocked, finished/unseen, working, idle, settled, and unknown states.
- **D-05:** A stale, offline, vanished, incompatible, or reassigned entry freezes its last known identity with a visible stale/offline veil. Its key must reject focus until a fresh authoritative snapshot rebinds it.
- **D-06:** A key press sends focus-pane only for the exact opaque identity represented by that tile. No settle, dismiss, reply, approval, acknowledge, or arbitrary host action is permitted.
- **D-07:** Focus feedback is pending first, then success only after Herdr acknowledges the exact opaque identity, host epoch, and snapshot revision. Rejection, timeout, stale binding, or vanished pane must remain visibly distinct from success.

### the agent's Discretion
- Exact typography, glyph shapes, color values, tile layout, compact workspace truncation, pending timeout, and animation timing are implementation choices constrained by the existing 128×128 tile contract and UI-SPEC.

### Deferred Ideas (OUT OF SCOPE)
- Codex subscription/usage tile and device menu belong to Phase 3.
- Host reboot, suspend/resume, and full cross-component recovery belong to Phase 4.
- Wi-Fi transport is not part of the product path.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INBX-01 | Project zero to three entries in exactly installed inbox order | Installed daemon/TUI use `tokens.rank` ascending then `state_change_seq` descending; missing rank must fail closed. |
| INBX-02 | Show title and workspace/repository discriminator | Active `AgentInfo` supplies nullable title/cwd/workspace_id and string tokens; `workspace.list` supplies labels. |
| INBX-03 | Distinguish blocked, finished/unseen, working, idle, settled, unknown | Installed rank constants, status icon map, and documented Herdr status enum/color language provide the source mapping. |
| INBX-04 | Explicit empty tiles | Phase 1 fixed four-panel contract requires bounded, literal state labels and clearing old content before updates. |
| FOCS-01 | Focus exact opaque target with epoch and revision | Herdr `agent.focus` accepts only `{target:string}`; `pane_id` is the public target, while `terminal_id`/agent session and bridge-owned epoch/revision must be validated host-side. |
| FOCS-02 | Reject empty/stale/vanished/incompatible/offline bindings | `agent.focus` rejects missing targets with `agent_not_found`; lifecycle events and full snapshots expose replacement/closure. |
| FOCS-03 | Success only after Herdr acknowledgement | Active live response is `type: "agent_info"` containing the focused `AgentInfo`; no device success before matching identity/epoch/revision is checked. |
| FOCS-04 | Focus-only; native seen/unread effects allowed, no triage/arbitrary actions | Public docs state focus marks seen; plugin control paths for settle/unread/clear are separate and must never be called by the bridge. |
| SYNC-02 | Atomic snapshot replacement and binding pairing | Phase 1 `ProtocolSession` is the sole typed device boundary; use complete staged snapshots and one commit point. |
| SAFE-02 | Device can request only typed focus | The host must expose one allowlisted focus dispatch and never proxy arbitrary Herdr methods or the inbox control socket. |
</phase_requirements>

## Summary

The authoritative projection seam is the installed `herdr-agent-inbox` metadata already returned by Herdr `agent.list`: its daemon reports `rank`, `title`, `age`, `since`, and `flag` tokens, and its TUI sorts rows by rank ascending followed by `state_change_seq` descending [VERIFIED: `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/daemon.py:6-20,47-71`; `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/inbox_tui.py:153-187`]. Pin this seam to installed revision `de409f683262` for v1. The bridge should read `agent.list`, require a usable rank token on every candidate, sort exactly with that two-key rule, take the first three rows, and treat absent/malformed rank as inbox-unavailable rather than reconstructing priority from raw status. `agent.view.set` is not the projection source: official docs say it changes the built-in view but does not change `agent.list` [CITED: https://herdr.dev/docs/socket-api/].

The active binary is Herdr 0.8.0 with generated schema protocol 19/schema version 1 [VERIFIED: `herdr --version`; `/tmp/herdr-api-schema.json:1-5`]. `session.snapshot` is a bootstrap response with required `version`, `protocol`, `workspaces`, `tabs`, `panes`, `layouts`, and `agents`; focused IDs are nullable and there is no server-provided `host_epoch` or top-level snapshot revision [VERIFIED: `/tmp/herdr-entities.json:2-70`]. Each `AgentInfo`/`PaneInfo` has a required opaque `pane_id`, required `terminal_id`, required workspace/tab IDs, required semantic `agent_status`, required boolean `focused`, and required per-record uint64 `revision`; `state_change_seq` is optional with default 0 [VERIFIED: `/tmp/herdr-entities.json:72-196,198-317`]. Therefore the host bridge must generate a random host epoch at bridge/device-session start, monotonically assign its own snapshot revision, and bind pixels, pane target, terminal/lifecycle fingerprint, epoch, and revision in one immutable generation. Do not claim that Herdr itself acknowledges the bridge epoch/revision: the Herdr response acknowledges its own target record; the bridge must echo and verify its own binding metadata before reporting device success.

`agent.focus` is a narrow public request `{target: string}` [VERIFIED: `/tmp/herdr-api-schema.json:4993-5007`]. The active live response for `herdr agent focus w14:p1` was `type: "agent_info"` with a focused `AgentInfo`, including `pane_id`, `terminal_id`, `agent_status`, `focused`, and `revision` [VERIFIED: `/tmp/herdr-focus-result.json`; active response union `/tmp/herdr-api-schema.json:8834-8848`]. A missing target returns a distinct error, observed as `{"code":"agent_not_found","message":"agent target w999:p999 not found"}` [VERIFIED: `/tmp/herdr-focus-invalid.out`]. Public CLI docs state that focusing a target marks its tab seen, while reading does not [CITED: https://herdr.dev/docs/cli-reference/]. This is not a mutation-free operation for a finished/unseen entry. The installed plugin additionally owns persisted manual `settled`/`unread` flags keyed by `terminal_id`; its `_on_focus` can clear a manual unread flag after the focus event arrives later than the 1.5-second guard [VERIFIED: `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/daemon.py:41-55,693-712,1308-1315`]. The product contract therefore means focus-only at the command allowlist, while accepting documented native seen and observed plugin unread effects; it must not promise state neutrality.

**Primary recommendation:** Implement the bridge as a read-only installed-projection adapter plus one fail-closed `agent.focus` executor. Use complete `session.snapshot` bootstrap/resynchronization, lifecycle event invalidation, `agent.list` metadata ordering, a bridge-owned epoch/revision, terminal/session identity revalidation, and a device protocol action that carries only the currently displayed binding.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Authoritative inbox ordering and lifecycle | API / Backend (Herdr + installed plugin) | Host bridge | The installed plugin owns rank, title, settle/unread state, and Herdr owns semantic status; the device must not recompute either. |
| Snapshot normalization and freshness | Host bridge | Device protocol session | The bridge can read Herdr and plugin metadata, assign epoch/revision, and reject unavailable data; the firmware only consumes bounded normalized data. |
| Tile identity/state rendering and stable three positions | Browser / Client equivalent (firmware device) | Host bridge | The device owns pixels and physical slots; host supplies normalized fields and fixed bindings. |
| Exact focus authorization | Host bridge | Herdr API | The bridge revalidates the displayed binding and calls only `agent.focus`; Herdr performs the actual focus and native seen transition. |
| Atomic display/binding commit | Device protocol/firmware | Host bridge | Phase 1's `ProtocolSession` is the sole admission boundary; firmware stages a complete generation and commits pixels/bindings together. |

## Standard Stack

### Core

| Component | Version / revision | Purpose | Why Standard |
|---|---|---|---|
| Herdr public socket API | Installed 0.8.0; generated protocol 19/schema 1 | `session.snapshot`, `agent.list`, `events.subscribe`, `agent.focus` | The active binary publishes the exact schema; public docs define NDJSON local-socket integration [VERIFIED: `/tmp/herdr-api-schema.json:1-5`; CITED: https://herdr.dev/docs/socket-api/]. |
| `herdr-agent-inbox` | Installed revision `de409f683262` | Authoritative rank/title/flag metadata and order | Its own daemon and TUI provide the only verified rank projection for this installation [VERIFIED: local daemon.py:41-71; local inbox_tui.py:153-187]. |
| Python standard library | Host Python 3.14.7 observed; plugin recommends Python 3.11+ | Unix socket NDJSON, bounded normalization, bridge supervision | The installed plugin itself is stdlib Python and documents Python 3.11+ [VERIFIED: local README.md:69-75; environment probe]. |
| Phase 1 `ProtocolCodec`/`ProtocolSession` | Current repository seam | Device admission, typed dispatch, framing and session correlation | Phase 2 context explicitly requires consuming this sole boundary rather than adding another parser [VERIFIED: `.planning/phases/02-authoritative-agent-projection-and-exact-focus/02-CONTEXT.md:53-66`]. |

### Supporting

| Component | Version / revision | Purpose | When to Use |
|---|---|---|---|
| `session.snapshot` | Active schema response `session_snapshot` | Initial and reconnect bootstrap | Call after connecting and after any event-stream reconnect or suspected missed lifecycle event; it is not a subscription [CITED: https://herdr.dev/docs/socket-api/]. |
| `events.subscribe` | Active schema `EventsSubscribeParams` | Lifecycle invalidation and refresh trigger | Subscribe to `pane.created`, `pane.updated`, `pane.closed`, `pane.focused`, `pane.moved`, `pane.exited`, `pane.agent_detected`, `pane.agent_status_changed`, workspace close, and relevant workspace/tab lifecycle events. The pushed envelope is `{event,data}` [VERIFIED: `/tmp/herdr-entities.json:319-331,333-978`; `/tmp/herdr-api-schema.json:6033-6048`]. |
| `workspace.list` | Active Herdr method | Workspace/repository discriminator | Resolve `workspace_id` to the human label; combine with a bounded cwd/repository basename because `AgentInfo.cwd` is nullable [VERIFIED: local daemon.py:960-965; `/tmp/herdr-entities.json:93-113`]. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| `agent.list` + plugin rank tokens | `agent.view.set` result/order | Rejected: official docs state a view projection does not reorder `agent.list`; it controls Herdr's own sidebar only [CITED: https://herdr.dev/docs/socket-api/]. |
| Public `agent.focus` | Inbox control socket or `pane.focus` | Rejected for device action: plugin control socket mutates settle/unread/clear, and `pane.focus` does not remove native seen semantics. Use the documented `agent.focus` allowlist only. |
| `pane_id` plus host-side lifecycle validation | Numeric slot or title/cwd lookup | Rejected: slots and labels are presentation, pane IDs are the public target, and title/cwd can collide or survive replacement. |

## Architecture Patterns

### System Architecture Diagram

```text
Herdr Unix socket
  ├─ session.snapshot ───────────────┐
  ├─ agent.list ─────────────────────┤
  ├─ workspace.list ────────────────►│ Read-only bridge cache
  └─ events.subscribe ── lifecycle ──┘     │
                                           ▼
                           require plugin rank + exact sort
                           rank asc, state_change_seq desc
                                           │
                           normalize 0..3 entries + identity
                           (pane_id, terminal_id, session, epoch, rev)
                                           │ complete snapshot
                                           ▼
                              Phase 1 device ProtocolSession
                                           │ stage then atomic commit
                              ┌────────────┴────────────┐
                              ▼                         ▼
                      three fixed tiles              key bindings
                              │                         │
                         physical press ────────────────┘
                                           │ typed focus intent only
                                           ▼
                         host revalidate epoch/revision/identity
                                           │
                              agent.focus {target:pane_id}
                                           │
                         agent_info ack or typed Herdr error
                                           ▼
                         pending → success/reject/uncertain
```

### Recommended Project Structure

Use the existing Phase 1 boundaries rather than a second parser or transport:

```text
host/permanent bridge (planned by executor)
├── herdr adapter: snapshot + events + agent.list/workspace.list
├── inbox projection: rank/title/flag validation and exact two-key order
├── identity cache: pane_id + terminal_id + session/lifecycle fingerprint
├── focus executor: one allowlisted agent.focus path
└── snapshot assembler: host epoch, monotonic revision, bounded device fields
firmware/src/protocol/protocol.{h,cpp}
firmware/src/main.cpp
firmware/src/board/{physical_map,board_adapter}.{h,cpp}
```

### Pattern 1: Bootstrap then event-driven invalidation

**What:** Call `session.snapshot` for a complete cache, subscribe to lifecycle events, and treat events as refresh/invalidation triggers rather than a replacement event log. The public docs explicitly say a snapshot is one-time and clients should snapshot again after reconnect or stale cache [CITED: https://herdr.dev/docs/socket-api/].

**When to use:** Every bridge/device connection and every event socket reconnect.

**Implementation contract:** On bootstrap/reconnect increment bridge host epoch, clear pending focus and stale bindings, request a fresh complete snapshot, and do not enable keys until a complete three-tile device generation is committed. On `pane.closed`, `pane.exited`, `pane.agent_detected` with `released`, `pane.moved`, or agent/status updates, invalidate affected bindings and refresh `agent.list`; a closed event with only `pane_id` is not enough to manufacture a replacement identity [VERIFIED: `/tmp/herdr-entities.json:698-731,770-827,875-912`].

### Pattern 2: Exact ordered projection

**What:** Consume `agent.list` rows and sort exactly as the installed inbox TUI does: `rank` ascending, then `state_change_seq` descending [VERIFIED: local inbox_tui.py:165-187]. `rank` is a string token produced by the installed daemon; its values are literal `"0"` through `"5"` [VERIFIED: local daemon.py:47-52].

**When to use:** Every refresh and before publishing a new device snapshot.

**Implementation contract:** Require the plugin's rank token and bounded title/discriminator inputs. Do not sort by raw `agent_status`, `focused`, workspace order, title, or pane ID. Preserve fixed tile positions 1–3; clear unused positions to explicit `EMPTY`. A missing rank, missing required opaque identity, malformed token, or source incompatibility produces unavailable/incompatible state and disables focus rather than a local fallback priority.

### Pattern 3: Identity-bound staged snapshot and focus

**What:** A device key binds to the immutable generation shown by its pixels. The device sends slot, opaque pane target, host epoch, and snapshot revision; the host verifies that the displayed entry is still the same live record, then sends only `agent.focus` with the revalidated pane target.

**When to use:** Every focus press, including a press during churn.

**Implementation contract:** Verify device session, host epoch, snapshot revision, slot occupied/current, source freshness, pane ID, terminal ID, optional agent-session fingerprint, and current `agent.list`/snapshot record before dispatch. The Herdr request itself can carry only `{target:pane_id}`; epoch/revision are bridge/device correlation fields, not Herdr parameters [VERIFIED: `/tmp/herdr-api-schema.json:4993-5007`]. On Herdr success require `result.type == "agent_info"`, `result.agent.pane_id == bound pane_id`, `result.agent.terminal_id == bound terminal_id`, and a focused result; otherwise return reject/uncertain. Never substitute the current occupant of a slot after a mismatch.

### Pattern 4: Focus-only allowlist

**What:** The host bridge exposes one typed focus operation. It never exposes generic method names, shell commands, plugin action names, or the inbox control socket to firmware.

**When to use:** All device-originated actions.

**Implementation contract:** Device input can produce only `focus` with a currently displayed binding. The bridge may read `agent.list`, `session.snapshot`, `workspace.list`, and events, and may call `agent.focus`; it must not call `settle`, `unread`, `clear`, `agent.prompt`, `agent.send_keys`, approvals, replies, or arbitrary pane methods. The installed TUI's focus path itself calls `agent.focus` with `{"target": row["pane_id"]}` and separately uses its control socket for triage [VERIFIED: local inbox_tui.py:766-775,821-849].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Inbox ordering/lifecycle priority | A second blocked/unread/settled priority model | Installed `tokens.rank` plus `state_change_seq` ordering | Plugin persistence and Herdr semantic status interact; local reimplementation will drift [VERIFIED: local daemon.py:737-754,952-1039]. |
| Agent targeting | Numeric slot, title, cwd, or terminal title lookup | Opaque `pane_id` target plus host validation of terminal/session identity | Public focus accepts a pane target; titles/cwds are nullable/colliding and pane occupants can change [CITED: https://herdr.dev/docs/cli-reference/; VERIFIED: `/tmp/herdr-entities.json:72-196`]. |
| Resynchronization | Missed-event replay log | `session.snapshot` bootstrap after connect/reconnect | Public docs define snapshot as bootstrap and event subscription as the live update path [CITED: https://herdr.dev/docs/socket-api/]. |
| Focus authorization | Generic Herdr/socket proxy | One typed host-side focus executor | SAFE-02 requires a narrow capability boundary; arbitrary proxying expands the device attack surface. |
| State colors/glyphs | New priority/color language | Installed TUI status mapping | Herdr/inbox uses blocked red/`!`, finished-unseen teal/blue/`●`, working yellow/`▸`, idle green/`○`, settled dim/`⚑`, unknown `?` [VERIFIED: local inbox_tui.py:385-398,566-577,724-735]. |

**Key insight:** The plugin's `rank` token is the supported projection seam for this installed revision, but it is not a public cross-plugin schema promise. Pin the installation and fail visibly when its metadata contract is absent; never silently degrade to a competing inbox.

## Runtime State Inventory

This phase is an integration/refinement phase with lifecycle migration risk; the runtime inventory is explicit:

| Category | Items Found | Action Required |
|---|---|---|
| Stored data | `herdr-agent-inbox` stores `state.json` keyed by `terminal_id` and `history.jsonl` under `agent-inbox-state` [VERIFIED: local daemon.py:16-20,81-90; README.md:195-210]. | No data migration. Bridge must not read or write these private files; use public `agent.list` metadata only. |
| Live service config | Herdr server socket and active plugin metadata are live; installed plugin asserts its transient `agent.view.set` projection [VERIFIED: local daemon.py:756-764,1356-1384]. | Read only. Do not replace the inbox view or call plugin triage actions from the device bridge. |
| OS-registered state | No Phase 2-specific service/task registration was found in the repository or requested scope. | None — verify actual bridge startup registration during implementation; do not add a second daemon registration in this phase. |
| Secrets/env vars | Herdr authentication and plugin/private prompt-derived state remain host-side. Current socket paths are selected by `HERDR_SOCKET_PATH` or default `~/.config/herdr/herdr.sock` [VERIFIED: local daemon.py:74-79; CITED: https://herdr.dev/docs/socket-api/]. | Never serialize credentials, raw prompts, transcripts, host paths, or control-socket commands to firmware. |
| Build artifacts / installed packages | Installed Herdr 0.8.0 binary and plugin checkout `de409f683262` are active; no Phase 2 build artifact exists yet. | Pin/record binary schema and plugin revision in bridge evidence; refresh compatibility on updates. |

## Common Pitfalls

### Pitfall 1: Treating `agent.focus` as state-neutral

**What goes wrong:** Herdr marks a focused target seen; a `done` (finished/unseen) row can become `idle`, leave rank 1, and reorder. The plugin's manual unread flag can also be cleared by `_on_focus` depending on event timing [CITED: https://herdr.dev/docs/cli-reference/; VERIFIED: local daemon.py:1308-1315].

**How to avoid:** Record before/after `agent_status`, rank, flag, `state_change_seq`, `pane_id`, `terminal_id`, and plugin state for each focus test. Describe the operation as focus-only command capability, not zero state mutation. Do not write a compensating `unread`/`settle` command after focus.

**Warning signs:** A finished-unseen tile changes to idle, a manual `●` disappears, or ordering changes after an otherwise successful focus.

### Pitfall 2: Trusting `agent.list` array order or `agent.view.set`

**What goes wrong:** `agent.view.set` owns Herdr's sidebar projection and does not change `agent.list`; array order is not the installed inbox order [CITED: https://herdr.dev/docs/socket-api/].

**How to avoid:** Read rank tokens and sort exactly `(rank asc, state_change_seq desc)`. Treat missing rank as unavailable/incompatible.

### Pitfall 3: Using a pane slot as an identity across lifecycle changes

**What goes wrong:** A pane can move, close, exit, or receive a replacement agent while the physical tile still shows the old title. A later `agent.focus` by stale pane ID can focus the new occupant.

**How to avoid:** Bind pane ID together with terminal ID, optional native `agent_session`, Herdr per-record revision, bridge epoch, and bridge snapshot revision. On any lifecycle/reassignment signal, freeze stale pixels and reject until a complete snapshot rebinds the tile. Herdr's lifecycle schema exposes `pane_closed` by pane ID, `pane_moved` with previous IDs and a replacement `PaneInfo`, and `pane_agent_detected` with `released`/`final_status` [VERIFIED: `/tmp/herdr-entities.json:698-827,875-912`].

### Pitfall 4: Assuming null optional fields are empty strings or stable identifiers

**What goes wrong:** `AgentInfo.agent`, `agent_session`, `cwd`, `display_agent`, `foreground_cwd`, `name`, `terminal_title`, and `title` are nullable/optional; tokens can be omitted. `session.snapshot` focused IDs are nullable [VERIFIED: `/tmp/herdr-entities.json:2-70,72-196`].

**How to avoid:** Preserve null as unavailable, never stringify null as a user label, and use required `pane_id`/`terminal_id` plus fresh revision for identity. Show `UNKNOWN`/`UNAVAILABLE` instead of guessing.

### Pitfall 5: Calling plugin-private state/control surfaces

**What goes wrong:** Reading `state.json` or sending to `agent-inbox-state/control.sock` couples the bridge to private persistence and enables settle/unread/clear mutations. The plugin README describes these as implementation details, while the public Herdr socket is the supported integration surface [VERIFIED: local README.md:195-210; CITED: https://herdr.dev/docs/socket-api/].

**How to avoid:** Consume only Herdr public socket records/events and plugin metadata tokens. Keep the device bridge's allowlist limited to typed focus.

### Pitfall 6: Declaring focus success from transport acknowledgement alone

**What goes wrong:** A request can be delivered while the target was replaced or focus result is stale. Herdr's success result contains a current `AgentInfo`; it is the evidence to compare, not a generic boolean [VERIFIED: live `/tmp/herdr-focus-result.json`; `/tmp/herdr-api-schema.json:8834-8848`].

**How to avoid:** Device shows pending first; host success requires matching pane/terminal/session identity and focused result, then sends result tied to the same device epoch/revision. Herdr error or timeout is distinct reject/uncertain; no automatic retry.

## Exact Active Schema/API Contract

### Generated schema facts

- Active `herdr` is version `0.8.0`; generated schema declares protocol `19` and `schema_version: 1` [VERIFIED: `herdr --version`; `/tmp/herdr-api-schema.json:1-5`].
- `session.snapshot` requires `version`, `protocol`, `workspaces`, `tabs`, `panes`, `layouts`, `agents`; `focused_workspace_id`, `focused_tab_id`, and `focused_pane_id` are nullable strings [VERIFIED: `/tmp/herdr-entities.json:2-70`]. There is no `host_epoch` field and no top-level snapshot revision in the active schema [VERIFIED: same lines].
- `AgentInfo` requires `terminal_id`, `agent_status`, `workspace_id`, `tab_id`, `pane_id`, `focused`, and `revision`; `revision` is uint64. `state_change_seq` is optional/default 0. Presentation and session fields are nullable as listed above [VERIFIED: `/tmp/herdr-entities.json:72-196`].
- `PaneInfo` has the same required pane/terminal/workspace/tab/focused/status/revision identity core, plus nullable `label`, optional nullable `scroll`, and optional title/tokens [VERIFIED: `/tmp/herdr-entities.json:198-317`].
- `agent.focus` requires exactly `{"target": string}` [VERIFIED: `/tmp/herdr-api-schema.json:4993-5007`]. Its success uses generic `agent_info` with an `agent` object, not a dedicated focus result [VERIFIED: `/tmp/herdr-api-schema.json:8834-8848`].
- A target miss is a typed error; live probe returned code `agent_not_found` [VERIFIED: `/tmp/herdr-focus-invalid.out`]. Treat unknown/stale/incompatible results as rejection or uncertainty, never as success.

### Authoritative ordered projection

Use the following exact current installed values, quoted verbatim from source:

> `RANK_BLOCKED = "0"`  
> `RANK_ATTENTION = "1"   # done (finished, unseen) or manually marked unread`  
> `RANK_WORKING = "2"`  
> `RANK_IDLE = "3"`  
> `RANK_UNKNOWN = "4"`  
> `RANK_SETTLED = "5"`  
> [VERIFIED: `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/daemon.py:47-52`]

> `VIEW_SORT = [`  
> `    {"field": {"token": "rank"}, "order": "asc"},`  
> `    {"field": "state_change_seq", "order": "desc"},`  
> `]`  
> [VERIFIED: `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/daemon.py:68-71`]

The TUI's executable projection is:

> `rows.sort(key=lambda r: (r["rank"], -r["seq"]))`  
> [VERIFIED: `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/inbox_tui.py:165-187`]

The daemon computes rank from semantic status and persisted flags in this order: blocked, unread, working, settled, done, idle, unknown [VERIFIED: local daemon.py:737-754]. It reports title/rank/age/since/flag via `pane.report_metadata` [VERIFIED: local daemon.py:1023-1039,1070-1085]. The bridge must not call `agent.view.set` merely to obtain ordering, because the official API says that view is transient UI projection and does not alter `agent.list` [CITED: https://herdr.dev/docs/socket-api/].

### Lifecycle/event contract

Subscribe to lifecycle events and treat them as refresh triggers. Active event data includes:

- `pane.created`: full `PaneInfo`.
- `pane.updated`: full `PaneInfo`.
- `pane.closed`: required `pane_id` and `workspace_id`; no replacement identity.
- `pane.focused`: required `pane_id` and `workspace_id`.
- `pane.moved`: previous pane/workspace/tab IDs and full replacement `PaneInfo`.
- `pane.exited`: pane/workspace IDs.
- `pane.agent_detected`: pane/workspace IDs, nullable agent, optional nullable final status, optional `released` boolean.
- `pane.agent_status_changed`: pane/workspace IDs, required status, nullable agent/display agent/title, and state labels.
[VERIFIED: `/tmp/herdr-entities.json:698-960`; public event list CITED: https://herdr.dev/docs/socket-api/]

On any lifecycle event that could change occupancy or semantic rank, refresh `agent.list` (or issue a full `session.snapshot` when the event stream reconnects). Do not derive a new binding from a partial event. The event subscription envelope is `{event,data}` and the initial subscribe response is separate from subsequent pushed events [VERIFIED: `/tmp/herdr-api-schema.json:6033-6048`; CITED: https://herdr.dev/docs/socket-api/].

## Before/After Focus Effects Matrix

This is the acceptance matrix for the live vertical slice. Evidence is split between verified documentation/source and unresolved controlled-fixture observations; do not mark the phase's live focus gate complete without collecting every row.

| Initial state | Before focus (record) | Documented/installed expected effect | After focus acceptance check | Current evidence |
|---|---|---|---|---|
| Working | status `working`, rank `2`, flag, sequence, pane/terminal/session identity | Focus changes UI focus; no plugin settle/unread call. | Success only if returned `agent_info` matches binding and `focused=true`; compare rank/flag/sequence. | Live focus on already-focused working `w14:p1` returned matching `agent_info`; no state transition was observable because it was already focused [VERIFIED: `/tmp/herdr-focus-result.json`]. |
| Idle/clear | status `idle`, rank `3`, no flag | Focus should select pane; no settle/unread mutation. | Compare exact state vector and order before/after; no hidden triage. | Public docs/source support no explicit plugin flag write; controlled idle fixture still required [CITED: https://herdr.dev/docs/cli-reference/]. |
| Blocked | status `blocked`, rank `0` | Focus selects pane; blocked state should remain blocked unless the agent itself changes. | Verify status/rank and no prompt/approval/send action. | Schema/status mapping verified; controlled blocked fixture required. |
| Finished/unseen (`done`) | status `done`, rank `1`, no manual flag | Herdr focus marks tab seen; docs define `done` as idle after unseen background work, so it may become `idle` and reorder. | Accept native seen transition as documented; never restore old rank/seen state. | Effect documented but not reproduced on this live session [CITED: https://herdr.dev/docs/cli-reference/]. |
| Manual unread | any status with plugin `flag="●"`, rank `1` | Focus event may clear plugin unread if it arrives after daemon's 1.5s guard; immediate/no transition focus may leave it set. | Record `flag`, rank and ordering immediately and after daemon refresh; report native timing outcome, never compensate. | `_on_focus` exact guard verified; live probe marked current already-focused pane unread and observed rank `1`/flag `●`, but no focus transition occurred; state was then restored with plugin `clear` [VERIFIED: local daemon.py:1308-1315; `/tmp/herdr-unread-before.json`, `/tmp/herdr-unread-after1.json`, `/tmp/herdr-after-clear.json`]. |
| Settled | idle/done/unknown with plugin `flag="⚑"`, rank `5` | Focus itself does not call settle/clear; settled flag is plugin-owned and should remain unless separate activity reopens it. | Verify flag/rank remain and no control-socket operation was issued. | Persistence/rank source verified; controlled settled fixture required [VERIFIED: local daemon.py:738-754,1248-1306]. |
| Vanished/closed | no current row; stale binding on tile | `agent.focus` should reject missing target (`agent_not_found`); host must reject before calling if stale. | Distinct stale/vanished result, full refresh, no slot substitution. | Live invalid-target probe returned `agent_not_found`; lifecycle schema supplies close/exited events [VERIFIED: `/tmp/herdr-focus-invalid.out`; `/tmp/herdr-entities.json:713-731,855-873`]. |
| Reassigned/replaced | same pane ID but changed terminal/session/revision/agent | Pane target string alone is insufficient to prove old occupant; host must reject mismatch and wait for fresh generation. | Never focus new occupant on an old tile; stale veil until complete rebind. | Identity fields and lifecycle events verified; replacement race needs controlled two-occupant fixture. |

### Required test fixture before live focus acceptance

Create or use a disposable Herdr fixture with at least two agent panes so one can be focused to create a real transition and another can hold each status. For each row capture `session.snapshot`/`agent.list` before, raw `agent.focus` response, event lines, and `agent.list` after immediate and delayed refresh. Record `pane_id`, `terminal_id`, optional `agent_session`, Herdr record `revision`, `state_change_seq`, `agent_status`, `tokens.rank`, `tokens.flag`, focused IDs, and ordered pane IDs. This is the only unresolved evidence gap that blocks claiming exact before/after behavior across all requested states.

## State and Stale/Nullability Policy

- **Current:** only a complete snapshot with valid plugin rank, required identity fields, and fresh bridge/device session may enable a tile.
- **Stale:** retain last pixels/identity only behind a visible stale/offline veil; disable key. Stale bindings never call `agent.focus`.
- **Unavailable/incompatible:** clear or show explicit unavailable/unknown state; disable key. Missing rank is not equivalent to rank 4.
- **Vanished/reassigned:** freeze old identity as stale until fresh complete snapshot; reject press and never use the current slot occupant.
- **Null display fields:** preserve null as unavailable; use bounded fallback only among authoritative non-null fields (`title`, plugin title token, agent label) and never invent identity from cwd when required identity is absent.
- **Host epoch:** bridge-generated random opaque value, rotated when bridge/device session or authoritative reconnect invalidates cache. Not supplied by active Herdr schema.
- **Snapshot revision:** bridge-monotonic uint64/sequence for complete normalized snapshots; must increase only on committed complete generation. Herdr's per-agent `revision` is retained for source validation but is not the bridge revision.
- **Action result:** pending until host/Herdr response. Success only after exact current target identity and bridge epoch/revision match; errors/mismatch/timeout become distinct reject or uncertain states and are not retried automatically.

## Security Domain

`security_enforcement` is enabled and ASVS level 1 is configured [VERIFIED: `.planning/config.json:96-125`].

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | yes (host/device link) | Keep Herdr authentication/session access on the host; use the already paired Phase 1 device boundary and do not put account credentials on firmware. |
| V3 Session Management | yes | Rotate host epoch on bridge/device session reset; discard uncertain in-flight actions; do not replay presses. |
| V4 Access Control | yes | Allowlist only typed focus for the current binding; reject empty/stale/offline/reassigned bindings; never expose raw Herdr methods. |
| V5 Input Validation | yes | Validate bounded Phase 1 frames, exact slot/epoch/revision/identity, rank/token shape, and current Herdr response before dispatch. |
| V6 Cryptography | limited | No provider secret crosses to firmware; do not invent device-side credential storage or cryptography in this phase. |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Slot reuse after reorder/reassignment | Tampering | Bind exact pane/terminal/session identity and snapshot revision; reject mismatch. |
| Replay after reconnect | Spoofing/Tampering | Rotate host epoch, clear pending intents, require fresh complete snapshot and fresh press. |
| Firmware acting as generic Herdr proxy | Elevation of privilege | Typed focus-only action schema and host-side allowlist. |
| Prompt/transcript/credential leakage | Information disclosure | Normalize to title/discriminator/state/age and opaque identity; no raw paths, transcripts, tokens, or socket-control commands on device. |
| Local unauthorized socket access | Elevation of privilege | Keep host socket ownership/permissions narrow; observed Herdr and inbox control sockets are mode 0600 owned by `nnex` [VERIFIED: `stat` probe]. |

## Code Examples

### Ordered projection (source-verified pseudocode)

```python
# Source: installed inbox_tui.py:165-187 and daemon.py:47-71
rows = []
for rec in agent_list_result["agents"]:
    tokens = rec.get("tokens") or {}
    rank = tokens.get("rank")
    if rank is None:
        return unavailable("inbox rank metadata missing")
    rows.append({
        "pane_id": rec["pane_id"],
        "terminal_id": rec["terminal_id"],
        "status": rec["agent_status"],
        "rank": rank,
        "seq": rec.get("state_change_seq", 0),
        "title": rec.get("title") or tokens.get("title"),
        "tokens": tokens,
    })
rows.sort(key=lambda row: (row["rank"], -row["seq"]))
top_three = rows[:3]
```

The `rank` values and sort fields in this example are quoted verbatim in the authoritative projection section above; the missing-rank fail-closed branch is a product safety rule, not an installed plugin fallback.

### Focus request/result boundary

```text
Device -> host: typed focus(slot, pane_id, terminal_id, host_epoch, snapshot_revision)
Host: verify current complete generation and current Herdr AgentInfo identity
Host -> Herdr: {"method":"agent.focus", "params":{"target":"<pane_id>"}}
Herdr -> host: {"result":{"type":"agent_info","agent":{...}}}
Host -> device: pending, then success only when returned pane/terminal/session is exact
```

The Herdr request shape and response type are active-schema verified [VERIFIED: `/tmp/herdr-api-schema.json:4993-5007,8834-8848`].

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| Read plugin-private `state.json`/control socket | Public Herdr `agent.list` plus plugin metadata tokens | Installed plugin README and Herdr 0.8.0 docs | Keeps the bridge on a supported read/action boundary and avoids private triage mutation [CITED: https://herdr.dev/docs/socket-api/; VERIFIED: local README.md:195-210]. |
| Focus by numeric slot | `pane_id` target plus terminal/session/revision revalidation | Phase 2 locked decisions | Prevents a reordered tile from focusing a replacement occupant. |
| Assume focus is mutation-free | Document native seen and possible manual-unread effects | Herdr 0.8.0 CLI docs + installed daemon | Product feedback must distinguish successful focus from changed attention ordering. |
| Event log as complete state | Snapshot bootstrap plus event-triggered refresh | Herdr 0.8.0 socket docs | Reconnect and missed-event recovery converge to one authoritative state [CITED: https://herdr.dev/docs/socket-api/]. |

**Deprecated/outdated for this phase:**
- Treating `agent.view.set`'s UI ordering as `agent.list` ordering.
- Recomputing rank from `agent_status` in bridge or firmware.
- Reading/writing `agent-inbox-state/state.json` or `control.sock`.
- Calling focus and then trying to restore plugin flags with `unread`/`settle`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | The installed `herdr-agent-inbox` rank/token contract remains compatible for the bridge lifetime. | Standard Stack / projection | Plugin update could change token names or rank meaning; startup compatibility gate must fail closed. |
| A2 | A future Herdr lifecycle can reuse a pane ID while terminal/session identity changes. | Pitfalls / identity | If false, validation is conservative; if true and omitted, stale presses can focus the wrong occupant. |
| A3 | The bridge can generate and persist an opaque host epoch in its device-session state. | Nullability policy | If Phase 1 protocol cannot carry it, Phase 2 requires a protocol extension before focus. |
| A4 | The installed daemon's 1.5-second `_on_focus` timing is sufficient to describe all manual-unread outcomes. | Focus matrix | Scheduling/event latency may vary; controlled fixture must measure immediate and delayed refresh. |

## Open Questions / Evidence Gaps

1. **Finished/unseen live before/after:** A disposable two-pane fixture has not yet been run, so the exact installed sequence/status/rank transition after focusing `done` is documented but not observed on this host.
2. **Manual-unread focus transition:** The current live probe marked an already-focused pane unread, so no actual `pane_focused` transition occurred; it confirmed rank/flag before and restored state, but did not prove delayed `_on_focus` clearing on a real focus transition.
3. **Settled live before/after:** Source confirms rank 5 and persistence, but no live settled pane was available for a focus transition.
4. **Reassigned pane race:** Active schema exposes required identity/revision and lifecycle events, but a controlled pane replacement/move must prove which identity combination remains stable on this Herdr build. Use terminal ID plus optional native session and reject on any mismatch.
5. **Host epoch/revision acknowledgement:** Active Herdr has per-agent `revision` but no host epoch/top-level snapshot revision. The bridge must define its own fields and cannot claim Herdr acknowledges them; implementation should document this distinction in the device protocol and outcome evidence.
6. **Phase 1 source availability:** The repository currently contains the Phase 1 protocol files, but Phase 1 execution is concurrent. Phase 2 planning must consume the final committed `ProtocolCodec`/`ProtocolSession` API and not infer new names from this research.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---:|---|---|
| `herdr` CLI | Schema, snapshot/list/focus probes | yes | 0.8.0 | None; active Herdr is required for live acceptance |
| Herdr Unix socket | Snapshot/events/focus | yes | `/home/nnex/.config/herdr/herdr.sock` | None; offline behavior must be simulated only for negative tests |
| `herdr-agent-inbox` control socket | Controlled plugin state probes only; not a product bridge dependency | yes | installed `de409f683262` | Do not use it in product code |
| Python | Installed plugin/host bridge | yes | 3.14.7 (plugin recommends 3.11+) | Python 3.11+ target remains the compatibility floor from installed README |

## Sources

### Primary (HIGH confidence)

- Installed active schema generated with `herdr api schema --json` (`/tmp/herdr-api-schema.json`), protocol 19/schema 1; exact request/response/entity/event shapes.
- Installed `herdr-agent-inbox` revision `de409f683262`: `README.md`, `daemon.py`, `inbox_tui.py`, and `actions.py`; exact rank constants, metadata projection, ordering, lifecycle refresh, and focus-side-effect code.
- Live probes on the active local session: `herdr agent list`, `herdr api snapshot`, `herdr agent focus w14:p1`, invalid focus, and controlled plugin unread/clear (`/tmp/herdr-*.json`, `/tmp/herdr-focus-invalid.out`).
- `.planning/phases/02-authoritative-agent-projection-and-exact-focus/02-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, Phase 1 `01-CONTEXT.md`, `01-UI-SPEC.md`, `01-PATTERNS.md`, and `firmware/src/protocol/protocol.{h,cpp}`.

### Secondary (MEDIUM confidence)

- Official Herdr Socket API documentation, latest 0.8.0: https://herdr.dev/docs/socket-api/.
- Official Herdr CLI reference, latest 0.8.0: https://herdr.dev/docs/cli-reference/.
- Existing project research: `.planning/research/STACK.md`, `ARCHITECTURE.md`, `PITFALLS.md`, `SUMMARY.md`, and `FEATURES.md`.

### Tertiary (LOW confidence)

- None used for implementation claims. Any future plugin revision behavior not covered by the installed source is an assumption and requires a compatibility check.

## Project Constraints (from AGENTS.md)

- Follow the host-authoritative product boundary: entries/order come from installed Herdr inbox; do not invent lifecycle/order.
- Focus selects an agent pane only; no automatic settle, dismiss, acknowledge, reply, approval, or arbitrary action.
- Keep credentials/authenticated access on the host; firmware receives normalized device-scoped data only.
- Distinguish offline/unavailable/stale data visibly.
- Consume the existing Phase 1 protocol/session boundary; do not add a second parser or transport.
- Do not touch Phase 1 source/artifacts/STATE.md/ROADMAP.md while Phase 1 execution is concurrent.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for active binary/schema and installed plugin; MEDIUM for future compatibility because plugin rank is not a public cross-plugin guarantee.
- Architecture: HIGH for host/device responsibility and Herdr API boundaries; MEDIUM for exact lifecycle identity stability until replacement fixture is run.
- Pitfalls: HIGH for ordering, nullable fields, focus request/result, and plugin `_on_focus` source; MEDIUM for all-state before/after focus effects pending controlled fixture.

**Research date:** 2026-08-17  
**Valid until:** 2026-08-24 for installed plugin/API behavior; re-run schema and projection checks after any Herdr/plugin update.
