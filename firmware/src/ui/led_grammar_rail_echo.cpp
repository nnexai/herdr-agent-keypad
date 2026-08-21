#include "led_grammar.h"

namespace {
constexpr uint16_t kBacklights = (1U << 1) | (1U << 4) | (1U << 7) | (1U << 10) | (1U << 13);
constexpr uint16_t kKeyMasks[3] = {(1U << 1), (1U << 4), (1U << 7)};
constexpr uint16_t kL13 = 1U << 13;

struct Hsv { uint16_t hue; uint8_t saturation; uint8_t brightness; };

Hsv stateHsv(TileState state, bool pulse_high) {
  switch (state) {
    case TileState::Blocked: return {350, 100, static_cast<uint8_t>(pulse_high ? 40 : 10)};
    case TileState::Unseen: return {195, 100, 30};
    case TileState::Working: return {35, 100, 18};
    case TileState::Idle: return {105, 100, 8};
    case TileState::Settled: return {230, 45, 0};
    case TileState::Unknown: return {230, 55, 0};
    default: return {0, 0, 0};
  }
}

bool active(TileFeedback feedback) {
  return feedback != TileFeedback::Disabled && feedback != TileFeedback::Ready;
}

bool pulseHigh(const RenderState& state, const LedEvents& events,
               TileFeedback feedback, uint32_t now_us) {
  const LedSemanticEvent event = ledSemanticEvent(state, events);
  if (ledFeedbackUsesSemanticPhase(feedback, event)) {
    return (ledSemanticPhase(state, events) & 1U) == 0;
  }
  return ((now_us / 200000UL) & 1U) == 0;
}

Hsv feedbackHsv(const RenderState& state, const LedEvents& events,
                TileFeedback feedback, uint32_t now_us) {
  if (feedback == TileFeedback::Pending) {
    return {185, 100, static_cast<uint8_t>(
        pulseHigh(state, events, feedback, now_us) ? 45 : 0)};
  }
  if (feedback == TileFeedback::Success) {
    return {120, 100, static_cast<uint8_t>(
        pulseHigh(state, events, feedback, now_us) ? 45 : 0)};
  }
  const bool blink = pulseHigh(state, events, feedback, now_us);
  return {0, 100, static_cast<uint8_t>(blink ? 45 : 0)};
}

void add(LedSegment* out, size_t& count, size_t cap, uint16_t mask,
         Hsv value) {
  if (mask == 0 || count >= cap || value.brightness == 0) return;
  out[count++] = {mask, value.hue, value.saturation, value.brightness};
}

class RailEcho final : public LedGrammar {
 public:
  size_t frame(const RenderState& state, const LedEvents& events,
               uint32_t now_us, LedSegment* out, size_t capacity) const override {
    size_t count = 0;
    const bool health = ledPresentationUnhealthy(state);
    if (health) {
      add(out, count, capacity, kBacklights, {0, 100, 10});
    } else {
      for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
        const RenderState::Slot& tile = state.slots[slot];
        if (active(tile.feedback)) continue;
        add(out, count, capacity, kKeyMasks[slot],
            stateHsv(tile.state, state.blocked_pulse_high));
      }
      const LedCodexCue usage = ledCodexCue(state);
      if (usage.visible) {
        add(out, count, capacity, 1U << 10,
            {usage.hue, usage.saturation, usage.brightness});
      }
    }
    for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
      const TileFeedback feedback = state.slots[slot].feedback;
      if (active(feedback)) {
        add(out, count, capacity, kKeyMasks[slot],
            feedbackHsv(state, events, feedback, now_us));
      }
    }
    if ((events.menu_open ||
         ledSemanticEvent(state, events) == LedSemanticEvent::MenuOpen) &&
        !health) {
      add(out, count, capacity, kL13, {180, 100, 25});
    }
    return count;
  }
};
}  // namespace

LedGrammar& railEchoGrammar() {
  static RailEcho grammar;
  return grammar;
}
