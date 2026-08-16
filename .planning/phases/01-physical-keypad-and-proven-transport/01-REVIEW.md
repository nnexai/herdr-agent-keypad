---
phase: 01-physical-keypad-and-proven-transport
reviewed: 2026-08-16T20:29:44Z
depth: standard
files_reviewed: 35
files_reviewed_list:
  - artifacts/phase1/20260816T083124Z-c8553c/manifest.json
  - artifacts/phase1/20260816T083124Z-c8553c/result.json
  - artifacts/phase1/20260816T083124Z-c8553c/SHA256SUMS
  - tools/phase1_bringup/src/phase1_bringup/__main__.py
  - firmware/src/board/board_adapter.cpp
  - firmware/src/board/board_adapter.h
  - firmware/src/board/physical_map.h
  - firmware/src/ui/bringup_renderer.h
  - firmware/src/main.cpp
  - tools/phase1_bringup/src/phase1_bringup/guide.py
  - tools/phase1_bringup/src/phase1_bringup/protocol.py
  - tools/phase1_bringup/src/phase1_bringup/ui.py
  - tools/phase1_bringup/src/phase1_bringup/evidence.py
  - tools/phase1_bringup/src/phase1_bringup/discovery.py
  - tools/phase1_bringup/src/phase1_bringup/pairing.py
  - tools/phase1_bringup/src/phase1_bringup/serial_link.py
  - host/udev/99-herdr-keypad.rules
  - protocol/schema/v1.json
  - protocol/fixtures/v1-golden.json
  - firmware/src/protocol/protocol.h
  - firmware/src/protocol/protocol.cpp
  - test/protocol/test_main.cpp
  - platformio.ini
  - artifacts/phase1/latest/result.json
  - artifacts/phase1/locks/usb-eligibility.json
  - tools/phase1_bringup/src/phase1_bringup/qualification.py
  - tools/phase1_bringup/ARCHIVED
  - artifacts/phase1/qualification-manifest.json
  - firmware/src/metrics/proof_metrics.h
  - firmware/src/transport/link.h
  - firmware/src/transport/usb_cdc.cpp
  - tools/phase1_bringup/pyproject.toml
  - tools/phase1_bringup/requirements.lock
  - tools/phase1_bringup/src/phase1_bringup/__init__.py
  - artifacts/phase1/20260816T190217Z-cc059b/result.json
findings:
  critical: 18
  warning: 8
  info: 0
  total: 26
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-08-16T20:29:44Z
**Depth:** standard
**Files Reviewed:** 35
**Status:** issues_found

## Summary

The Phase 01 implementation has serious correctness and evidence-integrity defects. Most importantly, the flashed firmware bypasses the protocol implementation exercised by the golden tests; the frozen qualification can pass without satisfying required interruption and latency gates; and the selection/build/archive verifiers do not re-establish the lineage, composition, or secret-free claims they print. The archived hashes currently resolve and match on this workstation, and no hardcoded Wi-Fi credentials, API keys, passwords, or private-key material were found in the reviewed files, but the verification code can accept self-consistent forged or semantically false evidence.

The summary-derived scope was cross-checked against commits `3912fc6^..b527526`; production files omitted by summary `key-files` were added to the review. The concrete qualification result referenced by the USB eligibility and archive locks was also inspected to verify source claims. No project validation commands, builds, linters, formatters, or test suites were run.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Flashed firmware bypasses the frozen protocol implementation

**Severity:** BLOCKER  
**File:** `firmware/src/main.cpp:295-406` (contrasted with `firmware/src/protocol/protocol.cpp:302-515`)  
**Issue:** `main.cpp` implements a second parser and session path instead of calling `FrameCodec` or `ProtocolSession`. The flashed path does not enforce an exact envelope, required `reply_to`, identifier bounds, positive/monotonic sequences, boot/session equality, duplicate/out-of-order rejection, queue bounds, or closed payload shapes. The native golden test at `test/protocol/test_main.cpp:95-100` therefore tests code that is not used to admit commands on the device. Replayed or cross-session `probe` frames—including `REBOOT`—can execute despite the claimed frozen semantics.  
**Fix:** Delete the duplicate admission logic and route every complete frame through the production codec/session before any side effect. Keep one explicit, tested bootstrap transition for adopting the host session, then enforce boot/session/sequence state for all subsequent frames. Exercise that integrated path, not a test-only parser.

### CR-02: Boot IDs are not fresh, and accepted evidence proves reuse across resets

**Severity:** BLOCKER  
**File:** `firmware/src/main.cpp:38-43,482-490`; `artifacts/phase1/20260816T190217Z-cc059b/result.json:1`; `artifacts/phase1/qualification-manifest.json:1`  
**Issue:** The boot identifier is `deviceId + "-" + millis()` during startup. Startup timing is repeatable, and the accepted qualification result records the identical boot ID `0000fccb0deabf8c-2385` for the initial session and every reconnect after software reset, flash/reset, same-port reconnect, different-port reconnect, and reset/unplug. The frozen manifest explicitly requires `fresh_boot_and_session` for every interruption. Neither recovery nor qualification compares the new boot ID with the prior one, so stale cross-boot work cannot be distinguished as claimed.  
**Fix:** Generate a per-boot nonce from a suitable hardware RNG and include it in `boot_id`. Record pre/post boot and session IDs per interruption and require the expected change before a row can pass.

### CR-03: Required interruption rows may all be unavailable and qualification still passes

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/qualification.py:521-584`; `artifacts/phase1/qualification-manifest.json:1`  
**Issue:** Every frozen interruption row is marked `applicable: true` and `required: true`, but `rows_ok` accepts any `U` response with a reason. A run can mark all seven required recovery scenarios unavailable and still become `status: "pass"` if traffic and metrics pass. The accepted artifact already contains `U` for two required rows. This is not merely preservation of an unavailable observation; it makes an unperformed required gate eligible for transport selection.  
**Fix:** Require `Y` plus action-specific machine recovery evidence for each applicable required row. If a scenario is genuinely unavailable, record it as not applicable in an authoritative profile revision or keep qualification incomplete/non-eligible; do not convert a required `U` into strict PASS.

### CR-04: Frozen latency gates are never measured or enforced

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/qualification.py:227-246,377-629`; `artifacts/phase1/qualification-manifest.json:1`  
**Issue:** The manifest freezes p99 acknowledgement limits of 250 ms/1000 ms and a 10-second endpoint-return/handshake limit. The runner records no acknowledgement latency distribution or interruption handshake duration, and `validate_qualification_result` checks none of those limits. The accepted result has no latency fields, yet is reported as every frozen gate passing.  
**Fix:** Measure the three frozen latency classes with a monotonic clock, persist sample counts and computed p99/maximum values, validate them against the manifest, and forbid PASS when any required latency measurement is absent or over limit.

### CR-05: The JSON Schema rejects every real non-empty payload

**Severity:** BLOCKER  
**File:** `protocol/schema/v1.json:16-42`  
**Issue:** The root payload subschema declares `additionalProperties: false` without declaring any payload properties. Properties required by separate `allOf` branches do not become recognized properties for that subschema, so a standards-compliant Draft 2020-12 validator rejects every real hello/probe/event/metrics payload. The extension object also defines `event` twice at lines 36 and 39, so ordinary JSON parsers silently discard the encoder form. `load_schema` and the golden check inspect only a few metadata tokens and never validate fixture frames against the schema.  
**Fix:** Define a closed payload schema per frame type in `$defs`, select it with `oneOf`/conditional references, and use `unevaluatedProperties: false` or local `properties` correctly. Remove duplicate keys and run every golden accepted/rejected vector through a real Draft 2020-12 validator.

### CR-06: Malformed host frames can escape validation or be accepted as v1

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/protocol.py:63-89,129-136,148-165`  
**Issue:** Membership checks such as `frame["type"] not in FRAME_TYPES`, `payload["request"] not in {...}`, and direction checks run before confirming a string type. A JSON array/object there is unhashable and raises `TypeError`, which `classify_line` and the top-level CLI do not convert to a typed protocol rejection. In addition, Python equality makes `True == 1`, so `v: true` and hello `protocol: true` are accepted as protocol v1. Malformed device input can therefore terminate a host run or cross a version gate.  
**Fix:** Type-check all discriminants before set membership, require `_is_int` for both version fields, and convert `TypeError`, `RecursionError`, and other parser-bound failures into stable rejection results.

### CR-07: The C++ codec accepts invalid versions and trailing garbage

**Severity:** BLOCKER  
**File:** `firmware/src/protocol/protocol.cpp:347-350,390-425`  
**Issue:** Version is narrowed to `uint8_t` before validation, so `v:257` becomes `1` and passes. After the top-level closing brace, the decoder never requires the cursor to reach the end, so a valid envelope followed by arbitrary non-whitespace bytes before LF can also pass. The recursive generic pre-parser has no nesting bound, allowing a bounded but deeply nested payload to exhaust an embedded stack before flat payload validation. These results diverge from the host codec and the closed schema.  
**Fix:** Validate the wide parsed version before narrowing, require only whitespace and end-of-input after the envelope, and enforce a small nesting limit or parse the expected flat payload directly.

### CR-08: Qualification locks can verify a semantic false PASS

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/evidence.py:70-170`  
**Issue:** Neither pointer resolution nor lock verification calls `validate_qualification_result`. Under `strict-traffic`, absent `expected`, `sent`, `received`, and `acknowledged` fields all compare equal as `None`, so a fabricated result with only zero failure counters can pass. Metrics, availability flags, physical overlap, latency, and interruption outcomes are not validated. `complete-interruption-matrix` trusts a freely copied `lock["interruption_ids"]` rather than the hashed result, and `immutable-linkage` has no dedicated enforcement. `verify_qualification_linkage(..., require_immutable_traffic=True)` also verifies no file if `traffic_path` is omitted.  
**Fix:** Re-run complete manifest-driven semantic validation while resolving and verifying every lock; require typed counters and metrics; derive interruption coverage/outcomes from the reopened result; compare the embedded traffic path to the concrete reopened file; and reject a required immutable-traffic check when no concrete file is verified.

### CR-09: Selection verification omits the invariants that make it a USB selection

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/evidence.py:192-276`  
**Issue:** `verify_selection_lock` does not re-check candidate purpose `selection-candidate`, source purpose `usb-eligibility`, USB-lock purpose, either lock's `transport == "usb"`, or manifest equality across the locks. It accepts any absolute selected source file whose caller-supplied hash matches rather than binding the path to repository `firmware/src/transport/usb_cdc.cpp`. A hand-authored selection can therefore verify as `selected-usb` without proving the generator's decision invariants.  
**Fix:** Recompute all generator invariants in the verifier, enforce the canonical repository source path after resolving containment/no-symlink ancestors, and require both qualification locks to be validated strict USB proofs of the same manifest/result/traffic.

### CR-10: Build composition and Wi-Fi-symbol absence are asserted, not proved

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/evidence.py:314-396`  
**Issue:** Composition is accepted through substring searches that comments or unrelated sections can satisfy. The build directory is searched only for filenames containing `wifi_tls`; no object or binary symbol inspection occurs, yet `unselected_symbol_present` is unconditionally written as `False`. `verify_build_lock` later trusts three booleans and hashes arbitrary absolute files without binding canonical platformio/main/binary paths or selected source back to the selection lock. The advertised “source, object, and symbol absent” proof is therefore not established.  
**Fix:** Parse the selected PlatformIO environment, bind all paths to canonical repository/build locations, inspect the actual build graph/object list, and inspect the final ELF symbol table. Recompute those facts during verification rather than trusting booleans.

### CR-11: Archive verification allows unrelated locks and false path/traffic claims

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/evidence.py:399-474`  
**Issue:** The verifier independently opens a valid selection, build, and qualification lock but does not prove that the build names that selection or that the qualification proof is the one selected. It does not compare archive `result_path`, `traffic_path`, `traffic_sha256`, or `binary_path` with their authoritative locks. Valid but unrelated locks, or false concrete paths paired with copied hashes, can be aggregated into a passing archive.  
**Fix:** Re-establish the full graph: build selection hash equals the selected lock; selection and qualification manifest/result/traffic paths and hashes all match; archive paths and hashes equal the source locks; and the archive object has an exact closed field set.

### CR-12: `no-secret-output` is bypassable by nesting or innocuous keys

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/evidence.py:442-474`  
**Issue:** Secret checking scans only top-level key names. Unknown fields are allowed, nested objects are not traversed, and values are never examined. For example, `{"metadata":{"password":"..."}}` or `{"notes":"private_key=..."}` passes. The CLI advertises `--require no-secret-output`, so this is a security control bypass even though the current reviewed archive contains no credential material.  
**Fix:** Enforce an exact allowlisted archive schema with no extension fields, reject secret-bearing data recursively at every linked output boundary, and make the CLI requirement explicit rather than relying on a top-level substring scan.

### CR-13: Physical and machine evidence validators accept fabricated or incomplete PASS

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/evidence.py:522-603,795-838`; `tools/phase1_bringup/src/phase1_bringup/__main__.py:661-743`  
**Issue:** A physical row with `human_response: "N"` and `physical_status: "pass"` is accepted; a physical map with one arbitrary row can satisfy `--require physical-map`; and result PASS is not derived from rows. Machine verification requires only that seven gate names appear, not the fixed steps/counts, successful mode/status, typed reply sequences, or complete 30-row observation set. Confirmed evidence records only a hash of the source `SHA256SUMS` file, and no verifier reopens that source or checks `source_machine_checksum`. Seven fabricated rows can therefore become a separately verified physical PASS.  
**Fix:** Validate the exact canonical step set/counts and response/status matrix; derive overall status from all rows; require successful machine-run state; hash the actual source manifest/result/checksum set; store its concrete contained path; and reopen/revalidate that source when confirming or verifying.

### CR-14: `recover` can label a generic reconnect as any requested interruption

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/__main__.py:280-334`  
**Issue:** The requested interruption is only copied into manifest/result text and prefixed onto generic reconnect details. The command neither induces nor measures reset, flash/reset, port movement, endpoint renumbering, or utility restart, and it does not compare pre/post boot, session, descriptor, or endpoint facts. An ordinary reconnect can be recorded as PASS for every CLI choice.  
**Fix:** Define action-specific preconditions and pre/post facts for each interruption, require the operator action before reconnect, and verify the expected boot/session/path transition before writing PASS.

### CR-15: Recovery-tour resume state is forgeable and path-traversable

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/__main__.py:336-359,367-455`  
**Issue:** `--resume` is interpolated into a path without validating it as one component or enforcing containment. A matching external JSON file can be overwritten and, when the loop completes, deleted. The state is also unauthenticated: setting `current_index` to the step count skips the tour, deletes state, prints completion, and returns success without checking any step artifact.  
**Fix:** Apply the existing bounded ID pattern, resolve and enforce containment/no-symlink ancestors, atomically persist a closed state schema, and on every resume derive progress from hash-verified immutable step artifacts rather than trusting `current_index`.

### CR-16: Guided `N` can be changed to PASS without a repeat or new observation

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/guide.py:476-524`; `tools/phase1_bringup/src/phase1_bringup/__main__.py:477-489`  
**Issue:** An `N` records a failed row but leaves the same step and stable machine fact active. The CLI immediately asks again; a following `Y` advances without re-stimulating or linking a typed replacement. Final status depends only on `gate_index`, so evidence containing an unresolved failure can end as PASS on the same observation.  
**Fix:** Make `N` terminal for the run, or require explicit `R`, a fresh stimulus/event, and a typed replacement link before a later PASS. Derive result status from the complete row history, not only the cursor position.

### CR-17: Advertised CLI verification requirements and composition flags are ignored

**Severity:** BLOCKER  
**File:** `tools/phase1_bringup/src/phase1_bringup/__main__.py:1070-1075,1112-1114,1156-1172,1245-1263`  
**Issue:** `verify-evidence` parses `immutable-selection`, `archived-source`, `exact-manifest-hash`, and `no-secret-output` but dispatches solely on file kind and never checks which requirements were requested. In self-check, `--exactly-one-adapter` and `--unselected-source-object-symbol-absent` are registered but never consulted; either can be supplied without adding any check. The CLI still prints “Evidence verified” or composition success.  
**Fix:** Map every accepted requirement/flag to a concrete verifier assertion, reject incompatible or unsupported requirements, and print success only after all requested checks return proof.

### CR-18: Failed board initialization still acknowledges hardware probes

**Severity:** BLOCKER  
**File:** `firmware/src/main.cpp:378-404,482-490`  
**Issue:** `boardReady` affects only the initial screen and is then discarded. The firmware continues to touch displays/brightness/inputs and returns `probe_ack {accepted:true}` even when `board.begin()` failed. Machine evidence can therefore claim a successful physical stimulus on an uninitialized board.  
**Fix:** Persist readiness state, avoid hardware calls after failed initialization, and reject every hardware-dependent probe with a stable error until the board is successfully initialized.

## Warnings

### WR-01: Digest canonicalization differs across all three protocol implementations

**Severity:** WARNING  
**File:** `firmware/src/main.cpp:46-77,312-318`; `firmware/src/protocol/protocol.cpp:151-154,289-295`; `tools/phase1_bringup/src/phase1_bringup/protocol.py:54-60`  
**Issue:** The host hashes sorted-key canonical JSON, the standalone C++ codec hashes the exact wire payload substring (including order/whitespace), and the flashed firmware hashes ArduinoJson reserialization order. Semantically identical frames can receive different digest decisions; Unicode behavior also disagrees with the schema's UTF-8 wording.  
**Fix:** Specify one byte-exact canonicalization, generate those bytes once, hash and transmit the same bytes, and add vectors for reordered keys, whitespace, escapes, and non-ASCII input.

### WR-02: Serial short writes and fallback read failures do not close stale links correctly

**Severity:** WARNING  
**File:** `tools/phase1_bringup/src/phase1_bringup/serial_link.py:56-80`; `tools/phase1_bringup/src/phase1_bringup/protocol.py:239-243`; `firmware/src/main.cpp:77-88`  
**Issue:** Host writes ignore the byte count returned by pyserial, so partial frames are treated as sent. Firmware likewise advances sequence before knowing a complete frame was written and does not retry/close on a short positive write. In `SerialLink.readline`, an exception from the no-size fallback inside the `except TypeError` block bypasses the sibling exception handler, leaving the descriptor open.  
**Fix:** Implement bounded write-all semantics with explicit short-write failure/close, and wrap both read call forms in one error path that always closes stale state.

### WR-03: Extra evidence files are outside `SHA256SUMS`, and symlink ancestors remain mutable

**Severity:** WARNING  
**File:** `tools/phase1_bringup/src/phase1_bringup/evidence.py:183-189,685-736,822-838`  
**Issue:** `EvidenceWriter.write` accepts extra files such as traffic but includes only manifest/result in `SHA256SUMS`; generic `verify()` neither hashes nor rejects extras. `_fixed_file` rejects only a symlink final component, and physical evidence accepts a symlink run directory, so a retargetable ancestor can satisfy “concrete/non-symlink” checks. Qualification adds a separate traffic hash, but the generic immutable-evidence contract remains weaker than advertised.  
**Fix:** Include every evidence file in a closed checksum manifest and reject undeclared files. Resolve paths once, reject symlinks in every ancestor, and enforce repository/evidence-root containment where applicable.

### WR-04: Archive and locks are tied to one workstation by absolute paths

**Severity:** WARNING  
**File:** `tools/phase1_bringup/ARCHIVED:1`; `artifacts/phase1/locks/usb-eligibility.json:1`; `tools/phase1_bringup/src/phase1_bringup/evidence.py:119-137,419-438`  
**Issue:** Durable lock files record `/home/nnex/dev/prj/lilygo-t3/...` paths. Hashes currently match, but moving the archive, cloning it elsewhere, or changing the checkout path makes verification fail even when every archived byte is present. This undermines the archive's maintainability and portability.  
**Fix:** Store repository/evidence-root-relative paths plus a declared root identity, then resolve with containment checks at verification time.

### WR-05: The initial accepted physical evidence contains no bound human confirmation

**Severity:** WARNING  
**File:** `artifacts/phase1/20260816T083124Z-c8553c/result.json:1`  
**Issue:** The result contains only `"physical_observation":"confirmed"`; it has no human response, stable step/run token, timestamp, or confirmation record. Its checksums match, but hashes preserve the assertion rather than prove the summary's explicit `Y PANEL-1` claim.  
**Fix:** Treat this artifact as superseded/non-qualifying or migrate the acceptance reference to an immutable artifact using the later row schema with explicit run/step-bound human confirmation.

### WR-06: Protocol queue state has no normal consume operation, and its test does not exercise queue-full behavior

**Severity:** WARNING  
**File:** `firmware/src/protocol/protocol.h:72-95`; `firmware/src/protocol/protocol.cpp:483-521`; `test/protocol/test_main.cpp:145-162`  
**Issue:** Every dispatched frame increments `pending_count_`, but the API exposes only wholesale `discard_pending`, not dequeue/completion. An integrated consumer would reach queue full after 16 lifetime dispatches unless it discards all state. The test named `test_queue_bound_and_discard` sends the same frame twice and asserts duplicate, never a distinct frame that reaches `queue_full`.  
**Fix:** Add an explicit dequeue/dispatch-complete operation and a test that fills the queue with distinct monotonic frames, rejects the next frame as queue-full, then proves consumption restores capacity.

### WR-07: `queue_high_water` measures serial bytes, not the protocol queue

**Severity:** WARNING  
**File:** `firmware/src/main.cpp:409-434`; `firmware/src/metrics/proof_metrics.h:49-54`  
**Issue:** `observeQueue(usbLink.available())` records buffered transport bytes while the named protocol queue is measured in frames and is not integrated into `main.cpp`. The accepted result reports `queue_high_water: 64`, but that value cannot demonstrate the 16-frame session queue bound claimed by the phase.  
**Fix:** Instrument the actual protocol pending-frame queue in frame units and name any transport-byte backlog as a separate metric.

### WR-08: `PhysicalMap` is dead state and cannot mediate the hardcoded mappings

**Severity:** WARNING  
**File:** `firmware/src/main.cpp:25-28,228-267`; `firmware/src/board/physical_map.h:98-138`  
**Issue:** A global `PhysicalMap` is instantiated but never read or updated. Key, click, LED, and panel mappings are hardcoded directly in stimulus logic, so the component described as the explicit physical observation boundary cannot affect device behavior and can drift independently.  
**Fix:** Either remove the unused runtime object and clearly make the map evidence-only, or initialize and consume it through `BoardAdapter` as the single mapping source, failing closed when a mapping is unavailable.

---

_Reviewed: 2026-08-16T20:29:44Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
