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
void drawStateUnderline(LGFX_Sprite& sprite, TileState state, int32_t x, int32_t y, int32_t w, uint16_t color) {
  switch (state) {
    case TileState::Working:  // full weight
      sprite.fillRect(x, y, w, 5, color);
      break;
    case TileState::Unseen:  // double underline
      sprite.fillRect(x, y, w, 2, color);
      sprite.fillRect(x, y + 4, w, 2, color);
      break;
    case TileState::Idle:  // 2 px
      sprite.fillRect(x, y, w, 2, color);
      break;
    case TileState::Settled:  // 1 px hairline
      sprite.fillRect(x, y, w, 1, color);
      break;
    case TileState::Unknown:  // dotted
      for (int32_t dx = 0; dx < w; dx += 6) sprite.fillRect(x + dx, y, 3, 2, color);
      break;
    default:
      break;  // BLOCKED handled by inversion band; empty draws none.
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
    char row[16] = {};

    // Header y:5..16 — feedback takeover wins, then fence band, then disc·age.
    if (feedback != nullptr) {
      sprite.fillRect(0, 4, 128, 14, feedback->color);
      sprite.setTextColor(kBackground, feedback->color);
      sprite.drawString(feedback->word, 6, 7);
    } else if (fence != nullptr) {
      // Persistent red band absorbing the discriminator.
      sprite.fillRect(0, 4, 128, 14, kDestructive);
      sprite.setTextColor(kBackground, kDestructive);
      sprite.drawString(fence, 6, 7);
    } else if (tile.state != TileState::Empty) {
      ellipsize(row, 14, tile.discriminator);
      sprite.setTextColor(meta, kBackground);
      sprite.drawString(row, 6, 7);
    }
    sprite.drawLine(4, 18, 124, 18, kSettled);  // hairline

    if (tile.state == TileState::Empty) {
      sprite.setTextColor(kMetadata, kBackground);
      sprite.drawString("SLOT EMPTY", 6, 56);
    } else {
      // Two-row title y:22.
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
      sprite.drawString(first, 6, 24);
      if (row[0] != '\0') sprite.drawString(row, 6, 38);
      if (detail_line_enabled) {
        sprite.setTextColor(meta, kBackground);
        sprite.drawString("—", 6, 54);
      }

      // State row y:72..88.
      if (tile.state == TileState::Blocked && fence == nullptr) {
        sprite.fillRect(0, 70, 128, 20, kBlocked);  // full-band inversion
        sprite.setTextColor(kBackground, kBlocked);
        sprite.drawString(base.word, 6, 76);
      } else {
        sprite.setTextColor(state_color, kBackground);
        sprite.drawString(base.word, 6, 74);
        drawStateUnderline(sprite, tile.state, 6, 86, 70, state_color);
      }
    }

    // Footer y:116 — failure reason left, slot dots right.
    if (feedback != nullptr && tile.feedback != TileFeedback::Pending && tile.feedback != TileFeedback::Success) {
      sprite.setTextColor(feedback->color, kBackground);
      sprite.drawString(feedback->word, 6, 114);
    }
    for (uint8_t dot = 0; dot < RenderState::kSlotCount; ++dot) {
      const int32_t cx = 100 + dot * 9;
      if (dot == slot) sprite.fillCircle(cx, 119, 2, meta);
      else sprite.drawCircle(cx, 119, 2, kSettled);
    }
  }

  void composePanel4(LGFX_Sprite& sprite, const RenderState&) override {
    // Ledger numbers page in honest UNAVAILABLE form: labels with em-dash
    // values, never fabricated numbers.
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("CODEX", 6, 7);
    sprite.drawLine(4, 18, 124, 18, kSettled);
    const char* labels[] = {"5H", "WEEKLY", "RESET"};
    for (uint8_t line = 0; line < 3; ++line) {
      const int32_t y = 30 + line * 20;
      sprite.setTextColor(kMetadata, kBackground);
      sprite.drawString(labels[line], 6, y);
      sprite.drawString("—", 96, y);
      sprite.drawLine(4, y + 14, 124, y + 14, kSettled);
    }
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("UNAVAILABLE", 6, 100);
    sprite.drawString("NO VALUES", 6, 114);
  }

  void composeMenu(LGFX_Sprite& sprite, const MenuState& menu) override {
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("SETTINGS", 6, 7);
    sprite.drawLine(4, 18, 124, 18, kSettled);
    sprite.setTextColor(menu.cursor == 0 ? kAccent : kMetadata, kBackground);
    sprite.drawString(menu.cursor == 0 ? "> THEME" : "  THEME", 6, 32);
    sprite.drawString(themeName(menu.theme_candidate), 68, 32);
    sprite.setTextColor(menu.cursor == 1 ? kAccent : kMetadata, kBackground);
    sprite.drawString(menu.cursor == 1 ? "> LED" : "  LED", 6, 52);
    sprite.drawString(grammarName(menu.grammar_candidate), 68, 52);
    sprite.drawLine(4, 72, 124, 72, kSettled);
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("TURN·SEL — CLICK·CLOSE", 6, 108);
  }

  void composeSync(LGFX_Sprite& sprite) override {
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kAccent, kBackground);
    sprite.setTextSize(1);
    sprite.drawString("SYNC", 8, 8);
    sprite.drawLine(4, 18, 124, 18, kAccent);
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("UPDATING", 8, 56);
  }
};

LedgerTheme g_ledger;
}  // namespace

ThemeRenderer& ledgerTheme() { return g_ledger; }
