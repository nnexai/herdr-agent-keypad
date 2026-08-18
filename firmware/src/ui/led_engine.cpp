#include "led_engine.h"

#include <string.h>

#include "../board/board_adapter.h"


LedGrammar& LedEngine::grammar() const {
  return grammar_ != nullptr ? *grammar_ : railEchoGrammar();
}

bool LedEngine::same(const ResolvedLed& left, const ResolvedLed& right) {
  return left.hue == right.hue && left.saturation == right.saturation &&
         left.brightness == right.brightness;
}

bool LedEngine::unhealthy(const char* source_status) {
  return source_status != nullptr &&
         (strcmp(source_status, "stale") == 0 || strcmp(source_status, "offline") == 0 ||
          strcmp(source_status, "unavailable") == 0);
}

bool LedEngine::red(const ResolvedLed& led) {
  return led.brightness != 0 && led.hue == 0 && led.saturation >= 90;
}

void LedEngine::resolve(const LedSegment* segments, size_t count,
                        const RenderState& state, const LedEvents& events) {
  for (uint8_t index = 0; index < kLedCount; ++index) resolved_[index] = {};
  for (size_t segment = 0; segment < count; ++segment) {
    const LedSegment& input = segments[segment];
    for (uint8_t index = 0; index < kLedCount; ++index) {
      if ((input.mask & (static_cast<uint16_t>(1U) << index)) == 0) continue;
      resolved_[index] = {input.hue, input.saturation, input.brightness};
    }
  }

  const bool health = unhealthy(state.source_status);
  bool semantic_high = health;
  for (const RenderState::Slot& slot : state.slots) {
    if (slot.state == TileState::Blocked ||
        (slot.feedback != TileFeedback::Disabled && slot.feedback != TileFeedback::Ready)) {
      semantic_high = true;
    }
  }

  uint8_t high_count = 0;
  for (uint8_t index = 0; index < kLedCount; ++index) {
    ResolvedLed& led = resolved_[index];
    if (led.brightness > kGlobalBrightnessCap) led.brightness = kGlobalBrightnessCap;
    if (events.dim && led.brightness > kDimBrightnessCap) led.brightness = kDimBrightnessCap;
    if (health && red(led) && led.brightness > kHealthBrightnessCap) led.brightness = kHealthBrightnessCap;
    if (!semantic_high && led.brightness > kRestingBrightnessCap) led.brightness = kRestingBrightnessCap;
    if (led.brightness > kRestingBrightnessCap) {
      if (high_count < kHighBrightnessCount) ++high_count;
      else led.brightness = kRestingBrightnessCap;
    }
  }
  if (events.all_off) {
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
  const size_t count = grammar().frame(state, events, now_us, segments, kLedGrammarMaxSegments);
  resolve(segments, count > kLedGrammarMaxSegments ? kLedGrammarMaxSegments : count, state, events);
  apply(board);
}

void LedEngine::allOff(BoardAdapter& board) {
  for (uint8_t index = 0; index < kLedCount; ++index) resolved_[index] = {};
  apply(board);
}
