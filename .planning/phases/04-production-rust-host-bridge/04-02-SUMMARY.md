---
phase: 04-production-rust-host-bridge
plan: "02"
subsystem: testing
tags: [rust, python, serde-json, sha256, fixtures, parity]

# Dependency graph
requires:
  - phase: 03.2-focus-then-hold-usb-keyboard
    provides: "Closed v2 protocol, authoritative projection/focus behavior, Codex normalization, and lifecycle/reconnect contracts used as the Python oracle."
  - phase: 04-production-rust-host-bridge
    provides: "Phase 4 migration contract and threat model for exporter-independent parity fixtures."
provides:
  - "Exporter-independent Rust integration validator for exact four-file oracle corpora, canonical hashes, bounds, privacy, and closed protocol types."
  - "Deterministic Python black-box exporter covering protocol, projection/focus, Codex, and lifecycle behavior."
  - "Four source-hash-linked JSON corpora proven byte-identical across isolated generation roots."
affects: [rust-host-bridge, differential-parity, protocol, projection, focus, codex, lifecycle]

# Actuals (#2632)
# 109018 changed-file bytes / 4, rounded up; task commits plus this summary commit.
actuals:
  tokens: 27255
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added:
    - "serde_json and sha2 0.10.8 in a temporary fixture-only Rust manifest; no production manifest was changed."
  patterns:
    - "Canonical compact sorted-key JSON for case and corpus digests."
    - "Fixed four-file corpus allowlist with eleven reopened source-hash records."
    - "Recursive privacy gate rejecting sensitive keys and absolute-path-shaped values before fixture writes."
    - "Two isolated exporter runs followed by Rust validation before committing bytes."

key-files:
  created:
    - host/herdr_keypad/native/tests/python_oracle_fixture.rs
    - host/herdr_keypad/tests/export_rust_oracle.py
    - host/herdr_keypad/native/tests/fixtures/protocol.json
    - host/herdr_keypad/native/tests/fixtures/projection-focus.json
    - host/herdr_keypad/native/tests/fixtures/codex.json
    - host/herdr_keypad/native/tests/fixtures/lifecycle.json
  modified: []

key-decisions:
  - "Keep Rust validation fixture-only and exporter-independent; production Rust has no Python executable or module dependency."
  - "Use stable public Python module behavior and normalized descriptors rather than serializing Python objects, upstream payloads, prompts, transcripts, or raw errors."
  - "Use an exact sha2 0.10.8 temporary validator dependency because the available Rust/Cargo 1.82 toolchain cannot compile the researched sha2 0.11/edition-2024 dependency chain; production dependency ownership remains with Plan 01."

patterns-established:
  - "Every case carries a stable name, normalized input, observable expected output, and canonical case hash."
  - "Every corpus carries schema version, family, fixed source lineage, bounded cases, and a canonical fixture hash."
  - "The closed v2 protocol admits exactly agent_snapshot, snapshot_ack, focus_intent, and focus_result in parity coverage."

requirements-completed: [RUST-01, RUST-02, RUST-08]

# Coverage metadata
coverage:
  - id: D1
    description: "Fixture-only Rust validator rejects tampered lineage, duplicate/unknown/oversized records, sensitive values, absolute paths, missing files/families, and protocol expansion while accepting synthetic valid corpora."
    requirement: RUST-02
    verification:
      - kind: unit
        ref: "cargo test --manifest-path host/herdr_keypad/native/Cargo.toml --test python_oracle_fixture synthetic_"
        status: pass
    human_judgment: false
  - id: D2
    description: "Deterministic exporter emits protocol, projection/focus, Codex, and lifecycle traces with source lineage and privacy/schema gates."
    requirement: RUST-01
    verification:
      - kind: integration
        ref: "host/herdr_keypad/tests/export_rust_oracle.py --verify-determinism --rust-manifest host/herdr_keypad/native/Cargo.toml"
        status: pass
    human_judgment: false
  - id: D3
    description: "Committed corpus is generated only after two isolated roots match byte-for-byte and both pass the Rust validator; focused Python oracle modules remain green."
    requirement: RUST-08
    verification:
      - kind: integration
        ref: "focused unittest modules: test_protocol, test_projection, test_focus, test_codex, and PluginLifecycleTests.test_alive_bridge_reconnects_and_acks_complete_snapshot_before_ready"
        status: pass
      - kind: integration
        ref: "exporter --verify-determinism Rust validation in both temporary roots"
        status: pass
    human_judgment: false

# Metrics
duration: 16 min
completed: 2026-08-30
status: complete
---

# Phase 04 Plan 02: Deterministic Python oracle summary

**Canonical Python oracle traces with independent Rust lineage/privacy validation for protocol, projection/focus, Codex, and lifecycle parity.**

## Performance

- **Duration:** approximately 16 minutes (from first task commit through summary preparation)
- **Started:** 2026-08-30T00:48:14Z
- **Completed:** 2026-08-30T01:03:42Z
- **Tasks:** 2/2
- **Files modified:** 6 new implementation/test/fixture paths

## Accomplishments

- Added an exporter-independent Rust integration validator that accepts only the versioned, exact four-file corpus; checks canonical case/corpus hashes, source lineage, explicit bounds, recursive privacy, and the closed four-frame protocol vocabulary.
- Added synthetic validator tests proving valid corpora pass and tampered duplicate-name, unknown-field, oversized, sensitive-key, absolute-path, missing-family, and fifth-protocol-type corpora fail closed.
- Added a deterministic Python exporter using stable public behavior from the frozen bridge, projection, focus, Codex, Herdr, and protocol modules. It covers accepted/rejected protocol frames, duplicate/nesting/null-versus-zero/session/sequence behavior, 4096-byte boundaries, projection ordering and revision rules, focus outcomes and retry, Codex baseline/merge/refetch/auth/offline/stale/redaction behavior, and lifecycle readiness/reconnect/discard/idle behavior.
- Added four source-hash-linked JSON corpora and a two-root determinism proof that byte-compares the complete corpus, compares SHA-256 manifests, validates both roots with Rust, and writes committed bytes only after those checks pass.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build the independent Rust fixture validator**
   - `218a79f` — `test(04-02): add independent fixture validator cases` (RED)
   - `5336f48` — `feat(04-02): validate oracle fixture lineage and privacy` (GREEN)
2. **Task 2: Export and prove deterministic Python behavioral traces**
   - `3214dd7` — `feat(04-02): freeze deterministic Python behavioral traces`

**Plan metadata:** This worktree intentionally does not update shared `STATE.md` or `ROADMAP.md`; the phase orchestrator owns those files.

## Files Created/Modified

- `host/herdr_keypad/native/tests/python_oracle_fixture.rs` — Rust-only corpus schema, bounds, hash, source-lineage, privacy, and closed-protocol validator with synthetic tamper tests.
- `host/herdr_keypad/tests/export_rust_oracle.py` — deterministic public-behavior exporter, schema/redaction self-tests, isolated-root proof, and Rust-validator invocation.
- `host/herdr_keypad/native/tests/fixtures/protocol.json` — accepted/rejected protocol and wire-boundary traces.
- `host/herdr_keypad/native/tests/fixtures/projection-focus.json` — projection ordering/revision and focus authorization/outcome traces.
- `host/herdr_keypad/native/tests/fixtures/codex.json` — Codex normalization, freshness, auth, outage, child-exit, and redaction traces.
- `host/herdr_keypad/native/tests/fixtures/lifecycle.json` — readiness, reconnect, deferred-focus discard, event-stream idle, and independent outage traces.

## Decisions Made

- The Rust validator remains a fixture-only integration test and reads its root only through `HERDR_ORACLE_FIXTURE_ROOT`; it neither imports nor spawns Python.
- Fixture inputs and expected values are normalized descriptors and public observable results. The exporter does not persist Python object structure, host paths, account identity, prompts, transcripts, raw stderr/stdout, or upstream payloads.
- The temporary local validator manifest pinned `sha2 = "=0.10.8"` for Rust 1.82/Cargo compatibility. It was removed with its generated lockfile and target directory; Plan 01 owns the production Cargo manifest and lockfile.

## Deviations from Plan

### Compatibility adjustment

**1. [Rule 3 - Blocking compatibility] Used an exact compatible temporary `sha2` pin for local validation**
- **Found during:** Task 1 (Build the independent Rust fixture validator)
- **Issue:** The researched `sha2` 0.11 dependency chain requires edition 2024 and cannot compile under the available Rust/Cargo 1.82 toolchain.
- **Fix:** Created a temporary uncommitted `host/herdr_keypad/native/Cargo.toml` with `serde_json` and exact `sha2 = "=0.10.8"` solely to compile and run the fixture validator, then removed the manifest, generated lockfile, and target directory. No shared production manifest was touched.
- **Files modified:** None retained; temporary files removed.
- **Verification:** Rust synthetic validator and both isolated exporter roots passed.
- **Committed in:** `5336f48` (validator implementation; temporary compatibility files were not committed).

**Total deviations:** 1 compatibility adjustment; no production dependency or architecture change.
**Impact on plan:** None on delivered behavior. Plan 01 remains the sole owner of production Cargo manifest and lockfile integration.

## Issues Encountered

- No unresolved implementation issues. The focused Python command ran 37 tests successfully, and the exporter determinism proof ran the Rust validator successfully against both temporary roots.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Rust implementation plans can consume the four committed corpora through the fixed envelope and independent validator.
- The source hash list and case names provide the parity contract for subsequent protocol, projection/focus, Codex, and lifecycle ports.
- Shared `STATE.md` and `ROADMAP.md` updates are intentionally left to the phase orchestrator for merge-safe bookkeeping.

---
*Phase: 04-production-rust-host-bridge*
*Plan: 02*
*Completed: 2026-08-30*

## Self-Check: PASSED

- All six planned implementation/test/fixture paths and this SUMMARY.md exist.
- Commits `218a79f`, `5336f48`, and `3214dd7` resolve to committed objects.
- No temporary Cargo manifest, lockfile, target directory, or generated Python cache remains in the worktree.
