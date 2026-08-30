---
created: 2026-08-30T21:51:07.847Z
title: Match Copilot tile to active theme
area: ui
severity: cosmetic
files:
  - firmware/src/ui/theme_signal_edge.cpp
  - firmware/src/ui/theme_ledger.cpp
  - firmware/src/ui/theme_beacon.cpp
  - firmware/src/ui/theme_instrument.cpp
  - firmware/src/ui/theme_common.h
---

## Problem

The live Copilot usage screen renders with the same visual treatment in every firmware theme. Codex follows Signal Edge, Ledger, Beacon, and Instrument styling, so switching to Copilot makes panel 4 look inconsistent with the other panels and the selected theme.

This is intentionally out of scope for quick task `260830-t2s`. Copilot collection, availability-aware alternation, labels, values, and exact-device behavior are complete.

## Solution

Give each existing panel-4 theme branch a theme-native Copilot composition while preserving the current `COPILOT`, `USED`, `INCL`, AIC values, truth-state wording, 8-second provider selection, and one-frame flush behavior. Reuse each theme's Codex geometry and palette rather than adding another design system. Verify all four deterministic Copilot captures on the paired keypad.
