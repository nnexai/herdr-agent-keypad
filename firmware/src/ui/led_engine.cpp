#include "led_engine.h"

#include "../board/board_adapter.h"

LedGrammar& LedEngine::grammar() const {
  return grammar_ != nullptr ? *grammar_ : railEchoGrammar();
}

bool LedEngine::same(const ResolvedLed& left, const ResolvedLed& right) {
  return left.hue == right.hue && left.saturation == right.saturation &&
         left.brightness == right.brightness;
}

bool LedEngine::red(const ResolvedLed& led) {
  return led.brightness != 0 && led.hue == 0 && led.saturation >= 90;
}

void LedEngine::resolve(const LedSegment* segments, size_t count,
                        const RenderState& state, const LedEvents& events) {
  for (uint8_t index = 0; index < kLedCount; ++index) resolved_[index] = {};
  for (size_t segment = 0; segment < count; ++segment) {
    const LedSegment& input = segments[segment];
    if (input.hold_cue &&
        (events.all_off ||
         events.semantic_event == LedSemanticEvent::Health ||
         events.semantic_event == LedSemanticEvent::Sync ||
         !ledHoldPresentationAllowed(state, input.hold_slot))) {
      continue;
    }
    for (uint8_t index = 0; index < kLedCount; ++index) {
      if ((input.mask & (static_cast<uint16_t>(1U) << index)) == 0) continue;
      resolved_[index] = {input.hue, input.saturation, input.brightness};
    }
  }

  const bool health = ledPresentationUnhealthy(state);
  bool feedback_active = false;
  bool semantic_high = health;
  for (const RenderState::Slot& slot : state.slots) {
    if (slot.feedback != TileFeedback::Disabled &&
        slot.feedback != TileFeedback::Ready) {
      feedback_active = true;
      semantic_high = true;
    }
    if (slot.state == TileState::Blocked) semantic_high = true;
  }

  uint8_t high_count = 0;
  for (uint8_t index = 0; index < kLedCount; ++index) {
    ResolvedLed& led = resolved_[index];
    if (led.brightness > kGlobalBrightnessCap) {
      led.brightness = kGlobalBrightnessCap;
    }
    if (events.dim && led.brightness > kDimBrightnessCap) {
      led.brightness = kDimBrightnessCap;
    }
    // Grammar health layers request <= 10. Keep the fail-safe clamp except
    // while a later, bounded focus cue is deliberately preempting that layer.
    if (health && !feedback_active && red(led) &&
        led.brightness > kHealthBrightnessCap) {
      led.brightness = kHealthBrightnessCap;
    }
    if (!semantic_high && led.brightness > kRestingBrightnessCap) {
      led.brightness = kRestingBrightnessCap;
    }
    if (led.brightness > kRestingBrightnessCap) {
      if (high_count < kHighBrightnessCount) ++high_count;
      else led.brightness = kRestingBrightnessCap;
    }
  }
  if (events.all_off || state.syncing ||
      ledSemanticEvent(state, events) == LedSemanticEvent::Sync) {
    for (uint8_t index = 0; index < kLedCount; ++index) resolved_[index] = {};
  }
}

void LedEngine::apply(BoardAdapter& board) {
  if (has_previous_) {
    bool changed = false;
    for (uint8_t index = 0; index < kLedCount; ++index) {
      if (!same(previous_[index], resolved_[index])) { changed = true; break; }
    }
    if (!changed) return;
  }

  bool all_off = true;
  for (const ResolvedLed& led : resolved_) if (led.brightness != 0) { all_off = false; break; }
  if (all_off) {
    board.setLeds(0, 0, 0, kAllMask);
  } else {
    bool emitted[kLedCount] = {};
    for (uint8_t index = 0; index < kLedCount; ++index) {
      if (emitted[index]) continue;
      const ResolvedLed value = resolved_[index];
      uint16_t mask = 0;
      for (uint8_t candidate = index; candidate < kLedCount; ++candidate) {
        if (!emitted[candidate] && same(value, resolved_[candidate])) {
          emitted[candidate] = true;
          mask |= static_cast<uint16_t>(1U) << candidate;
        }
      }
      board.setLeds(value.hue, value.saturation, value.brightness, mask);
    }
  }
  memcpy(previous_, resolved_, sizeof(previous_));
  has_previous_ = true;
}

void LedEngine::render(const RenderState& state, const LedEvents& events,
                       uint32_t now_us, BoardAdapter& board) {
  LedSegment segments[kLedGrammarMaxSegments]{};
  const size_t count =
      grammar().frame(state, events, now_us, segments, kLedGrammarMaxSegments);
  resolve(segments, count > kLedGrammarMaxSegments ? kLedGrammarMaxSegments : count,
          state, events);
  apply(board);
}

void LedEngine::allOff(BoardAdapter& board) {
  for (uint8_t index = 0; index < kLedCount; ++index) resolved_[index] = {};
  apply(board);
}
