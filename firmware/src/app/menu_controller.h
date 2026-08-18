#pragma once

#include <stdint.h>

#include "settings_store.h"
#include "../ui/theme.h"

class MenuController final {
 public:
  enum class Mode : uint8_t { Closed = 0, RowSelect, ValueCycle };

  explicit MenuController(SettingsStore& settings) : settings_(settings) {}

  void resetFromStore();
  bool click();
  bool rotate(long delta);
  bool cancel();
  bool takeDirty();

  bool open() const { return mode_ != Mode::Closed; }
  bool editing() const { return mode_ == Mode::ValueCycle; }
  Mode mode() const { return mode_; }
  const MenuState& state() const { return state_; }
  ThemeId activeTheme() const { return state_.theme_candidate; }
  LedGrammarId activeGrammar() const { return state_.grammar_candidate; }
  ThemeId storedTheme() const { return state_.theme_stored; }
  LedGrammarId storedGrammar() const { return state_.grammar_stored; }

 private:
  void markDirty() { dirty_ = true; }
  void close();
  void enterValueCycle();
  bool confirmValue();

  SettingsStore& settings_;
  Mode mode_ = Mode::Closed;
  MenuState state_{};
  bool confirmed_since_navigation_ = false;
  bool dirty_ = false;
};
