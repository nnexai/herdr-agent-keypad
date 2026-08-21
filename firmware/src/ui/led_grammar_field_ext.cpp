#include "led_grammar.h"

namespace {
constexpr uint16_t kKeyMasks[3] = {(1U << 0) | (1U << 1) | (1U << 2),
                                   (1U << 3) | (1U << 4) | (1U << 5),
                                   (1U << 6) | (1U << 7) | (1U << 8)};
constexpr uint16_t kCenterMasks[3] = {(1U << 1), (1U << 4), (1U << 7)};
constexpr uint16_t kUsageMask = (1U << 9) | (1U << 10) | (1U << 11);
constexpr uint16_t kHealthPair = (1U << 12) | (1U << 13);
constexpr uint16_t kL13 = 1U << 13;

void add(LedSegment* out, size_t& count, size_t cap, uint16_t mask,
         uint16_t hue, uint8_t saturation, uint8_t brightness) {
  if (mask == 0 || count >= cap || brightness == 0) return;
  out[count++] = {mask, hue, saturation, brightness};
}

uint8_t level(TileState state, bool pulse_high) {
  switch (state) {
    case TileState::Blocked: return pulse_high ? 38 : 8;
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

bool addFeedback(const RenderState::Slot& tile, const LedEvents& events,
                 uint8_t slot, LedSegment* out, size_t& count,
                 size_t capacity) {
  const uint16_t key = kKeyMasks[slot];
  if (tile.feedback == TileFeedback::Pending) {
    uint8_t phase = 0;
    const bool semantic = ledSemanticPhase(tile, events, phase);
    const uint8_t step = semantic ? phase % 3U : tile.feedback_phase % 3U;
    const uint16_t pending_mask =
        static_cast<uint16_t>(1U << (slot * 3U + step));
    add(out, count, capacity, pending_mask, 185, 100, 45);
    return true;
  }
  if (tile.feedback == TileFeedback::Disabled ||
      tile.feedback == TileFeedback::Ready) {
    return false;
  }
  uint8_t phase = 0;
  const bool semantic = ledSemanticPhase(tile, events, phase);
  const bool high = !semantic || (phase & 1U) == 0;
  const uint16_t feedback_hue =
      tile.feedback == TileFeedback::Success ? 120 : 0;
  const uint8_t feedback_brightness =
      tile.feedback == TileFeedback::Success ? 45 : 30;
  add(out, count, capacity, key, feedback_hue, 100,
      static_cast<uint8_t>(high ? feedback_brightness : 0));
  return true;
}
class FieldExtension final : public LedGrammar {
 public:
  size_t frame(const RenderState& state, const LedEvents& events,
               uint32_t now_us, LedSegment* out, size_t capacity) const override {
    (void)now_us;
    size_t count = 0;
    const bool health = ledPresentationUnhealthy(state);
    if (health) {
      const uint8_t health_brightness = state.blocked_pulse_high ? 10 : 3;
      add(out, count, capacity, kHealthPair, 0, 100, health_brightness);
      for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
        addFeedback(state.slots[slot], events, slot, out, count, capacity);
      }
      return count;
    }
    for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
      const RenderState::Slot& tile = state.slots[slot];
      const uint16_t key = kKeyMasks[slot];
      if (addFeedback(tile, events, slot, out, count, capacity)) {
        continue;
      }
      const uint8_t tile_brightness = level(tile.state, state.blocked_pulse_high);
      if (tile_brightness == 0) continue;
      const uint16_t color = hue(tile.state);
      add(out, count, capacity, kCenterMasks[slot], color, 100,
          tile_brightness);
      add(out, count, capacity,
          static_cast<uint16_t>(key & ~kCenterMasks[slot]), color, 100,
          static_cast<uint8_t>((tile_brightness * 60U) / 100U));
    }
    const LedCodexCue usage = ledCodexCue(state);
    if (usage.visible) {
      add(out, count, capacity, kUsageMask, usage.hue, usage.saturation,
          usage.brightness);
    }
    if ((events.menu_open ||
         ledSemanticEvent(state, events) == LedSemanticEvent::MenuOpen) &&
        !health) {
      add(out, count, capacity, kL13, 180, 100, 25);
    }
    return count;
  }
};
}  // namespace

LedGrammar& fieldExtensionGrammar() {
  static FieldExtension grammar;
  return grammar;
}
