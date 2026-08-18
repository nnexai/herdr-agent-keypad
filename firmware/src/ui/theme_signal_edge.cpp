#include <TKeyboardS3Pro.h>

#include <string.h>

#include "theme.h"
#include "theme_common.h"

// Signal Edge — the default display language. State rail on the left edge
// (width + fill pattern is the non-color state channel), quiet two-row title,
// discriminator, centered stroke glyph, state word, and an opaque bottom
// feedback band at y:108..128. Fenced source health desaturates content and
// pins the reason in the band. Composition only — flushing stays with the
// projection commit path.

namespace {
using namespace theme_common;

void drawDashedRect(LGFX_Sprite& sprite, int32_t x, int32_t y, int32_t w, int32_t h, uint16_t color) {
  for (int32_t dx = 0; dx < w; dx += 6) {
    const int32_t seg = dx + 3 <= w ? 3 : w - dx;
    sprite.drawLine(x + dx, y, x + dx + seg - 1, y, color);
    sprite.drawLine(x + dx, y + h - 1, x + dx + seg - 1, y + h - 1, color);
  }
  for (int32_t dy = 0; dy < h; dy += 6) {
    const int32_t seg = dy + 3 <= h ? 3 : h - dy;
    sprite.drawLine(x, y + dy, x, y + dy + seg - 1, color);
    sprite.drawLine(x + w - 1, y + dy, x + w - 1, y + dy + seg - 1, color);
  }
}

// State rail x:0..15 — width plus fill pattern is the state channel.
void drawRail(LGFX_Sprite& sprite, TileState state, uint16_t color, bool pulse_high) {
  switch (state) {
    case TileState::Blocked: {  // 16 px animated dashes — crawl by half a
      const int32_t offset = pulse_high ? 0 : 6;  // dash period per pulse phase
      for (int32_t y = offset; y < 128; y += 12) sprite.fillRect(0, y, 16, 7, color);
      break;
    }
    case TileState::Unseen:  // 3-1-3 doubled stripes.
      sprite.fillRect(0, 0, 3, 128, color);
      sprite.fillRect(4, 0, 3, 128, color);
      break;
    case TileState::Working:  // 16 px solid.
      sprite.fillRect(0, 0, 16, 128, color);
      break;
    case TileState::Idle:  // 8 px thin.
      sprite.fillRect(0, 0, 8, 128, color);
      break;
    case TileState::Settled:  // hollow outline.
      sprite.drawRect(0, 0, 16, 128, color);
      break;
    case TileState::Unknown:  // dotted.
      for (int32_t y = 4; y < 128; y += 8) sprite.fillCircle(6, y, 1, color);
      break;
    default:
      break;  // Empty renders no rail.
  }
}

void drawGlyph(LGFX_Sprite& sprite, TileState state, uint16_t color) {
  // 30 px stroke primitives centered in x:16..128 y:44..76.
  const int32_t cx = 72;
  const int32_t cy = 60;
  switch (state) {
    case TileState::Blocked:  // heavy cross
      sprite.drawLine(cx - 15, cy - 15, cx + 15, cy + 15, color);
      sprite.drawLine(cx + 15, cy - 15, cx - 15, cy + 15, color);
      sprite.drawLine(cx - 14, cy - 15, cx + 16, cy + 15, color);
      sprite.drawLine(cx + 16, cy - 15, cx - 14, cy + 15, color);
      break;
    case TileState::Unseen:  // filled disc
      sprite.fillCircle(cx, cy, 13, color);
      break;
    case TileState::Working:  // triangle
      sprite.drawLine(cx - 10, cy - 15, cx - 10, cy + 15, color);
      sprite.drawLine(cx - 10, cy - 15, cx + 14, cy, color);
      sprite.drawLine(cx + 14, cy, cx - 10, cy + 15, color);
      break;
    case TileState::Idle:  // ring
      sprite.drawCircle(cx, cy, 13, color);
      break;
    case TileState::Settled:  // corner
      sprite.drawLine(cx - 12, cy - 12, cx - 12, cy + 12, color);
      sprite.drawLine(cx - 12, cy - 12, cx + 12, cy - 12, color);
      break;
    case TileState::Unknown:  // question mark strokes
      sprite.drawCircle(cx, cy - 6, 8, color);
      sprite.fillRect(cx - 1, cy + 4, 2, 6, color);
      sprite.fillCircle(cx, cy + 14, 1, color);
      break;
    case TileState::Empty:  // dash
      sprite.fillRect(cx - 10, cy - 1, 20, 2, color);
      break;
    default:  // fence cross for stale/offline/unavailable
      sprite.drawLine(cx - 15, cy + 12, cx + 15, cy - 12, color);
      sprite.drawLine(cx - 15, cy - 12, cx + 15, cy + 12, color);
      break;
  }
}

// Two title rows at 12 px cell, ellipsized; bounded scratch, no allocation.
void drawTitleRows(LGFX_Sprite& sprite, const char* title, uint16_t color) {
  constexpr size_t kRowChars = 13;
  char row[kRowChars + 1] = {};
  const size_t length = strlen(title);
  size_t first = length < kRowChars ? length : kRowChars;
  memcpy(row, title, first);
  row[first] = '\0';
  sprite.setTextColor(color, kBackground);
  sprite.drawString(row, 18, 8);
  if (length > kRowChars) {
    size_t remaining = length - kRowChars;
    size_t second = remaining < kRowChars ? remaining : kRowChars;
    memcpy(row, title + kRowChars, second);
    row[second] = '\0';
    if (remaining > kRowChars && second >= 3) {
      row[second - 1] = '.';
      row[second - 2] = '.';
      row[second - 3] = '.';
    }
    sprite.drawString(row, 18, 20);
  }
}

class SignalEdgeTheme final : public ThemeRenderer {
 public:
  void composeTile(LGFX_Sprite& sprite, uint8_t slot, const RenderState& state) override {
    sprite.fillScreen(kBackground);
    if (slot >= RenderState::kSlotCount) return;
    const RenderState::Slot& tile = state.slots[slot];
    const char* fence = fenceWord(state.source_status);
    const StateStyle base = styleFor(tile.state);
    const StateStyle* feedback = feedbackStyle(tile.feedback);
    // Fence desaturates content; feedback band always wins the bottom band.
    const uint16_t content = fence != nullptr ? kSettled : base.color;

    if (tile.state == TileState::Empty) {
      drawDashedRect(sprite, 4, 4, 120, 120, kEmptyEdge);
      sprite.setTextColor(kMetadata, kBackground);
      sprite.drawString("NO AGENT", 24, 56);
      drawGlyph(sprite, TileState::Empty, kEmptyEdge);
    } else {
      drawRail(sprite, tile.state, content, state.blocked_pulse_high);
      drawTitleRows(sprite, tile.title, fence != nullptr ? kSettled : kPrimary);
      sprite.setTextColor(fence != nullptr ? kSettled : kMetadata, kBackground);
      sprite.drawString(tile.discriminator, 18, 34);
      drawGlyph(sprite, tile.state, content);
      sprite.setTextColor(content, kBackground);
      sprite.drawString(base.word, 18, 96);
    }

    if (feedback != nullptr) {
      sprite.fillRect(0, 108, 128, 20, feedback->color);
      sprite.setTextColor(kBackground, feedback->color);
      sprite.drawString(feedback->word, 18, 114);
    } else if (fence != nullptr) {
      sprite.fillRect(0, 108, 128, 20, kDestructive);
      sprite.setTextColor(kBackground, kDestructive);
      sprite.drawString(fence, 18, 114);
    }
  }

  void composePanel4(LGFX_Sprite& sprite, const RenderState&) override {
    // Honest no-data composition: no Codex collector exists in Phase 02.2.
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("CODEX", 18, 8);
    sprite.fillRect(0, 0, 16, 128, kSettled);
    for (uint8_t gauge = 0; gauge < 2; ++gauge) {
      const int32_t top = 32 + gauge * 32;
      sprite.drawRect(18, top, 102, 18, kSettled);
      for (int32_t x = 20; x < 116; x += 8) {
        sprite.drawLine(x, top + 15, x + 12, top + 3, kSettled);
      }
    }
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("UNAVAILABLE", 18, 100);
    sprite.drawString("NO VALUES", 18, 114);
  }

  void composeMenu(LGFX_Sprite& sprite, const MenuState& menu) override {
    sprite.fillScreen(kBackground);
    sprite.fillRect(0, 0, 12, 128, kAccent);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("MENU", 20, 8);
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("THEME", 20, 34);
    sprite.drawString("LED", 20, 62);
    sprite.setTextColor(menu.cursor == 0 ? kAccent : kSettled, kBackground);
    sprite.drawString(menu.cursor == 0 ? ">" : " ", 8, 34);
    sprite.setTextColor(menu.cursor == 1 ? kAccent : kSettled, kBackground);
    sprite.drawString(menu.cursor == 1 ? ">" : " ", 8, 62);
    sprite.setTextColor(menu.editing && menu.cursor == 0 ? kAccent : kPrimary, kBackground);
    sprite.drawString(themeName(menu.theme_candidate), 68, 34);
    sprite.setTextColor(menu.editing && menu.cursor == 1 ? kAccent : kPrimary, kBackground);
    sprite.drawString(grammarName(menu.grammar_candidate), 68, 62);
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("TURN·SEL — CLICK·CLOSE", 8, 110);
  }

  void composeSync(LGFX_Sprite& sprite) override {
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kAccent, kBackground);
    sprite.setTextSize(1);
    sprite.drawString("SYNC", 8, 8);
    sprite.drawRect(4, 4, 120, 4, kAccent);
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("UPDATING", 8, 56);
  }
};

SignalEdgeTheme g_signal_edge;
}  // namespace

ThemeRenderer& signalEdgeTheme() { return g_signal_edge; }

ThemeRenderer& themeById(ThemeId id) {
  switch (id) {
    case ThemeId::Ledger: return ledgerTheme();
    case ThemeId::Beacon: return beaconTheme();
    case ThemeId::Instrument: return instrumentTheme();
    case ThemeId::SignalEdge:
    default: return g_signal_edge;
  }
}
