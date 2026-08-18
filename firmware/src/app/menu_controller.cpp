#include "menu_controller.h"

namespace {
uint8_t nextValue(uint8_t value, long delta, uint8_t count) {
  if (count == 0 || delta == 0) return value;
  long next = static_cast<long>(value) + delta;
  next %= count;
  if (next < 0) next += count;
  return static_cast<uint8_t>(next);
}
}

void MenuController::resetFromStore() {
  mode_ = Mode::Closed;
  state_ = {};
  state_.theme_stored = settings_.theme();
  state_.grammar_stored = settings_.ledGrammar();
  state_.theme_candidate = state_.theme_stored;
  state_.grammar_candidate = state_.grammar_stored;
  confirmed_since_navigation_ = false;
  dirty_ = false;
}

void MenuController::close() {
  mode_ = Mode::Closed;
  state_.open = false;
  state_.editing = false;
  state_.theme_candidate = state_.theme_stored;
  state_.grammar_candidate = state_.grammar_stored;
  confirmed_since_navigation_ = false;
  markDirty();
}

void MenuController::enterValueCycle() {
  mode_ = Mode::ValueCycle;
  state_.editing = true;
  confirmed_since_navigation_ = false;
  markDirty();
}

bool MenuController::confirmValue() {
  if (state_.theme_candidate == state_.theme_stored &&
      state_.grammar_candidate == state_.grammar_stored) {
    close();
    return true;
  }
  if (!settings_.confirm(state_.theme_candidate, state_.grammar_candidate)) return false;
  state_.theme_stored = state_.theme_candidate;
  state_.grammar_stored = state_.grammar_candidate;
  mode_ = Mode::RowSelect;
  state_.editing = false;
  confirmed_since_navigation_ = true;
  markDirty();
  return true;
}

bool MenuController::click() {
  if (mode_ == Mode::Closed) {
    mode_ = Mode::RowSelect;
    state_.open = true;
    state_.editing = false;
    state_.cursor = 0;
    state_.theme_candidate = state_.theme_stored;
    state_.grammar_candidate = state_.grammar_stored;
    confirmed_since_navigation_ = false;
    markDirty();
    return true;
  }
  if (mode_ == Mode::ValueCycle) return confirmValue();
  if (confirmed_since_navigation_) {
    close();
    return true;
  }
  enterValueCycle();
  return true;
}

bool MenuController::rotate(long delta) {
  if (mode_ == Mode::Closed || delta == 0) return false;
  confirmed_since_navigation_ = false;
  if (mode_ == Mode::RowSelect) {
    long cursor = static_cast<long>(state_.cursor) + delta;
    if (cursor < 0) cursor = 0;
    if (cursor > 1) cursor = 1;
    const uint8_t next = static_cast<uint8_t>(cursor);
    if (next == state_.cursor) return false;
    state_.cursor = next;
    markDirty();
    return true;
  }
  if (state_.cursor == 0) {
    const ThemeId next = static_cast<ThemeId>(nextValue(static_cast<uint8_t>(state_.theme_candidate), delta, kThemeCount));
    if (next == state_.theme_candidate) return false;
    state_.theme_candidate = next;
  } else {
    const LedGrammarId next = static_cast<LedGrammarId>(nextValue(static_cast<uint8_t>(state_.grammar_candidate), delta, kLedGrammarCount));
    if (next == state_.grammar_candidate) return false;
    state_.grammar_candidate = next;
  }
  markDirty();
  return true;
}

bool MenuController::cancel() {
  if (mode_ == Mode::Closed) return false;
  close();
  return true;
}

bool MenuController::takeDirty() {
  const bool dirty = dirty_;
  dirty_ = false;
  return dirty;
}
