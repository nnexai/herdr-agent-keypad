#pragma once
#include <cstdint>
#include <cstring>

class Display {
 public:
  void fillScreen(uint16_t) {}
  void setTextColor(uint16_t, uint16_t) {}
  void setTextSize(uint8_t) {}
  void drawString(const char*, int32_t, int32_t) {}
  void drawRect(int32_t, int32_t, int32_t, int32_t, uint16_t) {}
  void drawLine(int32_t, int32_t, int32_t, int32_t, uint16_t) {}
  void fillCircle(int32_t, int32_t, int32_t, uint16_t) {}
  void drawCircle(int32_t, int32_t, int32_t, uint16_t) {}
};

class LGFX_Sprite {
 public:
  void setPsram(bool) {}
  void setColorDepth(uint8_t) {}
  void* createSprite(int32_t, int32_t) { return this; }
  void fillScreen(uint16_t) {}
  void setTextColor(uint16_t, uint16_t) {}
  void setTextSize(uint8_t) {}
  void drawString(const char*, int32_t, int32_t) {}
  void drawRect(int32_t, int32_t, int32_t, int32_t, uint16_t) {}
  void drawLine(int32_t, int32_t, int32_t, int32_t, uint16_t) {}
  void fillCircle(int32_t, int32_t, int32_t, uint16_t) {}
  void drawCircle(int32_t, int32_t, int32_t, uint16_t) {}
  void pushSprite(Display*, int32_t, int32_t) {}
};

namespace button { class ButtonSense {}; }
class TKeyboardS3ProClass {};
static TKeyboardS3ProClass TKeyboardS3Pro;
