# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## phase2-blank-panels — Phase 2 flash blanked startup panels and broke snapshot/focus acknowledgement
- **Date:** 2026-08-17
- **Error patterns:** blank panels, serial read failed, stale descriptor closed, snapshot acknowledgement unavailable, digest_mismatch, unrelated Herdr response, PENDING never FOCUSED, source_revision_changed
- **Root cause(s):** Startup cleared displays instead of rendering WAIT; HWCDC's 256-byte RX queue truncated valid v2 frames; device payload insertion order broke canonical digests; the host used obsolete Herdr subscription parameters; source-revision rejection never published a fresh authoritative generation.
- **Fix:** Restored startup WAIT rendering, sized HWCDC RX to the protocol line buffer, canonicalized device payload construction, used installed typed subscriptions, and refreshed/rebound the complete snapshot after source revision drift.
- **Files changed:** firmware/src/main.cpp, firmware/src/app/agent_projection.cpp, firmware/src/transport/link.h, firmware/src/transport/usb_cdc.cpp, host/herdr_keypad/src/herdr_keypad/herdr.py, host/herdr_keypad/src/herdr_keypad/bridge.py, host/herdr_keypad/tests/test_integration.py
- **Why not caught:** Existing build/native/fake gates did not exercise physical startup pixels, a >256-byte CDC frame, installed Herdr subscription schema, or stale-to-fresh physical focus as one end-to-end path.
- **Recurrence guard:** `host/herdr_keypad/tests/test_integration.py:test_source_revision_drift_rebinds_before_fresh_retry`, typed subscription assertions, live >256-byte snapshot/digest smoke, and exact-device startup/focus acceptance.
---

## already-focused-hold-rejected — Structured Herdr session identity rejected an exact already-focused target
- **Date:** 2026-08-30
- **Error patterns:** REJECTED, already focused, hold-to-speak unavailable, no held Space, SessionChanged
- **Root cause(s):** Herdr 0.8.2 returns agent_session as a structured object; the complete-read projection canonicalized it while HerdrClient::focus_pane narrowed the matching acknowledgement to a string and silently produced None, so the exact session fence rejected the current target.
- **Fix:** HerdrFocusAck now preserves the raw agent_session JSON value and passes it through the existing canonical session_token identity fence.
- **Files changed:** host/herdr_keypad/native/src/lib.rs, host/herdr_keypad/native/src/ports/herdr.rs, host/herdr_keypad/native/tests/herdr_parity.rs, host/herdr_keypad/native/src/core/orchestrator.rs
- **Why not caught:** no gate existed for a structured non-string agent_session at the real Herdr socket-to-focus-authorization seam
- **Recurrence guard:** `host/herdr_keypad/native/tests/herdr_parity.rs:already_focused_structured_session_is_authorized` and `different_structured_session_remains_rejected`
---
