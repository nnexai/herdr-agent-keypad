# Architecture Research

**Domain:** USB/Wi-Fi companion hardware for a local AI-agent inbox
**Researched:** 2026-08-16
**Confidence:** MEDIUM

## Executive Recommendation

Build the product as two independently testable systems joined by a small, versioned, transport-neutral device protocol:

1. **Host authority:** a herdr plugin/bridge reads the installed inbox's already-ranked agent projection, reads Codex limits through the local Codex app-server, assembles a device-scoped snapshot, and performs one bounded command: `agent.focus`.
2. **Device projection:** firmware accepts complete snapshots, renders three agent slots plus one quota slot, reports keypress intents, and visibly ages its last known data. It never owns inbox lifecycle, provider authentication, or agent ordering.

Use complete replaceable snapshots rather than a replicated event log. There are only four display slots, so full replacement is cheap and makes startup, reconnect, missed-frame recovery, and transport switching converge through the same path. Every keypress must carry the stable entry identity and snapshot revision that were displayed when the user pressed it; the host revalidates that identity before focusing. Selection must never invoke the inbox plugin's settle, unread, clear, or dismiss actions.

Do not lock transport before physical bring-up. Both native USB CDC and Wi-Fi station mode are officially supported on the ESP32-S3 software stack. USB serial is the leading v1 candidate because the device is already USB-powered and it keeps the service local, but its actual connector, enumeration identity, reset/reflash behavior, and sustained bidirectional operation must be proven on the connected board. Wi-Fi is the comparison path if USB proves operationally poor. A hybrid implementation should remain protocol-compatible but is not the default: two active links introduce duplicate actions and split-brain connection state without adding v1 value.

## Standard Architecture

### System Overview

```text
 HOST TRUST BOUNDARY
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ Upstream authorities                                                    │
 │                                                                         │
 │  herdr local socket                installed herdr-agent-inbox           │
 │  - session snapshot/events         - rank/title/settle/unread projection │
 │  - agent.focus                     - authoritative priority semantics    │
 │          │                                      │                       │
 │          └──────────────┬───────────────────────┘                       │
 │                         ▼                                               │
 │               ┌────────────────────┐                                    │
 │               │ Inbox Adapter      │  read-only projection              │
 │               └─────────┬──────────┘                                    │
 │                         │ NormalizedAgent[]                              │
 │                         ▼                                               │
 │  codex app-server   ┌────────────────────┐       ┌───────────────────┐  │
 │  + host auth ──────►│ Quota Collector    │──────►│ Snapshot Assembler│  │
 │                     └────────────────────┘       └─────────┬─────────┘  │
 │                                                          │ full state  │
 │               ┌────────────────────┐                     ▼             │
 │  key intent ─►│ Focus Executor     │◄──────┌────────────────────────┐  │
 │               │ validate + focus   │       │ Device Session Manager │  │
 │               └─────────┬──────────┘       │ revision/freshness/ack │  │
 │                         └──agent.focus─────►└───────────┬────────────┘  │
 │                                                        │               │
 │               ┌────────────────────────────────────────┴────────────┐  │
 │               │ Transport adapter: USB CDC OR Wi-Fi; hybrid-capable │  │
 │               └────────────────────────────────────────┬────────────┘  │
 └────────────────────────────────────────────────────────┼───────────────┘
                                                          │ versioned frames
 DEVICE TRUST BOUNDARY                                    │
 ┌────────────────────────────────────────────────────────┼───────────────┐
 │               ┌────────────────────────────────────────▼────────────┐  │
 │               │ Link + Protocol Session                            │  │
 │               │ frame, validate, deduplicate, acknowledge          │  │
 │               └──────────────┬───────────────────┬─────────────────┘  │
 │                              │                   │                    │
 │                    full snapshot              action result           │
 │                              ▼                   ▼                    │
 │               ┌────────────────────┐   ┌──────────────────────────┐  │
 │               │ Snapshot Cache     │   │ Input/Intent Controller  │  │
 │               │ revision + expiry  │◄──│ slot → displayed entry   │  │
 │               └─────────┬──────────┘   └────────────┬─────────────┘  │
 │                         ▼                           │ keypress         │
 │               ┌────────────────────┐                │                 │
 │               │ Four-tile Renderer │                │                 │
 │               │ 3 agents + quota   │                │                 │
 │               └─────────┬──────────┘                │                 │
 │                         ▼                           │                 │
 │        four GC9107 displays / LEDs / physical keys ┘                 │
 └──────────────────────────────────────────────────────────────────────┘
```

The **reusable seam** is the normalized snapshot/action protocol, not a host database and not a direct serialization of herdr or Codex objects. The firmware should know concepts such as `AgentTile`, `QuotaTile`, `Freshness`, and `FocusIntent`; it should not know herdr token names, Codex JSON-RPC fields, local paths, or credentials.

### Component Responsibilities

| Component | Owns | Must not own | Typical implementation boundary |
|---|---|---|---|
| Board support layer | Initialization and polling of four panels, keys, encoder, LEDs; physical key/panel map | Inbox semantics, network protocol, agent identity | Thin wrapper around official `TKeyboardS3Pro` APIs and LovyanGFX |
| Firmware renderer | Deterministic layout for three agent tiles and quota tile; current/stale/offline/pending/error visuals | Upstream fetching or action authorization | Pure rendering from immutable device snapshot plus local link state |
| Firmware input controller | Debounce/edge interpretation and binding a press to the identity currently displayed in that slot | Settle/unread behavior, arbitrary host commands | Emits a typed `focus` intent containing entry id, pane target token, snapshot revision, action id |
| Firmware protocol session | Framing, version negotiation, full-snapshot replacement, acknowledgements, heartbeat, action-result correlation | Transport-specific socket/serial details | Transport-independent state machine over byte/message streams |
| Firmware transport adapter | USB CDC or Wi-Fi connect/read/write and link events | Message meaning or retrying completed focus actions | `Link` interface used by protocol session |
| Host plugin/bridge lifecycle | Start/stop/reconnect workers with the herdr session; coordinate adapters and device sessions | Provider credentials in firmware; duplicate inbox state machine | Long-lived process launched by herdr plugin startup hook |
| Inbox adapter | Convert the installed inbox's authoritative ordered projection into at most three normalized entries; map stable entry id to live pane id | Recompute priority tiers or write settle/unread state | Read-only client of herdr socket plus installed inbox projection/state contract |
| Codex quota collector | Initialize local Codex app-server client; read and normalize rate limits; timestamp success/failure | OAuth/API tokens, quota guessing, device transport | Host subprocess/client using `account/rateLimits/read` and sparse update handling |
| Snapshot assembler | Join latest agent projection and quota observation; assign host epoch/revision and per-section freshness | Upstream source state or UI drawing details | Pure host-side projection function |
| Device session manager | Current published snapshot, connected device capabilities, revision acknowledgements, heartbeat, bounded action dedupe | Durable inbox lifecycle | In-memory per-device session; optional tiny local settings only if proven necessary |
| Focus executor | Revalidate displayed entry, resolve its current live pane, call public `agent.focus`, return accepted/rejected result | Settle, unread, clear, prompt, send keys, or shell execution | Single allowlisted command path to herdr socket |
| Transport endpoint | Expose the same framed session over selected link and apply local authentication policy | Upstream APIs and domain transforms | Serial port process or loopback/LAN network listener/client |

### State Ownership

| State | Authority | Replicas/caches | Rule |
|---|---|---|---|
| Agent process/pane topology and actual focus | herdr server | Host adapter cache; device gets opaque display identity only | Refresh from `session.snapshot` after reconnect, then update from events |
| Agent priority, title, settle/unread flags | Installed `herdr-agent-inbox` plugin | Host normalized projection; firmware display snapshot | Mirror its ordering; never implement a second rank function |
| Codex authentication and refresh tokens | Codex on the host | None on device | Collector uses the local authenticated app-server; firmware sees normalized limits only |
| Latest observed quota | Quota collector | Snapshot assembler and device last-known tile | Preserve `observed_at`; sparse notifications do not clear omitted values |
| Device-facing revision/epoch | Host bridge | Firmware cache and acknowledgements | A new host process creates a new epoch; revisions are monotonic only within that epoch |
| Displayed snapshot | Host bridge is publisher; firmware owns last delivered copy | Renderer consumes immutable copy | New full snapshot atomically replaces prior snapshot |
| Pending physical press | Firmware until sent; host while executing | Correlated by action id | Never replay automatically across a new device boot or host epoch |
| Inbox settlement/unread persistence | Existing inbox daemon/state file | None in new bridge | Focus path cannot write it |

## Recommended Project Structure

The exact language/toolchain belongs to stack research, but the dependency boundaries should remain visible in the repository:

```text
firmware/
├── src/
│   ├── board/              # T-Keyboard initialization and physical mapping
│   ├── protocol/           # transport-neutral session and message decoding
│   ├── transport/          # usb_cdc and wifi link implementations
│   ├── state/              # immutable snapshot cache and freshness clock
│   ├── input/              # slot binding and focus-intent creation
│   └── ui/                 # four-tile renderer, stale/offline/pending states
└── test-fixtures/          # captured protocol messages, usable without hardware

host/
├── plugin/                 # herdr manifest/startup integration
├── bridge/                 # orchestration and device session manager
├── adapters/
│   └── inbox/              # existing inbox projection → normalized entries
├── collectors/
│   └── codex/              # app-server lifecycle and quota normalization
├── actions/
│   └── focus/              # validate target and call agent.focus only
├── protocol/               # host codec and shared contract fixtures
└── transport/              # usb_serial and wifi implementations

protocol/
├── schema/                 # versioned message definitions
└── fixtures/               # language-neutral canonical examples/error cases
```

### Structure Rationale

- **`board/` is below firmware application logic:** physical panel/key numbering will be discovered during bring-up and should be corrected in one map rather than throughout UI code.
- **`protocol/` is separate from `transport/`:** the same messages, revisions, stale semantics, and action safety must work over serial or a network link.
- **Adapters and collectors are separate:** a herdr restart must not make a still-valid Codex observation disappear, and Codex failure must not blank agent tiles.
- **Focus is a dedicated allowlisted action:** it is easier to prove absence of mutation when no general command dispatcher exists.
- **Fixtures are shared across host and firmware:** they keep independently implemented codecs aligned without requiring the physical board for every change.

## Interface Boundaries

### Normalized Device Snapshot

The contract should express display truth, not upstream implementation details. A conceptual shape is:

```text
Snapshot {
  protocol_version
  host_epoch
  revision
  produced_at
  agent_source: { status, observed_at, expires_at, error_code? }
  agents[0..3]: {
    entry_id, pane_ref, title, state, state_since, workspace_label?, accent
  }
  quota_source: { status, observed_at, expires_at, error_code? }
  codex: {
    plan_label?, primary_used_percent?, primary_resets_at?,
    secondary_used_percent?, secondary_resets_at?
  }
}
```

Key constraints:

- `entry_id` is stable enough to compare the displayed entry with the current host projection. It is not a list index.
- `pane_ref` should be treated as an opaque, host-issued target token. The host still re-resolves/revalidates it; firmware must not synthesize one.
- `status` is an explicit enum such as `current`, `stale`, `unavailable`, or `offline`; absent values never imply zero usage or an empty inbox.
- `observed_at` describes the upstream observation, while `produced_at` describes projection generation. They are not interchangeable.
- Each source ages independently. Codex may be stale while agents remain current, or herdr may be offline while a recent quota observation remains displayable.
- Bounds are fixed and validated before allocation: at most three agents, bounded UTF-8 strings, and bounded frame size.

### Action Contract

```text
FocusIntent {
  protocol_version
  device_boot_id
  action_id
  host_epoch
  snapshot_revision
  entry_id
  pane_ref
  slot
  pressed_at_device_uptime_ms
}

ActionResult {
  action_id
  outcome: accepted | stale_target | not_found | herdr_offline | rejected | timeout
  current_revision
}
```

The bridge accepts only `focus`. It must verify that `(entry_id, pane_ref)` still names the same live agent represented by the referenced or current projection. A mismatched/stale slot is rejected and followed by a fresh snapshot; it must not focus whichever agent has since moved into the same slot. Dedupe is scoped to `(device_boot_id, action_id)`. A timeout is not proof that focus did not happen, so firmware may show an uncertain result but must not continuously retry the action.

### Transport Interface

Both host and firmware need an interface no richer than:

```text
Link.connect / Link.close
Link.readFrame / Link.writeFrame
Link.onConnected / Link.onDisconnected
Link.peerIdentity
```

Serial framing needs explicit message boundaries, maximum length, checksum or equivalent corruption detection, and parser resynchronization after garbage. Wi-Fi framing may use a message transport, but it must preserve the same maximums and application-level session handshake. Transport liveness does not prove upstream freshness.

## Data Flow

### Snapshot Flow

```text
herdr session.snapshot ──bootstrap──┐
herdr events.subscribe ──changes────┼─► Inbox Adapter ─► ordered top 3 ─┐
installed inbox projection ─────────┘                                   │
                                                                        ├─► Snapshot Assembler
Codex app-server initialize ─► rateLimits/read ─► Quota Collector ──────┘
                                                                              │
                                                host_epoch + revision + times │
                                                                              ▼
                                                    Device Session Manager
                                                                              │ full replacement
                                                                              ▼
                                                     firmware validates bounds
                                                                              │ atomic swap
                                                                              ▼
                                                cache ─► freshness ─► renderer
```

1. On host startup or herdr reconnect, bootstrap with an authoritative snapshot rather than waiting for future events. Official herdr documentation explicitly says `session.snapshot` is a one-time bootstrap and clients should take it again after reconnect.
2. Subscribe to relevant pane/agent/resource events and coalesce bursts into a new projection. The adapter does not assign ranks; it consumes the inbox plugin's order/rank metadata.
3. Independently initialize Codex app-server, perform `account/rateLimits/read`, then merge sparse `account/rateLimits/updated` notifications into the last complete observation or refetch. The official Codex documentation says these notifications are sparse.
4. Publish a complete device snapshot whenever normalized content or source freshness changes. Increment revision only for a changed published snapshot.
5. Firmware validates version, bounds, epoch, and revision, builds the replacement off-screen/in temporary state, then atomically swaps the snapshot. It acknowledges the accepted revision.
6. The renderer derives stale/offline visuals from the last snapshot plus a monotonic local clock; it does not need continuing host traffic to become truthful.

### Keypress-to-Focus Flow

```text
physical key down
  ► Input Controller reads slot binding from currently rendered snapshot
  ► FocusIntent(entry_id, pane_ref, host_epoch, revision, action_id)
  ► protocol/link
  ► Host session validates version, epoch, dedupe, and current binding
  ► Focus Executor calls herdr agent.focus(target = live pane id)
  ► ActionResult
  ► device shows short accepted/rejected/uncertain feedback
  ► host publishes refreshed full snapshot if focus or topology changed
```

The focus executor does **not** call the installed plugin's `settle`, `unread`, `clear`, or workspace actions and does not edit its `state.json`. The installed inbox TUI already focuses via public `agent.focus`, which is strong local evidence for this boundary. Herdr may naturally change its own focused-pane/seen presentation as part of focusing; that is the requested focus side effect, not permission to mutate inbox triage flags.

### Reconnect Convergence

1. Device establishes a link and sends `Hello(protocol_versions, device_id, device_boot_id, capabilities, last_host_epoch, last_revision)`.
2. Host selects a compatible protocol version and always sends the latest **full** snapshot. It does not assume the device's cached revision still exists.
3. Device replaces its cache if the host epoch changed, even when the numeric revision is lower.
4. Unacknowledged snapshots may be retransmitted; they are idempotent replacements.
5. Focus actions are deduplicated while the host process remembers them, but are not replayed by the firmware after a new boot/session handshake. Human input can be repeated deliberately.
6. After herdr reconnect, the host rebuilds agent state from `session.snapshot`, re-establishes subscriptions, then publishes. It does not apply queued mutations because there are none.
7. After Codex reconnect/auth recovery, the collector takes a new full rate-limit read before declaring the quota tile current.

This design converges after missed events, host restart, device reset, cable removal, Wi-Fi roam, or switching transport without a distributed database.

## Freshness, Offline, and Failure Boundaries

### Freshness Model

Use three independent clocks/statuses:

- **Link freshness:** last valid frame/heartbeat between device and bridge.
- **Agent-source freshness:** last successful authoritative herdr/inbox projection.
- **Quota-source freshness:** last successful Codex rate-limit observation.

The firmware should continue displaying the last known values with an unmistakable stale marker until their `expires_at`, then move to unavailable/offline presentation according to the source status. An empty current agent list means “no entries”; an unavailable agent source means “cannot know.” A missing quota percentage means “unavailable,” never `0% used`.

### Failure Matrix

| Failure | Containment boundary | Required behavior | Recovery |
|---|---|---|---|
| herdr socket down/restarted | Inbox adapter and focus executor | Agent tiles become stale/offline; focus rejects `herdr_offline`; quota can remain current | Backoff, take new `session.snapshot`, resubscribe, republish full snapshot |
| Inbox plugin daemon unavailable | Inbox adapter | Do not silently fall back to a competing priority algorithm; show agent source unavailable or explicitly degraded if a supported raw fallback is later designed | Reconnect to the plugin-supported projection and replace snapshot |
| Codex app-server/auth unavailable | Quota collector | Keep agent tiles live; show quota unavailable/stale with observation age | Restart/reinitialize app-server client and take a full read |
| Codex sparse update omits fields | Quota collector | Preserve prior fields; do not clear them | Merge sparse update or refetch full snapshot |
| USB cable/CDC disconnect | Transport adapter | Device ages cached state locally; host drops only that device session | Re-enumerate/reopen; Hello; full snapshot |
| Wi-Fi/AP loss | Wi-Fi adapter | Same visible aging; no blocking work in Wi-Fi callback task | Event sets state, main loop reconnects with backoff; Hello; full snapshot |
| Corrupt/oversized/unknown frame | Protocol boundary | Reject frame, never allocate from unchecked length, never execute action | Resynchronize or close/reconnect after bounded errors |
| Host response lost after focus | Action boundary | Show uncertain/timeout; do not automatic-loop the focus call | Fresh snapshot and deliberate user retry if needed |
| Agent disappears/reorders during press | Focus executor | Reject `stale_target`; never focus the new slot occupant | Publish latest full snapshot |
| Renderer/panel failure | Board/UI boundary | Other panels and link should continue where possible; diagnostic/offline indication | Reinitialize affected display if library permits; physical investigation if persistent |
| Bridge crash | Process boundary | Existing inbox daemon/herdr continue unaffected; device visibly ages | herdr startup/watchdog restarts bridge; new epoch and full snapshot |

## Transport Comparison and Decision Gate

| Criterion | USB CDC serial | Wi-Fi | Hybrid USB + Wi-Fi |
|---|---|---|---|
| Official stack support | Official LILYGO board settings enable Hardware CDC/JTAG and USB CDC on boot; Espressif exposes CDC connect/disconnect/RX/TX APIs | ESP32-S3 Arduino core supports STA mode, events, `reconnect`, `isConnected`, and auto-reconnect | Components exist, but simultaneous board-specific behavior is not established by documentation alone |
| v1 topology | One power/data cable to one Linux host | USB power plus LAN data path | USB power plus two data paths |
| Credentials | No network credential on device; host serial device permissions only | Device needs network provisioning and a device-scoped bridge credential | Wi-Fi credentials plus serial-device permissions |
| Attack surface | Local physical/OS device boundary | LAN listener/client, authentication, replay protection, and likely TLS/pinning concerns | Union of both surfaces plus link arbitration |
| Discovery | OS serial enumeration; stable identity/path must be proven | Address/discovery/pairing needed | Must associate two links with one physical device |
| Typical failure | Re-enumeration after reset/flash, port permissions, framing/partial writes | AP loss, DHCP/address changes, callback concurrency, network latency | Duplicate actions, competing snapshots, split-brain liveness |
| UX while host sleeps/restarts | Cable remains but data link can vanish; firmware must age state | LAN may remain while host service vanishes; same aging required | No semantic advantage unless one path actually survives and arbitration is correct |
| Recommendation | **Bring up first and leading v1 candidate**, not yet locked | **Second bring-up candidate** if serial usability/reliability is poor or wireless placement matters | Keep protocol capable; defer implementation unless measurements show a concrete need |

### Physical Bring-Up Decisions

The following cannot be responsibly closed from documentation and require the actual connected device:

1. Which USB-C connector/path exposes native ESP32-S3 CDC while powering the whole board, and whether flashing/resetting causes predictable Linux re-enumeration.
2. Whether the board exposes a stable USB identity that the bridge can select without relying on a volatile `/dev/ttyACM*` number; otherwise determine the safe host-side matching rule.
3. Sustained full-duplex serial behavior while refreshing all four panels, polling keys, and driving LEDs, including corruption/recovery after unplug/replug.
4. Actual key-to-panel mapping, panel order/orientation/color correctness, encoder position, and which physical key corresponds to each displayed agent tile.
5. Whether sequential redraw (required because the STM32 multiplexes panel chip-selects) meets latency expectations without starving input/protocol polling.
6. Wi-Fi association/reconnect reliability and memory headroom while all displays are active; callback-to-main-loop handoff must be exercised.
7. If hybrid remains under consideration, whether native USB and Wi-Fi remain stable simultaneously and which link wins after asymmetric reconnect. Do not implement arbitration before this test demonstrates value.
8. Whether firmware upload/debug logging can coexist with the production serial protocol or requires separate framing, port mode, or logging policy.

**Transport decision gate:** run the same minimal `Hello → full snapshot → key intent → action result → unplug/reconnect → full snapshot` scenario over USB and Wi-Fi on the real board. Select v1 transport using observed setup friction, reconnect time, error rate, and implementation/security cost. USB wins ties.

## Architectural Patterns

### Pattern 1: Host-Owned Adapter Boundary

**What:** Upstream-specific clients normalize into a device domain model on the host.

**When to use:** Always for herdr/inbox and provider quota data.

**Trade-offs:** Adds mapping code, but prevents firmware updates whenever an upstream schema changes and keeps credentials and private paths off the device.

### Pattern 2: Full Snapshot plus Bounded Intent

**What:** Host sends replaceable complete display state; device sends only narrow, identity-bound user intents.

**When to use:** Small projections where correctness and reconnect behavior matter more than bandwidth.

**Trade-offs:** Repeats a small amount of data, but removes patch ordering, tombstones, and event-log replay. With four tiles, incremental state replication is unjustified.

### Pattern 3: Epoch + Revision, Not Revision Alone

**What:** Each host process/session has a random epoch and monotonic snapshot revision.

**When to use:** Whenever both sides can restart independently.

**Trade-offs:** Adds one field, but prevents a restarted host's revision `1` from being mistaken for older data than the previous process's revision `900`.

### Pattern 4: Identity-Bound Actions

**What:** A press names the exact displayed entry and snapshot rather than merely “slot 2.”

**When to use:** Dynamic ordered lists where entries can move between observation and action.

**Trade-offs:** The host may reject a press during rapid churn, which is safer than focusing the wrong agent. A fresh snapshot makes the retry obvious.

### Pattern 5: Independent Source Health

**What:** Agent data, Codex data, and transport each carry their own health and observation time.

**When to use:** Always; these dependencies fail independently.

**Trade-offs:** More UI states, but avoids the dangerous binary “connected means current” assumption.

## Anti-Patterns

### Reimplementing Inbox Priority

**What people do:** Read raw `agent.list` and recreate blocked/done/working/idle/settled sorting in the new bridge.

**Why it is wrong:** It creates a second lifecycle model that can drift from the installed inbox's settle/unread semantics and ordering.

**Do this instead:** Consume the installed inbox's supported ordered/rank projection. If that projection is not externally consumable enough, extend its supported interface rather than copy its algorithm.

### Slot-Only Key Actions

**What people do:** Send `{slot: 1}` and focus whatever is currently in slot 1.

**Why it is wrong:** A reorder can focus the wrong agent.

**Do this instead:** Send stable entry identity, pane token, epoch, and revision; reject stale mappings.

### “Connected” as a Freshness Signal

**What people do:** Show cached data as current while the serial socket or Wi-Fi link is open.

**Why it is wrong:** Herdr or Codex can be unavailable behind a healthy device link.

**Do this instead:** Track and render source-level observation times and expiry separately from link liveness.

### General Remote Command Dispatcher

**What people do:** Let firmware submit arbitrary herdr methods, plugin actions, shell strings, or pane keystrokes.

**Why it is wrong:** It expands the security boundary and makes accidental settle/dismiss/mutation possible.

**Do this instead:** Implement one typed `focus` operation with server-side validation and no arbitrary payload.

### Durable Duplicate Inbox Store

**What people do:** Add SQLite to persist a second queue, acknowledgement state, and ordering.

**Why it is wrong:** The existing inbox is authoritative; duplicated durable state creates conflict resolution and migration work with no v1 need.

**Do this instead:** Keep derived projection/session state in memory and rebuild from upstream authorities. Persist only device configuration if later required.

### Automatic Action Replay

**What people do:** Retry a timed-out focus request indefinitely or replay queued presses after reconnect.

**Why it is wrong:** The first request may have succeeded and the displayed identity may no longer be current.

**Do this instead:** Dedupe action ids, report uncertainty, refresh state, and require a deliberate new press.

## Integration Points

### External Services

| Service | Integration pattern | Notes |
|---|---|---|
| herdr local socket | `session.snapshot` bootstrap, `events.subscribe` updates, `agent.focus` command | Newline-delimited JSON over Unix socket on Linux; resnapshot after reconnect |
| Installed `herdr-agent-inbox` | Read its authoritative rank/title/settle/unread projection | Its daemon is sole writer of its state; keypad must not invoke triage mutations |
| Codex app-server | Host-managed subprocess/client using stdio JSONL; initialize handshake; full rate-limit read plus sparse updates | Credentials remain in Codex host storage; websocket listener is documented experimental/unsupported and should not be the bridge-to-device transport |
| Linux device subsystem | Discover/open selected USB CDC device and observe disconnect/re-enumeration | Matching rule and permissions require physical/host bring-up |
| Local Wi-Fi/LAN | Optional device link using STA reconnect and device-scoped authentication | Do not expose herdr or Codex directly; expose only normalized protocol |

### Internal Boundaries

| Boundary | Communication | Invariant |
|---|---|---|
| Inbox adapter → snapshot assembler | `NormalizedAgent[]` already ordered | Maximum three; bridge does not rerank |
| Quota collector → snapshot assembler | `QuotaObservation` | Always includes observation time and explicit availability |
| Snapshot assembler → device session | Immutable full `Snapshot` | New epoch/revision uniquely identifies version |
| Device session ↔ transport | Bounded frames | Transport cannot execute domain actions |
| Firmware cache → renderer | Immutable state + monotonic time | Renderer performs no I/O |
| Firmware input → protocol | `FocusIntent` captured from displayed binding | No slot-only actions |
| Device session → focus executor | Validated typed command | Only `focus` is allowed |
| Focus executor → herdr | `agent.focus` with current live target | No inbox state action or filesystem mutation |

## Dependency-Driven Build Order

This is an ordering recommendation based on dependencies and risk, not final roadmap phase naming.

1. **Characterize the actual board and record the physical map.** Flash/run official display, key, encoder, LED, and CDC examples on the connected unit. Establish panel sequencing, key mapping, connector/data path, serial enumeration, and basic Wi-Fi viability. This retires the highest-risk unknown before architecture accumulates around an assumed board.
2. **Freeze the minimal normalized contract and golden fixtures.** Define full snapshot, source health, epoch/revision, Hello, FocusIntent, ActionResult, bounds, and forward-compatibility behavior. No upstream-specific fields. Host and firmware fixture decoders depend on this.
3. **Build an offline firmware projection on real hardware.** Feed synthetic fixture snapshots into cache/renderer; confirm three agent tiles, quota tile, stale/offline transitions, and exact identity captured by each physical key. This validates the product surface without transport or credentials.
4. **Build the smallest real transport vertical slice and run the transport gate.** Implement Hello/full snapshot/keypress/result/reconnect with a host simulator over USB first, then a narrow Wi-Fi spike using the same protocol. Measure on hardware and choose one v1 transport. Do not build hybrid arbitration unless measurements justify it.
5. **Integrate the inbox read path and focus action end to end.** Bootstrap/reconnect from herdr, consume the installed inbox order, publish top three, revalidate key identities, and call only `agent.focus`. This is the core value slice and should work on the selected physical transport before quota work expands scope.
6. **Add the Codex quota collector behind its adapter.** Implement app-server initialization, full read, sparse-update merge/refetch, normalization, timestamps, and independent failure state. The fourth tile protocol/UI already exists, so this cannot destabilize agent selection.
7. **Harden convergence and failure visibility.** Exercise host restart/new epoch, device reset, herdr restart, Codex logout, malformed frames, stale target, link loss, and ambiguous action timeout. Confirm each dependency fails within its boundary and recovers by full snapshot.
8. **Package the bridge as a herdr plugin lifecycle component.** Add startup/watchdog/configuration only after the executable core works against the actual device. Packaging should not hide transport or upstream failures.

The decisive early milestone is not “firmware compiles” or “bridge returns JSON”; it is a real board displaying a host-sent synthetic snapshot, producing an identity-bound physical keypress, surviving disconnect, and converging to a fresh full snapshot. The next decisive milestone is the same path focusing a real herdr agent without any change to settle/unread state.

## Scaling and Evolution Considerations

| Concern | One personal device (v1) | Several local devices | Future standalone bridge |
|---|---|---|---|
| Process topology | One host bridge process; in-memory derived state | Per-device sessions sharing one upstream projection | Keep adapters behind same normalized domain service |
| State distribution | Full snapshots | Full snapshot per device capability/profile | Add subscription fan-out before considering incremental patches |
| Action dedupe | Small bounded in-memory cache per boot id | Per-device bounded caches | Durable idempotency only if remote retries demand it |
| Security | Unix socket + physical serial, or authenticated trusted-LAN link | Device-specific credentials and revocation | TLS/private-network deployment, explicit enrollment and auditing |
| Transport | One selected link | Different adapters can coexist for different devices | Preserve transport-neutral protocol; avoid upstream exposure |
| Upstream load | One herdr subscription and one Codex collector | Still share collectors; do not create one per device | Rate-limit and cache collectors centrally |

The first likely bottleneck is not throughput; it is correctness during independent restarts and rapidly changing agent order. Full snapshots, epochs, stable identities, and explicit freshness address that directly. Only after multiple devices or remote deployments exist should durable device registration, TLS certificate rotation, or a standalone server become architectural requirements.

## Sources

All web sources retrieved 2026-08-16.

- [LILYGO, “T-Keyboard-S3-Pro Library Guide”](https://wiki.lilygo.cc/products/other/t-keyboard-s3-pro/library.html) — official board setup and APIs; confirms four host panels, five keys, sequential panel access, and Hardware CDC/JTAG settings. **Confidence: MEDIUM** (official primary source, current page; hardware behavior still requires physical verification).
- [LILYGO, official T-Keyboard-S3-Pro library repository](https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library) — board abstraction and examples. **Confidence: MEDIUM**.
- [Espressif, Arduino-ESP32 USB CDC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/usb_cdc.html) — CDC framing substrate and connection/RX/TX events. **Confidence: MEDIUM**.
- [Espressif, Arduino-ESP32 Wi-Fi API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/wifi.html) — station mode, event task warning, reconnect, connection state, and auto-reconnect. **Confidence: MEDIUM**.
- [herdr 0.8.0 documentation, “Socket API”](https://herdr.dev/docs/socket-api/) — local socket, `session.snapshot`, subscriptions, and public focus surface. **Confidence: MEDIUM**.
- [OpenAI Codex, `codex-app-server` protocol README](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md) — transport/lifecycle handshake and `account/rateLimits/read` / sparse update contract. **Confidence: MEDIUM**.
- Installed `herdr-agent-inbox` README and implementation at `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/`, inspected 2026-08-16 — authoritative evidence for this machine's rank tiers, daemon-owned settle/unread state, `agent.view.set`, reconnect behavior, and focus through `agent.focus`. **Confidence: MEDIUM** (local primary implementation, installation-specific).
- Preliminary note, `LILYGO T-Keyboard S3 Pro - physical Hermes AI inbox.md`, dated 2026-08-15 — used as leads and cross-check context only, not as authority. **Confidence: LOW**.

## Open Decisions Requiring Bring-Up

- Select USB serial or Wi-Fi for v1 after running the shared transport scenario on the connected device.
- Establish stable Linux device discovery/permissions for the actual USB identity.
- Lock the physical panel/key/orientation map and redraw budget.
- Determine whether production protocol and flash/debug logging can safely share native USB CDC.
- Consider hybrid only if measured failure recovery or placement needs justify its arbitration and security cost.

---
*Architecture research for: Herdr Agent Keypad*
*Researched: 2026-08-16*
