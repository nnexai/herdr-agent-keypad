---
phase: 03-truthful-codex-capacity-and-device-menu
plan: 08
subsystem: acceptance-capture-evidence
status: complete
tags: [codex, menu, capture, exact-device, evidence, r-bucket]

requires:
  - phase: 03-07
    provides: complete all-theme Codex and menu renderers
provides:
  - Complete named host/native Phase 3 acceptance matrix including R-BUCKET
  - Exact-pair deterministic capture scenes for every Codex state and menu page
  - Current selected-usb deployment, 72 source captures, two contact sheets, and strict pending evidence
  - Stable guarded bridge ownership after capture and Codex-only refresh
  - Plan 09 physical Y/N/R rows left explicitly pending
affects: [03-09, exact-device acceptance]

actuals:
  tasks: 2
  commits: 2

key-files:
  created:
    - tools/phase1_bringup/src/phase1_bringup/phase3_smoke.py
    - artifacts/phase3/03-DEVICE-EVIDENCE.json
    - artifacts/phase3/03-DEVICE-EVIDENCE.json.sha256
    - artifacts/phase3/screenshots/captures.json
    - artifacts/phase3/screenshots/codex-states-contact.png
    - artifacts/phase3/screenshots/menu-pages-contact.png
  modified:
    - firmware/src/app/agent_projection.cpp
    - firmware/src/app/agent_projection.h
    - firmware/src/main.cpp
    - host/herdr_keypad/src/herdr_keypad/bridge.py
    - host/herdr_keypad/tests/test_codex.py
    - test/test_agent_projection/test_main.cpp
    - tools/capture_panel.py

requirements-completed: [CODEX-01, CODEX-02, CODEX-03, CODEX-04, SYNC-03, SAFE-01, MENU-01, MENU-02, MENU-03, MENU-04]
completed: 2026-08-21
---

# Phase 03 Plan 08: Exact-Device Capture and Pending Evidence Summary

**The complete automated matrix now feeds a fresh, exact-paired selected-usb deployment package whose logical framebuffer captures, contact sheets, tracer links, and pending physical rows share one canonical deployment identity.**

## Accomplishments

- Named the six-shape `R-BUCKET` acceptance row and covered zero, one, eight, and over-eight observed-key manifests, non-ASCII keys, hash-only bounds, top-level authority, `selected_key: null`, `bucket_unavailable`, and `E-2401`.
- Extended the existing capture enum/parser/`AgentProjection::capturePanel()` route with nine Codex scenes and nine menu scenes. All four production themes render every scene; no second renderer or capture transport was introduced.
- Fixed same-revision Codex-only publications so they repaint panel 4 without changing agent entries, bindings, pending focus, or agent-panel pixels. The guarded bridge now fences and reconnects instead of terminating on a rejected publication.
- Built and uploaded current `selected-usb` firmware through the project venv inside `ensure-bridge.sh run-exclusive`, required a fresh exact-pair hello, and restored a stable guarded bridge owner afterward.
- Captured 72 exact 128x128 RGB565 source frames and deployment-tagged PNGs. Generated user-openable 1152x512 Codex and menu contact sheets covering four themes, every required Codex state, all root viewports, brightness, HEALTH, ABOUT, and longest bounded values.
- Wrote and reopened a strict captures manifest and pending device evidence package. The evidence dereferences the checksummed tracer's bounded elapsed time, closed child-exit record, and redaction result through the three fixed JSON pointers.
- Kept framebuffer pixels explicitly classified as logical-only. Every Plan 09 optical, LED, brightness, key, timeout, confirmation, reboot, and resync observation remains a physical `pending` row.

## Task Commits

1. **Task 1: Complete the cross-layer Phase 3 acceptance matrix** — `35f13a8` (`test(03-08): name complete R-BUCKET matrix`)
2. **Task 2: Generate contact sheets and strict pending exact-device evidence** — `a9e19a4` (`feat(03-08): capture exact-device acceptance evidence`)

## Deployment and Evidence Linkage

- Deployment ID: `d2bc313730c8cb690a0d579cf0418bd86f5f717c229a0366b1b9faeedca4be5e`
- Deployed firmware SHA-256: `3886923cb0eddd0a15a192efce49fb7d9a8da6a7f32ab7d4f52104343f87b5e6`
- Capture manifest SHA-256: `985b313ad46da01de06f6f765a28313f614e85d7b8acf8b3a1a103b9e780eeca`
- Device evidence status: `pending`; checksum sidecar passes from repository root.

## Verification

- Host matrix: **51/51 passed**.
- Native projection/menu/LED/capture matrix: **67/67 passed**.
- Plan native protocol command completed successfully; its configured filter reported zero selected cases, while host golden-vector parity and the native projection protocol consumers passed.
- `phase3_smoke validate --allow-pending`: **passed** for the current deployment.
- `sha256sum -c artifacts/phase3/03-DEVICE-EVIDENCE.json.sha256`: **passed**.
- Both contact sheets opened successfully and report 1152x512 RGB PNG dimensions; every manifest source is 128x128 with matching RGB565/PNG hashes.
- Guarded bridge PID retained `bridge.lock` after deployment/capture and remained stable after Codex refresh.

## Deviations from Plan

- The exact deployment exposed a same-revision Codex-only firmware rejection that automated host tests alone could not reveal. The production projection path was corrected so a Codex/diagnostic-only update preserves agent identity and pending focus while repainting panel 4 only; agent drift at the same revision remains rejected.
- The permanent bridge had terminated on that rejected publication, leaving no guard owner to stop for a second upload. The bridge loop now converts a typed publication failure into the existing disconnect/reconnect fence. This restored the required sole guarded ownership before the final upload and kept the final owner stable.

## Next Phase Readiness

- Plan 03-09 can start from a current exact-device deployment with valid guarded bridge ownership.
- All physical Y/N/R observations remain pending and must be supplied only through the Plan 09 checkpoint.

## Self-Check: PASSED

- Both task commits exist.
- Current deployment, binary, captures, contact sheets, tracer audit link, and evidence checksum reopen under the same deployment ID.
- STATE and ROADMAP now advance to Plan 09.
