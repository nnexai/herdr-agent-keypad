#pragma once

#include <stdint.h>
#include <string.h>

#include "render_state.h"

// Shared palette and state/feedback/fence style tables used by every display
// language. Colors match the accepted Phase 02.1 palette; state vocabulary and
// truth rules are identical across themes — geometry is the only difference.

namespace theme_common {

constexpr uint16_t kBackground = 0x0862;   // #0B0F14
constexpr uint16_t kAccent = 0x269D;       // #22D3EE
constexpr uint16_t kPrimary = 0xFFDF;      // #F8FAFC
constexpr uint16_t kMetadata = 0xCEBC;     // #CBD5E1
constexpr uint16_t kDestructive = 0xEA28;  // #EF4444
constexpr uint16_t kBlocked = 0xF3B1;      // #F7768E
constexpr uint16_t kUnseen = 0x7E7F;       // #7DCFFF
constexpr uint16_t kWorking = 0xE56D;      // #E0AF68
constexpr uint16_t kIdle = 0x9E6D;         // #9ECE6A
constexpr uint16_t kSettled = 0x52F1;      // #565F89
constexpr uint16_t kEmptyEdge = 0x21A9;    // #263648

struct StateStyle {
  const char* word;
  uint16_t color;
};

inline StateStyle styleFor(TileState state) {
  switch (state) {
    case TileState::Blocked: return {"BLOCKED", kBlocked};
    case TileState::Unseen: return {"UNSEEN", kUnseen};
    case TileState::Working: return {"WORKING", kWorking};
    case TileState::Idle: return {"IDLE", kIdle};
    case TileState::Settled: return {"SETTLED", kSettled};
    case TileState::Unknown: return {"UNKNOWN", kSettled};
    case TileState::Stale: return {"STALE", kDestructive};
    case TileState::Offline: return {"OFFLINE", kDestructive};
    case TileState::Unavailable: return {"UNAVAILABLE", kDestructive};
    case TileState::Empty:
    default: return {"EMPTY", kEmptyEdge};
  }
}

inline const StateStyle* feedbackStyle(TileFeedback feedback) {
  static constexpr StateStyle kPendingStyle{"PENDING", kAccent};
  static constexpr StateStyle kFocusedStyle{"FOCUSED", kIdle};
  static constexpr StateStyle kRejectedStyle{"REJECTED", kDestructive};
  static constexpr StateStyle kStaleStyle{"STALE", kDestructive};
  static constexpr StateStyle kVanishedStyle{"VANISHED", kDestructive};
  static constexpr StateStyle kOfflineStyle{"OFFLINE", kDestructive};
  static constexpr StateStyle kUncertainStyle{"UNCERTAIN", kWorking};
  static constexpr StateStyle kFailedStyle{"FAILED", kDestructive};
  switch (feedback) {
    case TileFeedback::Pending: return &kPendingStyle;
    case TileFeedback::Success: return &kFocusedStyle;
    case TileFeedback::Rejected: return &kRejectedStyle;
    case TileFeedback::Stale: return &kStaleStyle;
    case TileFeedback::Vanished: return &kVanishedStyle;
    case TileFeedback::Offline: return &kOfflineStyle;
    case TileFeedback::Uncertain: return &kUncertainStyle;
    case TileFeedback::Failed: return &kFailedStyle;
    default: return nullptr;  // Ready / Disabled have no feedback vehicle.
  }
}

inline const char* fenceWord(const char* source_status) {
  if (source_status == nullptr) return nullptr;
  if (strcmp(source_status, "stale") == 0) return "STALE";
  if (strcmp(source_status, "offline") == 0) return "OFFLINE";
  if (strcmp(source_status, "unavailable") == 0) return "UNAVAILABLE";
  return nullptr;
}

inline const char* themeName(ThemeId id) {
  switch (id) {
    case ThemeId::Ledger: return "LEDGER";
    case ThemeId::Beacon: return "BEACON";
    case ThemeId::Instrument: return "INSTRUMENT";
    case ThemeId::SignalEdge:
    default: return "SIGNAL EDGE";
  }
}

inline const char* grammarName(LedGrammarId id) {
  switch (id) {
    case LedGrammarId::Exception: return "EXCEPTION";
    case LedGrammarId::FieldExtension: return "FIELD EXT";
    case LedGrammarId::MeterLamps: return "METER+LAMPS";
    case LedGrammarId::RailEcho:
    default: return "RAIL ECHO";
  }
}

// Bounded tail-ellipsized copy into a caller-owned scratch row. Never
// allocates; `capacity` includes the terminator.
inline void ellipsize(char* destination, size_t capacity, const char* source) {
  if (destination == nullptr || capacity == 0) return;
  const size_t budget = capacity - 1;
  const size_t length = source != nullptr ? strlen(source) : 0;
  if (length <= budget) {
    memcpy(destination, source, length);
    destination[length] = '\0';
    return;
  }
  memcpy(destination, source, budget);
  destination[budget] = '\0';
  if (budget >= 3) {
    destination[budget - 1] = '.';
    destination[budget - 2] = '.';
    destination[budget - 3] = '.';
  }
}

}  // namespace theme_common
