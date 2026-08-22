#include "board_adapter.h"

void BoardAdapter::clearInputLatches() {
  pressed_latch_ = 0;
  down_latch_ = 0;
  released_latch_ = 0;
  for (uint8_t logical = 0; logical < PhysicalMap::kKeyCount; ++logical) {
    key_latched_at_us_[logical] = 0;
  }
  encoder_delta_latch_ = 0;
  encoder_latched_at_us_ = 0;
  input_latched_at_us_ = 0;
#ifdef ARDUINO
  portENTER_CRITICAL(&input_sample_mux_);
#endif
  sampled_pressed_latch_ = 0;
  sampled_down_latch_ = 0;
  sampled_released_latch_ = 0;
  for (uint8_t logical = 0; logical < PhysicalMap::kKeyCount; ++logical) {
    sampled_key_latched_at_us_[logical] = 0;
  }
  raw_sample_initialized_ = false;
  last_poll_at_us_ = 0;
  pending_max_poll_gap_us_ = 0;
#ifdef ARDUINO
  portEXIT_CRITICAL(&input_sample_mux_);
#endif
}

bool BoardAdapter::begin(const PhysicalMap& physical_map) {
  physical_map_ = &physical_map;
  ready_ = false;
  clearInputLatches();
  if (!physical_map_->complete()) return false;
  BoardConfig config;
  config.enableDisplay = true;
  config.enableEncoder = true;
  ready_ = board_.begin(config);
  if (!ready_) return false;
#ifdef ARDUINO
  captureRawKeySample(board_.keys(), micros());
  if (xTaskCreate(inputPollTaskEntry, "key-poll", 3072, this, 2,
                  &input_poll_task_) != pdPASS) {
    input_poll_task_ = nullptr;
    ready_ = false;
    clearInputLatches();
    return false;
  }
#else
  captureRawKeySample(board_.keys(), 0);
#endif
  return true;
}

uint8_t BoardAdapter::logicalKeyMask(uint8_t raw_key_state) const {
  if (physical_map_ == nullptr || !physical_map_->complete()) return 0;
  uint8_t logical_mask = 0;
  for (uint8_t logical = 0; logical < PhysicalMap::kKeyCount; ++logical) {
    uint8_t library_index = 0;
    if (!physical_map_->keyIndex(logical, library_index)) continue;
    const uint8_t raw_bit =
        static_cast<uint8_t>(1U << (PhysicalMap::kKeyCount - 1U - library_index));
    if ((raw_key_state & raw_bit) != 0) {
      logical_mask |= static_cast<uint8_t>(1U << logical);
    }
  }
  return logical_mask;
}

void BoardAdapter::captureRawKeySample(uint8_t raw_key_state, uint32_t now_us) {
  const uint8_t logical_down = logicalKeyMask(raw_key_state);
#ifdef ARDUINO
  portENTER_CRITICAL(&input_sample_mux_);
#endif
  if (!raw_sample_initialized_) {
    sampled_down_latch_ = logical_down;
    raw_sample_initialized_ = true;
    last_poll_at_us_ = now_us;
#ifdef ARDUINO
    portEXIT_CRITICAL(&input_sample_mux_);
#endif
    return;
  }

  const uint32_t gap = now_us - last_poll_at_us_;
  if (gap > pending_max_poll_gap_us_) pending_max_poll_gap_us_ = gap;
  last_poll_at_us_ = now_us;
  const uint8_t changed =
      static_cast<uint8_t>(sampled_down_latch_ ^ logical_down);
  const uint8_t pressed = static_cast<uint8_t>(changed & logical_down);
  const uint8_t released =
      static_cast<uint8_t>(changed & static_cast<uint8_t>(~logical_down));
  for (uint8_t logical = 0; logical < PhysicalMap::kKeyCount; ++logical) {
    const uint8_t bit = static_cast<uint8_t>(1U << logical);
    if ((pressed & bit) != 0 && (sampled_pressed_latch_ & bit) == 0) {
      sampled_key_latched_at_us_[logical] = now_us;
    }
  }
  sampled_pressed_latch_ |= pressed;
  sampled_released_latch_ |= released;
  sampled_down_latch_ = logical_down;
#ifdef ARDUINO
  portEXIT_CRITICAL(&input_sample_mux_);
#endif
}

void BoardAdapter::drainRawKeySamples() {
  uint8_t pressed = 0;
  uint8_t down = 0;
  uint8_t released = 0;
  uint32_t pressed_at[PhysicalMap::kKeyCount] = {};
#ifdef ARDUINO
  portENTER_CRITICAL(&input_sample_mux_);
#endif
  pressed = sampled_pressed_latch_;
  down = sampled_down_latch_;
  released = sampled_released_latch_;
  sampled_pressed_latch_ = 0;
  sampled_released_latch_ = 0;
  for (uint8_t logical = 0; logical < PhysicalMap::kKeyCount; ++logical) {
    pressed_at[logical] = sampled_key_latched_at_us_[logical];
    sampled_key_latched_at_us_[logical] = 0;
  }
#ifdef ARDUINO
  portEXIT_CRITICAL(&input_sample_mux_);
#endif

  for (uint8_t logical = 0; logical < PhysicalMap::kKeyCount; ++logical) {
    const uint8_t bit = static_cast<uint8_t>(1U << logical);
    if ((pressed & bit) != 0 && (pressed_latch_ & bit) == 0) {
      key_latched_at_us_[logical] = pressed_at[logical];
    }
  }
  pressed_latch_ |= pressed;
  released_latch_ |= released;
  down_latch_ = down;
  refreshInputLatchTimestamp();
}

uint32_t BoardAdapter::takeMaxPollGapUs() {
#ifdef ARDUINO
  portENTER_CRITICAL(&input_sample_mux_);
#endif
  const uint32_t gap = pending_max_poll_gap_us_;
  pending_max_poll_gap_us_ = 0;
#ifdef ARDUINO
  portEXIT_CRITICAL(&input_sample_mux_);
#endif
  return gap;
}

#ifndef ARDUINO
void BoardAdapter::captureRawKeySampleForTest(uint32_t now_us) {
  captureRawKeySample(board_.keys(), now_us);
}
#else
void BoardAdapter::inputPollTaskEntry(void* context) {
  static_cast<BoardAdapter*>(context)->inputPollTask();
}

void BoardAdapter::inputPollTask() {
  TickType_t next_poll = xTaskGetTickCount();
  for (;;) {
    captureRawKeySample(board_.keys(), micros());
    vTaskDelayUntil(&next_poll, pdMS_TO_TICKS(kInputPollPeriodMs));
  }
}
#endif

void BoardAdapter::refreshInputLatchTimestamp() {
  uint32_t first = 0;
  bool have_first = false;
  for (uint8_t logical = 0; logical < PhysicalMap::kKeyCount; ++logical) {
    if ((pressed_latch_ & static_cast<uint8_t>(1U << logical)) == 0) continue;
    const uint32_t candidate = key_latched_at_us_[logical];
    if (!have_first ||
        static_cast<int32_t>(candidate - first) < 0) {
      first = candidate;
      have_first = true;
    }
  }
  if (encoder_delta_latch_ != 0 &&
      (!have_first ||
       static_cast<int32_t>(encoder_latched_at_us_ - first) < 0)) {
    first = encoder_latched_at_us_;
    have_first = true;
  }
  input_latched_at_us_ = have_first ? first : 0;
}

void BoardAdapter::update(uint32_t now_us) {
  if (!ready_ || physical_map_ == nullptr || !physical_map_->complete()) {
    ready_ = false;
    clearInputLatches();
    return;
  }
  board_.update();
  captureRawKeySample(board_.keyState(), now_us);
  drainRawKeySamples();

  const long raw_delta = board_.encoder.delta();
  if (raw_delta != 0) {
    const int64_t bounded_delta =
        raw_delta > INT32_MAX ? INT32_MAX :
        raw_delta < INT32_MIN ? INT32_MIN : static_cast<int64_t>(raw_delta);
    const int64_t accumulated =
        static_cast<int64_t>(encoder_delta_latch_) + bounded_delta;
    if (encoder_delta_latch_ == 0) encoder_latched_at_us_ = now_us;
    encoder_delta_latch_ =
        accumulated > INT32_MAX ? INT32_MAX :
        accumulated < INT32_MIN ? INT32_MIN : static_cast<int32_t>(accumulated);
    if (encoder_delta_latch_ == 0) encoder_latched_at_us_ = 0;
  }
  refreshInputLatchTimestamp();
}

Display* BoardAdapter::displayAt(uint8_t index) {
  uint8_t library_index = 0;
  if (!ready_ || physical_map_ == nullptr ||
      !physical_map_->displayIndex(static_cast<uint8_t>(index + 1), library_index)) {
    return nullptr;
  }
  return &board_.displayAt(library_index);
}

uint8_t BoardAdapter::screenCount() const {
  return ready_ && physical_map_ != nullptr ? PhysicalMap::kDisplayCount : 0;
}


bool BoardAdapter::wasPressed(uint8_t logical_index) {
  if (!ready_ || logical_index >= PhysicalMap::kKeyCount) return false;
  return (pressed_latch_ & static_cast<uint8_t>(1U << logical_index)) != 0;
}

bool BoardAdapter::isDown(uint8_t logical_index) const {
  if (!ready_ || logical_index >= PhysicalMap::kKeyCount) return false;
  return (down_latch_ & static_cast<uint8_t>(1U << logical_index)) != 0;
}

bool BoardAdapter::consumeReleased(uint8_t logical_index) {
  if (!ready_ || logical_index >= PhysicalMap::kKeyCount) return false;
  const uint8_t bit = static_cast<uint8_t>(1U << logical_index);
  if ((released_latch_ & bit) == 0) return false;
  released_latch_ &= static_cast<uint8_t>(~bit);
  return true;
}

bool BoardAdapter::consumePressed(uint8_t logical_index, uint32_t* latched_at_us) {
  if (!wasPressed(logical_index)) return false;
  if (latched_at_us != nullptr) *latched_at_us = key_latched_at_us_[logical_index];
  pressed_latch_ &= static_cast<uint8_t>(~(1U << logical_index));
  key_latched_at_us_[logical_index] = 0;
  refreshInputLatchTimestamp();
  return true;
}

bool BoardAdapter::mapKeyLabel(uint8_t label, uint8_t& library_index) const {
  if (!ready_ || physical_map_ == nullptr || label < 1 || label > 4) return false;
  return physical_map_->keyIndex(static_cast<uint8_t>(label - 1), library_index);
}

bool BoardAdapter::mapEncoderClick(uint8_t& library_index) const {
  if (!ready_ || physical_map_ == nullptr) return false;
  return physical_map_->encoderClickIndex(library_index);
}

long BoardAdapter::encoderDelta() {
  if (!ready_) return 0;
  return encoder_delta_latch_;
}

long BoardAdapter::consumeEncoderDelta(uint32_t* latched_at_us) {
  if (!ready_) return 0;
  if (latched_at_us != nullptr) *latched_at_us = encoder_latched_at_us_;
  const long delta = encoder_delta_latch_;
  encoder_delta_latch_ = 0;
  encoder_latched_at_us_ = 0;
  refreshInputLatchTimestamp();
  return delta;
}

long BoardAdapter::encoderPosition() const {
  if (!ready_) return 0;
  return board_.encoderPosition();
}

void BoardAdapter::setBrightness(uint8_t brightness) {
  if (!ready_) return;
  board_.setBrightness(brightness);
}

void BoardAdapter::setLeds(uint16_t hue, uint8_t saturation, uint8_t brightness,
                           uint16_t ledMask) {
  if (!ready_ || physical_map_ == nullptr) return;
  uint16_t library_mask = 0;
  if (!physical_map_->ledMask(ledMask, library_mask)) return;
  board_.setLeds(hue, saturation, brightness, library_mask);
}

void BoardAdapter::clearDisplays(uint16_t color) {
  if (!ready_) return;
  // The Pro library owns STM32 panel selection. Keep this explicitly
  // sequential; selecting several panels at once is unreliable on this board.
  for (uint8_t panel = 0; panel < screenCount(); ++panel) {
    Display* display = displayAt(panel);
    if (display != nullptr) display->fillScreen(color);
  }
}
