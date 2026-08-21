#include "settings_store.h"

#include <Preferences.h>

namespace {
constexpr const char* kNamespace = "keypad";
constexpr const char* kVersionKey = "ver";
constexpr const char* kThemeKey = "theme";
constexpr const char* kGrammarKey = "ledgram";
constexpr const char* kBrightnessKey = "bright";

bool validThemeAndGrammar(uint8_t theme, uint8_t grammar) {
  return theme < kThemeCount && grammar < kLedGrammarCount;
}

bool validBrightness(uint8_t brightness) {
  return brightness >= 10 && brightness <= 100 && brightness % 10 == 0;
}

struct StoredRecord {
  uint32_t version = 0;
  uint8_t theme = 0xFF;
  uint8_t grammar = 0xFF;
  uint8_t brightness = SettingsStore::kDefaultBrightness;
  bool valid = false;
};

StoredRecord readRecord(Preferences& preferences) {
  StoredRecord record;
  const bool base_present = preferences.isKey(kVersionKey) &&
                            preferences.isKey(kThemeKey) &&
                            preferences.isKey(kGrammarKey);
  record.version = preferences.getUInt(kVersionKey, 0);
  record.theme = preferences.getUChar(kThemeKey, 0xFF);
  record.grammar = preferences.getUChar(kGrammarKey, 0xFF);
  if (record.version == SettingsStore::kLegacySchemaVersion) {
    record.valid = base_present &&
                   validThemeAndGrammar(record.theme, record.grammar);
    return record;
  }
  const bool brightness_present = preferences.isKey(kBrightnessKey);
  record.brightness = preferences.getUChar(
      kBrightnessKey, SettingsStore::kDefaultBrightness);
  record.valid = base_present && brightness_present &&
                 record.version == SettingsStore::kSchemaVersion &&
                 validThemeAndGrammar(record.theme, record.grammar) &&
                 validBrightness(record.brightness);
  return record;
}

void restoreRecord(Preferences& preferences, const StoredRecord& record) {
  if (!record.valid) return;
  preferences.putUInt(kVersionKey, 0);
  preferences.putUChar(kThemeKey, record.theme);
  preferences.putUChar(kGrammarKey, record.grammar);
  if (record.version == SettingsStore::kSchemaVersion) {
    preferences.putUChar(kBrightnessKey, record.brightness);
  } else {
    preferences.remove(kBrightnessKey);
  }
  preferences.putUInt(kVersionKey, record.version);
}
}  // namespace

bool SettingsStore::load() {
  theme_ = ThemeId::SignalEdge;
  grammar_ = LedGrammarId::RailEcho;
  brightness_ = kDefaultBrightness;
  Preferences preferences;
  if (!preferences.begin(kNamespace, true)) return false;
  const StoredRecord record = readRecord(preferences);
  preferences.end();
  if (!record.valid) return false;
  theme_ = static_cast<ThemeId>(record.theme);
  grammar_ = static_cast<LedGrammarId>(record.grammar);
  brightness_ = record.version == kLegacySchemaVersion
                    ? kDefaultBrightness
                    : record.brightness;
  return true;
}

bool SettingsStore::confirm(ThemeId theme, LedGrammarId grammar,
                            uint8_t brightness) {
  if (!validThemeAndGrammar(static_cast<uint8_t>(theme),
                            static_cast<uint8_t>(grammar)) ||
      !validBrightness(brightness)) {
    return false;
  }
  Preferences preferences;
  if (!preferences.begin(kNamespace, false)) return false;
  const StoredRecord prior = readRecord(preferences);
  const bool written =
      preferences.putUInt(kVersionKey, 0) != 0 &&
      preferences.putUChar(kThemeKey, static_cast<uint8_t>(theme)) != 0 &&
      preferences.putUChar(kGrammarKey, static_cast<uint8_t>(grammar)) != 0 &&
      preferences.putUChar(kBrightnessKey, brightness) != 0 &&
      preferences.putUInt(kVersionKey, kSchemaVersion) != 0;
  if (!written) restoreRecord(preferences, prior);
  preferences.end();
  if (!written) return false;
  theme_ = theme;
  grammar_ = grammar;
  brightness_ = brightness;
  return true;
}
