---
phase: 01-physical-keypad-and-proven-transport
verified: 2026-08-16T20:40:53Z
status: gaps_found
score: 12/28 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "The phase has a valid MVP user-story contract that can be verified through User Flow Coverage."
    status: failed
    reason: "ROADMAP declares mode: mvp, but the phase goal is not in the required As a..., I want..., so that... format; the canonical validator returned false. Technical goal-backward verification below therefore uses the explicit goal and success criteria, but cannot produce authoritative MVP User Flow Coverage."
    artifacts:
      - path: ".planning/ROADMAP.md"
        issue: "Phase 1 mode and goal are internally inconsistent."
    missing:
      - "Rewrite the Phase 1 MVP goal as a valid user story or remove the MVP mode designation through the canonical planning workflow."
  - truth: "The selected firmware and host exchange bounded, versioned, correlated v1 messages through the same frozen production protocol implementation."
    status: failed
    reason: "The flashed firmware parses and dispatches frames in main.cpp instead of FrameCodec/ProtocolSession; the host accepts boolean protocol versions and can raise untyped TypeError; the JSON Schema rejects real non-empty payloads; and the C++ codec accepts narrowed versions/trailing garbage."
    artifacts:
      - path: "firmware/src/main.cpp"
        issue: "handleFrame() is a second admission/session path and does not enforce the frozen protocol/session invariants."
      - path: "firmware/src/protocol/protocol.cpp"
        issue: "The tested codec is not called by the flashed runtime and has independent validation defects."
      - path: "tools/phase1_bringup/src/phase1_bringup/protocol.py"
        issue: "validate_frame() type-check ordering permits bool-as-v1 and unhashable discriminants escape typed rejection."
      - path: "protocol/schema/v1.json"
        issue: "The closed root payload schema recognizes no properties and x-payload-contract contains duplicate event keys."
    missing:
      - "Route every runtime frame through one tested production codec/session before side effects."
      - "Repair and actually validate the Draft 2020-12 schema against all golden vectors."
      - "Add adversarial host/C++ vectors for types, wide versions, trailing bytes, nesting, canonicalization, and integrated runtime dispatch."
  - truth: "After every required reset, unplug, port/link interruption, and utility restart, the same unit returns with a fresh boot/session and no uncertain replay."
    status: failed
    reason: "The accepted result repeats boot_id 0000fccb0deabf8c-2385 across every reconnect, two required rows are U yet qualification passes, and recover merely labels a generic reconnect without action-specific pre/post checks."
    artifacts:
      - path: "firmware/src/main.cpp"
        issue: "bootId is deviceId + millis(), which repeated across accepted resets."
      - path: "artifacts/phase1/20260816T190217Z-cc059b/result.json"
        issue: "Identical boot IDs recur; forced-endpoint-renumbering and host-utility-restart are unavailable."
      - path: "tools/phase1_bringup/src/phase1_bringup/__main__.py"
        issue: "run_recover() does not induce or validate the named interruption; recovery-tour resume state is forgeable/path-traversable."
    missing:
      - "Generate a hardware-random per-boot nonce and enforce pre/post boot and session transitions."
      - "Require action-specific machine facts for every required applicable row; required U must not qualify."
      - "Derive recovery-tour progress from hash-verified step artifacts with contained, validated resume IDs."
  - truth: "USB is selected from complete real measurements that enforce every frozen gate and remain immutable."
    status: failed
    reason: "No latency samples or limits are enforced, required U rows are accepted, the queue metric is transport bytes rather than protocol frames, and sha256sum -c fails for the accepted qualification result even though the qualification lock verifier reports success."
    artifacts:
      - path: "tools/phase1_bringup/src/phase1_bringup/qualification.py"
        issue: "rows_ok accepts required U; latency gates are frozen but never measured or validated."
      - path: "firmware/src/metrics/proof_metrics.h"
        issue: "queue_high_water observes USB buffered bytes, not the protocol queue."
      - path: "artifacts/phase1/20260816T190217Z-cc059b/SHA256SUMS"
        issue: "Expected result hash 1ad0ef... but current result hash is d9d1a7...; immutable evidence was changed after checksum finalization."
    missing:
      - "Measure and enforce all frozen p99/handshake latency gates."
      - "Require successful required interruption rows and actual protocol queue metrics."
      - "Restore a single immutable qualification result whose directory checksum, traffic hash, locks, and semantic validation all agree."
  - truth: "Selection, build, and archive verification re-establish full lineage, exact composition, and secret-free claims rather than trusting asserted booleans or copied hashes."
    status: failed
    reason: "Current locks are internally hashable and the actual ELF independently contains UsbCdcLink and no WifiTlsLink, but the production verifiers omit required purpose/transport/path/lineage checks, trust composition booleans, scan secrets only at top level, and ignore accepted CLI requirement flags."
    artifacts:
      - path: "tools/phase1_bringup/src/phase1_bringup/evidence.py"
        issue: "Qualification/selection/build/archive verifiers do not recompute all generator invariants or recursively enforce a closed secret-free schema."
      - path: "tools/phase1_bringup/src/phase1_bringup/__main__.py"
        issue: "immutable-selection, archived-source, exact-manifest-hash, no-secret-output, exactly-one-adapter, and unselected-source-object-symbol flags are parsed but not enforced."
      - path: "tools/phase1_bringup/ARCHIVED"
        issue: "The marker points to a qualification result whose own SHA256SUMS no longer matches."
    missing:
      - "Recompute canonical path, purpose, transport, manifest/result/traffic, selection/build/archive, object, and ELF-symbol invariants in every verifier."
      - "Make every advertised CLI flag a concrete required assertion and enforce an exact recursively secret-free archive schema."
  - truth: "Physical PASS and recovery PASS cannot be fabricated, inferred from ACK, or changed from failure without a fresh observation."
    status: failed
    reason: "Physical validators accept incomplete maps and do not require N/failed consistency; the guided loop accepts Y immediately after N against the same stable machine fact; board initialization failure still permits accepted probes."
    artifacts:
      - path: "tools/phase1_bringup/src/phase1_bringup/evidence.py"
        issue: "_validate_physical_row/_validate_physical_map do not enforce the canonical row set or response/status matrix and do not reopen the source machine evidence."
      - path: "tools/phase1_bringup/src/phase1_bringup/guide.py"
        issue: "GuidedRun.respond(N) leaves stable evidence active, permitting a following Y without restimulation or replacement."
      - path: "firmware/src/main.cpp"
        issue: "boardReady is discarded after setup and hardware-dependent probes still acknowledge."
    missing:
      - "Derive physical result status from the exact canonical row/history set and source evidence."
      - "Make N terminal or require R plus fresh machine evidence and a typed replacement link."
      - "Persist board readiness and reject hardware probes while initialization is failed."
  - truth: "The plan-owned host environment is exactly Python 3.11 with pyserial 3.5."
    status: failed
    reason: "The installed plan-owned venv reports Python 3.14.7; pyproject.toml declares only >=3.11. Both Plan 01-01 and later summaries explicitly record this deviation."
    artifacts:
      - path: "tools/phase1_bringup/.venv/bin/python"
        issue: "Runtime is Python 3.14.7, not the must-have exact Python 3.11."
      - path: "tools/phase1_bringup/pyproject.toml"
        issue: "requires-python is >=3.11 rather than an exact reproducibility pin."
    missing:
      - "Provide the exact Python 3.11 plan-owned environment or formally override/update the must-have."
---

# Phase 1: Physical Keypad and Proven Transport Verification Report

**Phase Goal:** The user can operate the delivered T-Keyboard S3 Pro through a verified physical map and a host link selected from real measurements.
**Verified:** 2026-08-16T20:40:53Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Verification Scope and Method

All eight `01-XX-PLAN.md` files, all eight matching `SUMMARY.md` files, `.planning/REQUIREMENTS.md`, the live firmware/host implementation, immutable physical/qualification/selection/build/archive artifacts, and `01-REVIEW.md` were inspected. SUMMARY claims were treated only as discovery input. Artifact contents, hashes, implementation wiring, narrow executable checks, and the final ELF were checked independently.

The roadmap declares `mode: mvp`, but:

```text
node .codex/gsd-core/bin/gsd-tools.cjs query user-story.validate --story "The user can operate ..." --pick valid
false
```

The required MVP User Story format is therefore invalid. To avoid discarding the requested audit, the report verifies the explicit goal, all four roadmap success criteria, and every PLAN must-have; it does not claim authoritative MVP User Flow Coverage.

## Goal Achievement

### Observable Truths

| # | Source | Truth | Status | Evidence |
|---:|---|---|---|---|
| 1 | Roadmap SC1 | The connected unit exposes the four displays/matching keys, encoder path, brightness, orientation, and deterministic reboot against a recorded map. | ✓ VERIFIED | `artifacts/phase1/confirmed-20260816T133300Z-f81cd8-e6c1b4/result.json` contains the exact 30-row set (4 displays, 4 keys, 3 encoder, 14 LEDs, 3 brightness, Identify, Reboot), every row `Y/pass/acknowledged`; both that run and source machine run pass `sha256sum -c`. |
| 2 | Roadmap SC2 | Device and host complete a bounded, versioned bidirectional exchange over the physically selected transport. | ✗ FAILED | Traffic bytes exist, but `firmware/src/main.cpp:295-406` bypasses `FrameCodec`/`ProtocolSession`; host and C++ validation diverge. The selected path is not the frozen semantics claimed by HARD-03. |
| 3 | Roadmap SC3 | The same unit re-establishes the selected link after reset, unplug, or interruption without unrecorded assumptions. | ✗ FAILED | Accepted evidence repeats boot ID `0000fccb0deabf8c-2385`; two required rows are `U`; `run_recover()` does not verify named interruption transitions. |
| 4 | Roadmap SC4 | Measurements prove USB suitable for v1 or prove the specific failure selecting Wi-Fi. | ✗ FAILED | Latency gates are absent, required unavailable rows still pass, and the accepted qualification directory checksum fails. The USB suitability decision is not proven. |
| 5 | Plan 01-01 T1 | One guided command proves physical stimulus/key, explicit confirmation, bounded correlated v1 USB round trip, and atomic evidence end to end. | ✗ FAILED | Initial artifact hashes pass, but `artifacts/phase1/20260816T083124Z-c8553c/result.json` has only an unbound `physical_observation: confirmed` assertion; runtime protocol admission is not the frozen path. |
| 6 | Plan 01-01 T2 | Host package runs only through the plan venv with exact Python 3.11 and pyserial 3.5. | ✗ FAILED | `tools/phase1_bringup/.venv/bin/python --version` is `Python 3.14.7`; `pyproject.toml:9-10` declares `>=3.11` and pyserial 3.5. |
| 7 | Plan 01-01 T3 | The tracer writes immutable manifest/result, finalizes SHA-256, reopens, and verifies before success. | ✓ VERIFIED | `EvidenceWriter.write()/verify()` at `evidence.py:685-736`; `sha256sum -c` passes for `artifacts/phase1/20260816T083124Z-c8553c`. This does not rescue later qualification evidence. |
| 8 | Plan 01-02 T1 | Every physical surface is separately stimulated and remains unapproved until fresh explicit confirmation. | ✗ FAILED | Stimulus coverage exists, but `guide.py:492-501` allows `N` followed by `Y` on the same stable fact, and `main.cpp:482-490` discards failed board readiness while probes still ACK. |
| 9 | Plan 01-02 T2 | Device UI implements fixed states, safe inset, sequential panels, WAIT, non-color cues, and low-brightness backstop. | ✓ VERIFIED | `bringup_renderer.h:35-55,85-155,158-268` is substantive and wired by `main.cpp:105-118`; physical confirmation artifact records all display/brightness groups as Y. |
| 10 | Plan 01-03 T1 | Host order is Identify, Displays, Keys, Encoder, LEDs, Brightness, Reboot, Pair, Recover, Traffic, Selection. | ✓ VERIFIED | `guide.py:14,34-55`; narrow `self-check --ui --guided-order` prints the exact order and exits 0. |
| 11 | Plan 01-03 T2 | Every physical row binds machine evidence and visible human confirmation while preserving unavailable/failed/replaced history immutably. | ✗ FAILED | The current 30-row artifact is complete, but `_validate_physical_map()` accepts one arbitrary row and does not reopen the machine source; `GuidedRun` permits N→Y without restimulation. The claimed invariant is not enforced. |
| 12 | Plan 01-03 T3 | Approved 80x24 host UI/copy, one active card, elapsed state, wrapping, and bounded empty/loading/populated/overflow behavior exist. | ✓ VERIFIED | `ui.py:10-19,59-203`; `self-check --ui --guided-order` exits 0. |
| 13 | Plan 01-04 T1 | Only the keypad showing the fresh typed challenge becomes the opaque device identity; descriptors remain discovery-only. | ✓ VERIFIED | `pairing.py:103-135` fails closed on zero/ambiguity/mismatch/no confirmation and persists hello `device_id`; `artifacts/phase1/20260816T134827Z-c913ce/result.json` records challenge `3167DB` and device `...bf8c`. |
| 14 | Plan 01-04 T2 | The exact unit rebinds unprivileged through every required interruption with fresh boot/session and no uncertain replay. | ✗ FAILED | Same boot ID across resets, two U rows, generic labeled reconnects, forgeable resume state, and no pre/post transition enforcement. |
| 15 | Plan 01-05 T1 | PlatformIO native runner loads the repository golden fixture and exercises firmware codec/session. | ✓ VERIFIED | `platformio.ini:31-40` compiles `protocol/**`, injects the fixture, and `test/protocol/test_main.cpp:94-171` invokes `FrameCodec`/`ProtocolSession`. |
| 16 | Plan 01-05 T2 | Host and native firmware tests consume the same frozen schema/fixtures and produce identical typed outcomes for every vector. | ✗ FAILED | Both consume the fixture, but the native harness does not validate against JSON Schema; the schema itself rejects real payloads; host/C++ behavior diverges outside the 24 fixture vectors. |
| 17 | Plan 01-05 T3 | Malformed/unknown/incompatible/oversized/duplicate/corrupt/out-of-order input is rejected before dispatch; session changes discard uncertain work. | ✗ FAILED | `main.cpp:295-406` does not enforce reply-to, closed shape, identifier bounds, boot/session equality, sequencing, duplicate/out-of-order, or queue bounds before side effects. |
| 18 | Plan 01-06 T1 | A frozen SHA-addressed manifest fixes duration, cadence, counts, bursts, overlap, interruption rows, resource gates, and protocol bound before traffic. | ✓ VERIFIED | `qualification-manifest.json` and `qualification.py:96-147,181-217` contain and validate those frozen values; manifest SHA is bound in the locks. |
| 19 | Plan 01-06 T2 | USB passes only on exact counters, zero failures, complete metrics, and physically confirmed overlap. | ✗ FAILED | The implemented pass omits frozen latency gates and lets required U rows pass; `queue_high_water` is not the protocol queue. |
| 20 | Plan 01-06 T3 | Manifest/result/traffic are sole hash-validated later inputs and failed/remediated attempts remain immutable. | ✗ FAILED | `sha256sum -c` fails for the accepted result; official lock verification still exits 0. The later chain binds a post-checksum-mutated result. |
| 21 | Plan 01-07 T1 | Wi-Fi work executes only after hash-validated repeatable remediated USB failure; valid USB success skips it without secrets/source. | ✗ FAILED | Wi-Fi was skipped, but the USB lock is not a valid strict qualification proof; the branch decision relies on the unsound lock verifier. |
| 22 | Plan 01-07 T2 | Conditional Wi-Fi credential/TLS provisioning is bounded, exact-device authorized, atomic, and rollback-safe. | ✓ VERIFIED (conditional skip) | USB lock reported pass and the conditional branch was not created; no Wi-Fi credential source or persistence artifact exists. This is not evidence that the absent Wi-Fi implementation works. |
| 23 | Plan 01-07 T3 | Conditional AP-auth failure preserves old/no credentials and emits only redacted status. | ✓ VERIFIED (conditional skip) | No Wi-Fi branch or credential output exists; review and repository scan found no current credential material. |
| 24 | Plan 01-07 T4 | Conditional Wi-Fi candidate composes exactly WifiTlsLink and records the matrix before selection. | ✓ VERIFIED (conditional skip) | The branch is intentionally absent after the recorded USB pass; `firmware/src/transport/` contains only `link.h` and `usb_cdc.cpp`. |
| 25 | Plan 01-08 T1 | Selection resolves a fixed pointer to concrete result/hash and validates result plus frozen manifest; latest is not consumed afterward. | ✗ FAILED | Concrete paths/hashes exist, but the resolved result fails its own SHA256SUMS and pointer/lock verification omits complete semantic validation. |
| 26 | Plan 01-08 T2 | USB is selected from the existing strict one-time pass; Wi-Fi is not reconsidered and no long rerun occurs. | ✗ FAILED | No second long run occurred, but the one-time result is not a strict valid pass because frozen gates and immutability failed. |
| 27 | Plan 01-08 T3 | Selection chooses exactly selected-usb; one Link is built and unselected source/object/symbol is absent. | ✓ VERIFIED | `platformio.ini:1-27` selects/excludes Wi-Fi; source tree has no Wi-Fi source; build object dir has only `usb_cdc.cpp.o`; independent `nm -C --defined-only firmware.elf` found UsbCdcLink symbols and zero WifiTlsLink symbols. |
| 28 | Plan 01-08 T4 | Final binary/archive is hash-validated against existing immutable physical qualification; no second 30-minute run occurs. | ✗ FAILED | Final binary hash exists and no rerun occurred, but archive lineage terminates at a qualification result whose own checksum fails, and required archive flags are ignored. |

**Score:** 12/28 truths verified (0 present-but-behavior-unverified)

### Must-Have Prohibitions

All 13 prohibitions were present in PLAN frontmatter as `status: unverified, flagged: true` with no verification tier. They were adjudicated against live code/evidence rather than silently passed.

| Plan | Prohibition | Verdict | Evidence |
|---|---|---|---|
| 01-01 | HARD-01 must not treat firmware ACK as physical observation. | ✗ VIOLATED | Initial accepted result has no step/run-bound human response; later validators can accept incomplete physical PASS. |
| 01-01 | HARD-03 must not accept unbounded/unversioned/uncorrelated tracer frames. | ✗ VIOLATED | Runtime `handleFrame()` bypasses frozen session checks. |
| 01-02 | HARD-01 must not replace delivered-unit observations with docs/defaults/ACKs. | ✓ CURRENT ARTIFACT OK | Current 30-row map has explicit group Y records; this is independent of the validator weakness. |
| 01-03 | HARD-01 must not infer PASS from ACK, Enter, docs, or prior run. | ✗ VIOLATED | N→Y can reuse the same machine fact; physical verifier does not reopen the source run. |
| 01-04 | HARD-01 must not pair first-match/look-alike/descriptor/path identity. | ✓ VERIFIED | Exact challenge and hello device ID gate in `pairing.py:103-135`. |
| 01-04 | HARD-03 must not replay uncertain work across boot/session changes. | ✗ VIOLATED | Boot freshness is not enforced and accepted boot IDs repeat. |
| 01-05 | HARD-03 must not accept malformed/unknown/incompatible/oversized/duplicate/corrupt/out-of-order traffic. | ✗ VIOLATED | Runtime parser lacks the production codec/session checks; host malformed discriminants escape typed rejection. |
| 01-05 | Frozen bounds/fixtures must not change after qualification starts. | ✓ VERIFIED | Current manifest binds schema/fixture hashes; no mismatch was found for those files. The result immutability failure is separate. |
| 01-06 | HARD-03 thresholds must not be lowered/reinterpreted after traffic begins. | ✗ VIOLATED | Frozen latency limits are never enforced and required U is treated as passing. |
| 01-06 | HARD-01 overlap must not be inferred from counters. | ✓ VERIFIED | Result stores explicit preflight/overlap `Y`; qualification code uses an operator checkpoint. |
| 01-07 | HARD-03 must not make Wi-Fi eligible before repeatable remediated USB failure. | ✗ VIOLATED IN DECISION GATE | Wi-Fi was skipped from a semantically invalid USB pass, so the prerequisite decision is not trustworthy. |
| 01-07 | Secrets must not appear in output/evidence/logs/summaries/errors/archives. | ✓ CURRENT CORPUS OK | No Wi-Fi source/credential artifacts or reviewed secret material found; verifier remains bypassable for future nested fields. |
| 01-08 | HARD-03 must not ship hybrid/failover/dormant unselected adapter/runtime selection. | ✓ VERIFIED | Actual source, object list, and ELF contain only USB adapter. |
| 01-08 | Selection must not trust latest summaries/archive before a strict pass. | ✗ VIOLATED | Candidate resolution accepts a semantically false/mutated qualification result and later verifiers trust copied assertions. |

## Required Artifacts

The canonical `verify.artifacts` query could not parse most scalar/flow-style PLAN artifact declarations (it reported no artifacts); artifacts were therefore verified manually at existence, substance, wiring, and—where applicable—data-flow levels.

| Artifact | Plans | L1/L2 | Wiring / Data | Final Status |
|---|---|---|---|---|
| `platformio.ini` | 01,05,07,08 | Exists, substantive | selected-usb/native environments active; Wi-Fi excluded | ✓ VERIFIED |
| `protocol/schema/v1.json` | 01,05 | Exists, substantive | Loaded only by superficial metadata checks; standards-invalid payload closure | ✗ DEFECTIVE |
| `protocol/fixtures/v1-golden.json` | 05 | Exists, 24 vectors | Host/native harness consume it | ✓ VERIFIED, coverage incomplete |
| `firmware/src/main.cpp` | 01,02,04,06,08 | Exists, substantive | Flashed runtime; bypasses tested protocol and ignores failed board readiness | ✗ DEFECTIVE |
| `firmware/src/board/physical_map.h` | 02 | Exists, substantive | Global `physicalMap` instantiated but never read or populated | ⚠ ORPHANED |
| `firmware/src/board/board_adapter.*` | 02 | Exists, substantive | Wired to renderer/main | ✓ VERIFIED |
| `firmware/src/ui/bringup_renderer.h` | 02 | Exists, substantive | Called through `render()` for sequential panels | ✓ VERIFIED |
| `tools/.../__main__.py` | 01,03,04,06,08 | Exists, substantive | CLI entrypoint; several advertised requirements ignored | ✗ DEFECTIVE |
| `tools/.../guide.py` | 03,04 | Exists, substantive | Wired to UI/evidence/protocol; N→Y state bug | ✗ DEFECTIVE |
| `tools/.../ui.py` | 03 | Exists, substantive | Wired through GuidedRun/BatchRun | ✓ VERIFIED |
| `tools/.../discovery.py` | 04 | Exists, substantive | Feeds pairing/reconnect candidate narrowing | ✓ VERIFIED |
| `tools/.../pairing.py` | 04,07 | Exists, substantive | Exact challenge→device_id→atomic store | ✓ VERIFIED |
| `tools/.../serial_link.py` | 04 | Exists, substantive | Reconnects exact identity; no prior-boot comparison; short-write/read-close defects | ⚠ PARTIAL |
| `host/udev/99-herdr-keypad.rules` | 04 | Exists, narrow measured rule | Checked by self-check; ordinary-user policy represented | ✓ VERIFIED |
| `firmware/src/protocol/protocol.{h,cpp}` | 05 | Exists, substantive | Native tests only; not wired to flashed runtime | ⚠ ORPHANED FROM RUNTIME |
| `test/protocol/test_main.cpp` | 05 | Exists, substantive | Native harness loads fixture; queue-full test is misleading | ⚠ PARTIAL |
| `firmware/src/metrics/proof_metrics.h` | 06 | Exists, substantive | Wired to main; queue metric measures bytes, not protocol frames | ✗ DEFECTIVE |
| `firmware/src/transport/link.h`, `usb_cdc.cpp` | 06,08 | Exists, substantive | Instantiated by main; object and ELF symbols present | ✓ VERIFIED |
| `tools/.../qualification.py` | 06,07 | Exists, substantive | Runs real traffic, but omits latency and accepts required U | ✗ DEFECTIVE |
| Plan 07 Wi-Fi/security artifacts | 07 | Absent | Conditional branch was skipped | ✓ EXPECTED ABSENCE |
| `tools/.../evidence.py` | 01,03,04,06,08 | Exists, substantive | Central writer/lock verifier; multiple semantic and lineage bypasses | ✗ DEFECTIVE |
| `artifacts/phase1/...confirmed...` | 03 | Exists, 30 rows | Source and confirmed checksum sets independently pass | ✓ CURRENT ARTIFACT VERIFIED |
| `artifacts/phase1/...190217...` | 06 | Exists, 3,800-frame result/traffic | `result.json` no longer matches `SHA256SUMS` | ✗ MUTATED/NOT IMMUTABLE |
| `artifacts/phase1/locks/*.json` | 06,08 | Exist, hash-addressed | Bind current files but accept semantically false evidence | ✗ DEFECTIVE PROOF |
| `.pio/build/selected-usb/firmware.elf/.bin` | 08 | Exist | ELF independently proves USB symbols and no Wi-Fi symbols | ✓ CURRENT BUILD VERIFIED |
| `tools/phase1_bringup/ARCHIVED` | 08 | Exists | Binds current locks but inherits invalid qualification and weak verifier | ✗ DEFECTIVE ARCHIVE |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| Plan venv module | Schema, USB tracer, EvidenceWriter | `python -m phase1_bringup` | ⚠ PARTIAL | Entrypoint is real; exact Python 3.11 missing and schema check is superficial. |
| Firmware runtime | Host frozen protocol | `main.cpp` ↔ `protocol.py` | ✗ NOT WIRED | Firmware runtime does not use `firmware/src/protocol/protocol.cpp`. |
| `BoardAdapter` | `BringupRenderer` | `main.cpp::render` | ✓ WIRED | Sequential rendering flows to all four panels. |
| `PhysicalMap` | Actual stimulus behavior | mapping lookup | ✗ NOT WIRED | Runtime map object is dead; mappings are hardcoded in `applyStimulus()`. |
| UI response | Machine fact | `GuidedRun.respond` | ⚠ PARTIAL | Step/run token binding exists, but failed N can be followed by Y on the same fact. |
| GuidedRun | EvidenceWriter | `_record` / finalize | ⚠ PARTIAL | Rows flow, but full canonical/history invariants are not validated. |
| Discovery | Pairing | challenge + hello `device_id` | ✓ WIRED | Exact identity persists only after challenge match. |
| Pairing binding | SerialLink | `reconnect_exact` | ⚠ PARTIAL | Exact device matching works; fresh boot/action-specific transition does not. |
| Native PlatformIO | Production codec fixture | `test_build_src`, fixture define | ✓ WIRED | Test binary compiles `protocol.cpp`; flashed binary does not use it. |
| QualificationRunner | USB/metrics/evidence | session traffic + metrics ack | ⚠ PARTIAL | Real data flows, but frozen latency/interruption gates do not. |
| Selection→build→archive | locks/hashes | `evidence.py` | ⚠ PARTIAL | Current paths/hashes flow; verifiers do not re-establish the full semantic graph. |

## Data-Flow Trace (Level 4)

| Artifact / Value | Source | Flow | Produces Real Data | Status |
|---|---|---|---|---|
| Confirmed physical-map rows | Device ACK/events + explicit group Y | `BatchRun`/`confirm-batch` → EvidenceWriter → confirmed result | Yes; 30 rows, source checksum independently matches | ✓ FLOWING, verifier weak |
| Qualification counters/traffic | Real serial traffic and device metrics | QualificationRunner → result/traffic → eligibility lock | 3,800 counts and metrics exist | ⚠ FLOWING BUT INCOMPLETE (no latency; U accepted) |
| Boot/session recovery facts | hello/reconnect transitions | SerialLink → result interruption matrix | Sessions change; boot ID does not | ✗ CONTRADICTORY |
| Selection/build/archive lineage | latest pointer → concrete result → selection → build → archive | Evidence lock chain | Hashes current files, but result's own checksum set fails and semantic gates are omitted | ✗ HOLLOW PROOF |
| Runtime command admission | USB bytes → `main.cpp::handleFrame` → hardware side effects | Does not traverse frozen FrameCodec/ProtocolSession | Real commands dispatch through duplicate parser | ✗ DISCONNECTED FROM FROZEN CONTRACT |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Host UI/order/evidence self-check | `...python -m phase1_bringup self-check --ui --guided-order --evidence-schema --physical-confirmation` | Exit 0; exact order printed | ✓ PASS (narrow) |
| Frozen fixture host self-check | `...python -m phase1_bringup self-check --protocol-golden ... --schema ...` | Exit 0; 24 vectors | ✓ PASS, but does not exercise runtime/schema defects |
| Malformed host discriminants | Direct `validate_frame/classify_line` probe | `v: true` accepted; list `type` raises `TypeError` | ✗ FAIL |
| Physical evidence hashes | `sha256sum -c` in confirmed physical run and source run | Both manifest/result sets OK | ✓ PASS |
| Qualification evidence hashes | `sha256sum -c` in `20260816T190217Z-cc059b` | `result.json: FAILED` | ✗ FAIL |
| Official qualification lock verifier | `verify-evidence usb-eligibility.json --require strict-traffic --require immutable-linkage --require complete-interruption-matrix` | Exit 0 despite checksum failure, repeated boot ID, and required U rows | ✗ FALSE POSITIVE |
| Physical directory verifier from plan shape | `verify-evidence artifacts/...confirmed... --require physical-map` | Exit 2, `Is a directory` | ✗ FAIL; `result.json` path succeeds instead |
| Official archive verifier | `verify-evidence ARCHIVED --require archived-source --require exact-manifest-hash --require immutable-linkage --require no-secret-output` | Exit 0 although requirement flags are ignored and qualification checksum fails | ✗ FALSE POSITIVE |
| Final selected symbols | `nm -C --defined-only .pio/build/selected-usb/firmware.elf` | UsbCdcLink symbols present; zero WifiTlsLink symbols | ✓ PASS |

No project-wide build, formatter, linter, or test suite was run. No server/service was started. All checks were narrow and read-only.

## Probe Execution

No `probe-*.sh` path is declared by any Phase 01 PLAN/SUMMARY, and repository probe discovery found no phase-declared probe. Step 7c is **SKIPPED (no declared probe scripts)**.

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| HARD-01 | 01-01 through 01-08 | Connected Pro has all physical controls/map and selected host link verified. | ✗ BLOCKED | Current physical map is independently present and hash-consistent, but selected host link/evidence lineage is not valid; physical PASS machinery permits false confirmation paths. |
| HARD-03 | 01-01 through 01-08 | Bounded versioned reliable messages over transport selected by physical bring-up. | ✗ BLOCKED | Runtime bypasses frozen protocol/session; recovery freshness and qualification/selection gates fail. |

No Phase 1 requirement is orphaned: `.planning/REQUIREMENTS.md:94-99` maps exactly HARD-01 and HARD-03 to Phase 1, and every PLAN declares both.

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---:|---|---|---|
| Phase-modified source set | — | `TBD|FIXME|XXX` | None | No unresolved debt-marker blocker found. |
| Phase-modified source set | — | `TODO|HACK|PLACEHOLDER` / empty stub patterns | None | No marker-based stub found. |
| `firmware/src/main.cpp` | 295-406 | Duplicate protocol implementation | 🛑 Blocker | Tested protocol is bypassed. |
| `firmware/src/main.cpp` | 482-490 | Readiness state discarded | 🛑 Blocker | Hardware probes can ACK after failed initialization. |
| `guide.py` | 492-501 | Failure-to-pass without fresh state | 🛑 Blocker | Same observation can change N→Y. |
| `qualification.py` | 579-584 | Required U accepted as pass | 🛑 Blocker | Unperformed interruption gates qualify transport. |
| `evidence.py` | 1245-1263 via CLI dispatch | Accepted requirements ignored | 🛑 Blocker | Commands print success without requested proof. |

## Review Reconciliation

`01-REVIEW.md` reported 18 critical and 8 warning issues. None were ignored. The table records the independent verification disposition and its effect on this verdict.

| Review ID | Disposition | Verification effect |
|---|---|---|
| CR-01 | Confirmed at `main.cpp:295-406`; no protocol include/use. | Blocks SC2, HARD-03, Plans 05/06. |
| CR-02 | Confirmed in source and accepted artifact; same boot ID across reconnects. | Blocks SC3 and recovery freshness. |
| CR-03 | Confirmed at `qualification.py:579`; accepted result has two required U rows. | Blocks SC3/SC4 and USB eligibility. |
| CR-04 | Confirmed; manifest has latency limits, result has no latency fields/checks. | Blocks measured USB suitability. |
| CR-05 | Confirmed at schema `payload.additionalProperties:false` plus duplicate `event`. | Blocks schema parity/frozen protocol truth. |
| CR-06 | Confirmed by executable probe (`v:true` accepted; list type raises TypeError). | Blocks typed malformed-frame rejection. |
| CR-07 | Confirmed at `protocol.cpp:347-350,390-428`; wide version narrows and end cursor is not checked. | Blocks host/firmware parity. |
| CR-08 | Confirmed; lock verification does not call full result validator and trusts copied interruption IDs. | Blocks immutable qualification/selection. |
| CR-09 | Confirmed; selection verifier omits full purpose/transport/canonical-source invariants. | Blocks selection proof, though current source is USB. |
| CR-10 | Verifier defect confirmed. Independent object/ELF inspection proves the current build is USB-only. | Current composition truth passes; automated proof remains a blocking artifact defect. |
| CR-11 | Confirmed; archive verifier compares only a subset of the full lineage. | Blocks archive proof. |
| CR-12 | Confirmed; only top-level key names are scanned. Current archive has no detected secret field. | Current corpus is clean; advertised no-secret verifier is not authoritative. |
| CR-13 | Confirmed; physical validator lacks exact row/count/status/source checks. Current 30-row artifact was independently checked and is complete. | Current SC1 evidence passes; Plan 03 evidence invariant fails. |
| CR-14 | Confirmed at `run_recover()`: requested interruption is only copied into evidence text. | Blocks action-specific recovery truth. |
| CR-15 | Confirmed at recovery-tour state path/index handling. | Blocks trustworthy utility restart/recovery tour. |
| CR-16 | Confirmed at `guide.py:492-501` and CLI loop `:477-487`. | Blocks fresh physical confirmation invariant. |
| CR-17 | Confirmed by source and official commands; flags are accepted but not consulted. | Blocks selection/archive verification claims. |
| CR-18 | Confirmed; `boardReady` is local to setup/render only. | Blocks fail-closed physical stimulus truth. |
| WR-01 | Confirmed host/wire/ArduinoJson digest paths differ. | Supports protocol parity failure. |
| WR-02 | Confirmed short-write result ignored and fallback read exception can escape close path. | Reliability warning under HARD-03. |
| WR-03 | Confirmed extras excluded from SHA256SUMS; additionally, accepted qualification `result.json` actually fails its checksum. | Escalated to blocking immutable-evidence failure. |
| WR-04 | Confirmed absolute workstation paths in every final lock/archive. | Portability warning; not the primary blocker. |
| WR-05 | Confirmed initial tracer result lacks bound human response/token. | Plan 01-01 T1 fails. |
| WR-06 | Confirmed queue test sends duplicate rather than filling queue; no normal consume operation. | Test does not prove queue bound. |
| WR-07 | Confirmed `observeQueue(usbLink.available())` measures bytes. | Qualification metric is mislabeled/inapplicable. |
| WR-08 | Confirmed `PhysicalMap physicalMap` is never read after construction. | Artifact is orphaned from runtime behavior. |

## Human Verification Required

No additional human-only check can close the blocking findings. The delivered-unit visual confirmations already exist in immutable artifacts and were credited for SC1. The remaining gaps are observable code, protocol, recovery, qualification, checksum, and verifier defects that require implementation and fresh targeted evidence—not another verbal confirmation.

## Deferred Items

None. Later Phase 4 mentions broader recovery, but Phase 1 explicitly owns reset, unplug, link interruption, selected transport, HARD-01, and HARD-03. Deferring these failures would reduce the Phase 1 roadmap contract.

## Gaps Summary

The current delivered build is concretely USB-only, the physical map artifact is complete and hash-consistent, the renderer/host UI are substantive, exact-device challenge pairing exists, and a 3,800-frame traffic artifact exists. Those facts do not establish the phase goal because the selected transport was admitted through an untested duplicate firmware parser, recovery does not prove fresh boot identity, frozen latency and required interruption gates were not enforced, and the accepted qualification result was modified after its checksum set was finalized. The selection/build/archive tools then accepted that chain while ignoring several advertised requirements.

The phase must remain blocked until the production runtime uses the frozen codec/session, recovery and qualification gates are enforced, physical/evidence state machines fail closed, immutable evidence is regenerated without checksum drift, and selection/archive verification recomputes the full graph. Exact Python 3.11 also remains an explicit unoverridden must-have failure.

---

_Verified: 2026-08-16T20:40:53Z_
_Verifier: the agent (gsd-verifier)_
