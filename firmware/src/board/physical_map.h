#pragma once

#include <stdint.h>
#include <string.h>

// Physical bring-up facts are intentionally separate from the board-library
// indices.  A library acknowledgement is not a physical observation.
enum class ObservationState : uint8_t {
  Unavailable = 0,
  Observed,
  Failed,
  Surprising,
};

struct Observation {
  ObservationState state;
  bool human_confirmed;

  Observation() : state(ObservationState::Unavailable), human_confirmed(false) {}

  void reset() {
    state = ObservationState::Unavailable;
    human_confirmed = false;
  }
};

struct DisplayMapping {
  uint8_t logical_index;
  bool has_library_index;
  uint8_t library_index;
  int8_t rotation;
  bool has_rotation;
  char physical_position[24];
  char top_edge_result[16];
  char color_result[16];
  Observation evidence;

  DisplayMapping() : logical_index(0), has_library_index(false), library_index(0), rotation(0),
                     has_rotation(false), physical_position{}, top_edge_result{}, color_result{}, evidence() {}
};

struct KeyMapping {
  uint8_t logical_index;
  bool has_library_index;
  uint8_t library_index;
  char physical_position[24];
  char associated_display[16];
  uint16_t duplicate_count;
  Observation evidence;

  KeyMapping() : logical_index(0), has_library_index(false), library_index(0), physical_position{},
                 associated_display{}, duplicate_count(0), evidence() {}
};

struct EncoderMapping {
  bool has_clockwise_sign;
  int8_t clockwise_sign;
  bool has_counter_clockwise_sign;
  int8_t counter_clockwise_sign;
  bool has_click_key;
  uint8_t click_key;
  uint8_t detents_per_prompted_move;
  Observation direction_evidence;
  Observation click_evidence;

  EncoderMapping() : has_clockwise_sign(false), clockwise_sign(0), has_counter_clockwise_sign(false),
                      counter_clockwise_sign(0), has_click_key(false), click_key(0),
                      detents_per_prompted_move(0), direction_evidence(), click_evidence() {}
};

struct LedMapping {
  uint8_t logical_index;
  bool has_library_index;
  uint8_t library_index;
  char physical_position[24];
  uint16_t requested_hue;
  uint8_t requested_brightness;
  Observation evidence;

  LedMapping() : logical_index(0), has_library_index(false), library_index(0), physical_position{},
                 requested_hue(0), requested_brightness(0), evidence() {}
};

struct BrightnessObservation {
  uint8_t requested_percent;
  bool has_requested_percent;
  uint8_t visible_percent;
  bool has_visible_percent;
  bool persists_after_reset;
  bool has_persistence_observation;
  Observation evidence;

  BrightnessObservation() : requested_percent(0), has_requested_percent(false), visible_percent(0),
                             has_visible_percent(false), persists_after_reset(false),
                             has_persistence_observation(false), evidence() {}
};

struct PhysicalMap {
  static constexpr uint8_t kDisplayCount = 4;
  static constexpr uint8_t kKeyCount = 5;
  static constexpr uint8_t kLedCount = 14;
  static constexpr uint8_t kBrightnessSampleCount = 3;

  DisplayMapping displays[kDisplayCount];
  KeyMapping keys[kKeyCount];
  EncoderMapping encoder;
  LedMapping leds[kLedCount];
  BrightnessObservation brightness[kBrightnessSampleCount];
  Observation software_reboot;
  Observation normal_flash_reset;
  Observation orientation;

  PhysicalMap() : displays{}, keys{}, encoder(), leds{}, brightness{}, software_reboot(),
                  normal_flash_reset(), orientation() {
    reset();
  }

  void reset() {
    for (uint8_t i = 0; i < kDisplayCount; ++i) {
      displays[i] = DisplayMapping();
      displays[i].logical_index = i + 1;
    }
    for (uint8_t i = 0; i < kKeyCount; ++i) {
      keys[i] = KeyMapping();
      keys[i].logical_index = i;
    }
    encoder = EncoderMapping();
    for (uint8_t i = 0; i < kLedCount; ++i) {
      leds[i] = LedMapping();
      leds[i].logical_index = i;
    }
    for (uint8_t i = 0; i < kBrightnessSampleCount; ++i) {
      brightness[i] = BrightnessObservation();
    }
    software_reboot.reset();
    normal_flash_reset.reset();
    orientation.reset();
  }
};
