# Set up an existing release on a new Mac

This guide installs an existing Herdr Agent Keypad release on a new Mac. It does not build the firmware or the native bridge.

The current macOS package supports Apple Silicon only. The keypad must already run the matching firmware, and you must have the pairing file for that physical keypad.

## What you need

- An Apple Silicon Mac. `uname -m` must print `arm64`.
- Herdr 0.8.2 or newer.
- Codex CLI installed and signed in with the ChatGPT account whose subscription limits should appear on the fourth key.
- The `herdr-keypad-aarch64-apple-darwin.tar.gz` release archive.
- The existing `keypad-binding.json` for this physical keypad.
- The flashed keypad and a USB data cable.

The release is unsigned and not notarized. Keep the archive and its evidence files together so you can check their hashes before removing a quarantine attribute.

## 1. Check the Mac and host tools

Run:

```bash
uname -m
herdr --version
codex --version
codex login status
```

Continue only when:

- `uname -m` prints `arm64`.
- Herdr is at least `0.8.2`.
- `codex login status` reports a ChatGPT login. API-key authentication does not provide ChatGPT subscription-window data for the limits key.

If Herdr is not installed, use its official installer:

```bash
curl -fsSL https://herdr.dev/install.sh | sh
```

Then open a project directory and run `herdr` once. This starts the default Herdr session and creates its configuration directories.

## 2. Verify and unpack the release

Set `KEYPAD_ARCHIVE` to the archive you already have. Keep the extracted plugin in a stable directory because Herdr links to that directory rather than copying it.

```bash
KEYPAD_ARCHIVE="$HOME/Downloads/herdr-keypad-aarch64-apple-darwin.tar.gz"
PLUGIN_DIR="$HOME/.local/share/herdr-keypad/0.1.0"
mkdir -p "$PLUGIN_DIR"
tar -xzf "$KEYPAD_ARCHIVE" -C "$PLUGIN_DIR"
chmod 755 "$PLUGIN_DIR/bin/herdr-keypad"
```

The directory must contain these files:

```text
herdr-plugin.toml
LIFECYCLE.md
bin/herdr-keypad
release-manifest.json
```

Check the binary architecture and compare its hash with the release manifest:

```bash
file "$PLUGIN_DIR/bin/herdr-keypad"
EXPECTED_BINARY_SHA="$(plutil -extract binary.sha256 raw -o - "$PLUGIN_DIR/release-manifest.json")"
ACTUAL_BINARY_SHA="$(shasum -a 256 "$PLUGIN_DIR/bin/herdr-keypad" | cut -d ' ' -f 1)"
test "$EXPECTED_BINARY_SHA" = "$ACTUAL_BINARY_SHA" && echo "binary hash matches"
```

`file` must identify an arm64 Mach-O executable. The final command must print `binary hash matches`.

If you also have `phase04-macos-evidence.json`, check the archive before extraction or linking:

```bash
EXPECTED_ARCHIVE_SHA="$(plutil -extract archive_sha256 raw -o - phase04-macos-evidence.json)"
ACTUAL_ARCHIVE_SHA="$(shasum -a 256 "$KEYPAD_ARCHIVE" | cut -d ' ' -f 1)"
test "$EXPECTED_ARCHIVE_SHA" = "$ACTUAL_ARCHIVE_SHA" && echo "archive hash matches"
```

A hash match detects corruption. It is not a code signature.

If macOS quarantined the downloaded binary, remove that attribute only after the hash check passes:

```bash
if xattr -p com.apple.quarantine "$PLUGIN_DIR/bin/herdr-keypad" >/dev/null 2>&1; then
  xattr -d com.apple.quarantine "$PLUGIN_DIR/bin/herdr-keypad"
fi
```

Do not link `host/herdr_keypad` directly from a source checkout. The source tree does not contain the target-specific `bin/herdr-keypad` release executable.

## 3. Move the keypad pairing file

The bridge reads one pairing file from:

```text
~/.config/herdr/keypad-binding.json
```

Migration Assistant may have copied it already. Check first:

```bash
test -f "$HOME/.config/herdr/keypad-binding.json" && echo "pairing file found"
```

If it is missing, copy `~/.config/herdr/keypad-binding.json` from the old Mac or from your backup. On the new Mac:

```bash
mkdir -p "$HOME/.config/herdr"
chmod 700 "$HOME/.config/herdr"
cp /path/to/keypad-binding.json "$HOME/.config/herdr/keypad-binding.json"
chmod 600 "$HOME/.config/herdr/keypad-binding.json"
```

Do not hand-edit this file or reuse one from another keypad. The bridge validates its exact schema and checks the device identity during the USB handshake.

The current production `re-pair` action does not create a new pairing file. If no valid binding exists anywhere, this release cannot complete first-time pairing on the new Mac. Recover the binding from the old host or its backup before continuing.

## 4. Connect and link the plugin

Connect the keypad directly with a USB data cable. No macOS serial driver or kernel extension is required.

Link the extracted plugin and check that Herdr sees it:

```bash
herdr plugin link --enabled "$PLUGIN_DIR"
herdr plugin list --plugin herdr-keypad --json
herdr plugin action list --plugin herdr-keypad
```

If Herdr reports that `herdr-keypad` is already linked, remove the old link and repeat the link command:

```bash
herdr plugin unlink herdr-keypad
herdr plugin link --enabled "$PLUGIN_DIR"
```

The plugin actions should include `start`, `stop`, `restart`, `status`, `repair`, and `re-pair`.

## 5. Start the bridge

Run these commands inside a Herdr shell pane or from another terminal attached to the same user account:

```bash
herdr plugin action invoke --plugin herdr-keypad start
herdr plugin action invoke --plugin herdr-keypad status
```

The status response is JSON. A complete connection reports:

- `state` as `ready`.
- `device_state` as `ready`.
- `herdr_state` as `ready`.
- `codex_state` as `ready`.

The bridge remains tied to the Herdr session that launched it. Closing one client window does not stop the Herdr server, but stopping that Herdr session ends the bridge authority.

## 6. Check the physical workflow

1. Confirm that up to three agent keys show the same leading entries as the Herdr inbox.
2. Confirm that the fourth key shows current Codex subscription-limit data rather than stale or unavailable data.
3. Press an agent key once. Herdr should focus that agent pane without settling, dismissing, or acknowledging the inbox entry.
4. Hold an agent key past the hold threshold. Herdr should focus the pane first, then the keypad should behave as a held Space key until release.

Run `status` again after this check:

```bash
herdr plugin action invoke --plugin herdr-keypad status
```

## Optional configuration

The defaults are suitable for normal use. To see the plugin configuration directory:

```bash
CONFIG_DIR="$(herdr plugin config-dir herdr-keypad)"
printf '%s\n' "$CONFIG_DIR"
```

The only supported file is `$CONFIG_DIR/config.toml`. The closed configuration accepts these fields:

```toml
logging_enabled = false
reconnect_initial_ms = 500
reconnect_max_ms = 8000
```

`reconnect_initial_ms` must be between 100 and 8000. It cannot exceed `reconnect_max_ms`, and the maximum cannot exceed 8000. Unknown fields make the configuration invalid.

Apply a change with an explicit restart:

```bash
herdr plugin action invoke --plugin herdr-keypad restart
herdr plugin action invoke --plugin herdr-keypad status
```

## Troubleshooting

### `device_unavailable`

- Confirm the cable carries data, not power only.
- Disconnect other copies of the same development board. Ambiguous matches fail closed.
- Check whether macOS created a stable callout device with `ls /dev/cu.*`.
- Inspect USB descriptors with `system_profiler SPUSBDataType`.
- The qualified USB identity is VID `303a`, PID `1001`, serial `8C:BF:EA:0D:CB:FC`, CDC interface `01`.
- Reconnect the keypad, wait for it to boot, then invoke `restart`.

### `binding_invalid` or a missing pairing file

Restore the exact `~/.config/herdr/keypad-binding.json` from the old host or backup. Permissions should be `600`, and the parent directory should be `700`.

### `herdr_unavailable`

Start or attach to Herdr with `herdr`, then invoke the plugin `restart` action. Do not try to run the bundled binary directly. Herdr supplies the socket, process identity, plugin configuration directory, and plugin state directory that the bridge requires.

### `codex_unavailable`

Run:

```bash
codex login status
```

Sign in with the intended ChatGPT account, then invoke `restart`. An API-key-only session cannot supply ChatGPT subscription quota.

### macOS refuses to open the binary

Recheck the binary hash. If it matches, remove only the binary's `com.apple.quarantine` attribute as shown in step 2. Do not disable Gatekeeper globally.

### The bridge does not start or exits

Read the bounded plugin logs and current status:

```bash
herdr plugin log list --plugin herdr-keypad --limit 20
herdr plugin action invoke --plugin herdr-keypad status
```

Operational logging is off by default. Set `logging_enabled = true`, restart once, reproduce the problem, and turn it off again after collecting the bounded logs.

## Updating or removing the setup

To install a newer existing release, unpack it into a new versioned directory, verify it, unlink the old directory, link the new directory, then invoke `restart`. Keep the pairing file in place.

To remove the plugin cleanly:

```bash
herdr plugin action invoke --plugin herdr-keypad stop
herdr plugin action invoke --plugin herdr-keypad status
herdr plugin unlink herdr-keypad
```

Confirm the stopped state before unlinking. Unlinking the plugin does not stop an already-running bridge.
