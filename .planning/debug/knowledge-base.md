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
