#include "board_adapter.h"

bool BoardAdapter::begin() {
  BoardConfig config;
  config.enableDisplay = true;
  config.enableEncoder = true;
  return board_.begin(config);
}

void BoardAdapter::update() {
  // This is the single poll path for STM32 keys, ButtonSense, and encoder.
  board_.update();
}

Display& BoardAdapter::displayAt(uint8_t index) {
  return board_.displayAt(index);
}

uint8_t BoardAdapter::screenCount() const {
  return TKeyboardS3ProClass::HOST_SCREEN_COUNT;
}

button::ButtonSense& BoardAdapter::key(uint8_t index) {
  return board_.key(index);
}

long BoardAdapter::encoderDelta() {
  return board_.encoder.delta();
}

long BoardAdapter::encoderPosition() const {
  return board_.encoderPosition();
}

void BoardAdapter::setBrightness(uint8_t brightness) {
  board_.setBrightness(brightness);
}

void BoardAdapter::setLeds(uint16_t hue, uint8_t saturation, uint8_t brightness,
                           uint16_t ledMask) {
  board_.setLeds(hue, saturation, brightness, ledMask);
}

void BoardAdapter::clearDisplays(uint16_t color) {
  // The Pro library owns STM32 panel selection.  Keep this explicitly
  // sequential; selecting several panels at once is unreliable on this board.
  for (uint8_t panel = 0; panel < screenCount(); ++panel) {
    displayAt(panel).fillScreen(color);
  }
}
