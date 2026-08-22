#pragma once

#include <stdint.h>

#include <TKeyboardS3Pro.h>

#include "physical_map.h"

// The only firmware-facing hardware boundary. The adapter uses the official
// Pro display, encoder, and raw STM32 key APIs. A dedicated bounded key poller
// latches raw edges so display flush latency cannot hide a complete tap.
class BoardAdapter {
 public:
  bool begin(const PhysicalMap& physical_map);
  // Merge every raw edge captured since the prior product-loop iteration and
  // advance the encoder. The first timestamp for each unconsumed press is
  // preserved even when press and release both occur between two calls.
  void update(uint32_t now_us);
  uint32_t inputLatchedAt() const { return input_latched_at_us_; }
  uint32_t takeMaxPollGapUs();
  long encoderDelta();
  long consumeEncoderDelta(uint32_t* latched_at_us = nullptr);
  bool ready() const { return ready_; }
  // These masks are the fixed three-agent-key physical frame. They expose the
  // latest drained down state and pending edge latches without polling hardware.
  static constexpr uint8_t kAgentKeyMask = 0x07U;
  uint8_t agentPressedMask() const {
    return ready_ ? static_cast<uint8_t>(pressed_latch_ & kAgentKeyMask) : 0;
  }
  uint8_t agentDownMask() const {
    return ready_ ? static_cast<uint8_t>(down_latch_ & kAgentKeyMask) : 0;
  }
  uint8_t agentReleasedMask() const {
    return ready_ ? static_cast<uint8_t>(released_latch_ & kAgentKeyMask) : 0;
  }

  Display* displayAt(uint8_t index);
  uint8_t screenCount() const;
#ifndef ARDUINO
  // Native regression seam for a complete tap captured between product-loop
  // updates. Production invokes the same path from the dedicated poll task.
  void captureRawKeySampleForTest(uint32_t now_us);
#endif
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
  uint8_t sampled_pressed_latch_ = 0;
  uint8_t sampled_down_latch_ = 0;
  uint8_t sampled_released_latch_ = 0;
  uint32_t sampled_key_latched_at_us_[PhysicalMap::kKeyCount] = {};
  bool raw_sample_initialized_ = false;
#ifdef ARDUINO
  static constexpr uint32_t kInputPollPeriodMs = 2;
  TaskHandle_t input_poll_task_ = nullptr;
  portMUX_TYPE input_sample_mux_ = portMUX_INITIALIZER_UNLOCKED;
#endif

  void refreshInputLatchTimestamp();
  void clearInputLatches();
  uint8_t logicalKeyMask(uint8_t raw_key_state) const;
  void captureRawKeySample(uint8_t raw_key_state, uint32_t now_us);
  void drainRawKeySamples();
#ifdef ARDUINO
  static void inputPollTaskEntry(void* context);
  void inputPollTask();
#endif
};
