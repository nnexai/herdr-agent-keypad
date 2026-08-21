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

enum class MenuVisual : uint8_t {
  SignalEdge = 0,
  Ledger,
  Beacon,
  Instrument,
};

inline bool menuCentered(MenuVisual visual) {
  return visual == MenuVisual::Beacon || visual == MenuVisual::Instrument;
}

inline int32_t menuLabelX(MenuVisual visual) {
  if (visual == MenuVisual::Ledger) return 6;
  if (visual == MenuVisual::SignalEdge) return 16;
  return 0;
}

inline void drawMenuTitle(LGFX_Sprite& sprite, MenuVisual visual,
                          const char* title) {
  sprite.setTextSize(1);
  sprite.setTextColor(kPrimary, kBackground);
  sprite.drawString(title, menuCentered(visual) ? centeredX(title)
                                                : menuLabelX(visual),
                    4);
  if (visual == MenuVisual::Ledger) {
    sprite.drawLine(4, 18, 124, 18, kSettled);
  }
}

inline const char* menuRootLabel(uint8_t row) {
  static constexpr const char* kLabels[] = {
      "THEME", "LEDS", "BRIGHTNESS", "HEALTH", "ABOUT", "CLOSE"};
  return row < 6 ? kLabels[row] : "";
}

inline const char* menuRootValue(const MenuState& menu, uint8_t row,
                                 char* brightness, size_t capacity) {
  switch (row) {
    case 0: return themeName(menu.theme_stored);
    case 1: return grammarName(menu.grammar_stored);
    case 2:
      snprintf(brightness, capacity, "%u%%",
               static_cast<unsigned>(menu.brightness_stored));
      return brightness;
    default: return "";
  }
}

inline void drawMenuRootFooter(LGFX_Sprite& sprite, MenuVisual visual) {
  sprite.setTextColor(kMetadata, kBackground);
  if (visual == MenuVisual::SignalEdge) {
    sprite.drawString("TURN:SEL", 16, 102);
    sprite.drawString("CLICK:OPEN", 16, 114);
    return;
  }
  const char* hint = "TURN:SEL CLICK:OPEN";
  sprite.drawString(hint, visual == MenuVisual::Ledger ? 6 : centeredX(hint),
                    112);
}

inline void drawMenuRoot(LGFX_Sprite& sprite, const MenuState& menu,
                         MenuVisual visual) {
  drawMenuTitle(sprite, visual, "MENU");
  const uint8_t start = menu.viewport_start > 3 ? 3 : menu.viewport_start;
  static constexpr int32_t kRows[] = {30, 54, 78};
  for (uint8_t visible = 0; visible < 3; ++visible) {
    const uint8_t row = static_cast<uint8_t>(start + visible);
    const int32_t y = kRows[visible];
    const bool selected = row == menu.cursor;
    const char* label = menuRootLabel(row);
    char brightness[5] = {};
    const char* value = menuRootValue(menu, row, brightness,
                                      sizeof(brightness));

    if (visual == MenuVisual::SignalEdge && selected) {
      sprite.fillRect(12, y - 10, 112, 24, kAccent);
    }
    if (visual == MenuVisual::Ledger) {
      sprite.drawLine(4, y + 13, 124, y + 13, kSettled);
    }
    const uint16_t foreground =
        selected && visual == MenuVisual::SignalEdge ? kBackground
                                                     : (selected ? kAccent
                                                                 : kMetadata);
    const uint16_t background =
        selected && visual == MenuVisual::SignalEdge ? kAccent : kBackground;
    sprite.setTextColor(foreground, background);

    if (visual == MenuVisual::Beacon) {
      char line[19] = {};
      if (value[0] != '\0') {
        snprintf(line, sizeof(line), "%s %s", label, value);
      } else {
        ellipsize(line, sizeof(line), label);
      }
      sprite.drawString(selected ? ">" : " ", 4, y);
      sprite.drawString(line, centeredX(line), y);
      continue;
    }

    const int32_t cursor_x = visual == MenuVisual::Ledger ? 6 : 16;
    const int32_t label_x = visual == MenuVisual::Ledger ? 14 : 24;
    sprite.drawString(selected ? ">" : " ", cursor_x, y);
    sprite.drawString(label, label_x, y);
    if (value[0] != '\0') {
      sprite.setTextColor(
          selected && visual == MenuVisual::SignalEdge ? kBackground
                                                       : kPrimary,
          background);
      sprite.drawString(value, rightAlignedX(value, 120), y);
    }
  }
  drawMenuRootFooter(sprite, visual);
}

inline void drawMenuEditFooter(LGFX_Sprite& sprite, MenuVisual visual,
                               int32_t turn_y = 102,
                               int32_t save_y = 114) {
  sprite.setTextSize(1);
  sprite.setTextColor(kMetadata, kBackground);
  const char* turn = "TURN:CHANGE";
  const char* save = "CLICK:SAVE";
  const int32_t x = visual == MenuVisual::SignalEdge
                        ? 16
                        : (visual == MenuVisual::Ledger ? 6 : centeredX(turn));
  sprite.drawString(turn, x, turn_y);
  sprite.drawString(save,
                    visual == MenuVisual::SignalEdge
                        ? 16
                        : (visual == MenuVisual::Ledger ? 6 : centeredX(save)),
                    save_y);
}

inline void drawMenuValuePreview(LGFX_Sprite& sprite, const MenuState& menu,
                                 MenuVisual visual) {
  const bool theme_page = menu.page == MenuPage::Theme;
  const char* title = theme_page ? "THEME" : "LEDS";
  const char* candidate =
      theme_page ? themeName(menu.theme_candidate)
                 : grammarName(menu.grammar_candidate);
  drawMenuTitle(sprite, visual, title);
  sprite.setTextColor(kAccent, kBackground);
  sprite.drawString(candidate,
                    menuCentered(visual) ? centeredX(candidate)
                                         : menuLabelX(visual),
                    30);
  if (visual == MenuVisual::Ledger) {
    sprite.drawLine(4, 43, 124, 43, kAccent);
  } else if (visual == MenuVisual::Beacon) {
    sprite.drawCircle(64, 56, 8, kSettled);
  } else if (visual == MenuVisual::Instrument) {
    sprite.drawLine(16, 43, 112, 43, kSettled);
  } else {
    sprite.drawRect(12, 20, 112, 24, kAccent);
  }
  drawMenuEditFooter(sprite, visual);
}

inline void drawBrightnessTrack(LGFX_Sprite& sprite, MenuVisual visual,
                                uint8_t brightness) {
  const int32_t x = visual == MenuVisual::Ledger ? 6
                    : visual == MenuVisual::Beacon ? 12
                                                   : 16;
  const int32_t width = visual == MenuVisual::Ledger ? 114 : 104;
  sprite.drawRect(x, 52, width, 8, kSettled);
  uint8_t steps = brightness / 10;
  if (steps < 1) steps = 1;
  if (steps > 10) steps = 10;
  const int32_t segment = (width - 11) / 10;
  for (uint8_t index = 0; index < steps; ++index) {
    sprite.fillRect(x + 2 + index * (segment + 1), 54, segment, 4, kAccent);
  }
}

inline void drawMenuBrightness(LGFX_Sprite& sprite, const MenuState& menu,
                               MenuVisual visual) {
  drawMenuTitle(sprite, visual, "BRIGHTNESS");
  char value[5] = {};
  snprintf(value, sizeof(value), "%u%%",
           static_cast<unsigned>(menu.brightness_candidate));
  sprite.setTextSize(2);
  sprite.setTextColor(kAccent, kBackground);
  const int32_t large_x =
      (128 - static_cast<int32_t>(strlen(value)) * 12) / 2;
  sprite.drawString(value, large_x, 24);
  sprite.setTextSize(1);
  drawBrightnessTrack(sprite, visual, menu.brightness_candidate);
  drawMenuEditFooter(sprite, visual, 102, 114);
}

inline const char* diagnosticStateWord(const char* state, bool link,
                                       bool codex) {
  if (state == nullptr) return link ? "OFFLINE" : "UNAVAILABLE";
  if (link) return strcmp(state, "current") == 0 ? "OK" : "OFFLINE";
  if (strcmp(state, "current") == 0) return "CURRENT";
  if (strcmp(state, "stale") == 0) return "STALE";
  if (strcmp(state, "auth_required") == 0 && codex) return "AUTH REQUIRED";
  if (strcmp(state, "offline") == 0 ||
      strcmp(state, "codex_offline") == 0 ||
      strcmp(state, "host_offline") == 0) {
    return "OFFLINE";
  }
  return "UNAVAILABLE";
}

inline const char* diagnosticAge(const char* age) {
  if (age == nullptr || age[0] == '\0' || strcmp(age, "AGE N/A") == 0) {
    return "N/A";
  }
  return strncmp(age, "AGE ", 4) == 0 ? age + 4 : age;
}

inline bool allowedMenuError(const char* error) {
  if (error == nullptr || strlen(error) != 6 || error[0] != 'E' ||
      error[1] != '-') {
    return false;
  }
  uint16_t value = 0;
  for (uint8_t index = 2; index < 6; ++index) {
    if (error[index] < '0' || error[index] > '9') return false;
    value = static_cast<uint16_t>(value * 10 +
                                  static_cast<uint16_t>(error[index] - '0'));
  }
  return value >= 2400 && value <= 2410;
}

inline const char* diagnosticVersion(const char* version) {
  return version == nullptr || version[0] == '\0' ||
                 strcmp(version, "UNAVAL") == 0
             ? "N/A"
             : version;
}

inline void drawMenuDetailRow(LGFX_Sprite& sprite, MenuVisual visual,
                              const char* label, const char* source,
                              int32_t y) {
  char value[14] = {};
  ellipsize(value, sizeof(value), source);
  sprite.setTextColor(kMetadata, kBackground);
  if (visual == MenuVisual::Beacon) {
    char line[21] = {};
    snprintf(line, sizeof(line), "%s %s", label, value);
    sprite.drawString(line, centeredX(line), y);
    return;
  }
  const int32_t label_x = visual == MenuVisual::Ledger ? 6 : 12;
  sprite.drawString(label, label_x, y);
  sprite.setTextColor(kPrimary, kBackground);
  sprite.drawString(value, rightAlignedX(value, 120), y);
  if (visual == MenuVisual::Ledger) {
    sprite.drawLine(4, y + 13, 124, y + 13, kSettled);
  }
}

inline void drawMenuBackFooter(LGFX_Sprite& sprite, MenuVisual visual) {
  const char* footer = "CLICK:BACK";
  sprite.setTextColor(kMetadata, kBackground);
  sprite.drawString(footer,
                    visual == MenuVisual::Ledger
                        ? 6
                        : (visual == MenuVisual::SignalEdge
                               ? 12
                               : centeredX(footer)),
                    122);
}

inline void drawMenuHealth(LGFX_Sprite& sprite, const MenuState& menu,
                           MenuVisual visual) {
  drawMenuTitle(sprite, visual, "HEALTH");
  const DiagnosticsRenderView& diagnostics = menu.diagnostics;
  const char* labels[] = {"LINK", "HERDR", "CODEX", "SYNC AGE", "CODEX AGE",
                          "ERR"};
  const char* values[] = {
      diagnosticStateWord(diagnostics.link_status, true, false),
      diagnosticStateWord(diagnostics.herdr_status, false, false),
      diagnosticStateWord(diagnostics.codex_status, false, true),
      diagnosticAge(diagnostics.sync_age),
      diagnosticAge(diagnostics.codex_age),
      allowedMenuError(diagnostics.error_code) ? diagnostics.error_code
                                               : "NONE"};
  static constexpr int32_t kRows[] = {30, 46, 62, 78, 94, 110};
  for (uint8_t row = 0; row < 6; ++row) {
    drawMenuDetailRow(sprite, visual, labels[row], values[row], kRows[row]);
  }
  drawMenuBackFooter(sprite, visual);
}

inline const char* diagnosticSuffix(const char* suffix) {
  if (suffix == nullptr || strlen(suffix) != 6) return "N/A";
  for (uint8_t index = 0; index < 6; ++index) {
    const char value = suffix[index];
    if (!((value >= 'A' && value <= 'F') ||
          (value >= '0' && value <= '9'))) {
      return "N/A";
    }
  }
  return suffix;
}

inline void drawMenuAbout(LGFX_Sprite& sprite, const MenuState& menu,
                          MenuVisual visual) {
  drawMenuTitle(sprite, visual, "ABOUT");
  char protocol[4] = {};
  snprintf(protocol, sizeof(protocol), "%u",
           static_cast<unsigned>(menu.diagnostics.protocol_version));
  const char* labels[] = {"FW", "PROTO", "BRIDGE", "DEV", "SES", "REV"};
  const char* values[] = {
      diagnosticVersion(menu.diagnostics.firmware_version), protocol,
      diagnosticVersion(menu.diagnostics.bridge_version),
      diagnosticSuffix(menu.diagnostics.device_suffix),
      diagnosticSuffix(menu.diagnostics.session_suffix),
      diagnosticSuffix(menu.diagnostics.revision_suffix)};
  static constexpr int32_t kRows[] = {30, 46, 62, 78, 94, 110};
  for (uint8_t row = 0; row < 6; ++row) {
    drawMenuDetailRow(sprite, visual, labels[row], values[row], kRows[row]);
  }
  drawMenuBackFooter(sprite, visual);
}

inline void drawMenuPage(LGFX_Sprite& sprite, const MenuState& menu,
                         MenuVisual visual) {
  switch (menu.page) {
    case MenuPage::Theme:
    case MenuPage::Leds:
      drawMenuValuePreview(sprite, menu, visual);
      break;
    case MenuPage::Brightness:
      drawMenuBrightness(sprite, menu, visual);
      break;
    case MenuPage::Health:
      drawMenuHealth(sprite, menu, visual);
      break;
    case MenuPage::About:
      drawMenuAbout(sprite, menu, visual);
      break;
    case MenuPage::Root:
    default:
      drawMenuRoot(sprite, menu, visual);
      break;
  }
}

}  // namespace theme_common
