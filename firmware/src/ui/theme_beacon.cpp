#include <TKeyboardS3Pro.h>

#include <string.h>

#include "theme.h"
#include "theme_common.h"

// Beacon — the distance-first display language. A 44 px center state glyph on
// a stepped radial field (4 concentric luminance bands of the state hue for
// active states; flat black for calm states), tracked state word beneath,
// title strip last. Feedback is a center takeover with a dimmed field.
// Stale desaturates and draws a bottom fence line; offline adds a red top
// hairline on every panel.

namespace {
using namespace theme_common;

// Scale a hue toward black using explicit luminance steps. The Beacon field
// reserves the brightest color for the glyph; the field itself peaks at 24 %.
uint16_t scale565(uint16_t color, uint8_t numerator, uint8_t denominator = 64) {
  const uint16_t r = static_cast<uint16_t>(((color >> 11) & 0x1F) * numerator / denominator);
  const uint16_t g = static_cast<uint16_t>(((color >> 5) & 0x3F) * numerator / denominator);
  const uint16_t b = static_cast<uint16_t>((color & 0x1F) * numerator / denominator);
  return static_cast<uint16_t>((r << 11) | (g << 5) | b);
}

bool activeField(TileState state) {
  return state == TileState::Blocked || state == TileState::Unseen || state == TileState::Working;
}

void drawField(LGFX_Sprite& sprite, uint16_t hue) {
  // Eight shallow bands avoid the old bullseye effect while remaining stable
  // on RGB565 panels. The outer band is intentionally near-black.
  static constexpr int32_t kRadii[] = {58, 52, 46, 40, 34, 28, 22, 16};
  static constexpr uint8_t kLuma[] = {3, 5, 7, 10, 14, 18, 21, 24};
  for (uint8_t band = 0; band < 8; ++band) {
    sprite.fillCircle(64, 52, kRadii[band], scale565(hue, kLuma[band]));
  }
}

void drawCenterGlyph(LGFX_Sprite& sprite, TileState state, uint16_t color) {
  // 44 px stroke primitives centered at (64, 52).
  const int32_t cx = 64;
  const int32_t cy = 52;
  switch (state) {
    case TileState::Blocked:  // heavy cross
      for (int8_t offset = -1; offset <= 1; ++offset) {
        sprite.drawLine(cx - 20 + offset, cy - 20, cx + 20 + offset, cy + 20, color);
        sprite.drawLine(cx + 20 + offset, cy - 20, cx - 20 + offset, cy + 20, color);
      }
      break;
    case TileState::Unseen:  // filled disc
      sprite.fillCircle(cx, cy, 20, color);
      break;
    case TileState::Working:  // triangle
      sprite.drawLine(cx - 14, cy - 20, cx - 14, cy + 20, color);
      sprite.drawLine(cx - 14, cy - 20, cx + 20, cy, color);
      sprite.drawLine(cx + 20, cy, cx - 14, cy + 20, color);
      break;
    case TileState::Idle:  // ring
      sprite.drawCircle(cx, cy, 20, color);
      sprite.drawCircle(cx, cy, 19, color);
      break;
    case TileState::Settled:  // corner
      sprite.drawLine(cx - 16, cy - 16, cx - 16, cy + 16, color);
      sprite.drawLine(cx - 16, cy - 16, cx + 16, cy - 16, color);
      break;
    case TileState::Unknown:  // question strokes
      sprite.drawCircle(cx, cy - 8, 11, color);
      sprite.fillRect(cx - 1, cy + 5, 3, 8, color);
      sprite.fillCircle(cx, cy + 18, 2, color);
      break;
    case TileState::Empty:  // dash
      sprite.fillRect(cx - 14, cy - 1, 28, 3, color);
      break;
    default:  // fence cross
      sprite.drawLine(cx - 20, cy + 16, cx + 20, cy - 16, color);
      sprite.drawLine(cx - 20, cy - 16, cx + 20, cy + 16, color);
      break;
  }
}

void drawFeedbackGlyph(LGFX_Sprite& sprite, TileFeedback feedback, uint16_t color) {
  const int32_t cx = 64;
  const int32_t cy = 52;
  switch (feedback) {
    case TileFeedback::Pending:  // spinner ring
      sprite.drawCircle(cx, cy, 18, color);
      sprite.fillCircle(cx, cy - 18, 3, color);
      break;
    case TileFeedback::Success:  // check
      sprite.drawLine(cx - 14, cy, cx - 4, cy + 12, color);
      sprite.drawLine(cx - 4, cy + 12, cx + 16, cy - 12, color);
      break;
    case TileFeedback::Uncertain:  // exclamation
      sprite.fillRect(cx - 1, cy - 16, 3, 20, color);
      sprite.fillCircle(cx, cy + 12, 2, color);
      break;
    default:  // failure cross
      sprite.drawLine(cx - 14, cy - 14, cx + 14, cy + 14, color);
      sprite.drawLine(cx + 14, cy - 14, cx - 14, cy + 14, color);
      break;
  }
}

class BeaconTheme final : public ThemeRenderer {
 public:
  void composeTile(LGFX_Sprite& sprite, uint8_t slot, const RenderState& state) override {
    sprite.fillScreen(kBackground);
    if (slot >= RenderState::kSlotCount) return;
    const RenderState::Slot& tile = state.slots[slot];
    const char* fence = fenceWord(state.source_status);
    const StateStyle base = styleFor(tile.state);
    const StateStyle* feedback = feedbackStyle(tile.feedback);
    const uint16_t content = fence != nullptr ? kSettled : base.color;
    char row[18] = {};

    if (tile.state == TileState::Empty) {
      // Dashed border, glyph + NO AGENT only.
      for (int32_t x = 4; x < 124; x += 8) {
        sprite.drawLine(x, 4, x + 4, 4, kEmptyEdge);
        sprite.drawLine(x, 123, x + 4, 123, kEmptyEdge);
      }
      for (int32_t y = 4; y < 124; y += 8) {
        sprite.drawLine(4, y, 4, y + 4, kEmptyEdge);
        sprite.drawLine(123, y, 123, y + 4, kEmptyEdge);
      }
      drawCenterGlyph(sprite, TileState::Empty, kEmptyEdge);
      sprite.setTextColor(kMetadata, kBackground);
      sprite.drawString("NO AGENT", 34, 96);
      return;
    }

    // Field: active states get the stepped radial field, calm states stay
    // flat black; fences desaturate everything.
    if (fence == nullptr && feedback == nullptr && activeField(tile.state)) {
      // BLOCKED field+glyph breathe in the 1.2 s pulse; other active states
      // render a steady field.
      const bool low = tile.state == TileState::Blocked && !state.blocked_pulse_high;
      drawField(sprite, low ? scale565(base.color, 12) : base.color);
    } else if (feedback != nullptr && activeField(tile.state)) {
      drawField(sprite, scale565(base.color, 12));  // dimmed field under takeover
    }

    if (feedback != nullptr) {
      drawFeedbackGlyph(sprite, tile.feedback, feedback->color);
      sprite.setTextColor(feedback->color, kBackground);
      sprite.drawString(feedback->word, 40, 73);
    } else {
      drawCenterGlyph(sprite, tile.state, content);
      sprite.setTextColor(content, kBackground);
      sprite.drawString(base.word, 40, 73);
    }

    // Opaque title strip prevents the radial field from bleeding behind text.
    sprite.fillRect(0, 96, 128, 32, kBackground);
    // Title strip y:100..122 — one title line + one identity line, centered.
    sprite.setTextColor(fence != nullptr ? kSettled : kMetadata, kBackground);
    sprite.drawString(tile.since, 92, 8);
    ellipsize(row, 17, tile.title);
    sprite.setTextColor(fence != nullptr ? kSettled : kPrimary, kBackground);
    sprite.drawString(row, 16, 100);
    ellipsize(row, 17, tile.discriminator);
    sprite.setTextColor(fence != nullptr ? kSettled : kMetadata, kBackground);
    sprite.drawString(row, 16, 112);

    if (fence != nullptr) {
      // Bottom fence line with the reason word; offline adds a red top
      // hairline on all panels.
      sprite.fillRect(0, 88, 128, 10, kDestructive);
      sprite.setTextColor(kBackground, kDestructive);
      sprite.drawString(fence, 40, 89);
      if (strcmp(fence, "OFFLINE") == 0) sprite.fillRect(0, 0, 128, 2, kDestructive);
    }
  }

  void composePanel4(LGFX_Sprite& sprite, const RenderState&) override {
    // Hatched conic dial in honest UNAVAILABLE form.
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("CODEX", 46, 8);
    sprite.drawCircle(64, 60, 34, kSettled);
    sprite.drawCircle(64, 60, 33, kSettled);
    for (int32_t hatch = -28; hatch <= 28; hatch += 8) {
      sprite.drawLine(64 + hatch - 6, 60 + 24, 64 + hatch + 6, 60 - 24, kSettled);
    }
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("UNAVAILABLE", 30, 102);
    sprite.drawString("NO VALUES", 36, 114);
  }

  void composeMenu(LGFX_Sprite& sprite, const MenuState& menu) override {
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("MENU", 48, 8);
    sprite.setTextColor(menu.cursor == 0 ? kAccent : kMetadata, kBackground);
    sprite.drawString("THEME", 28, 36);
    sprite.drawString(themeName(menu.theme_candidate), 28, 52);
    sprite.setTextColor(menu.cursor == 1 ? kAccent : kMetadata, kBackground);
    sprite.drawString("LED", 28, 76);
    sprite.drawString(grammarName(menu.grammar_candidate), 28, 92);
    sprite.setTextColor(kSettled, kBackground);
    sprite.drawString(menu.cursor == 0 ? ">" : " ", 14, 36);
    sprite.drawString(menu.cursor == 1 ? ">" : " ", 14, 76);
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("TURN·SEL — CLICK·CLOSE", 8, 112);
  }

  void composeSync(LGFX_Sprite& sprite) override {
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kAccent, kBackground);
    sprite.setTextSize(1);
    sprite.drawString("SYNC", 52, 46);
    sprite.drawCircle(64, 52, 24, kAccent);
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("UPDATING", 40, 100);
  }
};

BeaconTheme g_beacon;
}  // namespace

ThemeRenderer& beaconTheme() { return g_beacon; }
