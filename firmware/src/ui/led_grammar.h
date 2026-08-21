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

inline bool ledPresentationUnhealthy(const RenderState& state);

enum class LedSemanticEvent : uint8_t {
  None = 0,
  Blocked,
  Press,
  Pending,
  Focused,
  Rejected,
  Vanished,
  Uncertain,
  Failed,
  MenuOpen,
  Health,
  Sync,
  State,
};

// Transient controls and the bounded semantic presentation clock shared by
// the display and LED paths.  The epoch identifies the semantic start; the
// phase is deliberately grammar-neutral, so each grammar may choose its own
// physical choreography without drifting to a second event clock.
struct LedEvents {
  bool menu_open = false;
  bool dim = false;
  bool all_off = false;
  LedSemanticEvent semantic_event = LedSemanticEvent::None;
  uint32_t semantic_epoch = 0;
  uint8_t semantic_phase = 0;
};

inline uint32_t ledSemanticEpoch(const RenderState& state,
                                 const LedEvents& events) {
  return events.semantic_epoch != 0 ? events.semantic_epoch
                                    : state.semantic_event_epoch;
}

inline LedSemanticEvent ledSemanticEvent(const RenderState& state,
                                         const LedEvents& events) {
  if (events.semantic_event != LedSemanticEvent::None) {
    return events.semantic_event;
  }
  if (state.syncing) return LedSemanticEvent::Sync;
  for (const RenderState::Slot& slot : state.slots) {
    if (slot.press_impulse) return LedSemanticEvent::Press;
    switch (slot.feedback) {
      case TileFeedback::Pending: return LedSemanticEvent::Pending;
      case TileFeedback::Success: return LedSemanticEvent::Focused;
      case TileFeedback::Rejected: return LedSemanticEvent::Rejected;
      case TileFeedback::Stale:
      case TileFeedback::Offline: return LedSemanticEvent::Health;
      case TileFeedback::Vanished: return LedSemanticEvent::Vanished;
      case TileFeedback::Uncertain: return LedSemanticEvent::Uncertain;
      case TileFeedback::Failed: return LedSemanticEvent::Failed;
      default: break;
    }
  }
  if (ledPresentationUnhealthy(state)) return LedSemanticEvent::Health;
  for (const RenderState::Slot& slot : state.slots) {
    if (slot.state == TileState::Blocked) return LedSemanticEvent::Blocked;
  }
  if (events.menu_open) return LedSemanticEvent::MenuOpen;
  if (state.transition_active) return LedSemanticEvent::State;
  return LedSemanticEvent::None;
}

inline uint8_t ledSemanticPhase(const RenderState& state,
                                const LedEvents& events) {
  return events.semantic_event != LedSemanticEvent::None ||
                 events.semantic_epoch != 0
             ? events.semantic_phase
             : state.transition_phase;
}

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
