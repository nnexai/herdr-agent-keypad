#pragma once

#include <Arduino.h>

#include "../board/board_adapter.h"

enum class BringupState : uint8_t {
  Wait = 0,
  Map,
  Press,
  TurnCw,
  TurnCcw,
  Click,
  Brightness,
  Pair,
  Pass,
  Fail,
  LinkLost,
};

struct RenderRequest {
  BringupState state;
  uint8_t active_panel;
  uint8_t brightness_percent;
  char challenge[9];

  RenderRequest() : state(BringupState::Wait), active_panel(0), brightness_percent(0), challenge{} {}
};

// Fixed-state renderer for the temporary physical bring-up.  It owns no
// display or protocol state: each call clears and redraws all four panels in
// order through BoardAdapter, leaving only one panel active.
class BringupRenderer {
 public:
  static constexpr uint8_t kSafeInset = 4;
  static constexpr uint8_t kPanelCount = 4;
  static constexpr uint8_t kChallengeMax = 8;
  static constexpr uint8_t kLowestProofBrightness = 10;

  void render(BoardAdapter& board, const RenderRequest& request) const {
    const uint8_t active = (request.active_panel >= 1 && request.active_panel <= kPanelCount)
                               ? request.active_panel
                               : 0;
    for (uint8_t panel = 1; panel <= kPanelCount; ++panel) {
      Display& display = board.displayAt(panel - 1);
      display.fillScreen(TFT_BLACK);
      if (active == 0 || panel != active || request.state == BringupState::Wait) {
        drawWait(display);
      } else {
        drawActive(display, request);
      }
    }
  }

 private:
  static bool copyChallenge(const char* source, char* destination) {
    if (source == nullptr) {
      return false;
    }
    uint8_t length = 0;
    while (source[length] != '\0') {
      if (length >= kChallengeMax) {
        return false;
      }
      const char value = source[length];
      const bool allowed = (value >= 'A' && value <= 'Z') ||
                           (value >= '0' && value <= '9') || value == '-';
      if (!allowed) {
        return false;
      }
      ++length;
    }
    if (length == 0) {
      return false;
    }
    for (uint8_t i = 0; i < length; ++i) {
      destination[i] = source[i];
    }
    destination[length] = '\0';
    return true;
  }

  static void frame(Display& display, uint16_t color) {
    display.drawRoundRect(kSafeInset, kSafeInset, 128 - 2 * kSafeInset,
                          128 - 2 * kSafeInset, 5, color);
  }

  static void text(Display& display, const char* label, int32_t x, int32_t y,
                   uint16_t foreground = TFT_WHITE) {
    display.setTextColor(foreground, TFT_BLACK);
    display.setTextSize(1);
    display.drawString(label, x, y);
  }

  static void drawWait(Display& display) {
    text(display, "WAIT", 8, 8, TFT_DARKGREY);
    text(display, "IDLE", 48, 56, TFT_DARKGREY);
  }

  static void drawCue(Display& display, BringupState state, uint16_t color) {
    // Geometry repeats the state meaning so a color-blind or low-brightness
    // observation does not depend on the accent color.
    switch (state) {
      case BringupState::Map:
        display.drawLine(64, 38, 64, 56, color);
        display.drawLine(64, 56, 56, 48, color);
        display.drawLine(64, 56, 72, 48, color);
        break;
      case BringupState::TurnCw:
        display.drawLine(52, 58, 76, 58, color);
        display.drawLine(76, 58, 68, 50, color);
        display.drawLine(76, 58, 68, 66, color);
        break;
      case BringupState::TurnCcw:
        display.drawLine(76, 58, 52, 58, color);
        display.drawLine(52, 58, 60, 50, color);
        display.drawLine(52, 58, 60, 66, color);
        break;
      case BringupState::Pass:
        display.drawLine(48, 60, 60, 72, color);
        display.drawLine(60, 72, 82, 46, color);
        break;
      case BringupState::Fail:
        display.drawLine(52, 48, 76, 72, color);
        display.drawLine(76, 48, 52, 72, color);
        break;
      case BringupState::LinkLost:
        display.drawLine(50, 54, 60, 44, color);
        display.drawLine(68, 72, 78, 62, color);
        display.drawLine(58, 62, 70, 50, color);
        break;
      case BringupState::Press:
      case BringupState::Click:
      case BringupState::Brightness:
      case BringupState::Pair:
      case BringupState::Wait:
      default:
        break;
    }
  }

  static void drawActive(Display& display, const RenderRequest& request) {
    uint16_t accent = TFT_CYAN;
    const char* label = "WAIT";
    const char* glyph = "IDLE";
    const char* instruction = "READY";
    uint16_t glyph_color = TFT_WHITE;

    switch (request.state) {
      case BringupState::Map:
        label = "MAP";
        instruction = "ARROW ^";
        break;
      case BringupState::Press:
        label = "PRESS";
        glyph = "KEY";
        instruction = "PRESS KEY";
        break;
      case BringupState::TurnCw:
        label = "TURN CW";
        glyph = ">";
        instruction = "ROTATE";
        break;
      case BringupState::TurnCcw:
        label = "TURN CCW";
        glyph = "<";
        instruction = "ROTATE";
        break;
      case BringupState::Click:
        label = "CLICK";
        glyph = "ENC";
        instruction = "PRESS";
        break;
      case BringupState::Brightness:
        label = "BRIGHTNESS";
        glyph = "BRIGHT";
        instruction = "SAMPLE";
        break;
      case BringupState::Pair:
        label = "PAIR";
        glyph = "CHALLENGE";
        instruction = "TYPE CODE";
        break;
      case BringupState::Pass:
        label = "PASS";
        glyph = "CHECK";
        instruction = "CONFIRMED";
        glyph_color = TFT_GREEN;
        break;
      case BringupState::Fail:
        label = "FAIL";
        glyph = "X";
        instruction = "REPEAT";
        accent = TFT_RED;
        glyph_color = TFT_RED;
        break;
      case BringupState::LinkLost:
        label = "LINK LOST";
        glyph = "//";
        instruction = "RECONNECT";
        accent = TFT_RED;
        glyph_color = TFT_RED;
        break;
      case BringupState::Wait:
      default:
        drawWait(display);
        return;
    }

    frame(display, accent);
    text(display, label, 8, 8, accent);
    display.setTextColor(glyph_color, TFT_BLACK);
    display.setTextSize(request.state == BringupState::Map || request.state == BringupState::Pair ? 2 : 3);
    if (request.state == BringupState::Map) {
      // Keep the bounded panel identifier in its own row below the arrow cue.
      // A single draw prevents the PANEL text and number from colliding.
      char panel_label[8];
      snprintf(panel_label, sizeof(panel_label), "PANEL-%u", request.active_panel);
      display.drawString(panel_label, 22, 72);
    } else {
      display.drawString(glyph, request.state == BringupState::Pair ? 36 : 48, 48);
    }

    if (request.state == BringupState::Brightness) {
      char percentage[8];
      snprintf(percentage, sizeof(percentage), "%u%%", request.brightness_percent);
      display.setTextColor(TFT_WHITE, TFT_BLACK);
      display.setTextSize(2);
      display.drawString(percentage, 48, 72);
    } else if (request.state == BringupState::Pair) {
      char bounded_challenge[kChallengeMax + 1] = {};
      if (copyChallenge(request.challenge, bounded_challenge)) {
        display.setTextColor(TFT_CYAN, TFT_BLACK);
        display.setTextSize(2);
        display.drawString(bounded_challenge, 24, 72);
      } else {
        text(display, "INVALID", 44, 72, TFT_RED);
      }
    }
    drawCue(display, request.state, glyph_color);

    text(display, instruction, 8, 108, TFT_WHITE);
  }
};
