#include "board_adapter.h"

bool BoardAdapter::begin(const PhysicalMap& physical_map) {
  physical_map_ = &physical_map;
  ready_ = false;
  pressed_latch_ = 0;
  input_latched_at_us_ = 0;
  if (!physical_map_->complete()) return false;
  BoardConfig config;
  config.enableDisplay = true;
  config.enableEncoder = true;
  ready_ = board_.begin(config);
  return ready_;
}

void BoardAdapter::update(uint32_t now_us) {
  if (!ready_) return;
  // This is the single poll path for STM32 keys, ButtonSense, and encoder.
  board_.update();
  input_latched_at_us_ = now_us;
  for (uint8_t logical = 0; logical < PhysicalMap::kKeyCount; ++logical) {
    uint8_t library_index = 0;
    if (physical_map_->keyIndex(logical, library_index) && board_.key(library_index).wasPressed()) {
      pressed_latch_ |= static_cast<uint8_t>(1U << logical);
    }
  }
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

button::ButtonSense* BoardAdapter::key(uint8_t index) {
  uint8_t library_index = 0;
  if (!ready_ || physical_map_ == nullptr || !physical_map_->keyIndex(index, library_index)) {
    return nullptr;
  }
  return &board_.key(library_index);
}

bool BoardAdapter::wasPressed(uint8_t logical_index) {
  if (!ready_ || logical_index >= PhysicalMap::kKeyCount) return false;
  return (pressed_latch_ & static_cast<uint8_t>(1U << logical_index)) != 0;
}

bool BoardAdapter::consumePressed(uint8_t logical_index) {
  if (!wasPressed(logical_index)) return false;
  pressed_latch_ &= static_cast<uint8_t>(~(1U << logical_index));
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
  return board_.encoder.delta();
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
