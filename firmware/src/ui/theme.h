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
  // 0 = static frame. The bounded scheduler lands with the themes that use it.
  virtual uint8_t ambientTick(uint32_t now_us) {
    (void)now_us;
    return 0;
  }
};

ThemeRenderer& signalEdgeTheme();

// Resolves a persisted theme selection. Until plan 02.2-02 lands the three
// remaining languages, every id resolves to Signal Edge (the safe default).
ThemeRenderer& themeById(ThemeId id);
