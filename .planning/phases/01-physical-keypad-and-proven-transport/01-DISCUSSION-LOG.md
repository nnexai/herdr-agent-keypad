# Phase 1: Physical Keypad and Proven Transport - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-16
**Phase:** 1-Physical Keypad and Proven Transport
**Areas discussed:** Bring-up experience, USB proof bar, Recovery setup
**Area offered but not selected:** Evidence record

---

## Bring-up Experience

### Primary validation path

| Option | Description | Selected |
|--------|-------------|----------|
| Host-driven utility | A Linux command drives a small diagnostic firmware protocol, records results, and exercises the same host link future phases use. | ✓ |
| Dedicated test firmware | Flash a standalone diagnostic image that cycles displays, keys, encoder, LEDs, brightness, and reboot locally; transport proof happens separately. | |
| Retained self-test mode | Production firmware keeps a boot-time or key-combination diagnostic mode. | |

**User's choice:** Host-driven utility
**Notes:** Chosen as the primary Phase 1 hardware and transport validation path.

### Utility flow

| Option | Description | Selected |
|--------|-------------|----------|
| Guided run | One ordered session prompts for physical confirmations while automatically capturing board, USB, timing, and traffic facts. | ✓ |
| Independent commands | Separate commands for displays, keys, encoder, LEDs, brightness, reboot, and link tests. | |
| Both | A guided default built from individually runnable checks. | |

**User's choice:** Guided run
**Notes:** The operator should not have to discover the complete check sequence.

### Physical confirmation granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Confirm every control | Explicit confirmation for each display image/orientation, matching key, encoder click/direction, LED, and brightness change. | ✓ |
| Confirm grouped stages | One confirmation after each display, input, lighting, and reboot stage. | |
| Only flag failures | Run all checks and assume success unless the operator reports a problem. | |

**User's choice:** Confirm every control
**Notes:** Physical observations must be confirmed rather than inferred by software.

### Utility retention

| Option | Description | Selected |
|--------|-------------|----------|
| Keep as diagnostic tool | Retain a documented developer/troubleshooting command. | |
| Archive after evidence | Preserve the Phase 1 result, but do not maintain the guided utility after later firmware replaces it. | ✓ |
| Fold into bridge CLI | Make the same checks a permanent maintenance command of the eventual herdr bridge. | |

**User's choice:** Archive after evidence
**Notes:** The guided utility is a Phase 1 proof mechanism, not permanent product UI.

**Area completion:** Next area.

---

## USB Proof Bar

### Reliability standard

| Option | Description | Selected |
|--------|-------------|----------|
| Strict bounded link | No unexplained loss, duplication, corruption, or out-of-order acceptance; reset/unplug interruptions recover cleanly and uncertain in-flight work is discarded. | ✓ |
| Recoverable best effort | Occasional dropped telemetry is acceptable if the next authoritative snapshot repairs state and keypress commands remain exact. | |
| Functional exchange | Successful bidirectional exchange and basic reconnect are enough for Phase 1. | |

**User's choice:** Strict bounded link
**Notes:** USB must meet a control-surface reliability bar, not merely exchange sample frames.

### Proof workload

| Option | Description | Selected |
|--------|-------------|----------|
| Realistic plus bursts | Expected cadence, worst-case legal frames, rapid bidirectional bursts, and concurrent display/input operation. | ✓ |
| Realistic traffic only | Only the expected v1 message cadence and frame sizes. | |
| Maximum stress | Drive the endpoint at its maximum sustainable rate regardless of product workload. | |

**User's choice:** Realistic plus bursts
**Notes:** Prove normal operation and bounded peaks without inventing irrelevant throughput requirements.

### Flash/runtime lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| One cable, auto return | The same USB connection handles flashing and runtime; after flash/reset the endpoint returns and is rediscovered automatically. | ✓ |
| Manual flash is fine | Manual boot/flash steps are acceptable, but ordinary runtime recovery is automatic. | |
| Separate debug path | A distinct flashing/debug workflow or connection is acceptable. | |

**User's choice:** One cable, auto return
**Notes:** No manual port selection after flash or reset.

### Wi-Fi fallback trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Repeatable blocker | Switch only for a reproducible delivered-unit failure that remains after documented cable, USB mode, permission, and host-binding fixes. | ✓ |
| Operational friction | Persistent setup or rediscovery friction can justify Wi-Fi even when USB integrity is sound. | |
| USB must win | Keep fixing USB; do not select Wi-Fi within Phase 1. | |

**User's choice:** Repeatable blocker
**Notes:** Inconvenience alone does not change the preferred transport.

**Area completion:** Next area.

---

## Recovery Setup

### Linux permission setup

| Option | Description | Selected |
|--------|-------------|----------|
| One privileged setup | A setup command may install a narrow udev rule or group permission once; later operation is unprivileged. | Modified |
| No privileged changes | Work without udev rules, group changes, or sudo. | |
| Runtime sudo is acceptable | Run the host utility or bridge elevated whenever used. | |

**User's choice:** “for development one privileged setup - for later user experience i would prefer unprivileged permissions only ( even when running on a new device ) - this means careful consideration how the linking between keypad and host device are done”
**Notes:** Phase 1 development may use one privileged setup. The transport/linking design must preserve an unprivileged eventual new-device experience and cannot depend on permanent root-only operation.

### First-use device linking

| Option | Description | Selected |
|--------|-------------|----------|
| Physical first-use pairing | Discover matching devices, present a pairing challenge, require keypad confirmation, then store an opaque device identity. | ✓ |
| Auto-bind sole keypad | Trust and bind the only matching VID/PID device; fail if multiple are present. | |
| Configured serial identity | Require manual selection or entry of a USB serial/device ID. | |

**User's choice:** Physical first-use pairing
**Notes:** Linking must be explicit while remaining compatible with unprivileged discovery.

### Reconnection identity

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-rebind exact keypad | Rediscover the stored opaque identity on any USB port; reject look-alike or ambiguous devices. | ✓ |
| Confirm every reconnect | Require physical confirmation whenever the endpoint disappears and returns. | |
| Bind any sole keypad | Reconnect to whichever compatible keypad is currently the only match. | |

**User's choice:** Auto-rebind exact keypad
**Notes:** A transient `/dev/tty*` path or sole-device assumption is not identity.

### Phase 1 recovery scope

| Option | Description | Selected |
|--------|-------------|----------|
| Transport lifecycle | Prove device reset, unplug/replug on another port, endpoint renumbering, and host-utility restart. | ✓ |
| Add Linux reboot | Also require pairing and access to survive a full host reboot in Phase 1. | |
| Add suspend and reboot | Also prove host suspend/resume and reboot now. | |

**User's choice:** Transport lifecycle
**Notes:** Full host/component recovery remains later milestone work.

**Area completion:** Finish areas.

---

## Agent Discretion

- Exact proof duration, legal frame bounds, burst profile, and quantitative measurement thresholds.
- Concrete unprivileged discovery and one-time development permission mechanisms.
- Physical pairing challenge representation and stored opaque identity format.
- Evidence file format and archive layout; “Evidence record” was offered as a gray area but not selected for discussion.

## Deferred Ideas

- Full host reboot, suspend/resume, independent component recovery, and complete product resynchronization remain Phase 4 acceptance work.
- A permanent diagnostic mode or bridge maintenance command was considered but rejected for Phase 1.
