# Phase 1: Physical Keypad and Proven Transport - Context

**Gathered:** 2026-08-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove the delivered LILYGO T-Keyboard S3 Pro’s exact physical map and establish one measured, reliable, bounded host transport. The phase covers the connected unit’s displays, matching keys, encoder input, LEDs, orientation, brightness, reboot behavior, USB identity and rediscovery, and bidirectional framed traffic. USB remains preferred; exactly one v1 transport is selected from physical evidence, and hybrid transport is out of scope.

</domain>

<decisions>
## Implementation Decisions

### Bring-up Experience
- **D-01:** The primary Phase 1 validation path is a host-driven utility that exercises both the keypad hardware and the host transport.
- **D-02:** The utility runs one guided sequence rather than requiring the operator to discover and invoke independent checks.
- **D-03:** The guided run requires explicit human confirmation for every physical control and observable: each display and its orientation, each matching key, encoder click/direction, each relevant LED, brightness changes, and reboot behavior. Software must not infer that a physically observed result was correct.
- **D-04:** After the run passes and its evidence is preserved, archive the bring-up utility rather than maintaining it as a supported product diagnostic mode or folding it into the later bridge CLI.

### USB Proof Bar
- **D-05:** USB qualifies only as a strict bounded link: the defined proof run permits no unexplained frame loss, duplication, corruption, or out-of-order acceptance. Expected reset or unplug interruptions are acceptable only when reconnection is clean and uncertain in-flight work is discarded rather than replayed.
- **D-06:** Exercise realistic v1 traffic plus bounded peaks: expected snapshot/status cadence, worst-case legal frame sizes, rapid bidirectional bursts, and concurrent display/input activity. Maximum-rate stress unrelated to the product workload is not the acceptance target.
- **D-07:** Flashing and normal runtime use the same physical USB connection. After flashing or resetting, the runtime endpoint must return and be rediscovered without manual port selection.
- **D-08:** Select the single Wi-Fi fallback only for a repeatable failure on the delivered unit that still breaks the strict bounded-link bar after documented cable, USB-mode, permission, and host-binding remediation. Setup inconvenience alone does not disqualify USB.

### Recovery and Device Linking
- **D-09:** One privileged Linux setup is acceptable during Phase 1 development. The transport and identity design must nevertheless preserve an unprivileged later user experience, including first use with a new keypad; permanent root-only operation is not acceptable.
- **D-10:** A new keypad uses physical first-use pairing. The host stores an opaque device identity after explicit confirmation instead of trusting a transient port path or any matching device automatically. — **Reversibility:** costly — changing the pairing identity after later host and firmware work would require coordinated protocol and persisted-binding migration.
- **D-11:** After pairing, the host automatically rebinds only the exact paired keypad across device reset, unplug/replug, USB port changes, and endpoint renumbering. Look-alike or ambiguous devices fail closed rather than replacing the stored binding.
- **D-12:** The Phase 1 recovery proof covers device reset, unplug/replug on another USB port, endpoint renumbering, and host-utility restart. Full host reboot, suspend/resume, and cross-component product recovery remain later acceptance work.

### Agent Discretion
- Exact proof duration, legal frame bounds, burst profile, and measurement thresholds, provided they defend D-05 and D-06 with recorded evidence.
- The concrete unprivileged discovery mechanism and one-time development permission setup, provided runtime does not require root and no transient `/dev/tty*` path becomes device identity.
- The physical pairing challenge and confirmation representation, provided the user explicitly confirms the keypad and the resulting identity is opaque and stable.
- The evidence file format and archive layout; the unselected “Evidence record” gray area is left to standard project conventions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and Acceptance
- `.planning/PROJECT.md` — Defines the product boundary, physical surface, host authority, USB preference, credential boundary, and out-of-scope interactions.
- `.planning/REQUIREMENTS.md` — `HARD-01` and `HARD-03` define the Phase 1 physical-device and bounded-transport contracts; synchronization and safety requirements constrain later-compatible choices.
- `.planning/ROADMAP.md` — Phase 1 goal, mandatory physical research, success criteria, single-transport rule, and Wi-Fi fallback boundary.

### Prior Technical Research
- `.planning/research/SUMMARY.md` — Consolidated stack recommendation, dominant physical/transport risks, unresolved bring-up facts, and required USB operational proof.
- `.planning/research/STACK.md` — Recommended pinned firmware/host stack, official board-library APIs, USB CDC baseline, ButtonSense version discrepancy, and alternatives.
- `.planning/research/PITFALLS.md` — Board-generation/revision traps, STM32-mediated panel/input behavior, USB failure modes, and physical verification requirements.
- `.planning/research/ARCHITECTURE.md` — Proposed firmware/host boundaries and transport-neutral protocol structure; use as research input rather than an already-implemented convention.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- No firmware, host bridge, test utility, or application source exists yet; the repository currently contains planning and research artifacts only.

### Established Patterns
- No implementation pattern is established. Planning must create one coherent firmware/host structure rather than introduce parallel build or protocol conventions.
- Prior research favors the official LILYGO board abstraction, host-heavy authority, bounded versioned messages, and transport-neutral protocol boundaries; these are researched starting points that still require physical proof.

### Integration Points
- Device side: the delivered T-Keyboard S3 Pro through the official board library’s display, key, encoder, LED, brightness, and USB facilities.
- Host side: a Linux guided bring-up utility that discovers, pairs, drives, and measures the keypad without using a transient port name as identity.
- Boundary: the same bounded bidirectional protocol surface that later firmware and the herdr bridge can extend without retaining the one-off guided utility as product UI.

</code_context>

<specifics>
## Specific Ideas

- The bring-up experience should feel like one guided physical checklist: the host presents each step, the keypad produces the observable behavior, and the user confirms every control.
- One cable should cover flashing and runtime; the device should return from flash/reset without manual port selection.
- First linking should be physically confirmed, then exact-device reconnection should be automatic and independent of USB port numbering.

</specifics>

<deferred>
## Deferred Ideas

- Full host reboot, suspend/resume, independent component recovery, and complete product resynchronization remain Phase 4 acceptance work.
- A permanently supported diagnostic mode or bridge maintenance command was considered and rejected for Phase 1; the guided utility is archived after evidence capture.

</deferred>

---

*Phase: 1-Physical Keypad and Proven Transport*
*Context gathered: 2026-08-16*
