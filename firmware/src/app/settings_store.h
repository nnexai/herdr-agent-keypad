#pragma once

#include <stdint.h>

#include "../ui/render_state.h"

// NVS-backed persistence for device-owned presentation settings. Only
// explicitly confirmed selections are written. Invalid or missing data falls
// back in memory without a boot write. No host data, identities, epochs,
// bindings, credentials, snapshots, or diagnostics are ever persisted.
class SettingsStore final {
 public:
  static constexpr uint32_t kLegacySchemaVersion = 1;
  static constexpr uint32_t kSchemaVersion = 2;
  static constexpr uint8_t kDefaultBrightness = 80;

  // Reads and validates the stored selection.  Always leaves the store in a
  // usable state; returns false when the stored data was absent or invalid
  // and the defaults were applied.
  bool load();

  ThemeId theme() const { return theme_; }
  LedGrammarId ledGrammar() const { return grammar_; }
  uint8_t brightness() const { return brightness_; }

  // The only write path: called on explicit menu confirmation. The committed
  // schema marker is invalidated before replacing the complete record and
  // written last. A recoverable write failure restores the prior valid record;
  // a power interruption leaves an invalid marker rather than a valid hybrid.
  bool confirm(ThemeId theme, LedGrammarId grammar, uint8_t brightness);

 private:
  ThemeId theme_ = ThemeId::SignalEdge;
  LedGrammarId grammar_ = LedGrammarId::RailEcho;
  uint8_t brightness_ = kDefaultBrightness;
};
