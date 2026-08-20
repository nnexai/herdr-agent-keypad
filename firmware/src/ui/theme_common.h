#pragma once

#include <cstdio>
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

constexpr const char* kMenuHint = "TURN:SEL CLICK:CLOSE";
constexpr int32_t kMenuHintX = 4;
constexpr int32_t kSafeRight = 124;
constexpr int32_t kGlyphCellWidth = 6;

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
  if (source == nullptr) source = "";
  const size_t budget = capacity - 1;
  const size_t length = strlen(source);
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

inline int32_t rightAlignedX(const char* text, int32_t right = kSafeRight) {
  const size_t length = text != nullptr ? strlen(text) : 0;
  return right - static_cast<int32_t>(length) * kGlyphCellWidth;
}

inline int32_t centeredX(const char* text) {
  const size_t length = text != nullptr ? strlen(text) : 0;
  return (128 - static_cast<int32_t>(length) * kGlyphCellWidth) / 2;
}

inline const char* codexStateWord(CodexSourceState state) {
  switch (state) {
    case CodexSourceState::Current: return "CURRENT";
    case CodexSourceState::Stale: return "STALE";
    case CodexSourceState::AuthRequired: return "AUTH REQUIRED";
    case CodexSourceState::CodexOffline: return "CODEX OFFLINE";
    case CodexSourceState::HostOffline: return "HOST OFFLINE";
    case CodexSourceState::Unavailable:
    default: return "UNAVAILABLE";
  }
}

inline bool codexHasLimit(const CodexRenderView& view) {
  return view.reached_limit == 1;
}

inline bool codexClearsValues(const CodexRenderView& view) {
  return view.source_state == CodexSourceState::AuthRequired ||
         view.source_state == CodexSourceState::Unavailable;
}

inline bool codexVeiled(const CodexRenderView& view) {
  return view.source_state == CodexSourceState::Stale ||
         view.source_state == CodexSourceState::CodexOffline ||
         view.source_state == CodexSourceState::HostOffline;
}

inline bool codexNeedsHatch(const CodexRenderView& view) {
  return view.source_state == CodexSourceState::Unavailable ||
         view.source_state == CodexSourceState::Stale;
}

inline bool codexIsOffline(const CodexRenderView& view) {
  return view.source_state == CodexSourceState::CodexOffline ||
         view.source_state == CodexSourceState::HostOffline;
}

inline int16_t codexValue(const CodexRenderView& view, bool primary) {
  if (codexClearsValues(view)) return -1;
  return primary ? view.primary : view.secondary;
}

inline void formatCodexPercent(char* destination, size_t capacity, int16_t value) {
  if (destination == nullptr || capacity == 0) return;
  if (value < 0) {
    ellipsize(destination, capacity, "N/A");
    return;
  }
  if (value > 100) value = 100;
  snprintf(destination, capacity, "%d%%", static_cast<int>(value));
}

inline void formatCodexText(char* destination, size_t capacity, const char* source,
                            const char* fallback) {
  if (destination == nullptr || capacity == 0) return;
  const char* value = source != nullptr && source[0] != '\0' ? source : fallback;
  ellipsize(destination, capacity, value);
}

inline void formatCodexReset(char* destination, size_t capacity,
                             const CodexRenderView& view) {
  formatCodexText(destination, capacity,
                  codexClearsValues(view) ? nullptr : view.reset_text, "RESET N/A");
}

inline void formatCodexAge(char* destination, size_t capacity,
                           const CodexRenderView& view) {
  formatCodexText(destination, capacity, view.observation_age, "AGE N/A");
}

inline void formatCodexLabeledPercent(char* destination, size_t capacity,
                                      const char* label, int16_t value) {
  if (destination == nullptr || capacity == 0) return;
  char percent[8] = {};
  formatCodexPercent(percent, sizeof(percent), value);
  snprintf(destination, capacity, "%s %s", label, percent);
}

inline uint16_t codexValueColor(const CodexRenderView& view) {
  return codexVeiled(view) || view.source_state == CodexSourceState::Unavailable
             ? kSettled
             : kMetadata;
}

inline uint16_t codexStateColor(const CodexRenderView& view) {
  return view.source_state == CodexSourceState::Current ? kMetadata : kDestructive;
}

inline void drawCodexRowsText(LGFX_Sprite& sprite, const CodexRenderView& view,
                              int32_t label_x, int32_t value_right, int32_t primary_y,
                              int32_t secondary_y) {
  char primary[8] = {};
  char secondary[8] = {};
  formatCodexPercent(primary, sizeof(primary), codexValue(view, true));
  formatCodexPercent(secondary, sizeof(secondary), codexValue(view, false));
  sprite.setTextColor(codexValueColor(view), kBackground);
  sprite.drawString("5H", label_x, primary_y);
  sprite.drawString(primary, rightAlignedX(primary, value_right), primary_y);
  sprite.drawString("WEEK", label_x, secondary_y);
  sprite.drawString(secondary, rightAlignedX(secondary, value_right), secondary_y);
}

inline void drawCodexMetaText(LGFX_Sprite& sprite, const CodexRenderView& view,
                              int32_t reset_x, int32_t reset_y, int32_t age_x,
                              int32_t age_y, bool centered = false) {
  char reset[19] = {};
  char age[19] = {};
  formatCodexReset(reset, sizeof(reset), view);
  formatCodexAge(age, sizeof(age), view);
  sprite.setTextColor(codexValueColor(view), kBackground);
  sprite.drawString(reset, centered ? centeredX(reset) : reset_x, reset_y);
  sprite.drawString(age, centered ? centeredX(age) : age_x, age_y);
}

inline void drawCodexStateText(LGFX_Sprite& sprite, const CodexRenderView& view,
                               int32_t x, int32_t y, bool centered) {
  const char* word = codexStateWord(view.source_state);
  sprite.setTextColor(codexStateColor(view), kBackground);
  sprite.drawString(word, centered ? centeredX(word) : x, y);
}

inline void drawHatchedTrack(LGFX_Sprite& sprite, int32_t x, int32_t y, int32_t w,
                             int32_t h, uint16_t color) {
  sprite.drawRect(x, y, w, h, color);
  for (int32_t start = x + 2; start < x + w - 2; start += 7) {
    const int32_t end = start + 5 < x + w - 1 ? start + 5 : x + w - 1;
    sprite.drawLine(start, y + h - 2, end, y + 1, color);
  }
}

inline void drawCodexTrack(LGFX_Sprite& sprite, int32_t x, int32_t y, int32_t w,
                           int32_t h, int16_t value, uint16_t fill_color,
                           uint16_t outline_color) {
  if (value < 0) {
    drawHatchedTrack(sprite, x, y, w, h, outline_color);
    return;
  }
  if (value > 100) value = 100;
  sprite.drawRect(x, y, w, h, outline_color);
  const int32_t fill_width = (w * value) / 100;
  if (fill_width > 0) sprite.fillRect(x, y, fill_width, h, fill_color);
}

inline void drawCodexTrackVeil(LGFX_Sprite& sprite, const CodexRenderView& view,
                               int32_t x, int32_t y, int32_t w, int32_t h) {
  if (codexNeedsHatch(view)) {
    for (int32_t start = x + 3; start < x + w - 2; start += 9) {
      const int32_t end = start + 5 < x + w - 1 ? start + 5 : x + w - 1;
      sprite.drawLine(start, y + h - 2, end, y + 1, kSettled);
    }
  }
  if (codexIsOffline(view)) {
    const int32_t mid = x + w / 2;
    sprite.drawLine(mid - 6, y + h / 2, mid - 2, y + h / 2, kDestructive);
    sprite.drawLine(mid + 2, y + h / 2, mid + 6, y + h / 2, kDestructive);
  }
}

inline void drawCodexLimitHeader(LGFX_Sprite& sprite, const CodexRenderView& view,
                                 int32_t x, int32_t y) {
  if (!codexHasLimit(view)) return;
  sprite.setTextColor(kDestructive, kBackground);
  sprite.drawString("LIMIT", x, y);
}

}  // namespace theme_common
