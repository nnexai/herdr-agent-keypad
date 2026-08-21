#include <TKeyboardS3Pro.h>

#include <cstdio>
#include <string.h>

#include "theme.h"
#include "theme_common.h"

// Ledger — the typographic display language. A dense inbox row: header
// (discriminator · age) over a hairline, two-row title, a state row whose
// underline weight/style is the non-color channel, footer slot dots.
// BLOCKED inverts the state row to a solid rose band. Feedback takes over the
// header band opaquely with the exact cause word. Stale/offline/unavailable
// render a persistent red band absorbing the discriminator and dim content.

namespace {
using namespace theme_common;

// Underline geometry per state (weight in px; style markers keep the channel
// distinguishable in the native call log independent of color).
// Underline geometry per state (weight in px; style markers keep the channel
// distinguishable in the native call log independent of color).
void drawStateUnderline(LGFX_Sprite& sprite, TileState state, int32_t x, int32_t y,
                        int32_t w, uint16_t color, uint8_t phase) {
  int32_t weight = 0;
  switch (state) {
    case TileState::Working: weight = 5; break;
    case TileState::Unseen: weight = 2; break;
    case TileState::Idle: weight = 2; break;
    case TileState::Settled: weight = 1; break;
    case TileState::Unknown:
      for (int32_t dx = 0; dx < w; dx += 6) sprite.fillRect(x + dx, y, 3, 2, color);
      return;
    default:
      return;  // BLOCKED handled by inversion band; empty draws none.
  }
  if (state == TileState::Unseen) {
    sprite.fillRect(x, y, w, weight, color);
    sprite.fillRect(x, y + 4, w, weight, color);
  } else {
    sprite.fillRect(x, y, w, weight, color);
  }
  // A record's active row gets one bounded travelling gap. Baselines and
  // underline weight remain fixed; only the typographic accent moves.
  if (phase != 0 && (state == TileState::Working || state == TileState::Unseen)) {
    const int32_t gap_x = x + 4 + static_cast<int32_t>(phase % 4U) * 16;
    sprite.fillRect(gap_x, y, 8, weight, kBackground);
    if (state == TileState::Unseen) sprite.fillRect(gap_x, y + 4, 8, weight, kBackground);
  }
}
void drawLedgerGlyph(LGFX_Sprite& sprite, TileState state, int32_t cx, int32_t cy, uint16_t color) {
  switch (state) {
    case TileState::Blocked:
      sprite.drawLine(cx - 7, cy - 7, cx + 7, cy + 7, color);
      sprite.drawLine(cx + 7, cy - 7, cx - 7, cy + 7, color);
      break;
    case TileState::Unseen:
      sprite.fillCircle(cx, cy, 6, color);
      break;
    case TileState::Working:
      sprite.fillTriangle(cx - 5, cy - 7, cx - 5, cy + 7, cx + 7, cy, color);
      break;
    case TileState::Idle:
      sprite.drawCircle(cx, cy, 6, color);
      break;
    case TileState::Settled:
      sprite.drawLine(cx - 6, cy - 6, cx - 6, cy + 6, color);
      sprite.drawLine(cx - 6, cy - 6, cx + 6, cy - 6, color);
      break;
    case TileState::Unknown:
      sprite.drawCircle(cx, cy - 3, 4, color);
      sprite.fillRect(cx - 1, cy + 2, 2, 4, color);
      sprite.fillCircle(cx, cy + 8, 1, color);
      break;
    default:
      sprite.fillRect(cx - 6, cy - 1, 12, 2, color);
      break;
  }
}

class LedgerTheme final : public ThemeRenderer {
 public:
  bool detail_line_enabled = false;  // menu toggle hook; off by default

  void composeTile(LGFX_Sprite& sprite, uint8_t slot, const RenderState& state) override {
    sprite.fillScreen(kBackground);
    if (slot >= RenderState::kSlotCount) return;
    const RenderState::Slot& tile = state.slots[slot];
    const char* fence = fenceWord(state.source_status);
    const StateStyle base = styleFor(tile.state);
    const StateStyle* feedback = feedbackStyle(tile.feedback);
    const uint16_t ink = fence != nullptr ? kSettled : kPrimary;
    const uint16_t meta = fence != nullptr ? kSettled : kMetadata;
    const uint16_t state_color = fence != nullptr ? kSettled : base.color;
    const bool motion_active = fence == nullptr && !state.syncing &&
                               (state.transition_active || state.ambient_phase != 0);
    const uint8_t phase = motion_active
                              ? (state.transition_active ? state.transition_phase
                                                         : state.ambient_phase) % 4U
                              : 0;
    char row[16] = {};

    // Header y:5..16 — physical press gets a localized row cue before the
    // pending word is shown on the next complete frame.
    if (tile.press_impulse) {
      sprite.fillRect(30, 86, 64, 3, kAccent);
      sprite.fillRect(0, 4, 4, 14, kAccent);
    } else if (feedback != nullptr) {
      sprite.fillRect(0, 4, 128, 14, feedback->color);
      sprite.setTextColor(kBackground, feedback->color);
      sprite.drawString(feedback->word, 6, 7);
      if (tile.feedback == TileFeedback::Pending && phase != 0) {
        sprite.fillRect(8 + static_cast<int32_t>(phase) * 16, 16, 12, 2,
                        kBackground);
      } else if (tile.feedback == TileFeedback::Success && phase != 0) {
        sprite.drawLine(92, 8, 98 + static_cast<int32_t>(phase), 14, kBackground);
      }
    } else if (fence != nullptr) {
      sprite.fillRect(0, 4, 128, 14, kDestructive);
      sprite.setTextColor(kBackground, kDestructive);
      sprite.drawString(fence, 6, 7);
    } else if (tile.state != TileState::Empty) {
      ellipsize(row, 14, tile.discriminator);
      sprite.setTextColor(meta, kBackground);
      sprite.drawString(row, 6, 7);
      sprite.drawString(tile.age, 100, 7);
    }
    sprite.drawLine(4, 18, 124, 18, kSettled);

    if (tile.state == TileState::Empty) {
      sprite.setTextColor(kMetadata, kBackground);
      sprite.drawString("EMPTY", 6, 40);
      sprite.drawString("SLOT EMPTY", 6, 56);
      sprite.drawString("NO AGENT", 6, 72);
    } else {
      char first[16] = {};
      ellipsize(first, 15, tile.title);
      const size_t length = strlen(tile.title);
      if (length > 14) {
        memcpy(first, tile.title, 14);
        first[14] = '\0';
        ellipsize(row, 15, tile.title + 14);
      } else {
        row[0] = '\0';
      }
      sprite.setTextColor(ink, kBackground);
      sprite.drawString(first, 6, 22);
      if (row[0] != '\0') sprite.drawString(row, 6, 36);
      if (detail_line_enabled) {
        sprite.setTextColor(meta, kBackground);
        sprite.drawString("-", 6, 52);
      }

      if (tile.state == TileState::Blocked && fence == nullptr) {
        sprite.fillRect(0, 70, 128, 20, kBlocked);
        if (!state.blocked_pulse_high) sprite.fillRect(0, 70, 128, 2, kBackground);
        drawLedgerGlyph(sprite, tile.state, 16, 80, kBackground);
        sprite.setTextColor(kBackground, kBlocked);
        sprite.drawString(base.word, 30, 74);
      } else {
        drawLedgerGlyph(sprite, tile.state, 16, 80, state_color);
        sprite.setTextColor(state_color, kBackground);
        sprite.drawString(base.word, 30, 74);
        ellipsize(row, 6, tile.since);
        sprite.drawString(row, rightAlignedX(row), 74);
        drawStateUnderline(sprite, tile.state, 30, 86, 64, state_color, phase);
      }
    }

    for (uint8_t dot = 0; dot < RenderState::kSlotCount; ++dot) {
      const int32_t cx = 100 + dot * 9;
      if (dot == slot) sprite.fillCircle(cx, 119, 2, meta);
      else sprite.drawCircle(cx, 119, 2, kSettled);
    }
  }

  void composePanel4(LGFX_Sprite& sprite, const RenderState& state) override {
    const CodexRenderView& codex = state.codex;
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("CODEX", 6, 4);
    if (codex.source_state != CodexSourceState::Current) {
      sprite.fillRect(4, 4, 120, 14, kDestructive);
      sprite.setTextColor(kBackground, kDestructive);
      sprite.drawString("CODEX", 6, 4);
    }
    if (codexHasLimit(codex) &&
        codex.source_state != CodexSourceState::Current) {
      drawCodexLimitHeader(sprite, codex, 90, 4);
    }
    sprite.drawLine(4, 18, 124, 18, kSettled);

    char primary[8] = {};
    char secondary[8] = {};
    formatCodexPercent(primary, sizeof(primary), codexValue(codex, true));
    formatCodexPercent(secondary, sizeof(secondary), codexValue(codex, false));
    const bool invert_rows = codexHasLimit(codex) &&
                             codex.source_state == CodexSourceState::Current;
    if (invert_rows && codexValue(codex, true) >= 0) {
      sprite.fillRect(4, 20, 120, 18, kBlocked);
    }
    if (invert_rows && codexValue(codex, false) >= 0) {
      sprite.fillRect(4, 40, 120, 18, kBlocked);
    }
    const uint16_t row_color = codexValueColor(codex);
    sprite.setTextColor(invert_rows ? kBackground : row_color,
                        invert_rows ? kBlocked : kBackground);
    sprite.drawString("5H", 6, 30);
    sprite.drawString(primary, rightAlignedX(primary, 120), 30);
    sprite.drawString("WEEK", 6, 50);
    sprite.drawString(secondary, rightAlignedX(secondary, 120), 50);
    sprite.drawLine(4, 38, 124, 38, kSettled);
    sprite.drawLine(4, 58, 124, 58, kSettled);
    const bool motion_active = codex.source_state == CodexSourceState::Current &&
                               !state.syncing &&
                               (state.transition_active || state.ambient_phase != 0);
    if (motion_active) {
      const uint8_t phase = (state.transition_active ? state.transition_phase
                                                     : state.ambient_phase) % 4U;
      const int32_t x = 8 + static_cast<int32_t>(phase) * 24;
      if (codexValue(codex, true) >= 0) sprite.drawLine(x, 38, x + 8, 38, row_color);
      if (codexValue(codex, false) >= 0) sprite.drawLine(x, 58, x + 8, 58, row_color);
    }
    if (codex.source_state == CodexSourceState::AuthRequired) {
      sprite.drawLine(112, 8, 124, 20, kDestructive);
      sprite.drawLine(124, 8, 112, 20, kDestructive);
    }

    drawCodexMetaText(sprite, codex, 6, 70, 6, 86);
    sprite.drawLine(4, 78, 124, 78, kSettled);

    const bool state_alert = codex.source_state != CodexSourceState::Current ||
                             codexHasLimit(codex);
    if (state_alert) {
      const uint16_t band = codex.source_state == CodexSourceState::Current
                                ? kBlocked
                                : kDestructive;
      sprite.fillRect(4, 102, 120, 22, band);
      sprite.setTextColor(kBackground, band);
      if (codex.source_state == CodexSourceState::Current) {
        sprite.drawString("LIMIT", 6, 114);
      } else {
        sprite.drawString(codexStateWord(codex.source_state), 6, 114);
      }
    } else {
      drawCodexStateText(sprite, codex, 6, 114, false);
    }
  }

  void composeMenu(LGFX_Sprite& sprite, const MenuState& menu) override {
    sprite.fillScreen(kBackground);
    drawMenuPage(sprite, menu, MenuVisual::Ledger);
  }

  void composeSync(LGFX_Sprite& sprite) override {
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kAccent, kBackground);
    sprite.setTextSize(1);
    sprite.drawString("SYNC", 8, 8);
    sprite.drawLine(4, 18, 124, 18, kAccent);
    sprite.drawLine(8, 42, 88, 42, kSettled);
    sprite.drawLine(8, 58, 112, 58, kSettled);
    sprite.drawLine(8, 74, 72, 74, kSettled);
  }

  uint8_t ambientTick(uint32_t now_us) override {
    (void)now_us;
    return 0x07;
  }

  uint32_t ambientPeriodUs() const override { return 33334UL; }
};

LedgerTheme g_ledger;
}  // namespace

ThemeRenderer& ledgerTheme() { return g_ledger; }
