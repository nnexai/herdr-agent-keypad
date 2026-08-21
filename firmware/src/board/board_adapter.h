#pragma once

#include <stdint.h>

#include <TKeyboardS3Pro.h>

#include "physical_map.h"

// The only firmware-facing hardware boundary.  The adapter deliberately
// exposes the official Pro abstraction and ButtonSense objects, never raw
// panel chip-selects, GPIOs, or a second debounce path.
class BoardAdapter {
 public:
  bool begin(const PhysicalMap& physical_map);
  // Capture the poll timestamp at the adapter's single hardware latch seam.
  // Product input actions use this timestamp for edge-to-render evidence.
  void update(uint32_t now_us = 0);
  uint32_t inputLatchedAt() const { return input_latched_at_us_; }
  bool ready() const { return ready_; }

  Display* displayAt(uint8_t index);
  uint8_t screenCount() const;
  button::ButtonSense* key(uint8_t index);
  bool wasPressed(uint8_t logical_index);
  bool consumePressed(uint8_t logical_index);
  bool mapKeyLabel(uint8_t label, uint8_t& library_index) const;
  bool mapEncoderClick(uint8_t& library_index) const;
  long encoderDelta();
  long encoderPosition() const;

  void setBrightness(uint8_t brightness);
  void setLeds(uint16_t hue, uint8_t saturation, uint8_t brightness,
               uint16_t ledMask = 0x3FFF);
  void clearDisplays(uint16_t color);

 private:
  TKeyboardS3ProClass& board_ = TKeyboardS3Pro;
  const PhysicalMap* physical_map_ = nullptr;
  bool ready_ = false;
  uint8_t pressed_latch_ = 0;
  uint32_t input_latched_at_us_ = 0;
};
