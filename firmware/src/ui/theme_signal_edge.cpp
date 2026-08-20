#include <cstdio>

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
  const int32_t cx = state == TileState::Empty ? 64 : 72;
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
    case TileState::Working:  // filled triangle
      sprite.fillTriangle(cx - 10, cy - 15, cx - 10, cy + 15, cx + 14, cy, color);
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
  sprite.drawString(row, 15, 5);
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
    sprite.drawString(row, 15, 17);
  }
}

void drawHatchedGauge(LGFX_Sprite& sprite, int32_t x, int32_t y, int32_t w, int32_t h) {
  sprite.drawRect(x, y, w, h, kSettled);
  const int32_t right = x + w - 3;
  for (int32_t start = x + 2; start < right; start += 7) {
    const int32_t end = start + 7 < right ? start + 7 : right;
    sprite.drawLine(start, y + h - 3, end, y + h - 3 - (end - start), kSettled);
  }
}

void drawFeedbackGlyph(LGFX_Sprite& sprite, TileFeedback feedback, bool phase_high) {
  if (feedback == TileFeedback::Pending) {
    const uint8_t dots = phase_high ? 3 : 2;
    for (uint8_t dot = 0; dot < dots; ++dot) sprite.fillRect(11 + dot * 6, 117, 2, 2, kBackground);
  } else if (feedback == TileFeedback::Success) {
    sprite.drawLine(9, 118, 14, 123, kBackground);
    sprite.drawLine(14, 123, 24, 112, kBackground);
  } else if (feedback == TileFeedback::Uncertain) {
    sprite.fillRect(15, 112, 2, 8, kBackground);
    sprite.fillCircle(16, 123, 1, kBackground);
  } else {
    sprite.drawLine(10, 112, 24, 124, kBackground);
    sprite.drawLine(24, 112, 10, 124, kBackground);
  }
}

void drawMenuRow(LGFX_Sprite& sprite, int32_t y, bool selected, bool editing,
                 const char* label, const char* value) {
  if (selected) sprite.fillRect(12, y, 112, 20, kAccent);
  if (selected && editing) sprite.drawRect(12, y, 112, 20, kBackground);
  const uint16_t foreground = selected ? kBackground : kMetadata;
  const uint16_t background = selected ? kAccent : kBackground;
  sprite.setTextColor(foreground, background);
  sprite.drawString(selected ? ">" : " ", 16, y + 6);
  sprite.drawString(label, 28, y + 6);
  sprite.setTextColor(selected ? kBackground : kPrimary, background);
  sprite.drawString(value, rightAlignedX(value), y + 6);
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
      sprite.drawString("NO AGENT", centeredX("NO AGENT"), 104);
      drawGlyph(sprite, TileState::Empty, kEmptyEdge);
    } else {
      drawRail(sprite, tile.state, content, state.blocked_pulse_high);
      drawTitleRows(sprite, tile.title, fence != nullptr ? kSettled : kPrimary);
      sprite.setTextColor(fence != nullptr ? kSettled : kMetadata, kBackground);
      sprite.drawString(tile.discriminator, 15, 32);
      drawGlyph(sprite, tile.state, content);
      sprite.setTextColor(content, kBackground);
      sprite.drawString(base.word, 15, 110);
      char since[6] = {};
      ellipsize(since, sizeof(since), tile.since);
      sprite.setTextColor(fence != nullptr ? kSettled : kMetadata, kBackground);
      sprite.drawString(since, rightAlignedX(since), 112);
    }

    if (feedback != nullptr) {
      sprite.fillRect(0, 108, 128, 20, feedback->color);
      drawFeedbackGlyph(sprite, tile.feedback, state.blocked_pulse_high);
      sprite.setTextColor(kBackground, feedback->color);
      sprite.drawString(feedback->word, 34, 114);
    } else if (fence != nullptr) {
      sprite.fillRect(0, 108, 128, 20, kDestructive);
      sprite.setTextColor(kBackground, kDestructive);
      sprite.drawString(fence, centeredX(fence), 114);
    }
  }

  void composePanel4(LGFX_Sprite& sprite, const RenderState& state) override {
    sprite.fillScreen(kBackground);
    sprite.fillRect(0, 0, 8, 128, kSettled);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("CODEX", 16, 6);
    char primary[8] = "N/A";
    char secondary[8] = "N/A";
    if (state.codex.primary >= 0) snprintf(primary, sizeof(primary), "%d%%", state.codex.primary);
    if (state.codex.secondary >= 0) snprintf(secondary, sizeof(secondary), "%d%%", state.codex.secondary);
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("5H", 16, 28);
    sprite.drawString(primary, rightAlignedX(primary), 28);
    sprite.drawString("WEEK", 16, 48);
    sprite.drawString(secondary, rightAlignedX(secondary), 48);
    if (state.codex.primary >= 0) {
      sprite.fillRect(16, 32, 108 * state.codex.primary / 100, 8, kAccent);
      sprite.drawRect(16, 32, 108, 8, kSettled);
    } else {
      drawHatchedGauge(sprite, 16, 32, 108, 8);
    }
    if (state.codex.secondary >= 0) {
      sprite.fillRect(16, 52, 108 * state.codex.secondary / 100, 8, kAccent);
      sprite.drawRect(16, 52, 108, 8, kSettled);
    } else {
      drawHatchedGauge(sprite, 16, 52, 108, 8);
    }
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString(state.codex.reset_text, 16, 70);
    sprite.drawString(state.codex.observation_age, 16, 86);
    const char* status = state.codex.source_state == CodexSourceState::Current ? "CURRENT" :
                         state.codex.source_state == CodexSourceState::Stale ? "STALE" :
                         state.codex.source_state == CodexSourceState::AuthRequired ? "AUTH REQUIRED" :
                         state.codex.source_state == CodexSourceState::CodexOffline ? "CODEX OFFLINE" :
                         state.codex.source_state == CodexSourceState::HostOffline ? "HOST OFFLINE" :
                         "UNAVAILABLE";
    sprite.fillRect(0, 104, 128, 24, state.codex.reached_limit == 1 ? kDestructive : kDestructive);
    sprite.setTextColor(kBackground, kDestructive);
    sprite.drawString(status, 16, 114);
    if (state.codex.reached_limit == 1) sprite.drawString("LIMIT", 88, 6);
  }

  void composeMenu(LGFX_Sprite& sprite, const MenuState& menu) override {
    sprite.fillScreen(kBackground);
    sprite.fillRect(0, 0, 8, 128, kAccent);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("MENU", 16, 8);
    sprite.drawLine(16, 22, 124, 22, kSettled);

    drawMenuRow(sprite, 30, menu.cursor == 0, menu.editing && menu.cursor == 0,
                "THEME", themeName(menu.theme_candidate));
    drawMenuRow(sprite, 58, menu.cursor == 1, menu.editing && menu.cursor == 1,
                "LED", grammarName(menu.grammar_candidate));

    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString(menu.editing ? "TURN: CHANGE" : "TURN: SELECT", 16, 100);
    sprite.drawString(menu.editing ? "CLICK: SAVE" : "CLICK: ENTER", 16, 112);
  }

  void composeSync(LGFX_Sprite& sprite) override {
    sprite.fillScreen(kBackground);
    sprite.fillRect(0, 0, 8, 128, kAccent);
    sprite.setTextColor(kAccent, kBackground);
    sprite.setTextSize(1);
    sprite.drawString("SYNC", 24, 54);
    sprite.drawLine(24, 68, 104, 68, kAccent);
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
