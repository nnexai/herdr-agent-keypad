#pragma once

#include <stdint.h>

struct BoardConfig {
  bool enableDisplay = true;
  bool enableEncoder = true;
};

class Display {
 public:
  void fillScreen(uint16_t) {}
};

namespace button {

class ButtonSense {
 public:
  void setDebounceThresh(uint32_t msec) { debounce_ms_ = msec; }
  uint32_t getDebounceThresh() const { return debounce_ms_; }
  bool isPressed() {
    ++is_down_reads_;
    return down_;
  }

  bool wasPressed() {
    ++was_pressed_reads_;
    return pressed_edge_;
  }

  bool wasReleased() {
    ++was_released_reads_;
    return released_edge_;
  }

  void setSample(bool down, bool pressed_edge, bool released_edge) {
    down_ = down;
    pressed_edge_ = pressed_edge;
    released_edge_ = released_edge;
  }

 private:
  bool down_ = false;
  bool pressed_edge_ = false;
  bool released_edge_ = false;
  uint32_t debounce_ms_ = 10;
  uint32_t is_down_reads_ = 0;
  uint32_t was_pressed_reads_ = 0;
  uint32_t was_released_reads_ = 0;
};

}  // namespace button

namespace board_stub {

extern bool next_down[5];
extern bool next_pressed[5];
extern bool next_released[5];
extern uint32_t update_count;

inline void reset() {
  for (uint8_t index = 0; index < 5; ++index) {
    next_down[index] = false;
    next_pressed[index] = false;
    next_released[index] = false;
  }
  update_count = 0;
}

inline void sample(uint8_t index, bool down, bool pressed_edge, bool released_edge) {
  if (index >= 5) return;
  next_down[index] = down;
  next_pressed[index] = pressed_edge;
  next_released[index] = released_edge;
}

inline uint32_t update_calls() { return update_count; }

}  // namespace board_stub

class RotaryEncoder {
 public:
  long delta() { return 0; }
  long position() const { return 0; }
};

class TKeyboardS3ProClass {
 public:
  Display& displayAt(uint8_t index) { return displays[index < 4 ? index : 0]; }

  bool begin(BoardConfig) {
    for (uint8_t index = 0; index < 5; ++index) {
      keys_[index].setDebounceThresh(10);
    }
    return true;
  }

  void update() {
    ++board_stub::update_count;
    for (uint8_t index = 0; index < 5; ++index) {
      keys_[index].setSample(board_stub::next_down[index],
                             board_stub::next_pressed[index],
                             board_stub::next_released[index]);
    }
  }
  uint8_t keys(uint8_t = 0x01) const {
    uint8_t raw = 0;
    for (uint8_t index = 0; index < 5; ++index) {
      if (board_stub::next_down[index]) {
        raw |= static_cast<uint8_t>(1U << (4U - index));
      }
    }
    return raw;
  }
  uint8_t keyState() const { return keys(); }


  button::ButtonSense& key(uint8_t index) { return keys_[index < 5 ? index : 0]; }
  uint32_t debounceThresh(uint8_t index) const {
    return keys_[index < 5 ? index : 0].getDebounceThresh();
  }
  long encoderPosition() const { return encoder.position(); }
  void setBrightness(uint8_t) {}
  void setLeds(uint16_t, uint8_t, uint8_t, uint16_t) {}

  Display displays[4];
  RotaryEncoder encoder;

 private:
  button::ButtonSense keys_[5];
};

static TKeyboardS3ProClass TKeyboardS3Pro;
