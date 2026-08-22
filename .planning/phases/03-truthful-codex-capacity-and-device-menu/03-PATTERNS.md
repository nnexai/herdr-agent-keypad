# Phase 3: Truthful Codex Capacity and Device Menu - Pattern Map

**Mapped:** 2026-08-20
**Files analyzed:** 31 likely Phase 3 implementation, test, fixture, and evidence files (including one new Codex collector module and one new host test module)
**Analogs found:** 30 / 31 (the Codex app-server collector has no exact in-repository analog; its lifecycle must compose existing bounded subprocess/socket patterns)

This map is for the Phase 3 implementation described by `03-CONTEXT.md`, `03-RESEARCH.md`, and approved `03-UI-SPEC.md`. The existing architecture has one permanent host bridge, one Phase 1 codec/session boundary, one firmware `AgentProjection`, one shared `RenderState`, four existing `ThemeRenderer` implementations, one `MenuController`, and one `SettingsStore`. Extend those seams. Do not add a second bridge daemon, second JSONL/frame parser, second renderer/composition stack, or second settings/persistence path.

## File Classification

| New / modified file | Role | Data flow | Closest analog | Match quality |
|---|---|---|---|---|
| `host/herdr_keypad/src/herdr_keypad/codex.py` (new, likely) | service / supervised provider collector | subprocess JSONL request-response + event stream | `host/herdr_keypad/src/herdr_keypad/herdr.py::HerdrEventStream` and `host/herdr_keypad/src/herdr_keypad/usb.py::UsbDeviceSession` | role-match; no Codex collector exists |
| `host/herdr_keypad/src/herdr_keypad/projection.py` | host model / normalization | transform + independent source clocks | `InboxProjection.refresh()` / `invalidate()` | exact role and immutable generation pattern |
| `host/herdr_keypad/src/herdr_keypad/bridge.py` | controller / bridge integration | event-driven multi-source aggregation + atomic publication | `PermanentBridge.bootstrap()`, `run_once()`, `_publish_snapshot()` | exact |
| `host/herdr_keypad/src/herdr_keypad/usb.py` | transport adapter | bounded request-response framed I/O | `UsbDeviceSession.request_v2()` / `poll()` | exact transport boundary |
| `host/herdr_keypad/src/herdr_keypad/__main__.py` | host entrypoint/config | request-response setup and long-running loop | `_bridge()` and smoke loop | exact |
| `host/herdr_keypad/tests/test_codex.py` (new, likely) | unit/contract test | fixture-driven normalization and failure state transitions | `test_projection.py`, `test_integration.py` | exact test style |
| `host/herdr_keypad/tests/test_projection.py` | host normalization test | deterministic transform / generation invariants | existing `InboxProjection` tests | exact |
| `host/herdr_keypad/tests/test_integration.py` | integration test | bridge + USB + event/focus behavior | existing `PermanentBridge` fake clients | exact |
| `host/herdr_keypad/tests/test_protocol.py` | protocol contract test | closed payload admission and 4096-byte bound | existing golden-vector tests | exact |
| `protocol/schema/v2.json` | authoritative wire schema | closed bounded message admission | existing v2 schema definitions | exact |
| `protocol/fixtures/v2-golden.json` | wire fixture | canonical encoded-frame fixtures | existing v2 golden vectors | exact |
| `tools/phase1_bringup/src/phase1_bringup/protocol.py` | host codec / validator | canonical JSON, digest, frame/session validation | existing v2 validator/session | exact; keep as sole host parser |
| `firmware/src/protocol/protocol.h` | native protocol API | bounded decode/encode/session | existing `FrameCodec` / `ProtocolSession` | exact |
| `firmware/src/protocol/protocol.cpp` | native codec implementation | streaming JSON admission and queue fencing | existing closed key-mask decoder | exact |
| `firmware/src/main.cpp` | firmware controller / dispatch | framed input to staged projection, direct keys, menu | `dispatchAdmission()`, `reportAgentKey()`, `pollMenu()` | exact |
| `firmware/src/app/agent_projection.h` | firmware model / generation store | staged complete snapshot -> committed render/binding | `Generation`, `stageSnapshot()`, `commitSnapshot()` | exact |
| `firmware/src/app/agent_projection.cpp` | firmware projection/controller | atomic composition + sequential panel flush | `commitSnapshot(BoardAdapter&)`, `renderMenu()` | exact |
| `firmware/src/ui/render_state.h` | shared view model | normalized host state -> all panel/LED consumers | `RenderState` and `Tile` fields | exact |
| `firmware/src/ui/theme.h` | renderer/menu contract | shared bounded view -> complete panel frame | `ThemeRenderer` interface and `MenuState` | exact |
| `firmware/src/ui/theme_common.h` | shared renderer vocabulary/utilities | transform/render helpers, palette, bounded copy | `styleFor()`, `fenceWord()`, `ellipsize()` | exact |
| `firmware/src/ui/theme_signal_edge.cpp` | renderer | Codex panel/menu composition | existing `composePanel4()` / `composeMenu()` | exact theme analog |
| `firmware/src/ui/theme_ledger.cpp` | renderer | Codex panel/menu composition | existing `composePanel4()` / `composeMenu()` | exact theme analog |
| `firmware/src/ui/theme_beacon.cpp` | renderer | Codex panel/menu composition | existing `composePanel4()` / `composeMenu()` | exact theme analog |
| `firmware/src/ui/theme_instrument.cpp` | renderer | Codex panel/menu composition | existing `composePanel4()` / `composeMenu()` | exact theme analog |
| `firmware/src/app/menu_controller.h` | input state machine | encoder event -> bounded menu state | `Mode::{Closed,RowSelect,ValueCycle}` | exact but must extend rows/pages/timeout |
| `firmware/src/app/menu_controller.cpp` | input state machine | clamped rotation/click/confirm/revert | `click()`, `rotate()`, `cancel()`, `confirmValue()` | exact |
| `firmware/src/app/settings_store.h` | device persistence API | confirmed values -> NVS record | `load()` / `confirm()` contract | exact but schema v2/brightness extension |
| `firmware/src/app/settings_store.cpp` | device persistence implementation | NVS read/validate/atomic confirmed write | version-marker-last replacement | exact |
| `firmware/src/board/board_adapter.h` | hardware seam | local brightness command -> board library | `setBrightness()` | exact seam; likely no new abstraction |
| `firmware/src/board/board_adapter.cpp` | hardware implementation | bounded local hardware call | `BoardAdapter::setBrightness()` | exact seam; do not bypass |
| `test/test_agent_projection/test_main.cpp` | native behavioral test | render, generation, menu, settings, direct-input contracts | existing named tests in sections 02/Plan 02 | exact |
| `tools/phase1_bringup/src/phase1_bringup/phase22_smoke.py` (or a Phase 3 sibling using its writer) | physical evidence driver | machine facts + explicit operator sightings | `SmokeEvidence.skeleton()`, `DeviceSession`, `atomic_write_pair` | exact evidence pattern |
| `tools/capture_panel.py` | physical framebuffer capture utility | bounded probe request -> RGB565/PPM artifact | `capture_panel()` / `streamCapturedPanel()` path | exact |
| `artifacts/phase3/...` (new evidence outputs) | evidence artifact | immutable physical observations + hashes | `artifacts/phase2/*` and `SmokeEvidence.write()` | exact artifact convention |

### Files deliberately not added

- No `host/.../daemon.py`, `host/.../server.py`, or second bridge executable: `PermanentBridge` remains the one host authority.
- No `protocol/codex_parser.py` or firmware-side app-server parser: only the new host collector interprets Codex JSONL; device admission remains the existing Phase 1 codec/session.
- No `firmware/src/ui/codex_renderer.*` or `menu_renderer.*`: panel 4 and all menu pages remain methods on the four existing theme renderers.
- No `firmware/src/app/brightness_store.*`: brightness belongs in `SettingsStore` and is applied through `BoardAdapter::setBrightness()`.
- No raw panel/GPIO path: `BoardAdapter` remains the only hardware boundary.

## Pattern Assignments

### `host/herdr_keypad/src/herdr_keypad/codex.py` (new collector, service / subprocess JSONL)

**Closest analogs:**
- `host/herdr_keypad/src/herdr_keypad/herdr.py::HerdrEventStream` (lines 132-306): one owned stream, bounded line reads, deadline-based polling, explicit push/poll mode and failure reason.
- `host/herdr_keypad/src/herdr_keypad/usb.py::UsbDeviceSession` (lines 119-164, 203-235): one session owner, strict sequence/session checks, bounded request response, close-on-I/O failure.
- `tools/phase1_bringup/src/phase1_bringup/serial_link.py::_open_and_hello()` and `reconnect_exact()` (lines 196-243): supervised candidate/session lifecycle and fail-closed recovery.

**Required lifecycle pattern:** spawn exactly one `/home/linuxbrew/.linuxbrew/bin/codex app-server --stdio` child per collector session using `asyncio.create_subprocess_exec()` (the standard stack in `03-RESEARCH.md`). Send `initialize`, then `initialized`, then `account/read` and `account/rateLimits/read`; never send requests before handshake. Keep stdout JSONL separate from stderr. Bound every line and request deadline; classify child exit, malformed JSONL, request timeout, and transport/read failure as `CODEX OFFLINE`, not auth failure.

**Concrete supervision analog (`HerdrEventStream`):**
```python
# herdr.py:212-225, 251-305 — bounded reads and explicit mode/failure
line = self._readline(deadline=self.clock() + 0.001)
if line is None:
    self.reason = "timeout_or_eof_before_subscribe_ack"
    self.mode = "poll"
    self._close_socket()
    return self.mode
try:
    event = self._parse_event(line)
except HerdrError:
    self._close_socket()
    self.mode = "poll"
    self.reason = "stream_read_failure"
    return None
```

**Concrete request/session analog (`UsbDeviceSession`):**
```python
# usb.py:119-164 — validate before write; correlate response; close on I/O failure
validate_v2_payload(frame_type, payload_dict)
sequence = session.next_seq + 1
link.write(v1_protocol.encode_v2_frame(frame))
...
if response["type"] in allowed_set and response["reply_to"] == sequence:
    return dict(response["payload"])
raise UsbSessionError("timeout", ...)
```

**Codex-specific rules from research/context:**
- Full `account/rateLimits/read` is the only baseline that can establish current capacity; preserve absent/null primary/secondary windows as unavailable.
- `account/rateLimits/updated` is sparse. Merge only fields present into a known full baseline; omitted fields remain unchanged. If no baseline exists or shape is ambiguous, refetch and do not advance observation age.
- `account/read` with `account: null` and `requiresOpenaiAuth: true`, explicit login/auth JSON-RPC error, or explicit unauthorized response is `AUTH REQUIRED`. Do not infer this from timeout/process exit.
- Never read or serialize auth files, tokens, email, `codexHome`, host paths, raw errors, prompts, or transcripts. Keep only bounded normalized fields and one allowlisted redacted error code.
- Poll every 5 minutes; stale after 15 minutes without valid full read or valid sparse merge. On account/auth change clear cached capacity immediately and require a new full read.

**No exact analog found:** The repository contains no subprocess supervisor or Codex schema implementation. Do not copy upstream response objects as a second protocol model; use the installed binary's generated stable schema during implementation and normalize into the project-owned dataclass/view.

### `host/herdr_keypad/src/herdr_keypad/projection.py` (host normalization, transform + independent clocks)

**Analog:** `InboxProjection` and `ProjectionSnapshot` (`projection.py:24-58,106-324`).

**Data model pattern:** add normalized Codex data to the existing complete projection rather than creating a parallel published snapshot. Preserve immutable dataclasses, bounded fields, explicit source status, and bridge-owned revision.

```python
# projection.py:279-300 — normalize, derive a stable key, increment revision only on material change
entries = self._project_entries(list(rows), labels)
projection_key = (entries, source_status, self.plugin_revision, self.schema_version)
if self.current is not None and projection_key == self._last_projection_key:
    return self.current
self.snapshot_revision += 1
snapshot = ProjectionSnapshot(..., source_status, entries, ...)
self.current = snapshot
```

```python
# projection.py:312-324 — preserve last identity but fence actionability on source failure
entries = tuple(
    ProjectedEntry(..., reason, ..., identity, stale=True)
    if entry.identity is not None else ProjectedEntry.empty(entry.slot, reason)
    for entry in self._last_entries
)
self.current = ProjectionSnapshot(..., reason, entries, ...)
```

**Apply to Codex:** retain separate `herdr_observed_at`, `codex_observed_at`, and `link_observed_at`; a Codex failure must not erase or revise agent entries. Build the complete host projection off to the side and publish one incremented host generation. Keep source statuses distinct even if the wire payload uses compact enums. Cached Codex values may survive stale/offline veils; auth change clears them.

**Normalization helpers to copy:** `_text()` / `_opaque()` / `_uint()` (`projection.py:62-80`) reject non-ASCII, controls, empty required values, and unbounded integers. `_repo_basename()` (`projection.py:94-103`) demonstrates stripping path-like data before a device-facing discriminator. Codex reset/age/plan/error text must use equivalent allowlisted bounded formatting, never arbitrary upstream strings.

### `host/herdr_keypad/src/herdr_keypad/bridge.py` (one bridge integration)

**Analog:** `PermanentBridge` (`bridge.py:537-862`).

**Atomic publication:** `_publish_snapshot()` (`bridge.py:629-650`) clears pending focus before publishing, checks the device ACK epoch/revision, and marks ready only after a complete current projection is accepted. Extend its projection assembler to include normalized Codex/diagnostic state in the same snapshot; do not publish a second Codex frame or maintain a second USB session.

**Independent source/event pattern:** `bootstrap()` (`bridge.py:659-696`) establishes Herdr and USB once; `_consume_events()` / `_refresh_if_dirty()` (`bridge.py:782-848`) coalesces invalidations, prevents overlapping refreshes, and preserves focus ordering. Add Codex polling/notification work to this owner with its own timestamp/status; do not let Codex retries block Herdr updates or change direct focus bindings.

**Error pattern:** `_mark_unavailable()` (`bridge.py:616-627`) clears actionable focus and publishes a bounded source failure. Phase 3 must refine this for independent `host-offline` vs `codex-offline` while preserving agent source state and redacting error details. `_wire_focus_result()` (`bridge.py:423-455`) is the model for converting internal outcomes to a closed wire vocabulary.

**Credential/diagnostic boundary:** `write_acceptance_evidence()` (`bridge.py:865-891`) records bounded hashes and generation facts only. Extend diagnostics with firmware/protocol/bridge versions and six-character suffixes; never include account identity, paths, raw process output, prompts, or credentials.

### `host/herdr_keypad/src/herdr_keypad/usb.py` and `__main__.py` (transport/config)

`UsbDeviceSession.connect()` (`usb.py:81-108`) is the exact paired USB identity path. Keep link freshness separate from Herdr and Codex freshness. `request_v2()` (`usb.py:119-164`) remains the sole host device request path after schema extension; `poll()` (`usb.py:203-226`) remains the sole inbound line reader. `_bridge()` (`__main__.py:29-33`) should construct the one `PermanentBridge` with the one projection and collector, not start a second daemon.

### `protocol/schema/v2.json`, `tools/.../protocol.py`, and firmware `protocol.{h,cpp}` (wire schema / validation)

**Authoritative schema analog:** `protocol/schema/v2.json:1-101` is closed-envelope v2 with `additionalProperties:false`, explicit `oneOf` payloads, and the `x-max-encoded-line-bytes-including-lf:4096` contract. Extend the existing `agent_snapshot` payload definition (or its frozen successor chosen by planning) with normalized Codex and bounded diagnostics, then update every required field in host and native validators together. Keep sequence, digest, exact field sets, and rejection vocabulary closed.

**Host validator analog:** `tools/phase1_bringup/src/phase1_bringup/protocol.py:263-325` rejects unknown fields before interpretation, enforces exactly three agents, distinguishes empty identity from occupied identity, and validates bounded ASCII/uints. `new_v2_frame()` and `encode_v2_frame()` (`protocol.py:328-378`) validate before canonical sorted-key encoding and reject lines over 4096 bytes including LF. Extend this function; do not create `codex_protocol.py` or a second JSON parser.

**Native validator analog:** `firmware/src/protocol/protocol.h:8-12,43-103` keeps fixed buffers and one `ProtocolSession`; `firmware/src/protocol/protocol.cpp` uses explicit payload key masks and bounded cursor parsing (see current snapshot keys around lines 397-442). Add the new closed fields and statuses to this decoder using fixed buffers and presence bits. Reject unknown/missing/oversized fields before staging. No app-server JSON reaches firmware.

**Wire rules:** send bounded integers/flags/enums/ages/reset strings only; preserve missing/null fields with explicit presence/unknown state; never encode host paths or raw upstream objects. Validate encoded size before allocation or write. Keep `ProtocolSession` as the sole admission/ordering/queue boundary and preserve its 16-item capacity/4096-byte bound.

### `protocol/fixtures/v2-golden.json`, host protocol tests, and native tests (fixtures)

**Golden-vector pattern:** `protocol/fixtures/v2-golden.json:1-8` stores canonical complete JSON lines and expected schema/reason/dispatch. `host/herdr_keypad/tests/test_protocol.py:21-39` runs each vector through the host classifier/session; `test_protocol.py:41-67` verifies closed fields, generation fencing, and encoded-size bounds. Add vectors for current/unavailable, sparse merge, stale/offline/auth/host-offline, null windows, reached-limit unknown/true, diagnostic redaction, unknown field, and near/over 4096-byte frames.

**Native fixture pattern:** `test/test_agent_projection/test_main.cpp:650-734` uses each real renderer and inspects literal vocabulary and primitive logs rather than a second renderer. Keep fixtures deterministic and bounded; test behavior (null does not become `0%`, omitted sparse fields do not clear known values, auth clears cache, stale/offline retains values behind a veil), not source text.

### `firmware/src/app/agent_projection.h/.cpp` (generation state and panel-4 dispatch)

**Analog:** `AgentProjection::Generation`, `stageSnapshot()`, `commitSnapshot(BoardAdapter&)`, `renderState()`, and `renderMenu()` (`agent_projection.h:47-88,112-144`; `agent_projection.cpp:148-255,335-356,404-420`).

**Stage/commit pattern:** `stageSnapshot()` validates the complete bounded object and rejects old revisions (`agent_projection.cpp:148-203`). `commitSnapshot(BoardAdapter&)` disables bindings, composes/flushed all panels sequentially, falls back to SYNC on failure, then activates bindings only after all complete frames (`agent_projection.cpp:232-255`). Add Codex/diagnostic fields to staged and committed generation state and pass one immutable `RenderState` to panel 4; never mutate a live panel halfway through a snapshot.

**Render/flush pattern:** `renderTile()` builds a local `RenderState`, invokes the selected `ThemeRenderer`, and pushes one complete sprite (`agent_projection.cpp:274-292`). `renderMenu()` targets only `displayAt(3)` and chooses `composeMenu()` vs `composePanel4()` (`agent_projection.cpp:335-341`). Preserve this single shared PSRAM composition sprite and sequential `BoardAdapter` flush. A menu open/close swaps only panel 4; panels 1-3 and bindings stay untouched.

**Capture pattern:** `capturePanel()` (`agent_projection.cpp:358-379`) already supports deterministic panel scenes and routes through the selected existing theme. Extend this fixture seam for Codex states/menu pages instead of adding another rendering stack.

### `firmware/src/ui/render_state.h` and `theme.h` (shared view/menu contract)

`RenderState` (`render_state.h:5-45`) is explicitly the shared presentation state for all themes and LED grammar. Extend it with one bounded Codex view and bounded diagnostic/menu values, including presence/unknown flags, observation age, reset text, reached-limit state, Codex source state, link/Herdr state, sync/Codex ages, error code, versions, and suffixes. Keep strings as caller-owned fixed storage or fixed arrays; no per-frame allocation.

`ThemeRenderer` (`theme.h:20-42`) is the only renderer interface. Keep `composePanel4()` and `composeMenu()` on this interface; do not add `CodexRenderer`, `MenuRenderer`, or a parallel sprite. `MenuState` (`theme.h:8-18`) is currently only theme/LED candidates; extend this same object for six root rows, brightness preview, health/about pages, viewport/cursor, and timeout-related presentation. Renderer methods remain pure composition; projection owns flushing and controller owns transitions/persistence.

### Four panel-4 renderers (all must change in place)

All existing methods currently render deliberate `N/A`/`UNAVAILABLE` placeholders. The exact analogs and geometry are:

#### `firmware/src/ui/theme_signal_edge.cpp::SignalEdgeTheme::composePanel4()` / `composeMenu()`

Current placeholder/menu is `theme_signal_edge.cpp:204-238`: left rail, `CODEX` at x=16, two hatched gauges, bottom state band; `drawHatchedGauge()` is lines 123-130 and `drawMenuRow()` lines 148-159. Copy its rail, hatch, right alignment, selected fill, and bottom-band takeover. Replace placeholder coordinates with the UI contract: title glyph box at `(16,4)`, primary/secondary baselines 30/50 and gauges at y=32/52, reset/age baselines 70/86, state baseline 114; menu rows baselines 30/54/78, six-row viewport, and footer hints.

#### `firmware/src/ui/theme_ledger.cpp::LedgerTheme::composePanel4()` / `composeMenu()`

Current placeholder/menu is `theme_ledger.cpp:150-183`: ruled ledger rows, right-side `N/A`, header divider, compact cursor/value treatment. Copy `drawStateUnderline()` (`lines 21-41`) for non-color state encoding and preserve right-aligned values. Implement the UI contract's title anchor `(6,4)`, baselines 30/50/70/86/114, stale/offline/auth header-band takeover, and warning-row inversion for `LIMIT` without erasing cached numbers.

#### `firmware/src/ui/theme_beacon.cpp::BeaconTheme::composePanel4()` / `composeMenu()`

Current placeholder/menu is `theme_beacon.cpp:223-258`: radial/dithered field vocabulary, centered words, and left cursor. Copy `drawField()` (`lines 39-64`) and existing centered geometry. Implement stepped dual-ring panel 4 centered `(64,40)`, primary/secondary rows in bands 20..39/40..59, centered reset/age/state lines at 70/86/114, crossed/hatched/offline rings, and centered six-row menu words with the cursor at x=4.

#### `firmware/src/ui/theme_instrument.cpp::InstrumentTheme::composePanel4()` / `composeMenu()`

Current placeholder/menu is `theme_instrument.cpp:223-247`; `drawBezelTicks()` is lines 127-136 and `drawUsageGauge()` lines 138-149. Copy bezel ticks, track geometry, and 75% warning mark. Implement centered `CODEX` at y=4, tracks x=8/y=32 and x=8/y=52, reset/age/state baselines 70/86/114, and `LIMIT` warning through red ticks/75% marks. Keep menu centered with bezel and six-row viewport.

**Shared renderer rules:** `theme_common.h:14-29,36-80,102-129` is the palette/state/fence vocabulary and bounded `ellipsize()`/alignment helper. Extend shared helpers for Codex state precedence rather than implementing provider semantics independently in each theme. Never use color alone: every state has literal ASCII (`CURRENT`, `STALE`, `UNAVAILABLE`, `AUTH REQUIRED`, `CODEX OFFLINE`, `HOST OFFLINE`, `LIMIT`) and geometry.

**State precedence from UI contract:** `HOST OFFLINE > CODEX OFFLINE > AUTH REQUIRED > STALE > CURRENT/UNAVAILABLE`. `LIMIT` is layered and never replaces a dominant failure veil. Missing/null percentages are exactly `N/A`, never `0%`; missing/null reached state produces no positive `OK`/`CLEAR` claim; reset is `RESET N/A` unless a supplied future primary/secondary reset exists.

### `firmware/src/app/menu_controller.h/.cpp` (menu state and direct interaction)

**Analog:** current state machine (`menu_controller.h:8-40`; `menu_controller.cpp:13-114`).

`resetFromStore()` copies confirmed values into stored and candidate fields without writing (`menu_controller.cpp:13-22`). `close()` restores candidates to stored values and marks the panel dirty (`lines 24-32`). `confirmValue()` writes only through `SettingsStore::confirm()` and updates stored values after success (`lines 41-54`). `click()` has explicit closed/open/edit/confirm transitions (`lines 57-75`). `rotate()` clamps root navigation and cycles candidates (`lines 78-101`), while `cancel()` reverts (`lines 104-108`). Preserve these explicit transitions; replace the two-row cursor bounds and modulo candidate handling with the exact flat six-row root and page modes.

**Phase 3 state contract:** root rows are `THEME`, `LEDS`, `BRIGHTNESS`, `HEALTH`, `ABOUT`, `CLOSE`, cursor clamped (never wrapped), three visible rows, 30-second encoder-only inactivity timeout. Click opens, enters selected value/brightness/read-only page, confirms edits, returns from HEALTH/ABOUT, or closes. Theme/LED previews apply candidate rendering/LED preview but persist only on click. Brightness preview starts at stored 10..100 value, changes in 10% steps and calls `BoardAdapter::setBrightness()` live, confirms locally through `SettingsStore`, and reverts through the same board seam on close/timeout. Health/Codex refreshes and direct keys do not reset timeout.

### `firmware/src/main.cpp` (direct key precedence and integration)

**Direct-key analog:** `reportAgentKey()` (`main.cpp:490-502`) consumes logical keys 0..2 and captures immutable focus intents before other runtime work. The loop calls it immediately after the single `board.update()` (`main.cpp:577-596`) and before `readFrames()`, projection tick, and `pollMenu()`.

**Required precedence:** retain this order. Keys 1-3 must be consumed and dispatched by `reportAgentKey()` regardless of menu mode, submenu, HEALTH, or ABOUT. `pollMenu()` (`main.cpp:547-551`) may consume only encoder click logical key 4 and encoder delta; it must never inspect or route keys 0..2. Direct key presses do not move menu cursor, enter rows, or reset inactivity. A menu-open LED cue may be driven from `menuController.open()` as currently done (`main.cpp:597-599`).

**Boot brightness migration:** setup currently loads settings and then hardcodes `board.setBrightness(80)` (`main.cpp:555-573`). Replace only that hardware value with `settingsStore.brightness()` (which falls back to 80 in memory), leaving boot read-only. Do not change generation IDs, inbox order, focus bindings, LED semantic state, or protocol admission on a local brightness action.

**Menu refresh analog:** `refreshMenuPresentation()` (`main.cpp:528-545`) applies confirmed theme to all agent tiles through `redrawTiles()`, selects preview theme for panel 4, sets LED grammar, then calls `renderMenu()`. Extend it for all menu pages and brightness preview; keep `redrawTiles()` as the only complete agent-panel theme transition and keep panel 4 as the only menu surface.

### `firmware/src/app/settings_store.h/.cpp` (brightness persistence migration)

**Analog:** schema-v1 NVS implementation (`settings_store.h:7-32`; `settings_store.cpp:5-47`).

`load()` resets in-memory defaults, opens Preferences read-only, checks all keys/version/ranges, and returns false without writing defaults (`settings_store.cpp:12-29`). `confirm()` validates enums, writes an invalid version marker first, replaces all values, writes the schema marker last, and updates memory only after all writes succeed (`lines 32-47`). Native tests prove fresh fallback, corrupt version/enum no-write, and failed replacement never loads a hybrid (`test_main.cpp:464-544`).

**Phase 3 extension:** keep v1 theme/LED keys readable unchanged; missing/invalid brightness is 80% in memory; boot does not write migration data. Use schema v2 only on explicit confirmed Phase 3 setting confirmation, preserving existing values. Brightness is a bounded 10..100 value and must be written in the same atomic/version-marker-last confirmed record. No host data, bindings, identities, snapshots, or credentials belong in NVS. Keep `BoardAdapter::setBrightness()` (`board_adapter.cpp:79-82`) as the only hardware application seam.

### `firmware/src/board/board_adapter.h/.cpp` (brightness hardware seam; no second path)

`BoardAdapter` explicitly says it is the only firmware hardware boundary (`board_adapter.h:9-11`). `setBrightness()` delegates directly to the official board abstraction (`board_adapter.cpp:79-82`); `clearDisplays()` proves the required sequential panel handling (`lines 92-100`). Reuse this method from boot and menu preview/revert. Do not add raw panel writes, NVS calls to board code, or a second brightness API.

### Physical evidence: `phase22_smoke.py`, `capture_panel.py`, and `artifacts/phase3`

**Evidence analog:** `tools/phase1_bringup/src/phase1_bringup/phase22_smoke.py:95-150` separates machine facts from `HumanSighting`, builds a complete pending skeleton, computes status only when every combination/sighting is explicitly `Y`, and writes content plus SHA-256 through `atomic_write_pair()`. Extend this artifact pattern for Phase 3 coverage rather than claiming physical success from firmware logs.

Required Phase 3 evidence rows should cover:
- Codex current values, null/missing values, stale veil/age, auth-required cache clearing, Codex-offline cached values, host-offline fence, nearest reset and reached-limit precedence across all four themes.
- Six-row menu viewport/clamped cursor, theme/LED preview/revert, brightness 10..100 live ladder, explicit confirmation, timeout/close revert, boot v1 fallback/no write-back and schema-v2 post-confirm persistence.
- Direct key 1-3 focus while root/edit/HEALTH/ABOUT is open; no cursor/timer interference.
- Independent link/Herdr/Codex health and bounded ABOUT/HEALTH copy; no account identity, paths, prompts, transcripts, or raw errors.
- No black flash/mixed generation and panel-4-only menu replacement.

`tools/capture_panel.py:34-107` is the direct framebuffer utility: bounded scene/theme map, one `probe` request, exact capture marker, fixed RGB565 byte count, PPM plus raw sidecar. Extend its scene map or add Phase 3 scene names, but keep the existing probe/transport path and one-panel capture. Store physical outputs under `artifacts/phase3/...` with hashes and explicit pending/unavailable outcomes; do not turn a pending skeleton into a pass without operator sightings.

## Shared Patterns

### One host authority and independent source clocks

**Sources:** `PermanentBridge` (`bridge.py:537-862`), `InboxProjection` (`projection.py:106-324`), and `03-RESEARCH.md` Pattern 2.

- Herdr remains the inbox/order/focus authority.
- Codex collector owns provider auth interpretation and observation timestamp.
- USB link state is independent of Herdr and Codex.
- Build one complete normalized generation, publish atomically, and fence only the affected source semantics.
- A brightness write is device-local and cannot increment host snapshot generation or alter bindings.

### Bounded, redacted values

**Sources:** `bridge.py:_bounded_text()/_opaque()`, `projection.py:_text()/_opaque()`, `protocol.py:238-260`, `theme_common.h:102-129`, and `03-UI-SPEC.md:27-31,80`.

All device-facing strings are printable bounded ASCII with fixed capacities and `...` as the only truncation marker. Use enum/status/error codes, percentages, reset text, ages, versions, and suffixes only. Never forward account identity, credentials, host paths, raw errors, prompts, transcripts, or app-server metadata.

### Complete-frame composition and flush

**Sources:** `AgentProjection::commitSnapshot(BoardAdapter&)` (`agent_projection.cpp:232-255`), `renderTile()` (`274-292`), `renderMenu()` (`335-341`), and `03-UI-SPEC.md:37-44,267-278`.

Compose complete old/new frames into the existing shared 128x128 RGB565 sprite, flush one panel at a time through `BoardAdapter`, and enable bindings only after the complete generation is visible. Menu open/close is a complete panel-4 replacement; no second display abstraction and no mixed frame.

### Direct input precedence

**Sources:** `main.cpp:490-502,577-599` and `03-UI-SPEC.md:31-33,257-263`.

`reportAgentKey()` remains before USB/menu polling. Menu state is never modal for keys 1-3. Encoder click/delta are the only menu inputs; no long-press/double-click grammar.

### Persistence only after explicit confirmation

**Sources:** `SettingsStore::load()/confirm()` (`settings_store.cpp:12-47`), `MenuController::confirmValue()/close()` (`menu_controller.cpp:24-54`), and native tests (`test_main.cpp:464-544,951-983`).

Read/fallback is memory-only. Confirmed writes use version-marker-last atomic replacement. Unconfirmed preview must be reversible and never written; brightness remains usable offline.

## No Analog Found

| File / responsibility | Classification | Gap | Planner guidance |
|---|---|---|---|
| `host/herdr_keypad/src/herdr_keypad/codex.py` | supervised provider service, subprocess JSONL | No existing subprocess-owned provider collector | Compose `HerdrEventStream` deadline/parse/error pattern with `UsbDeviceSession` session/close/correlation pattern; keep all Codex interpretation host-only and test with deterministic fake JSONL child |

All other likely Phase 3 files have a direct role/data-flow analog above. `BoardAdapter` is an existing hardware seam and should normally remain unchanged; it is listed to make the no-second-brightness-path constraint explicit.

## Metadata

**Analog search scope:** `host/herdr_keypad/src/herdr_keypad`, `host/herdr_keypad/tests`, `firmware/src/app`, `firmware/src/protocol`, `firmware/src/ui`, `firmware/src/board`, `firmware/src/main.cpp`, `protocol/schema`, `protocol/fixtures`, `tools/phase1_bringup/src/phase1_bringup`, `tools/capture_panel.py`, `test/test_agent_projection`, and `artifacts/phase1`/`artifacts/phase2`.
**Strong analogs scanned:** `PermanentBridge`, `InboxProjection`, `UsbDeviceSession`, `HerdrEventStream`, `FrameCodec`/`ProtocolSession`, `AgentProjection`, `MenuController`, `SettingsStore`, all four theme renderers, `BoardAdapter`, golden-vector tests, native firmware tests, `phase22_smoke`, and `capture_panel`.
**Pattern extraction date:** 2026-08-20
