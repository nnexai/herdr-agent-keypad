#include "led_grammar.h"

#include <string.h>

namespace {
constexpr uint16_t kKeyMasks[3] = {(1U << 0) | (1U << 1) | (1U << 2),
                                   (1U << 3) | (1U << 4) | (1U << 5),
                                   (1U << 6) | (1U << 7) | (1U << 8)};
constexpr uint16_t kCenterMasks[3] = {(1U << 1), (1U << 4), (1U << 7)};
constexpr uint16_t kUsageMask = (1U << 9) | (1U << 10) | (1U << 11);
constexpr uint16_t kHealthPair = (1U << 12) | (1U << 13);

void add(LedSegment* out, size_t& count, size_t cap, uint16_t mask,
         uint16_t hue, uint8_t saturation, uint8_t brightness) {
  if (mask == 0 || count >= cap || brightness == 0) return;
  out[count++] = {mask, hue, saturation, brightness};
}

uint8_t level(TileState state) {
  switch (state) {
    case TileState::Blocked: return 38;
    case TileState::Unseen: return 28;
    case TileState::Working: return 16;
    case TileState::Idle: return 8;
    default: return 0;
  }
}

uint16_t hue(TileState state) {
  switch (state) {
    case TileState::Blocked: return 350;
    case TileState::Unseen: return 195;
    case TileState::Working: return 35;
    case TileState::Idle: return 105;
    default: return 230;
  }
}

bool unhealthy(const char* status) {
  return status != nullptr && (strcmp(status, "stale") == 0 ||
                               strcmp(status, "offline") == 0 ||
                               strcmp(status, "unavailable") == 0);
}

class FieldExtension final : public LedGrammar {
 public:
  size_t frame(const RenderState& state, const LedEvents&, uint32_t now_us,
               LedSegment* out, size_t capacity) const override {
    size_t count = 0;
    if (unhealthy(state.source_status)) {
      add(out, count, capacity, kHealthPair, 0, 100, 10);
      return count;
    }
    for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
      const RenderState::Slot& tile = state.slots[slot];
      const uint16_t key = kKeyMasks[slot];
      if (tile.feedback == TileFeedback::Pending) {
        const uint8_t step = static_cast<uint8_t>((now_us / 300000UL) % 3U);
        add(out, count, capacity, static_cast<uint16_t>(1U << (slot * 3U + step)),
            185, 100, 45);
        continue;
      }
      if (tile.feedback == TileFeedback::Success || tile.feedback == TileFeedback::Rejected ||
          tile.feedback == TileFeedback::Stale || tile.feedback == TileFeedback::Vanished ||
          tile.feedback == TileFeedback::Offline || tile.feedback == TileFeedback::Uncertain ||
          tile.feedback == TileFeedback::Failed) {
        const uint16_t feedback_hue = tile.feedback == TileFeedback::Success ? 120 : 0;
        add(out, count, capacity, key, feedback_hue, 100,
            static_cast<uint8_t>(tile.feedback == TileFeedback::Success ? 45 : 30));
        continue;
      }
      const uint8_t brightness = level(tile.state);
      if (brightness == 0) continue;
      const uint16_t color = hue(tile.state);
      add(out, count, capacity, kCenterMasks[slot], color, 100, brightness);
      add(out, count, capacity, static_cast<uint16_t>(key & ~kCenterMasks[slot]), color, 100,
          static_cast<uint8_t>((brightness * 60U) / 100U));
    }
    (void)kUsageMask;  // Usage is intentionally dark until Phase 3 data exists.
    return count;
  }
};
}  // namespace

LedGrammar& fieldExtensionGrammar() {
  static FieldExtension grammar;
  return grammar;
}
