# Herdr Keypad Lifecycle

This procedure is for ordinary users of the Herdr keypad plugin. Herdr owns plugin installation and invocation. The plugin package contains one target-selected native executable at `bin/herdr-keypad` and this document as static content.

## Supported targets and package

- The supported release targets are **Linux x86-64** and **macOS Apple Silicon**.
- Herdr selects the package for the host target. The package contains `herdr-plugin.toml`, `bin/herdr-keypad`, and `LIFECYCLE.md`.
- The native executable uses Herdr-provided runtime information and the installed Codex command. No separately installed bridge runtime or package is needed.

## Install with Herdr

1. Install the selected known release through Herdr's plugin install action.
2. Herdr places the plugin under `HERDR_PLUGIN_ROOT`, including the target executable and this lifecycle document.
3. No additional configuration is required for an ordinary installation.
4. Use the plugin's startup action after installation; Herdr starts the native bridge for the active Herdr session.

## Start, status, stop, and restart

1. Invoke `start` through the plugin action surface to start the bridge, or to report the already-active instance when the effective configuration is unchanged.
2. Invoke `status` through the plugin action surface to read the current bridge state. `status` is read-only and does not change pairing, source data, focus, or device ownership.
3. Invoke `stop` through the plugin action surface for an explicit successful stop. A stopped bridge remains stopped until an explicit start, restart, or a later Herdr start.
4. Invoke `restart` through the plugin action surface to replace the current bridge authority and apply validated configuration changes.

The bridge exits when its launching Herdr session exits. Temporary source or device unavailability is reported with bounded state while that Herdr session remains alive. A bridge crash is recovered with an explicit `start` or `restart`, not with an unseen lifecycle action. Operational logging is off by default; when enabled by validated configuration, only bounded redacted events go to Herdr-captured `stderr`.

## Disable

1. Invoke `stop` through the plugin action surface.
2. Confirm a successful stop with the read-only `status` action.
3. Invoke `disable` through Herdr's plugin management surface.

Herdr `disable` does not stop an already-running bridge. Do not disable the plugin until the explicit stop has succeeded.

## Unlink

1. Invoke `stop` through the plugin action surface.
2. Confirm a successful stop with the read-only `status` action.
3. Invoke `unlink` through Herdr's plugin management surface.

Herdr `unlink` does not stop an already-running bridge. Do not unlink the plugin until the explicit stop has succeeded.

## Remove

1. Invoke `stop` through the plugin action surface.
2. Confirm a successful stop with the read-only `status` action.
3. Invoke `remove` through Herdr's plugin management surface and remove the selected plugin release.

Herdr removal does not stop an already-running bridge. Do not remove the plugin until the explicit stop has succeeded.

## Update activation

1. Install the selected new plugin release through Herdr's plugin install or update flow.
2. Use an explicit restart to activate the newly bundled executable while the current Herdr session remains alive.
3. If the bridge is not running, the next Herdr start invokes the updated startup hook.
4. The old bridge authority ends before the updated executable establishes fresh USB, Herdr, and Codex sessions.

Configuration is not handed to a live bridge. The updated executable reads its validated startup inputs and publishes current state after its fresh sessions are ready.

## Failed-update recovery

1. Invoke `stop` through the plugin action surface and confirm the stop succeeded.
2. Choose one specifically selected known plugin release that is expected to work.
3. Manually reinstall one specifically selected known plugin release through Herdr.
4. Invoke `start` through the restored plugin action surface.
5. Invoke `status` and continue only when the read-only result is bounded and reports the expected running or stopped state.

No automatic rollback is provided. If the chosen release is unavailable, select another known release and repeat the manual Herdr install after the bridge has stopped.

## Configuration and diagnostics

1. Keep advanced overrides only in validated files under `HERDR_PLUGIN_CONFIG_DIR`.
2. Apply a configuration change with an explicit `restart` or on the next Herdr start; configuration is not watched or reloaded while the bridge is running.
3. Herdr supplies `HERDR_PLUGIN_ROOT`, `HERDR_PLUGIN_CONFIG_DIR`, and `HERDR_PLUGIN_STATE_DIR`; these symbolic directories are the only plugin-owned locations used by the procedure.
4. Keep `status` as the read-only diagnostic action. It reports bounded operational state and does not expose credentials, account identity, private conversation content, host paths, or upstream response contents.
