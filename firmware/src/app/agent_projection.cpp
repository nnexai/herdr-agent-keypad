#include "agent_projection.h"

#include <Arduino.h>
#include <string.h>

#include "../board/board_adapter.h"
#include "../ui/theme.h"

namespace {
constexpr const char* kSourceStatuses[] = {"current", "empty", "stale", "unavailable", "offline"};
constexpr const char* kStates[] = {"empty", "working", "idle", "blocked", "finished", "settled", "unknown"};
constexpr const char* kLinkStates[] = {"current", "offline"};
constexpr const char* kCodexStates[] = {"current", "stale", "unavailable", "auth_required", "codex_offline", "host_offline"};
constexpr uint16_t kBackground = 0x0862;  // #0B0F14
bool validErrorCode(const char* value) {
  if (value == nullptr || value[0] == '\0') return value != nullptr;
  if (strlen(value) != 6 || value[0] != 'E' || value[1] != '-') return false;
  uint32_t code = 0;
  for (uint8_t index = 2; index < 6; ++index) {
    if (value[index] < '0' || value[index] > '9') return false;
    code = code * 10U + static_cast<uint32_t>(value[index] - '0');
  }
  return code >= 2400 && code <= 2410;
}
bool validSuffix(const char* value) {
  if (value == nullptr || value[0] == '\0' || strlen(value) > 6) return false;
  for (size_t index = 0; value[index] != '\0'; ++index) {
    const char c = value[index];
    if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) return false;
  }
  return true;
}

bool validVersion(const char* value) {
  if (value == nullptr || value[0] == '\0') return false;
  if (strcmp(value, "UNAVAL") == 0) return true;
  bool has_digit = false;
  for (size_t index = 0; value[index] != '\0'; ++index) {
    const char c = value[index];
    has_digit = has_digit || (c >= '0' && c <= '9');
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '.' || c == '+' || c == '-')) {
      return false;
    }
  }
  return has_digit;
}

LGFX_Sprite g_composition;
bool g_composition_ready = false;

bool ensureComposition() {
  if (g_composition_ready) return true;
  g_composition.setPsram(true);
  g_composition.setColorDepth(16);
  g_composition_ready = g_composition.createSprite(128, 128) != nullptr;
  if (g_composition_ready) g_composition.fillScreen(kBackground);
  return g_composition_ready;
}

bool listed(const char* value, const char* const* values, size_t count) {
  if (value == nullptr) return false;
  for (size_t index = 0; index < count; ++index) if (strcmp(value, values[index]) == 0) return true;
  return false;
}

bool printable(const char* value, bool allow_empty) {
  if (value == nullptr || (!allow_empty && value[0] == '\0')) return false;
  for (size_t index = 0; value[index] != '\0'; ++index) {
    const unsigned char byte = static_cast<unsigned char>(value[index]);
    if (byte < 0x20 || byte >= 0x80) return false;
  }
  return true;
}

bool elapsed(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}
uint8_t semanticEventPhase(uint32_t now_us, uint32_t started_us) {
  if (started_us == 0 ||
      static_cast<int32_t>(now_us - started_us) < 0) return 0;
  constexpr uint32_t kSemanticPhaseUs = 100000UL;
  return static_cast<uint8_t>(((now_us - started_us) / kSemanticPhaseUs) & 0x07U);
}

uint8_t menuPresentationProgress(const MenuState& menu, uint32_t now_us,
                                 AnimationScheduler::Level level) {
  if (level == AnimationScheduler::Level::Static) return 3;
  if (menu.presentation_duration_us == 0) return 3;
  const int32_t signed_elapsed =
      static_cast<int32_t>(now_us - menu.presentation_started_us);
  if (signed_elapsed <= 0) return menu.presentation_progress;
  const uint32_t elapsed_us = static_cast<uint32_t>(signed_elapsed);
  if (elapsed_us >= menu.presentation_duration_us) return 3;
  const uint32_t phase =
      (static_cast<uint64_t>(elapsed_us) * 4U) / menu.presentation_duration_us;
  return static_cast<uint8_t>(phase > 3 ? 3 : phase);
}


bool isSlotCardinalityCapture(CaptureScene scene) {
  return scene >= CaptureScene::SlotsZero && scene <= CaptureScene::SlotsThree;
}

uint8_t slotCardinality(CaptureScene scene) {
  if (!isSlotCardinalityCapture(scene)) return RenderState::kSlotCount;
  return static_cast<uint8_t>(scene) -
         static_cast<uint8_t>(CaptureScene::SlotsZero);
}

RenderState captureFixture(CaptureScene scene) {
  RenderState state;
  state.source_status = "current";
  state.blocked_pulse_high = true;
  for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
    RenderState::Slot& tile = state.slots[slot];
    tile.occupied = true;
    tile.title = "@DESIGNER-ONBOARDING.html";
    tile.discriminator = "lilygo-t3.long";
    tile.since = "5h42m";
    tile.age = "3m";
    tile.state = TileState::Working;
    tile.feedback = TileFeedback::Ready;
  }

  TileState tile_state = TileState::Working;
  TileFeedback feedback = TileFeedback::Ready;
  switch (scene) {
    case CaptureScene::Blocked: tile_state = TileState::Blocked; break;
    case CaptureScene::Unseen: tile_state = TileState::Unseen; break;
    case CaptureScene::Working: tile_state = TileState::Working; break;
    case CaptureScene::Idle: tile_state = TileState::Idle; break;
    case CaptureScene::Settled: tile_state = TileState::Settled; break;
    case CaptureScene::Unknown: tile_state = TileState::Unknown; break;
    case CaptureScene::Empty: tile_state = TileState::Empty; break;
    case CaptureScene::Stale: state.source_status = "stale"; break;
    case CaptureScene::Offline: state.source_status = "offline"; break;
    case CaptureScene::Unavailable: state.source_status = "unavailable"; break;
    case CaptureScene::Pending: feedback = TileFeedback::Pending; break;
    case CaptureScene::Focused: feedback = TileFeedback::Success; break;
    case CaptureScene::Rejected: feedback = TileFeedback::Rejected; break;
    case CaptureScene::Vanished: feedback = TileFeedback::Vanished; break;
    case CaptureScene::Uncertain: feedback = TileFeedback::Uncertain; break;
    case CaptureScene::Failed: feedback = TileFeedback::Failed; break;
    default: break;
  }
  const uint8_t occupied_count = slotCardinality(scene);
  for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
    state.slots[slot].state = tile_state;
    state.slots[slot].feedback = feedback;
    if (tile_state == TileState::Empty || slot >= occupied_count) {
      state.slots[slot].occupied = false;
      state.slots[slot].state = TileState::Empty;
      state.slots[slot].feedback = TileFeedback::Disabled;
    }
  }
  return state;
}

uint8_t capturePhase(CaptureLevel level, uint8_t phase) {
  if (level == CaptureLevel::Static) return 0;
  if (level == CaptureLevel::Half) return static_cast<uint8_t>(phase & 0xFE);
  return phase;
}

void applyCapturePresentation(RenderState& state, CaptureLevel level, uint8_t phase) {
  const uint8_t resolved = capturePhase(level, phase);
  state.ambient_phase = resolved;
  state.blocked_phase = resolved;
  state.transition_phase = static_cast<uint8_t>(resolved % AnimationScheduler::kTransitionPhaseCount);
  state.transition_active = level != CaptureLevel::Static;
  state.blocked_pulse_high = resolved < AnimationScheduler::kBlockedPhaseCount / 2U;
  for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
    state.slots[slot].feedback_phase = resolved;
  }
}

bool isCodexCapture(CaptureScene scene) {
  return scene >= CaptureScene::CodexCurrent && scene <= CaptureScene::CodexLong;
}

RenderState codexCaptureFixture(CaptureScene scene) {
  RenderState state = captureFixture(CaptureScene::Working);
  state.codex.source_state = CodexSourceState::Current;
  state.codex.primary = 42;
  state.codex.secondary = 78;
  state.codex.reset_text = "RESET 5H 01:20";
  state.codex.observation_age = "AGE 14M";
  state.codex.reached_limit = 0;
  state.codex.error_code = "";

  switch (scene) {
    case CaptureScene::CodexPartial:
      state.codex.primary = -1;
      state.codex.secondary = 7;
      state.codex.reset_text = "RESET WEEK 2D";
      state.codex.reached_limit = -1;
      break;
    case CaptureScene::CodexStale:
      state.codex.source_state = CodexSourceState::Stale;
      state.codex.observation_age = "AGE 18M";
      break;
    case CaptureScene::CodexUnavailable:
      state.codex.source_state = CodexSourceState::Unavailable;
      state.codex.primary = -1;
      state.codex.secondary = -1;
      state.codex.reset_text = "RESET N/A";
      state.codex.observation_age = "AGE N/A";
      state.codex.reached_limit = -1;
      state.codex.error_code = "E-2401";
      break;
    case CaptureScene::CodexAuthRequired:
      state.codex.source_state = CodexSourceState::AuthRequired;
      state.codex.primary = -1;
      state.codex.secondary = -1;
      state.codex.reset_text = "RESET N/A";
      state.codex.observation_age = "AGE N/A";
      state.codex.reached_limit = -1;
      state.codex.error_code = "E-2404";
      break;
    case CaptureScene::CodexOffline:
      state.codex.source_state = CodexSourceState::CodexOffline;
      state.codex.observation_age = "AGE 59M";
      state.codex.error_code = "E-2406";
      break;
    case CaptureScene::HostOffline:
      state.codex.source_state = CodexSourceState::HostOffline;
      state.codex.observation_age = "AGE 59M";
      state.codex.error_code = "E-2408";
      break;
    case CaptureScene::CodexLimit:
      state.codex.reached_limit = 1;
      break;
    case CaptureScene::CodexLong:
      state.codex.primary = 100;
      state.codex.secondary = 100;
      state.codex.reset_text = "RESET WEEK 999D";
      state.codex.observation_age = "AGE 999H";
      break;
    default:
      break;
  }
  return state;
}

bool isMenuCapture(CaptureScene scene) {
  return scene == CaptureScene::MenuTheme || scene == CaptureScene::MenuLed ||
         (scene >= CaptureScene::MenuRoot0 && scene <= CaptureScene::MenuAbout);
}

MenuState menuCaptureFixture(CaptureScene scene) {
  MenuState menu;
  menu.open = true;
  menu.theme_candidate = ThemeId::Instrument;
  menu.grammar_candidate = LedGrammarId::MeterLamps;
  menu.brightness_candidate = 100;
  menu.theme_stored = ThemeId::Instrument;
  menu.grammar_stored = LedGrammarId::MeterLamps;
  menu.brightness_stored = 100;
  menu.diagnostics.link_status = "offline";
  menu.diagnostics.herdr_status = "unavailable";
  menu.diagnostics.codex_status = "auth_required";
  menu.diagnostics.sync_age = "AGE 999H";
  menu.diagnostics.codex_age = "AGE 999H";
  menu.diagnostics.firmware_version = "2026.08.21-RC1";
  menu.diagnostics.protocol_version = 2;
  menu.diagnostics.bridge_version = "2026.08.21-RC1";
  menu.diagnostics.device_suffix = "ABCDEF";
  menu.diagnostics.session_suffix = "123456";
  menu.diagnostics.revision_suffix = "FEDCBA";
  menu.diagnostics.error_code = "E-2401";

  if (scene >= CaptureScene::MenuRoot0 && scene <= CaptureScene::MenuRoot5) {
    menu.page = MenuPage::Root;
    menu.cursor = static_cast<uint8_t>(scene) -
                  static_cast<uint8_t>(CaptureScene::MenuRoot0);
    menu.viewport_start = menu.cursor == 0 ? 0 :
                          (menu.cursor >= 4 ? 3 : menu.cursor - 1);
  } else if (scene == CaptureScene::MenuTheme) {
    menu.page = MenuPage::Theme;
    menu.cursor = 0;
    menu.editing = true;
  } else if (scene == CaptureScene::MenuLed) {
    menu.page = MenuPage::Leds;
    menu.cursor = 1;
    menu.editing = true;
  } else if (scene == CaptureScene::MenuBrightness) {
    menu.page = MenuPage::Brightness;
    menu.cursor = 2;
    menu.editing = true;
  } else if (scene == CaptureScene::MenuHealth) {
    menu.page = MenuPage::Health;
    menu.cursor = 3;
  } else if (scene == CaptureScene::MenuAbout) {
    menu.page = MenuPage::About;
    menu.cursor = 4;
  }
  return menu;
}
}  // namespace

AgentProjection::AgentProjection() : feedback_{} {
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) feedback_[slot] = Feedback::Disabled;
}

ThemeRenderer& AgentProjection::theme() const {
  return theme_ != nullptr ? *theme_ : signalEdgeTheme();
}

bool AgentProjection::copyBounded(char* destination, size_t capacity, const char* source, bool allow_empty) const {
  if (destination == nullptr || source == nullptr || strlen(source) >= capacity || !printable(source, allow_empty)) return false;
  strncpy(destination, source, capacity - 1);
  destination[capacity - 1] = '\0';
  return true;
}

bool AgentProjection::copyOptional(char* destination, size_t capacity, JsonVariantConst value, bool& present) const {
  if (value.isNull()) {
    destination[0] = '\0';
    present = false;
    return true;
  }
  const char* text = value.as<const char*>();
  if (!copyBounded(destination, capacity, text, false)) return false;
  present = true;
  return true;
}

bool AgentProjection::copyDisplay(char* destination, size_t capacity, const char* source, const char* fallback) const {
  if (source == nullptr || source[0] == '\0') source = fallback;
  if (source == nullptr || destination == nullptr || capacity < 4) return false;
  size_t length = strlen(source);
  if (length >= capacity) {
    length = capacity - 1;
    destination[length - 3] = '.';
    destination[length - 2] = '.';
    destination[length - 1] = '.';
    destination[length] = '\0';
    for (size_t index = 0; index < length - 3; ++index) {
      const unsigned char byte = static_cast<unsigned char>(source[index]);
      if (byte < 0x20 || byte >= 0x80) return false;
      destination[index] = source[index];
    }
    return true;
  }
  return copyBounded(destination, capacity, source, false);
}

AgentProjection::TileState AgentProjection::parseState(const char* state) const {
  if (state == nullptr) return TileState::Unknown;
  if (strcmp(state, "empty") == 0) return TileState::Empty;
  if (strcmp(state, "blocked") == 0) return TileState::Blocked;
  if (strcmp(state, "finished") == 0) return TileState::Unseen;
  if (strcmp(state, "working") == 0) return TileState::Working;
  if (strcmp(state, "idle") == 0) return TileState::Idle;
  if (strcmp(state, "settled") == 0) return TileState::Settled;
  return strcmp(state, "unknown") == 0 ? TileState::Unknown : TileState::Unknown;
}

bool AgentProjection::stageSnapshot(JsonObjectConst payload) {
  staged_codex_only_ = false;
  const char* epoch = payload["host_epoch"].as<const char*>();
  const char* source_status = payload["source_status"].as<const char*>();
  const uint32_t revision = payload["snapshot_revision"].as<uint32_t>();
  JsonArrayConst agents = payload["agents"].as<JsonArrayConst>();
  JsonObjectConst codex = payload["codex"].as<JsonObjectConst>();
  JsonObjectConst diagnostics = payload["diagnostics"].as<JsonObjectConst>();
  Generation candidate{};
  if (!copyBounded(candidate.host_epoch, sizeof(candidate.host_epoch), epoch, false) ||
      !copyBounded(candidate.source_status, sizeof(candidate.source_status), source_status, false) ||
      !listed(source_status, kSourceStatuses, sizeof(kSourceStatuses) / sizeof(kSourceStatuses[0])) ||
      revision == 0 || agents.isNull() || agents.size() != kSlotCount || codex.isNull() || diagnostics.isNull()) {
    staged_valid_ = false;
    return false;
  }
  if (committed_ && strcmp(committed_generation_.host_epoch, candidate.host_epoch) == 0 &&
      revision < committed_generation_.snapshot_revision) {
    staged_valid_ = false;
    return false;
  }
  candidate.snapshot_revision = revision;

  const char* codex_state = codex["source_state"].as<const char*>();
  const char* codex_error = codex["error_code"].as<const char*>();
  if (!codex_state || !listed(codex_state, kCodexStates, sizeof(kCodexStates) / sizeof(kCodexStates[0])) ||
      !copyBounded(candidate.codex_source_state, sizeof(candidate.codex_source_state), codex_state, false) ||
      !copyBounded(candidate.codex_reset_text, sizeof(candidate.codex_reset_text), codex["reset_text"].as<const char*>(), false) ||
      !copyBounded(candidate.codex_observation_age, sizeof(candidate.codex_observation_age), codex["observation_age"].as<const char*>(), false) ||
      !codex_error || !copyBounded(candidate.codex_error_code, sizeof(candidate.codex_error_code), codex_error, true) ||
      !validErrorCode(candidate.codex_error_code)) {
    staged_valid_ = false;
    return false;
  }
  for (int16_t* target : {&candidate.codex_primary, &candidate.codex_secondary}) {
    const char* key = target == &candidate.codex_primary ? "primary" : "secondary";
    JsonVariantConst value = codex[key];
    if (!value.isNull()) {
      if (!value.is<int>() || value.is<bool>()) {
        staged_valid_ = false;
        return false;
      }
      const int16_t percent = value.as<int16_t>();
      if (percent < 0 || percent > 100) {
        staged_valid_ = false;
        return false;
      }
      *target = percent;
    }
  }
  JsonVariantConst reached = codex["reached_limit"];
  if (!reached.isNull()) {
    if (!reached.is<bool>()) {
      staged_valid_ = false;
      return false;
    }
    candidate.codex_reached_limit = reached.as<bool>() ? 1 : 0;
  }
  if (strcmp(candidate.codex_error_code, "E-2401") == 0 &&
      (strcmp(candidate.codex_source_state, "unavailable") != 0 || candidate.codex_primary >= 0 ||
       candidate.codex_secondary >= 0 || strcmp(candidate.codex_reset_text, "RESET N/A") != 0 ||
       candidate.codex_reached_limit >= 0)) {
    staged_valid_ = false;
    return false;
  }

  const char* link_status = diagnostics["link_status"].as<const char*>();
  const char* herdr_status = diagnostics["herdr_status"].as<const char*>();
  const char* diagnostics_codex_status = diagnostics["codex_status"].as<const char*>();
  if (!link_status || !listed(link_status, kLinkStates, sizeof(kLinkStates) / sizeof(kLinkStates[0])) ||
      !copyBounded(candidate.diagnostics_link_status, sizeof(candidate.diagnostics_link_status), link_status, false) ||
      !herdr_status || !listed(herdr_status, kSourceStatuses, sizeof(kSourceStatuses) / sizeof(kSourceStatuses[0])) ||
      !copyBounded(candidate.diagnostics_herdr_status, sizeof(candidate.diagnostics_herdr_status), herdr_status, false) ||
      !diagnostics_codex_status || !listed(diagnostics_codex_status, kCodexStates, sizeof(kCodexStates) / sizeof(kCodexStates[0])) ||
      !copyBounded(candidate.diagnostics_codex_status, sizeof(candidate.diagnostics_codex_status), diagnostics_codex_status, false) ||
      !copyBounded(candidate.diagnostics_sync_age, sizeof(candidate.diagnostics_sync_age), diagnostics["sync_age"].as<const char*>(), false) ||
      !copyBounded(candidate.diagnostics_codex_age, sizeof(candidate.diagnostics_codex_age), diagnostics["codex_age"].as<const char*>(), false) ||
      !copyBounded(candidate.diagnostics_firmware_version, sizeof(candidate.diagnostics_firmware_version), diagnostics["firmware_version"].as<const char*>(), false) ||
      !validVersion(candidate.diagnostics_firmware_version) ||
      !copyBounded(candidate.diagnostics_bridge_version, sizeof(candidate.diagnostics_bridge_version), diagnostics["bridge_version"].as<const char*>(), false) ||
      !validVersion(candidate.diagnostics_bridge_version) ||
      !copyBounded(candidate.diagnostics_device_suffix, sizeof(candidate.diagnostics_device_suffix), diagnostics["device_suffix"].as<const char*>(), false) ||
      !validSuffix(candidate.diagnostics_device_suffix) ||
      !copyBounded(candidate.diagnostics_session_suffix, sizeof(candidate.diagnostics_session_suffix), diagnostics["session_suffix"].as<const char*>(), false) ||
      !validSuffix(candidate.diagnostics_session_suffix) ||
      !copyBounded(candidate.diagnostics_revision_suffix, sizeof(candidate.diagnostics_revision_suffix), diagnostics["revision_suffix"].as<const char*>(), false) ||
      !validSuffix(candidate.diagnostics_revision_suffix)) {
    staged_valid_ = false;
    return false;
  }
  JsonVariantConst protocol_version = diagnostics["protocol_version"];
  if (!protocol_version.is<int>() || protocol_version.is<bool>() || protocol_version.as<int>() != 2) {
    staged_valid_ = false;
    return false;
  }
  const char* diagnostics_error = diagnostics["error_code"].as<const char*>();
  if (!diagnostics_error ||
      !copyBounded(candidate.diagnostics_error_code, sizeof(candidate.diagnostics_error_code), diagnostics_error, true) ||
      !validErrorCode(candidate.diagnostics_error_code)) {
    staged_valid_ = false;
    return false;
  }

  bool seen[kSlotCount] = {};
  for (JsonObjectConst agent : agents) {
    const uint8_t slot = agent["slot"].as<uint8_t>();
    if (slot >= kSlotCount || seen[slot]) { staged_valid_ = false; return false; }
    seen[slot] = true;
    const char* state = agent["state"].as<const char*>();
    if (!listed(state, kStates, sizeof(kStates) / sizeof(kStates[0]))) { staged_valid_ = false; return false; }
    Tile& tile = candidate.tiles[slot];
    tile = Tile();
    tile.state = parseState(state);
    const bool empty = tile.state == TileState::Empty;
    const char* entry_id = agent["entry_id"].as<const char*>();
    const char* pane_id = agent["pane_id"].as<const char*>();
    const char* terminal_id = agent["terminal_id"].as<const char*>();
    bool workspace_present = false;
    bool tab_present = false;
    if (!copyBounded(tile.binding.entry_id, sizeof(tile.binding.entry_id), entry_id, empty) ||
        !copyBounded(tile.binding.pane_id, sizeof(tile.binding.pane_id), pane_id, empty) ||
        !copyBounded(tile.binding.terminal_id, sizeof(tile.binding.terminal_id), terminal_id, empty) ||
        !copyOptional(tile.binding.workspace_id, sizeof(tile.binding.workspace_id), agent["workspace_id"], workspace_present) ||
        !copyOptional(tile.binding.tab_id, sizeof(tile.binding.tab_id), agent["tab_id"], tab_present) ||
        !copyOptional(tile.binding.agent_session, sizeof(tile.binding.agent_session), agent["agent_session"], tile.binding.has_agent_session) ||
        !copyDisplay(tile.title, sizeof(tile.title), agent["title"].as<const char*>(), "NO AGENT") ||
        !copyDisplay(tile.discriminator, sizeof(tile.discriminator), agent["discriminator"].as<const char*>(), "NO WORKSPACE") ||
        !copyDisplay(tile.since, sizeof(tile.since), agent["since"].as<const char*>(), "-") ||
        !copyDisplay(tile.age, sizeof(tile.age), agent["age"].as<const char*>(), "-")) {
      staged_valid_ = false;
      return false;
    }
    tile.binding.source_revision = agent["source_revision"].as<uint32_t>();
    tile.binding.occupied = !empty;
    if (tile.binding.occupied && tile.binding.source_revision == 0) { staged_valid_ = false; return false; }
    if (!tile.binding.occupied && tile.binding.source_revision != 0) { staged_valid_ = false; return false; }
  }
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) if (!seen[slot]) { staged_valid_ = false; return false; }
  if (committed_ &&
      strcmp(committed_generation_.host_epoch, candidate.host_epoch) == 0 &&
      revision == committed_generation_.snapshot_revision) {
    if (strcmp(committed_generation_.source_status, candidate.source_status) != 0 ||
        memcmp(committed_generation_.tiles, candidate.tiles,
               sizeof(candidate.tiles)) != 0) {
      staged_valid_ = false;
      return false;
    }
    staged_codex_only_ = true;
  }
  staged_ = candidate;
  staged_valid_ = true;
  return true;
}

void AgentProjection::beginSemanticEvent(uint32_t now_us) {
  ++semantic_event_epoch_;
  if (semantic_event_epoch_ == 0) semantic_event_epoch_ = 1;
  semantic_event_started_us_ = now_us != 0 ? now_us : 1;
}

void AgentProjection::disableActive(BoardAdapter* board) {
  committed_ = false;
  syncing_ = true;
  beginSemanticEvent(micros());
  animation_.interruptTransition(staged_.snapshot_revision);
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    pending_[slot] = Binding();
    pending_action_[slot] = 0;
    pending_action_text_[slot][0] = '\0';
    pending_deadline_[slot] = 0;
    pending_step_[slot] = 0;
    feedback_until_[slot] = 0;
    press_impulse_[slot] = false;
    feedback_phase_[slot] = 0;
    feedback_[slot] = Feedback::Disabled;
  }
  if (board != nullptr) renderSync(*board);
}
bool AgentProjection::commitSnapshot() {
  const bool animate = transition_after_commit_ || committed_;
  transition_after_commit_ = false;
  committed_generation_ = staged_;
  const uint32_t event_started_us = micros();
  beginSemanticEvent(event_started_us);
  staged_valid_ = false;
  staged_codex_only_ = false;
  const bool urgent = strcmp(committed_generation_.source_status, "current") != 0;
  if (urgent || !animate) {
    animation_.interruptTransition(committed_generation_.snapshot_revision);
  } else {
    animation_.beginTransition(committed_generation_.snapshot_revision, event_started_us);
  }
  if (!committed_) {
    committed_ = true;
    syncing_ = false;
  }
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    pending_[slot] = Binding();
    pending_action_[slot] = 0;
    pending_deadline_[slot] = 0;
    pending_step_[slot] = 0;
    press_impulse_[slot] = false;
    feedback_phase_[slot] = 0;
    feedback_[slot] = (committed_generation_.tiles[slot].binding.occupied && !urgent)
                          ? Feedback::Ready : Feedback::Disabled;
  }
  return true;
}
bool AgentProjection::commitSnapshot(BoardAdapter& board) {
  MenuState closed;
  return commitSnapshot(board, theme(), closed);
}

bool AgentProjection::commitSnapshot(BoardAdapter& board, ThemeRenderer& panel4_theme,
                                     const MenuState& menu) {
  if (!staged_valid_ || !ensureComposition()) return false;
  transition_after_commit_ = committed_;
  if (staged_codex_only_) {
    Display* display = board.displayAt(3);
    if (display == nullptr) {
      staged_valid_ = false;
      staged_codex_only_ = false;
      return false;
    }
    const bool animate = transition_after_commit_;
    transition_after_commit_ = false;
    committed_generation_ = staged_;
    const uint32_t event_started_us = micros();
    beginSemanticEvent(event_started_us);
    staged_valid_ = false;
    staged_codex_only_ = false;
    if (animate && strcmp(committed_generation_.source_status, "current") == 0) {
      animation_.beginTransition(committed_generation_.snapshot_revision, event_started_us);
    } else {
      animation_.interruptTransition(committed_generation_.snapshot_revision);
    }
    if (menu.open) {
      renderMenu(board, panel4_theme, menu);
    } else {
      theme().composePanel4(g_composition, renderState(micros()));
      g_composition.pushSprite(display, 0, 0);
    }
    return true;
  }
  // Per-panel direct-cut reveal (R-2): panels flip old-complete -> new-complete
  // sequentially with no SYNC veil for ordinary refreshes.  Bindings deactivate
  // here at stage time and activate only after the third flush, so a press
  // during the reveal window can never bind to mixed pixels.  Boot, session
  // reset, and any compose/flush failure keep the SYNC presentation.
  disableActive(nullptr);
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    if (!renderTile(board, theme(), staged_, slot, staged_.tiles[slot],
                    Feedback::Disabled)) {
      staged_valid_ = false;
      syncing_ = true;
      renderSync(board);  // best-effort fail-closed SYNC on all panels
      return false;
    }
#ifdef ARDUINO
    // Snapshot flushes are long enough to overlap a normal human press. Keep
    // ButtonSense sampling between panels; BoardAdapter latches the edge until
    // the normal input dispatcher consumes it after the commit.
    board.update();
#endif
  }
  return commitSnapshot();
}

bool AgentProjection::renderSync(BoardAdapter& board) const {
  if (!ensureComposition()) return false;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    Display* display = board.displayAt(slot);
    if (display == nullptr) return false;
    theme().composeSync(g_composition);
    g_composition.pushSprite(display, 0, 0);
  }
  return true;
}

bool AgentProjection::renderTile(BoardAdapter& board, uint8_t slot, const Tile& tile,
                                 Feedback feedback) const {
  return renderTileAt(board, slot, tile, feedback, micros());
}
bool AgentProjection::renderTileAt(BoardAdapter& board, uint8_t slot, const Tile& tile,
                                   Feedback feedback, uint32_t now_us) const {
  return renderTileAt(board, theme(), committed_generation_, slot, tile, feedback, now_us);
}
bool AgentProjection::renderTile(BoardAdapter& board, ThemeRenderer& renderer,
                                 uint8_t slot, const Tile& tile, Feedback feedback) const {
  return renderTileAt(board, renderer, slot, tile, feedback, micros());
}
bool AgentProjection::renderTileAt(BoardAdapter& board, ThemeRenderer& renderer,
                                   uint8_t slot, const Tile& tile, Feedback feedback,
                                   uint32_t now_us) const {
  return renderTileAt(board, renderer, committed_generation_, slot, tile, feedback, now_us);
}
bool AgentProjection::renderTile(BoardAdapter& board, ThemeRenderer& renderer,
                                 const Generation& generation, uint8_t slot, const Tile& tile,
                                 Feedback feedback) const {
  return renderTileAt(board, renderer, generation, slot, tile, feedback, micros());
}
bool AgentProjection::renderTileAt(BoardAdapter& board, ThemeRenderer& renderer,
                                   const Generation& generation, uint8_t slot, const Tile& tile,
                                   Feedback feedback, uint32_t now_us) const {
  Display* display = board.displayAt(slot);
  if (display == nullptr || !ensureComposition()) return false;
  RenderState state;
  state.source_status = generation.source_status;
  state.syncing = syncing_;
  state.transition_epoch = animation_.transitionEpoch();
  state.semantic_event_epoch = semantic_event_epoch_;
  state.semantic_event_started_us = semantic_event_started_us_;
  state.semantic_event_phase = semanticEventPhase(now_us, semantic_event_started_us_);
  state.transition_active =
      strcmp(generation.source_status, "current") == 0 &&
      !syncing_ && animation_.level() != AnimationScheduler::Level::Static &&
      animation_.transitionActive();
  state.transition_phase = state.transition_active ? animation_.transitionProgress(now_us) :
                           AnimationScheduler::kNeutralPhase;
  state.ambient_phase = animation_.presentationPhase(now_us);
  state.blocked_phase = animation_.blockedPhase(now_us);
  state.blocked_pulse_high = animation_.blockedPulseHigh(now_us);
  RenderState::Slot& out = state.slots[slot];
  out.occupied = tile.binding.occupied;
  out.title = tile.title;
  out.discriminator = tile.discriminator;
  out.since = tile.since;
  out.age = tile.age;
  out.state = tile.state;
  out.feedback_phase = feedback_phase_[slot];
  out.press_impulse = press_impulse_[slot];
  state.codex.source_state = strcmp(generation.codex_source_state, "current") == 0 ? CodexSourceState::Current :
                             strcmp(generation.codex_source_state, "stale") == 0 ? CodexSourceState::Stale :
                             strcmp(generation.codex_source_state, "auth_required") == 0 ? CodexSourceState::AuthRequired :
                             strcmp(generation.codex_source_state, "codex_offline") == 0 ? CodexSourceState::CodexOffline :
                             strcmp(generation.codex_source_state, "host_offline") == 0 ? CodexSourceState::HostOffline :
                             CodexSourceState::Unavailable;
  state.codex.primary = generation.codex_primary;
  state.codex.secondary = generation.codex_secondary;
  state.codex.reset_text = generation.codex_reset_text;
  state.codex.observation_age = generation.codex_observation_age;
  state.codex.reached_limit = generation.codex_reached_limit;
  state.codex.error_code = generation.codex_error_code;
  state.diagnostics.link_status = generation.diagnostics_link_status;
  state.diagnostics.herdr_status = generation.diagnostics_herdr_status;
  state.diagnostics.codex_status = generation.diagnostics_codex_status;
  state.diagnostics.sync_age = generation.diagnostics_sync_age;
  state.diagnostics.codex_age = generation.diagnostics_codex_age;
  state.diagnostics.firmware_version = generation.diagnostics_firmware_version;
  state.diagnostics.protocol_version = generation.diagnostics_protocol_version;
  state.diagnostics.bridge_version = generation.diagnostics_bridge_version;
  state.diagnostics.device_suffix = generation.diagnostics_device_suffix;
  state.diagnostics.session_suffix = generation.diagnostics_session_suffix;
  state.diagnostics.revision_suffix = generation.diagnostics_revision_suffix;
  state.diagnostics.error_code = generation.diagnostics_error_code;
  out.feedback = feedback;
  renderer.composeTile(g_composition, slot, state);
  g_composition.pushSprite(display, 0, 0);
  animation_.noteCompleteFrame();
  return true;
}

void AgentProjection::tick(BoardAdapter& board, uint32_t now_us) {
  animation_.beginFrameWindow();
  if (!committed_ || syncing_) return;

  bool feedback_dirty = false;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    if (pending_action_[slot] != 0 && elapsed(now_us, pending_deadline_[slot])) {
      pending_action_[slot] = 0;
      pending_[slot] = Binding();
      pending_deadline_[slot] = 0;
      pending_step_[slot] = 0;
      press_impulse_[slot] = false;
      feedback_phase_[slot] = 0;
      feedback_[slot] = Feedback::Uncertain;
      beginSemanticEvent(now_us);
      feedback_until_[slot] = now_us + kFeedbackHoldUs;
      renderTileAt(board, slot, committed_generation_.tiles[slot], feedback_[slot], now_us);
      feedback_dirty = true;
    } else if (pending_action_[slot] != 0 &&
               pending_step_[slot] != 0 && elapsed(now_us, pending_step_[slot])) {
      pending_step_[slot] = now_us + kPendingStepUs;
      feedback_phase_[slot] = static_cast<uint8_t>((feedback_phase_[slot] + 1U) % 8U);
      renderTileAt(board, slot, committed_generation_.tiles[slot], feedback_[slot], now_us);
      feedback_dirty = true;
    } else if (pending_action_[slot] == 0 && feedback_until_[slot] != 0 &&
               elapsed(now_us, feedback_until_[slot])) {
      feedback_until_[slot] = 0;
      feedback_[slot] = (committed_generation_.tiles[slot].binding.occupied &&
                         strcmp(committed_generation_.source_status, "current") == 0)
                            ? Feedback::Ready : Feedback::Disabled;
      renderTileAt(board, slot, committed_generation_.tiles[slot], feedback_[slot], now_us);
      feedback_dirty = true;
    }
  }

  // Urgent source truth and immediate feedback always win over motion.
  if (feedback_dirty || strcmp(committed_generation_.source_status, "current") != 0) return;

  if (animation_.level() != AnimationScheduler::Level::Static &&
      animation_.transitionDue(now_us)) {
    // Every transition sample is a complete frame for every panel. The
    // renderer moves only presentation accents; identity and state remain
    // committed and stable.
    for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
      renderTileAt(board, slot, committed_generation_.tiles[slot], feedback_[slot], now_us);
    }
    return;
  }

  const bool blocked_frame = animation_.blockedFrameDue(now_us);
  const bool ambient_frame = animation_.ambientFrameDue(now_us);
  if (!blocked_frame && !ambient_frame) return;
  const uint8_t ambient_mask = ambient_frame ? theme().ambientTick(now_us) : 0;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    const bool feedback_active = feedback_[slot] != Feedback::Ready &&
                                 feedback_[slot] != Feedback::Disabled;
    const bool blocked_dirty = blocked_frame &&
                               committed_generation_.tiles[slot].state == TileState::Blocked;
    const bool ambient_dirty = (ambient_mask & static_cast<uint8_t>(1U << slot)) != 0;
    if (feedback_active) continue;
    if (blocked_dirty || (ambient_dirty && !feedback_active)) {
      renderTileAt(board, slot, committed_generation_.tiles[slot], feedback_[slot], now_us);
    }
  }
}

void AgentProjection::renderMenu(BoardAdapter& board, ThemeRenderer& theme,
                                 const MenuState& menu) const {
  Display* display = board.displayAt(3);
  if (display == nullptr || !ensureComposition()) return;
  const uint32_t now_us = micros();
  if (menu.open) {
    MenuState frame = menu;
    frame.presentation_progress =
        menuPresentationProgress(menu, now_us, animation_.level());
    frame.diagnostics = renderState(now_us).diagnostics;
    theme.composeMenu(g_composition, frame);
  } else {
    theme.composePanel4(g_composition, renderState(now_us));
  }
  g_composition.pushSprite(display, 0, 0);
}

bool AgentProjection::redrawTiles(BoardAdapter& board) {
  return redrawTiles(board, theme());
}

bool AgentProjection::redrawTiles(BoardAdapter& board, ThemeRenderer& candidate) {
  if (!committed_ || syncing_) return false;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    if (!renderTile(board, candidate, slot, committed_generation_.tiles[slot], feedback_[slot])) {
      disableActive(&board);
      return false;
    }
  }
  theme_ = &candidate;
  return true;
}
bool AgentProjection::capturePanel(uint8_t panel, ThemeRenderer* renderer,
                                   CaptureScene scene, CaptureLevel level,
                                   uint8_t phase) {
  if (panel >= 4 || !ensureComposition() || phase >= kCapturePhaseCount) return false;
  ThemeRenderer& selected = renderer != nullptr ? *renderer : theme();
  if (scene == CaptureScene::Sync) {
    selected.composeSync(g_composition);
    return true;
  }
  if (isMenuCapture(scene)) {
    if (panel != 3) return false;
    MenuState menu = menuCaptureFixture(scene);
    menu.presentation_cause = MenuPresentationCause::Navigate;
    menu.presentation_direction = (phase & 1U) == 0 ? -1 : 1;
    menu.presentation_progress =
        level == CaptureLevel::Static ? 3 : static_cast<uint8_t>(capturePhase(level, phase) % 4);
    selected.composeMenu(g_composition, menu);
    return true;
  }
  RenderState state =
      scene == CaptureScene::Current ? renderState(micros()) :
      (isCodexCapture(scene) ? codexCaptureFixture(scene) : captureFixture(scene));
  applyCapturePresentation(state, level, phase);
  if (panel < kSlotCount) selected.composeTile(g_composition, panel, state);
  else selected.composePanel4(g_composition, state);
  return true;
}
const uint16_t* AgentProjection::capturePixels() const {
  return static_cast<const uint16_t*>(g_composition.getBuffer());
}

void AgentProjection::renderFeedback(BoardAdapter& board, uint8_t slot) {
  if (slot >= kSlotCount || !committed_ || syncing_) return;
  renderTile(board, slot, committed_generation_.tiles[slot], feedback_[slot]);
  // captureFocusIntent arms exactly one complete-frame physical cue. Clearing
  // only after composition keeps the next frame honest PENDING.
  press_impulse_[slot] = false;
}

bool AgentProjection::hasBinding(uint8_t slot) const {
  // Feedback is presentation-only. A current occupied binding remains
  // actionable after any terminal result so a fast retry is never swallowed
  // by the feedback hold timer; only an in-flight action suppresses duplicates.
  return committed_ && !syncing_ && slot < kSlotCount && committed_generation_.tiles[slot].binding.occupied &&
         strcmp(committed_generation_.source_status, "current") == 0;
}

AgentProjection::Feedback AgentProjection::feedback(uint8_t slot) const { return slot < kSlotCount ? feedback_[slot] : Feedback::Disabled; }
AgentProjection::TileState AgentProjection::state(uint8_t slot) const { return slot < kSlotCount ? committed_generation_.tiles[slot].state : TileState::Unavailable; }
const char* AgentProjection::title(uint8_t slot) const { return slot < kSlotCount ? committed_generation_.tiles[slot].title : ""; }
const char* AgentProjection::discriminator(uint8_t slot) const { return slot < kSlotCount ? committed_generation_.tiles[slot].discriminator : ""; }

RenderState AgentProjection::renderState(uint32_t now_us) const {
  RenderState state;
  state.source_status = committed_generation_.source_status;
  state.syncing = syncing_;
  state.transition_epoch = animation_.transitionEpoch();
  state.semantic_event_epoch = semantic_event_epoch_;
  state.semantic_event_started_us = semantic_event_started_us_;
  state.semantic_event_phase = semanticEventPhase(now_us, semantic_event_started_us_);
  state.transition_active =
      strcmp(committed_generation_.source_status, "current") == 0 &&
      !syncing_ && animation_.level() != AnimationScheduler::Level::Static &&
      animation_.transitionActive();
  state.transition_phase = state.transition_active ? animation_.transitionProgress(now_us) :
                           AnimationScheduler::kNeutralPhase;
  state.ambient_phase = animation_.presentationPhase(now_us);
  state.blocked_phase = animation_.blockedPhase(now_us);
  state.blocked_pulse_high = animation_.blockedPulseHigh(now_us);
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    RenderState::Slot& output = state.slots[slot];
    const Tile& tile = committed_generation_.tiles[slot];
    output.occupied = tile.binding.occupied;
    output.title = tile.title;
    output.discriminator = tile.discriminator;
    output.since = tile.since;
    output.state = tile.state;
    output.feedback = feedback_[slot];
    output.feedback_phase = feedback_phase_[slot];
    output.press_impulse = press_impulse_[slot];
  }
  state.codex.source_state = strcmp(committed_generation_.codex_source_state, "current") == 0 ? CodexSourceState::Current :
                             strcmp(committed_generation_.codex_source_state, "stale") == 0 ? CodexSourceState::Stale :
                             strcmp(committed_generation_.codex_source_state, "auth_required") == 0 ? CodexSourceState::AuthRequired :
                             strcmp(committed_generation_.codex_source_state, "codex_offline") == 0 ? CodexSourceState::CodexOffline :
                             strcmp(committed_generation_.codex_source_state, "host_offline") == 0 ? CodexSourceState::HostOffline :
                             CodexSourceState::Unavailable;
  state.codex.primary = committed_generation_.codex_primary;
  state.codex.secondary = committed_generation_.codex_secondary;
  state.codex.reset_text = committed_generation_.codex_reset_text;
  state.codex.observation_age = committed_generation_.codex_observation_age;
  state.codex.reached_limit = committed_generation_.codex_reached_limit;
  state.codex.error_code = committed_generation_.codex_error_code;
  state.diagnostics.link_status = committed_generation_.diagnostics_link_status;
  state.diagnostics.herdr_status = committed_generation_.diagnostics_herdr_status;
  state.diagnostics.codex_status = committed_generation_.diagnostics_codex_status;
  state.diagnostics.sync_age = committed_generation_.diagnostics_sync_age;
  state.diagnostics.codex_age = committed_generation_.diagnostics_codex_age;
  state.diagnostics.firmware_version = committed_generation_.diagnostics_firmware_version;
  state.diagnostics.protocol_version = committed_generation_.diagnostics_protocol_version;
  state.diagnostics.bridge_version = committed_generation_.diagnostics_bridge_version;
  state.diagnostics.device_suffix = committed_generation_.diagnostics_device_suffix;
  state.diagnostics.session_suffix = committed_generation_.diagnostics_session_suffix;
  state.diagnostics.revision_suffix = committed_generation_.diagnostics_revision_suffix;
  state.diagnostics.error_code = committed_generation_.diagnostics_error_code;
  return state;
}

bool AgentProjection::captureFocusIntent(uint8_t key, const char* action_id, JsonObject payload) {
  // A new physical press supersedes the previous request for this tile. The
  // old result is rejected by action-id correlation; the newest press remains
  // the visible pending action and is the one that determines the final state.
  if (!committed_ || syncing_ || key >= kSlotCount || action_id == nullptr || !hasBinding(key) ||
      !copyBounded(pending_action_text_[key], sizeof(pending_action_text_[key]), action_id, false)) return false;
  pending_[key] = committed_generation_.tiles[key].binding;
  pending_action_[key] = next_action_++;
  if (next_action_ == 0) next_action_ = 1;
  const uint32_t started = micros();
  beginSemanticEvent(started);
  pending_deadline_[key] = started + kPendingDeadlineUs;
  pending_step_[key] = started + kPendingStepUs;
  press_impulse_[key] = true;
  feedback_phase_[key] = 0;
  feedback_[key] = Feedback::Pending;
  payload["action_id"] = pending_action_text_[key];
  if (pending_[key].has_agent_session) payload["agent_session"] = pending_[key].agent_session; else payload["agent_session"] = nullptr;
  payload["entry_id"] = pending_[key].entry_id;
  payload["host_epoch"] = committed_generation_.host_epoch;
  payload["pane_id"] = pending_[key].pane_id;
  payload["slot"] = key;
  payload["snapshot_revision"] = committed_generation_.snapshot_revision;
  payload["source_revision"] = pending_[key].source_revision;
  payload["terminal_id"] = pending_[key].terminal_id;
  return true;
}

bool AgentProjection::matchingResult(JsonObjectConst payload, const Binding& binding, uint8_t slot) const {
  const char* entry = payload["entry_id"].as<const char*>();
  const char* pane = payload["pane_id"].as<const char*>();
  const char* terminal = payload["terminal_id"].as<const char*>();
  if (payload["slot"].as<uint8_t>() != slot || entry == nullptr || pane == nullptr || terminal == nullptr ||
      strcmp(entry, binding.entry_id) != 0 || strcmp(pane, binding.pane_id) != 0 || strcmp(terminal, binding.terminal_id) != 0 ||
      payload["source_revision"].as<uint32_t>() != binding.source_revision) return false;
  const JsonVariantConst session = payload["agent_session"];
  if (binding.has_agent_session) return !session.isNull() && strcmp(session.as<const char*>(), binding.agent_session) == 0;
  return session.isNull();
}

bool AgentProjection::applyFocusResult(JsonObjectConst payload) {
  const uint8_t slot = payload["slot"].as<uint8_t>();
  const char* action = payload["action_id"].as<const char*>();
  const char* epoch = payload["host_epoch"].as<const char*>();
  const char* outcome = payload["outcome"].as<const char*>();
  if (!committed_ || syncing_ || slot >= kSlotCount || pending_action_[slot] == 0 || action == nullptr || epoch == nullptr || outcome == nullptr ||
      strcmp(action, pending_action_text_[slot]) != 0 || strcmp(epoch, committed_generation_.host_epoch) != 0 ||
      payload["snapshot_revision"].as<uint32_t>() != committed_generation_.snapshot_revision || !matchingResult(payload, pending_[slot], slot)) return false;
  pending_action_[slot] = 0;
  pending_[slot] = Binding();
  pending_deadline_[slot] = 0;
  pending_step_[slot] = 0;
  press_impulse_[slot] = false;
  feedback_phase_[slot] = 0;
  const uint32_t result_started_us = micros();
  beginSemanticEvent(result_started_us);
  if (strcmp(outcome, "accepted") == 0 && payload["focused"].as<bool>()) feedback_[slot] = Feedback::Success;
  else if (strcmp(outcome, "stale_target") == 0) feedback_[slot] = Feedback::Stale;
  else if (strcmp(outcome, "vanished") == 0 || strcmp(outcome, "not_found") == 0) feedback_[slot] = Feedback::Vanished;
  else if (strcmp(outcome, "herdr_offline") == 0) feedback_[slot] = Feedback::Offline;
  else if (strcmp(outcome, "timeout") == 0 || strcmp(outcome, "uncertain") == 0) feedback_[slot] = Feedback::Uncertain;
  else if (strcmp(outcome, "failed") == 0) feedback_[slot] = Feedback::Failed;
  else feedback_[slot] = Feedback::Rejected;
  feedback_until_[slot] = result_started_us + (feedback_[slot] == Feedback::Success ? kSuccessHoldUs : kFeedbackHoldUs);
  return feedback_[slot] == Feedback::Success;
}
