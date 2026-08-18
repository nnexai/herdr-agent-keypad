#pragma once

#include <TKeyboardS3Pro.h>
#include <stdint.h>

#include "render_state.h"

// Panel-4 encoder menu state. Plan 02.2-04 extends this; until then themes
// render their honest panel-4 rest composition when the menu is closed.
struct MenuState {
  bool open = false;
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
