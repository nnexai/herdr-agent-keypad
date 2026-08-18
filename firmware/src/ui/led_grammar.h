#pragma once

#include <stddef.h>
#include <stdint.h>

#include "render_state.h"

class BoardAdapter;

struct LedSegment {
  uint16_t mask = 0;
  uint16_t hue = 0;
  uint8_t saturation = 0;
  uint8_t brightness = 0;
};

struct LedEvents {
  bool menu_open = false;
  bool dim = false;
  bool all_off = false;
};

class LedGrammar {
 public:
  virtual ~LedGrammar() = default;
  virtual size_t frame(const RenderState& state, const LedEvents& events,
                       uint32_t now_us, LedSegment* out, size_t capacity) const = 0;
};

constexpr size_t kLedGrammarMaxSegments = 8;

LedGrammar& railEchoGrammar();
LedGrammar& exceptionChannelGrammar();
LedGrammar& fieldExtensionGrammar();
LedGrammar& meterLampsGrammar();
LedGrammar& ledGrammarById(LedGrammarId id);
