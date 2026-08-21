#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

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

struct LedCodexCue {
  bool visible = false;
  bool limit = false;
  uint16_t hue = 0;
  uint8_t saturation = 0;
  uint8_t brightness = 0;
};

inline bool ledHerdrUnhealthy(const char* source_status) {
  return source_status != nullptr &&
         (strcmp(source_status, "stale") == 0 ||
          strcmp(source_status, "offline") == 0 ||
          strcmp(source_status, "unavailable") == 0);
}

inline bool ledCodexUnhealthy(const CodexRenderView& codex) {
  return codex.source_state != CodexSourceState::Current;
}

inline bool ledPresentationUnhealthy(const RenderState& state) {
  return ledHerdrUnhealthy(state.source_status) ||
         ledCodexUnhealthy(state.codex);
}

inline LedCodexCue ledCodexCue(const RenderState& state) {
  const CodexRenderView& codex = state.codex;
  if (codex.source_state != CodexSourceState::Current) return {};
  if (codex.reached_limit == 1) return {true, true, 0, 100, 25};
  if (codex.primary < 0 || codex.primary > 100) return {};
  if (codex.primary >= 75) return {true, false, 35, 100, 18};
  return {true, false, 180, 100, 12};
}

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
