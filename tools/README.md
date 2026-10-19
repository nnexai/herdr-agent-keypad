# Keypad developer diagnostics

Production is the bundled Rust Herdr plugin. Python under `tools/` is for diagnostics, not a snapshot publisher or host bridge; stdlib CI/release evidence tools remain separately under `host/herdr_keypad/release/`. Historical evidence and phase documents retain their original meaning.

## Stop, lease, capture, restart

Run from the repository root with the diagnostics venv. Discover and cache the real state directory **while the installed bridge is running** (Linux `/proc` discovery; default plugin root `~/.local/share/herdr/plugins/herdr-keypad`). Continue only if `locate` succeeds:

```bash
PY=tools/phase1_bringup/.venv/bin/python3
LEASE="$PY tools/keypad_lease.py"
STATE_DIR="$($LEASE locate)"
# For another installation: $LEASE locate --plugin-root /absolute/plugin/root
# In Herdr's herdr-keypad plugin actions, invoke stop, then status.
# Continue only when status reports stopped.
$LEASE run --state-dir "$STATE_DIR" -- \
  $PY tools/capture_panel.py 0 /tmp/keypad-current.ppm
$LEASE run --state-dir "$STATE_DIR" -- \
  $PY tools/capture_panel.py 0 /tmp/keypad-beacon.ppm --theme beacon --scene blocked
# Before start, check the exact paired device with fuser; no holder may remain.
# In Herdr's herdr-keypad plugin actions, explicitly invoke start.
```

The `current` capture is the firmware's rendering **after the Rust host session ended**, not proof of a still-live authoritative snapshot. Record what the device actually shows; use deterministic theme/scene captures for visual regression. Capture writes PPM plus a `.rgb565` sidecar. See the repository `screen-capture-flow` skill for conversion and pixel interpretation.

**Never open the port without the lease.** Always use `$LEASE run`: it holds the existing Rust `state_dir/bridge.lock`, bounds child lifetime, cleans up the child process group, and independently checks authority release with a fresh `flock`. Supplementary `/proc` holder scans are best-effort: known visible device holders block, but inaccessible processes produce a visibility warning, not proof that every tty is closed. Shared authority exclusion remains mandatory even with limited visibility. Never fabricate fd 9 or lease environment variables. This is cooperative same-user mutual exclusion, not authentication or a security boundary. The runner neither creates the lock nor stops/restarts Herdr. `run` accepts `--state-dir DIR` or `HERDR_PLUGIN_STATE_DIR`; do not guess/create a state directory or call `locate` after stopping.

## Other retained workflows

Use the same cached state and stopped bridge for every device command; restart explicitly only after release:

```bash
$PY -m platformio run -e selected-usb
$LEASE run --state-dir "$STATE_DIR" -- $PY -m platformio run -e selected-usb -t upload
$LEASE run --state-dir "$STATE_DIR" -- $PY -m phase1_bringup pair
$LEASE run --state-dir "$STATE_DIR" -- $PY -m phase1_bringup recover --interruption utility-restart
# Hardware-free; no lease or stop required:
$PY -m phase1_bringup self-check --schema protocol/schema/v1.json --protocol-golden protocol/fixtures/v1-golden.json \
  --pairing --discovery --serial-reconnect --udev-rule host/udev/99-herdr-keypad.rules
```

`pair` is the binding writer and requires its physical challenge; it is not routine capture preparation. Retained historical qualification/capture commands also require the lease. Artifact-only evidence verifiers remain hardware-free; use each module's `--help` for its retained modes.

## Exit codes and failed release

`run` accepts `--wait-seconds 0..10` (default `0`) and `--max-seconds 1..3600` (default `900`). After verified authority release and no known visible device holders, it returns the child's code; runner codes are `2` invalid arguments/state/discovery, `3` device held before child start, `75` authority busy, and `124` child timeout. Codes `4` (lock still held) or `5` (device still visibly open) mean **not released** and take precedence over the child's result. Inspect the printed holder PIDs; never start the bridge while a holder remains. A visibility-limited warning means absence of other holders cannot be proved; `fuser` can also be visibility-limited. After resolving known holders, or after an interrupted runner, require this recheck to exit `0`, then inspect the exact paired device with `fuser` before Herdr `start`:

```bash
$LEASE run --state-dir "$STATE_DIR" --wait-seconds 0 -- true
```

Keep generated captures and local build output out of commits unless explicitly requested as fixtures. Do not rewrite historical `.planning/phases/` documents or `artifacts/` to describe the new workflow.
