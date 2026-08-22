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
  // Every poll must provide its real hardware-observation timestamp. The
  // adapter preserves the first timestamp until the corresponding key/delta
  // is consumed; later polls cannot move an unconsumed edge forward.
  void update(uint32_t now_us);
  uint32_t inputLatchedAt() const { return input_latched_at_us_; }
  uint32_t takeMaxPollGapUs() {
    const uint32_t gap = pending_max_poll_gap_us_;
    pending_max_poll_gap_us_ = 0;
    return gap;
  }
  long encoderDelta();
  long consumeEncoderDelta(uint32_t* latched_at_us = nullptr);
  bool ready() const { return ready_; }

  Display* displayAt(uint8_t index);
  uint8_t screenCount() const;
  button::ButtonSense* key(uint8_t index);
  bool wasPressed(uint8_t logical_index);
  bool isDown(uint8_t logical_index) const;
  bool consumeReleased(uint8_t logical_index);
  bool consumePressed(uint8_t logical_index, uint32_t* latched_at_us = nullptr);
  bool mapKeyLabel(uint8_t label, uint8_t& library_index) const;
  bool mapEncoderClick(uint8_t& library_index) const;
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
  uint8_t down_latch_ = 0;
  uint8_t released_latch_ = 0;
  uint32_t key_latched_at_us_[PhysicalMap::kKeyCount] = {};
  int32_t encoder_delta_latch_ = 0;
  uint32_t encoder_latched_at_us_ = 0;
  uint32_t input_latched_at_us_ = 0;
  uint32_t last_poll_at_us_ = 0;
  uint32_t pending_max_poll_gap_us_ = 0;

  void refreshInputLatchTimestamp();
};
