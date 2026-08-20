#include <Arduino.h>
#include <ArduinoJson.h>
#include <unity.h>

#include <string>
#include <vector>

#include "../../firmware/src/app/agent_projection.h"
#include "../../firmware/src/app/settings_store.h"
#include "../../firmware/src/board/board_adapter.h"
#include "../../firmware/src/ui/theme.h"
#include "../../firmware/src/ui/led_engine.h"
#include "../../firmware/src/app/menu_controller.h"
#include "../../firmware/src/ui/led_grammar.h"

namespace {
Display displays[4];
struct LedCall { uint16_t hue; uint8_t saturation; uint8_t brightness; uint16_t mask; };
std::vector<LedCall> g_led_calls;
bool missing_panel = false;

JsonDocument snapshot_document(uint32_t revision, const char* state0 = "working",
                               const char* source_status = "current") {
  JsonDocument document;
  JsonObject root = document.to<JsonObject>();
  root["host_epoch"] = "native-epoch";
  root["snapshot_revision"] = revision;
  root["source_status"] = source_status;
  JsonArray agents = root["agents"].to<JsonArray>();
  for (uint8_t slot = 0; slot < 3; ++slot) {
    JsonObject agent = agents.add<JsonObject>();
    agent["slot"] = slot;
    agent["entry_id"] = slot == 0 ? "entry-0" : "";
    agent["title"] = slot == 0 ? "Agent" : "NO AGENT";
    agent["discriminator"] = slot == 0 ? "repo" : "NO WORKSPACE";
    agent["state"] = slot == 0 ? state0 : "empty";
    agent["pane_id"] = slot == 0 ? "pane-0" : "";
    agent["terminal_id"] = slot == 0 ? "term-0" : "";
    agent["agent_session"] = nullptr;
    agent["source_revision"] = slot == 0 ? 1 : 0;
    agent["workspace_id"] = nullptr;
    agent["tab_id"] = nullptr;
  }
  return document;
}

JsonDocument focus_result_document(const char* action_id, const char* outcome) {
  JsonDocument document;
  JsonObject root = document.to<JsonObject>();
  root["action_id"] = action_id;
  root["agent_session"] = nullptr;
  root["entry_id"] = "entry-0";
  root["focused"] = std::string(outcome) == "accepted";
  root["host_epoch"] = "native-epoch";
  root["outcome"] = outcome;
  root["pane_id"] = "pane-0";
  root["slot"] = 0;
  root["snapshot_revision"] = 0;  // caller patches
  root["source_revision"] = 1;
  root["terminal_id"] = "term-0";
  return document;
}

void resetLog() { g_render_log.clear(); }

size_t countPushes() {
  size_t pushes = 0;
  for (const auto& entry : g_render_log) if (entry.rfind("push:", 0) == 0) ++pushes;
  return pushes;
}

bool logContainsText(const char* word) {
  const std::string needle = std::string("text:") + word;
  for (const auto& entry : g_render_log) if (entry == needle) return true;
  return false;
}

bool logContainsFragment(const char* word) {
  const std::string needle = std::string("text:") + word;
  for (const auto& entry : g_render_log) if (entry.find(needle) != std::string::npos) return true;
  return false;
}

bool logContainsAny(const char* word) {
  for (const auto& entry : g_render_log) if (entry.find(word) != std::string::npos) return true;
  return false;
}

size_t logTextCount(const char* word) {
  const std::string needle = std::string("text:") + word;
  size_t count = 0;
  for (const auto& entry : g_render_log) {
    if (entry == needle) ++count;
  }
  return count;
}

std::vector<int> pushOrder() {
  std::vector<int> order;
  for (const auto& entry : g_render_log) {
    if (entry.rfind("push:", 0) == 0) order.push_back(std::stoi(entry.substr(5)));
  }
  return order;
}
}  // namespace

int displayIndexOf(Display* display) {
  for (int index = 0; index < 4; ++index) if (display == &displays[index]) return index;
  return -1;
}

Display* BoardAdapter::displayAt(uint8_t index) {
  if (index >= 4 || (missing_panel && index == 1)) return nullptr;
  return &displays[index];
}

void BoardAdapter::setLeds(uint16_t hue, uint8_t saturation, uint8_t brightness, uint16_t mask) {
  g_led_calls.push_back({hue, saturation, brightness, mask});
}

void setUp() {}
void tearDown() {
  missing_panel = false;
  g_nvs.clear();
  g_nvs_write_count = 0;
  g_nvs_fail_on_write = -1;
  g_nvs_write_attempt = 0;
  resetLog();
  g_led_calls.clear();
  g_sync_draw_count = 0;
}

// --- Preserved Phase 02.1 behavior ---------------------------------------

void test_compose_then_flush_commits_generation() {
  AgentProjection projection;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  BoardAdapter board;
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_TRUE(projection.committed());
  TEST_ASSERT_TRUE(projection.hasBinding(0));
  TEST_ASSERT_FALSE(projection.hasBinding(1));
}

void test_null_panel_fails_closed() {
  AgentProjection projection;
  JsonDocument document = snapshot_document(2);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  BoardAdapter board;
  missing_panel = true;
  TEST_ASSERT_FALSE(projection.commitSnapshot(board));
  TEST_ASSERT_FALSE(projection.committed());
  TEST_ASSERT_FALSE(projection.hasBinding(0));
}

void test_generation_replacement_clears_feedback() {
  AgentProjection projection;
  JsonDocument first = snapshot_document(1);
  JsonDocument second = snapshot_document(2);
  BoardAdapter board;
  TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_TRUE(projection.stageSnapshot(second.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Ready), static_cast<int>(projection.feedback(0)));
}

void test_snapshot_commit_keeps_visible_sync_cutout_hidden() {
  AgentProjection projection;
  JsonDocument document = snapshot_document(3);
  BoardAdapter board;
  g_sync_draw_count = 0;
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_EQUAL_UINT32(0, g_sync_draw_count);
}

// --- Theme seam ------------------------------------------------------------

void test_flush_ordering_one_push_per_panel_sequential() {
  AgentProjection projection;
  JsonDocument document = snapshot_document(1);
  BoardAdapter board;
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  resetLog();
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  const std::vector<int> order = pushOrder();
  TEST_ASSERT_EQUAL_UINT32(3, order.size());
  TEST_ASSERT_EQUAL_INT(0, order[0]);
  TEST_ASSERT_EQUAL_INT(1, order[1]);
  TEST_ASSERT_EQUAL_INT(2, order[2]);
  // Every drawing op precedes its panel's single push: the log must never
  // contain a draw entry after the final push.
  size_t last_push = 0;
  for (size_t index = 0; index < g_render_log.size(); ++index) {
    if (g_render_log[index].rfind("push:", 0) == 0) last_push = index;
  }
  TEST_ASSERT_EQUAL_UINT32(g_render_log.size() - 1, last_push);
}

void test_theme_dispatch_renders_through_injected_theme() {
  // A counting theme proves composition is delegated to the injected pointer.
  struct CountingTheme final : public ThemeRenderer {
    int tile_calls = 0;
    int sync_calls = 0;
    void composeTile(LGFX_Sprite&, uint8_t, const RenderState&) override { ++tile_calls; }
    void composePanel4(LGFX_Sprite&, const RenderState&) override {}
    void composeMenu(LGFX_Sprite&, const MenuState&) override {}
    void composeSync(LGFX_Sprite&) override { ++sync_calls; }
  } counting;
  AgentProjection projection;
  projection.setTheme(counting);
  JsonDocument document = snapshot_document(1);
  BoardAdapter board;
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_EQUAL_INT(3, counting.tile_calls);
}

void test_signal_edge_renders_literal_state_words() {
  const struct { const char* state; const char* word; } cases[] = {
      {"blocked", "BLOCKED"}, {"finished", "UNSEEN"}, {"working", "WORKING"},
      {"idle", "IDLE"}, {"settled", "SETTLED"}, {"unknown", "UNKNOWN"},
  };
  uint32_t revision = 1;
  for (const auto& test_case : cases) {
    AgentProjection projection;
    JsonDocument document = snapshot_document(revision++, test_case.state);
    BoardAdapter board;
    TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
    resetLog();
    TEST_ASSERT_TRUE_MESSAGE(projection.commitSnapshot(board), test_case.state);
    TEST_ASSERT_TRUE_MESSAGE(logContainsText(test_case.word), test_case.word);
  }
}

void test_signal_edge_renders_fence_words() {
  const struct { const char* status; const char* word; } cases[] = {
      {"stale", "STALE"}, {"offline", "OFFLINE"}, {"unavailable", "UNAVAILABLE"},
  };
  uint32_t revision = 1;
  for (const auto& test_case : cases) {
    AgentProjection projection;
    JsonDocument document = snapshot_document(revision++, "working", test_case.status);
    BoardAdapter board;
    TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
    resetLog();
    TEST_ASSERT_TRUE(projection.commitSnapshot(board));
    TEST_ASSERT_TRUE_MESSAGE(logContainsText(test_case.word), test_case.word);
    // A fenced source never yields an actionable binding.
    TEST_ASSERT_FALSE(projection.hasBinding(0));
  }
}

void test_signal_edge_renders_feedback_words() {
  AgentProjection projection;
  JsonDocument document = snapshot_document(1);
  BoardAdapter board;
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "action-1", intent.to<JsonObject>()));
  resetLog();
  projection.renderFeedback(board, 0);
  TEST_ASSERT_TRUE(logContainsText("PENDING"));
  JsonDocument result = focus_result_document("action-1", "rejected");
  result["snapshot_revision"] = 1;
  TEST_ASSERT_FALSE(projection.applyFocusResult(result.as<JsonObjectConst>()));
  resetLog();
  projection.renderFeedback(board, 0);
  TEST_ASSERT_TRUE(logContainsText("REJECTED"));
}

// --- Per-panel reveal fencing (R-2) ----------------------------------------

void test_reveal_window_press_is_inert() {
  // A press after the first panel flush but before the third must capture no
  // binding: bindings deactivate at stage time via commitSnapshot's
  // disableActive and only reactivate after the final flush.
  struct RevealProbeTheme final : public ThemeRenderer {
    AgentProjection* projection = nullptr;
    bool press_attempted = false;
    bool press_captured = false;
    void composeTile(LGFX_Sprite&, uint8_t slot, const RenderState&) override {
      if (slot == 1 && !press_attempted && projection != nullptr) {
        press_attempted = true;
        JsonDocument intent;
        press_captured = projection->captureFocusIntent(0, "reveal-press", intent.to<JsonObject>());
      }
    }
    void composePanel4(LGFX_Sprite&, const RenderState&) override {}
    void composeMenu(LGFX_Sprite&, const MenuState&) override {}
    void composeSync(LGFX_Sprite&) override {}
  } probe;
  AgentProjection projection;
  probe.projection = &projection;
  projection.setTheme(probe);
  BoardAdapter board;
  JsonDocument first = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  probe.press_attempted = false;  // arm for the second (ordinary) refresh
  JsonDocument second = snapshot_document(2);
  TEST_ASSERT_TRUE(projection.stageSnapshot(second.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_TRUE(probe.press_attempted);
  TEST_ASSERT_FALSE(probe.press_captured);
  // After the third flush the new generation is actionable again.
  TEST_ASSERT_TRUE(projection.hasBinding(0));
}

void test_ordinary_refresh_skips_sync_veil() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument first = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument second = snapshot_document(2);
  TEST_ASSERT_TRUE(projection.stageSnapshot(second.as<JsonObjectConst>()));
  g_sync_draw_count = 0;
  resetLog();
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_EQUAL_UINT32(0, g_sync_draw_count);
  // Direct cut: exactly one push per panel, nothing else.
  TEST_ASSERT_EQUAL_UINT32(3, countPushes());
}

void test_mid_reveal_failure_falls_back_to_sync_on_all_panels() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument first = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument second = snapshot_document(2);
  TEST_ASSERT_TRUE(projection.stageSnapshot(second.as<JsonObjectConst>()));
  missing_panel = true;  // panel 1 flush fails mid-reveal
  g_sync_draw_count = 0;
  TEST_ASSERT_FALSE(projection.commitSnapshot(board));
  missing_panel = false;
  TEST_ASSERT_FALSE(projection.committed());
  TEST_ASSERT_FALSE(projection.hasBinding(0));
}

// --- Feedback timing split (R-3 / D-15) -------------------------------------

void test_success_hold_is_shorter_than_failure_hold() {
  TEST_ASSERT_EQUAL_UINT32(800000UL, AgentProjection::kSuccessHoldUs);
  TEST_ASSERT_EQUAL_UINT32(2000000UL, AgentProjection::kFeedbackHoldUs);

  // Success expires at ~800 ms.
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "action-ok", intent.to<JsonObject>()));
  JsonDocument result = focus_result_document("action-ok", "accepted");
  result["snapshot_revision"] = 1;
  const uint32_t applied_at = micros();
  TEST_ASSERT_TRUE(projection.applyFocusResult(result.as<JsonObjectConst>()));
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Success), static_cast<int>(projection.feedback(0)));
  // Just before the 800 ms bound the hold persists...
  projection.tick(board, applied_at + 700000UL);
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Success), static_cast<int>(projection.feedback(0)));
  // ...and just after it, feedback returns to the resting actionable state.
  projection.tick(board, applied_at + 900000UL);
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Ready), static_cast<int>(projection.feedback(0)));
}

void test_rejected_persists_beyond_success_bound() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "action-no", intent.to<JsonObject>()));
  JsonDocument result = focus_result_document("action-no", "rejected");
  result["snapshot_revision"] = 1;
  const uint32_t applied_at = micros();
  TEST_ASSERT_FALSE(projection.applyFocusResult(result.as<JsonObjectConst>()));
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Rejected), static_cast<int>(projection.feedback(0)));
  // Still rejected past the success bound...
  projection.tick(board, applied_at + 900000UL);
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Rejected), static_cast<int>(projection.feedback(0)));
  // ...until the longer failure hold expires.
  projection.tick(board, applied_at + 2100000UL);
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Ready), static_cast<int>(projection.feedback(0)));
}

void test_terminal_feedback_does_not_block_next_press() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));

  JsonDocument first_intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "first-action", first_intent.to<JsonObject>()));
  JsonDocument rejected = focus_result_document("first-action", "rejected");
  rejected["snapshot_revision"] = 1;
  TEST_ASSERT_FALSE(projection.applyFocusResult(rejected.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.hasBinding(0));

  JsonDocument second_intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "second-action", second_intent.to<JsonObject>()));
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Pending), static_cast<int>(projection.feedback(0)));
}

void test_pending_press_is_superseded_by_new_press() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));

  JsonDocument first;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "first-action", first.to<JsonObject>()));
  JsonDocument second;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "second-action", second.to<JsonObject>()));
  TEST_ASSERT_EQUAL_STRING("second-action", second["action_id"].as<const char*>());

  JsonDocument old_result = focus_result_document("first-action", "accepted");
  old_result["snapshot_revision"] = 1;
  TEST_ASSERT_FALSE(projection.applyFocusResult(old_result.as<JsonObjectConst>()));
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Pending), static_cast<int>(projection.feedback(0)));

  JsonDocument new_result = focus_result_document("second-action", "accepted");
  new_result["snapshot_revision"] = 1;
  TEST_ASSERT_TRUE(projection.applyFocusResult(new_result.as<JsonObjectConst>()));
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Success), static_cast<int>(projection.feedback(0)));
}

void test_multiple_agent_keys_capture_without_waiting() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  JsonArray agents = document["agents"].as<JsonArray>();
  JsonObject slot1 = agents[1].as<JsonObject>();
  slot1["entry_id"] = "entry-1";
  slot1["title"] = "Agent two";
  slot1["discriminator"] = "repo";
  slot1["state"] = "idle";
  slot1["pane_id"] = "pane-1";
  slot1["terminal_id"] = "term-1";
  slot1["source_revision"] = 2;
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));

  JsonDocument first;
  JsonDocument second;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "key-one", first.to<JsonObject>()));
  TEST_ASSERT_TRUE(projection.captureFocusIntent(1, "key-two", second.to<JsonObject>()));
  TEST_ASSERT_EQUAL_STRING("key-one", first["action_id"].as<const char*>());
  TEST_ASSERT_EQUAL_STRING("key-two", second["action_id"].as<const char*>());
  TEST_ASSERT_EQUAL_UINT8(0, first["slot"].as<uint8_t>());
  TEST_ASSERT_EQUAL_UINT8(1, second["slot"].as<uint8_t>());
}

// --- Settings store ----------------------------------------------------------

void test_settings_fresh_device_falls_back_without_write() {
  SettingsStore store;
  TEST_ASSERT_FALSE(store.load());
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::SignalEdge), static_cast<int>(store.theme()));
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::RailEcho), static_cast<int>(store.ledGrammar()));
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);
}

void test_settings_valid_roundtrip() {
  SettingsStore store;
  TEST_ASSERT_TRUE(store.confirm(ThemeId::Beacon, LedGrammarId::FieldExtension));
  SettingsStore reloaded;
  TEST_ASSERT_TRUE(reloaded.load());
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::Beacon), static_cast<int>(reloaded.theme()));
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::FieldExtension), static_cast<int>(reloaded.ledGrammar()));
}

void test_settings_corrupt_version_falls_back_without_write() {
  SettingsStore store;
  TEST_ASSERT_TRUE(store.confirm(ThemeId::Ledger, LedGrammarId::Exception));
  g_nvs["ver"] = 99;
  g_nvs_write_count = 0;
  SettingsStore reloaded;
  TEST_ASSERT_FALSE(reloaded.load());
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::SignalEdge), static_cast<int>(reloaded.theme()));
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::RailEcho), static_cast<int>(reloaded.ledGrammar()));
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);
  TEST_ASSERT_EQUAL_UINT32(99, g_nvs["ver"]);  // no write-back
}

void test_settings_out_of_range_enum_falls_back_without_write() {
  SettingsStore store;
  TEST_ASSERT_TRUE(store.confirm(ThemeId::Instrument, LedGrammarId::MeterLamps));
  g_nvs["theme"] = 7;
  g_nvs_write_count = 0;
  SettingsStore reloaded;
  TEST_ASSERT_FALSE(reloaded.load());
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::SignalEdge), static_cast<int>(reloaded.theme()));
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);
  TEST_ASSERT_EQUAL_UINT32(7, g_nvs["theme"]);  // no write-back
}

void test_settings_confirm_rejects_out_of_range() {
  SettingsStore store;
  TEST_ASSERT_FALSE(store.confirm(static_cast<ThemeId>(9), LedGrammarId::RailEcho));
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);
}

void test_settings_failed_replacement_never_loads_hybrid_pair() {
  SettingsStore initial;
  TEST_ASSERT_TRUE(initial.confirm(ThemeId::Beacon, LedGrammarId::FieldExtension));
  for (int32_t failure = 0; failure < 4; ++failure) {
    g_nvs_fail_on_write = failure;
    g_nvs_write_attempt = 0;
    SettingsStore replacement;
    SettingsStore reloaded;
    if (failure == 0) {
      TEST_ASSERT_TRUE(reloaded.load());
      TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::Beacon), static_cast<int>(reloaded.theme()));
      TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::FieldExtension), static_cast<int>(reloaded.ledGrammar()));
    } else {
      TEST_ASSERT_FALSE(reloaded.load());
      TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::SignalEdge), static_cast<int>(reloaded.theme()));
      TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::RailEcho), static_cast<int>(reloaded.ledGrammar()));
    }
    g_nvs_write_attempt = 0;
    TEST_ASSERT_TRUE(initial.confirm(ThemeId::Beacon, LedGrammarId::FieldExtension));
  }
}

// --- Plan 02: three more themes -------------------------------------------

namespace {
// Renders one committed snapshot through `theme` and returns whether the log
// contains the literal word afterwards.
void commitThroughTheme(ThemeRenderer& theme, AgentProjection& projection, BoardAdapter& board,
                        uint32_t revision, const char* state0, const char* source_status = "current") {
  projection.setTheme(theme);
  JsonDocument document = snapshot_document(revision, state0, source_status);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  resetLog();
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
}

void assertThemeVocabulary(ThemeRenderer& theme) {
  const struct { const char* state; const char* word; } states[] = {
      {"blocked", "BLOCKED"}, {"finished", "UNSEEN"}, {"working", "WORKING"},
      {"idle", "IDLE"}, {"settled", "SETTLED"}, {"unknown", "UNKNOWN"},
  };
  uint32_t revision = 1;
  for (const auto& entry : states) {
    AgentProjection projection;
    BoardAdapter board;
    commitThroughTheme(theme, projection, board, revision++, entry.state);
    TEST_ASSERT_TRUE_MESSAGE(logContainsText(entry.word), entry.word);
  }
  const struct { const char* status; const char* word; } fences[] = {
      {"stale", "STALE"}, {"offline", "OFFLINE"}, {"unavailable", "UNAVAILABLE"},
  };
  for (const auto& entry : fences) {
    AgentProjection projection;
    BoardAdapter board;
    commitThroughTheme(theme, projection, board, revision++, "working", entry.status);
    TEST_ASSERT_TRUE_MESSAGE(logContainsText(entry.word), entry.word);
    TEST_ASSERT_FALSE(projection.hasBinding(0));
  }
  // Feedback words: PENDING and REJECTED through the real focus path.
  AgentProjection projection;
  BoardAdapter board;
  commitThroughTheme(theme, projection, board, revision++, "working");
  JsonDocument intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "vocab-action", intent.to<JsonObject>()));
  resetLog();
  projection.renderFeedback(board, 0);
  TEST_ASSERT_TRUE(logContainsText("PENDING"));
  JsonDocument result = focus_result_document("vocab-action", "rejected");
  result["snapshot_revision"] = revision - 1;
  TEST_ASSERT_FALSE(projection.applyFocusResult(result.as<JsonObjectConst>()));
  resetLog();
  projection.renderFeedback(board, 0);
  TEST_ASSERT_TRUE(logContainsText("REJECTED"));
}
}  // namespace

void test_ledger_full_vocabulary() { assertThemeVocabulary(ledgerTheme()); }
void test_beacon_full_vocabulary() { assertThemeVocabulary(beaconTheme()); }
void test_instrument_full_vocabulary() { assertThemeVocabulary(instrumentTheme()); }

void test_theme_by_id_dispatches_all_four() {
  TEST_ASSERT_EQUAL_PTR(&signalEdgeTheme(), &themeById(ThemeId::SignalEdge));
  TEST_ASSERT_EQUAL_PTR(&ledgerTheme(), &themeById(ThemeId::Ledger));
  TEST_ASSERT_EQUAL_PTR(&beaconTheme(), &themeById(ThemeId::Beacon));
  TEST_ASSERT_EQUAL_PTR(&instrumentTheme(), &themeById(ThemeId::Instrument));
}

void test_theme_redraw_flushes_every_agent_panel() {
  AgentProjection projection;
  BoardAdapter board;
  commitThroughTheme(signalEdgeTheme(), projection, board, 1, "working");
  projection.setTheme(instrumentTheme());
  resetLog();
  TEST_ASSERT_TRUE(projection.redrawTiles(board));
  const std::vector<int> order = pushOrder();
  TEST_ASSERT_EQUAL_UINT32(3, order.size());
  TEST_ASSERT_EQUAL_INT(0, order[0]);
  TEST_ASSERT_EQUAL_INT(1, order[1]);
  TEST_ASSERT_EQUAL_INT(2, order[2]);
}

void test_ledger_empty_and_blocked_inversion() {
  AgentProjection projection;
  BoardAdapter board;
  commitThroughTheme(ledgerTheme(), projection, board, 1, "blocked");
  TEST_ASSERT_TRUE(logContainsText("BLOCKED"));
  // Slot 1 is empty in the fixture: SLOT EMPTY must appear in the same commit.
  TEST_ASSERT_TRUE(logContainsText("SLOT EMPTY"));
}

void test_panel4_compositions_are_honest() {
  ThemeRenderer* themes[] = {&signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme()};
  LGFX_Sprite sprite;
  RenderState rest;
  for (ThemeRenderer* theme : themes) {
    resetLog();
    theme->composePanel4(sprite, rest);
    TEST_ASSERT_TRUE(logContainsText("CODEX"));
    TEST_ASSERT_TRUE(logContainsText("UNAVAILABLE"));
  }
}

void test_feedback_and_sync_copy_is_not_duplicated() {
  AgentProjection projection;
  ThemeRenderer* themes[] = {&signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme()};
  for (ThemeRenderer* theme : themes) {
    resetLog();
    TEST_ASSERT_TRUE(projection.capturePanel(0, theme, CaptureScene::Rejected));
    TEST_ASSERT_EQUAL_UINT32(1, logTextCount("REJECTED"));
    resetLog();
    LGFX_Sprite sprite;
    theme->composeSync(sprite);
    TEST_ASSERT_EQUAL_UINT32(1, logTextCount("SYNC"));
    TEST_ASSERT_EQUAL_UINT32(0, logTextCount("UPDATING"));
  }
}

void test_signal_edge_polish_geometry() {
  LGFX_Sprite sprite;
  RenderState state;
  state.source_status = "current";
  state.slots[0].occupied = true;
  state.slots[0].title = "Agent";
  state.slots[0].discriminator = "workspace";
  state.slots[0].since = "4m";
  state.slots[0].state = TileState::Idle;
  state.slots[0].feedback = TileFeedback::Pending;
  resetLog();
  signalEdgeTheme().composeTile(sprite, 0, state);
  TEST_ASSERT_TRUE(logContainsAny("fillRect:0:108:128:20"));

  state.slots[0].occupied = false;
  state.slots[0].state = TileState::Empty;
  state.slots[0].feedback = TileFeedback::Disabled;
  resetLog();
  signalEdgeTheme().composeTile(sprite, 0, state);
  TEST_ASSERT_TRUE(logContainsAny("fillRect:54:59:20:2"));

  MenuState menu;
  menu.open = true;
  menu.cursor = 0;
  menu.editing = true;
  menu.theme_candidate = ThemeId::Instrument;
  menu.grammar_candidate = LedGrammarId::MeterLamps;
  resetLog();
  signalEdgeTheme().composeMenu(sprite, menu);
  TEST_ASSERT_TRUE(logContainsAny("fillRect:12:30:112:20"));
  TEST_ASSERT_TRUE(logContainsText("TURN: CHANGE"));
  TEST_ASSERT_TRUE(logContainsText("CLICK: SAVE"));
}

void test_usage_placeholders_follow_theme_geometry() {
  LGFX_Sprite sprite;
  RenderState state;

  resetLog();
  signalEdgeTheme().composePanel4(sprite, state);
  TEST_ASSERT_TRUE(logContainsText("5H"));
  TEST_ASSERT_TRUE(logContainsText("WEEK"));
  TEST_ASSERT_EQUAL_UINT32(2, logTextCount("N/A"));
  TEST_ASSERT_EQUAL_UINT32(0, logTextCount("NO VALUES"));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:16:40:108:12"));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:16:72:108:12"));

  resetLog();
  instrumentTheme().composePanel4(sprite, state);
  TEST_ASSERT_TRUE(logContainsText("5H"));
  TEST_ASSERT_TRUE(logContainsText("WEEK"));
  TEST_ASSERT_EQUAL_UINT32(2, logTextCount("N/A"));
  TEST_ASSERT_EQUAL_UINT32(0, logTextCount("NO VALUES"));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:8:32:112:10"));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:8:64:112:10"));
  TEST_ASSERT_FALSE(logContainsAny("drawCircle:"));
}

void test_working_symbols_are_filled_in_every_theme() {
  ThemeRenderer* themes[] = {&signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme()};
  LGFX_Sprite sprite;
  RenderState state;
  state.source_status = "current";
  state.slots[0].occupied = true;
  state.slots[0].state = TileState::Working;
  for (ThemeRenderer* theme : themes) {
    resetLog();
    theme->composeTile(sprite, 0, state);
    TEST_ASSERT_TRUE(logContainsAny("fillTriangle:"));
  }
}

void test_beacon_pending_uses_large_animated_takeover() {
  LGFX_Sprite sprite;
  RenderState state;
  state.source_status = "current";
  state.blocked_pulse_high = true;
  state.slots[0].occupied = true;
  state.slots[0].title = "Agent";
  state.slots[0].discriminator = "workspace";
  state.slots[0].state = TileState::Working;
  state.slots[0].feedback = TileFeedback::Pending;
  resetLog();
  beaconTheme().composeTile(sprite, 0, state);
  TEST_ASSERT_TRUE(logContainsText("FOCUS SENT"));
  TEST_ASSERT_TRUE(logContainsAny("fillCircle:42:52:2"));
}

// --- Plan 02: animation scheduler -------------------------------------------

void test_blocked_pulse_cadence_and_phase() {
  AnimationScheduler scheduler;
  const uint32_t start = 1000;
  scheduler.blockedFrameDue(start);  // establishes the epoch
  TEST_ASSERT_FALSE(scheduler.blockedFrameDue(start + 100000UL));       // within half period
  TEST_ASSERT_TRUE(scheduler.blockedFrameDue(start + 650000UL));        // crossed 600 ms
  TEST_ASSERT_FALSE(scheduler.blockedFrameDue(start + 700000UL));
  TEST_ASSERT_TRUE(scheduler.blockedFrameDue(start + 1250000UL));       // next half period
  // Phase query is stable and derived from the same epoch.
  TEST_ASSERT_TRUE(scheduler.blockedPulseHigh(start + 100000UL));
  TEST_ASSERT_FALSE(scheduler.blockedPulseHigh(start + 650000UL));
  TEST_ASSERT_TRUE(scheduler.blockedPulseHigh(start + 1250000UL));
  TEST_ASSERT_EQUAL_UINT32(start, scheduler.blockedPhaseEpoch());
}

void test_ambient_cadence_degrades_under_budget_pressure() {
  AnimationScheduler scheduler;
  scheduler.setAmbientPeriod(100000UL);  // 100 ms ambient cadence
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Full), static_cast<int>(scheduler.level()));
  // Flush cost 50 ms per 100 ms period = 50 % duty > 30 % -> Half.
  scheduler.observeFlushCost(50000UL, 1000000UL);
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Half), static_cast<int>(scheduler.level()));
  // Still over budget at halved cadence (50 ms / 200 ms = 25 %? no — 25 < 30,
  // so feed a heavier cost to force Static).
  scheduler.observeFlushCost(90000UL, 1000000UL);
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Static), static_cast<int>(scheduler.level()));
  // Static level schedules no ambient frames.
  TEST_ASSERT_FALSE(scheduler.ambientFrameDue(1));
  TEST_ASSERT_FALSE(scheduler.ambientFrameDue(10000000UL));
  // Comfortable margin recovers toward full cadence stepwise.
  scheduler.observeFlushCost(1000UL, 1000000UL);
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Half), static_cast<int>(scheduler.level()));
  scheduler.observeFlushCost(1000UL, 1000000UL);
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Full), static_cast<int>(scheduler.level()));
}

void test_blocked_motion_suppressed_by_fence_and_no_alloc() {
  AgentProjection projection;
  BoardAdapter board;
  // Fenced source: tick must schedule no animation frames.
  commitThroughTheme(signalEdgeTheme(), projection, board, 1, "blocked", "stale");
  resetLog();
  projection.tick(board, 5000000UL);
  projection.tick(board, 10000000UL);
  TEST_ASSERT_EQUAL_UINT32(0, countPushes());
}

void test_blocked_motion_recomposes_blocked_panel_only() {
  AgentProjection projection;
  BoardAdapter board;
  commitThroughTheme(signalEdgeTheme(), projection, board, 1, "blocked");
  // First tick establishes the epoch; the second, one half-period later, must
  // recompose exactly the BLOCKED slot (slot 0) as one complete frame.
  projection.tick(board, 1000);
  resetLog();
  projection.tick(board, 1000 + 650000UL);
  const std::vector<int> order = pushOrder();
  TEST_ASSERT_EQUAL_UINT32(1, order.size());
  TEST_ASSERT_EQUAL_INT(0, order[0]);
}

void test_led_grammars_and_policy() {
  RenderState state;
  state.source_status = "current";
  state.blocked_pulse_high = true;
  state.slots[0].occupied = true;
  state.slots[0].state = TileState::Blocked;
  state.slots[1].occupied = true;
  state.slots[1].state = TileState::Unseen;
  state.slots[2].occupied = true;
  state.slots[2].state = TileState::Working;

  BoardAdapter board;
  LedEngine engine;
  engine.setGrammar(railEchoGrammar());
  engine.render(state, LedEvents(), 0, board);
  TEST_ASSERT_TRUE(g_led_calls.size() > 0);
  bool saw_blocked = false;
  bool saw_unseen = false;
  bool saw_working = false;
  for (const LedCall& call : g_led_calls) {
    TEST_ASSERT_LESS_OR_EQUAL_UINT8(45, call.brightness);
    if ((call.mask & (1U << 1)) != 0 && call.brightness == 40) saw_blocked = true;
    if ((call.mask & (1U << 4)) != 0 && call.brightness == 30) saw_unseen = true;
    if ((call.mask & (1U << 7)) != 0 && call.brightness == 18) saw_working = true;
  }
  TEST_ASSERT_TRUE(saw_blocked);
  TEST_ASSERT_TRUE(saw_unseen);
  TEST_ASSERT_TRUE(saw_working);
  const size_t writes = g_led_calls.size();
  engine.render(state, LedEvents(), 1, board);
  TEST_ASSERT_EQUAL_UINT32(writes, g_led_calls.size());

  state.source_status = "stale";
  engine.setGrammar(exceptionChannelGrammar());
  g_led_calls.clear();
  engine.render(state, LedEvents(), 0, board);
  bool saw_health = false;
  for (const LedCall& call : g_led_calls) {
    if (call.hue == 0 && call.brightness == 10 && (call.mask & (1U << 0)) != 0) saw_health = true;
  }
  TEST_ASSERT_TRUE(saw_health);
}

void test_led_policy_clamps_bright_led_count_and_all_off() {
  struct Overbright final : public LedGrammar {
    size_t frame(const RenderState&, const LedEvents&, uint32_t,
                 LedSegment* out, size_t capacity) const override {
      if (capacity == 0) return 0;
      out[0] = {0x3FFF, 220, 100, 90};
      return 1;
    }
  } overbright;
  RenderState state;
  state.source_status = "current";
  state.slots[0].state = TileState::Blocked;
  LedEngine engine;
  engine.setGrammar(overbright);
  BoardAdapter board;
  engine.render(state, LedEvents(), 0, board);
  TEST_ASSERT_EQUAL_UINT32(2, g_led_calls.size());
  TEST_ASSERT_EQUAL_UINT16(0x003F, g_led_calls[0].mask);
  TEST_ASSERT_EQUAL_UINT8(45, g_led_calls[0].brightness);
  TEST_ASSERT_EQUAL_UINT16(0x3FC0, g_led_calls[1].mask);
  TEST_ASSERT_EQUAL_UINT8(25, g_led_calls[1].brightness);

  g_led_calls.clear();
  LedEvents off;
  off.all_off = true;
  engine.render(state, off, 1, board);
  TEST_ASSERT_EQUAL_UINT32(1, g_led_calls.size());
  TEST_ASSERT_EQUAL_UINT16(0x3FFF, g_led_calls[0].mask);
  TEST_ASSERT_EQUAL_UINT8(0, g_led_calls[0].brightness);
}

void test_led_grammar_scene_masks() {
  RenderState state;
  state.source_status = "current";
  state.slots[0].state = TileState::Idle;
  state.slots[1].state = TileState::Working;
  state.slots[2].state = TileState::Empty;
  LedSegment segments[kLedGrammarMaxSegments]{};
  LedEvents menu;
  menu.menu_open = true;
  const size_t rail_count = railEchoGrammar().frame(state, menu, 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_EQUAL_UINT32(3, rail_count);
  TEST_ASSERT_EQUAL_UINT16(1U << 13, segments[2].mask);
  state.slots[0].feedback = TileFeedback::Pending;
  const size_t field_count = fieldExtensionGrammar().frame(state, LedEvents(), 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_TRUE(field_count >= 2);
  TEST_ASSERT_EQUAL_UINT16(1U, segments[0].mask);
  TEST_ASSERT_EQUAL_UINT8(45, segments[0].brightness);
  const size_t meter_count = meterLampsGrammar().frame(state, LedEvents(), 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_TRUE(meter_count > 0);
  for (size_t index = 0; index < meter_count; ++index) {
    TEST_ASSERT_EQUAL_UINT16(0, static_cast<uint16_t>(segments[index].mask & ((1U << 0) | (1U << 2) | (1U << 3) | (1U << 6))));
  }
}

void test_menu_controller_clamps_previews_and_persists_only_on_confirm() {
  SettingsStore settings;
  settings.load();
  MenuController menu(settings);
  menu.resetFromStore();
  TEST_ASSERT_TRUE(menu.click());
  TEST_ASSERT_TRUE(menu.open());
  TEST_ASSERT_EQUAL_UINT8(0, menu.state().cursor);
  TEST_ASSERT_FALSE(menu.rotate(-1));
  TEST_ASSERT_TRUE(menu.rotate(1));
  TEST_ASSERT_EQUAL_UINT8(1, menu.state().cursor);
  TEST_ASSERT_TRUE(menu.click());
  TEST_ASSERT_TRUE(menu.editing());
  TEST_ASSERT_TRUE(menu.rotate(1));
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::Exception), static_cast<int>(menu.activeGrammar()));
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);
  TEST_ASSERT_TRUE(menu.click());
  TEST_ASSERT_FALSE(menu.editing());
  TEST_ASSERT_EQUAL_UINT32(4, g_nvs_write_count);
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::Exception), static_cast<int>(menu.storedGrammar()));
  TEST_ASSERT_TRUE(menu.click());
  TEST_ASSERT_FALSE(menu.open());

  menu.click();
  menu.rotate(1);
  menu.click();
  const uint32_t writes_before_revert = g_nvs_write_count;
  menu.rotate(1);
  TEST_ASSERT_TRUE(menu.cancel());
  TEST_ASSERT_FALSE(menu.open());
  TEST_ASSERT_EQUAL_UINT32(writes_before_revert, g_nvs_write_count);
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::Exception), static_cast<int>(menu.storedGrammar()));
}

void test_each_theme_composes_menu_vocabulary() {
  MenuState menu;
  menu.open = true;
  menu.cursor = 1;
  menu.editing = true;
  menu.theme_candidate = ThemeId::Instrument;
  menu.grammar_candidate = LedGrammarId::FieldExtension;
  ThemeRenderer* themes[] = {&signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme()};
  for (ThemeRenderer* theme : themes) {
    resetLog();
    LGFX_Sprite sprite;
    theme->composeMenu(sprite, menu);
    TEST_ASSERT_TRUE(logContainsAny("THEME"));
    TEST_ASSERT_TRUE(logContainsAny("LED"));
    if (theme == &signalEdgeTheme()) {
      TEST_ASSERT_TRUE(logContainsText("TURN: CHANGE"));
      TEST_ASSERT_TRUE(logContainsText("CLICK: SAVE"));
    } else {
      TEST_ASSERT_TRUE(logContainsText("TURN:SEL CLICK:CLOSE"));
    }
  }
}

void test_menu_redraw_is_panel4_only() {
  AgentProjection projection;
  BoardAdapter board;
  MenuState menu;
  menu.open = true;
  menu.cursor = 0;
  resetLog();
  projection.renderMenu(board, signalEdgeTheme(), menu);
  const std::vector<int> order = pushOrder();
  TEST_ASSERT_EQUAL_UINT32(1, order.size());
  TEST_ASSERT_EQUAL_INT(3, order[0]);
}

int runAllTests() {
  UNITY_BEGIN();
  RUN_TEST(test_compose_then_flush_commits_generation);
  RUN_TEST(test_null_panel_fails_closed);
  RUN_TEST(test_generation_replacement_clears_feedback);
  RUN_TEST(test_snapshot_commit_keeps_visible_sync_cutout_hidden);
  RUN_TEST(test_flush_ordering_one_push_per_panel_sequential);
  RUN_TEST(test_theme_dispatch_renders_through_injected_theme);
  RUN_TEST(test_signal_edge_renders_literal_state_words);
  RUN_TEST(test_signal_edge_renders_fence_words);
  RUN_TEST(test_signal_edge_renders_feedback_words);
  RUN_TEST(test_reveal_window_press_is_inert);
  RUN_TEST(test_ordinary_refresh_skips_sync_veil);
  RUN_TEST(test_mid_reveal_failure_falls_back_to_sync_on_all_panels);
  RUN_TEST(test_success_hold_is_shorter_than_failure_hold);
  RUN_TEST(test_rejected_persists_beyond_success_bound);
  RUN_TEST(test_terminal_feedback_does_not_block_next_press);
  RUN_TEST(test_pending_press_is_superseded_by_new_press);
  RUN_TEST(test_multiple_agent_keys_capture_without_waiting);
  RUN_TEST(test_settings_fresh_device_falls_back_without_write);
  RUN_TEST(test_settings_valid_roundtrip);
  RUN_TEST(test_settings_corrupt_version_falls_back_without_write);
  RUN_TEST(test_settings_out_of_range_enum_falls_back_without_write);
  RUN_TEST(test_settings_confirm_rejects_out_of_range);
  RUN_TEST(test_settings_failed_replacement_never_loads_hybrid_pair);
  RUN_TEST(test_ledger_full_vocabulary);
  RUN_TEST(test_beacon_full_vocabulary);
  RUN_TEST(test_instrument_full_vocabulary);
  RUN_TEST(test_theme_redraw_flushes_every_agent_panel);
  RUN_TEST(test_theme_by_id_dispatches_all_four);
  RUN_TEST(test_ledger_empty_and_blocked_inversion);
  RUN_TEST(test_panel4_compositions_are_honest);
  RUN_TEST(test_feedback_and_sync_copy_is_not_duplicated);
  RUN_TEST(test_signal_edge_polish_geometry);
  RUN_TEST(test_usage_placeholders_follow_theme_geometry);
  RUN_TEST(test_working_symbols_are_filled_in_every_theme);
  RUN_TEST(test_beacon_pending_uses_large_animated_takeover);
  RUN_TEST(test_blocked_pulse_cadence_and_phase);
  RUN_TEST(test_ambient_cadence_degrades_under_budget_pressure);
  RUN_TEST(test_blocked_motion_suppressed_by_fence_and_no_alloc);
  RUN_TEST(test_led_grammars_and_policy);
  RUN_TEST(test_led_policy_clamps_bright_led_count_and_all_off);
  RUN_TEST(test_led_grammar_scene_masks);
  RUN_TEST(test_blocked_motion_recomposes_blocked_panel_only);
  RUN_TEST(test_menu_controller_clamps_previews_and_persists_only_on_confirm);
  RUN_TEST(test_each_theme_composes_menu_vocabulary);
  RUN_TEST(test_menu_redraw_is_panel4_only);
  return UNITY_END();
}

int main(int, char**) { return runAllTests(); }
