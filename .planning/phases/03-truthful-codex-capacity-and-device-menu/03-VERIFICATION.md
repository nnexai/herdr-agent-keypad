---
phase: 03-truthful-codex-capacity-and-device-menu
verified: 2026-08-21T03:32:36Z
status: passed
score: 62/62 must-haves verified
behavior_unverified: 0
overrides_applied: 0
verification_scope:
  roadmap_success_criteria: 5
  plan_truths: 57
  requirements: 10
  validation_commands: skipped_by_request
---

# Phase 03: Truthful Codex Capacity and Device Menu — Verification Report

**Phase Goal:** The user can trust the dedicated Codex tile and inspect device health or adjust brightness without disrupting direct agent selection.

**Verified:** 2026-08-21T03:32:36Z  
**Status:** passed  
**Re-verification:** No — initial verification

> **Method.** This is a goal-backward audit of current production source, registered production-path tests, the installed-Codex tracer, current exact-device evidence, capture manifest, and physical rows. SUMMARY claims were not accepted as proof. At the user's direction, no build, test, smoke, checksum, formatter, linter, or validator command was run during this verification. Thus, this report does **not** claim a fresh command result; it records the static evidence and previously captured exact-device observations that are present in the repository.

## User Flow Coverage

The ROADMAP phase is marked MVP. Its outcome phrasing is represented by the Plan 01 user-flow contract: *“As a user of the delivered keypad, I want to trust the dedicated Codex tile and inspect device health or adjust brightness, so that Codex capacity and secondary controls never disrupt direct agent selection.”*

| Step | Expected user-visible result | Current code and exact-device evidence | Status |
|---|---|---|---|
| Read capacity | Panel 4 is read-only and shows 5H/WEEK values only when supplied, with reset, age, source state, and LIMIT semantics. | `CodexCollector` normalizes only top-level `rateLimits` (`codex.py:285-303`); the four `composePanel4()` implementations consume the committed `RenderState::codex`. The installed tracer records current `secondary: 41`, `primary: null`, `RESET WEEK 6D0H49M`, and unknown reached limit; physical `source-labels-remain-legible` is `Y`. | ✓ VERIFIED |
| Inspect health | Encoder opens a secondary panel-4 menu; HEALTH exposes independent link/Herdr/Codex states and ages, while ABOUT exposes only bounded versions and suffixes. | `MenuController` has HEALTH/ABOUT modes (`menu_controller.cpp:95-114`); `PermanentBridge::_diagnostics()` builds the closed fields (`bridge.py:695-723`); all themes compose six fixed HEALTH/ABOUT rows. Physical direct-key rows confirm HEALTH and ABOUT remain open and non-modal. | ✓ VERIFIED |
| Adjust brightness | The user previews 10–100% locally, confirms explicitly, or receives a revert on close/timeout; confirmed brightness survives reboot. | `MenuController::rotate/close/expire()` emits local brightness intents and reverts (`menu_controller.cpp:40-52,123-174`); `SettingsStore::confirm()` writes only theme, grammar, and brightness marker-last (`settings_store.cpp:82-104`). Eight explicit physical brightness/LED/persistence rows are `Y`, including reboot restore. | ✓ VERIFIED |
| Keep selection direct | Any displayed agent key retains its exact focus path while the menu is open; it cannot move the menu or prolong its deadline. | `main.cpp:634-643` captures one frame after `board.update()`, routes agent slots before encoder actions, then dispatches focus through `reportAgentKey()`. `ProductInputRouter` never sends an agent action to the menu (`product_input_router.cpp:11-25`). Four physical root/brightness/HEALTH/ABOUT rows are `Y`. | ✓ VERIFIED |
| Outcome | Codex capacity and secondary controls do not disrupt direct selection. | Current source uses a closed host → protocol → staged generation path for data, and an isolated device-only menu/NVS path for brightness; exact-device rows record direct focus in each required menu context. | ✓ VERIFIED |

## Goal Achievement

### ROADMAP Success Criteria

| # | Success criterion | Evidence | Status |
|---:|---|---|---|
| 1 | Fourth display is read-only and conditionally shows both windows, nearest reset, and reached-limit state. | `codex.py:193-243,263-303` preserves 300-minute/10,080-minute slot meaning and selects the nearest future reset; schema requires closed Codex fields; `theme_common.h:171-208` maps absent values to `N/A`; all four panel-4 renderers consume that one view. The installed trace is a real current weekly-only shape (`secondary: 41`, `primary: null`), while registered renderer tests cover populated two-window and reached cases. | ✓ VERIFIED |
| 2 | Null/missing values remain unavailable; current/stale/unavailable/authentication-failed/host-offline and age are distinct. | `CodexCollector::view()` uses a separate observation clock and 900-second stale threshold (`codex.py:364-387`); auth classification admits only structured evidence (`313-322`); the protocol enum is closed (`protocol/schema/v2.json:72-84`); four renderers use literal state words and geometric fences. Physical source-label row is explicit `Y`. | ✓ VERIFIED |
| 3 | Encoder opens/closes a secondary menu while agent keys stay direct and non-modal. | `MenuController::click()` is the only open/enter/confirm/back/close grammar (`76-121`); production routing orders all agent actions before click/rotation; native production-router tests are registered at `test_main.cpp:1666-1828`; four exact-device key-context rows are `Y`. | ✓ VERIFIED |
| 4 | Menu independently reports source health and ages plus bounded troubleshooting/version data without sensitive host/provider content. | `_diagnostics()` emits only closed link, Herdr, Codex, age, version, suffix, and error-code fields (`bridge.py:695-723`); v2 schema rejects extra members; four theme menu composers render fixed HEALTH/ABOUT layouts. Native diagnostic test injects email/path/raw-error fields and proves they do not render (`test_main.cpp:2164-2234`). | ✓ VERIFIED |
| 5 | Brightness changes persist without affecting order, target identity, or focus semantics. | Brightness is local `BoardAdapter::setBrightness()` output and NVS-only setting; no host brightness protocol action exists. `ProductInputRouter` and menu tests cover candidate/revert/confirm/timeout; `settings_store.cpp` stores only `ver`, `theme`, `ledgram`, and `bright`. Physical ladder, zero rejection, close/timeout reverts, confirmation, and reboot rows are all explicit `Y`. | ✓ VERIFIED |

### Plan Must-Have Audit

All 57 plan-frontmatter truths were traced; the grouped rows below retain each plan's truth count rather than treating file existence as proof.

| Plan | Truths | Artifact, wiring, and behavior evidence | Status |
|---|---:|---|---|
| 03-01 | 9/9 | The sole host validator/schema, guarded `run-exclusive` owner, `CodexCollector`, `PermanentBridge`, staged firmware dispatch, Signal Edge, and trace artifact form one path. The trace records the actual four-step installed handshake, 961 ms of a 3000 ms deadline, redaction pass, bounded child-exit shape, fresh paired hello, ACK, and same binary SHA as the final deployment. Raw credential/provider objects are absent from the normalized artifact. | ✓ VERIFIED |
| 03-02 | 7/7 | `CodexCollector` requires a full baseline before sparse publication (`434-516`), preserves omissions, handles null/zero separately, coalesces refetches, applies 300/900-second timing, and clears account state. `PermanentBridge` joins independent clocks while `preserve_focus=True` protects Codex-only publications (`bridge.py:739-780`). | ✓ VERIFIED |
| 03-03 | 5/5 | `protocol/schema/v2.json` closes `agent_snapshot` over agents, Codex, and diagnostics; the host validator and native parser reject unknown/duplicate/oversize/sensitive payloads before staged state. `AgentProjection` owns the committed shared `RenderState`; registered protocol and rejection-preservation tests cover this boundary. | ✓ VERIFIED |
| 03-04 | 5/5 | `theme_common.h` centralizes N/A, reset, age, source precedence, and LIMIT helpers. Signal Edge, Ledger, Beacon, and Instrument each consume `RenderState::codex`; registered primitive-log cases cover null/zero/partial/populated, state precedence, long text, safe bounds, and Codex-only redraw invariants. | ✓ VERIFIED |
| 03-05 | 4/4 | Production `main.cpp` passes committed `agentProjection.renderState(now)` to `LedEngine`; every grammar consumes the committed view and `LedEvents` remains transient-only. Registered native cases cover current/absent/LIMIT/failure/focus/menu/all-off behavior. Panel text remains the semantic authority. | ✓ VERIFIED |
| 03-06 | 7/7 | The menu root has exactly six clamped entries; the controller accepts only approved encoder semantics and keeps a 30-second encoder-only deadline. The fixed-capacity router is compiled production code, not a source-text assertion. Brightness is 10–100 only, previews locally, and `SettingsStore` reads v1 without boot writes then confirms a marker-last v2 record. | ✓ VERIFIED |
| 03-07 | 5/5 | `ThemeRenderer::composeMenu()` remains the sole all-theme menu seam. HEALTH/ABOUT are six-row bounded allowlists driven by committed diagnostics; `AgentProjection::renderMenu()` repaints panel 4 only. Registered tests cover viewports, page bands, diagnostic admission, direct focus, bounds, and panel targeting. | ✓ VERIFIED |
| 03-08 | 8/8 | `phase3_smoke.py` defines a closed exact-pair capture/evidence contract. The live trace, `R-BUCKET`, 72 128×128 logical framebuffer records, two deployment-tagged contact sheets, source labels, and physical-row separation are present. Current evidence is finalized rather than left pending. | ✓ VERIFIED |
| 03-09 | 7/7 | The final evidence has all 13 physical rows explicit and `pass`; its exact paired device, selected-usb binary hash, capture manifest deployment, tracer link, and fresh bridge resync receipt are present. Rows cover 10% optical text, direct keys, brightness transitions, LED behavior, persistence/reboot, and post-run bridge publication. | ✓ VERIFIED |

**Score:** 62/62 truths verified (5 ROADMAP criteria + 57 plan-specific truths).  
**Behavior-unverified:** 0 — all behavioral outcome categories have either registered production-path coverage and/or explicit exact-device observations. No test command was re-run in this verification.

## Required Artifacts

| Artifact group | Expected | L1/L2: existence and substance | L3/L4: wiring and real data flow | Status |
|---|---|---|---|---|
| `host/herdr_keypad/src/herdr_keypad/codex.py` | Supervised installed-Codex collector and normalization | Substantive collector, cache, sparse merge, deadline, child lifecycle, redaction, duration mapping, and status classification. | Installed `codex app-server --stdio` → normalized `CodexView` → `PermanentBridge`; live tracer records the actual handshake and current response. | ✓ VERIFIED |
| `bridge.py`, `projection.py`, `protocol/schema/v2.json`, host/native codecs | One closed publication with independent diagnostics | Schema and validators are closed; Codex/diagnostics are required in `agent_snapshot`; 4096-byte limit remains defined. | `PermanentBridge::_projection_payload()` validates before USB publish; native `ProtocolSession` admits before `AgentProjection` stages. | ✓ VERIFIED |
| `firmware/src/app/agent_projection.*`, `render_state.h`, four theme files | One committed display view and truthful panel 4 | Fixed-capacity generation/state plus substantive all-theme Codex/menu composers. | Decoded snapshot → candidate generation → committed `RenderState` → theme/LED consumers; no static provider fixture drives normal panel state. | ✓ VERIFIED |
| `menu_controller.*`, `product_input_router.*`, `main.cpp`, `settings_store.*` | Non-modal menu and local brightness persistence | Six-row state machine, fixed five-action router, local brightness intent, marker-last record. | One board sample → agent-first router → focus/menu dispatch; confirmed brightness → BoardAdapter + NVS only. | ✓ VERIFIED |
| LED engine and four grammars | Redundant Codex/health cue without copied state | Current/limit/failure mapping is substantive and `LedEvents` has no Codex cache. | Committed `RenderState` flows from production `main.cpp` through `LedEngine` to existing grammar zones and board LEDs. | ✓ VERIFIED |
| `03-CODEX-TRACER.json` and sidecar | Secret-free installed outcome | Current closed JSON records only normalized capacity, timing, child state, redaction, deployment/hello, and ACK facts. | Device evidence dereferences its checksum-pinned elapsed/child/redaction paths. | ✓ VERIFIED |
| `03-DEVICE-EVIDENCE.json`, captures manifest, contact sheets, sidecars | Exact-device and logical-pixel evidence kept separate | Final evidence is `status: pass`; capture records are 128×128 and sheets identify the same capture deployment. | 13 physical Y rows remain explicitly `physical`; scripted/machine/framebuffer/live sources stay typed separately. | ✓ VERIFIED |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| Installed `codex app-server` | `CodexCollector` | Bounded JSONL initialize → initialized → account/read → rateLimits/read | WIRED | `codex.py:608-674` starts exactly one stdio child, supplies required `clientInfo`, and only forwards normalized values. Tracer records all four stages. |
| `CodexCollector` | `PermanentBridge` | `CodexView` plus independent clock | WIRED | `_collect_codex()`, `refresh_codex()`, sparse, and account-change paths (`bridge.py:739-780`) update only Codex state and preserve focus on Codex-only publishes. |
| `PermanentBridge` | firmware `AgentProjection` | sole v2 `agent_snapshot` | WIRED | `_projection_payload()` produces the closed schema, `usb.publish_snapshot()` sends it, native protocol dispatch stages it, then shared state feeds rendering. |
| Committed `RenderState::codex` | all four panel-4 themes and LED grammars | shared view, no provider cache | WIRED | Four `composePanel4()` methods read `state.codex`; production `main.cpp` passes `agentProjection.renderState(now)` directly to `LedEngine`. |
| Board input | direct focus and secondary menu | one capture → agent-first router → existing focus / menu calls | WIRED | `main.cpp:574-609,634-643` and `product_input_router.cpp:11-25`; menu never receives agent-slot actions. |
| Brightness candidate | display + persistent local setting | preview intent / explicit confirm | WIRED | Preview/revert reaches `BoardAdapter::setBrightness`; only `SettingsStore::confirm()` writes the v2 preferences record. |
| Physical/machine observations | final evidence | canonical deployment/capture records + tracer audit link | WIRED | Device evidence binds its 13 rows and capture manifest to `9d1b…8f4b`; tracer link uses `fa365…1ce8` and fixed pointers. |

## Data-Flow Trace

| Artifact | Data variable | Source | Produces real data | Status |
|---|---|---|---|---|
| Capacity tile | `CodexView.primary/secondary/reset_text/reached_limit` | Installed local Codex app-server | The checked-in live tracer is source `installed`, `source_state: current`, with actual weekly `41` and primary absent; no fixture values occupy that record. | ✓ FLOWING |
| Freshness/health | source state and age | collector monotonic timestamps plus bridge link/Herdr clocks | Independent Codex, Herdr, sync, and link values are joined by `_join_health()` rather than copied from a single health flag. | ✓ FLOWING |
| Panel 4 and LEDs | committed Codex render view | admitted staged firmware generation | `AgentProjection` exposes one committed view to all theme and LED consumers. | ✓ FLOWING |
| HEALTH/ABOUT | closed diagnostics | bridge-derived bounded diagnostics | Diagnostic source is schema-validated and renderers use fixed allowlists; raw account/provider/path/error strings are rejected before render. | ✓ FLOWING |
| Brightness | candidate/stored brightness | encoder + device Preferences | Preview goes directly to hardware; confirm writes only device settings; it is disconnected from host snapshots, bindings, or focus identities. | ✓ FLOWING |

## Physical and Live Evidence Assessment

### Installed Codex trace

- `03-CODEX-TRACER.json` is explicitly `source.live: installed`, `result: pass`, and records `account_observed: true`, `rate_limits_observed: true`, and a completed four-stage handshake.
- Its observed values are truthful rather than synthesized: `primary: null`, `secondary: 41`, `reached_limit: null`, `source_state: current`, `observation_age: AGE 0M`, and `RESET WEEK 6D0H49M`.
- `collector.elapsed_ms` is 961 against `deadline_ms` 3000; `child_exit` has the closed `{state, code, signal}` shape; recursive redaction reports `pass` with only two hashed bucket-key prefixes and `selected_key: null`.
- The tracer and final device evidence share the selected-usb binary SHA-256 `d188d8f4…f26e`. Their per-run deployment IDs differ because each fresh deployment records fresh boot/session identity; the final evidence binds the tracer through its checksum and fixed audit pointers, not by claiming the separate run IDs are identical.

### Exact-device record

- `03-DEVICE-EVIDENCE.json` is `status: pass`, bound to exact paired device `0000fccb0deabf8c`, `selected-usb`, firmware identity `phase1-bringup`, and deployment `9d1b8a…8f4b`.
- All 13 required rows are explicit `source: physical`, `result: pass`, `answer: Y` where a human sighting is required. They cover all-theme 10% long text, source labels, direct keys from root/brightness/HEALTH/ABOUT, 10–100 ladder, zero rejection, close/timeout reverts, LED preview semantics, confirm, reboot restore, and fresh bridge resync.
- `captures.json` labels framebuffer output `logical-framebuffer-only`, gives every sampled frame 128×128 dimensions and the capture deployment ID, and labels its two 1152×512 contact sheets as logical artifacts. It does not substitute pixels for physical observations.

### Evidence integrity

| Check | Static result | Assessment |
|---|---|---|
| Tracer checksum reference | Sidecar names `03-CODEX-TRACER.json`; device evidence uses the same digest `fa365c0e…1ce8`. | ✓ Linked |
| Device-evidence checksum reference | Sidecar names the final evidence artifact. | ✓ Present |
| Audit fields | Final evidence has only the fixed tracer checksum plus `/collector/elapsed_ms`, `/collector/child_exit`, and `/redaction/result` pointers; the target fields exist with the stated bounded values. | ✓ Linked |
| Deployment chain | Evidence deployment, capture-manifest reference, every displayed capture inspected, and both contact-sheet metadata use `9d1b8a…8f4b`; tracer/final deployment binary hashes match. | ✓ Consistent |
| Evidence-kind separation | Installed, scripted R-BUCKET, machine, logical-framebuffer, and physical sources are distinct fields/rows. | ✓ Preserved |

The integrity findings above are static cross-reference checks. Cryptographic digest recomputation and the smoke validator were deliberately not re-run under the requested no-validation-command constraint.

## Requirements Coverage

| Requirement | Source plans | Description | Status | Evidence |
|---|---|---|---|---|
| CODEX-01 | 01, 03–05, 08–09 | Read-only fourth tile shows supplied primary/secondary usage. | ✓ SATISFIED | Closed normalization/schema/render path; installed weekly-only result and all-theme physical/source-label evidence. |
| CODEX-02 | 01, 03–04, 08–09 | Nearest reset and reached-limit indication when supplied. | ✓ SATISFIED | Nearest-reset code, state helpers, renderer matrix, and live `RESET WEEK 6D0H49M` trace. |
| CODEX-03 | 01–05, 08–09 | Null/missing unavailable; all required source states distinct. | ✓ SATISFIED | Presence-aware collector/protocol/renderers, registered source-state matrix, and physical source-label row. |
| CODEX-04 | 01–04, 08–09 | Observation age visible. | ✓ SATISFIED | Independent collector timestamp/`AGE` formatting, diagnostics, theme meta rows, live `AGE 0M`. |
| SYNC-03 | 01–03, 05, 07–09 | Herdr, Codex, and link health independently tracked/rendered. | ✓ SATISFIED | Separate bridge clocks/diagnostics, closed v2 fields, HEALTH page, and Codex-only focus-preservation tests. |
| SAFE-01 | 01–04, 06–09 | Credentials remain host-only; device data is bounded. | ✓ SATISFIED | Host-only child boundary, redaction rejection, closed protocol/diagnostic grammar, secret-free trace/evidence. |
| MENU-01 | 06–09 | Encoder menu is secondary; direct keys stay direct. | ✓ SATISFIED | Agent-first production router plus physical key rows in all required menu contexts. |
| MENU-02 | 07–09 | Menu reports link, source health, and ages. | ✓ SATISFIED | Closed `_diagnostics()` projection, all-theme fixed HEALTH rows, panel-4-only render tests. |
| MENU-03 | 03, 07–09 | Bounded IDs/versions without secrets or host paths. | ✓ SATISFIED | Closed protocol and diagnostic admission; source-injection test proves sensitive values do not render; ABOUT physical long-text sighting. |
| MENU-04 | 06–09 | Persist brightness without changing order/focus semantics. | ✓ SATISFIED | Device-only `SettingsStore`, local BoardAdapter preview, router/invariance tests, explicit physical ladder/revert/confirm/reboot rows. |

**Traceability note:** `.planning/REQUIREMENTS.md` still labels MENU-01 through MENU-04 as unchecked/Pending in its checklist/traceability rows even though current Phase 03 source and exact-device evidence satisfy them. That is planning-status metadata drift, not a failed Phase 03 requirement; it should be reconciled during phase bookkeeping rather than represented as a product gap.

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Host Codex/bridge/protocol behaviors | Not run — user instructed all validation commands be skipped. | Current tests define dedicated collector, projection, integration, and protocol cases; static audit only. | SKIPPED BY REQUEST |
| Firmware panel/menu/LED/input behavior | Not run — user instructed all validation commands be skipped. | Native runner registers production module tests for the claimed transitions; static audit only. | SKIPPED BY REQUEST |
| Guided device/evidence validator | Not run — user instructed all validation commands be skipped. | Current final evidence contains the recorded physical/machine artifacts; static cross-links inspected. | SKIPPED BY REQUEST |

## Anti-Patterns and Regression Risk

| Scope | Finding | Severity | Disposition |
|---|---|---|---|
| Phase 03 production files sampled from collector, bridge, protocol, renderer, menu, settings, input, LED, and capture paths | No `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER`, or unimplemented marker found. | INFO | No stub/debt-marker blocker. |
| `firmware/src/ui/theme_signal_edge.cpp:168-171` | A protocol-valid 32-character agent discriminator can overflow the available Signal Edge width. | WARNING — deferred | Standard-depth review WR-01 assigns ellipsizing plus a native regression to Phase 03.1. This existing agent-panel polish issue does not falsify Phase 03's Codex/menu goal or its recorded exact-device acceptance. |
| `firmware/src/ui/theme_instrument.cpp:138-149` | `drawUsageGauge()` is unused and retains stale gauge vocabulary. | INFO — deferred | Standard-depth review IN-02 assigns deletion to Phase 03.1. It is dead helper cleanup, not an alternate Codex/menu data path. |
| Evidence commands | No fresh command revalidation occurred. | INFO | Deliberately constrained by this verification request; results above are static/recorded evidence, not newly observed execution. |

The two Phase 03.1 deferrals are intentionally **not** blockers for Phase 03: the review explicitly found zero critical findings and no remaining security blocker for the accepted exact binary. Phase 03.1 has specific success criteria for renderer/interaction polish and is the recorded owner of those changes.

## Human Verification Required

None. The final evidence package already contains explicit physical observations for visual legibility, direct interaction, brightness, LEDs, focus contexts, reboot persistence, and post-acceptance bridge publication. This verifier did not solicit or re-run a new UAT because the user required validation commands be skipped.

## Verdict

The phase goal is achieved. The actual installed Codex result flows through the single collector/bridge/protocol/staged-render path without fabricating absent fields; the menu exposes bounded diagnostics and local brightness without intercepting agent selection; and the final exact-device evidence records the physical behaviors code alone cannot prove. No missing/stub artifact, broken key link, data-flow hollow, unstructured sensitive payload, or blocker debt marker was found.

---

_Verified: 2026-08-21T03:32:36Z_  
_Verifier: the agent (gsd-verifier)_
