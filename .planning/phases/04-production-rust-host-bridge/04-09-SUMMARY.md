---
phase: 04-production-rust-host-bridge
plan: "09"
subsystem: release-ci
tags: [rust, cargo, herdr, release, ci, reproducibility, privacy]

# Dependency graph
requires:
  - phase: 04-production-rust-host-bridge
    provides: Integrated native bridge and direct Herdr plugin lifecycle contract from Plans 07-08
provides:
  - Closed target bundle manifest schema and archive verifier
  - Release-bundle native policy tests for directory and TAR packages
  - Isolated Linux x86-64 and macOS Apple Silicon release workflow with unsigned provenance
affects: [native-release, herdr-keypad-packaging, ci-artifacts]

# Actuals (#2632)
actuals:
  tokens: 16394
  tasks: 2
  commits: 8

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Standard-library Python verifier is CI-only and never enters the production bundle
    - Target packages use a four-entry closed allowlist with direct bundled executable argv
    - Reproducibility evidence records two source archives and two clean unsigned binary hashes

key-files:
  created:
    - .github/workflows/native-release.yml
    - host/herdr_keypad/bundle/manifest.schema.json
    - host/herdr_keypad/release/verify_bundle.py
    - host/herdr_keypad/native/tests/release_bundle.rs
  modified: []

key-decisions:
  - "Use x86_64-unknown-linux-gnu and aarch64-apple-darwin as the only release triples; the macOS job requires macos-14-xlarge and asserts uname -m=arm64 before building."
  - "Keep plugin archives closed to herdr-plugin.toml, LIFECYCLE.md, bin/herdr-keypad, and release-manifest.json; all verifier, source, fixture, and evidence files remain outside the package."
  - "Record unsigned reproducibility and dependency/test evidence while signing and notarization remain explicitly not-run; no Apple credentials or signing claims belong in this workflow."

patterns-established:
  - "Each target materializes GITHUB_SHA twice with independent archive extraction, CARGO_HOME, and CARGO_TARGET_DIR roots before comparing native outputs."
  - "The verifier reopens the lifecycle document, resolves every manifest argv to the sole packaged executable, checks target-native headers/dependencies, and rejects unsafe paths/strings/metadata."

requirements-completed: [RUST-05, RUST-06, RUST-07, RUST-08]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Closed native bundle schema, verifier, lifecycle/privacy reopening, target architecture/dependency inspection, and hash/signing-status enforcement."
    requirement: RUST-07
    verification:
      - kind: integration
        ref: "cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test release_bundle"
        status: pass
    human_judgment: false
  - id: D2
    description: "Linux x86-64 and macOS Apple Silicon workflow contract with pinned actions, arm64 runner assertion, two clean roots, locked builds/tests, provenance, hashes, verification, and artifact upload."
    requirement: RUST-08
    verification:
      - kind: other
        ref: "python3 host/herdr_keypad/release/verify_bundle.py --workflow .github/workflows/native-release.yml --check-workflow-contract"
        status: pass
    human_judgment: false
  - id: D3
    description: "Target-native CI execution and artifact publication on both hosted runners."
    requirement: RUST-05
    verification: []
    human_judgment: true
    rationale: "The plan explicitly forbids external CI dispatch; hosted Linux and Apple Silicon execution remains to be performed by the release trigger."

# Metrics
duration: 20min
completed: 2026-08-30
status: complete
---

# Phase 04 Plan 09: Native Release and CI Summary

**Closed, unsigned Herdr plugin bundles now carry target-native Rust binaries, lifecycle metadata, reproducibility provenance, dependency/test evidence, and no separately installed language runtime.**

## Performance

- **Duration:** 20 min (approximate execution window)
- **Started:** 2026-08-30T05:18:00Z (approximate)
- **Completed:** 2026-08-30T05:38:17Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `manifest.schema.json` and `verify_bundle.py` as a closed release-evidence contract. Directory and TAR bundles are checked for exact contents, direct native argv, lifecycle hash/content/privacy, target architecture, dynamic dependencies, binary hash/size, source/Cargo.lock provenance, and honest unsigned signing/notarization status.
- Added focused Rust integration tests covering valid Linux bundles, TAR archives, wrong targets, extra runtime/source/fixture/evidence entries, unresolved argv, hash/metadata mismatches, lifecycle privacy, unknown schema fields, and false signing claims.
- Added `.github/workflows/native-release.yml` with pinned third-party actions, separate Ubuntu and `macos-14-xlarge` jobs, explicit Apple Silicon assertion, two independent `GITHUB_SHA` archive extractions, distinct Cargo homes/target directories, locked native tests/builds, target-native dependency inspection, two-run SHA-256 comparison, commit-bound manifests, and uploaded bundle/provenance artifacts.
- Kept Python confined to CI verification and made unsigned status explicit; the archive contains no verifier, source checkout, fixture, evidence, package-manager, or runtime files.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define and verify a closed target bundle** - `da3f5f5` (test), `ed187be` (feat), `1b948f8` (test coverage), `fe8ee20` (fix)
2. **Task 2: Build and test both native targets in CI** - `8d2e758` (feat), `f51b951` (fix)

The execution summary metadata commit follows after this file is self-checked.

## Files Created/Modified

- `.github/workflows/native-release.yml` - Pinned Linux/macOS native build, test, inspect, reproducibility, package, and artifact-upload jobs.
- `host/herdr_keypad/bundle/manifest.schema.json` - Closed JSON Schema for target, compiler, provenance, lifecycle, binary, dependency, test, signing, and notarization evidence.
- `host/herdr_keypad/release/verify_bundle.py` - Standard-library directory/archive, manifest, lifecycle, argv, architecture, dependency, privacy, hash, and workflow-contract verifier plus CI manifest generator.
- `host/herdr_keypad/native/tests/release_bundle.rs` - Focused native release policy tests and TAR archive smoke coverage.

## Decisions Made

- Release targets are limited to Linux x86-64 (`x86_64-unknown-linux-gnu`) and macOS Apple Silicon (`aarch64-apple-darwin`), matching the current Herdr package target set.
- The workflow uses the repository's pinned `rust-toolchain.toml` channel (currently Rust 1.98.0), installs the target on the native runner, and uses `cargo ... --locked` for every build/test invocation.
- Independent Cargo target directories and Cargo homes are retained for both clean roots; binary and source archive hashes are retained as loose artifact evidence and in `release-manifest.json`.
- Signing and notarization are deliberately `not-run`; the workflow does not require or expose signing credentials and does not imply distribution signing occurred.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the release test fixture's moved-path borrow**
- **Found during:** Task 1 (Define and verify a closed target bundle)
- **Issue:** The initial new Rust test moved a `PathBuf` into `fs::write` and then borrowed it for cleanup, preventing the focused test from compiling.
- **Fix:** Borrowed the path for the write operation.
- **Files modified:** `host/herdr_keypad/native/tests/release_bundle.rs`
- **Verification:** Locked release-bundle test suite passed.
- **Committed in:** `da3f5f5` (test commit included the corrected test).

**2. [Rule 1 - Bug] Resolved binaries from the isolated Cargo target directories**
- **Found during:** Task 2 (Build and test both native targets in CI)
- **Issue:** The first workflow draft exported external `CARGO_TARGET_DIR` values but looked for binaries under each source checkout's `native/target` path.
- **Fix:** Read artifacts from `$WORK/target-a/$TARGET` and `$WORK/target-b/$TARGET`, preserving the no-shared-compiled-cache contract.
- **Files modified:** `.github/workflows/native-release.yml`
- **Verification:** Workflow contract verifier passed after the correction.
- **Committed in:** `f51b951`.

**3. [Rule 1 - Bug] Made release policy tests target-portable**
- **Found during:** Task 1 (Define and verify a closed target bundle)
- **Issue:** The first focused tests used Linux-only `sha256sum` and hard-coded Linux ELF fixture metadata, which would make the mandated macOS native test job fail before packaging.
- **Fix:** Use the existing Rust `sha2` dependency for hashing and select target-native `/bin/true`, target metadata, dependency tool, and expected target at compile time.
- **Files modified:** `host/herdr_keypad/native/tests/release_bundle.rs`
- **Verification:** Locked Linux release-bundle suite passed; macOS-specific branches are compile-time selected for the hosted Apple Silicon job.
- **Committed in:** `fe8ee20`.

**Total deviations:** 3 auto-fixed (3 Rule 1 bugs)
**Impact on plan:** All fixes were directly necessary for the scoped tests/workflow to execute on both target families; no runtime or packaging scope was added.

## Issues Encountered

- No local macOS target, Apple Silicon runner, or signing/notarization environment was available or invoked. The workflow explicitly retains those target-native operations for its hosted jobs and does not claim they ran locally.
- The focused Cargo suite emitted three compiler warnings from existing native test/build code; no formatter, linter, repository-wide suite, UAT, physical check, or external CI dispatch was run.

## User Setup Required

None - no credentials or external service configuration is required for the unsigned workflow.

## Next Phase Readiness

- The release workflow is ready to run on its configured Linux and Apple Silicon hosted runners and will publish target archives plus loose provenance/hash records.
- Triggering hosted CI, signing/notarization, UAT, and physical hardware checks remain intentionally outside this plan's verification scope.

## Self-Check: PASSED

- Summary file exists at the required phase path.
- Release workflow, manifest schema, verifier, and focused test file exist.
- Task commits `da3f5f5`, `ed187be`, `1b948f8`, `8d2e758`, `f51b951`, and `fe8ee20` exist.
- Locked release-bundle tests passed (10 tests).
- Workflow-contract verification and Python/schema static parsing passed.
- On-disk file and commit existence checks passed; the summary was the only expected untracked file before its metadata commit.

---
*Phase: 04-production-rust-host-bridge*
*Completed: 2026-08-30*
