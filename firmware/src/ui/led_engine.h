#pragma once

#include <stddef.h>
#include <stdint.h>

#include "led_grammar.h"

class BoardAdapter;

struct ResolvedLed {
  uint16_t hue = 0;
  uint8_t saturation = 0;
  uint8_t brightness = 0;
};

class LedEngine final {
 public:
  static constexpr uint8_t kLedCount = 14;
  static constexpr uint16_t kAllMask = 0x3FFF;
  static constexpr uint8_t kGlobalBrightnessCap = 45;
  static constexpr uint8_t kRestingBrightnessCap = 25;
  static constexpr uint8_t kHighBrightnessCount = 6;
  static constexpr uint8_t kHealthBrightnessCap = 10;
  static constexpr uint8_t kDimBrightnessCap = 8;

  void setGrammar(LedGrammar& grammar) { grammar_ = &grammar; }
  LedGrammar& grammar() const;
  void render(const RenderState& state, const LedEvents& events,
              uint32_t now_us, BoardAdapter& board);
  void allOff(BoardAdapter& board);
  const ResolvedLed& resolved(uint8_t index) const { return resolved_[index < kLedCount ? index : 0]; }

 private:
  static bool same(const ResolvedLed& left, const ResolvedLed& right);
  static bool unhealthy(const char* source_status);
  static bool red(const ResolvedLed& led);
  void resolve(const LedSegment* segments, size_t count,
               const RenderState& state, const LedEvents& events);
  void apply(BoardAdapter& board);

  LedGrammar* grammar_ = nullptr;
  ResolvedLed resolved_[kLedCount]{};
  ResolvedLed previous_[kLedCount]{};
  bool has_previous_ = false;
};
