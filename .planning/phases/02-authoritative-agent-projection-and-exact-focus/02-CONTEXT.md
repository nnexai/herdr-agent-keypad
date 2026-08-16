# Phase 2: Authoritative Agent Projection and Exact Focus - Context

**Gathered:** 2026-08-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the three-agent projection and exact focus interaction: mirror the installed herdr inbox order onto the first three display keys, show authoritative identity/state, and send only a typed focus request for the exact displayed pane. No Codex usage tile, device menu, Wi-Fi transport, or broader recovery workflow belongs in this phase.

</domain>

<decisions>
## Implementation Decisions

### Tile identity and ordering
- **D-01:** Each occupied tile shows the agent title plus a compact workspace/repository discriminator so similarly named agents remain distinguishable.
- **D-02:** Tile order is the installed `herdr-agent-inbox` order. The bridge must not invent a second priority model or reorder entries in firmware.
- **D-03:** Keep three physical tile positions stable. When fewer than three entries exist, render explicit empty tiles rather than collapsing or shifting occupied positions.

### State and stale-data presentation
- **D-04:** Use Herdr-consistent color plus a compact glyph for blocked, finished/unseen, working, idle, settled, and unknown states.
- **D-05:** A stale, offline, vanished, incompatible, or reassigned entry freezes its last known identity with a visible stale/offline veil. Its key must reject focus until a fresh authoritative snapshot rebinds it.

### Focus interaction
- **D-06:** A key press sends focus-pane only for the exact opaque identity represented by that tile. No settle, dismiss, reply, approval, acknowledge, or arbitrary host action is permitted.
- **D-07:** Focus feedback is pending first, then success only after Herdr acknowledges the exact opaque identity, host epoch, and snapshot revision. Rejection, timeout, stale binding, or vanished pane must remain visibly distinct from success.

### the agent's Discretion
- Exact typography, glyph shapes, color values, tile layout, compact workspace truncation, pending timeout, and animation timing are implementation choices constrained by the existing 128×128 tile contract and UI-SPEC.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product scope and requirements
- `.planning/ROADMAP.md` §Phase 2 — authoritative phase goal, success criteria, and requirement mapping.
- `.planning/REQUIREMENTS.md` — INBX-01..04, FOCS-01..04, SYNC-02, SAFE-02.
- `.planning/PROJECT.md` — USB-first product boundary, credential ownership, truthfulness, and exact hardware constraints.
- `.planning/phases/01-physical-keypad-and-proven-transport/01-CONTEXT.md` — locked transport/protocol and hardware decisions from Phase 1.
- `.planning/phases/01-physical-keypad-and-proven-transport/01-UI-SPEC.md` — fixed four-tile visual contract and display constraints.

### Herdr integration authority
- `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/README.md` — installed inbox plugin behavior and metadata projection.
- `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/daemon.py` — installed plugin event/state integration.
- `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/inbox_tui.py` — verified ordering algorithm: `tokens.rank` ascending, then `state_change_seq` descending.
- `https://herdr.dev/docs/socket-api/` — public socket methods, snapshots, events, metadata tokens, and `agent.focus` contract.

### Existing transport and device seams
- `firmware/src/protocol/protocol.h` and `firmware/src/protocol/protocol.cpp` — Phase 1 production codec/session boundary; Phase 2 must consume it rather than create another parser.
- `firmware/src/main.cpp` — flashed dispatch integration point after Phase 1 runtime work.
- `firmware/src/board/physical_map.h` and `firmware/src/board/board_adapter.h` — canonical physical key/display mapping.
- `tools/phase1_bringup/src/phase1_bringup/` — host-side serial/session conventions and evidence patterns.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The Phase 1 production `ProtocolCodec`/`ProtocolSession` is the sole device admission and typed-dispatch boundary.
- The board adapter and physical map provide stable key indices and the four fixed 128×128 display surfaces.
- The host bridge already has Unix-socket, NDJSON, reconnect, and evidence conventions to extend rather than replace.

### Established Patterns
- Host owns provider credentials and authenticated Herdr/Codex access; firmware receives only normalized device-scoped data.
- The installed inbox is authoritative for ordering and lifecycle; missing `rank` must be treated as unavailable rather than replaced with a local priority algorithm.
- Snapshot generations and opaque identities must remain paired through rendering and focus dispatch; stale generations fail closed.

### Integration Points
- Herdr snapshot/event projection feeds a normalized three-entry device snapshot.
- The bridge maps each physical key to the corresponding opaque pane identity and snapshot revision.
- A focus response updates the pending tile state only after the host confirms the matching identity/epoch/revision.

</code_context>

<specifics>
## Specific Ideas

Use stable three-position tiles, title plus workspace discriminator, Herdr color plus glyph, explicit empty tiles, stale veil with focus rejection, and pending-then-result feedback. Keep all provider credentials and Herdr protocol details on the host.

</specifics>

<deferred>
## Deferred Ideas

- Codex subscription/usage tile and device menu belong to Phase 3.
- Host reboot, suspend/resume, and full cross-component recovery belong to Phase 4.
- Wi-Fi transport is not part of the product path.

</deferred>

---

*Phase: 02-authoritative-agent-projection-and-exact-focus*
*Context gathered: 2026-08-16*
