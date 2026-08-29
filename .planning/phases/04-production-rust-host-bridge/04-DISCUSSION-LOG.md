# Phase 04: Production Rust Host Bridge - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-29
**Phase:** 04-Production Rust Host Bridge
**Areas discussed:** Launch and lifecycle, Install and upgrades, Config and migration, Diagnostics surface

---

## Launch and lifecycle

### Primary launch ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Herdr-managed | Herdr starts the bundled native binary through its plugin lifecycle. | ✓ |
| OS user service | systemd user unit on Linux and LaunchAgent on macOS. | |
| Foreground command | User runs the binary explicitly. | |
| You decide | Defer to lifecycle research. | |

**User's choice:** Herdr-managed.

### Herdr exit or restart

| Option | Description | Selected |
|--------|-------------|----------|
| Stay alive and reconnect | Keep the bridge and independent boundaries alive; mark Herdr offline and reconnect. | ✓ |
| Exit with Herdr | New Herdr process creates a new bridge process. | |
| Grace period then exit | Retry for a bounded period before stopping. | |
| You decide | Follow the verified plugin process contract. | |

**User's choice:** Stay alive and reconnect.
**Notes:** The user explicitly asked whether a Herdr server restart can recover without restarting the bridge. Recovery is required: fence actions, reconnect, and complete authoritative resynchronization.

### Intentional shutdown

| Option | Description | Selected |
|--------|-------------|----------|
| Disable, stop, or logout | Plugin disable/removal, explicit stop, or user logout ends the bridge. | ✓ |
| Explicit stop only | Survive every other lifecycle event. | |
| Plugin disable only | Herdr plugin state is the only administrative control. | |
| You decide | Follow available Herdr/OS lifecycle primitives. | |

**User's choice:** Disable, stop, or logout. Ordinary Herdr restarts do not stop it.

### Repeated matching start

| Option | Description | Selected |
|--------|-------------|----------|
| Report running and succeed | Idempotent start; leave live authority untouched. | ✓ |
| Fail clearly | Return an already-running error. | |
| Replace the process | Stop the old process and take over. | |
| You decide | Choose while enforcing one authority. | |

**User's choice:** Report running and succeed.

### Herdr-restart presentation

| Option | Description | Selected |
|--------|-------------|----------|
| Last entries under offline veil | Retain orientation, mark unavailable, disable actions. | ✓ |
| Global synchronization screen | Replace all agent content with SYNC/OFFLINE. | |
| Clear to empty | Remove entries and show empty/offline tiles. | |
| You decide | Reuse the established failure-state contract. | |

**User's choice:** Last entries under offline veil.

### Herdr not ready at bridge start

| Option | Description | Selected |
|--------|-------------|----------|
| Remain running and wait | Keep retrying with bounded backoff. | ✓ |
| Bounded wait then exit | Let a later event restart the process. | |
| Fail immediately | Require strict startup ordering. | |
| You decide | Follow the actual Herdr startup contract. | |

**User's choice:** Remain running and wait.

### Bridge-process crash recovery

| Option | Description | Selected |
|--------|-------------|----------|
| Automatic Herdr restart | Herdr/plugin lifecycle restarts the bridge. | ✓ |
| Restart on next Herdr event | No continuous restart supervision. | |
| Manual restart | User must start it again. | |
| You decide | Use the strongest supported Herdr behavior. | |

**User's choice:** Automatic Herdr restart.

### Repeated crash policy

| Option | Description | Selected |
|--------|-------------|----------|
| Keep retrying with capped backoff | Remain self-healing and expose a bounded persistent diagnostic. | ✓ |
| Stop after a threshold | Require an explicit reset after repeated failure. | |
| Retry only on new events | End the loop until another Herdr event. | |
| You decide | Match the supervisor contract without a hot loop. | |

**User's choice:** Keep retrying with capped backoff.

### HID Space during bridge stop

| Option | Description | Selected |
|--------|-------------|----------|
| Release first, then exit | Bridge commands a bounded release before shutdown. | |
| Exit immediately | Rely on device/USB lifecycle. | |
| Refuse while active | Wait for physical release. | |
| Device retains authority | Bridge stop does not synthesize Space-up; physical release or device lifecycle ends it. | ✓ |

**User's choice:** Device retains authority.
**Notes:** The first prompt incorrectly treated the bridge as the active HID owner. The user corrected this: Space is controlled by firmware after assertion. The final decision supersedes the earlier provisional selection.

### Exact keypad absent at startup

| Option | Description | Selected |
|--------|-------------|----------|
| Stay alive and reconnect | Report unavailable and attach only when the exact paired device appears. | ✓ |
| Exit after bounded wait | Rely on a later event or explicit start. | |
| Exit immediately | Require the device before startup. | |
| You decide | Follow existing exact-pair recovery. | |

**User's choice:** Stay alive and reconnect.

### Host suspend/resume

| Option | Description | Selected |
|--------|-------------|----------|
| Same process recovers | Invalidate old sessions and reconnect every boundary. | ✓ |
| Clean process restart | Exit and let Herdr start a new process. | |
| Either is acceptable | Lock only fresh-session observable behavior. | |
| You decide | Follow verified platform suspend primitives. | |

**User's choice:** Same process recovers.

### Changed configuration on repeated start

| Option | Description | Selected |
|--------|-------------|----------|
| Reject configuration mismatch | Active configuration remains unchanged. | |
| Reconfigure live | Fence authority and atomically adopt changed settings in the active process. | ✓ |
| Replace explicitly | Perform a clean process handoff. | |
| You decide | Choose the narrowest one-authority behavior. | |

**User's choice:** Reconfigure live.
**Notes:** The user expects only one Herdr instance and considers reconfiguration the best experience when that instance changes settings.

---

## Install and upgrades

### Distribution shape

| Option | Description | Selected |
|--------|-------------|----------|
| Bundled Herdr plugin | Plugin includes the correct native executable. | ✓ |
| Release archive | Separate platform archive and install script. | |
| Native package managers | Homebrew and Linux package channels. | |
| You decide | Choose the narrowest two-platform distribution. | |

**User's choice:** Bundled Herdr plugin.

### Release architectures

| Option | Description | Selected |
|--------|-------------|----------|
| Linux x64 + macOS Apple Silicon | Current Linux architecture plus current-generation Mac architecture. | ✓ |
| Linux x64 + macOS universal | Add Intel macOS. | |
| Linux and macOS, x64 + ARM64 | Four native targets. | |
| You decide | Infer the minimum honest matrix. | |

**User's choice:** Linux x86-64 and macOS Apple Silicon.

### Upgrade activation

| Option | Description | Selected |
|--------|-------------|----------|
| Controlled immediate restart | End old authority, start new binary, establish fresh sessions. | ✓ |
| Next Herdr restart | Delay activation until Herdr restarts. | |
| Live handoff | Transfer live state between versions. | |
| You decide | Use the safest supported plugin lifecycle. | |

**User's choice:** Controlled immediate restart.

### Rollback

| Option | Description | Selected |
|--------|-------------|----------|
| Rollback whole plugin bundle | Restore previous plugin and binary automatically. | |
| Rollback binary, reset state | Restore executable and rebuild non-pairing state. | |
| Manual reinstall only | Document reinstall of a known plugin release. | ✓ |
| You decide | Choose a bounded rollback contract. | |

**User's choice:** Manual reinstall only.

---

## Config and migration

### Existing keypad binding

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse it in place | Read the existing binding without rewriting it. | ✓ |
| Import to new state | One-time validated import to Rust-owned state. | |
| Require fresh pairing | Pair the keypad again for Rust. | |
| You decide | Choose after freezing the binding contract. | |

**User's choice:** Reuse `~/.config/herdr/keypad-binding.json` in place.

### Ordinary configuration

| Option | Description | Selected |
|--------|-------------|----------|
| Zero required configuration | Discover safe defaults and use Herdr runtime data. | ✓ |
| Herdr plugin settings | Require user-editable plugin settings. | |
| Standalone config file | Require per-user TOML. | |
| You decide | Choose the narrowest safe surface. | |

**User's choice:** Zero required configuration.

### Advanced overrides

| Option | Description | Selected |
|--------|-------------|----------|
| Herdr plugin settings | One validated administrative surface. | ✓ |
| Bridge config file | Platform-native strict TOML. | |
| Command-line arguments | Plugin supplies explicit persistent arguments. | |
| You decide | Choose one deterministic authority. | |

**User's choice:** Herdr plugin settings.

### Invalid or incompatible state

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed and preserve | Do not rewrite, guess, or connect to another device. | ✓ |
| Quarantine and reset | Move invalid state aside and start from defaults. | |
| Best-effort migration | Salvage and rewrite recognized fields. | |
| You decide | Choose after freezing Python formats. | |

**User's choice:** Fail closed and preserve.

---

## Diagnostics surface

### Primary diagnostic entry

| Option | Description | Selected |
|--------|-------------|----------|
| Herdr plugin status | One product-native operational view. | ✓ |
| Bridge CLI status | Query the active process through the bundled executable. | |
| Device HEALTH page | Make the keypad menu primary. | |
| You decide | Keep device HEALTH while choosing one primary host surface. | |

**User's choice:** Herdr plugin status.

### Default detail

| Option | Description | Selected |
|--------|-------------|----------|
| Current summary plus recent transitions | Present health, identity, backoff, last error, and bounded recent transitions. | ✓ |
| Current summary only | Present current health and one error. | |
| Verbose operational trace | Present detailed requests/protocol/timing events. | |
| You decide | Derive the smallest useful parity status. | |

**User's choice:** Current summary plus recent transitions.

### Log ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Herdr-owned plugin logs | Structured redacted events through Herdr logging. | ✓ |
| Per-user rotating files | Bridge-owned platform-native files. | |
| OS logging facilities | journald and macOS unified logging. | |
| You decide | Prefer Herdr if its verified contract is sufficient. | |

**User's choice:** Herdr-owned plugin logs.

### Diagnostic mutations

| Option | Description | Selected |
|--------|-------------|----------|
| Read-only status | Keep start/stop/restart/repair separate. | ✓ |
| Status plus restart | Add one restart action. | |
| Status plus guided repair | Add restart, config repair, and re-pairing. | |
| You decide | Preserve observation/authority separation. | |

**User's choice:** Read-only status.

---

## the agent's Discretion

No user question was delegated with “You decide.” Technical choices left to research and planning are captured in `04-CONTEXT.md` under **the agent's Discretion**.

## Deferred Ideas

None. Discussion stayed within Phase 4.
