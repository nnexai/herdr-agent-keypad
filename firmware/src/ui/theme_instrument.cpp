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

static constexpr int8_t kRingPoints[][2] = {
    {0, -32}, {12, -30}, {23, -23}, {30, -12},
    {32, 0}, {30, 12}, {23, 23}, {12, 30},
    {0, 32}, {-12, 30}, {-23, 23}, {-30, 12},
    {-32, 0}, {-30, -12}, {-23, -23}, {-12, -30},
};

void drawGapMask(LGFX_Sprite& sprite, int32_t gap_count) {
  // Punch evenly spaced background gaps on the ring itself.
  const int32_t step = 16 / gap_count;
  for (int32_t gap = 0; gap < gap_count; ++gap) {
    const int32_t point = gap * step;
    const int32_t gx = kCx + kRingPoints[point][0];
    const int32_t gy = kCy + kRingPoints[point][1];
    sprite.fillRect(gx - 2, gy - 2, 5, 5, kBackground);
  }
}

void drawSymmetricBlockedGaps(LGFX_Sprite& sprite, uint8_t phase) {
  // Four quarter-turn positions guarantee equal opposing arcs for every
  // phase. Two adjacent scheduler phases intentionally share a pose.
  const uint8_t rotation = static_cast<uint8_t>(phase % 4U);
  for (uint8_t gap = 0; gap < 4; ++gap) {
    const uint8_t point = static_cast<uint8_t>(rotation + gap * 4U);
    const int32_t gx = kCx + kRingPoints[point][0];
    const int32_t gy = kCy + kRingPoints[point][1];
    sprite.fillRect(gx - 2, gy - 2, 5, 5, kBackground);
  }
}

void drawDottedRing(LGFX_Sprite& sprite, uint16_t color) {
  for (const auto& point : kRingPoints) {
    sprite.fillCircle(kCx + point[0], kCy + point[1], 1, color);
  }
}

// Stroke styles: solid(3px), thin(2px), heavy dashed, double, discrete
// dotted points, hairline, and dashed hairline.
void drawStateRing(LGFX_Sprite& sprite, TileState state, uint16_t color,
                   uint8_t phase, bool pulse_high) {
  switch (state) {
    case TileState::Working:
      sprite.drawCircle(kCx, kCy, kRadius, color);
      sprite.drawCircle(kCx, kCy, kRadius - 1, color);
      sprite.drawCircle(kCx, kCy, kRadius - 2, color);
      break;
    case TileState::Idle:
      sprite.drawCircle(kCx, kCy, kRadius, color);
      sprite.drawCircle(kCx, kCy, kRadius - 1, color);
      break;
    case TileState::Blocked:
      sprite.drawCircle(kCx, kCy, kRadius, color);
      sprite.drawCircle(kCx, kCy, kRadius - 1, color);
      sprite.drawCircle(kCx, kCy, kRadius - 2, color);
      drawSymmetricBlockedGaps(sprite, phase);
      break;
    case TileState::Unseen:
      sprite.drawCircle(kCx, kCy, kRadius, color);
      sprite.drawCircle(kCx, kCy, kRadius - 5, color);
      break;
    case TileState::Unknown:
      drawDottedRing(sprite, color);
      break;
    case TileState::Settled:
      sprite.drawCircle(kCx, kCy, kRadius, color);
      break;
    case TileState::Empty:
      sprite.drawCircle(kCx, kCy, kRadius, color);
      drawGapMask(sprite, 4);
      break;
    default:
      sprite.drawCircle(kCx, kCy, kRadius, color);
      break;
  }
  if (phase != 0 && (state == TileState::Working || state == TileState::Unseen)) {
    const uint8_t point = static_cast<uint8_t>((phase * 2U) & 0x0FU);
    sprite.fillCircle(kCx + kRingPoints[point][0], kCy + kRingPoints[point][1], 2, color);
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
      sprite.fillTriangle(kCx - 8, kCy - 12, kCx - 8, kCy + 12, kCx + 12, kCy, color);
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
  sprite.drawLine(4, 4, 10, 4, color);
  sprite.drawLine(4, 4, 4, 10, color);
  sprite.drawLine(117, 4, 123, 4, color);
  sprite.drawLine(123, 4, 123, 10, color);
  sprite.drawLine(4, 117, 4, 123, color);
  sprite.drawLine(4, 123, 10, 123, color);
  sprite.drawLine(117, 123, 123, 123, color);
  sprite.drawLine(123, 117, 123, 123, color);
}

void drawUsageGauge(LGFX_Sprite& sprite, int32_t track_y, const char* label) {
  sprite.setTextColor(kMetadata, kBackground);
  sprite.drawString(label, 8, track_y - 10);
  sprite.drawString("N/A", rightAlignedX("N/A", 120), track_y - 10);
  sprite.drawRect(8, track_y, 112, 10, kSettled);
  for (int32_t start = 10; start < 117; start += 7) {
    const int32_t end = start + 6 < 117 ? start + 6 : 117;
    sprite.drawLine(start, track_y + 7, end, track_y + 7 - (end - start), kSettled);
  }
  // Fixed 75% warning mark from the accepted Instrument gauge language.
  sprite.fillRect(92, track_y - 1, 2, 12, kBlocked);
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
    const bool motion_active = fence == nullptr && !state.syncing &&
                               (state.transition_active || state.ambient_phase != 0);
    const uint8_t phase = tile.feedback == TileFeedback::Pending
                              ? static_cast<uint8_t>(tile.feedback_phase & 7U)
                              : (motion_active
                                     ? (state.transition_active
                                            ? static_cast<uint8_t>(state.transition_phase * 2U)
                                            : state.ambient_phase) & 7U
                                     : 0);
    char row[18] = {};

    // Health channel: all four bezel ticks red on every panel simultaneously.
    drawBezelTicks(sprite, fence != nullptr ? kDestructive : kSettled);

    if (tile.state == TileState::Empty) {
      drawStateRing(sprite, TileState::Empty, kEmptyEdge, 0, true);
      drawInnerGlyph(sprite, TileState::Empty, kEmptyEdge);
      sprite.setTextColor(kMetadata, kBackground);
      sprite.drawString("EMPTY", centeredX("EMPTY"), 80);
      sprite.drawString("NO AGENT", centeredX("NO AGENT"), 89);
      if (fence != nullptr) {
        sprite.setTextColor(kDestructive, kBackground);
        sprite.drawString(fence, centeredX(fence), 100);
      }
      return;
    }

    // Header y:4 centered discriminator.
    ellipsize(row, 15, tile.discriminator);
    sprite.setTextColor(fence != nullptr ? kSettled : kMetadata, kBackground);
    sprite.drawString(row, centeredX(row), 5);

    // Ring: the press impulse marks detection on the local gauge only.
    if (tile.press_impulse) {
      drawStateRing(sprite, TileState::Working, kAccent, 0,
                    state.blocked_pulse_high);
      sprite.drawCircle(kCx, kCy, 14, kAccent);
      sprite.fillCircle(kCx, kCy - 14, 2, kAccent);
    } else if (feedback != nullptr) {
      if (tile.feedback == TileFeedback::Pending) {
        drawStateRing(sprite, TileState::Blocked, feedback->color, phase,
                      state.blocked_pulse_high);
        sprite.drawCircle(kCx, kCy, 12, feedback->color);
        sprite.fillCircle(kCx, kCy - 12 + static_cast<int32_t>(phase % 3U), 2, feedback->color);
      } else if (tile.feedback == TileFeedback::Success) {
        drawStateRing(sprite, TileState::Working, feedback->color, phase,
                      state.blocked_pulse_high);
        sprite.drawLine(kCx - 10, kCy, kCx - 3, kCy + 8, feedback->color);
        sprite.drawLine(kCx - 3, kCy + 8, kCx + 12, kCy - 9, feedback->color);
      } else {
        drawStateRing(sprite, TileState::Working, feedback->color, 0,
                      state.blocked_pulse_high);
        sprite.drawLine(kCx - 10, kCy - 10, kCx + 10, kCy + 10, feedback->color);
        sprite.drawLine(kCx + 10, kCy - 10, kCx - 10, kCy + 10, feedback->color);
      }
    } else {
      const bool low = tile.state == TileState::Blocked && !state.blocked_pulse_high;
      const uint8_t ring_phase = tile.state == TileState::Blocked
                                     ? state.blocked_phase : phase;
      drawStateRing(sprite, tile.state,
                    low ? dim565(content) : content, ring_phase,
                    state.blocked_pulse_high);
      drawInnerGlyph(sprite, tile.state, content);
    }
      if (holdMicPermitted(state, tile, fence)) {
        if (tile.hold_active_owner) {
          drawHoldMic(sprite, kCx, kCy, kAccent, true, phase);
        } else if (tile.hold_candidate && tile.hold_threshold_qualified) {
          drawHoldMic(sprite, kCx, kCy, kAccent, false, phase);
        }
      }

    // State line remains the underlying state during the physical impulse;
    // feedback words begin only on the following complete frame.
    const bool feedback_text = feedback != nullptr && !tile.press_impulse;
    sprite.setTextColor(feedback_text ? feedback->color : content, kBackground);
    sprite.drawString(feedback_text ? feedback->word : base.word,
                      centeredX(feedback_text ? feedback->word : base.word), 89);
    if (!feedback_text) {
      ellipsize(row, 6, tile.since);
      sprite.drawString(row, rightAlignedX(row), 89);
    }
    if (fence != nullptr) {
      sprite.setTextColor(kDestructive, kBackground);
      sprite.drawString(fence, centeredX(fence), 100);
    }

    // Title y:112 centered.
    ellipsize(row, 17, tile.title);
    sprite.setTextColor(fence != nullptr ? kSettled : kPrimary, kBackground);
    sprite.drawString(row, centeredX(row), 112);
  }

  void composePanel4(LGFX_Sprite& sprite, const RenderState& state) override {
    if (state.usage_provider == UsageProvider::Copilot) {
      drawCopilotPanel(sprite, state.copilot, true);
      return;
    }
    if (state.usage_provider == UsageProvider::None) {
      drawUnavailableUsagePanel(sprite);
      return;
    }
    const CodexRenderView& codex = state.codex;
    sprite.fillScreen(kBackground);
    const uint16_t bezel_color =
        codex.source_state == CodexSourceState::Current && !codexHasLimit(codex)
            ? kSettled
            : kDestructive;
    drawBezelTicks(sprite, bezel_color);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("CODEX", centeredX("CODEX"), 4);
    if (codexHasLimit(codex) &&
        codex.source_state != CodexSourceState::Current) {
      drawCodexLimitHeader(sprite, codex, 94, 4);
    }

    drawCodexRowsText(sprite, codex, 8, 120, 22, 42);
    const uint16_t gauge_color =
        codex.source_state == CodexSourceState::Current
            ? (codexHasLimit(codex) ? kDestructive : kAccent)
            : kSettled;
    drawCodexTrack(sprite, 8, 32, 112, 8, codexValue(codex, true),
                   gauge_color, kSettled);
    drawCodexTrack(sprite, 8, 52, 112, 8, codexValue(codex, false),
                   gauge_color, kSettled);
    const bool motion_active = codex.source_state == CodexSourceState::Current &&
                               !state.syncing &&
                               (state.transition_active || state.ambient_phase != 0);
    if (motion_active) {
      const uint8_t phase = (state.transition_active
                                 ? static_cast<uint8_t>(state.transition_phase * 2U)
                                 : state.ambient_phase) & 7U;
      const int32_t x = 10 + static_cast<int32_t>(phase) * 13;
      if (codexValue(codex, true) >= 0) sprite.fillRect(x, 31, 2, 10, gauge_color);
      if (codexValue(codex, false) >= 0) sprite.fillRect(x, 51, 2, 10, gauge_color);
    }
    const uint16_t warning_color = codexHasLimit(codex) ? kDestructive : kBlocked;
    sprite.fillRect(92, 31, 2, 10, warning_color);
    sprite.fillRect(92, 51, 2, 10, warning_color);
    if (codex.source_state == CodexSourceState::AuthRequired) {
      sprite.drawLine(112, 8, 124, 20, kDestructive);
      sprite.drawLine(124, 8, 112, 20, kDestructive);
    }

    drawCodexMetaText(sprite, codex, 0, 70, 0, 86, true);
    if (codexHasLimit(codex) &&
        codex.source_state == CodexSourceState::Current) {
      sprite.setTextColor(kDestructive, kBackground);
      sprite.drawString("LIMIT", centeredX("LIMIT"), 114);
    } else {
      drawCodexStateText(sprite, codex, 0, 114, true);
    }
  }

  void composeMenu(LGFX_Sprite& sprite, const MenuState& menu) override {
    sprite.fillScreen(kBackground);
    drawBezelTicks(sprite, kSettled);
    drawMenuPage(sprite, menu, MenuVisual::Instrument);
    if (menu.presentation_progress < 3 &&
        menu.presentation_cause != MenuPresentationCause::None) {
      const int32_t cue_x =
          16 + static_cast<int32_t>(menu.presentation_direction) *
                   (3 - menu.presentation_progress) * 2;
      sprite.drawLine(cue_x, 43, cue_x + 96, 43, kAccent);
    }
  }

  void composeSync(LGFX_Sprite& sprite) override {
    sprite.fillScreen(kBackground);
    drawBezelTicks(sprite, kSettled);
    sprite.setTextColor(kAccent, kBackground);
    sprite.setTextSize(1);
    sprite.drawCircle(kCx, kCy, kRadius, kAccent);
    sprite.drawString("SYNC", centeredX("SYNC"), 50);
  }

  uint8_t ambientTick(uint32_t now_us) override {
    (void)now_us;
    return 0x07;
  }

  uint32_t ambientPeriodUs() const override { return 33334UL; }

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
