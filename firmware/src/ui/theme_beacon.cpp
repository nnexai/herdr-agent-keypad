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

void drawField(LGFX_Sprite& sprite, uint16_t hue) {
  // Ordered-dithered radial falloff. One bounded pass over the visible field
  // avoids the hard concentric bullseye produced by nested solid circles.
  static constexpr uint8_t kBayer4[4][4] = {
      {0, 8, 2, 10},
      {12, 4, 14, 6},
      {3, 11, 1, 9},
      {15, 7, 13, 5},
  };
  static constexpr int32_t kRadius = 58;
  static constexpr int32_t kRadiusSquared = kRadius * kRadius;
  for (int32_t y = 0; y < 96; ++y) {
    const int32_t dy = y - 52;
    for (int32_t x = 6; x < 123; ++x) {
      const int32_t dx = x - 64;
      const int32_t distance_squared = dx * dx + dy * dy;
      if (distance_squared > kRadiusSquared) continue;
      const uint32_t alpha_sixteenths =
          static_cast<uint32_t>(kRadiusSquared - distance_squared) * 240U /
          static_cast<uint32_t>(kRadiusSquared);
      uint8_t alpha = static_cast<uint8_t>(alpha_sixteenths >> 4);
      if (kBayer4[y & 3][x & 3] < (alpha_sixteenths & 0x0F)) ++alpha;
      sprite.drawPixel(x, y, blend565(kBackground, hue, alpha));
    }
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

void drawPendingSpinner(LGFX_Sprite& sprite, uint16_t color, bool phase_high) {
  const uint8_t start = phase_high ? 0 : 8;
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

void drawFeedbackGlyph(LGFX_Sprite& sprite, TileFeedback feedback, uint16_t color, bool phase_high) {
  const int32_t cx = 64;
  const int32_t cy = 52;
  switch (feedback) {
    case TileFeedback::Pending:
      drawPendingSpinner(sprite, color, phase_high);
      break;
    case TileFeedback::Success:
      sprite.drawLine(cx - 14, cy, cx - 4, cy + 12, color);
      sprite.drawLine(cx - 4, cy + 12, cx + 16, cy - 12, color);
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

void drawCodexRing(LGFX_Sprite& sprite, int32_t radius, int16_t value,
                   uint16_t color, bool broken) {
  sprite.drawCircle(64, 40, radius, color);
  if (value >= 0) {
    const uint8_t segments = static_cast<uint8_t>((value * 16) / 100);
    for (uint8_t segment = 0; segment < segments; ++segment) {
      const uint8_t next = static_cast<uint8_t>((segment + 1) & 0x0F);
      const int32_t scale = radius;
      const int32_t x0 = 64 + kCodexRingPoints[segment][0] * scale / 19;
      const int32_t y0 = 40 + kCodexRingPoints[segment][1] * scale / 19;
      const int32_t x1 = 64 + kCodexRingPoints[next][0] * scale / 19;
      const int32_t y1 = 40 + kCodexRingPoints[next][1] * scale / 19;
      sprite.drawLine(x0, y0, x1, y1, color);
    }
  } else {
    for (uint8_t point = 0; point < 16; point += 3) {
      sprite.fillCircle(64 + kCodexRingPoints[point][0] * radius / 19,
                        40 + kCodexRingPoints[point][1] * radius / 19, 1, color);
    }
  }
  if (broken) {
    sprite.drawLine(64 - radius, 40 - radius, 64 + radius, 40 + radius, color);
    sprite.drawLine(64 + radius, 40 - radius, 64 - radius, 40 + radius, color);
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
      sprite.drawString("NO AGENT", centeredX("NO AGENT"), 96);
    } else {
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
        drawFeedbackGlyph(sprite, tile.feedback, feedback->color, state.blocked_pulse_high);
        sprite.setTextColor(feedback->color, kBackground);
        sprite.drawString(feedback->word, centeredX(feedback->word), 76);
        if (tile.feedback == TileFeedback::Pending) {
          sprite.setTextColor(kMetadata, kBackground);
          sprite.drawString("FOCUS SENT", centeredX("FOCUS SENT"), 88);
        }
      } else {
        drawCenterGlyph(sprite, tile.state, content);
        sprite.setTextColor(content, kBackground);
        sprite.drawString(base.word, centeredX(base.word), 73);
      }

      // Opaque title strip prevents the radial field from bleeding behind text.
      sprite.fillRect(0, 96, 128, 32, kBackground);
      // Title strip y:100..122 — one title line + one identity line, centered.
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
      // Bottom fence line with the reason word; offline adds a red top
      // hairline on all panels.
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
    if (codexHasLimit(codex) &&
        codex.source_state != CodexSourceState::Current) {
      drawCodexLimitHeader(sprite, codex, 94, 4);
    }

    const uint16_t ring_color = codexHasLimit(codex)
                                    ? kDestructive
                                    : codex.source_state == CodexSourceState::Current
                                          ? kAccent
                                          : kSettled;
    const bool broken = codex.source_state == CodexSourceState::Stale ||
                        codexIsOffline(codex) ||
                        codex.source_state == CodexSourceState::AuthRequired;
    drawCodexRing(sprite, 19, codexValue(codex, true), ring_color, broken);
    drawCodexRing(sprite, 12, codexValue(codex, false), ring_color,
                  codex.source_state == CodexSourceState::HostOffline);
    if (codex.source_state == CodexSourceState::AuthRequired) {
      sprite.drawLine(45, 21, 83, 59, kDestructive);
      sprite.drawLine(83, 21, 45, 59, kDestructive);
    } else if (codex.source_state == CodexSourceState::HostOffline) {
      sprite.fillRect(4, 16, 120, 2, kDestructive);
    }

    char primary[14] = {};
    char secondary[14] = {};
    formatCodexLabeledPercent(primary, sizeof(primary), "5H",
                              codexValue(codex, true));
    formatCodexLabeledPercent(secondary, sizeof(secondary), "WEEK",
                              codexValue(codex, false));
    sprite.setTextColor(codexValueColor(codex), kBackground);
    sprite.drawString(primary, centeredX(primary), 30);
    sprite.drawString(secondary, centeredX(secondary), 50);
    drawCodexMetaText(sprite, codex, 0, 70, 0, 86, true);

    if (codexHasLimit(codex) &&
        codex.source_state == CodexSourceState::Current) {
      sprite.setTextColor(kDestructive, kBackground);
      sprite.drawString("LIMIT", centeredX("LIMIT"), 40);
    }
    drawCodexStateText(sprite, codex, 0, 114, true);
  }

  void composeMenu(LGFX_Sprite& sprite, const MenuState& menu) override {
    sprite.fillScreen(kBackground);
    drawMenuPage(sprite, menu, MenuVisual::Beacon);
  }

  void composeSync(LGFX_Sprite& sprite) override {
    sprite.fillScreen(kBackground);
    sprite.setTextColor(kAccent, kBackground);
    sprite.setTextSize(1);
    sprite.drawCircle(64, 52, 24, kAccent);
    sprite.drawString("SYNC", centeredX("SYNC"), 48);
  }
};

BeaconTheme g_beacon;
}  // namespace

ThemeRenderer& beaconTheme() { return g_beacon; }
