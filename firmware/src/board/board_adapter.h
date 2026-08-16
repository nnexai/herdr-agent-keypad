#pragma once

#include <stdint.h>

#include <TKeyboardS3Pro.h>

#include "physical_map.h"

// The only firmware-facing hardware boundary.  The adapter deliberately
// exposes the official Pro abstraction and ButtonSense objects, never raw
// panel chip-selects, GPIOs, or a second debounce path.
class BoardAdapter {
 public:
  bool begin();
  void update();

  Display& displayAt(uint8_t index);
  uint8_t screenCount() const;
  button::ButtonSense& key(uint8_t index);
  long encoderDelta();
  long encoderPosition() const;

  void setBrightness(uint8_t brightness);
  void setLeds(uint16_t hue, uint8_t saturation, uint8_t brightness,
               uint16_t ledMask = 0x3FFF);
  void clearDisplays(uint16_t color);

 private:
  TKeyboardS3ProClass& board_ = TKeyboardS3Pro;
};
