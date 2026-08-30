---
phase: 04-production-rust-host-bridge
verified: 2026-08-30T07:28:56Z
status: passed
score: 38/38 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 38/39
  gaps_closed:
    - "Runnable end-to-end Herdr-to-device-to-exact-focus proof is superseded by the accepted WR-01 maintained composed proof."
  gaps_remaining: []
  regressions: []
decision_coverage:
  honored: 23
  total: 23
  not_honored: []
---

# Phase 4: Production Rust Host Bridge Verification Report

**Phase Goal:** As a keypad user, I want the production host bridge to preserve the Python bridge's inbox projection, exact focus, truthful Codex capacity, freshness/error states, reconnect behavior, and authorized focus-then-hold workflow as one efficient native Rust executable installed on Linux, with a portable macOS adapter and deterministic cross-target release automation ready for a later hosted release.

**Verified:** 2026-08-30T07:28:56Z  
**Status:** passed  
**Re-verification:** Yes — after WR-01 clean-cutover authority amendment

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Black-box Rust behavior preserves projection/order, exact focus, focus-only authority, source health, Codex windows, diagnostics, recovery, and the existing HID-authorized workflow. | ✓ VERIFIED | `black_box_parity` (8 tests), `projection_focus_parity` (10), `codex_parity` (8), `herdr_parity` (4), and `production_surface` (6) passed in the locked suite; Python oracle determinism and 37 focused Python tests also passed. |
| 2 | The closed v2 four-message protocol retains bounds, fresh-session/ACK fences, identity-bound focus, and no arbitrary Herdr/HID action surface. | ✓ VERIFIED | `protocol_parity` (4), `usb_platform` (17), and `projection_focus_parity` cover malformed/oversized/duplicate/session inputs, ACK readiness, old-session rejection, and no keyboard/generic-action variant. |
| 3 | Core policy is portable; Linux/macOS code is confined to platform discovery/I/O and lifecycle adapter concerns. | ✓ VERIFIED | `src/{core,protocol,ports,platform}` separation is substantive; `usb_platform` covers Linux exact descriptors and portable macOS registry/suspend cases. |
| 4 | Normal operation is event-driven and bounded; timers are explicit recovery/freshness deadlines rather than a busy loop. | ✓ VERIFIED | `RuntimeCoordinator::run` uses `tokio::select!`; `herdr_parity::healthy_push_idle_is_not_fallback_but_eof_is_recoverable`, lifecycle idle metrics, and `resource_bounds` passed. |
| 5 | Native Linux/macOS release definitions, bundles, dependency/provenance/hash verification, and later aggregation are deterministic and locally contract-verified. | ✓ VERIFIED | `release_bundle` (10), `verify_bundle.py --check-workflow-contract`, and collector aggregation-contract check passed. Hosted execution is expressly parked by roadmap/requirements authority. |
| 6 | Production launch exposes no developer/test/runtime leakage and retains bounded redacted diagnostics. | ✓ VERIFIED | `production_surface` validates Python-free status with empty `PATH`, closed commands, and source/environment boundaries; `lifecycle_resource` validates default-off safe stderr logs and bounded read-only status. |
| 7 | Linux installation has native startup/status/restart/single-authority/config-state/removal-of-Python coverage; physical recovery remains Phase 5. | ✓ VERIFIED | `production_surface` process tests passed. Recorded deployment evidence in 04-10-SUMMARY identifies a ready/running installed native process, same-config process replacement, preserved read-only binding, and no legacy Python bridge; this report makes no device claim. |
| 8 | Differential, malformed-input, lifecycle/resource/platform/bundle/release-contract checks are automated without a hosted/macOS/signing/publication claim. | ✓ VERIFIED | Locked suite ran 101 tests; deterministic oracle, collector (8 tests), bundle workflow contract, and release build all exited 0. |
| 9 | The maintained composed proof directly covers Herdr invalidation/read, committed projection, matching snapshot-ACK actionability, exact focus, sole `agent.focus`, and Herdr-owned lifecycle. | ✓ VERIFIED | Accepted 04-01 WR-01 amendment names `RuntimeCoordinator` plus `black_box_parity` (8), `projection_focus_parity` (10), `herdr_parity` (4), `usb_platform` (17), and `production_surface` (6). The re-verification command ran these five suites: 45 passed, 0 failed. |

**Score:** 38/38 must-haves verified (0 present-but-behavior-unverified)

## Required Artifacts

| Artifact group | Expected | Status | Details |
|---|---|---|---|
| `native/src/{lib,protocol/v2,core/{projection,focus,orchestrator},ports/{herdr,codex,usb,control,status},platform/{linux,macos},main}.rs` | Portable core, strict protocol, exact focus, event-driven sources, bounded lifecycle, and platform adapters | ✓ VERIFIED | 17 substantive native modules compiled in the locked test/build commands and are exercised by the named integration suites. |
| `host/herdr_keypad/tests/export_rust_oracle.py` and `native/tests/fixtures/*.json` | Deterministic, redacted Python behavioral oracle | ✓ VERIFIED | Two independently generated roots byte-matched; both passed Rust fixture validation; 37 focused Python tests passed. |
| `host/herdr_keypad/native/src/core/orchestrator.rs` plus `native/tests/{black_box_parity,projection_focus_parity,herdr_parity,usb_platform,production_surface}.rs` | Accepted WR-01 maintained composed proof replacing the obsolete bootstrap tracer | ✓ VERIFIED | The current 04-01 authority explicitly supersedes `production_tracer.rs`; all five substantive paths exist and the focused maintained suite passed 45 tests. |
| `host/herdr_keypad/native/tests/{black_box_parity,resource_bounds,production_surface,usb_platform,lifecycle_resource}.rs` | Parity, recovery, resource, surface, lifecycle, and platform evidence | ✓ VERIFIED | Present, substantive, and run by `cargo test --locked` (101 passing tests total). |
| Plugin/lifecycle/bundle/release artifacts | Native launch, lifecycle procedure, closed bundle/release schemas and collectors | ✓ VERIFIED | `plugin_cutover` and `release_bundle` passed; both Python workflow/aggregation contract checkers passed. |

Artifact scan against the **current** all-ten-plan authority: **33/33 present and substantive**. The historical `production_tracer.rs` is explicitly superseded by the accepted WR-01 composed proof and is not a current artifact requirement.

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `RuntimeCoordinator` | Herdr/projection/USB/focus ports | Maintained composed proof | ✓ WIRED | Current 04-01 key links enumerate `main.rs → RuntimeCoordinator`, `RuntimeCoordinator → Herdr`, `→ USB`, and `→ projection`; the 45-test focused suite directly exercises the named public contracts. |
| `main.rs` | `lib.rs` / `RuntimeCoordinator` | Thin native process entrypoint | ✓ WIRED | `main.rs` imports native contracts and constructs/runs `RuntimeCoordinator`; process-surface tests exercised the binary. |
| Projection | Focus | Current immutable binding | ✓ WIRED | `projection_focus_parity` proves committed current bindings, exact revalidation, one retry, and no other effects. |
| Herdr/Codex ports | Core model/projection | Typed invalidations, complete reads, normalized observations | ✓ WIRED | `herdr_parity`, `codex_parity`, and `black_box_parity` exercise public boundary outputs. |
| Linux/macOS platform adapters | USB port | Exact measured descriptor candidate plus binding/hello authority | ✓ WIRED | `usb_platform` covers exact descriptor selection, ambiguity rejection, binding immutability, fresh hello/ACK, and old-frame discard. |
| Lifecycle/control/status/logging | Runtime authority | Lock-owned IPC and shared safe vocabulary | ✓ WIRED | Lifecycle and production-surface tests cover control ownership, restart, read-only status, bounded safe logging. |
| Plugin/bundle/release workflow | Bundled native executable and validation/aggregation tools | Direct argv and target-package verification | ✓ WIRED | `plugin_cutover`, `release_bundle`, `verify_bundle.py`, and collector aggregation check passed. |

## Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Produces real data | Status |
|---|---|---|---|---|
| `core/projection.rs` | Three-slot snapshot/binding | Complete typed `agent.list` plus `workspace.list` reads from `ports/herdr.rs` | Ordered normalized entries and immutable actionable identities | ✓ FLOWING |
| `ports/codex.rs` | `CodexView` / `CodexSnapshot` | Bounded Codex app-server child result | Presence-aware primary/secondary values and source/freshness states | ✓ FLOWING |
| `ports/usb.rs` | Session frames, ACK, focus intent/result | Exact paired serial candidate, frozen binding, fresh application hello | Closed v2 frames gated by current boot/session/ACK authority | ✓ FLOWING |
| `ports/status.rs` | `StatusSnapshot` | Lifecycle transitions and allowlisted safe codes | Bounded read-only operational status without raw upstream content | ✓ FLOWING |

No dynamic production render/transport value traced to a static fallback, empty hardcoded prop, or mock-only source.

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full native contract, including all integration tests | `cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml` | 101 passed, 0 failed (15 suites) | ✓ PASS |
| Release native executable build | `cargo build --locked --release --manifest-path host/herdr_keypad/native/Cargo.toml` | Exit 0 | ✓ PASS |
| Python oracle determinism and frozen behavioral suite | `PYTHONPATH=host/herdr_keypad/src:tools/phase1_bringup/src python host/herdr_keypad/tests/export_rust_oracle.py --verify-determinism --rust-manifest host/herdr_keypad/native/Cargo.toml && python -m unittest …` | Two roots byte-identical; Rust fixture validation passed twice; 37 tests passed | ✓ PASS |
| Future release aggregation machinery | `python -m unittest host.herdr_keypad.release.test_collect_phase4_evidence && python host/herdr_keypad/release/collect_phase4_evidence.py --workflow .github/workflows/native-release.yml --check-aggregation-contract` | 8 tests passed; aggregation contract verified | ✓ PASS |
| Target workflow/bundle policy | `python host/herdr_keypad/release/verify_bundle.py --workflow .github/workflows/native-release.yml --check-workflow-contract` | Workflow contract verified | ✓ PASS |
| WR-01 maintained composed proof | `cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test black_box_parity --test projection_focus_parity --test herdr_parity --test usb_platform --test production_surface -- --test-threads=1` | 45 passed, 0 failed (5 suites) | ✓ PASS |

## Probe Execution

No Phase 4 probe script was declared and no `scripts/**/probe-*.sh` file exists. The native, oracle, bundle, and collector checks above are the applicable automated probes.

## Requirements Coverage

| Requirement | Supporting direct evidence | Status |
|---|---|---|
| RUST-01 | Python-oracle byte determinism; `black_box_parity`, projection/focus, Herdr, and Codex parity suites | ✓ SATISFIED |
| RUST-02 | `protocol_parity`, `usb_platform`, projection/focus action-surface tests, closed `agent.focus` port | ✓ SATISFIED |
| RUST-03 | Event-driven `RuntimeCoordinator`, Herdr/Codex recovery suites, lifecycle/resource and resource-bound tests | ✓ SATISFIED |
| RUST-04 | Linux/macOS adapters plus 17 `usb_platform` tests for exact descriptor, frozen binding, fresh hello/session authority | ✓ SATISFIED |
| RUST-05 | Direct native plugin manifest, lifecycle/control tests, production binary restart/single-authority tests, recorded installed-Linux evidence | ✓ SATISFIED |
| RUST-06 | Closed bundle/release schema, 10 release-bundle tests, workflow-contract and aggregation-contract checks | ✓ SATISFIED |
| RUST-07 | Empty-PATH Python-free binary smoke, closed manifest/action surface, privacy/log/status/bundle tests | ✓ SATISFIED |
| RUST-08 | Differential/malformed/lifecycle/resource/platform/bundle/collector tests; local release build and future-hosted contract checks | ✓ SATISFIED |

All eight Phase 4 requirement IDs are claimed by Plan 04-10; no orphaned Phase 4 requirement was found in `REQUIREMENTS.md`.

## Test Quality Audit

| Test evidence | Linked requirements | Active | Skipped | Circular | Assertion level | Verdict |
|---|---|---:|---:|---|---|---|
| Native Rust integration suite | RUST-01..RUST-08 | 101 | 0 | No | Value and behavioral | ✓ PASS |
| Python oracle exporter + focused Python suite | RUST-01, RUST-02, RUST-08 | 37 | 0 | No — expected corpus is independently regenerated from frozen Python oracle and Rust validates separate roots | Value and behavioral | ✓ PASS |
| Collector tests | RUST-06, RUST-08 | 8 | 0 | No — synthetic producer records are rejected/accepted by independent collector policy | Value and behavioral | ✓ PASS |

Disabled-test scan found no disabled requirement test. The `pending` matches in the scan are ordinary variable names, not disabled-test annotations. Assertions test outcomes, exact safe error codes, bounded capacities, process replacement, and privacy policy—not merely presence or type.

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---:|---|---|---|
| `host/herdr_keypad/native/src/ports/control.rs` | 278 | Compiler warns `AuthorityLock.file` is read only to retain the lock | ℹ️ Info | Intentional RAII ownership; no behavioral or completion defect. |
| Native sources | — | No unreferenced `TBD`, `FIXME`, or `XXX` markers found | ℹ️ Info | No debt-marker blocker. |

## Decision Coverage

All **23/23** trackable decisions from `04-CONTEXT.md` are honored by shipped artifacts (`check.decision-coverage-verify`).

## Human Verification

N/A — this is an infrastructure/foundation migration phase. Every current Phase 4 acceptance claim is programmatically covered or is explicitly recorded deployment evidence. Physical device acceptance, actual-device reconnect, and hosted release execution remain Phase 5/later-release scope and are not invented as UAT here.

## Verification Conclusion

The former tracer gap is closed. Commit `ee3fe41` amended Plan 04-01 and its SUMMARY with accepted WR-01 clean-cutover supersession authority: the obsolete root coordinator and coupled tracer must remain deleted, while maintained `RuntimeCoordinator` composition and five named public-boundary suites are the current proof. The verifier inspected that amendment and ran its exact focused command successfully (45 tests).

All current Phase 4 must-haves and RUST-01 through RUST-08 have direct evidence. Hosted GitHub execution, macOS native execution, signing/notarization, publication, upload, and physical-device acceptance are explicitly parked by current planning authority and are not gaps.

---
_Verified: 2026-08-30T07:28:56Z_  
_Verifier: the agent (gsd-verifier)_
