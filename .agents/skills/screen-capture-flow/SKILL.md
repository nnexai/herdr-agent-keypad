---
name: screen-capture-flow
description: This skill should be used when the user asks to "capture keypad screenshots", "dump the device framebuffer", "compare rendered panels", "inspect on-device rendering", or refine LILYGO keypad display geometry from actual pixels.
version: 0.1.0
---

# Screen Capture Flow

Capture the composed 128×128 panel framebuffer directly from the connected keypad over USB. Use this flow to compare firmware output with the Phase 02.2 design contract without relying on a camera, optical alignment, display glare, or subpixel distortion.

## Scope

Use the capture path for logical rendering verification:

- Capture the exact RGB565 pixels produced immediately before panel flush.
- Inspect geometry, placement, palette, bands, rings, glyphs, text clipping, and panel-4 composition.
- Compare captures against `.planning/phases/02.2-firmware-themes-led-bars-and-device-selection-menu/02.2-UI-SPEC.md` and `.planning/research/DESIGN-PROPOSALS.html`.
- Refine firmware composition code, rebuild, flash, and recapture.

Do not treat a framebuffer capture as proof of physical brightness, viewing-angle legibility, panel orientation, LED output, or optical artifacts. Use a camera or direct human observation for those hardware properties.

## Preconditions

Run commands from the repository root. Use the supplied environment for every Python or PlatformIO operation:

```text
tools/phase1_bringup/.venv/bin/python3
```

Require:

- A paired keypad binding at `~/.config/herdr/keypad-binding.json`.
- The keypad enumerated as the exact paired USB identity.
- Firmware containing the capture seam and `tools/capture_panel.py`.
- Exclusive serial ownership. Stop the bridge before direct capture or firmware upload:

```bash
host/herdr_keypad/scripts/ensure-bridge.sh stop-for-acceptance
```

The bridge may be restarted after capture or upload. Never select the first arbitrary `/dev/ttyACM*`; `capture_panel.py` uses exact pairing and fresh hello validation.

## Standard Capture

1. Build and upload the current firmware when source changed:

   ```bash
   tools/phase1_bringup/.venv/bin/python3 -m platformio run
   tools/phase1_bringup/.venv/bin/python3 -m platformio run -t upload
   ```

2. Publish a current authoritative snapshot if tile captures need real agent content:

   ```bash
   PYTHONPATH=host/herdr_keypad/src:tools/phase1_bringup/src \
     tools/phase1_bringup/.venv/bin/python3 -m herdr_keypad \
     --smoke \
     --binding "$HOME/.config/herdr/keypad-binding.json" \
     --evidence artifacts/phase2/capture-smoke.json
   ```

   The snapshot command requires the bridge or direct host session according to the current runtime. If the bridge owns the serial device, stop it before invoking a direct capture.

3. Capture one zero-based panel. Panel `0`–`2` are agent tiles; panel `3` is panel 4:

   ```bash
   tools/phase1_bringup/.venv/bin/python3 \
     tools/capture_panel.py 0 artifacts/phase2/panel-1.ppm
   ```

   The utility sends the bounded `probe` stimulus `CAPTURE:N` for a live capture or the extended deterministic fixture form when `--theme` / `--scene` is present. It waits for `probe_ack`, validates the `SCREENSHOT-RGB565\n` marker, reads exactly `128 × 128 × 2` bytes, and writes both PPM and a `.rgb565` sidecar.

4. Convert and inspect the capture:

   ```bash
   ffmpeg -hide_banner -loglevel error \
     -f image2 -i artifacts/phase2/panel-1.ppm \
     -frames:v 1 artifacts/phase2/panel-1.png
   ```

5. Capture all panels and create a contact sheet when reviewing panel relationships:

   ```bash
   for n in 0 1 2 3; do
     tools/phase1_bringup/.venv/bin/python3 tools/capture_panel.py \
       "$n" "artifacts/phase2/panel-$((n + 1)).ppm"
     ffmpeg -hide_banner -loglevel error \
       -f image2 -i "artifacts/phase2/panel-$((n + 1)).ppm" \
       -frames:v 1 "artifacts/phase2/panel-$((n + 1)).png"
   done
   ffmpeg -hide_banner -loglevel error \
     -i artifacts/phase2/panel-1.png \
     -i artifacts/phase2/panel-2.png \
     -i artifacts/phase2/panel-3.png \
     -i artifacts/phase2/panel-4.png \
     -filter_complex \
     '[0:v][1:v][2:v][3:v]xstack=inputs=4:layout=0_0|128_0|0_128|128_128' \
     -frames:v 1 artifacts/phase2/panels-contact.png
   ```

## Deterministic Scene Capture

Use the on-device fixture renderer to inspect every theme and semantic state without changing NVS, the active theme, inbox bindings, or host data:

```bash
tools/phase1_bringup/.venv/bin/python3 tools/capture_panel.py \
  0 artifacts/phase2/beacon-blocked.ppm \
  --theme beacon --scene blocked

tools/phase1_bringup/.venv/bin/python3 tools/capture_panel.py \
  3 artifacts/phase2/instrument-menu.ppm \
  --theme instrument --scene menu-led
```

`--theme` selects one of the four renderers. `--scene` selects a resting state, source fence, feedback state, sync screen, or menu row; use `tools/capture_panel.py --help` for the exact current choices. Capture menu scenes from panel `3`; capture tile scenes from panel `0`–`2`. The fixture uses long bounded title, discriminator, and time values so clipping and overlap failures remain visible.

## Pixel Interpretation

The capture is the sprite memory in RGB565 byte order. Decode each pixel as big-endian wire bytes:

```python
value = (raw[index * 2] << 8) | raw[index * 2 + 1]
r = ((value >> 11) & 0x1F) * 255 // 31
g = ((value >> 5) & 0x3F) * 255 // 63
b = (value & 0x1F) * 255 // 31
```

If the image has an implausible green or blue cast, check byte order before changing firmware colors. Validate the background first. The Phase 02.2 background is `#0B0F14`, encoded as RGB565 `0x0862`; a swapped decode commonly produces a false green-tinted result.

The shared firmware palette lives in `firmware/src/ui/theme_common.h`. Keep source comments and encoded values synchronized. Convert design RGB hex values to RGB565 with rounded channel quantization, then verify the resulting capture rather than trusting a hand-written constant.

## Compare Against the Design

Read the UI contract before judging geometry. Check the actual pixels against these fixed invariants:

- 128×128 panel with a 4 px safe inset.
- Signal Edge: rail at the left, title rows near y=5, discriminator near y=32, glyph centered, state row near y=110.
- Ledger: header and age near y=5, hairline near y=18, title rows at y=22/36, state row near y=74, footer dots near y=119.
- Beacon: center glyph/field around `(64,52)`, state word near y=73, title strip beginning around y=96 and opaque behind text.
- Instrument: bezel ticks at corners, ring center around `(64,54)`, state line near y=89, feedback meta line near y=100, title near y=112.
- Panel 4: `CODEX`, honest `UNAVAILABLE`, and `NO VALUES`; no fabricated usage or quota numbers in Phase 02.2.
- Every semantic state retains literal text or a structural non-color cue.

Use captures to distinguish these failure classes:

- **Palette error:** background or state hue differs uniformly; inspect RGB565 encoding first.
- **Geometry error:** edges, rings, rails, or glyph centers are consistently displaced; adjust source coordinates.
- **Banding error:** radial field forms a harsh bullseye; use more shallow RGB565 luminance bands, keep the brightest field below glyph luminance, and inspect again.
- **Bleed error:** field appears behind title or metadata; add an intentional opaque strip before text composition.
- **Clipping error:** text touches the safe inset or loses distinguishing characters; fix bounded ellipsis budgets, not panel scaling.
- **Truth error:** unavailable data appears numeric or stale content lacks a fence; fix state composition and source-status handling.

## Refinement Loop

Repeat this bounded loop for each rendering change:

1. Identify one visible mismatch from the captured pixels.
2. Locate the owning theme renderer; keep composition in the shared `LGFX_Sprite`.
3. Make the smallest geometry, palette, or primitive change.
4. Run `git diff --check` on changed source.
5. Rebuild with the supplied venv.
6. Stop the bridge, upload firmware, publish a controlled snapshot if needed, and recapture the affected panel.
7. Inspect the new PNG and compare against the previous capture.
8. Keep the change only when the pixel evidence improves the contract without regressing semantic cues or safe bounds.

Avoid optical screenshots for this comparison loop. Use them only after logical pixels satisfy the contract and physical appearance still needs validation.

## Safety and Cleanup

Keep capture frames bounded and diagnostic-only. Do not add credentials, transcripts, filesystem paths, or unbounded payloads to the device protocol. Do not leave the bridge and direct capture utility competing for `/dev/ttyACM0`. Restart the bridge only when host-driven live behavior is needed:

```bash
host/herdr_keypad/scripts/ensure-bridge.sh
```

Keep generated PPM/PNG/RGB565 artifacts out of commits unless the task explicitly requests visual fixtures. Commit source, utility, and skill changes only.

## Additional Resources

- `tools/capture_panel.py` — exact paired-device framebuffer capture utility.
- `firmware/src/app/agent_projection.cpp` — composition sprite and capture seam.
- `firmware/src/main.cpp` — bounded `CAPTURE:N` probe dispatch and USB stream.
- `firmware/src/ui/theme_common.h` — shared RGB565 palette and state vocabulary.
- `firmware/src/ui/theme_beacon.cpp` — Beacon field and radial geometry.
- `.planning/phases/02.2-firmware-themes-led-bars-and-device-selection-menu/02.2-UI-SPEC.md` — authoritative geometry and semantic contract.
- `.planning/research/DESIGN-PROPOSALS.html` — visual proposal source.
