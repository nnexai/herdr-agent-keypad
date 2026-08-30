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
  - Linux contract and current-run artifact aggregation workflow with canonical checksum sidecar, retained for a later hosted release
  - Completed Phase 04 acceptance from local automated checks and the installed Linux native Herdr bridge; no hosted or public-release claim
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
  - "Keep the release workflow and collector as future hosted-release machinery; Phase 04 does not require or claim a GitHub Actions dispatch or CI-produced final record."
  - "Require future producer artifact directories to contain the exact bundle output set, including the native executable and lifecycle files, while the Linux contract directory contains only its bounded JSON record."
  - "Treat target-level resource status as not-run until a hosted native bundle job executes; the recorded Linux contract resource tests supply the completed Phase 04 resource gate."
  - "Close Phase 04 per D-23 on 18 focused Rust tests, 8 collector tests, the aggregation-contract check, and final installed Linux native Herdr evidence."

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
    description: "Pinned Linux parity producer and commit/run-scoped aggregation jobs form a locally verified contract that can publish canonical JSON and a SHA-256 sidecar after future Linux, macOS Apple Silicon, and Linux contract jobs succeed."
    requirement: RUST-06
    verification:
      - kind: other
        ref: "python host/herdr_keypad/release/collect_phase4_evidence.py --workflow .github/workflows/native-release.yml --check-aggregation-contract"
        status: pass
    human_judgment: false
  - id: D4
    description: "The release-built Linux x86-64 binary is installed in the enabled local Herdr plugin, starts through the native plugin action, reports ready/running status, survives same-configuration Herdr restart with new authority, and leaves no legacy Python bridge process."
    requirement: RUST-05
    verification:
      - kind: other
        ref: "Herdr 0.8.2 plugin logs 34, 35, and 38 plus staged binary SHA-256 47f6c3b146738cb657d22a1d7a4512e20090e03aca1aea4971fabb354d3dd589"
        status: pass
    human_judgment: false

requirements-completed: [RUST-01, RUST-02, RUST-03, RUST-04, RUST-05, RUST-06, RUST-07, RUST-08]

# Metrics
duration: 45min
completed: 2026-08-30
status: complete
---

# Phase 04 Plan 10: Parity, resource, and release-contract summary

**Frozen Python parity, bounded recovery/resource checks, Python-free production smoke, deterministic release machinery, and the installed Linux native bridge close Phase 04 without claiming an unrun hosted release.**

## Performance

- **Duration:** 45 min (approximate execution window)
- **Started:** 2026-08-30T05:40:00Z (approximate)
- **Completed:** 2026-08-30
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added three focused Rust integration suites. They validate every frozen protocol corpus admission result, byte-identical Python oracle regeneration, public Codex/projection/recovery behavior, duplicate/session fencing, bounded channels and payloads, measured Linux RSS/CPU samples, and a production binary status action with an empty `PATH`.
- Added the standard-library collector and eight synthetic unit tests. The collector rejects missing target/contract evidence, duplicate or foreign files, wrong commit/run/ref, tampered hashes, absent clean-build provenance, oversized/privacy-sensitive records, and missing/tampered checksum sidecars before emitting a canonical bounded record.
- Extended `native-release.yml` with a pinned Linux Phase 04 contract job and an aggregation job that explicitly needs both native bundle producers plus the contract producer, downloads only SHA-named artifacts from the current run, validates all reopened hashes, and can upload the final JSON/checksum pair during a later hosted release. The local aggregation-contract check passed; GitHub Actions did not run.
- Kept `artifacts/phase04/phase04-release-evidence.json` out of the worktree. It is a future hosted-workflow output requiring real Linux and macOS producer inputs, not a Phase 04 completion artifact.

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

- The final evidence JSON remains a future CI-generated output because local Linux execution cannot truthfully provide a macOS Apple Silicon result. Phase 04 completion does not require that file.
- Bundle producer definitions preserve the existing closed archive output, while the recorded Linux contract tests own the completed local resource proof.
- The collector records signing and notarization as `not-run` and physical acceptance scope as `Phase 5`; it emits no credentials, account identity, raw logs, prompts, transcripts, filesystem paths, or physical claims.

## Installed Linux native bridge evidence

- Herdr `0.8.2` links and enables `~/.local/share/herdr/plugins/herdr-keypad` as the local plugin.
- The staged `bin/herdr-keypad` is executable, 2,769,296 bytes, and has SHA-256 `47f6c3b146738cb657d22a1d7a4512e20090e03aca1aea4971fabb354d3dd589`.
- Plugin log 34 records a successful native `start`. Plugin log 35 reports bridge `0.1.0`, bridge state `running`, device state `ready`, Herdr state `running`, Codex state `unavailable`, and configuration identity `c8c4a35718a5a4245a6f613b6`.
- A same-configuration Herdr restart ended PID `699375`, started PID `700051` from the staged native executable with `restart`, retained the mode-0600 control socket, and produced the same healthy status in plugin log 38.
- The existing mode-0600 `~/.config/herdr/keypad-binding.json` remained unchanged at SHA-256 `dfc89c32966cb7f7fa0f0c98d9d9ed4086a3c31eb1c3340ef26f3ce1304f0257`, and the final legacy Python bridge process query returned no rows.
- This is Linux native deployment evidence only. It makes no hardware, hosted Linux, macOS, signing, notarization, artifact-publication, or public-release claim.

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

- GitHub Actions was intentionally not dispatched in Phase 04. Hosted Linux/macOS execution, artifact aggregation/publication, signing, notarization, and release upload remain later release work; this summary makes no claim that they ran.
- PyYAML and Ruby were unavailable for local YAML parsing; the collector's strict static aggregation-contract checker and existing bundle workflow checker passed. No formatter, linter, repository-wide suite, firmware build, physical check, signing, notarization, UAT, or external CI dispatch was run.
- Unit-test execution creates a Python bytecode cache; it was removed before committing and is not part of the task changes.

## User Setup Required

None. Hosted GitHub Actions and public release operations are future release work, not Phase 04 setup or acceptance.

## Next Phase Readiness

- Phase 04 is complete with no human checkpoint or UAT: the focused Rust suites passed 18 tests, the collector passed 8 tests, the aggregation-contract check passed, and the final native Linux Herdr plugin installation started, reported ready, restarted with fresh process authority, and left no legacy Python bridge process.

## Self-Check: PASSED

- Summary file exists at the required phase path.
- Task commits `14e1827`, `457ce6d`, and `bfad68d` exist.
- Focused Rust tests passed (18 tests), collector unit tests passed (8 tests), and the aggregation-contract check passed.
- The installed Linux native Herdr bridge passed start, status, same-configuration restart, control-socket, binding-preservation, and legacy-process absence checks. No hosted release evidence file was created or claimed.

---
*Phase: 04-production-rust-host-bridge*
*Completed: 2026-08-30*