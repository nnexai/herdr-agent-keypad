---
phase: 2
slug: authoritative-agent-projection-and-exact-focus
status: draft
shadcn_initialized: false
preset: none
created: 2026-08-17
---

# Phase 2 — UI Design Contract

> Visual and interaction contract for the real three-agent projection and exact-focus path on the connected LILYGO T-Keyboard S3 Pro. The fourth physical panel is reserved for Phase 3 and is not a Phase 2 surface.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — embedded C++ firmware and host-side Python bridge |
| Preset | not applicable |
| Component library | none; use the existing `BoardAdapter`, `ProtocolSession`, and bounded renderer seam |
| Icon library | none; use locally drawn geometric primitives and short ASCII labels |
| Font | the locally bundled legible bitmap sans family from Phase 1, regular and semibold only; no runtime font, emoji, icon, or network asset loading |

The shadcn gate does not apply: this is not React, Next.js, or Vite. The Phase 1 visual language remains authoritative: dark bounded panels, a 4px safe inset, literal state labels, short ASCII copy, no decorative animation, and all four panels drawn sequentially through `BoardAdapter::displayAt()`/the official board abstraction. The product renderer must not introduce a second display abstraction, direct panel chip-select access, a second key map, or a second transport.

### Evidence basis

- `.planning/phases/01-physical-keypad-and-proven-transport/01-UI-SPEC.md` fixes the 128×128 panel, 4px inset, typography roles, dark surface language, literal cues, and no-animation rule.
- `firmware/src/ui/bringup_renderer.h` fixes `kSafeInset = 4`, `kPanelCount = 4`, clear-before-redraw behavior, bounded centered text, and geometric cues.
- `firmware/src/board/board_adapter.h` is the only firmware-facing hardware boundary; panels are accessed one at a time through `displayAt()` and input through the mapped key API.
- `firmware/src/board/physical_map.h` fixes four logical displays and the verified physical mapping. Phase 2 uses only the first three agent positions; the fourth panel/key remains unassigned.
- Installed `herdr-agent-inbox` revision `de409f683262` defines rank `0..5`, the title/flag language, and the state order. Its TUI maps blocked to red/`!`, finished-unseen to teal/blue/`●`, working to yellow/`▸`, idle to green/`○`, settled to dim/`⚑`, and unknown to a neutral cue/`?`.
- Active Herdr configuration is `tokyo-night`; the installed TUI palette supplies the semantic state colors used below (`red #F7768E`, `yellow #E0AF68`, `green #9ECE6A`, `teal #7DCFFF`, `overlay0 #565F89`, `surface0 #24283B`, accent `#7AA2F7`).
- `.planning/phases/02-authoritative-agent-projection-and-exact-focus/02-CONTEXT.md` and `02-RESEARCH.md` lock installed inbox order, identity-bound focus, stale rejection, and atomic host epoch/snapshot revision behavior.

### Responsibility boundary

The host owns Herdr credentials, public-socket reads, installed-inbox ordering, identity validation, host epoch, and monotonic complete-snapshot revision. Firmware receives only bounded normalized display data and an opaque binding needed for the typed focus request. Firmware owns pixels, the fixed three physical positions, and visible action feedback. The display never exposes raw prompts, transcripts, credentials, raw cwd/repository paths, Herdr method names, plugin control commands, or Codex data.

---

## Hardware and Panel Layout

### Fixed physical seam

- Logical agent positions are fixed positions **1–3**, mapped by the verified `PhysicalMap`/`BoardAdapter` to the first three display/key pairs. Do not derive a new slot map in the renderer.
- Physical panel/key 4 is neutral and untouched by Phase 2 agent projection or focus. It must not be used as a fourth agent, overflow list, menu, status page, or temporary error panel.
- Each display is exactly 128×128 pixels. Every draw stays inside the 4px safe inset, leaving a 120×120 content box. No title, border, glyph, veil, or feedback label may touch the bezel.
- The renderer clears and draws through the existing adapter, one panel at a time. It must not address raw GPIO, panel chip-selects, or a second LovyanGFX/LVGL surface.

### Occupied tile geometry

Each current occupied tile uses the following stable hierarchy. Coordinates are design bands inside the safe inset, not permission to draw outside it:

| Band | Bounds | Content |
|------|--------|---------|
| State rail | x=4..123, y=4..7 | 4px semantic-color top rail; no color-only meaning because the same state has a glyph and word |
| Identity | x=8..119, y=10..42 | One-line title at the heading role, then one-line workspace/repository discriminator at the label role |
| State mark | x=8..119, y=45..82 | One centered non-color glyph, with the literal state word beneath or beside it |
| Focus feedback | x=8..119, y=96..119 | One bounded action/result label; blank only in the ordinary current state |

The title is the short authoritative session title. The second line is a compact discriminator from an authoritative workspace label or repository basename. Render both as single lines with measured width; truncate the middle or tail with ASCII `...` while preserving a distinguishing prefix/suffix. Never render a raw cwd, home path, transcript excerpt, or guessed label. Two identical titles must remain distinguishable whenever the normalized discriminator is available; if it is unavailable, show `NO WORKSPACE` rather than inventing one.

The title/discriminator are presentation fields only. They never identify a focus target. Focus identity remains the opaque pane/terminal/session binding paired with the hidden host epoch and snapshot revision.

### Empty and synchronization geometry

- Empty positions remain in their physical locations. They never collapse, shift later entries left, or retain the previous occupant's pixels.
- An empty tile uses the same border and inset, a centered outlined square/dash glyph, `EMPTY` at the state mark, and `NO AGENT` in the identity band. It is visibly intentional, not a blank screen.
- While a complete snapshot is staged, all three agent panels show the static `SYNC` label and a neutral double-line/buffer glyph after old content is cleared. Keys 1–3 are disabled during this bounded redraw. The previous generation is not actionable during the transition.
- The three staged records and three bindings become visible/actionable only at one commit point after all three panels have been rendered. The committed pixels, slot bindings, host epoch, and snapshot revision are one logical generation. Panel 4 is not touched.

---

## Spacing Scale

The Phase 1 4-point scale is retained. Device coordinates use the same values as spacing tokens wherever a token is applicable.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Safe inset, state rail, glyph-to-label gap, veil edge |
| sm | 8px | Panel content inset, identity start, feedback padding |
| md | 16px | Separation between identity and state mark; host-side status groups |
| lg | 24px | Separation between state mark and feedback; host diagnostic grouping |
| xl | 32px | Major host grouping only; not a device gap |
| 2xl | 48px | Host section break only |
| 3xl | 64px | Host page-level break only |

Exceptions: none. One-pixel primitives are allowed for glyph strokes, dividers, hatch marks, and connector lines, but are not spacing tokens. A status rail is 4px because it is a layout-bearing state boundary, matching Phase 1.

---

## Typography

Exactly four sizes and two weights are allowed, inherited from Phase 1:

| Role | Size | Weight | Line Height | Phase 2 use |
|------|------|--------|-------------|-------------|
| Body | 16px | regular (400) | 1.5 | Host bridge diagnostics and evidence, not dense device copy |
| Label | 12px | semibold (600) | 1.25 | Workspace/repository discriminator, state words, `EMPTY`, `STALE`, and focus result labels |
| Heading | 20px | semibold (600) | 1.2 | Occupied tile title; measured one-line truncation is mandatory |
| Display | 24px | semibold (600) | 1.0 | Centered state glyph or focus-result glyph |

Device copy is uppercase ASCII and short. Use geometric drawing for filled circle, open circle, triangle, flag, broken-link, slash, check, cross, and question cues; do not depend on Unicode emoji or a missing-font symbol. A state must always have a literal word as well as its glyph. Font size, weight, and color alone must never carry meaning.

---

## Color

### Surface contract

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#0B0F14` | All panel backgrounds and cleared pixels |
| Secondary (30%) | `#1F2937` | Empty/sync tile fill, neutral veil, inactive border/focus feedback field |
| Accent (10%) | `#22D3EE` | Pending focus rail/glyph, snapshot `SYNC` rail, and the single currently active feedback cue only |
| Destructive | `#EF4444` | Rejected/failed result, stale/offline veil edge, incompatible source, and no other content |

Accent reserved for: `PENDING`, `SYNC`, and the active focus feedback cue. It is not a general link color, a title color, a decorative border, or a way to mark every occupied tile.

### Installed Herdr semantic state mapping

The active installed Herdr theme is Tokyo Night. Use these fixed semantic colors for state rail/glyph accents, while retaining the literal word and geometric cue:

| Installed rank/token | Display state | Glyph | Color | Literal label |
|----------------------|---------------|-------|-------|---------------|
| `0` | blocked | `!` in a filled diamond/alert primitive | `#F7768E` (Herdr red) | `BLOCKED` |
| `1` | finished/unseen or manual unread | filled circle | `#7DCFFF` (Herdr teal/blue family) | `UNSEEN` |
| `2` | working | right-pointing triangle | `#E0AF68` (Herdr yellow) | `WORKING` |
| `3` | idle/clear | open circle | `#9ECE6A` (Herdr green) | `IDLE` |
| `4` | unknown | question mark in a neutral circle | `#565F89` (Herdr overlay0) | `UNKNOWN` |
| `5` | settled | flag primitive | `#565F89` (Herdr overlay0, dimmed) | `SETTLED` |

The installed source uses rank `1` for both done/unseen and manual unread; the device must not claim to distinguish those with a second local priority model. The rank and state word are authoritative inputs. Settled and unknown share a neutral family but remain distinct through their glyph and literal label.

### Non-color and contrast rules

- Primary title and state text use `#F8FAFC` on `#0B0F14`; metadata uses `#CBD5E1` or brighter when the panel background requires it. Text must meet at least 4.5:1 contrast against its immediate background; colored rails/glyphs are not the only contrast test.
- A current state always has all three cues: semantic color, non-color glyph/geometry, and literal label.
- Stale/offline veils reduce the old content's luminance and add diagonal hatch/slash geometry. The old identity remains readable enough to diagnose what became stale, but the overlay must dominate and the key must be disabled.
- `REJECTED`, `FAILED`, and `OFFLINE` use `#EF4444` plus cross/broken-link geometry and words. `UNCERTAIN` uses neutral gray plus `?`, not green or cyan.
- LEDs, if rendered by later implementation through the verified physical map, may repeat the semantic state color but never introduce meaning absent from the panel. Phase 2 acceptance is display-first.

---

## Tile State Contract

| Surface state | Identity content | State cue | Key behavior |
|----------------|------------------|------------|--------------|
| Occupied/current | Title + workspace/repository discriminator | Installed rank mapping above | Enabled only after commit and while binding is fresh/current |
| Empty | `NO AGENT` | outlined square/dash + `EMPTY`, neutral secondary surface | Disabled; press produces visible `REJECTED`/`EMPTY`, never host I/O |
| Stale | Freeze last known title/discriminator/state | diagonal veil + `STALE`, destructive veil edge | Disabled; no focus dispatch until a complete authoritative snapshot rebinds it |
| Offline | Freeze last known title/discriminator when available; otherwise `NO AGENT` | broken-link geometry + `OFFLINE`, destructive veil edge | Disabled; no queue, replay, or optimistic retry |
| Unknown rank/state (`4`) | Current authoritative identity if complete | `?` + `UNKNOWN`, neutral Herdr overlay color | Enabled only if the complete identity/binding is fresh; unknown is not unavailable |
| Unavailable/incompatible source | No guessed identity; show `UNAVAILABLE` | `?`/blocked buffer glyph plus destructive edge | Disabled until a valid complete source generation arrives |
| Snapshot synchronization | No mixed-generation identity is actionable | `SYNC` + neutral double-line/buffer glyph | All three agent keys disabled during stage/render/commit |

State precedence is strict: incompatible or source-unavailable > offline > stale > focus feedback > ordinary rank state. A lifecycle event never substitutes the new occupant of a slot. It freezes the old identity as stale until a complete fresh snapshot commits.

---

## Focus Interaction and Feedback

The only device action is a typed focus intent containing the committed slot/binding plus action correlation, host epoch, and snapshot revision. The host revalidates the exact opaque pane identity, terminal identity, optional session fingerprint, source revision, epoch, and snapshot revision before calling Herdr `agent.focus({target: pane_id})`. No slot-only lookup, title lookup, settle, dismiss, unread, reply, approval, prompt, key-send, shell command, or arbitrary Herdr method is reachable from a key.

| Feedback | Glyph/rail | Exact device copy | Entry and exit |
|----------|------------|-------------------|----------------|
| Pending | static right arrow or short line; `#22D3EE` | `PENDING` | Appears immediately after an accepted current-binding press. No spinner or pulse. Remains until result or 3-second bounded deadline. |
| Success | check mark; Herdr green semantic accent | `FOCUSED` | Only after a matching focused `agent_info` proves pane, terminal/session identity, source revision, host epoch, and snapshot revision. Hold for 2 seconds or until a newer complete snapshot commits. |
| Rejected | cross; `#EF4444` | `REJECTED` | For empty, stale, incompatible, invalid slot/generation, or host/Herdr typed error. Hold for 2 seconds; no retry. |
| Stale binding | diagonal slash; `#EF4444` | `STALE` | Distinct from generic rejection when the displayed generation is no longer current. The tile remains veiled and disabled until rebind. |
| Vanished target | broken-link/cross; `#EF4444` | `VANISHED` | Distinct result when the target disappeared or Herdr returns `agent_not_found`; never substitute a new occupant. |
| Offline | broken-link; `#EF4444` | `OFFLINE` | Distinct source/link state; all agent keys disabled, no action queued or replayed. |
| Timeout/uncertain | question mark; neutral gray | `UNCERTAIN` | No acknowledged exact focus before the 3-second bound. Do not show success and do not retry automatically; a fresh press after a fresh authoritative generation is required. |
| Protocol/compatibility failure | cross over buffer; `#EF4444` | `FAILED` | Invalid response, wrong action/epoch/revision, malformed source, or incompatible protocol. Distinct from Herdr `REJECTED` and not actionable. |

A native Herdr focus may mark a tab seen or affect the installed manual-unread timing. The keypad must not compensate, restore flags, or reinterpret that native behavior as a triage action. A subsequent authoritative snapshot may reorder the three tiles; that is a normal source update, not an animation or local reprioritization.

### Atomic generation behavior

1. Host stages a complete three-position snapshot, including explicit empty records, normalized state, title/discriminator, opaque identity, Herdr record revision, host epoch, and bridge snapshot revision.
2. Firmware validates the bounded frame through the existing `ProtocolCodec`/`ProtocolSession` seam and stages it separately from the committed generation.
3. Firmware clears the first three panels to `SYNC`, disables key dispatch, and renders staged panels in canonical order through `BoardAdapter`.
4. After every panel draw succeeds, firmware commits pixels and bindings together and enables only fresh occupied bindings. If any panel or validation fails, keep the generation non-actionable and show `FAILED`/`UNAVAILABLE`; never partially enable a tile.
5. A focus result is accepted only for the committed action and exact committed generation. A reconnect/session transition rotates the host epoch, discards pending intents, and requires a new complete snapshot.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA | `Focus agent` (host/evidence wording only; keypad action is a direct keypress) |
| Empty state heading | `EMPTY` |
| Empty state body | `NO AGENT` |
| Error state | `Focus rejected. The displayed agent is stale, unavailable, offline, or no longer present; wait for a fresh snapshot and press its current key.` |
| Destructive confirmation | None. Phase 2 has no destructive keypad action and must not add one. |

### Required bounded device labels

`SYNC`, `EMPTY`, `NO AGENT`, `BLOCKED`, `UNSEEN`, `WORKING`, `IDLE`, `SETTLED`, `UNKNOWN`, `STALE`, `OFFLINE`, `UNAVAILABLE`, `PENDING`, `FOCUSED`, `REJECTED`, `VANISHED`, `UNCERTAIN`, and `FAILED` are the only state/result words. They are uppercase ASCII and may be shortened only through a contract-approved renderer abbreviation; never replace them with a blank, generic `ERROR`, or color-only indicator.

Copy rules:

- Use direct nouns and verbs. `FOCUSED` means exact Herdr acknowledgement, not USB delivery or a host-side optimistic assumption.
- `PENDING` means an accepted current-generation request is in flight; it is not success.
- Never promise retry, replay, queueing, or automatic recovery. A failed/uncertain press is discarded.
- Do not expose opaque pane IDs, terminal IDs, host epochs, snapshot revisions, raw paths, prompts, transcripts, credentials, or socket details on a 128×128 panel. They belong in bounded host evidence only.

---

## UI Considerations

Applicable state considerations resolved: 8 covered, 1 backstop, 0 unresolved. The real-time/offline/identity domain rules are specified above rather than treated as generic list states.

| Category | Element(s) | Status | Resolution / Reason |
|----------|------------|--------|---------------------|
| empty | three fixed agent tiles, normalized list | ✅ covered | Zero entries render three stable `EMPTY`/`NO AGENT` tiles; occupied entries never shift into a different physical position. |
| loading | snapshot transition, focus result | ✅ covered | Snapshot staging renders static `SYNC` and disables keys; focus renders static `PENDING` without a spinner or optimistic success. |
| error | tile, focus feedback, source health | ✅ covered | Render `REJECTED`, `VANISHED`, `FAILED`, `STALE`, or `OFFLINE` with a distinct geometric cue and safe next condition; never leave a blank or claim success. |
| populated | occupied tile | ✅ covered | Render title, discriminator, installed state glyph/word, and a fresh committed binding in one fixed panel hierarchy. |
| partial | title/discriminator/source metadata | ✅ covered | Missing nullable presentation fields become bounded `UNAVAILABLE`/`NO WORKSPACE`; required identity/rank failures disable the source rather than guessing or showing a false occupied tile. |
| overflow | title and discriminator | ✅ covered | Measure each one-line field, truncate with ASCII `...`, preserve a distinguishing suffix/prefix where possible, and never allow text to cross the 4px inset. |
| zero-one-many | three agent positions | ✅ covered | Zero, one, two, and three entries all render the same three positions; extra rows are not shown and do not alter installed ordering of the first three. |
| long-text | title, workspace/repository discriminator | 🧪 backstop | On the delivered unit, exercise maximum normalized strings at the lowest proof brightness and correct desk orientation; verify no clipping, bezel collision, or loss of the state/result label. |

---

## Explicit Non-Goals

This contract does **not** include:

- a Codex usage or fourth tile; physical panel/key 4 remains neutral until Phase 3;
- a device menu, encoder navigation, brightness control, diagnostics page, or browsing mode;
- Wi-Fi, hybrid transport, network provisioning, or credentials on the device; Phase 1's selected USB seam remains the only path;
- settle, dismiss, mark-read/unread, acknowledge, reply, approval, prompt, key-send, arbitrary Herdr methods, plugin control-socket actions, or generic host commands;
- local inbox prioritization, a second sort order, title/cwd slot lookup, or substitution after reassignment;
- Phase 4 reboot/suspend/resume/recovery workflow, queued/replayed presses, or broad cross-component recovery;
- decorative animation, flashing attention effects, remote fonts/icons, a web UI, or any registry component.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not applicable — embedded firmware/host Python, no React stack |
| Third-party UI registries | none permitted | not applicable; no registry code, remote assets, fonts, or icons may enter this phase |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
