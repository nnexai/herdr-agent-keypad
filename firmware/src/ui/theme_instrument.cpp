#include <TKeyboardS3Pro.h>

#include <cstdio>
#include <string.h>

#include "theme.h"
#include "theme_common.h"

// Instrument — the ring/bezel display language. Four corner bezel ticks
// (red = health channel, all panels simultaneously), centered discriminator
// header, a ⌀64 state ring whose stroke style is the non-color channel,
// 26 px glyph inside, fused "WORD · SINCE" state line, reserved meta line for
// feedback reasons, centered title last.
//
// Ring strokes are drawn as segmented circles (concentric drawCircle passes
// plus arc gaps via background overdraw) so the stroke-style channel stays
// structural in the native call log; the primitive can be upgraded to
// drawArc on hardware without changing the contract.

namespace {
using namespace theme_common;

constexpr int32_t kCx = 64;
constexpr int32_t kCy = 54;
constexpr int32_t kRadius = 32;  // ⌀64

void drawGapMask(LGFX_Sprite& sprite, int32_t gap_count) {
  // Punch background-colored radial gaps to create dashed/dotted strokes.
  // Gap positions are fixed multiples around the ring; bounded op count.
  static constexpr int8_t kOffsets[][2] = {
      {0, -1}, {1, -1}, {1, 0}, {1, 1}, {0, 1}, {-1, 1}, {-1, 0}, {-1, -1},
  };
  for (int32_t gap = 0; gap < gap_count && gap < 8; ++gap) {
    const int32_t gx = kCx + kOffsets[gap][0] * kRadius;
    const int32_t gy = kCy + kOffsets[gap][1] * kRadius;
    sprite.fillRect(gx - 4, gy - 4, 9, 9, kBackground);
  }
}

// Stroke styles: solid(3px)=3 circles, thin(1.5px)=2 circles, dashed=heavy+8
// gaps, double=2 separated circles, dotted=1 circle+8 gaps, hairline=1 circle.
void drawStateRing(LGFX_Sprite& sprite, TileState state, uint16_t color) {
  switch (state) {
    case TileState::Working:  // solid 3 px
      sprite.drawCircle(kCx, kCy, kRadius, color);
      sprite.drawCircle(kCx, kCy, kRadius - 1, color);
      sprite.drawCircle(kCx, kCy, kRadius - 2, color);
      break;
    case TileState::Idle:  // thin 1.5 px
      sprite.drawCircle(kCx, kCy, kRadius, color);
      sprite.drawCircle(kCx, kCy, kRadius - 1, color);
      break;
    case TileState::Blocked:  // heavy dashed
      sprite.drawCircle(kCx, kCy, kRadius, color);
      sprite.drawCircle(kCx, kCy, kRadius - 1, color);
      sprite.drawCircle(kCx, kCy, kRadius - 2, color);
      drawGapMask(sprite, 8);
      break;
    case TileState::Unseen:  // double ring
      sprite.drawCircle(kCx, kCy, kRadius, color);
      sprite.drawCircle(kCx, kCy, kRadius - 5, color);
      break;
    case TileState::Unknown:  // dotted
      sprite.drawCircle(kCx, kCy, kRadius, color);
      drawGapMask(sprite, 8);
      break;
    case TileState::Settled:  // hairline
      sprite.drawCircle(kCx, kCy, kRadius, color);
      break;
    case TileState::Empty:  // dashed hairline ring
      sprite.drawCircle(kCx, kCy, kRadius, color);
      drawGapMask(sprite, 4);
      break;
    default:  // fence: hairline + cross inside
      sprite.drawCircle(kCx, kCy, kRadius, color);
      break;
  }
}

void drawInnerGlyph(LGFX_Sprite& sprite, TileState state, uint16_t color) {
  // 26 px stroke primitives inside the ring.
  switch (state) {
    case TileState::Blocked:
      sprite.drawLine(kCx - 12, kCy - 12, kCx + 12, kCy + 12, color);
      sprite.drawLine(kCx + 12, kCy - 12, kCx - 12, kCy + 12, color);
      sprite.drawLine(kCx - 11, kCy - 12, kCx + 13, kCy + 12, color);
      sprite.drawLine(kCx + 13, kCy - 12, kCx - 11, kCy + 12, color);
      break;
    case TileState::Unseen:
      sprite.fillCircle(kCx, kCy, 11, color);
      break;
    case TileState::Working:
      sprite.drawLine(kCx - 8, kCy - 12, kCx - 8, kCy + 12, color);
      sprite.drawLine(kCx - 8, kCy - 12, kCx + 12, kCy, color);
      sprite.drawLine(kCx + 12, kCy, kCx - 8, kCy + 12, color);
      break;
    case TileState::Idle:
      sprite.drawCircle(kCx, kCy, 11, color);
      break;
    case TileState::Settled:
      sprite.drawLine(kCx - 10, kCy - 10, kCx - 10, kCy + 10, color);
      sprite.drawLine(kCx - 10, kCy - 10, kCx + 10, kCy - 10, color);
      break;
    case TileState::Unknown:
      sprite.drawCircle(kCx, kCy - 5, 7, color);
      sprite.fillRect(kCx - 1, kCy + 3, 2, 5, color);
      sprite.fillCircle(kCx, kCy + 11, 1, color);
      break;
    case TileState::Empty:
      sprite.fillRect(kCx - 8, kCy - 1, 16, 2, color);
      break;
    default:  // fence cross
      sprite.drawLine(kCx - 12, kCy + 10, kCx + 12, kCy - 10, color);
      sprite.drawLine(kCx - 12, kCy - 10, kCx + 12, kCy + 10, color);
      break;
  }
}

void drawBezelTicks(LGFX_Sprite& sprite, uint16_t color) {
  sprite.fillRect(4, 4, 6, 6, color);
  sprite.fillRect(118, 4, 6, 6, color);
  sprite.fillRect(4, 118, 6, 6, color);
  sprite.fillRect(118, 118, 6, 6, color);
}

class InstrumentTheme final : public ThemeRenderer {
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

    // Health channel: all four bezel ticks red on every panel simultaneously.
    drawBezelTicks(sprite, fence != nullptr ? kDestructive : kSettled);

    if (tile.state == TileState::Empty) {
      drawStateRing(sprite, TileState::Empty, kEmptyEdge);
      drawInnerGlyph(sprite, TileState::Empty, kEmptyEdge);
      sprite.setTextColor(kMetadata, kBackground);
      sprite.drawString("NO AGENT", 34, 112);
      return;
    }

    // Header y:4 centered discriminator.
    ellipsize(row, 15, tile.discriminator);
    sprite.setTextColor(fence != nullptr ? kSettled : kMetadata, kBackground);
    sprite.drawString(row, 22, 5);

    // Ring: feedback recolors the ring (cyan-dashed pending, lime success,
    // red cause); resting uses the per-state stroke style.
    if (feedback != nullptr) {
      if (tile.feedback == TileFeedback::Pending) {
        drawStateRing(sprite, TileState::Blocked, feedback->color);  // dashed cyan
      } else {
        drawStateRing(sprite, TileState::Working, feedback->color);  // solid recolor
      }
      drawInnerGlyph(sprite, tile.state, dim565(content));
    } else {
      const bool low = tile.state == TileState::Blocked && !state.blocked_pulse_high;
      drawStateRing(sprite, tile.state, low ? dim565(content) : content);
      drawInnerGlyph(sprite, tile.state, content);
    }

    // State line y:89 — fused word · since; feedback reason on meta line.
    sprite.setTextColor(feedback != nullptr ? feedback->color : content, kBackground);
    sprite.drawString(feedback != nullptr ? feedback->word : base.word, 22, 89);
    if (fence != nullptr) {
      sprite.setTextColor(kDestructive, kBackground);
      sprite.drawString(fence, 22, 100);
    } else if (feedback != nullptr && tile.feedback != TileFeedback::Pending && tile.feedback != TileFeedback::Success) {
      sprite.setTextColor(feedback->color, kBackground);
      sprite.drawString(feedback->word, 22, 100);
    }

    // Title y:112 centered.
    ellipsize(row, 17, tile.title);
    sprite.setTextColor(fence != nullptr ? kSettled : kPrimary, kBackground);
    sprite.drawString(row, 16, 112);
  }

  void composePanel4(LGFX_Sprite& sprite, const RenderState&) override {
    // Twin gauges with the 75 % warn tick, honest UNAVAILABLE form.
    sprite.fillScreen(kBackground);
    drawBezelTicks(sprite, kSettled);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("CODEX", 46, 5);
    for (uint8_t gauge = 0; gauge < 2; ++gauge) {
      const int32_t cx = 36 + gauge * 56;
      sprite.drawCircle(cx, 58, 22, kSettled);
      // 75 % warn tick.
      sprite.drawLine(cx + 15, 42, cx + 19, 38, kSettled);
      // Hatch: no needle, no value.
      sprite.drawLine(cx - 10, 68, cx + 10, 48, kSettled);
      sprite.drawLine(cx - 10, 62, cx + 10, 42, kSettled);
    }
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("UNAVAILABLE", 30, 100);
    sprite.drawString("NO VALUES", 36, 114);
  }

  void composeMenu(LGFX_Sprite& sprite, const MenuState&) override {
    RenderState rest;
    composePanel4(sprite, rest);
  }

  void composeSync(LGFX_Sprite& sprite) override {
    sprite.fillScreen(kBackground);
    drawBezelTicks(sprite, kSettled);
    sprite.setTextColor(kAccent, kBackground);
    sprite.setTextSize(1);
    sprite.drawString("SYNC", 52, 50);
    sprite.drawCircle(kCx, kCy, kRadius, kAccent);
    sprite.setTextColor(kMetadata, kBackground);
    sprite.drawString("UPDATING", 40, 100);
  }

 private:
  static uint16_t dim565(uint16_t color) {
    const uint16_t r = ((color >> 11) & 0x1F) >> 1;
    const uint16_t g = ((color >> 5) & 0x3F) >> 1;
    const uint16_t b = (color & 0x1F) >> 1;
    return static_cast<uint16_t>((r << 11) | (g << 5) | b);
  }
};

InstrumentTheme g_instrument;
}  // namespace

ThemeRenderer& instrumentTheme() { return g_instrument; }
