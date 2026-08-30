---
phase: 04-production-rust-host-bridge
plan: "10"
subsystem: parity-resource-release-evidence
tags: [rust, python, parity, resources, ci, release, provenance, privacy]

# Dependency graph
requires:
  - phase: 04-production-rust-host-bridge
    provides: Integrated native bridge, closed bundle verifier, and isolated Linux/macOS release producers from Plans 07-09
provides:
  - Black-box frozen Python-oracle parity, protocol admission, recovery, resource-bound, and production-surface integration tests
  - Fail-closed commit/run-bound Phase 04 evidence collector with synthetic rejection coverage
  - Linux contract and current-run artifact aggregation workflow with canonical checksum sidecar
  - CI-only final evidence publication; no locally fabricated Phase 04 release record
affects: [native-release, parity-evidence, release-artifacts, production-cutover]

# Actuals (#2632)
actuals:
  tokens: 18619
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Public-boundary integration tests consume the frozen oracle corpus and exercise direct production binaries without private object-state assertions
    - Evidence collection uses closed artifact directories, exact commit/run/ref identity, reopened manifest/provenance hashes, and bounded canonical output
    - CI downloads each commit-named producer artifact with an explicit current workflow run ID before aggregation

key-files:
  created:
    - host/herdr_keypad/native/tests/black_box_parity.rs
    - host/herdr_keypad/native/tests/resource_bounds.rs
    - host/herdr_keypad/native/tests/production_surface.rs
    - host/herdr_keypad/release/collect_phase4_evidence.py
    - host/herdr_keypad/release/test_collect_phase4_evidence.py
    - .planning/phases/04-production-rust-host-bridge/04-10-SUMMARY.md
  modified:
    - .github/workflows/native-release.yml

decisions:
  - "Keep phase04-release-evidence.json CI-generated: the plan's artifacts_produced section defines it as a CI output, and no local macOS Apple Silicon producer evidence exists to support a checked-in record."
  - "Require the producer artifact directory to contain the exact bundle output set, including the native executable and lifecycle files, while allowing the separate Linux contract directory to contain only its bounded JSON record."
  - "Treat target-level resource status as not-run when produced by the native bundle jobs; Linux contract resource tests provide the actual resource gate and final evidence check links."

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Frozen Python oracle, malformed input, session fencing, projection, recovery, bounded queue/payload, process resource, and Python-free production surface checks."
    requirement: RUST-01
    verification:
      - kind: integration
        ref: "cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test black_box_parity --test resource_bounds --test production_surface -- --test-threads=1"
        status: pass
    human_judgment: false
  - id: D2
    description: "Fail-closed synthetic evidence collector rejects missing, duplicate, foreign, tampered, oversized, privacy-sensitive, and checksum-invalid inputs while producing all RUST and D check IDs."
    requirement: RUST-08
    verification:
      - kind: unit
        ref: "python -m unittest host.herdr_keypad.release.test_collect_phase4_evidence"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pinned Linux parity producer and commit/run-scoped aggregation job publish final canonical JSON and SHA-256 sidecar after Linux, macOS Apple Silicon, and Linux contract jobs succeed."
    requirement: RUST-06
    verification:
      - kind: other
        ref: "python host/herdr_keypad/release/collect_phase4_evidence.py --workflow .github/workflows/native-release.yml --check-aggregation-contract"
        status: pass
    human_judgment: true
    rationale: "Hosted Linux execution, macOS Apple Silicon execution, and artifact aggregation must run in GitHub Actions; no local macOS runner or external CI dispatch is available in this worktree."

requirements-completed: [RUST-01, RUST-02, RUST-03, RUST-04, RUST-05, RUST-06, RUST-07, RUST-08]

# Metrics
duration: 45min
completed: 2026-08-30
status: complete
---

# Phase 04 Plan 10: Parity, Resource, and Release Evidence Summary

**Frozen Python parity, bounded recovery/resource checks, Python-free production smoke, and commit/run-locked native release evidence now form the final automated Phase 04 gate.**

## Performance

- **Duration:** 45 min (approximate execution window)
- **Started:** 2026-08-30T05:40:00Z (approximate)
- **Completed:** 2026-08-30
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added three focused Rust integration suites. They validate every frozen protocol corpus admission result, byte-identical Python oracle regeneration, public Codex/projection/recovery behavior, duplicate/session fencing, bounded channels and payloads, measured Linux RSS/CPU samples, and a production binary status action with an empty `PATH`.
- Added the standard-library collector and eight synthetic unit tests. The collector rejects missing target/contract evidence, duplicate or foreign files, wrong commit/run/ref, tampered hashes, absent clean-build provenance, oversized/privacy-sensitive records, and missing/tampered checksum sidecars before emitting a canonical bounded record.
- Extended `native-release.yml` with a pinned Linux Phase 04 contract job and an aggregation job that explicitly needs both native bundle producers plus the contract producer, downloads only SHA-named artifacts from the current run, validates all reopened hashes, and uploads the final JSON/checksum pair.
- Kept `artifacts/phase04/phase04-release-evidence.json` out of the worktree. It is a CI-produced artifact requiring real Linux and macOS producer inputs; no placeholder or unsupported local evidence was committed.

## Task Commits

Each task was committed atomically:

1. **Task 1: Prove parity, resource bounds, and the closed production surface** - `14e1827`, `457ce6d` (test)
2. **Task 2: Publish hash-linked Linux and macOS release evidence** - `bfad68d` (feat)

The execution summary metadata commit follows after this file is self-checked.

## Files Created/Modified

- `host/herdr_keypad/native/tests/black_box_parity.rs` - Frozen corpus integrity, Python exporter black-box comparison, public protocol/session admission, projection, and adversarial input checks.
- `host/herdr_keypad/native/tests/resource_bounds.rs` - Channel, queue, payload, timer, duplicate/recovery, sustained traffic, and Linux process-resource checks.
- `host/herdr_keypad/native/tests/production_surface.rs` - Direct plugin manifest, Python-free status smoke, forbidden command, and private developer-surface checks.
- `host/herdr_keypad/release/collect_phase4_evidence.py` - Commit/run/ref-bound closed evidence validator, source hash reopening, canonical record writer, sidecar verifier, and aggregation workflow contract checker.
- `host/herdr_keypad/release/test_collect_phase4_evidence.py` - Deterministic synthetic producer/contract fixtures and fail-closed collector/checksum tests.
- `.github/workflows/native-release.yml` - Commit-named producer artifacts, Linux contract producer, and three-input current-run aggregation/upload job.

## Decisions Made

- The final evidence JSON remains CI-generated because the plan explicitly describes it as a CI-produced artifact and local Linux execution cannot truthfully provide the macOS Apple Silicon result.
- Bundle producer evidence preserves the existing closed archive output, while target resource proof is owned by the Linux contract job that runs the new focused suites.
- The collector records signing and notarization as `not-run` and physical acceptance scope as `Phase 5`; it emits no credentials, account identity, raw logs, prompts, transcripts, filesystem paths, or physical claims.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected frozen boundary test construction and observable fixture indexing**
- **Found during:** Task 1 (Prove parity, resource bounds, and the closed production surface)
- **Issue:** Initial tests supplied whitespace instead of the valid 4096-byte fixture boundary and indexed fixture case fields one level too high; adversarial expected codes also reflected the parser's wrong-shape result incorrectly.
- **Fix:** Reused the committed valid snapshot bytes for the exact boundary, indexed the case `expected` object explicitly, and asserted the public parser's exact safe rejection code.
- **Files modified:** `host/herdr_keypad/native/tests/black_box_parity.rs`, `host/herdr_keypad/native/tests/resource_bounds.rs`
- **Verification:** The three focused suites passed with 18 tests.

**2. [Rule 1 - Bug] Reconciled producer bundle layout with fail-closed artifact validation**
- **Found during:** Task 2 (Publish hash-linked Linux and macOS release evidence)
- **Issue:** Native producer uploads contain the existing bundle's nested `bin/herdr-keypad` plus lifecycle/plugin files, and release binaries can exceed a one-megabyte input cap; rejecting that known layout would make aggregation fail before evidence validation.
- **Fix:** Added the exact known bundle entries to the closed allowlist, traversed directories while rejecting every unlisted nested file/symlink, and raised the bounded hashed-input limit to 64 MiB while retaining the 128 KiB record limit.
- **Files modified:** `host/herdr_keypad/release/collect_phase4_evidence.py`, `host/herdr_keypad/release/test_collect_phase4_evidence.py`
- **Verification:** Collector unit tests and both workflow-contract checks passed.
- **Committed in:** `bfad68d`.

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes were directly required for the planned tests and existing producer bundle layout; no production runtime or release target scope was added.

## Issues Encountered

- The local machine has no macOS Apple Silicon runner, so hosted native macOS build/test, artifact download, and final aggregation remain external CI acceptance steps. The workflow is explicitly prepared for that run and does not claim those results locally.
- PyYAML and Ruby were unavailable for local YAML parsing; the collector's strict static workflow contract checker and existing bundle workflow checker both passed. No formatter, linter, repository-wide suite, firmware build, physical check, signing, notarization, UAT, or external CI dispatch was run.
- Unit-test execution creates a Python bytecode cache; it was removed before committing and is not part of the task changes.

## User Setup Required

None - no credentials or external service configuration is required for unsigned CI aggregation. Hosted GitHub Actions execution is required to produce the final Phase 04 JSON/checksum artifact.

## Next Phase Readiness

- Implementation is committed and locally verified: Rust focused suites passed (18 tests), collector unit tests passed (8 tests), and both release workflow contract checks passed.

## Self-Check: PASSED

- Summary file exists at the required phase path.
- Task commits `14e1827`, `457ce6d`, and `bfad68d` exist.
- Focused Rust tests passed (18 tests), collector unit tests passed (8 tests), and both workflow-contract checks passed.
- No local `artifacts/phase04/phase04-release-evidence.json` was created; final evidence is intentionally CI-produced.

---
*Phase: 04-production-rust-host-bridge*
*Completed: 2026-08-30*