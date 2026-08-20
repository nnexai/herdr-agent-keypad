---
phase: 03
slug: truthful-codex-capacity-and-device-menu
status: approved
shadcn_initialized: false
preset: none
created: 2026-08-20
reviewed_at: 2026-08-20T20:38:00+02:00
---

# Phase 03 — UI Design Contract

> Visual and interaction contract for the read-only Codex capacity tile and the encoder-operated device menu on the connected LILYGO T-Keyboard S3 Pro. This is an embedded-firmware contract, not a web UI. It extends the accepted Phase 02.2 theme, LED, focus, and compose-then-flush contracts.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — embedded C++ firmware using LovyanGFX primitives through the existing composition sprite |
| Preset | not applicable |
| Component library | none; existing `AgentProjection`, `ThemeRenderer`, `MenuController`, `SettingsStore`, `BoardAdapter`, and bounded protocol/session seams |
| Icon library | none; locally drawn geometric primitives only: bars, hatch, ticks, arcs, ring, cross, broken-link, question, check, and dash |
| Font | existing bitmap mono family; exactly four roles below, regular and semibold only; no runtime font, emoji, icon, remote asset, or Unicode-symbol dependency |

The shadcn gate does not apply: this is a four-panel embedded device. Do not add LVGL, a second display abstraction, raw panel chip-select access, a second key map, or remote assets. Every frame is composed in the existing reusable 128x128 RGB565 sprite and flushed through `BoardAdapter` one panel at a time. The 4px safe inset, bounded ASCII copy, literal state words, host-authoritative data, identity-bound direct focus, and no-color-only meaning remain binding.

### Responsibility boundary

The host owns Codex authentication, app-server interpretation, full-read/sparse-merge semantics, source timestamps, state classification, bounded reset text, normalized percentages, and redacted diagnostic values. Firmware receives only bounded device-scoped values and draws them. Firmware never receives or displays credentials, account identity, host paths, raw JSON-RPC errors, prompts, transcripts, or Codex app-server metadata such as `codexHome`.

The existing three agent panels and their generation-bound focus bindings remain untouched by the menu. `reportAgentKey()` stays ahead of menu polling. Keys 1–3 are direct focus paths whether the menu is closed, open, on a submenu, or showing HEALTH/ABOUT.

---

## Fixed Hardware and Rendering Constraints

- Every panel is exactly 128x128 pixels. Content text and semantic geometry stay inside the 4px safe inset (`x=4..123`, `y=4..123`). Existing Signal Edge's edge rail and Instrument's bezel ticks are intentional theme channels and may occupy the established edge pixels; no copy crosses them.
- Panel 4 is the dedicated read-only Codex/menu surface. It is never an agent tile and never becomes a second focus path.
- The three agent tiles keep their existing Phase 02.2 anatomy, colors, state vocabulary, and LED mapping. Opening the menu replaces only panel 4; it does not veil, redraw, or disable the three agent tiles.
- A complete staged snapshot is still composed and published as one generation. Codex freshness, Herdr freshness, link health, and a menu brightness change never mutate inbox order, target identity, or focus state.
- Ordinary refreshes may use the accepted sequential per-panel reveal, but each panel is always a complete old or new frame. SYNC remains the all-panel presentation for boot, session reset, and failure.
- No per-frame allocation is permitted. Truncate bounded strings before rendering; never shrink below the declared type size to fit text.

---

## Spacing Scale

Device coordinates use the retained Phase 1/02.2 4-point scale:

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Safe inset, bezel/rail boundary, hatch pitch, glyph-to-label gap |
| sm | 8px | Panel content inset, title-to-rule gap, row padding |
| md | 16px | Primary/secondary row separation, diagnostic line pitch |
| lg | 24px | Menu viewport row height, major panel-4 data separation |
| xl | 32px | Gauge group separation where a theme already uses it |
| 2xl | 48px | Host-side grouping only; no panel gap |
| 3xl | 64px | Host-side grouping only; no panel gap |

Exceptions: one-pixel rules, gauge strokes, hatch marks, arc strokes, and glyph lines are drawing primitives rather than spacing tokens. The existing Signal Edge edge rail, Beacon field/ring, and Instrument bezel are established theme geometry, not new spacing tokens. Brightness values use a 10 percentage-point domain (`10,20,...,100`), not a layout scale.

---

## Typography

Exactly four sizes and two weights are allowed, inherited from Phase 02.2:

| Role | Size | Weight | Line Height | Use in Phase 3 |
|------|------|--------|-------------|----------------|
| Body | 16px | regular (400) | 1.5 | Host-side evidence only; never dense panel copy |
| Label | 12px | semibold (600) | 1.25 | All panel-4 copy, including `CODEX`, `MENU`, `HEALTH`, `ABOUT`, labels, percentages, status words, menu rows, and diagnostic values |
| Heading | 20px | semibold (600) | 1.2 | Host/evidence headings only; never a panel-4 page title |
| Display | 24px | semibold (600) | 1.0 | Large `LIMIT`, percentage emphasis, ring/dial center value, and menu brightness preview |

Panel-4 titles (`CODEX`, `MENU`, `HEALTH`, and `ABOUT`) are always one measured 12px Label line. The exact title convention is a measured glyph-box top-left at `y=4`, with glyph bounds `y=4..15` inclusive; no title uses the old `y=5`, `y=6`, `y=7`, or `y=8` coordinate. Left themes use their stated x anchor and centered themes use center `x=64`. This convention applies to the Codex tile, menu root, value previews, HEALTH, and ABOUT.
The Label glyph-box metric is explicit and uniform: for baseline `b`, glyph bounds are `y=b-10..b+1` inclusive (12px high). Therefore baseline `y=114` always produces `y=104..115`; no panel copy may use a different ascent, descent, or line box. The required title-to-first-content gap is 4px (`y=16..19`) after the title glyph bounds `y=4..15`.

Panel copy is uppercase ASCII, bounded, and measured before drawing. Titles and diagnostic values use the existing 6px mono cell width at the label floor; panel-4 strings are capped at 18 cells. `...` is the only truncation marker. Geometric primitives carry state meaning alongside a literal word; color, size, and weight never carry meaning alone.

---

## Color

The existing Tokyo-Night-equivalent palette is retained across all four languages:

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#0B0F14` | Cleared panel background, calm data field, menu background |
| Secondary (30%) | `#1F2937` | Neutral hatch/veil, inactive rule, preview/revert field, unavailable gauge interior |
| Accent (10%) | `#22D3EE` | Current usage bars/arcs, menu cursor, active brightness preview, live pending feedback, and encoder-open cue |
| Destructive | `#EF4444` | `STALE`, `UNAVAILABLE`, `AUTH REQUIRED`, `CODEX OFFLINE`, `HOST OFFLINE`, failed health, and limit alert channel |

Existing semantic colors remain available for state-equivalent geometry: blocked rose `#F7768E`, unseen blue `#7DCFFF`, working amber `#E0AF68`, idle green `#9ECE6A`, settled/neutral `#565F89`, and empty edge `#263648`.

Accent reserved for: current Codex gauge fill/arc, current menu cursor, confirmed brightness preview, the encoder menu-open indication, and the existing PENDING focus vehicle. It is not a general title color or decoration. `LIMIT` uses the theme's established dominant warning geometry in blocked rose/destructive red; it is never represented by an `OK` cue. Missing/null reached-limit data produces no positive cue.

---

## Codex Data Contract and State Precedence

The panel consumes one normalized Codex view containing `primary`, `secondary`, `reset_text`, `observation_age`, `source_state`, and `reached_limit`. `primary` and `secondary` are either supplied integer percentages or absent. Absent/null is always `N/A`, never `0%`. The host stamps observation age after a successful full `account/rateLimits/read` or a valid sparse merge into a known full snapshot.

- Full reads are attempted every 5 minutes. An observation becomes `STALE` after 15 minutes without a valid full read or valid sparse merge.
- A sparse `account/rateLimits/updated` event may refresh age only after presence-aware merge into a known full snapshot. It cannot establish the first current state or clear omitted values.
- The reset display uses the nearest supplied future reset across the primary and secondary windows. The label identifies its source window: `RESET 5H 01:20` or `RESET WEEK 2D`. With no supplied future reset it is exactly `RESET N/A`. Reset time is not observation age.
- `reached_limit` is true only when the normalized response supplies a non-null reached-limit classification. A missing/null field is unknown and renders no `OK`, `CLEAR`, or other positive claim. When true, render `LIMIT` through the theme's dominant alert channel.
- State precedence is: `HOST OFFLINE` > `CODEX OFFLINE` > `AUTH REQUIRED` > `STALE` > `CURRENT`/`UNAVAILABLE`. The limit cue is layered on current or cached data, but never hides a host/offline/auth/stale label.

| Source state | Panel data | Required visual treatment | Key/menu behavior |
|---------------|-------------|---------------------------|-------------------|
| `CURRENT` | Show each supplied percentage; each absent window is `N/A`; show reset and age | Normal theme geometry; current bars/arcs use accent; footer/status says `CURRENT` | Agent keys remain direct; encoder menu works |
| `STALE` | Retain the last complete values and reset fields; show observation age | Desaturate/dim values, add hatch/veil, and make `STALE` unmistakable; cached values never look current | Agent keys are governed by Herdr freshness and remain independently fenced if stale; menu remains available |
| `AUTH REQUIRED` | Clear cached capacity immediately; all usage/reset fields are `N/A` | Cross/auth veil in destructive red; one measured 12px `AUTH REQUIRED` line at the shared state baseline `y=114`, never wrapped or split | No login prompt or URL; menu HEALTH reports Codex `AUTH REQUIRED` |
| `UNAVAILABLE` | No complete observation, or all requested fields absent/null; show `N/A` fields | Hatched/empty gauges or dial, settled neutral geometry, red `UNAVAILABLE` word | No Codex value claim; menu remains available |
| `CODEX OFFLINE` | Preserve cached values when a complete observation exists; otherwise `N/A` | Broken-link geometry and destructive `CODEX OFFLINE` veil; show age when cached | Do not infer auth failure from timeout; menu HEALTH remains usable |
| `HOST OFFLINE` | Preserve cached values when available; otherwise `N/A` | Full host-offline fence distinct from Codex-offline; exact `HOST OFFLINE` label and age when cached | No queued/replayed writes or focus actions; local brightness remains usable |

For stale/offline cached data, the last values remain readable but are never shown without the state veil and age. For auth-required, no cached values remain on the panel. The three agent panels do not inherit Codex source state; SYNC-03 source health is independent.

### Limit cue

When `reached_limit=true`, `LIMIT` is the dominant theme-equivalent alert while preserving the source state word and age. Signal Edge uses a full-width alert footer; Ledger inverts the active data row and prints `LIMIT`; Beacon changes the outer dial/halo to warning red and prints `LIMIT` at center; Instrument turns all bezel ticks and the 75% warning mark red and prints `LIMIT` in the status lane. If the source is stale/offline, the state veil remains dominant and a compact `LIMIT` marker stays in the header; never replace `STALE`, `CODEX OFFLINE`, or `HOST OFFLINE` with `LIMIT`.

---

## Panel 4 — Shared Data Bands

Common content bounds are:

| Band | Y range | Content |
|------|---------|---------|
| Header | 4..15 | `CODEX` and, where needed, a compact `LIMIT` marker |
| Title-to-content gap | 16..19 | Clear pixels after title glyph bounds `y=4..15` |
| Primary | 20..39 | label `5H`, integer percentage/N/A, theme gauge |
| Secondary | 40..59 | label `WEEK`, integer percentage/N/A, theme gauge |
| Reset | 60..75 | `RESET ...`, nearest future window or `RESET N/A` |
| Observation | 76..91 | `AGE ...`, always visible even for cached values |
| State | 92..123 | source state word and its theme fence/alert |

With the uniform metric above, the shared line baselines are primary `y=30` (`20..31`), secondary `y=50` (`40..51`), reset `y=70` (`60..71`), observation `y=86` (`76..87`), and state `y=114` (`104..115`). Every glyph box is wholly inside its declared band, and the state line remains inside the 4px safe inset.

The host supplies `observation_age` in bounded uppercase units: `AGE N/A`, `AGE 0M`, `AGE 14M`, `AGE 1H`, or `AGE 2D`. Firmware does not silently turn an absent timestamp into `AGE 0M`. The reset string is bounded to fit the theme's label floor and is not recomputed from observation age.

### Exact theme layouts

#### A — Signal Edge

- Keep the existing left edge rail at `x=0..8`; it is a panel channel, not text. Header `CODEX` uses the shared title contract at top-left `(16,4)`, with glyph bounds `y=4..15`.
- Primary label/value baseline is `y=30` (glyph bounds `y=20..31`); gauge rectangle is `x=16,y=32,w=108,h=8` inside the primary band. Secondary baseline is `y=50` (glyph bounds `y=40..51`); gauge is `x=16,y=52,w=108,h=8` inside the secondary band. The supplied percentage fills the gauge left-to-right; `N/A` leaves the track hatched.
- Draw `RESET ...` at `(16,70)` (glyph bounds `y=60..71`), `AGE ...` at `(16,86)` (glyph bounds `y=76..87`), and every source state, including one-line `AUTH REQUIRED`, at `(16,114)` (glyph bounds `y=104..115`). Right-align primary/secondary values at `x=120`.
- Current calm state uses the accent bars. Stale/offline/unavailable hatches use settled neutral plus a red bottom veil. Auth-required and Codex/host-offline use the existing full-width bottom band; `LIMIT` uses the same band with warning color and a large alert glyph at the left.
- `MENU`, `HEALTH`, and `ABOUT` use the same 12px Label top-left title convention at `(16,4)`, with glyph bounds `y=4..15`; their detail copy remains left-aligned within the 8px rail.

#### B — Ledger

- Keep the existing header title anchor at `(6,4)`, with glyph bounds `y=4..15`, and divider `y=18`.
- Primary row label/value baseline is `y=30` (glyph bounds `y=20..31`); underline at `y=38`. Secondary row uses `y=50` (glyph bounds `y=40..51`); underline at `y=58`. Labels start at `x=6`; values are right-aligned to `x=120`.
- Reset baseline is `y=70` (glyph bounds `y=60..71`), observation baseline `y=86` (glyph bounds `y=76..87`), and every source state, including one-line `AUTH REQUIRED`, uses baseline `y=114` (glyph bounds `y=104..115`). The `RESET` row is a ledger entry with a hairline below it when space permits.
- Percentages are right-aligned ledger values with no invented decimal precision. `N/A` is the same width-budgeted value treatment as a supplied percentage.
- `LIMIT` inverts the active primary/secondary ledger row in blocked rose and prints `LIMIT` in the state lane. Stale/offline/auth fences use the existing header-band takeover without erasing the last readable numbers.
- `MENU`, `HEALTH`, and `ABOUT` use the same 12px Label top-left title convention at `(6,4)`, with glyph bounds `y=4..15`, with Ledger's left cursor, ruled rows, and compact right-column values.

#### C — Beacon

- Keep the Beacon radial language. The centered `CODEX` title uses the shared 12px Label top-left convention at `y=4`, centered on `x=64`, with glyph bounds `y=4..15`. The usage field is a stepped dual-ring gauge centered at `(64,40)`: outer ring radius 19 is primary (`5H`), inner ring radius 12 is secondary (`WEEK`), so the complete field stays within `y=20..59` (the primary and secondary bands). A supplied value draws a proportional accent arc; missing values draw a neutral hatched arc.
- Put `5H NN%` centered at baseline `y=30` (glyph bounds `y=20..31`) and `WEEK NN%` centered at baseline `y=50` (glyph bounds `y=40..51`). The labels remain readable over the stepped field; values are text-authoritative.
- Draw `RESET ...` centered at `y=70` (glyph bounds `y=60..71`), `AGE ...` centered at `y=86` (glyph bounds `y=76..87`), and every source state, including one-line `AUTH REQUIRED`, centered at baseline `y=114` (glyph bounds `y=104..115`).
- Current arcs use accent. Stale/offline dims the field and adds a broken/hatched outer ring; unavailable uses a fully hatched dual ring; auth-required uses a crossed ring and destructive one-line `AUTH REQUIRED`; host-offline adds the red top hairline already used by Beacon fences.
- `LIMIT` turns the outer ring and center alert treatment to warning red without changing the two percentage texts. `MENU`, `HEALTH`, and `ABOUT` use the same centered 12px Label title convention (top-left y=`4`, center x=`64`, glyph bounds `y=4..15`). Menu rows remain centered Beacon words with the cursor at the safe left inset.

#### D — Instrument

- Keep four bezel ticks at the established corners. Header `CODEX` uses the centered shared 12px Label title convention at top-left `y=4`, center `x=64`, with glyph bounds `y=4..15`.
- Primary label/value baseline is `y=30` (glyph bounds `y=20..31`); gauge track is `x=8,y=32,w=112,h=8` inside the primary band. Secondary baseline is `y=50` (glyph bounds `y=40..51`); gauge track is `x=8,y=52,w=112,h=8` inside the secondary band. Values right-align to `x=120`; retain the existing 75% warning mark at the primary and secondary tracks.
- Reset baseline is `y=70` (glyph bounds `y=60..71`), observation baseline is `y=86` (glyph bounds `y=76..87`), and every source state, including one-line `AUTH REQUIRED`, uses centered baseline `y=114` (glyph bounds `y=104..115`). `LIMIT` uses the 75% mark plus all bezel ticks in warning red and a centered status word.
- `MENU`, `HEALTH`, and `ABOUT` use the same centered 12px Label title convention (top-left y=`4`, center x=`64`, glyph bounds `y=4..15`) with the bezel and centered page vocabulary from the existing Instrument renderer.

---

## Menu Root and Interaction Contract

### Root list

Encoder click opens and closes the secondary menu. The root is one flat, bounded six-row list in this exact order:

1. `THEME`
2. `LEDS`
3. `BRIGHTNESS`
4. `HEALTH`
5. `ABOUT`
6. `CLOSE`

Only three rows are visible at once. Preserve the 3 rows × 24px viewport in `y=20..91`, with row bands `20..43`, `44..67`, and `68..91`; row baselines are `y=30,54,78`, producing glyph bounds `y=20..31`, `44..55`, and `68..79`. The page title glyphs occupy `y=4..15`, leaving the required 4px clear title-to-first-row gap `y=16..19`. The interaction footer occupies `y=92..123`, retaining the required lower hint strip `y=104..123`; no row glyph overlaps it. Cursor is clamped, never wrapped: `viewport_start = min(max(cursor - 1, 0), 3)`. Thus cursor 0 shows rows 1–3, cursor 1 shows rows 1–3, cursor 2 shows rows 1–3, cursor 3 shows rows 2–4, cursor 4 shows rows 3–5, and cursor 5 shows rows 4–6. A selected row has a geometric cursor and accent treatment; color alone is never the selection cue.

Each row is one measured line at the label floor. Values use these bounded forms: `SIGNAL EDGE`, `LEDGER`, `BEACON`, `INSTRUMENT`; `RAIL ECHO`, `EXCEPTION`, `FIELD EXT`, `METER+LAMPS`; brightness `10%`–`100%`. With the 6px mono cell width, every right-column root value is right-aligned within `x=55..120` (maximum width 11 cells); the root shows current values to the right for THEME, LEDS, and BRIGHTNESS, while HEALTH, ABOUT, and CLOSE have no fabricated value.

Theme-specific root geometry is exact:

| Theme | Header | Visible rows | Cursor/value treatment | Hint |
|-------|--------|--------------|------------------------|-------|
| Signal Edge | rail `x=0..8`, `MENU` Label title top-left `(16,4)`, glyph bounds `y=4..15` | baselines `30,54,78` with glyph bounds `20..31`, `44..55`, `68..79` | selected row fill `x=12..123`; cursor `>` glyph bounds `x=16..20`; label column `x=24..53`; longest value (`SIGNAL EDGE`) bounds `x=54..119`, right edge `x=120`; thus `THEME SIGNAL EDGE` has no cursor/value overlap | `TURN:SEL` at baseline `y=102` (glyph bounds `92..103`), `CLICK:OPEN` at baseline `y=114` (glyph bounds `104..115`) |
| Ledger | `MENU` Label title top-left `(6,4)`, glyph bounds `y=4..15`, rule `y=18` | baselines `30,54,78` with glyph bounds `20..31`, `44..55`, `68..79` | cursor `>` glyph bounds `x=6..10`; `THEME` bounds `x=14..43`; clear `x=44..54`; right-aligned longest value (`SIGNAL EDGE`) bounds `x=55..120`; ruled rows; every root value is right-aligned to `x=120` | `TURN:SEL CLICK:OPEN` at baseline `y=112` (glyph bounds `102..113`) |
| Beacon | centered `MENU` Label title top-left `y=4`, center `x=64`, glyph bounds `y=4..15` | baselines `30,54,78` with glyph bounds `20..31`, `44..55`, `68..79` | cursor glyph bounds `x=4..8`; each row is one centered measured line; longest `THEME SIGNAL EDGE` bounds `x=13..114` (102px, center `x=63.5`/`64`), leaving `x=9..12` as a 4px gap from cursor | centered `TURN:SEL CLICK:OPEN` at baseline `y=112` (glyph bounds `102..113`) |
| Instrument | bezel ticks, centered `MENU` title top-left `y=4`, center `x=64`, glyph bounds `y=4..15` | baselines `30,54,78` with glyph bounds `20..31`, `44..55`, `68..79` | cursor `>` glyph bounds `x=16..20`; label column `x=24..53` and longest value (`SIGNAL EDGE`) bounds `x=54..119`, right edge `x=120`; `THEME SIGNAL EDGE` is therefore non-overlapping | centered `TURN:SEL CLICK:OPEN` at baseline `y=112` (glyph bounds `102..113`) |

Rotation changes only the clamped cursor in root mode. Click on THEME or LEDS enters value-cycle mode; click on BRIGHTNESS enters brightness preview; click on HEALTH or ABOUT enters its read-only page; click on CLOSE closes the menu. There is no long press and no double click.

### Theme and LED value preview

- Value-cycle title is the selected label (`THEME` or `LEDS`) as a measured 12px Label line using the shared top-left `y=4` convention and glyph bounds `y=4..15`; the required 4px clear gap is `y=16..19`, and the current candidate is the first content line at baseline `y=30` with Label glyph bounds `y=20..31` inside content band `y=20..43`. `TURN:CHANGE` and `CLICK:SAVE` use the footer band `y=92..123`.
- Rotation cycles exactly four values and clamps at the first/last value; no wrap. The candidate theme changes the panel-4 menu language immediately, but agent tiles and their committed bindings do not preview a theme change. LED candidate drives only its bounded live LED preview.
- Click confirms the candidate, persists it through the existing schema-versioned `SettingsStore`, and returns to the root with the cursor on the same row. Closing, selecting CLOSE, or timing out before confirmation restores the stored value and LED grammar.
- Invalid/missing stored theme or LED values fall back in memory to Signal Edge + Rail Echo and are not written back during boot. Existing confirmed settings are read unchanged; Phase 3 writes schema v2 only after explicit confirmation of a Phase 3 setting.
Missing or invalid brightness reads as `80%` in memory. Boot never writes a migration record; only an explicit confirmed brightness setting may write schema v2.

### Brightness preview, confirmation, and revert

- Entering BRIGHTNESS starts at the stored brightness. Valid values are exactly `10%` through `100%` in 10% steps; 0% is not representable.
- Rotation changes the candidate by one step, clamps at 10%/100%, and applies it live through `BoardAdapter::setBrightness()` to all panels. The preview never changes snapshot generation, inbox order, focus identity, LEDs' semantic policy, or host state.
- The preview page shows `BRIGHTNESS` as a measured 12px Label title using the shared top-left `y=4` convention and glyph bounds `y=4..15`; the large `NN%` Display value occupies the measured center band `y=24..47`, the bounded 10-step track occupies `y=52..59`, and `TURN:CHANGE` / `CLICK:SAVE` use the footer band `y=94..123`. The title-to-content clear gap remains `y=16..23`, and encoder click confirms and persists the brightness on-device via `SettingsStore`; no host round trip is required.
- Closing the menu, selecting CLOSE, or the inactivity timeout reverts an unconfirmed candidate to the stored value through `BoardAdapter`. No unconfirmed value is written. The device remains visibly powered at the minimum 10%.
- Brightness remains adjustable while HOST OFFLINE. A brightness action is local and is never queued or replayed as a protocol action.

### HEALTH page

HEALTH is read-only. Its `HEALTH` title is the shared measured 12px Label line at the theme's title anchor (`y=4` top-left, or centered `x=64` for Beacon/Instrument), with glyph bounds `y=4..15`. Rotation does not change content but counts as encoder activity for timeout; click returns to root without changing cursor. Use six fixed 16px rows at baselines `y=30,46,62,78,94,110`, with glyph bounds `y=20..31`, `36..47`, `52..63`, `68..79`, `84..95`, and `100..111`; the first row therefore clears the title by the required 4px gap `y=16..19`. The data bands are `20..35`, `36..51`, `52..67`, `68..83`, `84..99`, and `100..111`; reserve `112..123` for the footer.

| Row | Label | Value |
|-----|-------|-------|
| 1 | `LINK` | `OK` or `OFFLINE` |
| 2 | `HERDR` | `CURRENT`, `STALE`, `UNAVAILABLE`, or `OFFLINE` |
| 3 | `CODEX` | `CURRENT`, `STALE`, `UNAVAILABLE`, `AUTH REQUIRED`, or `OFFLINE` |
| 4 | `SYNC AGE` | bounded age or `N/A` |
| 5 | `CODEX AGE` | bounded age or `N/A` |
| 6 | `ERR` | `NONE` or bounded redacted code `E-####` |

Values are right-aligned to `x=120` (Beacon centers row pairs; Ledger uses its ruled value column). `ERR` is one allowlisted code only; raw errors are never rendered. HEALTH never displays account identity, auth mode, credentials, paths, prompts, transcripts, or a Codex request ID.
HEALTH renders `CLICK:BACK` at baseline `y=122` (glyph bounds `y=112..123`) in the theme's footer treatment; it does not create a seventh data row.

### ABOUT page

ABOUT is read-only and click returns to root. Its `ABOUT` title is the shared measured 12px Label line at the theme's title anchor (`y=4` top-left, or centered `x=64` for Beacon/Instrument), with glyph bounds `y=4..15`. It shows exactly these six bounded lines, with versions and suffixes supplied by the host/device projection:

| Row | Label | Value |
|-----|-------|-------|
| 1 | `FW` | installed firmware version |
| 2 | `PROTO` | installed protocol version |
| 3 | `BRIDGE` | bridge version |
| 4 | `DEV` | six-character device suffix |
| 5 | `SES` | six-character session suffix |
| 6 | `REV` | six-character snapshot revision suffix |

Rows use baselines `y=30,46,62,78,94,110`, with glyph bounds `y=20..31`, `36..47`, `52..63`, `68..79`, `84..95`, and `100..111`; the first row clears the title by the required 4px gap `y=16..19`. The six data bands are `20..35`, `36..51`, `52..67`, `68..83`, `84..99`, and `100..111`; `CLICK:BACK` is drawn at baseline `y=122` (glyph bounds `y=112..123`). Values are bounded to the available right column and tail-ellipsized. Versions are short semantic versions or `N/A` when absent; suffixes are uppercase hex only. ABOUT has no account, host path, credential, transcript, prompt, raw diagnostic, or arbitrary identifier.

### Menu timeout and live agent keys

- Opening the menu starts a 30-second inactivity deadline. Any encoder rotation or click resets it. Health/Codex updates, animation ticks, and direct agent-key presses do not reset it.
- At 30 seconds without encoder activity, discard any unconfirmed theme/LED/brightness preview, restore stored brightness through `BoardAdapter`, close the menu, and return panel 4 to the committed Codex composition.
- A click on CLOSE or a normal close click has the same discard/revert behavior for unconfirmed candidates. A confirmed setting remains confirmed.
- Keys 1–3 are dispatched before menu polling and remain immediate direct focus actions while the menu is open. They never move the menu cursor, enter a menu row, or reset the menu timeout. Their PENDING/FOCUSED/REJECTED/STALE/VANISHED/OFFLINE/UNCERTAIN/FAILED feedback remains on the pressed agent tile and its mapped LED zone.
- Encoder menu-open indication is the active grammar's existing L13 cue. Health updates may repaint menu values in place but never move the cursor, alter the viewport, or reset the timer.

---

## Motion and Flush Contract

| Event | Visual behavior | Bound |
|-------|-----------------|-------|
| Panel-4 data refresh | Compose a complete new panel-4 frame, then perform the accepted panel reveal; never mutate a live half-frame | One complete old/new image per flush; no black flash |
| Current → STALE/OFFLINE/AUTH | Fence cut with the new state and age | Semantic fence preempts ambient motion |
| Limit onset | Immediate dominant theme alert | No pulse or animation may obscure `LIMIT` |
| Menu open/close | Complete panel-4 replacement between Codex and menu frames | Agent panels remain untouched |
| Brightness rotation | Live board brightness change and complete preview repaint | 10% steps; no persistence until click |
| Theme/LED confirmation | Complete themed repaint after confirmation | No mixed-theme cluster; bindings unchanged |
| Ambient theme animation | Existing Phase 02.2 scheduler only | Complete frames, ≤30% loop wall time, degrade half cadence then static; never overtake state/fence/feedback |
| Menu timeout | Revert candidate brightness/settings, close, repaint Codex | Exactly 30 seconds without encoder activity |

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA | `CONFIRM BRIGHTNESS` (menu/evidence wording; physical action is encoder click) |
| Empty state heading | `UNAVAILABLE` |
| Empty state body | `No complete Codex observation. Wait for a fresh host read.` (host/evidence wording; panel uses `N/A` fields and `UNAVAILABLE`) |
| Error state | `CODEX OFFLINE — wait for host recovery; cached values remain fenced.` (panel uses exact bounded `CODEX OFFLINE` and age) |
| Destructive confirmation | None. `LIMIT` is a read-only provider state, not a device action. |

### Required panel vocabulary

`CODEX`, `5H`, `WEEK`, `NN%`, `N/A`, `RESET`, `AGE`, `CURRENT`, `STALE`, `UNAVAILABLE`, `AUTH REQUIRED`, `CODEX OFFLINE`, `HOST OFFLINE`, `LIMIT`, `MENU`, `THEME`, `LEDS`, `BRIGHTNESS`, `HEALTH`, `ABOUT`, `CLOSE`, `TURN:SEL`, `TURN:CHANGE`, `CLICK:OPEN`, `CLICK:BACK`, and `CLICK:SAVE` are the bounded Phase 3 additions. Existing Phase 02.2 agent/focus words remain unchanged.

Use `CURRENT` only after a valid current observation. Never use `OK` on the Codex tile, never render a missing percentage as `0%`, never show `RESET` without a supplied future reset, and never imply that a transport/link success proves Codex authentication or quota freshness. `AUTH REQUIRED` is an observed auth classification only; timeouts and process failures are `CODEX OFFLINE`, not auth failures.

---

## UI Considerations

Applicable state considerations resolved: 10 covered, 1 backstop, 0 unresolved.

| Category | Element(s) | Status | Resolution / Reason |
|----------|------------|--------|---------------------|
| empty | no complete Codex observation; absent primary/secondary/reset/reached fields | ✅ covered | Render `UNAVAILABLE`, `N/A`, `RESET N/A`, and `AGE N/A`; never fabricate zero or `OK`. |
| loading | first full-read wait, panel refresh, menu opening | ✅ covered | Panel 4 remains explicit `UNAVAILABLE` until a full observation; refresh/menu use complete compose-then-flush frames. |
| error | stale, auth-required, Codex-offline, host-offline, reached-limit | ✅ covered | Each state has a distinct literal word, geometric fence, and independent source semantics; limit never masks offline/auth/stale truth. |
| populated | current primary/secondary windows | ✅ covered | Fixed `5H` and `WEEK` rows show supplied integer percentages, nearest reset, and observation age. |
| partial | one window/reset/reached field missing or null | ✅ covered | Each absent field independently renders `N/A`; nearest reset is `RESET N/A` when neither future reset exists; no positive reached cue for unknown. |
| overflow | reset text, age, version, diagnostic code, menu value | ✅ covered | Host/device strings use fixed bounded forms; values are measured and tail-ellipsized within the 4px inset. |
| zero-one-many | zero, one, or two supplied usage windows; six root rows | ✅ covered | Both fixed rows always remain present; root cursor clamps over all six rows with a three-row viewport. |
| long-text | `AUTH REQUIRED`, `CODEX OFFLINE`, `HOST OFFLINE`, `RESET WEEK ...`, version values | 🧪 backstop | Exact-device smoke at lowest 10% brightness verifies legibility, no clipping/bezel collision, and persistent source-state words across all four themes. |
| interaction | encoder root/submenus, direct keys while menu open | ✅ covered | Click/rotation grammar is bounded; 30-second timeout discards previews; keys 1–3 bypass menu and focus their exact displayed agents. |
| persistence | brightness and existing theme/LED settings | ✅ covered | Confirm-only writes; brightness reverts on close/timeout; invalid legacy settings fall back in memory without boot write-back. |

---

## Explicit Non-Goals

- Any Codex provider call, OAuth flow, token handling, or account identity on firmware.
- Any additional provider, multi-bucket browsing UI, credits balance, spend-control dashboard, reset-credit detail list, or richer diagnostic counter page.
- Any arbitrary host command, app-server proxy, transcript/prompt display, host path, raw error, login URL, credential, or queue/replay behavior.
- Any change to Herdr ordering, snapshot revision, opaque focus identity, direct-key semantics, or the Phase 02.2 theme/LED grammar vocabulary.
- Display-off brightness, a 0% brightness state, long press, double click, wraparound menu navigation, modal agent keys, or encoder-required agent selection.
- A second renderer, second settings store, second key/LED map, LVGL, remote assets, unbudgeted animation, or black-flash transitions.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not applicable — embedded firmware/host bridge; no React stack |
| Third-party UI registries | none permitted | not applicable; no registry code, remote assets, fonts, or icons may enter this phase |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved
