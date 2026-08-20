#include "settings_store.h"

#include <Preferences.h>

namespace {
constexpr const char* kNamespace = "keypad";
constexpr const char* kVersionKey = "ver";
constexpr const char* kThemeKey = "theme";
constexpr const char* kGrammarKey = "ledgram";
}  // namespace

bool SettingsStore::load() {
  theme_ = ThemeId::SignalEdge;
  grammar_ = LedGrammarId::RailEcho;
  Preferences preferences;
  if (!preferences.begin(kNamespace, true)) return false;
  const bool keys_present = preferences.isKey(kVersionKey) && preferences.isKey(kThemeKey) &&
                            preferences.isKey(kGrammarKey);
  const uint32_t version = preferences.getUInt(kVersionKey, 0);
  const uint8_t theme = preferences.getUChar(kThemeKey, 0xFF);
  const uint8_t grammar = preferences.getUChar(kGrammarKey, 0xFF);
  preferences.end();
  if (!keys_present || version != kSchemaVersion || theme >= kThemeCount || grammar >= kLedGrammarCount) {
    // Fallback is not a confirmation: never write defaults back (D-12).
    return false;
  }
  theme_ = static_cast<ThemeId>(theme);
  grammar_ = static_cast<LedGrammarId>(grammar);
  return true;
}

bool SettingsStore::confirm(ThemeId theme, LedGrammarId grammar) {
  if (static_cast<uint8_t>(theme) >= kThemeCount || static_cast<uint8_t>(grammar) >= kLedGrammarCount) return false;
  Preferences preferences;
  if (!preferences.begin(kNamespace, false)) return false;
  // Keep the record invalid until both enum values have been replaced.  The
  // marker is deliberately committed last so reboot cannot accept a hybrid.
  const bool written = preferences.putUInt(kVersionKey, 0) != 0 &&
                       preferences.putUChar(kThemeKey, static_cast<uint8_t>(theme)) != 0 &&
                       preferences.putUChar(kGrammarKey, static_cast<uint8_t>(grammar)) != 0 &&
                       preferences.putUInt(kVersionKey, kSchemaVersion) != 0;
  preferences.end();
  if (!written) return false;
  theme_ = theme;
  grammar_ = grammar;
  return true;
}
