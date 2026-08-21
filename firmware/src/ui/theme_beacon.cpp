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

uint16_t blend565(uint16_t base, uint16_t color, uint8_t numerator, uint8_t denominator = 64) {
  const int32_t base_r = (base >> 11) & 0x1F;
  const int32_t base_g = (base >> 5) & 0x3F;
  const int32_t base_b = base & 0x1F;
  const int32_t color_r = (color >> 11) & 0x1F;
  const int32_t color_g = (color >> 5) & 0x3F;
  const int32_t color_b = color & 0x1F;
  const uint16_t r = static_cast<uint16_t>(base_r + (color_r - base_r) * numerator / denominator);
  const uint16_t g = static_cast<uint16_t>(base_g + (color_g - base_g) * numerator / denominator);
  const uint16_t b = static_cast<uint16_t>(base_b + (color_b - base_b) * numerator / denominator);
  return static_cast<uint16_t>((r << 11) | (g << 5) | b);
}

uint16_t scale565(uint16_t color, uint8_t numerator, uint8_t denominator = 64) {
  return blend565(0, color, numerator, denominator);
}

bool activeField(TileState state) {
  return state == TileState::Blocked || state == TileState::Unseen || state == TileState::Working;
}

void drawField(LGFX_Sprite& sprite, uint16_t hue, uint8_t phase) {
  // Ordered-dithered radial falloff. One bounded pass over the visible field
  // avoids the hard concentric bullseye produced by nested solid circles.
  static constexpr uint8_t kBayer4[4][4] = {
      {0, 8, 2, 10},
      {12, 4, 14, 6},
      {3, 11, 1, 9},
      {15, 7, 13, 5},
  };
  static constexpr uint8_t kFieldScale[8] = {64, 56, 48, 40, 48, 56, 64, 56};
  const uint16_t field_hue = scale565(hue, kFieldScale[phase & 7U]);
  static constexpr int8_t kHaloRadius[8] = {0, 24, 26, 28, 30, 28, 26, 24};
  const int32_t halo = kHaloRadius[phase & 7U];
  const int32_t radius = 58;
  const int32_t radius_squared = radius * radius;
  for (int32_t y = 0; y < 96; ++y) {
    const int32_t dy = y - 52;
    for (int32_t x = 6; x < 123; ++x) {
      const int32_t dx = x - 64;
      const int32_t distance_squared = dx * dx + dy * dy;
      if (distance_squared > radius_squared) continue;
      const uint32_t alpha_sixteenths =
          static_cast<uint32_t>(radius_squared - distance_squared) * 240U /
          static_cast<uint32_t>(radius_squared);
      uint8_t alpha = static_cast<uint8_t>(alpha_sixteenths >> 4);
      if (kBayer4[y & 3][x & 3] < (alpha_sixteenths & 0x0F)) ++alpha;
      sprite.drawPixel(x, y, blend565(kBackground, field_hue, alpha));
    }
  }
  if (halo != 0) {
    sprite.drawCircle(64, 52, halo, scale565(hue, 24));
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
    case TileState::Working:  // filled triangle
      sprite.fillTriangle(cx - 14, cy - 20, cx - 14, cy + 20, cx + 20, cy, color);
      break;
    case TileState::Idle:  // thin ring
      sprite.drawCircle(cx, cy, 20, color);
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

static constexpr int8_t kSpinnerPoints[][2] = {
    {0, -22}, {8, -20}, {16, -16}, {20, -8},
    {22, 0}, {20, 8}, {16, 16}, {8, 20},
    {0, 22}, {-8, 20}, {-16, 16}, {-20, 8},
    {-22, 0}, {-20, -8}, {-16, -16}, {-8, -20},
};

void drawPendingSpinner(LGFX_Sprite& sprite, uint16_t color, uint8_t phase) {
  const uint8_t start = static_cast<uint8_t>((phase * 2U) & 0x0FU);
  for (uint8_t segment = 0; segment < 12; ++segment) {
    const uint8_t from = static_cast<uint8_t>((start + segment) & 0x0F);
    const uint8_t to = static_cast<uint8_t>((from + 1) & 0x0F);
    sprite.drawLine(64 + kSpinnerPoints[from][0], 52 + kSpinnerPoints[from][1],
                    64 + kSpinnerPoints[to][0], 52 + kSpinnerPoints[to][1], color);
    sprite.fillCircle(64 + kSpinnerPoints[from][0], 52 + kSpinnerPoints[from][1], 1, color);
  }
  const uint8_t marker = static_cast<uint8_t>((start + 12) & 0x0F);
  sprite.fillCircle(64 + kSpinnerPoints[marker][0], 52 + kSpinnerPoints[marker][1], 2, color);
}

void drawFeedbackGlyph(LGFX_Sprite& sprite, TileFeedback feedback, uint16_t color,
                       uint8_t phase) {
  const int32_t cx = 64;
  const int32_t cy = 52;
  switch (feedback) {
    case TileFeedback::Pending:
      drawPendingSpinner(sprite, color, phase);
      break;
    case TileFeedback::Success:
      sprite.drawLine(cx - 14, cy, cx - 4, cy + 12, color);
      sprite.drawLine(cx - 4, cy + 12, cx + 16, cy - 12, color);
      if (phase != 0) sprite.drawCircle(cx, cy, 24 + static_cast<int32_t>(phase), color);
      break;
    case TileFeedback::Uncertain:
      sprite.fillRect(cx - 1, cy - 16, 3, 20, color);
      sprite.fillCircle(cx, cy + 12, 2, color);
      break;
    default:
      sprite.drawLine(cx - 14, cy - 14, cx + 14, cy + 14, color);
      sprite.drawLine(cx + 14, cy - 14, cx - 14, cy + 14, color);
      break;
  }
}

static constexpr int8_t kCodexRingPoints[][2] = {
    {0, -19}, {7, -18}, {13, -13}, {18, -7},
    {19, 0}, {18, 7}, {13, 13}, {7, 18},
    {0, 19}, {-7, 18}, {-13, 13}, {-18, 7},
    {-19, 0}, {-18, -7}, {-13, -13}, {-7, -18},
};

void drawCodexRing(LGFX_Sprite& sprite, int32_t center_x, int32_t center_y,
                   int32_t radius, int16_t value, uint16_t color, bool broken) {
  sprite.drawCircle(center_x, center_y, radius, color);
  if (value >= 0) {
    const uint8_t segments = static_cast<uint8_t>((value * 16) / 100);
    for (uint8_t segment = 0; segment < segments; ++segment) {
      const uint8_t next = static_cast<uint8_t>((segment + 1) & 0x0F);
      const int32_t x0 = center_x + kCodexRingPoints[segment][0] * radius / 19;
      const int32_t y0 = center_y + kCodexRingPoints[segment][1] * radius / 19;
      const int32_t x1 = center_x + kCodexRingPoints[next][0] * radius / 19;
      const int32_t y1 = center_y + kCodexRingPoints[next][1] * radius / 19;
      sprite.drawLine(x0, y0, x1, y1, color);
    }
  } else {
    for (uint8_t point = 0; point < 16; point += 3) {
      sprite.fillCircle(center_x + kCodexRingPoints[point][0] * radius / 19,
                        center_y + kCodexRingPoints[point][1] * radius / 19, 1, color);
    }
  }
  if (broken) {
    sprite.drawLine(center_x - radius, center_y - radius, center_x + radius,
                    center_y + radius, color);
    sprite.drawLine(center_x + radius, center_y - radius, center_x - radius,
                    center_y + radius, color);
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

    if (tile.state == TileState::Empty) {
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
      sprite.drawString("EMPTY", centeredX("EMPTY"), 88);
      sprite.drawString("NO AGENT", centeredX("NO AGENT"), 96);
    } else {
      if (fence == nullptr && feedback == nullptr && activeField(tile.state)) {
        const bool blocked = tile.state == TileState::Blocked;
        const uint8_t blocked_scale = static_cast<uint8_t>(
            12U + static_cast<uint8_t>(state.blocked_phase * 6U));
        drawField(sprite, blocked ? scale565(base.color, blocked_scale) : base.color, phase);
      } else if (feedback != nullptr && activeField(tile.state)) {
        drawField(sprite, scale565(base.color, 12), phase);
      }

      if (tile.press_impulse) {
        // The beacon halo is the physical-detection cue; it carries no
        // request/result word and therefore cannot imply FOCUSED.
        sprite.drawCircle(64, 52, 28, kAccent);
        sprite.fillCircle(64, 52, 3, kAccent);
        sprite.setTextColor(content, kBackground);
        sprite.drawString(base.word, centeredX(base.word), 76);
      } else if (feedback != nullptr) {
        drawFeedbackGlyph(sprite, tile.feedback, feedback->color, phase);
        sprite.setTextColor(feedback->color, kBackground);
        sprite.drawString(feedback->word, centeredX(feedback->word), 76);
      } else {
        drawCenterGlyph(sprite, tile.state, content);
        sprite.setTextColor(content, kBackground);
        sprite.drawString(base.word, centeredX(base.word), 73);
      }

      sprite.fillRect(0, 96, 128, 32, kBackground);
      sprite.setTextColor(fence != nullptr ? kSettled : kMetadata, kBackground);
      char since[6] = {};
      ellipsize(since, sizeof(since), tile.since);
      sprite.drawString(since, rightAlignedX(since), 8);
      ellipsize(row, 17, tile.title);
      sprite.setTextColor(fence != nullptr ? kSettled : kPrimary, kBackground);
      sprite.drawString(row, centeredX(row), 100);
      ellipsize(row, 17, tile.discriminator);
      sprite.setTextColor(fence != nullptr ? kSettled : kMetadata, kBackground);
      sprite.drawString(row, centeredX(row), 112);
    }

    if (fence != nullptr) {
      sprite.fillRect(0, 88, 128, 8, kDestructive);
      sprite.setTextColor(kBackground, kDestructive);
      sprite.drawString(fence, centeredX(fence), 88);
      if (strcmp(fence, "OFFLINE") == 0) sprite.fillRect(0, 0, 128, 2, kDestructive);
    }
  }

  void composePanel4(LGFX_Sprite& sprite, const RenderState& state) override {
    const CodexRenderView& codex = state.codex;
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kPrimary, kBackground);
    sprite.drawString("CODEX", centeredX("CODEX"), 4);
    drawCodexLimitHeader(sprite, codex, 94, 4);
    const uint16_t ring_color = codexHasLimit(codex)
                                    ? kDestructive
                                    : codex.source_state == CodexSourceState::Current
                                          ? kAccent
                                          : kSettled;
    const bool broken = codex.source_state == CodexSourceState::Stale ||
                        codexIsOffline(codex) ||
                        codex.source_state == CodexSourceState::AuthRequired;
    drawCodexRing(sprite, 18, 34, 8, codexValue(codex, true), ring_color, broken);
    drawCodexRing(sprite, 18, 54, 8, codexValue(codex, false), ring_color,
                  codex.source_state == CodexSourceState::HostOffline ||
                      codex.source_state == CodexSourceState::AuthRequired);
    if (codex.source_state == CodexSourceState::HostOffline) {
      sprite.fillRect(4, 16, 120, 2, kDestructive);
    }
    char primary[14] = {};
    char secondary[14] = {};
    formatCodexLabeledPercent(primary, sizeof(primary), "5H", codexValue(codex, true));
    formatCodexLabeledPercent(secondary, sizeof(secondary), "WEEK", codexValue(codex, false));
    sprite.setTextColor(codexValueColor(codex), kBackground);
    sprite.drawString(primary, 34, 30);
    sprite.drawString(secondary, 34, 50);
    drawCodexMetaText(sprite, codex, 0, 70, 0, 86, true);
    drawCodexStateText(sprite, codex, 0, 114, true);
    const bool motion_active = codex.source_state == CodexSourceState::Current &&
                               !state.syncing &&
                               (state.transition_active || state.ambient_phase != 0);
    if (motion_active && codexValue(codex, true) >= 0) {
      const uint8_t phase = (state.transition_active
                                 ? static_cast<uint8_t>(state.transition_phase * 2U)
                                 : state.ambient_phase) & 7U;
      sprite.fillCircle(18 + static_cast<int32_t>(phase % 8U), 24, 1, ring_color);
    }
  }

  void composeMenu(LGFX_Sprite& sprite, const MenuState& menu) override {
    sprite.fillScreen(kBackground);
    drawMenuPage(sprite, menu, MenuVisual::Beacon);
    if (menu.presentation_progress < 3 &&
        menu.presentation_cause != MenuPresentationCause::None) {
      const int32_t cue_x =
          64 + static_cast<int32_t>(menu.presentation_direction) *
                   (3 - menu.presentation_progress) * 2;
      sprite.drawCircle(cue_x, 56, 8, kAccent);
    }
  }

  void composeSync(LGFX_Sprite& sprite) override {
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kAccent, kBackground);
    sprite.setTextSize(1);
    sprite.drawCircle(64, 52, 24, kAccent);
    sprite.drawString("SYNC", centeredX("SYNC"), 48);
  }

  uint8_t ambientTick(uint32_t now_us) override {
    (void)now_us;
    return 0x07;
  }

  uint32_t ambientPeriodUs() const override { return 66668UL; }
};

BeaconTheme g_beacon;
}  // namespace

ThemeRenderer& beaconTheme() { return g_beacon; }
