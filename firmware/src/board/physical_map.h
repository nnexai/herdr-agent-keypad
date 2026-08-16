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

  // This is the hash-verified delivered-unit mapping accepted by the Phase 1
  // bring-up evidence. Runtime dispatch consumes these lookups rather than
  // maintaining a second table in main.cpp.
  void loadVerified() {
    reset();
    for (uint8_t i = 0; i < kDisplayCount; ++i) {
      displays[i].has_library_index = true;
      displays[i].library_index = i;
      displays[i].has_rotation = true;
      displays[i].rotation = 0;
      displays[i].evidence.state = ObservationState::Observed;
      displays[i].evidence.human_confirmed = true;
    }
    for (uint8_t i = 0; i < kKeyCount; ++i) {
      keys[i].has_library_index = true;
      keys[i].library_index = i;
      keys[i].evidence.state = ObservationState::Observed;
      keys[i].evidence.human_confirmed = true;
    }
    encoder.has_clockwise_sign = true;
    encoder.clockwise_sign = 1;
    encoder.has_counter_clockwise_sign = true;
    encoder.counter_clockwise_sign = -1;
    encoder.has_click_key = true;
    encoder.click_key = 4;
    encoder.detents_per_prompted_move = 1;
    encoder.direction_evidence.state = ObservationState::Observed;
    encoder.direction_evidence.human_confirmed = true;
    encoder.click_evidence.state = ObservationState::Observed;
    encoder.click_evidence.human_confirmed = true;
    for (uint8_t i = 0; i < kLedCount; ++i) {
      leds[i].has_library_index = true;
      leds[i].library_index = i;
      leds[i].evidence.state = ObservationState::Observed;
      leds[i].evidence.human_confirmed = true;
    }
    const uint8_t requested[kBrightnessSampleCount] = {10, 50, 100};
    for (uint8_t i = 0; i < kBrightnessSampleCount; ++i) {
      brightness[i].requested_percent = requested[i];
      brightness[i].has_requested_percent = true;
      brightness[i].visible_percent = requested[i];
      brightness[i].has_visible_percent = true;
      brightness[i].evidence.state = ObservationState::Observed;
      brightness[i].evidence.human_confirmed = true;
    }
    orientation.state = ObservationState::Observed;
    orientation.human_confirmed = true;
    software_reboot.state = ObservationState::Observed;
    software_reboot.human_confirmed = true;
    normal_flash_reset.state = ObservationState::Observed;
    normal_flash_reset.human_confirmed = true;
  }

  bool complete() const {
    for (uint8_t i = 0; i < kDisplayCount; ++i)
      if (!displays[i].has_library_index || displays[i].library_index >= kDisplayCount) return false;
    for (uint8_t i = 0; i < kKeyCount; ++i)
      if (!keys[i].has_library_index || keys[i].library_index >= kKeyCount) return false;
    for (uint8_t i = 0; i < kLedCount; ++i)
      if (!leds[i].has_library_index || leds[i].library_index >= kLedCount) return false;
    return encoder.has_click_key && encoder.has_clockwise_sign &&
           encoder.has_counter_clockwise_sign &&
           encoder.click_key < kKeyCount;
  }

  bool displayIndex(uint8_t logical_index, uint8_t& library_index) const {
    if (logical_index < 1 || logical_index > kDisplayCount) return false;
    const DisplayMapping& mapping = displays[logical_index - 1];
    if (!mapping.has_library_index || mapping.library_index >= kDisplayCount) return false;
    library_index = mapping.library_index;
    return true;
  }

  bool keyIndex(uint8_t logical_index, uint8_t& library_index) const {
    if (logical_index >= kKeyCount) return false;
    const KeyMapping& mapping = keys[logical_index];
    if (!mapping.has_library_index || mapping.library_index >= kKeyCount) return false;
    library_index = mapping.library_index;
    return true;
  }

  bool encoderClickIndex(uint8_t& library_index) const {
    if (!encoder.has_click_key || !keyIndex(encoder.click_key, library_index)) return false;
    return true;
  }

  bool ledMask(uint16_t logical_mask, uint16_t& library_mask) const {
    library_mask = 0;
    for (uint8_t logical = 0; logical < kLedCount; ++logical) {
      if ((logical_mask & (static_cast<uint16_t>(1U) << logical)) == 0) continue;
      if (!leds[logical].has_library_index || leds[logical].library_index >= kLedCount) return false;
      library_mask |= static_cast<uint16_t>(1U) << leds[logical].library_index;
    }
    return true;
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
