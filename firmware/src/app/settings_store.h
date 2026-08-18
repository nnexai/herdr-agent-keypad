#pragma once

#include <stdint.h>

#include "../ui/render_state.h"

// NVS-backed persistence for the two device-owned presentation settings.
// Only explicitly confirmed selections are written (D-11); invalid, missing,
// or out-of-range stored values fall back to Signal Edge + Rail Echo without
// a write-back — a fallback is never a user confirmation (D-12).  No host
// data, identities, epochs, or bindings are ever persisted.
class SettingsStore final {
 public:
  static constexpr uint32_t kSchemaVersion = 1;

  // Reads and validates the stored selection.  Always leaves the store in a
  // usable state; returns false when the stored data was absent or invalid
  // and the defaults were applied.
  bool load();

  ThemeId theme() const { return theme_; }
  LedGrammarId ledGrammar() const { return grammar_; }

  // The only write path: called on explicit menu confirmation.  Writes the
  // schema version first, then both enums, and updates the in-memory
  // selection.  Returns false when any write failed.
  bool confirm(ThemeId theme, LedGrammarId grammar);

 private:
  ThemeId theme_ = ThemeId::SignalEdge;
  LedGrammarId grammar_ = LedGrammarId::RailEcho;
};
