#pragma once

#include <TKeyboardS3Pro.h>
#include <stdint.h>

#include "render_state.h"

// Panel-4 menu pages. The controller owns transitions and persistence;
// themes only render this bounded view.
enum class MenuPage : uint8_t {
  Root = 0,
  Theme,
  Leds,
  Brightness,
  Health,
  About,
};

enum class MenuPresentationCause : uint8_t {
  None = 0,
  Open,
  Navigate,
  Detail,
  Brightness,
  Confirm,
  Close,
  Cancel,
  Timeout,
};


// Complete bounded menu state passed to the active theme.
struct MenuState {
  bool open = false;
  uint8_t cursor = 0;
  uint8_t viewport_start = 0;
  bool editing = false;
  MenuPage page = MenuPage::Root;
  ThemeId theme_candidate = ThemeId::SignalEdge;
  LedGrammarId grammar_candidate = LedGrammarId::RailEcho;
  MenuPresentationCause presentation_cause =
      MenuPresentationCause::None;
  int8_t presentation_direction = 0;
  uint32_t presentation_started_us = 0;
  uint32_t presentation_duration_us = 0;
  uint8_t presentation_progress = 0;
  uint8_t brightness_candidate = 80;
  ThemeId theme_stored = ThemeId::SignalEdge;
  LedGrammarId grammar_stored = LedGrammarId::RailEcho;
  uint8_t brightness_stored = 80;
  DiagnosticsRenderView diagnostics;
};

// A display language. Every implementation composes complete frames into the
// single shared composition sprite; flushing (one pushSprite per panel) stays
// owned by the projection/commit path and is never done here.
class ThemeRenderer {
 public:
  virtual ~ThemeRenderer() = default;

  virtual void composeTile(LGFX_Sprite& sprite, uint8_t slot, const RenderState& state) = 0;
  virtual void composePanel4(LGFX_Sprite& sprite, const RenderState& state) = 0;
  virtual void composeMenu(LGFX_Sprite& sprite, const MenuState& menu) = 0;
  virtual void composeSync(LGFX_Sprite& sprite) = 0;

  // Returns a dirty-slot bitmask requesting recomposition for ambient motion.
  // 0 = static frame. Driven by the AnimationScheduler through tick().
  virtual uint8_t ambientTick(uint32_t now_us) {
    (void)now_us;
    return 0;
  }

  // Ambient cadence declared by the theme (0 = no ambient loop). The
  // scheduler owns degradation; the theme only declares its natural period.
  virtual uint32_t ambientPeriodUs() const { return 0; }
};

ThemeRenderer& signalEdgeTheme();
ThemeRenderer& ledgerTheme();
ThemeRenderer& beaconTheme();
ThemeRenderer& instrumentTheme();

// Resolves a persisted theme selection to its language implementation.
ThemeRenderer& themeById(ThemeId id);
