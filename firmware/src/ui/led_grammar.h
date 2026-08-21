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
  uint32_t semantic_start_us = 0;
  uint8_t semantic_phase = 0;
};

// Keep the feedback-to-clock mapping in one place.  Stale and Offline are
// health fences rather than focus-result clocks; every other focus result has
// a distinct semantic event so its cue can follow the event-relative phase.
inline LedSemanticEvent ledFeedbackSemanticEvent(TileFeedback feedback) {
  switch (feedback) {
    case TileFeedback::Pending: return LedSemanticEvent::Pending;
    case TileFeedback::Success: return LedSemanticEvent::Focused;
    case TileFeedback::Rejected: return LedSemanticEvent::Rejected;
    case TileFeedback::Vanished: return LedSemanticEvent::Vanished;
    case TileFeedback::Uncertain: return LedSemanticEvent::Uncertain;
    case TileFeedback::Failed: return LedSemanticEvent::Failed;
    case TileFeedback::Stale:
    case TileFeedback::Offline: return LedSemanticEvent::Health;
    default: return LedSemanticEvent::None;
  }
}

inline bool ledFeedbackUsesSemanticPhase(TileFeedback feedback,
                                         LedSemanticEvent event) {
  if (feedback == TileFeedback::Pending && event == LedSemanticEvent::Press) {
    return true;
  }
  return event != LedSemanticEvent::None &&
         event == ledFeedbackSemanticEvent(feedback);
}
// Resolve one feedback segment against its own semantic clock. A physical
// press keeps PENDING on the press event for that frame; result feedback uses
// its mapped event. Prefer the slot clock so simultaneous focus actions never
// share phase; fall back only when the slot has no semantic clock.
inline bool ledSemanticPhase(const RenderState::Slot& slot,
                             const LedEvents& events, uint8_t& phase) {
  const LedSemanticEvent slot_event =
      slot.press_impulse ? LedSemanticEvent::Press
                         : ledFeedbackSemanticEvent(slot.feedback);
  if (!ledFeedbackUsesSemanticPhase(slot.feedback, slot_event)) {
    return false;
  }
  if (slot.semantic_event_epoch != 0 ||
      slot.semantic_event_started_us != 0) {
    phase = slot.semantic_event_phase;
  } else if (events.semantic_event != LedSemanticEvent::None) {
    phase = events.semantic_phase;
  } else {
    phase = slot.feedback_phase;
  }
  return true;
}


inline LedSemanticEvent ledSemanticEvent(const RenderState& state,
                                         const LedEvents& events);
inline int8_t ledSemanticSlot(const RenderState& state,
                              const LedEvents& events) {
  const LedSemanticEvent resolved = ledSemanticEvent(state, events);
  for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
    const RenderState::Slot& candidate = state.slots[slot];
    if (candidate.press_impulse && resolved == LedSemanticEvent::Press) {
      return static_cast<int8_t>(slot);
    }
    const LedSemanticEvent feedback_event =
        ledFeedbackSemanticEvent(candidate.feedback);
    if (feedback_event != LedSemanticEvent::None &&
        resolved == feedback_event) {
      return static_cast<int8_t>(slot);
    }
  }
  return -1;
}
inline uint32_t ledSemanticEpoch(const RenderState& state,
                                 const LedEvents& events) {
  const LedSemanticEvent resolved = ledSemanticEvent(state, events);
  if (events.semantic_epoch != 0 &&
      resolved == events.semantic_event) {
    return events.semantic_epoch;
  }
  const int8_t slot = ledSemanticSlot(state, events);
  if (slot >= 0 && state.slots[slot].semantic_event_epoch != 0) {
    return state.slots[slot].semantic_event_epoch;
  }
  return state.semantic_event_epoch;
}
inline uint32_t ledSemanticStartUs(const RenderState& state,
                                   const LedEvents& events) {
  const LedSemanticEvent resolved = ledSemanticEvent(state, events);
  if (resolved == events.semantic_event && events.semantic_event != LedSemanticEvent::None) {
    return events.semantic_start_us;
  }
  const int8_t slot = ledSemanticSlot(state, events);
  if (slot >= 0 && state.slots[slot].semantic_event_started_us != 0) {
    return state.slots[slot].semantic_event_started_us;
  }
  if (resolved == events.semantic_event &&
      events.semantic_event != LedSemanticEvent::None) {
    return events.semantic_start_us;
  }
  return events.menu_open ? state.semantic_event_started_us : 0;
}

inline LedSemanticEvent ledSemanticEvent(const RenderState& state,
                                         const LedEvents& events) {
  if (state.syncing || events.semantic_event == LedSemanticEvent::Sync) {
    return LedSemanticEvent::Sync;
  }
  if (ledPresentationUnhealthy(state) ||
      events.semantic_event == LedSemanticEvent::Health) {
    return LedSemanticEvent::Health;
  }
  for (const RenderState::Slot& slot : state.slots) {
    if (slot.press_impulse) return LedSemanticEvent::Press;
    const LedSemanticEvent feedback_event =
        ledFeedbackSemanticEvent(slot.feedback);
    if (feedback_event != LedSemanticEvent::None) return feedback_event;
  }
  if (events.semantic_event != LedSemanticEvent::None &&
      events.semantic_event != LedSemanticEvent::MenuOpen) {
    return events.semantic_event;
  }
  if (events.menu_open || events.semantic_event == LedSemanticEvent::MenuOpen) {
    return LedSemanticEvent::MenuOpen;
  }
  if (state.transition_active) return LedSemanticEvent::State;
  return LedSemanticEvent::None;
}

inline uint8_t ledSemanticPhase(const RenderState& state,
                                const LedEvents& events) {
  const LedSemanticEvent resolved = ledSemanticEvent(state, events);
  if (events.semantic_event != LedSemanticEvent::None &&
      resolved == events.semantic_event) {
    return events.semantic_phase;
  }
  const int8_t slot = ledSemanticSlot(state, events);
  if (slot >= 0 && state.slots[slot].semantic_event_epoch != 0) {
    return state.slots[slot].semantic_event_phase;
  }
  if (state.semantic_event_epoch != 0 ||
      state.semantic_event_started_us != 0) {
    return state.semantic_event_phase;
  }
  return state.transition_phase;
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
