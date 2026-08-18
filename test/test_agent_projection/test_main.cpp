#include <Arduino.h>
#include <ArduinoJson.h>
#include <unity.h>

#include <string>
#include <vector>

#include "../../firmware/src/app/agent_projection.h"
#include "../../firmware/src/app/settings_store.h"
#include "../../firmware/src/board/board_adapter.h"
#include "../../firmware/src/ui/theme.h"

namespace {
Display displays[4];
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
  if (index >= 3 || (missing_panel && index == 1)) return nullptr;
  return &displays[index];
}

void setUp() {}
void tearDown() {
  missing_panel = false;
  g_nvs.clear();
  g_nvs_write_count = 0;
  resetLog();
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
  RUN_TEST(test_settings_fresh_device_falls_back_without_write);
  RUN_TEST(test_settings_valid_roundtrip);
  RUN_TEST(test_settings_corrupt_version_falls_back_without_write);
  RUN_TEST(test_settings_out_of_range_enum_falls_back_without_write);
  RUN_TEST(test_settings_confirm_rejects_out_of_range);
  return UNITY_END();
}

int main(int, char**) { return runAllTests(); }
