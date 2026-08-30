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

## native-ack-churn-never-ready — Exact ACKs could not establish readiness under publication churn and missing ACKs never expired
- **Date:** 2026-08-30
- **Error patterns:** stale, device_unavailable, exact ACK, publication churn, reconnect_attempt 0, last_error null, focus starvation
- **Root cause(s):** Accepted exact snapshot ACK link health was incorrectly gated on publication_dirty becoming quiescent, so continuous coalescing never established readiness or drained focus; PendingPublication had no bounded ACK deadline or expiry transition, so a missing ACK remained pending forever without reconnect or safe error evidence.
- **Fix:** RuntimeCoordinator now tracks authenticated device link readiness independently from Herdr generation usability, establishes link health on one exact accepted ACK, continues coalesced publication separately, and expires missing ACKs into fail-closed session teardown, bounded reconnect, and safe status evidence.
- **Files changed:** host/herdr_keypad/native/src/core/orchestrator.rs, host/herdr_keypad/native/tests/resource_bounds.rs
- **Why not caught:** No coordinator regression gate independently modeled authenticated ACK link health under endless generation invalidation or expired a sent publication that never receives an ACK.
- **Recurrence guard:** `host/herdr_keypad/native/src/core/orchestrator.rs` tests `invalidation_before_an_exact_ack_still_establishes_link_readiness`, `focus_waiting_during_coalesced_publication_gets_a_bounded_result`, `sent_publication_without_ack_reconnects_within_the_bounded_deadline`, `mismatched_snapshot_ack_fields_never_establish_link_readiness`, and `ack_timeout_recovery_surfaces_bounded_safe_status`.
---
