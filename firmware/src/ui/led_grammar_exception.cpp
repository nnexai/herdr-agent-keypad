#include "led_grammar.h"

namespace {
constexpr uint16_t kKeyMasks[3] = {(1U << 1), (1U << 4), (1U << 7)};
constexpr uint16_t kAboveKey = (1U << 0) | (1U << 3) | (1U << 6) | (1U << 9);
constexpr uint16_t kL13 = 1U << 13;

bool active(TileFeedback feedback) {
  return feedback != TileFeedback::Disabled && feedback != TileFeedback::Ready;
}

void add(LedSegment* out, size_t& count, size_t cap, uint16_t mask,
         uint16_t hue, uint8_t saturation, uint8_t brightness) {
  if (mask == 0 || count >= cap || brightness == 0) return;
  out[count++] = {mask, hue, saturation, brightness};
}

bool feedbackHigh(const RenderState::Slot& tile, const LedEvents& events,
                  uint32_t now_us) {
  uint8_t phase = 0;
  if (ledSemanticPhase(tile, events, phase)) return (phase & 1U) == 0;
  return ((now_us / 150000UL) & 1U) == 0;
}

uint8_t stateBrightness(TileState state, bool pulse_high) {
  switch (state) {
    case TileState::Blocked: return pulse_high ? 30 : 8;
    case TileState::Unseen: return 20;
    default: return 0;
  }
}

class ExceptionChannel final : public LedGrammar {
 public:
  size_t frame(const RenderState& state, const LedEvents& events,
               uint32_t now_us, LedSegment* out, size_t capacity) const override {
    size_t count = 0;
    const bool health = ledPresentationUnhealthy(state);
    if (health) {
      add(out, count, capacity, kAboveKey, 0, 100, 10);
    } else {
      const LedCodexCue usage = ledCodexCue(state);
      if (usage.visible) {
        add(out, count, capacity, 1U << 10, usage.hue,
            usage.saturation, usage.brightness);
      }
    }
    for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
      const RenderState::Slot& tile = state.slots[slot];
      if (active(tile.feedback)) {
        const bool blink = feedbackHigh(tile, events, now_us);
        const uint16_t hue = tile.feedback == TileFeedback::Pending ? 185 :
                             tile.feedback == TileFeedback::Success ? 120 : 0;
        add(out, count, capacity, kKeyMasks[slot], hue, 100,
            static_cast<uint8_t>(blink ? 30 : 0));
        continue;
      }
      const uint8_t brightness = stateBrightness(tile.state, state.blocked_pulse_high);
      const uint16_t hue = tile.state == TileState::Unseen ? 195 : 350;
      add(out, count, capacity, kKeyMasks[slot], hue, 100, brightness);
    }
    if (events.menu_open ||
        ledSemanticEvent(state, events) == LedSemanticEvent::MenuOpen) {
      add(out, count, capacity, kL13, 180, 100, 25);
    }
    return count;
  }
};
}  // namespace

LedGrammar& exceptionChannelGrammar() {
  static ExceptionChannel grammar;
  return grammar;
}
