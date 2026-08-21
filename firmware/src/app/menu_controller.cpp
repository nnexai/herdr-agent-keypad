#include "menu_controller.h"

namespace {
uint8_t clampValue(long value, uint8_t minimum, uint8_t maximum) {
  if (value < minimum) return minimum;
  if (value > maximum) return maximum;
  return static_cast<uint8_t>(value);
}
}  // namespace

void MenuController::resetFromStore() {
  mode_ = Mode::Closed;
  state_ = {};
  state_.theme_stored = settings_.theme();
  state_.grammar_stored = settings_.ledGrammar();
  state_.brightness_stored = settings_.brightness();
  state_.theme_candidate = state_.theme_stored;
  state_.grammar_candidate = state_.grammar_stored;
  state_.brightness_candidate = state_.brightness_stored;
  last_encoder_activity_us_ = 0;
  brightness_intent_ = state_.brightness_stored;
  brightness_intent_pending_ = false;
  dirty_ = false;
}

void MenuController::noteEncoderActivity(uint32_t now_us) {
  last_encoder_activity_us_ = now_us;
}

void MenuController::updateViewport() {
  const uint8_t centered = state_.cursor > 0 ? state_.cursor - 1 : 0;
  state_.viewport_start = centered > 3 ? 3 : centered;
}

void MenuController::emitBrightness(uint8_t brightness) {
  brightness_intent_ = brightness;
  brightness_intent_pending_ = true;
}

void MenuController::close() {
  if (state_.brightness_candidate != state_.brightness_stored) {
    emitBrightness(state_.brightness_stored);
  }
  mode_ = Mode::Closed;
  state_.open = false;
  state_.editing = false;
  state_.page = MenuPage::Root;
  state_.theme_candidate = state_.theme_stored;
  state_.grammar_candidate = state_.grammar_stored;
  state_.brightness_candidate = state_.brightness_stored;
  markDirty();
}

void MenuController::enter(MenuPage page, Mode mode) {
  mode_ = mode;
  state_.page = page;
  state_.editing = editing();
  markDirty();
}

bool MenuController::confirmValue() {
  if (!settings_.confirm(state_.theme_candidate, state_.grammar_candidate,
                         state_.brightness_candidate)) {
    return false;
  }
  state_.theme_stored = state_.theme_candidate;
  state_.grammar_stored = state_.grammar_candidate;
  state_.brightness_stored = state_.brightness_candidate;
  mode_ = Mode::Root;
  state_.page = MenuPage::Root;
  state_.editing = false;
  markDirty();
  return true;
}

bool MenuController::click(uint32_t now_us) {
  noteEncoderActivity(now_us);
  if (mode_ == Mode::Closed) {
    mode_ = Mode::Root;
    state_.open = true;
    state_.editing = false;
    state_.page = MenuPage::Root;
    state_.cursor = 0;
    updateViewport();
    state_.theme_candidate = state_.theme_stored;
    state_.grammar_candidate = state_.grammar_stored;
    state_.brightness_candidate = state_.brightness_stored;
    markDirty();
    return true;
  }
  if (mode_ == Mode::Theme || mode_ == Mode::Leds ||
      mode_ == Mode::Brightness) {
    return confirmValue();
  }
  if (mode_ == Mode::Health || mode_ == Mode::About) {
    enter(MenuPage::Root, Mode::Root);
    return true;
  }
  switch (state_.cursor) {
    case 0:
      enter(MenuPage::Theme, Mode::Theme);
      return true;
    case 1:
      enter(MenuPage::Leds, Mode::Leds);
      return true;
    case 2:
      enter(MenuPage::Brightness, Mode::Brightness);
      return true;
    case 3:
      enter(MenuPage::Health, Mode::Health);
      return true;
    case 4:
      enter(MenuPage::About, Mode::About);
      return true;
    case 5:
      close();
      return true;
    default:
      return false;
  }
}

bool MenuController::rotate(long delta, uint32_t now_us) {
  if (mode_ == Mode::Closed || delta == 0) return false;
  noteEncoderActivity(now_us);
  if (mode_ == Mode::Root) {
    const uint8_t next = clampValue(static_cast<long>(state_.cursor) + delta,
                                    0, kRootRowCount - 1);
    if (next == state_.cursor) return false;
    state_.cursor = next;
    updateViewport();
    markDirty();
    return true;
  }
  if (mode_ == Mode::Health || mode_ == Mode::About) return false;
  if (mode_ == Mode::Theme) {
    const ThemeId next = static_cast<ThemeId>(
        clampValue(static_cast<long>(state_.theme_candidate) + delta,
                   0, kThemeCount - 1));
    if (next == state_.theme_candidate) return false;
    state_.theme_candidate = next;
  } else if (mode_ == Mode::Leds) {
    const LedGrammarId next = static_cast<LedGrammarId>(
        clampValue(static_cast<long>(state_.grammar_candidate) + delta,
                   0, kLedGrammarCount - 1));
    if (next == state_.grammar_candidate) return false;
    state_.grammar_candidate = next;
  } else {
    const uint8_t next = clampValue(
        static_cast<long>(state_.brightness_candidate) + delta * 10L,
        10, 100);
    if (next == state_.brightness_candidate) return false;
    state_.brightness_candidate = next;
    emitBrightness(next);
  }
  markDirty();
  return true;
}

bool MenuController::cancel() {
  if (mode_ == Mode::Closed) return false;
  close();
  return true;
}

bool MenuController::expire(uint32_t now_us) {
  if (mode_ == Mode::Closed ||
      static_cast<uint32_t>(now_us - last_encoder_activity_us_) <
          kInactivityUs) {
    return false;
  }
  close();
  return true;
}

bool MenuController::takeDirty() {
  const bool dirty = dirty_;
  dirty_ = false;
  return dirty;
}

bool MenuController::takeBrightnessIntent(uint8_t& brightness) {
  if (!brightness_intent_pending_) return false;
  brightness = brightness_intent_;
  brightness_intent_pending_ = false;
  return true;
}
