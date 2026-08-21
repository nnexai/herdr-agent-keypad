#pragma once

#include <stdint.h>

#include "settings_store.h"
#include "../ui/theme.h"

class MenuController final {
 public:
  enum class Mode : uint8_t {
    Closed = 0,
    Root,
    Theme,
    Leds,
    Brightness,
    Health,
    About,
  };
  static constexpr uint32_t kInactivityUs = 30000000U;
  static constexpr uint8_t kRootRowCount = 6;

  explicit MenuController(SettingsStore& settings) : settings_(settings) {}

  void resetFromStore();
  bool click(uint32_t now_us);
  bool rotate(long delta, uint32_t now_us);
  bool cancel();
  bool expire(uint32_t now_us);
  bool takeDirty();
  bool takeBrightnessIntent(uint8_t& brightness);

  bool open() const { return mode_ != Mode::Closed; }
  bool editing() const {
    return mode_ == Mode::Theme || mode_ == Mode::Leds ||
           mode_ == Mode::Brightness;
  }
  Mode mode() const { return mode_; }
  const MenuState& state() const { return state_; }
  ThemeId activeTheme() const { return state_.theme_candidate; }
  LedGrammarId activeGrammar() const { return state_.grammar_candidate; }
  uint8_t activeBrightness() const { return state_.brightness_candidate; }
  ThemeId storedTheme() const { return state_.theme_stored; }
  LedGrammarId storedGrammar() const { return state_.grammar_stored; }
  uint8_t storedBrightness() const { return state_.brightness_stored; }
  uint32_t lastEncoderActivityUs() const { return last_encoder_activity_us_; }

 private:
  void markDirty() { dirty_ = true; }
  void noteEncoderActivity(uint32_t now_us);
  void updateViewport();
  void close();
  void enter(MenuPage page, Mode mode);
  bool confirmValue();
  void emitBrightness(uint8_t brightness);

  SettingsStore& settings_;
  Mode mode_ = Mode::Closed;
  MenuState state_{};
  uint32_t last_encoder_activity_us_ = 0;
  uint8_t brightness_intent_ = SettingsStore::kDefaultBrightness;
  bool brightness_intent_pending_ = false;
  bool dirty_ = false;
};
