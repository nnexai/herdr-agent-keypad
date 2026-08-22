#include <Arduino.h>
#include <ArduinoJson.h>
#include <unity.h>

#include <string>
#include <cstdio>
#include <vector>
#include <algorithm>

#include "../../firmware/src/app/agent_projection.h"
#include "../../firmware/src/app/settings_store.h"
#include "../../firmware/src/board/board_adapter.h"
#include "../../firmware/src/ui/theme.h"
#include "../../firmware/src/ui/led_engine.h"
#include "../../firmware/src/app/menu_controller.h"
#include "../../firmware/src/app/product_input_router.h"
#include "../../firmware/src/ui/led_grammar.h"
#include "../../firmware/src/metrics/proof_metrics.h"
#include "../../firmware/src/app/hold_controller.h"

namespace {
ProductInputFrame holdFrame(uint8_t pressed, uint8_t down, uint8_t released,
                            uint32_t edge = 1000) {
  ProductInputFrame frame;
  for (uint8_t slot = 0; slot < ProductInputFrame::kAgentSlotCount; ++slot) {
    frame.agent_pressed[slot] = (pressed & (1U << slot)) != 0;
    frame.agent_down[slot] = (down & (1U << slot)) != 0;
    frame.agent_released[slot] = (released & (1U << slot)) != 0;
    frame.agent_latched_at_us[slot] =
        frame.agent_pressed[slot] ? edge : 0;
  }
  return frame;
}

int g_projection_space_down = 0;
int g_projection_release_all = 0;
bool g_projection_hid_ready = true;
}  // namespace

bool FixedSpaceHid::spaceDown() {
  if (!g_projection_hid_ready) return false;
  ++g_projection_space_down;
  return true;
}

bool FixedSpaceHid::releaseAll() {
  ++g_projection_release_all;
  return g_projection_hid_ready;
}

bool FixedSpaceHid::ready() { return g_projection_hid_ready; }

namespace {
Display displays[4];
struct LedCall { uint16_t hue; uint8_t saturation; uint8_t brightness; uint16_t mask; };
std::vector<LedCall> g_led_calls;
std::vector<uint8_t> g_brightness_calls;
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
  JsonObject codex = root["codex"].to<JsonObject>();
  codex["source_state"] = "current";
  codex["primary"] = 0;
  codex["secondary"] = nullptr;
  codex["reset_text"] = "RESET 5H 01:20";
  codex["observation_age"] = "AGE 0M";
  codex["reached_limit"] = nullptr;
  codex["error_code"] = "";
  JsonObject diagnostics = root["diagnostics"].to<JsonObject>();
  diagnostics["link_status"] = "current";
  diagnostics["herdr_status"] = "current";
  diagnostics["codex_status"] = "current";
  diagnostics["sync_age"] = "AGE 0M";
  diagnostics["codex_age"] = "AGE 0M";
  diagnostics["firmware_version"] = "phase1";
  diagnostics["protocol_version"] = 2;
  diagnostics["bridge_version"] = "0.1.0";
  diagnostics["device_suffix"] = "ABC123";
  diagnostics["session_suffix"] = "DEF456";
  diagnostics["revision_suffix"] = "000001";
  diagnostics["error_code"] = "";
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

bool logContainsTextAt(const char* text, int32_t x, int32_t y) {
  const std::string needle = std::string("textAt:") + text + ":" +
                             std::to_string(x) + ":" + std::to_string(y);
  for (const auto& entry : g_render_log) if (entry == needle) return true;
  return false;
}

void assertPanelTextBounded() {
  for (const auto& entry : g_render_log) {
    if (entry.rfind("textAt:", 0) != 0) continue;
    const size_t y_separator = entry.rfind(':');
    const size_t x_separator = entry.rfind(':', y_separator - 1);
    const std::string text = entry.substr(7, x_separator - 7);
    const int32_t x = std::stoi(entry.substr(x_separator + 1,
                                             y_separator - x_separator - 1));
    const int32_t y = std::stoi(entry.substr(y_separator + 1));
    TEST_ASSERT_TRUE_MESSAGE(x >= 4, entry.c_str());
    TEST_ASSERT_TRUE_MESSAGE(x + static_cast<int32_t>(text.size()) * 6 <= 124,
                             entry.c_str());
    TEST_ASSERT_TRUE_MESSAGE(y >= 4 && y <= 122, entry.c_str());
  }
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

void BoardAdapter::setBrightness(uint8_t brightness) {
  g_brightness_calls.push_back(brightness);
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
  g_brightness_calls.clear();
  g_sync_draw_count = 0;
  g_projection_space_down = 0;
  g_projection_release_all = 0;
  g_projection_hid_ready = true;
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
void test_committed_render_state_exposes_one_codex_and_diagnostics_view() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  const RenderState state = projection.renderState(0);
  TEST_ASSERT_EQUAL_INT(static_cast<int>(CodexSourceState::Current), static_cast<int>(state.codex.source_state));
  TEST_ASSERT_EQUAL_INT(0, state.codex.primary);
  TEST_ASSERT_EQUAL_INT(-1, state.codex.secondary);
  TEST_ASSERT_EQUAL_STRING("RESET 5H 01:20", state.codex.reset_text);
  TEST_ASSERT_EQUAL_STRING("current", state.diagnostics.codex_status);
  TEST_ASSERT_EQUAL_STRING("phase1", state.diagnostics.firmware_version);
  TEST_ASSERT_EQUAL_UINT8(2, state.diagnostics.protocol_version);
  TEST_ASSERT_EQUAL_STRING("ABC123", state.diagnostics.device_suffix);
}

void test_rejected_diagnostics_preserve_committed_generation_and_binding() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument first = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_TRUE(projection.hasBinding(0));
  JsonDocument rejected = snapshot_document(2);
  rejected["diagnostics"]["protocol_version"] = 1;
  TEST_ASSERT_FALSE(projection.stageSnapshot(rejected.as<JsonObjectConst>()));
  const RenderState state = projection.renderState(0);
  TEST_ASSERT_EQUAL_UINT32(1, state.diagnostics.protocol_version == 2 ? 1 : 0);
  TEST_ASSERT_EQUAL_STRING("phase1", state.diagnostics.firmware_version);
  TEST_ASSERT_TRUE(projection.hasBinding(0));
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
  projection.renderFeedback(board, 0);  // one-frame physical press impulse
  resetLog();
  projection.renderFeedback(board, 0);  // current request is now PENDING
  TEST_ASSERT_TRUE(logContainsText("PENDING"));
  JsonDocument result = focus_result_document("action-1", "rejected");
  result["snapshot_revision"] = 1;
  TEST_ASSERT_FALSE(projection.applyFocusResult(result.as<JsonObjectConst>()));
  resetLog();
  projection.renderFeedback(board, 0);
  TEST_ASSERT_TRUE(logContainsText("REJECTED"));
}

void test_press_impulse_precedes_pending_render() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "impulse-action", intent.to<JsonObject>()));

  resetLog();
  projection.renderFeedback(board, 0);
  // The first complete frame acknowledges physical detection with a localized
  // cue, not an optimistic PENDING or FOCUSED result.
  TEST_ASSERT_FALSE(logContainsText("PENDING"));
  TEST_ASSERT_FALSE(logContainsText("FOCUSED"));
  TEST_ASSERT_TRUE(logContainsAny("fillRect:0:0:16:128"));

  resetLog();
  projection.renderFeedback(board, 0);
  TEST_ASSERT_TRUE(logContainsText("PENDING"));
  TEST_ASSERT_FALSE(logContainsText("FOCUSED"));
}

void test_pending_feedback_advances_at_bounded_300ms_steps() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "cadence-action", intent.to<JsonObject>()));
  const uint32_t captured_at = micros();
  projection.renderFeedback(board, 0);  // consume the one-frame impulse
  resetLog();
  RenderState pending_state = projection.renderState(captured_at);
  pending_state.ambient_phase = 0;
  LedSegment segments[kLedGrammarMaxSegments]{};
  const size_t count = fieldExtensionGrammar().frame(
      pending_state, LedEvents(), captured_at, segments,
      kLedGrammarMaxSegments);
  TEST_ASSERT_TRUE(count > 0);
  TEST_ASSERT_EQUAL_UINT16(1U, segments[0].mask);
  resetLog();
  projection.tick(board, captured_at + AgentProjection::kPendingStepUs);
  TEST_ASSERT_TRUE(countPushes() > 0);
  TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Pending),
                    static_cast<int>(projection.feedback(0)));
  pending_state = projection.renderState(captured_at);
  pending_state.ambient_phase = 0;
  const size_t stepped_count = fieldExtensionGrammar().frame(
      pending_state, LedEvents(), captured_at, segments,
      kLedGrammarMaxSegments);
  TEST_ASSERT_TRUE(stepped_count > 0);
  TEST_ASSERT_EQUAL_UINT16(1U << 1, segments[0].mask);
}
void test_semantic_feedback_events_restart_bounded_clock() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  const RenderState committed = projection.renderState(micros());
  JsonDocument intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "clock-action", intent.to<JsonObject>()));
  const RenderState pending = projection.renderState(micros());
  TEST_ASSERT_TRUE(committed.semantic_event_epoch != pending.semantic_event_epoch);
  TEST_ASSERT_TRUE(pending.semantic_event_started_us != 0);

  projection.renderFeedback(board, 0);
  JsonDocument result = focus_result_document("clock-action", "rejected");
  result["snapshot_revision"] = 1;
  TEST_ASSERT_FALSE(projection.applyFocusResult(result.as<JsonObjectConst>()));
  const RenderState rejected = projection.renderState(micros());
  TEST_ASSERT_TRUE(pending.semantic_event_epoch != rejected.semantic_event_epoch);
  TEST_ASSERT_TRUE(pending.semantic_event_started_us != rejected.semantic_event_started_us);
}



// --- Per-panel reveal fencing (R-2) ----------------------------------------

void test_beacon_and_instrument_press_impulse_and_exact_focus_outcomes() {
  ThemeRenderer* themes[] = {&beaconTheme(), &instrumentTheme()};
  for (ThemeRenderer* theme : themes) {
    AgentProjection projection;
    projection.setTheme(*theme);
    BoardAdapter board;
    JsonDocument document = snapshot_document(1);
    TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
    TEST_ASSERT_TRUE(projection.commitSnapshot(board));

    JsonDocument impulse;
    TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "theme-impulse", impulse.to<JsonObject>()));
    resetLog();
    projection.renderFeedback(board, 0);
    TEST_ASSERT_FALSE(logContainsText("PENDING"));
    TEST_ASSERT_FALSE(logContainsText("FOCUSED"));
    resetLog();
    projection.renderFeedback(board, 0);
    TEST_ASSERT_TRUE(logContainsText("PENDING"));

    // Accepted delivery without focused=true is a rejection, never optimistic
    // success.
    JsonDocument not_focused = focus_result_document("theme-impulse", "accepted");
    not_focused["focused"] = false;
    not_focused["snapshot_revision"] = 1;
    TEST_ASSERT_FALSE(projection.applyFocusResult(not_focused.as<JsonObjectConst>()));
    TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Rejected),
                      static_cast<int>(projection.feedback(0)));

    JsonDocument exact;
    TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "theme-exact", exact.to<JsonObject>()));
    projection.renderFeedback(board, 0);  // consume this press's impulse
    resetLog();
    exact["snapshot_revision"] = 1;
    JsonDocument accepted = focus_result_document("theme-exact", "accepted");
    accepted["snapshot_revision"] = 1;
    TEST_ASSERT_TRUE(projection.applyFocusResult(accepted.as<JsonObjectConst>()));
    TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Success),
                      static_cast<int>(projection.feedback(0)));
    resetLog();
    projection.renderFeedback(board, 0);
    TEST_ASSERT_TRUE(logContainsText("FOCUSED"));

    // A generation replacement fences the old action and leaves no replay.
    JsonDocument pending;
    TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "theme-old", pending.to<JsonObject>()));
    JsonDocument replacement = snapshot_document(2);
    TEST_ASSERT_TRUE(projection.stageSnapshot(replacement.as<JsonObjectConst>()));
    TEST_ASSERT_TRUE(projection.commitSnapshot(board));
    JsonDocument old_result = focus_result_document("theme-old", "accepted");
    old_result["snapshot_revision"] = 1;
    TEST_ASSERT_FALSE(projection.applyFocusResult(old_result.as<JsonObjectConst>()));
    TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Ready),
                      static_cast<int>(projection.feedback(0)));
  }
}

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
// --- Plan 03.2: passive hold presentation -------------------------------

void test_render_state_exposes_passive_hold_candidate_and_owner() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));

  FixedSpaceHid hid;
  HoldController hold(hid, 550000);
  projection.setHoldController(hold);

  JsonDocument intent;
  TEST_ASSERT_TRUE(
      projection.captureFocusIntent(0, "hold-action", intent.to<JsonObject>()));
  TEST_ASSERT_TRUE(hold.registerPress(0, "hold-action", 1000));
  hold.observeFrame(holdFrame(1, 1, 0, 1000), 1000, true);
  hold.observeFrame(holdFrame(0, 1, 0), 551000, true);

  const RenderState waiting = projection.renderState(551000);
  TEST_ASSERT_TRUE(waiting.slots[0].hold_candidate);
  TEST_ASSERT_TRUE(waiting.slots[0].hold_threshold_qualified);
  TEST_ASSERT_FALSE(waiting.slots[0].hold_active_owner);
  TEST_ASSERT_EQUAL_INT(0, g_projection_space_down);

  JsonDocument result = focus_result_document("hold-action", "accepted");
  result["snapshot_revision"] = 1;
  TEST_ASSERT_TRUE(projection.applyFocusResult(result.as<JsonObjectConst>()));
  hold.observeFocusResult(0, "hold-action", true, 551001);
  hold.observeFrame(holdFrame(0, 1, 0), 551001, true);

  const RenderState active = projection.renderState(551001);
  TEST_ASSERT_FALSE(active.slots[0].hold_candidate);
  TEST_ASSERT_FALSE(active.slots[0].hold_threshold_qualified);
  TEST_ASSERT_TRUE(active.slots[0].hold_active_owner);
  TEST_ASSERT_EQUAL_INT(1, g_projection_space_down);
}

void test_passive_owner_survives_focus_and_snapshot_generation_changes() {
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

  FixedSpaceHid hid;
  HoldController hold(hid, 550000);
  projection.setHoldController(hold);
  JsonDocument intent;
  TEST_ASSERT_TRUE(
      projection.captureFocusIntent(0, "owner-action", intent.to<JsonObject>()));
  TEST_ASSERT_TRUE(hold.registerPress(0, "owner-action", 1000));
  hold.observeFrame(holdFrame(1, 1, 0, 1000), 1000, true);
  hold.observeFocusResult(0, "owner-action", true, 1000);
  hold.observeFrame(holdFrame(0, 1, 0), 551000, true);
  TEST_ASSERT_TRUE(hold.active());

  JsonDocument other_intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(
      1, "other-action", other_intent.to<JsonObject>()));
  const RenderState during_other_focus = projection.renderState(551001);
  TEST_ASSERT_TRUE(during_other_focus.slots[0].hold_active_owner);
  TEST_ASSERT_EQUAL(static_cast<int>(TileFeedback::Pending),
                    static_cast<int>(during_other_focus.slots[1].feedback));

  JsonDocument other_result = focus_result_document("other-action", "accepted");
  other_result["entry_id"] = "entry-1";
  other_result["pane_id"] = "pane-1";
  other_result["terminal_id"] = "term-1";
  other_result["slot"] = 1;
  other_result["source_revision"] = 2;
  other_result["snapshot_revision"] = 1;
  TEST_ASSERT_TRUE(
      projection.applyFocusResult(other_result.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.renderState(551002).slots[0].hold_active_owner);

  JsonDocument replacement = snapshot_document(2);
  JsonArray replacement_agents = replacement["agents"].as<JsonArray>();
  JsonObject replacement_slot1 = replacement_agents[1].as<JsonObject>();
  replacement_slot1["entry_id"] = "entry-1";
  replacement_slot1["title"] = "Agent two";
  replacement_slot1["discriminator"] = "repo";
  replacement_slot1["state"] = "idle";
  replacement_slot1["pane_id"] = "pane-1";
  replacement_slot1["terminal_id"] = "term-1";
  replacement_slot1["source_revision"] = 2;
  TEST_ASSERT_TRUE(
      projection.stageSnapshot(replacement.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  const RenderState after_generation = projection.renderState(551003);
  TEST_ASSERT_TRUE(after_generation.slots[0].hold_active_owner);
  TEST_ASSERT_FALSE(after_generation.slots[1].hold_active_owner);
  TEST_ASSERT_TRUE(hold.active());
}
namespace {

void commitHoldSnapshot(AgentProjection& projection, BoardAdapter& board,
                        const char* source_status = "current") {
  JsonDocument document = snapshot_document(1, "working", source_status);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
}

void armQualifiedCandidate(AgentProjection& projection, HoldController& hold,
                           const char* action_id = "hold-action") {
  JsonDocument intent;
  TEST_ASSERT_TRUE(
      projection.captureFocusIntent(0, action_id, intent.to<JsonObject>()));
  TEST_ASSERT_TRUE(hold.registerPress(0, action_id, 1000));
  hold.observeFrame(holdFrame(1, 1, 0, 1000), 1000, true);
  hold.observeFrame(holdFrame(0, 1, 0), 551000, true);
}

void armActiveOwner(AgentProjection& projection, HoldController& hold,
                    const char* action_id = "hold-action") {
  armQualifiedCandidate(projection, hold, action_id);
  hold.observeFocusResult(0, action_id, true, 551001);
  hold.observeFrame(holdFrame(0, 1, 0), 551001, true);
  TEST_ASSERT_TRUE(hold.active());
}

void assertHoldFactsCleared(const RenderState& state) {
  TEST_ASSERT_FALSE(state.slots[0].hold_candidate);
  TEST_ASSERT_FALSE(state.slots[0].hold_threshold_qualified);
  TEST_ASSERT_FALSE(state.slots[0].hold_active_owner);
}

}  // namespace

void test_hold_cancellation_returns_to_ordinary_focus_feedback() {
  AgentProjection projection;
  BoardAdapter board;
  commitHoldSnapshot(projection, board);
  FixedSpaceHid hid;
  HoldController hold(hid, 550000);
  projection.setHoldController(hold);
  armQualifiedCandidate(projection, hold);

  hold.observeFrame(holdFrame(0, 0, 1), 551001, true);
  const RenderState state = projection.renderState(551001);
  assertHoldFactsCleared(state);
  TEST_ASSERT_EQUAL(static_cast<int>(TileFeedback::Pending),
                    static_cast<int>(state.slots[0].feedback));
  TEST_ASSERT_FALSE(hold.hasCandidate());
}

void test_hold_prethreshold_release_never_exposes_cancellation_state() {
  AgentProjection projection;
  BoardAdapter board;
  commitHoldSnapshot(projection, board);
  FixedSpaceHid hid;
  HoldController hold(hid, 550000);
  projection.setHoldController(hold);

  JsonDocument intent;
  TEST_ASSERT_TRUE(
      projection.captureFocusIntent(0, "short-action", intent.to<JsonObject>()));
  TEST_ASSERT_TRUE(hold.registerPress(0, "short-action", 1000));
  hold.observeFrame(holdFrame(1, 1, 0, 1000), 1000, true);
  hold.observeFrame(holdFrame(0, 0, 1), 200000, true);

  const RenderState state = projection.renderState(200000);
  assertHoldFactsCleared(state);
  TEST_ASSERT_EQUAL(static_cast<int>(TileFeedback::Pending),
                    static_cast<int>(state.slots[0].feedback));
}

void test_hold_success_expiry_keeps_qualified_candidate_visible() {
  AgentProjection projection;
  BoardAdapter board;
  commitHoldSnapshot(projection, board);
  FixedSpaceHid hid;
  HoldController hold(hid, 550000);
  projection.setHoldController(hold);
  armQualifiedCandidate(projection, hold);

  JsonDocument result = focus_result_document("hold-action", "accepted");
  result["snapshot_revision"] = 1;
  TEST_ASSERT_TRUE(projection.applyFocusResult(result.as<JsonObjectConst>()));
  hold.observeFocusResult(0, "hold-action", true, 551001);

  projection.tick(board, micros() + AgentProjection::kSuccessHoldUs + 1);
  const RenderState state = projection.renderState(micros());
  TEST_ASSERT_TRUE(state.slots[0].hold_candidate);
  TEST_ASSERT_TRUE(state.slots[0].hold_threshold_qualified);
  TEST_ASSERT_FALSE(state.slots[0].hold_active_owner);
}

void test_named_focus_failures_preempt_hold_facts() {
  const char* outcomes[] = {
      "rejected", "stale_target", "vanished", "herdr_offline",
      "uncertain", "timeout", "failed",
  };
  for (const char* outcome : outcomes) {
    AgentProjection projection;
    BoardAdapter board;
    commitHoldSnapshot(projection, board);
    FixedSpaceHid hid;
    HoldController hold(hid, 550000);
    projection.setHoldController(hold);
    armQualifiedCandidate(projection, hold);

    JsonDocument result = focus_result_document("hold-action", outcome);
    result["snapshot_revision"] = 1;
    TEST_ASSERT_FALSE(projection.applyFocusResult(result.as<JsonObjectConst>()));
    hold.observeFocusResult(0, "hold-action", false, 551001);

    const RenderState state = projection.renderState(551001);
    assertHoldFactsCleared(state);
    TileFeedback expected = TileFeedback::Rejected;
    if (strcmp(outcome, "stale_target") == 0) expected = TileFeedback::Stale;
    else if (strcmp(outcome, "vanished") == 0) expected = TileFeedback::Vanished;
    else if (strcmp(outcome, "herdr_offline") == 0) expected = TileFeedback::Offline;
    else if (strcmp(outcome, "uncertain") == 0 ||
             strcmp(outcome, "timeout") == 0) {
      expected = TileFeedback::Uncertain;
    } else if (strcmp(outcome, "failed") == 0) {
      expected = TileFeedback::Failed;
    }
    TEST_ASSERT_EQUAL(static_cast<int>(expected),
                      static_cast<int>(state.slots[0].feedback));
  }
}

void test_source_fence_preempts_candidate_and_active_owner() {
  {
    AgentProjection projection;
    BoardAdapter board;
    commitHoldSnapshot(projection, board);
    FixedSpaceHid hid;
    HoldController hold(hid, 550000);
    projection.setHoldController(hold);
    armQualifiedCandidate(projection, hold);

    JsonDocument stale = snapshot_document(2, "working", "stale");
    TEST_ASSERT_TRUE(projection.stageSnapshot(stale.as<JsonObjectConst>()));
    TEST_ASSERT_TRUE(projection.commitSnapshot(board));
    assertHoldFactsCleared(projection.renderState(551001));
  }

  {
    AgentProjection projection;
    BoardAdapter board;
    commitHoldSnapshot(projection, board);
    FixedSpaceHid hid;
    HoldController hold(hid, 550000);
    projection.setHoldController(hold);
    armActiveOwner(projection, hold);

    JsonDocument stale = snapshot_document(2, "working", "offline");
    TEST_ASSERT_TRUE(projection.stageSnapshot(stale.as<JsonObjectConst>()));
    TEST_ASSERT_TRUE(projection.commitSnapshot(board));
    assertHoldFactsCleared(projection.renderState(551001));
    TEST_ASSERT_TRUE(hold.active());
  }
}

void test_lifecycle_events_preempt_hold_presentation() {
  const HoldController::LifecycleEvent events[] = {
      HoldController::LifecycleEvent::Disconnect,
      HoldController::LifecycleEvent::SessionReplacement,
      HoldController::LifecycleEvent::ControlledReset,
      HoldController::LifecycleEvent::UsbStopped,
      HoldController::LifecycleEvent::UsbSuspend,
      HoldController::LifecycleEvent::UsbResume,
  };
  for (const HoldController::LifecycleEvent event : events) {
    AgentProjection projection;
    BoardAdapter board;
    commitHoldSnapshot(projection, board);
    FixedSpaceHid hid;
    HoldController hold(hid, 550000);
    projection.setHoldController(hold);
    armActiveOwner(projection, hold);

    TEST_ASSERT_TRUE(hold.onLifecycle(event));
    const RenderState state = projection.renderState(551002);
    assertHoldFactsCleared(state);
    TEST_ASSERT_TRUE(state.hold_lifecycle_blocked);
    TEST_ASSERT_TRUE(state.hold_empty_report_complete);
    TEST_ASSERT_FALSE(hold.active());
  }
}

void test_failed_down_and_failed_up_clear_before_report_failure() {
  {
    AgentProjection projection;
    BoardAdapter board;
    commitHoldSnapshot(projection, board);
    FixedSpaceHid hid;
    HoldController hold(hid, 550000);
    projection.setHoldController(hold);
    armQualifiedCandidate(projection, hold);
    g_projection_hid_ready = false;
    hold.observeFrame(holdFrame(0, 1, 0), 551001, false);

    const RenderState state = projection.renderState(551001);
    assertHoldFactsCleared(state);
    TEST_ASSERT_FALSE(state.hold_lifecycle_blocked);
    TEST_ASSERT_TRUE(state.hold_empty_report_complete);
  }

  g_projection_hid_ready = true;
  {
    AgentProjection projection;
    BoardAdapter board;
    commitHoldSnapshot(projection, board);
    FixedSpaceHid hid;
    HoldController hold(hid, 550000);
    projection.setHoldController(hold);
    armActiveOwner(projection, hold);
    g_projection_hid_ready = false;
    hold.observeFrame(holdFrame(0, 0, 1), 551002, false);

    const RenderState state = projection.renderState(551002);
    assertHoldFactsCleared(state);
    TEST_ASSERT_TRUE(state.hold_lifecycle_blocked);
    TEST_ASSERT_FALSE(state.hold_empty_report_complete);
  }
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

void test_settings_fresh_and_legacy_load_without_boot_write() {
  SettingsStore fresh;
  TEST_ASSERT_FALSE(fresh.load());
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::SignalEdge),
                    static_cast<int>(fresh.theme()));
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::RailEcho),
                    static_cast<int>(fresh.ledGrammar()));
  TEST_ASSERT_EQUAL_UINT8(80, fresh.brightness());
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);

  g_nvs["ver"] = SettingsStore::kLegacySchemaVersion;
  g_nvs["theme"] = static_cast<uint8_t>(ThemeId::Beacon);
  g_nvs["ledgram"] = static_cast<uint8_t>(LedGrammarId::FieldExtension);
  SettingsStore legacy;
  TEST_ASSERT_TRUE(legacy.load());
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::Beacon),
                    static_cast<int>(legacy.theme()));
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::FieldExtension),
                    static_cast<int>(legacy.ledGrammar()));
  TEST_ASSERT_EQUAL_UINT8(80, legacy.brightness());
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);
}

void test_settings_v2_roundtrip_and_bounded_brightness() {
  SettingsStore store;
  TEST_ASSERT_TRUE(
      store.confirm(ThemeId::Beacon, LedGrammarId::FieldExtension, 60));
  TEST_ASSERT_EQUAL_UINT32(SettingsStore::kSchemaVersion, g_nvs["ver"]);
  TEST_ASSERT_EQUAL_UINT32(4, g_nvs.size());
  SettingsStore reloaded;
  TEST_ASSERT_TRUE(reloaded.load());
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::Beacon),
                    static_cast<int>(reloaded.theme()));
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::FieldExtension),
                    static_cast<int>(reloaded.ledGrammar()));
  TEST_ASSERT_EQUAL_UINT8(60, reloaded.brightness());

  const uint32_t writes = g_nvs_write_count;
  TEST_ASSERT_FALSE(
      store.confirm(ThemeId::Beacon, LedGrammarId::FieldExtension, 0));
  TEST_ASSERT_FALSE(
      store.confirm(ThemeId::Beacon, LedGrammarId::FieldExtension, 55));
  TEST_ASSERT_FALSE(store.confirm(static_cast<ThemeId>(9),
                                  LedGrammarId::RailEcho, 80));
  TEST_ASSERT_EQUAL_UINT32(writes, g_nvs_write_count);
}

void test_settings_invalid_records_fall_back_without_write() {
  g_nvs["ver"] = 99;
  g_nvs["theme"] = static_cast<uint8_t>(ThemeId::Ledger);
  g_nvs["ledgram"] = static_cast<uint8_t>(LedGrammarId::Exception);
  SettingsStore corrupt_version;
  TEST_ASSERT_FALSE(corrupt_version.load());
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);

  g_nvs["ver"] = SettingsStore::kSchemaVersion;
  g_nvs["bright"] = 0;
  SettingsStore zero_brightness;
  TEST_ASSERT_FALSE(zero_brightness.load());
  TEST_ASSERT_EQUAL_UINT8(80, zero_brightness.brightness());
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);

  g_nvs["ver"] = 0;
  g_nvs["theme"] = static_cast<uint8_t>(ThemeId::Instrument);
  g_nvs["ledgram"] = static_cast<uint8_t>(LedGrammarId::MeterLamps);
  g_nvs["bright"] = 100;
  SettingsStore interrupted;
  TEST_ASSERT_FALSE(interrupted.load());
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::SignalEdge),
                    static_cast<int>(interrupted.theme()));
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);
}

void test_settings_failed_replacement_restores_prior_record_and_active_values() {
  for (int32_t failure = 0; failure < 5; ++failure) {
    g_nvs.clear();
    g_nvs_fail_on_write = -1;
    g_nvs_write_attempt = 0;
    SettingsStore store;
    TEST_ASSERT_TRUE(
        store.confirm(ThemeId::Beacon, LedGrammarId::FieldExtension, 60));

    g_nvs_fail_on_write = failure;
    g_nvs_write_attempt = 0;
    TEST_ASSERT_FALSE(
        store.confirm(ThemeId::Instrument, LedGrammarId::MeterLamps, 100));
    TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::Beacon),
                      static_cast<int>(store.theme()));
    TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::FieldExtension),
                      static_cast<int>(store.ledGrammar()));
    TEST_ASSERT_EQUAL_UINT8(60, store.brightness());

    SettingsStore reloaded;
    TEST_ASSERT_TRUE(reloaded.load());
    TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::Beacon),
                      static_cast<int>(reloaded.theme()));
    TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::FieldExtension),
                      static_cast<int>(reloaded.ledGrammar()));
    TEST_ASSERT_EQUAL_UINT8(60, reloaded.brightness());
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
    // The fixture has two empty slots; each must carry the same source fence.
    TEST_ASSERT_TRUE(logTextCount(entry.word) >= 3);
    TEST_ASSERT_FALSE(projection.hasBinding(0));
  }
  // Feedback words: PENDING and REJECTED through the real focus path.
  AgentProjection projection;
  BoardAdapter board;
  commitThroughTheme(theme, projection, board, revision++, "working");
  JsonDocument intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "vocab-action", intent.to<JsonObject>()));
  resetLog();
  projection.renderFeedback(board, 0);  // physical press impulse
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

namespace {
RenderState holdMicFixture() {
  RenderState state;
  state.source_status = "current";
  state.slots[0].occupied = true;
  state.slots[0].title = "Agent";
  state.slots[0].discriminator = "repo";
  state.slots[0].since = "NOW";
  state.slots[0].age = "0M";
  state.slots[0].state = TileState::Working;
  state.slots[0].feedback = TileFeedback::Pending;
  state.slots[0].hold_candidate = true;
  state.slots[0].hold_threshold_qualified = true;
  return state;
}

bool hasSignalEdgeMicBody(bool solid) {
  return logContainsAny(solid ? "fillRect:104:56:8:12"
                              : "drawRect:104:56:8:12");
}

bool hasLedgerMicBody(bool solid) {
  return logContainsAny(solid ? "fillRect:104:50:8:12"
                              : "drawRect:104:50:8:12");
}

void composeHoldTile(ThemeRenderer& theme, const RenderState& state) {
  LGFX_Sprite sprite;
  resetLog();
  theme.composeTile(sprite, 0, state);
}
}  // namespace

void test_signal_edge_and_ledger_hold_mic_precedence() {
  RenderState state = holdMicFixture();
  composeHoldTile(signalEdgeTheme(), state);
  TEST_ASSERT_TRUE(hasSignalEdgeMicBody(false));
  TEST_ASSERT_FALSE(hasSignalEdgeMicBody(true));
  TEST_ASSERT_TRUE(logContainsAny("drawLine:101:70:115:70"));
  TEST_ASSERT_TRUE(logContainsAny("drawLine:108:70:108:74"));

  state.slots[0].feedback_phase = 1;
  composeHoldTile(signalEdgeTheme(), state);
  TEST_ASSERT_TRUE(hasSignalEdgeMicBody(false));
  TEST_ASSERT_TRUE(logContainsAny("drawLine:98:54:100:52"));

  state.slots[0].feedback = TileFeedback::Success;
  state.slots[0].hold_candidate = false;
  state.slots[0].hold_threshold_qualified = false;
  state.slots[0].hold_active_owner = true;
  composeHoldTile(signalEdgeTheme(), state);
  TEST_ASSERT_TRUE(hasSignalEdgeMicBody(true));
  TEST_ASSERT_FALSE(hasSignalEdgeMicBody(false));

  state.slots[1].occupied = true;
  state.slots[1].feedback = TileFeedback::Pending;
  state.slots[1].hold_active_owner = false;
  composeHoldTile(signalEdgeTheme(), state);
  TEST_ASSERT_TRUE(hasSignalEdgeMicBody(true));
  composeHoldTile(signalEdgeTheme(), RenderState{});
  TEST_ASSERT_FALSE(hasSignalEdgeMicBody(false));

  state = holdMicFixture();
  state.slots[0].hold_candidate = false;
  state.slots[0].hold_threshold_qualified = false;
  composeHoldTile(signalEdgeTheme(), state);
  TEST_ASSERT_FALSE(hasSignalEdgeMicBody(false));
  TEST_ASSERT_FALSE(hasSignalEdgeMicBody(true));

  const TileFeedback failures[] = {
      TileFeedback::Rejected, TileFeedback::Stale, TileFeedback::Vanished,
      TileFeedback::Offline, TileFeedback::Uncertain, TileFeedback::Failed,
  };
  for (const TileFeedback failure : failures) {
    state = holdMicFixture();
    state.slots[0].feedback = failure;
    state.slots[0].hold_active_owner = true;
    composeHoldTile(signalEdgeTheme(), state);
    TEST_ASSERT_FALSE(hasSignalEdgeMicBody(false));
    TEST_ASSERT_FALSE(hasSignalEdgeMicBody(true));
  }

  const char* fences[] = {"stale", "offline", "unavailable"};
  for (const char* fence : fences) {
    state = holdMicFixture();
    state.source_status = fence;
    state.slots[0].hold_active_owner = true;
    composeHoldTile(signalEdgeTheme(), state);
    TEST_ASSERT_FALSE(hasSignalEdgeMicBody(false));
    TEST_ASSERT_FALSE(hasSignalEdgeMicBody(true));
  }

  state = holdMicFixture();
  state.syncing = true;
  state.slots[0].hold_active_owner = true;
  composeHoldTile(signalEdgeTheme(), state);
  TEST_ASSERT_FALSE(hasSignalEdgeMicBody(false));
  TEST_ASSERT_FALSE(hasSignalEdgeMicBody(true));

  state = holdMicFixture();
  state.hold_lifecycle_blocked = true;
  state.slots[0].hold_active_owner = true;
  composeHoldTile(signalEdgeTheme(), state);
  TEST_ASSERT_FALSE(hasSignalEdgeMicBody(false));
  TEST_ASSERT_FALSE(hasSignalEdgeMicBody(true));
}

void test_ledger_hold_mic_geometry_and_precedence() {
  RenderState state = holdMicFixture();
  composeHoldTile(ledgerTheme(), state);
  TEST_ASSERT_TRUE(hasLedgerMicBody(false));
  TEST_ASSERT_FALSE(hasLedgerMicBody(true));
  TEST_ASSERT_TRUE(logContainsAny("drawLine:101:64:115:64"));
  TEST_ASSERT_TRUE(logContainsAny("drawLine:108:64:108:68"));

  state.slots[0].feedback = TileFeedback::Success;
  state.slots[0].hold_candidate = false;
  state.slots[0].hold_threshold_qualified = false;
  state.slots[0].hold_active_owner = true;
  composeHoldTile(ledgerTheme(), state);
  TEST_ASSERT_TRUE(hasLedgerMicBody(true));
  TEST_ASSERT_FALSE(hasLedgerMicBody(false));

  state = holdMicFixture();
  state.slots[0].hold_candidate = false;
  state.slots[0].hold_threshold_qualified = false;
  composeHoldTile(ledgerTheme(), state);
  TEST_ASSERT_FALSE(hasLedgerMicBody(false));
  TEST_ASSERT_FALSE(hasLedgerMicBody(true));

  const TileFeedback failures[] = {
      TileFeedback::Rejected, TileFeedback::Stale, TileFeedback::Vanished,
      TileFeedback::Offline, TileFeedback::Uncertain, TileFeedback::Failed,
  };
  for (const TileFeedback failure : failures) {
    state = holdMicFixture();
    state.slots[0].feedback = failure;
    state.slots[0].hold_active_owner = true;
    composeHoldTile(ledgerTheme(), state);
    TEST_ASSERT_FALSE(hasLedgerMicBody(false));
    TEST_ASSERT_FALSE(hasLedgerMicBody(true));
  }

  state = holdMicFixture();
  state.hold_empty_report_complete = false;
  state.slots[0].hold_active_owner = true;
  composeHoldTile(ledgerTheme(), state);
  TEST_ASSERT_FALSE(hasLedgerMicBody(false));
  TEST_ASSERT_FALSE(hasLedgerMicBody(true));
}

bool hasBeaconMicBody(bool solid) {
  return logContainsAny(solid ? "fillRect:60:44:8:12"
                              : "drawRect:60:44:8:12");
}

bool hasInstrumentMicBody(bool solid) {
  return logContainsAny(solid ? "fillRect:60:46:8:12"
                              : "drawRect:60:46:8:12");
}

void assertHoldMicPrecedence(ThemeRenderer& theme, bool beacon_geometry) {
  RenderState state = holdMicFixture();
  composeHoldTile(theme, state);
  TEST_ASSERT_TRUE(beacon_geometry ? hasBeaconMicBody(false)
                                   : hasInstrumentMicBody(false));
  TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(true)
                                    : hasInstrumentMicBody(true));

  state.slots[0].hold_candidate = false;
  state.slots[0].hold_threshold_qualified = false;
  state.slots[0].hold_active_owner = true;
  state.slots[0].feedback = TileFeedback::Success;
  composeHoldTile(theme, state);
  TEST_ASSERT_TRUE(beacon_geometry ? hasBeaconMicBody(true)
                                   : hasInstrumentMicBody(true));
  TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(false)
                                    : hasInstrumentMicBody(false));

  const TileFeedback failures[] = {
      TileFeedback::Rejected, TileFeedback::Stale, TileFeedback::Vanished,
      TileFeedback::Offline, TileFeedback::Uncertain, TileFeedback::Failed,
  };
  for (const TileFeedback failure : failures) {
    state = holdMicFixture();
    state.slots[0].feedback = failure;
    state.slots[0].hold_active_owner = true;
    composeHoldTile(theme, state);
    TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(false)
                                      : hasInstrumentMicBody(false));
    TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(true)
                                      : hasInstrumentMicBody(true));
  }

  const char* fences[] = {"stale", "offline", "unavailable"};
  for (const char* fence : fences) {
    state = holdMicFixture();
    state.source_status = fence;
    state.slots[0].hold_active_owner = true;
    composeHoldTile(theme, state);
    TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(false)
                                      : hasInstrumentMicBody(false));
    TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(true)
                                      : hasInstrumentMicBody(true));
  }

  state = holdMicFixture();
  state.syncing = true;
  state.slots[0].hold_active_owner = true;
  composeHoldTile(theme, state);
  TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(false)
                                    : hasInstrumentMicBody(false));
  TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(true)
                                    : hasInstrumentMicBody(true));

  state = holdMicFixture();
  state.hold_lifecycle_blocked = true;
  state.slots[0].hold_active_owner = true;
  composeHoldTile(theme, state);
  TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(false)
                                    : hasInstrumentMicBody(false));
  TEST_ASSERT_FALSE(beacon_geometry ? hasBeaconMicBody(true)
                                    : hasInstrumentMicBody(true));
}

void test_beacon_and_instrument_hold_mic_geometry_and_precedence() {
  assertHoldMicPrecedence(beaconTheme(), true);
  assertHoldMicPrecedence(instrumentTheme(), false);
}

void test_hold_capture_scenes_use_production_renderers_without_mutation() {
  AgentProjection projection;
  ThemeRenderer* themes[] = {
      &signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme()};
  ThemeRenderer& original_theme = projection.theme();
  const CaptureScene scenes[] = {
      CaptureScene::HoldPending, CaptureScene::SpaceActiveOwner,
      CaptureScene::CancellationReturn, CaptureScene::OwnerAfterOtherFocus,
      CaptureScene::FailurePreemption, CaptureScene::LifecycleClear,
  };
  for (ThemeRenderer* theme : themes) {
    for (const CaptureScene scene : scenes) {
      resetLog();
      TEST_ASSERT_TRUE(projection.capturePanel(
          0, theme, scene, AnimationScheduler::Level::Static, 0));
      TEST_ASSERT_EQUAL_PTR(&original_theme, &projection.theme());
      TEST_ASSERT_NOT_NULL(projection.capturePixels());
      assertPanelTextBounded();
      if (scene == CaptureScene::HoldPending ||
          scene == CaptureScene::SpaceActiveOwner ||
          scene == CaptureScene::OwnerAfterOtherFocus) {
        if (theme == &beaconTheme()) {
          TEST_ASSERT_TRUE(hasBeaconMicBody(
              scene == CaptureScene::SpaceActiveOwner ||
              scene == CaptureScene::OwnerAfterOtherFocus));
        } else if (theme == &instrumentTheme()) {
          TEST_ASSERT_TRUE(hasInstrumentMicBody(
              scene == CaptureScene::SpaceActiveOwner ||
              scene == CaptureScene::OwnerAfterOtherFocus));
        }
      } else {
        TEST_ASSERT_FALSE(theme == &beaconTheme() && hasBeaconMicBody(false));
        TEST_ASSERT_FALSE(theme == &beaconTheme() && hasBeaconMicBody(true));
        TEST_ASSERT_FALSE(theme == &instrumentTheme() && hasInstrumentMicBody(false));
        TEST_ASSERT_FALSE(theme == &instrumentTheme() && hasInstrumentMicBody(true));
      }
    }
  }
  TEST_ASSERT_FALSE(projection.hasBinding(0));
}

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

void test_failed_theme_redraw_enters_sync_and_disables_bindings() {
  AgentProjection projection;
  BoardAdapter board;
  commitThroughTheme(signalEdgeTheme(), projection, board, 1, "working");
  TEST_ASSERT_TRUE(projection.hasBinding(0));
  missing_panel = true;
  g_sync_draw_count = 0;
  TEST_ASSERT_FALSE(projection.redrawTiles(board, instrumentTheme()));
  missing_panel = false;
  TEST_ASSERT_FALSE(projection.committed());
  TEST_ASSERT_FALSE(projection.hasBinding(0));
  TEST_ASSERT_TRUE(g_sync_draw_count > 0);
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

namespace {
ThemeRenderer* codexThemes[] = {
    &signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme(),
};

void renderCodex(ThemeRenderer& theme, const CodexRenderView& codex) {
  LGFX_Sprite sprite;
  RenderState state;
  state.codex = codex;
  resetLog();
  theme.composePanel4(sprite, state);
}
}  // namespace

void test_codex_rows_preserve_null_zero_partial_and_populated_values() {
  for (ThemeRenderer* theme : codexThemes) {
    CodexRenderView codex;
    codex.source_state = CodexSourceState::Current;
    codex.primary = 0;
    codex.secondary = -1;
    codex.reset_text = "RESET N/A";
    codex.observation_age = "AGE 0M";
    renderCodex(*theme, codex);
    TEST_ASSERT_TRUE(logContainsAny("0%"));
    TEST_ASSERT_TRUE(logContainsAny("N/A"));
    TEST_ASSERT_TRUE(logContainsText("RESET N/A"));
    TEST_ASSERT_TRUE(logContainsText("AGE 0M"));
    TEST_ASSERT_TRUE(logContainsText("CURRENT"));
    TEST_ASSERT_FALSE(logContainsText("OK"));
    TEST_ASSERT_FALSE(logContainsText("CLEAR"));
    TEST_ASSERT_FALSE(logContainsText("LIMIT"));

    codex.primary = 17;
    codex.secondary = 98;
    codex.reset_text = "RESET WEEK 2D";
    codex.observation_age = "AGE 14M";
    renderCodex(*theme, codex);
    TEST_ASSERT_TRUE(logContainsAny("17%"));
    TEST_ASSERT_TRUE(logContainsAny("98%"));
    TEST_ASSERT_TRUE(logContainsText("RESET WEEK 2D"));
    TEST_ASSERT_TRUE(logContainsText("AGE 14M"));
  }
}

void test_codex_source_precedence_clears_or_retains_values_truthfully() {
  const struct {
    CodexSourceState state;
    const char* word;
    bool retains_cache;
  } cases[] = {
      {CodexSourceState::Stale, "STALE", true},
      {CodexSourceState::AuthRequired, "AUTH REQUIRED", false},
      {CodexSourceState::CodexOffline, "CODEX OFFLINE", true},
      {CodexSourceState::HostOffline, "HOST OFFLINE", true},
      {CodexSourceState::Unavailable, "UNAVAILABLE", false},
  };
  for (ThemeRenderer* theme : codexThemes) {
    for (const auto& entry : cases) {
      CodexRenderView codex;
      codex.source_state = entry.state;
      codex.primary = 44;
      codex.secondary = 55;
      codex.reset_text = "RESET 5H 01:20";
      codex.observation_age = "AGE 2H";
      renderCodex(*theme, codex);
      TEST_ASSERT_TRUE_MESSAGE(logContainsText(entry.word), entry.word);
      TEST_ASSERT_TRUE(logContainsText("AGE 2H"));
      if (entry.retains_cache) {
        TEST_ASSERT_TRUE(logContainsAny("44%"));
        TEST_ASSERT_TRUE(logContainsAny("55%"));
        TEST_ASSERT_TRUE(logContainsText("RESET 5H 01:20"));
      } else {
        TEST_ASSERT_FALSE(logContainsAny("44%"));
        TEST_ASSERT_FALSE(logContainsAny("55%"));
        TEST_ASSERT_TRUE(logContainsAny("N/A"));
        TEST_ASSERT_TRUE(logContainsText("RESET N/A"));
      }

      codex.primary = -1;
      codex.secondary = -1;
      codex.reset_text = "RESET N/A";
      renderCodex(*theme, codex);
      TEST_ASSERT_TRUE(logContainsText(entry.word));
      TEST_ASSERT_TRUE(logContainsAny("N/A"));
    }
  }
}

void test_codex_limit_layers_without_hiding_source_state() {
  for (ThemeRenderer* theme : codexThemes) {
    CodexRenderView codex;
    codex.source_state = CodexSourceState::Current;
    codex.primary = 100;
    codex.secondary = 81;
    codex.reset_text = "RESET 5H 01:20";
    codex.observation_age = "AGE 0M";
    codex.reached_limit = -1;
    renderCodex(*theme, codex);
    TEST_ASSERT_FALSE(logContainsText("LIMIT"));
    TEST_ASSERT_FALSE(logContainsText("OK"));

    codex.reached_limit = 1;
    renderCodex(*theme, codex);
    TEST_ASSERT_TRUE(logContainsText("LIMIT"));

    codex.source_state = CodexSourceState::Stale;
    codex.observation_age = "AGE 1H";
    renderCodex(*theme, codex);
    TEST_ASSERT_TRUE(logContainsText("STALE"));
    TEST_ASSERT_TRUE(logContainsText("LIMIT"));

    codex.source_state = CodexSourceState::CodexOffline;
    renderCodex(*theme, codex);
    TEST_ASSERT_TRUE(logContainsText("CODEX OFFLINE"));
    TEST_ASSERT_TRUE(logContainsText("LIMIT"));

    codex.source_state = CodexSourceState::HostOffline;
    renderCodex(*theme, codex);
    TEST_ASSERT_TRUE(logContainsText("HOST OFFLINE"));
    TEST_ASSERT_TRUE(logContainsText("LIMIT"));

    codex.source_state = CodexSourceState::AuthRequired;
    renderCodex(*theme, codex);
    TEST_ASSERT_TRUE(logContainsText("AUTH REQUIRED"));
    TEST_ASSERT_TRUE(logContainsText("LIMIT"));
    TEST_ASSERT_FALSE(logContainsAny("100%"));
  }
}

void test_codex_status_cues_do_not_cross_value_rows() {
  CodexRenderView codex;
  codex.source_state = CodexSourceState::AuthRequired;
  codex.primary = -1;
  codex.secondary = -1;
  codex.reset_text = "RESET N/A";
  codex.observation_age = "AGE N/A";
  ThemeRenderer* top_right_marker[] = {
      &signalEdgeTheme(), &ledgerTheme(), &instrumentTheme()};
  for (ThemeRenderer* theme : top_right_marker) {
    renderCodex(*theme, codex);
    TEST_ASSERT_TRUE(logContainsAny("drawLine:112:8:124:20"));
    TEST_ASSERT_TRUE(logContainsAny("drawLine:124:8:112:20"));
    TEST_ASSERT_FALSE(logContainsAny("drawLine:16:20:124:59"));
    TEST_ASSERT_FALSE(logContainsAny("drawLine:4:20:124:59"));
    TEST_ASSERT_FALSE(logContainsAny("drawLine:8:20:120:59"));
  }

  codex.source_state = CodexSourceState::CodexOffline;
  renderCodex(signalEdgeTheme(), codex);
  TEST_ASSERT_FALSE(logContainsAny("drawLine:64:36:68:36"));
  renderCodex(instrumentTheme(), codex);
  TEST_ASSERT_FALSE(logContainsAny("drawLine:58:36:62:36"));
  renderCodex(ledgerTheme(), codex);
  TEST_ASSERT_FALSE(logContainsAny("drawLine:54:38:60:38"));

  codex.source_state = CodexSourceState::Stale;
  codex.primary = 42;
  codex.secondary = 78;
  renderCodex(ledgerTheme(), codex);
  TEST_ASSERT_FALSE(logContainsAny("drawLine:4:38:24:20"));
}

void test_codex_exact_theme_geometry_and_shared_baselines() {
  CodexRenderView codex;
  codex.source_state = CodexSourceState::Current;
  codex.primary = 17;
  codex.secondary = 83;
  codex.reset_text = "RESET 5H 01:20";
  codex.observation_age = "AGE 14M";

  renderCodex(signalEdgeTheme(), codex);
  TEST_ASSERT_TRUE(logContainsTextAt("CODEX", 16, 4));
  TEST_ASSERT_TRUE(logContainsTextAt("5H", 16, 22));
  TEST_ASSERT_TRUE(logContainsTextAt("17%", 102, 22));
  TEST_ASSERT_TRUE(logContainsTextAt("WEEK", 16, 42));
  TEST_ASSERT_TRUE(logContainsTextAt("RESET 5H 01:20", 16, 70));
  TEST_ASSERT_TRUE(logContainsTextAt("AGE 14M", 16, 86));
  TEST_ASSERT_TRUE(logContainsTextAt("CURRENT", 16, 114));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:16:32:108:8"));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:16:52:108:8"));

  renderCodex(ledgerTheme(), codex);
  TEST_ASSERT_TRUE(logContainsTextAt("CODEX", 6, 4));
  TEST_ASSERT_TRUE(logContainsTextAt("5H", 6, 30));
  TEST_ASSERT_TRUE(logContainsTextAt("17%", 102, 30));
  TEST_ASSERT_TRUE(logContainsAny("drawLine:4:38:124:38"));
  TEST_ASSERT_TRUE(logContainsAny("drawLine:4:58:124:58"));
  TEST_ASSERT_TRUE(logContainsTextAt("RESET 5H 01:20", 6, 70));
  TEST_ASSERT_TRUE(logContainsTextAt("AGE 14M", 6, 86));
  TEST_ASSERT_TRUE(logContainsTextAt("CURRENT", 6, 114));

  renderCodex(beaconTheme(), codex);
  TEST_ASSERT_TRUE(logContainsTextAt("CODEX", 49, 4));
  TEST_ASSERT_TRUE(logContainsTextAt("5H 17%", 34, 30));
  TEST_ASSERT_TRUE(logContainsTextAt("WEEK 83%", 34, 50));
  TEST_ASSERT_TRUE(logContainsAny("drawCircle:18:34:8"));
  TEST_ASSERT_TRUE(logContainsAny("drawCircle:18:54:8"));
  TEST_ASSERT_TRUE(logContainsTextAt("RESET 5H 01:20", 22, 70));
  TEST_ASSERT_TRUE(logContainsTextAt("AGE 14M", 43, 86));
  TEST_ASSERT_TRUE(logContainsTextAt("CURRENT", 43, 114));

  renderCodex(instrumentTheme(), codex);
  TEST_ASSERT_TRUE(logContainsTextAt("CODEX", 49, 4));
  TEST_ASSERT_TRUE(logContainsTextAt("5H", 8, 22));
  TEST_ASSERT_TRUE(logContainsTextAt("WEEK", 8, 42));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:8:32:112:8"));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:8:52:112:8"));
  TEST_ASSERT_TRUE(logContainsTextAt("RESET 5H 01:20", 22, 70));
  TEST_ASSERT_TRUE(logContainsTextAt("AGE 14M", 43, 86));
  TEST_ASSERT_TRUE(logContainsTextAt("CURRENT", 43, 114));
}

void test_codex_copy_is_tail_ellipsized_inside_safe_inset() {
  CodexRenderView codex;
  codex.source_state = CodexSourceState::Current;
  codex.primary = 1;
  codex.secondary = 2;
  codex.reset_text = "RESET WEEK ABCDEFGHIJKLMNOP";
  codex.observation_age = "AGE ABCDEFGHIJKLMNOPQRST";
  for (ThemeRenderer* theme : codexThemes) {
    renderCodex(*theme, codex);
    TEST_ASSERT_TRUE(logContainsText("RESET WEEK ABCD..."));
    TEST_ASSERT_TRUE(logContainsText("AGE ABCDEFGHIJK..."));
    TEST_ASSERT_FALSE(logContainsAny("EFGHIJKLMNOP"));
    assertPanelTextBounded();
  }
}

void test_codex_only_redraw_preserves_agents_bindings_and_snapshot_identity() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(7);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  const std::string title = projection.title(0);
  const std::string discriminator = projection.discriminator(0);
  TEST_ASSERT_TRUE(projection.hasBinding(0));

  MenuState menu;
  menu.open = false;
  resetLog();
  projection.renderMenu(board, beaconTheme(), menu);
  const std::vector<int> order = pushOrder();
  TEST_ASSERT_EQUAL_UINT32(1, order.size());
  TEST_ASSERT_EQUAL_INT(3, order[0]);
  TEST_ASSERT_EQUAL_STRING(title.c_str(), projection.title(0));
  TEST_ASSERT_EQUAL_STRING(discriminator.c_str(), projection.discriminator(0));
  TEST_ASSERT_TRUE(projection.hasBinding(0));
  JsonDocument intent;
  TEST_ASSERT_TRUE(projection.captureFocusIntent(0, "codex-only", intent.to<JsonObject>()));
  TEST_ASSERT_EQUAL_UINT32(7, intent["snapshot_revision"].as<uint32_t>());
}

void test_codex_only_same_revision_repaints_panel4_without_losing_focus_intent() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument initial = snapshot_document(7);
  TEST_ASSERT_TRUE(projection.stageSnapshot(initial.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument intent;
  TEST_ASSERT_TRUE(
      projection.captureFocusIntent(0, "codex-pending", intent.to<JsonObject>()));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(TileFeedback::Pending),
                        static_cast<int>(projection.feedback(0)));

  JsonDocument update = snapshot_document(7);
  update["codex"]["primary"] = 90;
  update["codex"]["observation_age"] = "AGE 1M";
  update["diagnostics"]["codex_age"] = "AGE 1M";
  resetLog();
  TEST_ASSERT_TRUE(projection.stageSnapshot(update.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  const std::vector<int> order = pushOrder();
  TEST_ASSERT_EQUAL_UINT32(1, order.size());
  TEST_ASSERT_EQUAL_INT(3, order[0]);
  TEST_ASSERT_TRUE(projection.hasBinding(0));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(TileFeedback::Pending),
                        static_cast<int>(projection.feedback(0)));

  JsonDocument drift = snapshot_document(7, "blocked");
  TEST_ASSERT_FALSE(projection.stageSnapshot(drift.as<JsonObjectConst>()));
}

void test_codex_only_same_revision_keeps_open_menu_on_panel4() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument initial = snapshot_document(7);
  TEST_ASSERT_TRUE(projection.stageSnapshot(initial.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));

  MenuState menu;
  menu.open = true;
  menu.page = MenuPage::Root;
  menu.cursor = 2;
  menu.viewport_start = 1;
  JsonDocument update = snapshot_document(7);
  update["codex"]["primary"] = 90;
  update["codex"]["observation_age"] = "AGE 1M";
  update["diagnostics"]["codex_age"] = "AGE 1M";
  TEST_ASSERT_TRUE(projection.stageSnapshot(update.as<JsonObjectConst>()));
  resetLog();
  TEST_ASSERT_TRUE(projection.commitSnapshot(board, signalEdgeTheme(), menu));
  const std::vector<int> order = pushOrder();
  TEST_ASSERT_EQUAL_UINT32(1, order.size());
  TEST_ASSERT_EQUAL_INT(3, order[0]);
  TEST_ASSERT_TRUE(logContainsText("MENU"));
  TEST_ASSERT_FALSE(logContainsText("CODEX"));
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

void test_phase3_capture_scenes_use_production_panel4_renderers() {
  AgentProjection projection;
  ThemeRenderer* themes[] = {
      &signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme()};
  struct SceneWord {
    CaptureScene scene;
    const char* word;
  };
  const SceneWord codex_scenes[] = {
      {CaptureScene::CodexCurrent, "CURRENT"},
      {CaptureScene::CodexPartial, "CURRENT"},
      {CaptureScene::CodexStale, "STALE"},
      {CaptureScene::CodexUnavailable, "UNAVAILABLE"},
      {CaptureScene::CodexAuthRequired, "AUTH REQUIRED"},
      {CaptureScene::CodexOffline, "CODEX OFFLINE"},
      {CaptureScene::HostOffline, "HOST OFFLINE"},
      {CaptureScene::CodexLimit, "LIMIT"},
      {CaptureScene::CodexLong, "CURRENT"},
  };
  const SceneWord menu_scenes[] = {
      {CaptureScene::MenuRoot0, "MENU"},
      {CaptureScene::MenuRoot1, "MENU"},
      {CaptureScene::MenuRoot2, "MENU"},
      {CaptureScene::MenuRoot3, "MENU"},
      {CaptureScene::MenuRoot4, "MENU"},
      {CaptureScene::MenuRoot5, "MENU"},
      {CaptureScene::MenuBrightness, "100%"},
      {CaptureScene::MenuHealth, "HEALTH"},
      {CaptureScene::MenuAbout, "ABOUT"},
  };
  for (ThemeRenderer* theme : themes) {
    for (const SceneWord& item : codex_scenes) {
      resetLog();
      TEST_ASSERT_TRUE(projection.capturePanel(3, theme, item.scene));
      TEST_ASSERT_TRUE_MESSAGE(logContainsText(item.word), item.word);
      assertPanelTextBounded();
    }
    for (const SceneWord& item : menu_scenes) {
      resetLog();
      TEST_ASSERT_TRUE(projection.capturePanel(3, theme, item.scene));
      TEST_ASSERT_TRUE_MESSAGE(logContainsText(item.word), item.word);
      assertPanelTextBounded();
    }
  }
  TEST_ASSERT_FALSE(
      projection.capturePanel(0, &signalEdgeTheme(), CaptureScene::MenuHealth));
}

void test_capture_phase_and_level_vocabulary_is_bounded_and_deterministic() {
  AgentProjection projection;
  ThemeRenderer* themes[] = {
      &signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme()};
  const AnimationScheduler::Level levels[] = {
      AnimationScheduler::Level::Full,
      AnimationScheduler::Level::Half,
      AnimationScheduler::Level::Static,
  };
  for (ThemeRenderer* theme : themes) {
    for (AnimationScheduler::Level level : levels) {
      for (uint8_t phase = 0; phase < 8; ++phase) {
        TEST_ASSERT_TRUE(projection.capturePanel(
            0, theme, CaptureScene::Working, level, phase));
        TEST_ASSERT_NOT_NULL(projection.capturePixels());
      }
    }
  }
  TEST_ASSERT_FALSE(projection.capturePanel(
      0, &signalEdgeTheme(), CaptureScene::Working,
      AnimationScheduler::Level::Full, 8));
  TEST_ASSERT_TRUE(projection.capturePanel(
      0, &signalEdgeTheme(), CaptureScene::Working,
      AnimationScheduler::Level::Static, 7));
}
void test_blocked_renderstate_motion_has_distinct_complete_frames() {
  AgentProjection projection;
  ThemeRenderer* themes[] = {
      &signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme()};
  for (ThemeRenderer* theme : themes) {
    std::vector<std::vector<std::string>> frames;
    for (uint8_t phase = 0; phase < AnimationScheduler::kBlockedPhaseCount; ++phase) {
      resetLog();
      TEST_ASSERT_TRUE(projection.capturePanel(
          0, theme, CaptureScene::Blocked, AnimationScheduler::Level::Full, phase));
      TEST_ASSERT_NOT_NULL(projection.capturePixels());
      if (std::find(frames.begin(), frames.end(), g_render_log) == frames.end()) {
        frames.push_back(g_render_log);
      }
    }
    TEST_ASSERT_GREATER_OR_EQUAL_UINT32(3, frames.size());
  }
}
void test_ledger_and_instrument_blocked_motion_stays_semantic_and_symmetric() {
  AgentProjection projection;
  std::vector<std::vector<std::string>> ledger_frames;
  for (uint8_t phase = 0; phase < AnimationScheduler::kBlockedPhaseCount; ++phase) {
    resetLog();
    TEST_ASSERT_TRUE(projection.capturePanel(
        0, &ledgerTheme(), CaptureScene::Blocked, AnimationScheduler::Level::Full, phase));
    TEST_ASSERT_TRUE(logContainsText("BLOCKED"));
    bool full_width_scanline = false;
    for (const std::string& entry : g_render_log) {
      if (entry == "fillRect:0:70:128:2") full_width_scanline = true;
    }
    TEST_ASSERT_FALSE(full_width_scanline);
    TEST_ASSERT_TRUE(logContainsAny(
        ("fillRect:" + std::to_string(8 + static_cast<int32_t>(phase) * 14) +
         ":64:12:2").c_str()));
    if (std::find(ledger_frames.begin(), ledger_frames.end(), g_render_log) ==
        ledger_frames.end()) {
      ledger_frames.push_back(g_render_log);
    }
  }
  TEST_ASSERT_GREATER_OR_EQUAL_UINT32(3, ledger_frames.size());

  for (uint8_t phase = 0; phase < AnimationScheduler::kBlockedPhaseCount; ++phase) {
    resetLog();
    TEST_ASSERT_TRUE(projection.capturePanel(
        0, &instrumentTheme(), CaptureScene::Blocked, AnimationScheduler::Level::Full, phase));
    TEST_ASSERT_TRUE(logContainsText("BLOCKED"));
    std::vector<std::pair<int32_t, int32_t>> gaps;
    for (const std::string& entry : g_render_log) {
      int32_t x = 0;
      int32_t y = 0;
      int32_t width = 0;
      int32_t height = 0;
      if (std::sscanf(entry.c_str(), "fillRect:%d:%d:%d:%d",
                      &x, &y, &width, &height) == 4 &&
          width == 5 && height == 5) {
        gaps.emplace_back(x + 2, y + 2);
      }
    }
    TEST_ASSERT_EQUAL_UINT32(4, gaps.size());
    for (size_t gap = 0; gap < gaps.size(); ++gap) {
      bool has_opposite = false;
      for (size_t other = 0; other < gaps.size(); ++other) {
        if (gaps[gap].first + gaps[other].first == 128 &&
            gaps[gap].second + gaps[other].second == 108) {
          has_opposite = true;
        }
      }
      TEST_ASSERT_TRUE(has_opposite);
    }
  }
}

void test_capture_slot_cardinality_is_bounded_and_semantic() {
  AgentProjection projection;
  for (CaptureScene scene : {CaptureScene::SlotsZero, CaptureScene::SlotsOne,
                             CaptureScene::SlotsTwo, CaptureScene::SlotsThree}) {
    resetLog();
    TEST_ASSERT_TRUE(projection.capturePanel(
        0, &signalEdgeTheme(), scene, AnimationScheduler::Level::Static, 0));
    TEST_ASSERT_NOT_NULL(projection.capturePixels());
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
  TEST_ASSERT_TRUE(logContainsTextAt("EMPTY", 49, 92));
  TEST_ASSERT_TRUE(logContainsTextAt("NO AGENT", 40, 104));
  TEST_ASSERT_TRUE(logContainsAny("fillRect:54:59:20:2"));

  MenuState menu;
  menu.open = true;
  menu.cursor = 0;
  menu.viewport_start = 0;
  menu.page = MenuPage::Root;
  menu.theme_stored = ThemeId::Instrument;
  menu.grammar_stored = LedGrammarId::MeterLamps;
  resetLog();
  signalEdgeTheme().composeMenu(sprite, menu);
  TEST_ASSERT_TRUE(logContainsAny("fillRect:12:20:112:24"));
  TEST_ASSERT_TRUE(logContainsText("TURN:SEL"));
  TEST_ASSERT_TRUE(logContainsText("CLICK:OPEN"));
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
  TEST_ASSERT_TRUE(logContainsAny("drawRect:16:32:108:8"));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:16:52:108:8"));

  resetLog();
  instrumentTheme().composePanel4(sprite, state);
  TEST_ASSERT_TRUE(logContainsText("5H"));
  TEST_ASSERT_TRUE(logContainsText("WEEK"));
  TEST_ASSERT_EQUAL_UINT32(2, logTextCount("N/A"));
  TEST_ASSERT_EQUAL_UINT32(0, logTextCount("NO VALUES"));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:8:32:112:8"));
  TEST_ASSERT_TRUE(logContainsAny("drawRect:8:52:112:8"));
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

void test_pending_feedback_phase_changes_all_theme_render_seams_when_ambient_static() {
  ThemeRenderer* themes[] = {
      &signalEdgeTheme(), &ledgerTheme(), &beaconTheme(), &instrumentTheme()};
  LGFX_Sprite sprite;
  RenderState state;
  state.source_status = "current";
  state.codex.source_state = CodexSourceState::Current;
  state.slots[0].occupied = true;
  state.slots[0].title = "Agent";
  state.slots[0].discriminator = "repo";
  state.slots[0].state = TileState::Working;
  state.slots[0].feedback = TileFeedback::Pending;
  state.ambient_phase = 0;
  state.transition_active = false;
  for (ThemeRenderer* theme : themes) {
    state.slots[0].feedback_phase = 0;
    resetLog();
    theme->composeTile(sprite, 0, state);
    const std::vector<std::string> first = g_render_log;
    state.slots[0].feedback_phase = 1;
    resetLog();
    theme->composeTile(sprite, 0, state);
    TEST_ASSERT_TRUE_MESSAGE(first != g_render_log,
                             "pending feedback phase did not reach theme render seam");
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
  TEST_ASSERT_TRUE(logContainsTextAt("PENDING", 43, 76));
  TEST_ASSERT_FALSE(logContainsText("FOCUS SENT"));
  TEST_ASSERT_TRUE(logContainsAny("fillCircle:42:52:2"));
}
void test_beacon_and_instrument_phase_motion_is_distinct_and_semantically_fixed() {
  LGFX_Sprite sprite;
  RenderState state;
  state.source_status = "current";
  state.slots[0].occupied = true;
  state.slots[0].title = "Agent";
  state.slots[0].discriminator = "repo";
  state.slots[0].since = "4m";
  state.slots[0].state = TileState::Working;
  state.transition_active = true;

  TEST_ASSERT_EQUAL_UINT32(66668UL, beaconTheme().ambientPeriodUs());
  TEST_ASSERT_EQUAL_UINT32(33334UL, instrumentTheme().ambientPeriodUs());

  state.transition_phase = 0;
  resetLog();
  beaconTheme().composeTile(sprite, 0, state);
  const std::vector<std::string> beacon_neutral = g_render_log;
  state.transition_phase = 2;
  resetLog();
  beaconTheme().composeTile(sprite, 0, state);
  const std::vector<std::string> beacon_motion = g_render_log;
  TEST_ASSERT_TRUE(beacon_neutral != beacon_motion);
  TEST_ASSERT_TRUE(logContainsTextAt("WORKING", 43, 73));
  TEST_ASSERT_TRUE(logContainsTextAt("Agent", 49, 100));
  TEST_ASSERT_TRUE(logContainsTextAt("repo", 52, 112));

  state.transition_phase = 0;
  resetLog();
  instrumentTheme().composeTile(sprite, 0, state);
  const std::vector<std::string> instrument_neutral = g_render_log;
  state.transition_phase = 2;
  resetLog();
  instrumentTheme().composeTile(sprite, 0, state);
  const std::vector<std::string> instrument_motion = g_render_log;
  TEST_ASSERT_TRUE(instrument_neutral != instrument_motion);
  TEST_ASSERT_TRUE(logContainsTextAt("WORKING", 43, 89));
  TEST_ASSERT_TRUE(logContainsTextAt("Agent", 49, 112));
  TEST_ASSERT_TRUE(beacon_motion != instrument_motion);
}

void test_beacon_and_instrument_fences_empty_and_codex_are_phase_static() {
  LGFX_Sprite sprite;
  RenderState state;
  state.source_status = "offline";
  state.slots[0].occupied = false;
  state.slots[0].state = TileState::Empty;
  state.transition_active = true;
  state.transition_phase = 0;
  for (ThemeRenderer* theme : {&beaconTheme(), &instrumentTheme()}) {
    resetLog();
    theme->composeTile(sprite, 0, state);
    const std::vector<std::string> first = g_render_log;
    state.transition_phase = 3;
    resetLog();
    theme->composeTile(sprite, 0, state);
    TEST_ASSERT_TRUE(first == g_render_log);
    TEST_ASSERT_TRUE(logContainsText("NO AGENT"));
    TEST_ASSERT_TRUE(logContainsText("OFFLINE"));
  }

  state.source_status = "current";
  state.slots[0].occupied = true;
  state.slots[0].state = TileState::Working;
  state.codex.source_state = CodexSourceState::Unavailable;
  state.codex.primary = -1;
  state.codex.secondary = -1;
  state.transition_phase = 0;
  for (ThemeRenderer* theme : {&beaconTheme(), &instrumentTheme()}) {
    resetLog();
    theme->composePanel4(sprite, state);
    const std::vector<std::string> first = g_render_log;
    state.transition_phase = 3;
    resetLog();
    theme->composePanel4(sprite, state);
    TEST_ASSERT_TRUE(first == g_render_log);
    TEST_ASSERT_TRUE(logContainsText("UNAVAILABLE"));
    TEST_ASSERT_TRUE(logContainsAny("N/A"));
  }
}

// --- Plan 02: animation scheduler -------------------------------------------

void test_blocked_pulse_cadence_and_phase() {
  AnimationScheduler scheduler;
  const uint32_t start = 1000;
  scheduler.blockedFrameDue(start);  // establishes the epoch
  TEST_ASSERT_FALSE(scheduler.blockedFrameDue(start + 100000UL));       // within 150 ms phase
  TEST_ASSERT_TRUE(scheduler.blockedFrameDue(start + 200000UL));        // crossed 150 ms
  TEST_ASSERT_FALSE(scheduler.blockedFrameDue(start + 250000UL));
  TEST_ASSERT_TRUE(scheduler.blockedFrameDue(start + 350000UL));        // crossed 300 ms
  TEST_ASSERT_EQUAL_UINT8(0, scheduler.blockedPhase(start + 100000UL));
  TEST_ASSERT_EQUAL_UINT8(1, scheduler.blockedPhase(start + 200000UL));
  TEST_ASSERT_EQUAL_UINT8(4, scheduler.blockedPhase(start + 650000UL));
  TEST_ASSERT_TRUE(scheduler.blockedPulseHigh(start + 100000UL));
  TEST_ASSERT_FALSE(scheduler.blockedPulseHigh(start + 650000UL));
  TEST_ASSERT_EQUAL_UINT32(start, scheduler.blockedPhaseEpoch());
}

void test_ambient_cadence_degrades_under_budget_pressure() {
  AnimationScheduler scheduler;
  scheduler.setAmbientPeriod(100000UL);  // 100 ms ambient cadence
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Full), static_cast<int>(scheduler.level()));
  // Measured complete-frame cost is evaluated against the measured loop wall
  // window, not a synthetic 1 ms approximation.
  scheduler.observeFlushCost(50000UL, 100000UL);
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Half), static_cast<int>(scheduler.level()));
  // Still over budget at the measured window, so the next observation reaches Static.
  scheduler.observeFlushCost(90000UL, 100000UL);
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
void test_main_loop_cadence_bounds_duty_and_does_not_oscillate_static() {

  AnimationScheduler scheduler;
  scheduler.setAmbientPeriod(33334UL);

  constexpr uint32_t kFrameCostUs = 107587UL;
  uint32_t completed_at_us = 33334UL + kFrameCostUs;
  uint32_t max_duty_percent = 0;
  uint32_t level_changes = 0;
  AnimationScheduler::Level previous = scheduler.level();

  for (uint8_t frame = 0; frame < 8; ++frame) {

    scheduler.observeFlushCostAt(kFrameCostUs, completed_at_us);
    if (scheduler.lastDutyPercent() > max_duty_percent) {
      max_duty_percent = scheduler.lastDutyPercent();
    }
    if (scheduler.level() != previous) {
      ++level_changes;
      previous = scheduler.level();
    }

    completed_at_us += kFrameCostUs + 33334UL;
  }

  TEST_ASSERT_LESS_OR_EQUAL_UINT32(100, max_duty_percent);
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Static),
                    static_cast<int>(scheduler.level()));
  TEST_ASSERT_EQUAL_UINT32(2, level_changes);

  ProofMetrics frame_metrics;
  AnimationScheduler classified;
  classified.setAmbientPeriod(100000UL);
  AnimationScheduler::Level rendered_level = classified.level();
  classified.observeFlushCostAt(50000UL, 100000UL);
  frame_metrics.observeAnimationFrame(
      classified.lastFlushUs(), classified.lastLoopWindowUs(),
      static_cast<uint8_t>(rendered_level));
  TEST_ASSERT_EQUAL_UINT32(1, frame_metrics.full_frames);
  TEST_ASSERT_EQUAL_UINT32(0, frame_metrics.half_frames);
  TEST_ASSERT_EQUAL_UINT32(0, frame_metrics.static_frames);

  rendered_level = classified.level();
  classified.observeFlushCostAt(90000UL, 200000UL);
  frame_metrics.observeAnimationFrame(
      classified.lastFlushUs(), classified.lastLoopWindowUs(),
      static_cast<uint8_t>(rendered_level));
  TEST_ASSERT_EQUAL_UINT32(1, frame_metrics.full_frames);
  TEST_ASSERT_EQUAL_UINT32(1, frame_metrics.half_frames);
  TEST_ASSERT_EQUAL_UINT32(0, frame_metrics.static_frames);

  AnimationScheduler wrap_safe;
  wrap_safe.setAmbientPeriod(1000000UL);
  wrap_safe.observeFlushCostAt(1000UL, 0);
  wrap_safe.observeFlushCostAt(40000UL, 100000UL);
  TEST_ASSERT_EQUAL_UINT32(100000UL, wrap_safe.lastLoopWindowUs());
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Half),
                    static_cast<int>(wrap_safe.level()));
}

void test_animation_metrics_bound_duty_and_measure_frame_allocation_pairs() {
  ProofMetrics metrics;
  for (uint8_t sample = 0; sample < 10; ++sample) {
    metrics.observeAnimationFrame(107587UL, 107587UL, 2);
  }
  TEST_ASSERT_EQUAL_UINT32(100, metrics.animation_duty_max_percent);
  metrics.beginAnimationLevelEpoch();
  TEST_ASSERT_EQUAL_UINT32(0, metrics.animation_duty_max_percent);
  for (uint8_t sample = 0; sample < 4; ++sample) {
    metrics.observeAnimationFrame(35000UL, 300000UL, 2);
  }
  TEST_ASSERT_EQUAL_UINT32(11, metrics.animation_duty_max_percent);

  metrics.observeAnimationAllocation(100000UL, 80000UL, 100000UL, 80000UL);
  TEST_ASSERT_EQUAL_UINT32(1, metrics.allocation_stable);
  metrics.observeAnimationAllocation(100000UL, 80000UL, 99984UL, 79984UL);
  TEST_ASSERT_EQUAL_UINT32(0, metrics.allocation_stable);
}

void test_transition_phase_is_bounded_and_interruptible() {
  AnimationScheduler scheduler;
  TEST_ASSERT_TRUE(scheduler.beginTransition(7, 1000));
  TEST_ASSERT_TRUE(scheduler.transitionActive());
  TEST_ASSERT_EQUAL_UINT32(0, scheduler.transitionProgress(1000));
  TEST_ASSERT_TRUE(scheduler.transitionProgress(101000) > 0);
  TEST_ASSERT_TRUE(scheduler.transitionProgress(101000) < AnimationScheduler::kTransitionPhaseCount);
  TEST_ASSERT_TRUE(scheduler.transitionDue(250999));
  TEST_ASSERT_FALSE(scheduler.transitionActive());
  TEST_ASSERT_TRUE(scheduler.beginTransition(8, 500000));
  TEST_ASSERT_TRUE(scheduler.interruptTransition(9));
  TEST_ASSERT_FALSE(scheduler.transitionActive());
  TEST_ASSERT_EQUAL_UINT32(9, scheduler.transitionEpoch());
}

void test_half_samples_every_second_phase_and_static_keeps_semantics() {
  AnimationScheduler scheduler;
  scheduler.setAmbientPeriod(100000UL);
  scheduler.beginTransition(1, 1);
  scheduler.setLevel(AnimationScheduler::Level::Half);
  TEST_ASSERT_FALSE(scheduler.ambientFrameDue(1));
  TEST_ASSERT_TRUE(scheduler.ambientFrameDue(200001));
  scheduler.setLevel(AnimationScheduler::Level::Static);
  TEST_ASSERT_FALSE(scheduler.ambientFrameDue(1000000));
  TEST_ASSERT_EQUAL(static_cast<int>(AnimationScheduler::Level::Static),
                    static_cast<int>(scheduler.level()));
  TEST_ASSERT_EQUAL_UINT32(AnimationScheduler::kNeutralPhase,
                            scheduler.presentationPhase());
}

void test_signal_edge_transition_changes_only_rail_accent() {
  LGFX_Sprite sprite;
  RenderState state;
  state.source_status = "current";
  state.slots[0].occupied = true;
  state.slots[0].title = "Agent";
  state.slots[0].discriminator = "repo";
  state.slots[0].state = TileState::Working;
  state.transition_active = true;
  state.transition_phase = 0;
  resetLog();
  signalEdgeTheme().composeTile(sprite, 0, state);
  const std::vector<std::string> first = g_render_log;
  state.transition_phase = 2;
  resetLog();
  signalEdgeTheme().composeTile(sprite, 0, state);
  TEST_ASSERT_TRUE(logContainsText("WORKING"));
  TEST_ASSERT_TRUE(first != g_render_log);
}
void test_signal_edge_and_ledger_phase_motion_is_distinct_and_semantically_fixed() {
  LGFX_Sprite sprite;
  RenderState state;
  state.source_status = "current";
  state.slots[0].occupied = true;
  state.slots[0].title = "Agent";
  state.slots[0].discriminator = "repo";
  state.slots[0].since = "4m";
  state.slots[0].state = TileState::Working;
  state.transition_active = true;

  state.transition_phase = 0;
  resetLog();
  signalEdgeTheme().composeTile(sprite, 0, state);
  const std::vector<std::string> signal_neutral = g_render_log;
  state.transition_phase = 2;
  resetLog();
  signalEdgeTheme().composeTile(sprite, 0, state);
  const std::vector<std::string> signal_motion = g_render_log;
  TEST_ASSERT_TRUE(signal_neutral != signal_motion);
  TEST_ASSERT_TRUE(logContainsTextAt("WORKING", 15, 110));
  TEST_ASSERT_TRUE(logContainsTextAt("Agent", 15, 5));
  TEST_ASSERT_TRUE(logContainsTextAt("repo", 15, 32));

  state.transition_phase = 0;
  resetLog();
  ledgerTheme().composeTile(sprite, 0, state);
  const std::vector<std::string> ledger_neutral = g_render_log;
  state.transition_phase = 2;
  resetLog();
  ledgerTheme().composeTile(sprite, 0, state);
  const std::vector<std::string> ledger_motion = g_render_log;
  TEST_ASSERT_TRUE(ledger_neutral != ledger_motion);
  TEST_ASSERT_TRUE(logContainsTextAt("WORKING", 30, 74));
  TEST_ASSERT_TRUE(logContainsTextAt("Agent", 6, 22));
  TEST_ASSERT_TRUE(logContainsTextAt("repo", 6, 7));
  TEST_ASSERT_TRUE(signal_motion != ledger_motion);
}

void test_signal_edge_and_ledger_fences_empty_and_codex_are_phase_static() {
  LGFX_Sprite sprite;
  RenderState state;
  state.source_status = "stale";
  state.slots[0].occupied = false;
  state.slots[0].state = TileState::Empty;
  state.transition_active = true;
  state.transition_phase = 0;
  for (ThemeRenderer* theme : {&signalEdgeTheme(), &ledgerTheme()}) {
    resetLog();
    theme->composeTile(sprite, 0, state);
    const std::vector<std::string> first = g_render_log;
    state.transition_phase = 3;
    resetLog();
    theme->composeTile(sprite, 0, state);
    TEST_ASSERT_TRUE(first == g_render_log);
    TEST_ASSERT_TRUE(logContainsText("NO AGENT"));
    TEST_ASSERT_TRUE(logContainsText("STALE"));
  }

  state.source_status = "current";
  state.slots[0].occupied = true;
  state.slots[0].state = TileState::Working;
  state.codex.source_state = CodexSourceState::Unavailable;
  state.codex.primary = -1;
  state.codex.secondary = -1;
  state.transition_phase = 0;
  for (ThemeRenderer* theme : {&signalEdgeTheme(), &ledgerTheme()}) {
    resetLog();
    theme->composePanel4(sprite, state);
    const std::vector<std::string> first = g_render_log;
    state.transition_phase = 3;
    resetLog();
    theme->composePanel4(sprite, state);
    TEST_ASSERT_TRUE(first == g_render_log);
    TEST_ASSERT_TRUE(logContainsText("UNAVAILABLE"));
    TEST_ASSERT_TRUE(logContainsText("N/A"));
  }
}


void test_render_state_transition_metadata_is_presentation_only() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument first = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument second = snapshot_document(2);
  TEST_ASSERT_TRUE(projection.stageSnapshot(second.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  const RenderState state = projection.renderState(1000);
  TEST_ASSERT_EQUAL_UINT32(2, state.transition_epoch);
  TEST_ASSERT_TRUE(state.transition_active);
  TEST_ASSERT_TRUE(projection.hasBinding(0));
}
void test_urgent_generation_cuts_transition_and_fences_bindings() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument first = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  JsonDocument ordinary = snapshot_document(2);
  TEST_ASSERT_TRUE(projection.stageSnapshot(ordinary.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_TRUE(projection.animation().transitionActive());

  JsonDocument stale = snapshot_document(3, "working", "stale");
  TEST_ASSERT_TRUE(projection.stageSnapshot(stale.as<JsonObjectConst>()));
  resetLog();
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  const RenderState state = projection.renderState(0);
  TEST_ASSERT_FALSE(state.transition_active);
  TEST_ASSERT_FALSE(projection.hasBinding(0));
  TEST_ASSERT_TRUE(logContainsText("STALE"));
  resetLog();
  projection.tick(board, 1000000UL);
  TEST_ASSERT_EQUAL_UINT32(0, countPushes());
}

void test_static_commit_flushes_complete_semantics_without_motion() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument first = snapshot_document(1);
  TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  projection.animation().setLevel(AnimationScheduler::Level::Static);
  JsonDocument second = snapshot_document(2);
  TEST_ASSERT_TRUE(projection.stageSnapshot(second.as<JsonObjectConst>()));
  resetLog();
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  TEST_ASSERT_EQUAL_UINT32(3, countPushes());
  const RenderState state = projection.renderState(0);
  TEST_ASSERT_FALSE(state.transition_active);
  TEST_ASSERT_TRUE(projection.hasBinding(0));
  TEST_ASSERT_TRUE(logContainsText("WORKING"));
  resetLog();
  projection.tick(board, 1000000UL);
  TEST_ASSERT_EQUAL_UINT32(0, countPushes());
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
void test_blocked_tick_produces_changing_complete_frames_at_measured_static_cost() {
  AgentProjection projection;
  BoardAdapter board;
  commitThroughTheme(signalEdgeTheme(), projection, board, 1, "blocked");
  // Model the measured 140 ms complete-panel cost in the 150 ms loop window:
  // Full -> Half -> Static must not erase the semantic BLOCKED motion path.
  projection.animation().observeFlushCost(140000UL, 150000UL);
  projection.animation().observeFlushCost(140000UL, 150000UL);
  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(AnimationScheduler::Level::Static),
                          static_cast<uint8_t>(projection.animation().level()));
  projection.tick(board, 1000);
  std::vector<std::string> previous;
  size_t distinct = 0;
  for (uint8_t phase = 1; phase <= 3; ++phase) {
    resetLog();
    projection.tick(board, 1000U + static_cast<uint32_t>(phase) * 150000U);
    TEST_ASSERT_EQUAL_UINT32(1, countPushes());
    if (g_render_log != previous) ++distinct;
    previous = g_render_log;
  }
  TEST_ASSERT_GREATER_OR_EQUAL_UINT32(2, distinct);
}

RenderState committedCodexLedState(AgentProjection& projection,
                                   BoardAdapter& board,
                                   const char* source_state,
                                   int16_t primary,
                                   int8_t reached_limit,
                                   const char* observation_age = "AGE 0M") {
  JsonDocument document = snapshot_document(1);
  JsonObject codex = document["codex"].as<JsonObject>();
  codex["source_state"] = source_state;
  if (primary < 0) codex["primary"] = nullptr;
  else codex["primary"] = primary;
  if (reached_limit < 0) codex["reached_limit"] = nullptr;
  else codex["reached_limit"] = reached_limit != 0;
  codex["observation_age"] = observation_age;
  if (std::string(source_state) == "auth_required" ||
      std::string(source_state) == "unavailable") {
    codex["primary"] = nullptr;
    codex["secondary"] = nullptr;
    codex["reset_text"] = "RESET N/A";
  }
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  return projection.renderState(0);
}

bool resolvedOn(const LedEngine& engine, uint8_t index) {
  return engine.resolved(index).brightness != 0;
}
uint8_t segmentBrightness(const LedSegment* segments, size_t count,
                          uint16_t mask) {
  for (size_t index = 0; index < count; ++index) {
    if ((segments[index].mask & mask) != 0) return segments[index].brightness;
  }
  return 0;
}

void assertUsageCue(LedGrammar& grammar, const RenderState& state,
                    uint16_t mask, uint16_t hue) {
  BoardAdapter board;
  LedEngine engine;
  engine.setGrammar(grammar);
  g_led_calls.clear();
  engine.render(state, LedEvents(), 0, board);
  TEST_ASSERT_TRUE_MESSAGE(!g_led_calls.empty(), "engine emitted no LED log");
  for (uint8_t index = 0; index < LedEngine::kLedCount; ++index) {
    if ((mask & (static_cast<uint16_t>(1U) << index)) == 0) continue;
    TEST_ASSERT_TRUE_MESSAGE(resolvedOn(engine, index), "usage zone stayed dark");
    TEST_ASSERT_EQUAL_UINT16(hue, engine.resolved(index).hue);
  }
}

void test_led_grammars_consume_committed_current_usage_boundaries() {
  constexpr uint16_t kRailUsage = 1U << 10;
  constexpr uint16_t kExceptionUsage = 1U << 10;
  constexpr uint16_t kFieldUsage = (1U << 9) | (1U << 10) | (1U << 11);
  constexpr uint16_t kMeterUsageLamp = 1U << 10;
  struct GrammarZone {
    LedGrammar* grammar;
    uint16_t mask;
  };
  GrammarZone zones[] = {
      {&railEchoGrammar(), kRailUsage},
      {&exceptionChannelGrammar(), kExceptionUsage},
      {&fieldExtensionGrammar(), kFieldUsage},
      {&meterLampsGrammar(), kMeterUsageLamp},
  };

  for (const int16_t primary : {0, 74, 75, 100}) {
    AgentProjection projection;
    BoardAdapter projection_board;
    const RenderState state =
        committedCodexLedState(projection, projection_board, "current",
                               primary, -1);
    const uint16_t expected_hue = primary >= 75 ? 35 : 180;
    for (const GrammarZone& zone : zones) {
      assertUsageCue(*zone.grammar, state, zone.mask, expected_hue);
    }
  }

  AgentProjection absent_projection;
  BoardAdapter absent_board;
  const RenderState absent =
      committedCodexLedState(absent_projection, absent_board, "current", -1,
                             -1);
  for (const GrammarZone& zone : zones) {
    LedEngine engine;
    BoardAdapter board;
    engine.setGrammar(*zone.grammar);
    LedEvents transient;
    transient.menu_open = true;
    engine.render(absent, transient, 0, board);
    for (uint8_t index = 0; index < LedEngine::kLedCount; ++index) {
      if ((zone.mask & (static_cast<uint16_t>(1U) << index)) != 0) {
        TEST_ASSERT_FALSE_MESSAGE(resolvedOn(engine, index),
                                  "transient event manufactured Codex usage");
      }
    }
  }

  AgentProjection limit_projection;
  BoardAdapter limit_board;
  const RenderState limit =
      committedCodexLedState(limit_projection, limit_board, "current", 100, 1);
  for (const GrammarZone& zone : zones) {
    assertUsageCue(*zone.grammar, limit, zone.mask, 0);
  }
}

void test_meter_lamps_uses_exact_primary_quarter_boundaries() {
  constexpr uint8_t kMeterIndices[] = {0, 2, 3, 6};
  struct Boundary {
    int16_t primary;
    uint8_t full;
    bool partial;
  };
  const Boundary boundaries[] = {
      {0, 0, false}, {1, 0, true},  {24, 0, true}, {25, 1, false},
      {26, 1, true}, {50, 2, false}, {75, 3, false}, {100, 4, false},
  };
  for (const Boundary& boundary : boundaries) {
    AgentProjection projection;
    BoardAdapter projection_board;
    const RenderState state =
        committedCodexLedState(projection, projection_board, "current",
                               boundary.primary, -1);
    LedEngine engine;
    BoardAdapter board;
    engine.setGrammar(meterLampsGrammar());
    engine.render(state, LedEvents(), 0, board);
    for (uint8_t step = 0; step < 4; ++step) {
      const bool expected =
          step < boundary.full || (step == boundary.full && boundary.partial);
      TEST_ASSERT_EQUAL(expected, resolvedOn(engine, kMeterIndices[step]));
    }
  }
}

void test_codex_failures_use_health_overlays_and_focus_preempts_them() {
  constexpr const char* kFailures[] = {
      "stale", "auth_required", "codex_offline", "host_offline",
      "unavailable",
  };
  struct GrammarHealth {
    LedGrammar* grammar;
    uint16_t health_mask;
    uint8_t focus_index;
    uint8_t focus_brightness;
    uint8_t failure_brightness;
  };
  GrammarHealth grammars[] = {
      {&railEchoGrammar(), 0x2492, 1, 45, 45},
      {&exceptionChannelGrammar(), 0x0249, 1, 30, 30},
      {&fieldExtensionGrammar(), 0x3000, 0, 45, 30},
      {&meterLampsGrammar(), 0x2492, 1, 45, 45},
  };

  for (const char* failure : kFailures) {
    AgentProjection projection;
    BoardAdapter projection_board;
    const RenderState failed =
        committedCodexLedState(projection, projection_board, failure, 80, 1,
                               "AGE 2H");
    for (const GrammarHealth& grammar : grammars) {
      LedEngine engine;
      BoardAdapter board;
      engine.setGrammar(*grammar.grammar);
      engine.render(failed, LedEvents(), 0, board);
      bool saw_health = false;
      for (uint8_t index = 0; index < LedEngine::kLedCount; ++index) {
        if ((grammar.health_mask &
             (static_cast<uint16_t>(1U) << index)) == 0) {
          continue;
        }
        const ResolvedLed& led = engine.resolved(index);
        if (led.hue == 0 && led.saturation == 100 &&
            led.brightness != 0 &&
            led.brightness <= LedEngine::kHealthBrightnessCap) {
          saw_health = true;
        }
      }
      for (uint8_t index = 0; index < LedEngine::kLedCount; ++index) {
        const ResolvedLed& led = engine.resolved(index);
        TEST_ASSERT_FALSE_MESSAGE(
            led.brightness != 0 && (led.hue == 180 || led.hue == 35),
            "cached/offline percentage looked current");
      }
      TEST_ASSERT_TRUE_MESSAGE(saw_health, failure);
    }
  }

  AgentProjection focus_projection;
  BoardAdapter focus_projection_board;
  committedCodexLedState(focus_projection, focus_projection_board, "stale",
                         80, -1, "AGE 16M");
  JsonDocument intent;
  TEST_ASSERT_TRUE(
      focus_projection.captureFocusIntent(0, "led-focus", intent.to<JsonObject>()));
  const RenderState focused = focus_projection.renderState(0);
  TEST_ASSERT_EQUAL(static_cast<int>(TileFeedback::Pending),
                    static_cast<int>(focused.slots[0].feedback));
  for (const GrammarHealth& grammar : grammars) {
    LedEngine engine;
    BoardAdapter board;
    engine.setGrammar(*grammar.grammar);
    engine.render(focused, LedEvents(), 0, board);
    const ResolvedLed& led = engine.resolved(grammar.focus_index);
    TEST_ASSERT_EQUAL_UINT16(185, led.hue);
    TEST_ASSERT_EQUAL_UINT8(grammar.focus_brightness, led.brightness);
  }

  JsonDocument rejected = focus_result_document("led-focus", "rejected");
  rejected["snapshot_revision"] = 1;
  TEST_ASSERT_FALSE(
      focus_projection.applyFocusResult(rejected.as<JsonObjectConst>()));
  const RenderState failed_focus = focus_projection.renderState(0);
  TEST_ASSERT_EQUAL(static_cast<int>(TileFeedback::Rejected),
                    static_cast<int>(failed_focus.slots[0].feedback));
  for (const GrammarHealth& grammar : grammars) {
    LedEngine engine;
    BoardAdapter board;
    engine.setGrammar(*grammar.grammar);
    engine.render(failed_focus, LedEvents(), 0, board);
    const ResolvedLed& led = engine.resolved(grammar.focus_index);
    TEST_ASSERT_EQUAL_UINT16(0, led.hue);
    TEST_ASSERT_EQUAL_UINT8(grammar.failure_brightness, led.brightness);
  }
}

void test_menu_all_off_and_grammar_switch_keep_led_engine_precedence() {
  AgentProjection projection;
  BoardAdapter projection_board;
  const RenderState state =
      committedCodexLedState(projection, projection_board, "current", 62, -1);
  LedGrammar* grammars[] = {
      &railEchoGrammar(), &exceptionChannelGrammar(),
      &fieldExtensionGrammar(), &meterLampsGrammar(),
  };
  BoardAdapter board;
  LedEngine engine;
  LedEvents menu;
  menu.menu_open = true;
  for (LedGrammar* grammar : grammars) {
    engine.setGrammar(*grammar);
    engine.render(state, menu, 0, board);
    TEST_ASSERT_TRUE(resolvedOn(engine, 13));
    TEST_ASSERT_EQUAL_UINT16(180, engine.resolved(13).hue);
  }

  g_led_calls.clear();
  LedEvents off = menu;
  off.all_off = true;
  engine.render(state, off, 1, board);
  TEST_ASSERT_EQUAL_UINT32(1, g_led_calls.size());
  TEST_ASSERT_EQUAL_UINT16(LedEngine::kAllMask, g_led_calls[0].mask);
  TEST_ASSERT_EQUAL_UINT8(0, g_led_calls[0].brightness);
}

void test_led_grammars_and_policy() {
  RenderState state;
  state.source_status = "current";
  state.codex.source_state = CodexSourceState::Current;
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
  state.codex.source_state = CodexSourceState::Current;
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
  const size_t field_count =
      fieldExtensionGrammar().frame(state, LedEvents(), 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_TRUE(field_count >= 2);
  TEST_ASSERT_EQUAL_UINT16(1U, segments[0].mask);
  TEST_ASSERT_EQUAL_UINT8(45, segments[0].brightness);
  LedEvents field_menu;
  field_menu.menu_open = true;
  const size_t field_menu_count =
      fieldExtensionGrammar().frame(state, field_menu, 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_TRUE(field_menu_count > field_count);
  TEST_ASSERT_EQUAL_UINT16(1U << 13, segments[field_menu_count - 1].mask);
  state.source_status = "stale";
  state.blocked_pulse_high = true;
  const size_t health_high =
      fieldExtensionGrammar().frame(state, LedEvents(), 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_EQUAL_UINT32(2, health_high);
  TEST_ASSERT_EQUAL_UINT8(10, segments[0].brightness);
  TEST_ASSERT_EQUAL_UINT8(45, segments[1].brightness);
  state.blocked_pulse_high = false;
  fieldExtensionGrammar().frame(state, LedEvents(), 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_EQUAL_UINT8(3, segments[0].brightness);
  state.source_status = "current";
  state.slots[0].feedback = TileFeedback::Disabled;
  state.slots[0].state = TileState::Blocked;
  state.blocked_pulse_high = true;
  fieldExtensionGrammar().frame(state, LedEvents(), 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_EQUAL_UINT8(38, segments[0].brightness);
  state.blocked_pulse_high = false;
  fieldExtensionGrammar().frame(state, LedEvents(), 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_EQUAL_UINT8(8, segments[0].brightness);
  const size_t meter_count =
      meterLampsGrammar().frame(state, LedEvents(), 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_TRUE(meter_count > 0);
  for (size_t index = 0; index < meter_count; ++index) {
    TEST_ASSERT_EQUAL_UINT16(
        0, static_cast<uint16_t>(segments[index].mask & ((1U << 0) | (1U << 2) | (1U << 3) | (1U << 6))));
  }
}

void test_product_input_router_orders_simultaneous_frame_without_state() {
  ProductInputFrame frame;
  frame.agent_pressed[2] = true;
  frame.agent_pressed[0] = true;
  frame.agent_pressed[1] = true;
  frame.encoder_clicked = true;
  frame.encoder_delta = -7;
  const ProductInputActions actions = ProductInputRouter::route(frame);
  TEST_ASSERT_EQUAL_UINT8(ProductInputFrame::kAgentSlotCount + 1 + 7,
                           actions.count);
  for (uint8_t slot = 0; slot < ProductInputFrame::kAgentSlotCount; ++slot) {
    TEST_ASSERT_EQUAL(
        static_cast<int>(ProductInputActionKind::AgentSlot),
        static_cast<int>(actions[slot].kind));
    TEST_ASSERT_EQUAL_INT(slot, actions[slot].value);
  }
  TEST_ASSERT_EQUAL(
      static_cast<int>(ProductInputActionKind::EncoderClick),
      static_cast<int>(actions[3].kind));
  for (uint8_t index = 4; index < actions.count; ++index) {
    TEST_ASSERT_EQUAL(
        static_cast<int>(ProductInputActionKind::EncoderRotate),
        static_cast<int>(actions[index].kind));
    TEST_ASSERT_EQUAL_INT(-1, actions[index].value);
  }

  const ProductInputActions empty =
      ProductInputRouter::route(ProductInputFrame{});
  TEST_ASSERT_EQUAL_UINT8(0, empty.count);
}

namespace {
void openMenuMode(MenuController& menu, MenuController::Mode mode,
                  uint32_t now_us) {
  if (mode == MenuController::Mode::Closed) return;
  menu.click(now_us++);
  if (mode == MenuController::Mode::Root) return;
  uint8_t cursor = 0;
  switch (mode) {
    case MenuController::Mode::Theme:
      cursor = 0;
      break;
    case MenuController::Mode::Leds:
      cursor = 1;
      break;
    case MenuController::Mode::Brightness:
      cursor = 2;
      break;
    case MenuController::Mode::Health:
      cursor = 3;
      break;
    case MenuController::Mode::About:
      cursor = 4;
      break;
    default:
      return;
  }
  if (cursor != 0) menu.rotate(cursor, now_us++);
  menu.click(now_us);
}

void makeEverySlotFocusable(JsonDocument& document) {
  JsonArray agents = document["agents"].as<JsonArray>();
  const char* entries[] = {"entry-0", "entry-1", "entry-2"};
  const char* panes[] = {"pane-0", "pane-1", "pane-2"};
  const char* terminals[] = {"term-0", "term-1", "term-2"};
  for (uint8_t slot = 0; slot < ProductInputFrame::kAgentSlotCount; ++slot) {
    JsonObject agent = agents[slot];
    agent["entry_id"] = entries[slot];
    agent["title"] = entries[slot];
    agent["discriminator"] = "repo";
    agent["state"] = "idle";
    agent["pane_id"] = panes[slot];
    agent["terminal_id"] = terminals[slot];
    agent["source_revision"] = slot + 1;
  }
}
}  // namespace

void test_product_router_keeps_direct_keys_live_in_every_menu_mode() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument document = snapshot_document(41);
  makeEverySlotFocusable(document);
  TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  const MenuController::Mode modes[] = {
      MenuController::Mode::Closed,     MenuController::Mode::Root,
      MenuController::Mode::Theme,      MenuController::Mode::Leds,
      MenuController::Mode::Brightness, MenuController::Mode::Health,
      MenuController::Mode::About,
  };
  for (MenuController::Mode mode : modes) {
    SettingsStore settings;
    settings.load();
    MenuController menu(settings);
    menu.resetFromStore();
    openMenuMode(menu, mode, 1000);
    TEST_ASSERT_EQUAL(static_cast<int>(mode),
                      static_cast<int>(menu.mode()));
    const uint8_t cursor = menu.state().cursor;
    const uint8_t viewport = menu.state().viewport_start;
    const uint32_t activity = menu.lastEncoderActivityUs();

    ProductInputFrame frame;
    frame.agent_pressed[0] = true;
    frame.agent_pressed[1] = true;
    frame.agent_pressed[2] = true;
    const ProductInputActions actions = ProductInputRouter::route(frame);
    TEST_ASSERT_EQUAL_UINT8(3, actions.count);
    for (uint8_t index = 0; index < actions.count; ++index) {
      TEST_ASSERT_EQUAL(
          static_cast<int>(ProductInputActionKind::AgentSlot),
          static_cast<int>(actions[index].kind));
      JsonDocument intent;
      char action_id[16];
      std::snprintf(action_id, sizeof(action_id), "mode-%u-%u",
                    static_cast<unsigned>(mode),
                    static_cast<unsigned>(index));
      TEST_ASSERT_TRUE(projection.captureFocusIntent(
          static_cast<uint8_t>(actions[index].value), action_id,
          intent.to<JsonObject>()));
      TEST_ASSERT_EQUAL_UINT8(index, intent["slot"].as<uint8_t>());
      TEST_ASSERT_EQUAL_UINT32(
          41, intent["snapshot_revision"].as<uint32_t>());
    }
    TEST_ASSERT_EQUAL(static_cast<int>(mode),
                      static_cast<int>(menu.mode()));
    TEST_ASSERT_EQUAL_UINT8(cursor, menu.state().cursor);
    TEST_ASSERT_EQUAL_UINT8(viewport, menu.state().viewport_start);
    TEST_ASSERT_EQUAL_UINT32(activity, menu.lastEncoderActivityUs());
  }
}

void test_simultaneous_direct_keys_precede_click_and_rotation_dispatch() {
  SettingsStore settings;
  settings.load();
  MenuController menu(settings);
  menu.resetFromStore();
  menu.click(10);
  ProductInputFrame frame;
  frame.agent_pressed[0] = true;
  frame.agent_pressed[2] = true;
  frame.encoder_clicked = true;
  frame.encoder_delta = 2;
  const ProductInputActions actions = ProductInputRouter::route(frame);
  std::vector<int> dispatch_order;
  for (uint8_t index = 0; index < actions.count; ++index) {
    const ProductInputAction& action = actions[index];
    if (action.kind == ProductInputActionKind::AgentSlot) {
      dispatch_order.push_back(10 + action.value);
    } else if (action.kind == ProductInputActionKind::EncoderClick) {
      dispatch_order.push_back(20);
      menu.click(20);
    } else {
      dispatch_order.push_back(30);
      menu.rotate(action.value, 20);
    }
  }
  const int expected[] = {10, 12, 20, 30, 30};
  TEST_ASSERT_EQUAL_INT_ARRAY(expected, dispatch_order.data(),
                              dispatch_order.size());
  TEST_ASSERT_EQUAL(static_cast<int>(MenuController::Mode::Theme),
                    static_cast<int>(menu.mode()));
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::Beacon),
                    static_cast<int>(menu.activeTheme()));
}
void test_menu_presentation_is_immediate_bounded_and_reversible() {
  SettingsStore settings;
  settings.load();
  MenuController menu(settings);
  menu.resetFromStore();

  TEST_ASSERT_TRUE(menu.click(100));
  TEST_ASSERT_EQUAL(static_cast<int>(MenuPresentationCause::Open),
                    static_cast<int>(menu.state().presentation_cause));
  TEST_ASSERT_EQUAL_INT8(0, menu.state().presentation_direction);
  TEST_ASSERT_EQUAL_UINT32(100, menu.state().presentation_started_us);
  TEST_ASSERT_TRUE(menu.state().presentation_duration_us <= 120000U);

  TEST_ASSERT_TRUE(menu.rotate(1, 200));
  TEST_ASSERT_EQUAL_UINT8(1, menu.state().cursor);
  TEST_ASSERT_EQUAL_INT8(1, menu.state().presentation_direction);
  TEST_ASSERT_EQUAL(static_cast<int>(MenuPresentationCause::Navigate),
                    static_cast<int>(menu.state().presentation_cause));
  TEST_ASSERT_EQUAL_UINT32(200, menu.state().presentation_started_us);
  TEST_ASSERT_EQUAL_UINT8(0, menu.state().presentation_progress);

  TEST_ASSERT_TRUE(menu.rotate(-1, 250));
  TEST_ASSERT_EQUAL_UINT8(0, menu.state().cursor);
  TEST_ASSERT_EQUAL_INT8(-1, menu.state().presentation_direction);
  TEST_ASSERT_EQUAL_UINT32(250, menu.state().presentation_started_us);
  TEST_ASSERT_TRUE(menu.state().presentation_duration_us <= 200000U);

  TEST_ASSERT_TRUE(menu.click(300));
  TEST_ASSERT_EQUAL(static_cast<int>(MenuController::Mode::Theme),
                    static_cast<int>(menu.mode()));
  TEST_ASSERT_EQUAL(static_cast<int>(MenuPresentationCause::Detail),
                    static_cast<int>(menu.state().presentation_cause));
  TEST_ASSERT_EQUAL_UINT8(0, menu.state().presentation_progress);
}


void test_menu_controller_walks_six_clamped_rows_and_all_pages() {
  SettingsStore settings;
  settings.load();
  MenuController menu(settings);
  menu.resetFromStore();
  TEST_ASSERT_TRUE(menu.click(100));
  const uint8_t expected_viewports[] = {0, 0, 1, 2, 3, 3};
  for (uint8_t cursor = 0; cursor < MenuController::kRootRowCount; ++cursor) {
    TEST_ASSERT_EQUAL_UINT8(cursor, menu.state().cursor);
    TEST_ASSERT_EQUAL_UINT8(expected_viewports[cursor],
                            menu.state().viewport_start);
    if (cursor + 1 < MenuController::kRootRowCount) {
      TEST_ASSERT_TRUE(menu.rotate(1, 101 + cursor));
    }
  }
  TEST_ASSERT_FALSE(menu.rotate(1, 200));
  TEST_ASSERT_EQUAL_UINT8(5, menu.state().cursor);
  TEST_ASSERT_TRUE(menu.click(201));
  TEST_ASSERT_FALSE(menu.open());

  menu.click(300);
  TEST_ASSERT_TRUE(menu.click(301));
  TEST_ASSERT_EQUAL(static_cast<int>(MenuController::Mode::Theme),
                    static_cast<int>(menu.mode()));
  TEST_ASSERT_FALSE(menu.rotate(-1, 302));
  TEST_ASSERT_TRUE(menu.rotate(20, 303));
  TEST_ASSERT_EQUAL(static_cast<int>(ThemeId::Instrument),
                    static_cast<int>(menu.activeTheme()));
  TEST_ASSERT_FALSE(menu.rotate(1, 304));
  TEST_ASSERT_TRUE(menu.click(305));
  TEST_ASSERT_EQUAL(static_cast<int>(MenuController::Mode::Root),
                    static_cast<int>(menu.mode()));

  TEST_ASSERT_TRUE(menu.rotate(1, 400));
  TEST_ASSERT_TRUE(menu.click(401));
  TEST_ASSERT_EQUAL(static_cast<int>(MenuController::Mode::Leds),
                    static_cast<int>(menu.mode()));
  TEST_ASSERT_TRUE(menu.rotate(20, 402));
  TEST_ASSERT_EQUAL(static_cast<int>(LedGrammarId::MeterLamps),
                    static_cast<int>(menu.activeGrammar()));
  TEST_ASSERT_TRUE(menu.click(403));

  TEST_ASSERT_TRUE(menu.rotate(2, 500));
  TEST_ASSERT_TRUE(menu.click(501));
  TEST_ASSERT_EQUAL(static_cast<int>(MenuController::Mode::Health),
                    static_cast<int>(menu.mode()));
  const uint8_t cursor = menu.state().cursor;
  TEST_ASSERT_FALSE(menu.rotate(1, 502));
  TEST_ASSERT_EQUAL_UINT8(cursor, menu.state().cursor);
  TEST_ASSERT_TRUE(menu.click(503));
  TEST_ASSERT_EQUAL_UINT8(cursor, menu.state().cursor);
  TEST_ASSERT_TRUE(menu.rotate(1, 504));
  TEST_ASSERT_TRUE(menu.click(505));
  TEST_ASSERT_EQUAL(static_cast<int>(MenuController::Mode::About),
                    static_cast<int>(menu.mode()));
  TEST_ASSERT_TRUE(menu.click(506));
  TEST_ASSERT_EQUAL_UINT8(4, menu.state().cursor);
}

void test_menu_brightness_previews_confirms_and_reverts_locally() {
  SettingsStore settings;
  settings.load();
  MenuController menu(settings);
  BoardAdapter board;
  menu.resetFromStore();
  menu.click(0);
  menu.rotate(2, 1);
  menu.click(2);
  TEST_ASSERT_EQUAL(static_cast<int>(MenuController::Mode::Brightness),
                    static_cast<int>(menu.mode()));
  TEST_ASSERT_TRUE(menu.rotate(-20, 3));
  TEST_ASSERT_EQUAL_UINT8(10, menu.activeBrightness());
  uint8_t brightness = 0;
  TEST_ASSERT_TRUE(menu.takeBrightnessIntent(brightness));
  TEST_ASSERT_EQUAL_UINT8(10, brightness);
  board.setBrightness(brightness);
  TEST_ASSERT_EQUAL_UINT8(10, g_brightness_calls.back());
  TEST_ASSERT_FALSE(menu.rotate(-1, 4));
  TEST_ASSERT_FALSE(menu.takeBrightnessIntent(brightness));
  const uint32_t writes_before_cancel = g_nvs_write_count;
  TEST_ASSERT_TRUE(menu.cancel());
  TEST_ASSERT_TRUE(menu.takeBrightnessIntent(brightness));
  TEST_ASSERT_EQUAL_UINT8(80, brightness);
  board.setBrightness(brightness);
  TEST_ASSERT_EQUAL_UINT8(80, g_brightness_calls.back());
  TEST_ASSERT_EQUAL_UINT32(writes_before_cancel, g_nvs_write_count);

  menu.click(10);
  menu.rotate(2, 11);
  menu.click(12);
  TEST_ASSERT_TRUE(menu.rotate(2, 13));
  TEST_ASSERT_TRUE(menu.takeBrightnessIntent(brightness));
  TEST_ASSERT_EQUAL_UINT8(100, brightness);
  board.setBrightness(brightness);
  TEST_ASSERT_EQUAL_UINT8(100, g_brightness_calls.back());
  TEST_ASSERT_TRUE(menu.click(14));
  TEST_ASSERT_EQUAL_UINT8(100, menu.storedBrightness());
  TEST_ASSERT_EQUAL_UINT32(SettingsStore::kSchemaVersion, g_nvs["ver"]);
  TEST_ASSERT_FALSE(menu.takeBrightnessIntent(brightness));
}

void test_menu_encoder_only_timeout_is_wrap_safe_and_reverts_preview() {
  SettingsStore settings;
  settings.load();
  MenuController menu(settings);
  menu.resetFromStore();
  const uint32_t opened = 0xFFF00000U;
  menu.click(opened);
  menu.rotate(2, opened + 10U);
  menu.click(opened + 20U);
  menu.rotate(-1, opened + 30U);
  uint8_t brightness = 0;
  TEST_ASSERT_TRUE(menu.takeBrightnessIntent(brightness));
  TEST_ASSERT_FALSE(
      menu.expire(opened + 30U + MenuController::kInactivityUs - 1U));
  TEST_ASSERT_TRUE(
      menu.expire(opened + 30U + MenuController::kInactivityUs));
  TEST_ASSERT_FALSE(menu.open());
  TEST_ASSERT_TRUE(menu.takeBrightnessIntent(brightness));
  TEST_ASSERT_EQUAL_UINT8(80, brightness);
  TEST_ASSERT_EQUAL_UINT32(0, g_nvs_write_count);
}

void test_all_theme_root_viewports_use_exact_three_row_geometry() {
  ThemeRenderer* themes[] = {&signalEdgeTheme(), &ledgerTheme(),
                             &beaconTheme(), &instrumentTheme()};
  const uint8_t starts[] = {0, 0, 1, 2, 3, 3};
  LGFX_Sprite sprite;
  for (uint8_t cursor = 0; cursor < 6; ++cursor) {
    MenuState menu;
    menu.open = true;
    menu.page = MenuPage::Root;
    menu.cursor = cursor;
    menu.viewport_start = starts[cursor];
    menu.theme_stored = ThemeId::SignalEdge;
    menu.grammar_stored = LedGrammarId::MeterLamps;
    menu.brightness_stored = 100;
    for (ThemeRenderer* theme : themes) {
      resetLog();
      theme->composeMenu(sprite, menu);
      TEST_ASSERT_EQUAL_UINT32(1, logTextCount("MENU"));
      for (uint8_t visible = 0; visible < 3; ++visible) {
        const uint8_t row = starts[cursor] + visible;
        const char* label = row == 0 ? "THEME"
                            : row == 1 ? "LEDS"
                            : row == 2 ? "BRIGHTNESS"
                            : row == 3 ? "HEALTH"
                            : row == 4 ? "ABOUT"
                                       : "CLOSE";
        if (theme == &beaconTheme() && row < 3) {
          const char* line = row == 0 ? "THEME SIGNAL EDGE"
                             : row == 1 ? "LEDS METER+LAMPS"
                                        : "BRIGHTNESS 100%";
          TEST_ASSERT_TRUE(logContainsTextAt(line, (128 - strlen(line) * 6) / 2,
                                             30 + visible * 24));
        } else {
          TEST_ASSERT_TRUE(logContainsTextAt(
              label,
              theme == &ledgerTheme() ? 14
              : theme == &beaconTheme() ? (128 - strlen(label) * 6) / 2
                                         : 24,
              30 + visible * 24));
        }
      }
      TEST_ASSERT_TRUE(logContainsText(
          theme == &signalEdgeTheme() ? "TURN:SEL"
                                      : "TURN:SEL CLICK:OPEN"));
      assertPanelTextBounded();
    }
  }

  MenuState exact;
  exact.open = true;
  exact.cursor = 0;
  exact.theme_stored = ThemeId::SignalEdge;
  exact.grammar_stored = LedGrammarId::RailEcho;
  resetLog();
  signalEdgeTheme().composeMenu(sprite, exact);
  TEST_ASSERT_TRUE(logContainsTextAt("MENU", 16, 4));
  TEST_ASSERT_TRUE(logContainsTextAt(">", 16, 30));
  TEST_ASSERT_TRUE(logContainsTextAt("THEME", 24, 30));
  TEST_ASSERT_TRUE(logContainsTextAt("SIGNAL EDGE", 54, 30));
  TEST_ASSERT_TRUE(logContainsAny("fillRect:12:20:112:24"));
  resetLog();
  ledgerTheme().composeMenu(sprite, exact);
  TEST_ASSERT_TRUE(logContainsTextAt("MENU", 6, 4));
  TEST_ASSERT_TRUE(logContainsTextAt(">", 6, 30));
  TEST_ASSERT_TRUE(logContainsTextAt("THEME", 14, 30));
  TEST_ASSERT_TRUE(logContainsTextAt("SIGNAL EDGE", 54, 30));
  resetLog();
  beaconTheme().composeMenu(sprite, exact);
  TEST_ASSERT_TRUE(logContainsTextAt("MENU", 52, 4));
  TEST_ASSERT_TRUE(logContainsTextAt(">", 4, 30));
  TEST_ASSERT_TRUE(logContainsTextAt("THEME SIGNAL EDGE", 13, 30));
  resetLog();
  instrumentTheme().composeMenu(sprite, exact);
  TEST_ASSERT_TRUE(logContainsTextAt("MENU", 52, 4));
  TEST_ASSERT_TRUE(logContainsTextAt(">", 16, 30));
  TEST_ASSERT_TRUE(logContainsTextAt("THEME", 24, 30));
  TEST_ASSERT_TRUE(logContainsTextAt("SIGNAL EDGE", 54, 30));
}

void test_all_theme_value_and_brightness_pages_use_approved_bands() {
  ThemeRenderer* themes[] = {&signalEdgeTheme(), &ledgerTheme(),
                             &beaconTheme(), &instrumentTheme()};
  LGFX_Sprite sprite;
  for (ThemeRenderer* theme : themes) {
    MenuState menu;
    menu.open = true;
    menu.page = MenuPage::Theme;
    menu.theme_candidate = ThemeId::Instrument;
    resetLog();
    theme->composeMenu(sprite, menu);
    TEST_ASSERT_TRUE(logContainsTextAt(
        "THEME", theme == &signalEdgeTheme() ? 16
                 : theme == &ledgerTheme() ? 6
                                            : 49,
        4));
    TEST_ASSERT_TRUE(logContainsTextAt(
        "INSTRUMENT", theme == &signalEdgeTheme() ? 16
                       : theme == &ledgerTheme() ? 6
                                                  : 34,
        30));
    TEST_ASSERT_TRUE(logContainsTextAt(
        "TURN:CHANGE", theme == &signalEdgeTheme() ? 16
                       : theme == &ledgerTheme() ? 6
                                                  : 31,
        102));
    TEST_ASSERT_TRUE(logContainsTextAt(
        "CLICK:SAVE", theme == &signalEdgeTheme() ? 16
                      : theme == &ledgerTheme() ? 6
                                                 : 34,
        114));

    menu.page = MenuPage::Leds;
    menu.grammar_candidate = LedGrammarId::MeterLamps;
    resetLog();
    theme->composeMenu(sprite, menu);
    TEST_ASSERT_TRUE(logContainsText("LEDS"));
    TEST_ASSERT_TRUE(logContainsText("METER+LAMPS"));

    menu.page = MenuPage::Brightness;
    menu.brightness_candidate = 100;
    resetLog();
    theme->composeMenu(sprite, menu);
    TEST_ASSERT_TRUE(logContainsTextAt(
        "BRIGHTNESS", theme == &signalEdgeTheme() ? 16
                       : theme == &ledgerTheme() ? 6
                                                  : 34,
        4));
    TEST_ASSERT_TRUE(logContainsTextAt("100%", 40, 24));
    TEST_ASSERT_TRUE(logContainsAny("drawRect:"));
    TEST_ASSERT_TRUE(logContainsTextAt(
        "TURN:CHANGE", theme == &signalEdgeTheme() ? 16
                       : theme == &ledgerTheme() ? 6
                                                  : 31,
        102));
    TEST_ASSERT_TRUE(logContainsTextAt(
        "CLICK:SAVE", theme == &signalEdgeTheme() ? 16
                      : theme == &ledgerTheme() ? 6
                                                 : 34,
        114));
    assertPanelTextBounded();
  }
}

void test_all_theme_health_and_about_pages_are_fixed_bounded_allowlists() {
  ThemeRenderer* themes[] = {&signalEdgeTheme(), &ledgerTheme(),
                             &beaconTheme(), &instrumentTheme()};
  LGFX_Sprite sprite;
  MenuState menu;
  menu.open = true;
  menu.page = MenuPage::Health;
  menu.diagnostics.link_status = "current";
  menu.diagnostics.herdr_status = "stale";
  menu.diagnostics.codex_status = "auth_required";
  menu.diagnostics.sync_age = "AGE 999M";
  menu.diagnostics.codex_age = "AGE N/A";
  menu.diagnostics.error_code = "E-2407";
  const int32_t rows[] = {24, 40, 56, 72, 88, 104};
  const char* labels[] = {"LINK", "HERDR", "CODEX", "SYNC AGE", "CODEX AGE",
                          "ERR"};
  const char* values[] = {"OK", "STALE", "AUTH REQUIRED", "999M", "N/A",
                          "E-2407"};
  for (ThemeRenderer* theme : themes) {
    menu.page = MenuPage::Health;
    resetLog();
    theme->composeMenu(sprite, menu);
    TEST_ASSERT_TRUE(logContainsText("HEALTH"));
    for (uint8_t row = 0; row < 6; ++row) {
      if (theme == &beaconTheme()) {
        char line[21] = {};
        snprintf(line, sizeof(line), "%s %s", labels[row], values[row]);
        TEST_ASSERT_TRUE(logContainsTextAt(line, (128 - strlen(line) * 6) / 2,
                                           rows[row]));
      } else {
        TEST_ASSERT_TRUE(logContainsTextAt(
            labels[row], theme == &ledgerTheme() ? 6 : 12, rows[row]));
        TEST_ASSERT_TRUE(logContainsTextAt(
            values[row], 120 - strlen(values[row]) * 6, rows[row]));
      }
    }
    TEST_ASSERT_TRUE(logContainsTextAt(
        "CLICK:BACK", theme == &ledgerTheme() ? 6
                      : theme == &signalEdgeTheme() ? 12
                                                    : 34,
        118));
    TEST_ASSERT_EQUAL_UINT32(0, logTextCount("NONE"));
    assertPanelTextBounded();

    menu.page = MenuPage::About;
    menu.diagnostics.firmware_version = "1234567890ABCDEF";
    menu.diagnostics.protocol_version = 2;
    menu.diagnostics.bridge_version = "";
    menu.diagnostics.device_suffix = "ABCDEF";
    menu.diagnostics.session_suffix = "123456";
    menu.diagnostics.revision_suffix = "A1B2C3";
    resetLog();
    theme->composeMenu(sprite, menu);
    TEST_ASSERT_TRUE(logContainsText("ABOUT"));
    TEST_ASSERT_TRUE(logContainsAny("1234567890ABCDEF"));
    TEST_ASSERT_FALSE(logContainsAny("123456789012..."));
    TEST_ASSERT_TRUE(logContainsAny("N/A"));
    TEST_ASSERT_TRUE(logContainsAny("ABCDEF"));
    TEST_ASSERT_TRUE(logContainsTextAt(
        "CLICK:BACK", theme == &ledgerTheme() ? 6
                      : theme == &signalEdgeTheme() ? 12
                                                    : 34,
        118));
    assertPanelTextBounded();
  }
}

void test_all_theme_menu_motion_is_decorative_and_brightness_safe() {
  ThemeRenderer* themes[] = {&signalEdgeTheme(), &ledgerTheme(),
                             &beaconTheme(), &instrumentTheme()};
  LGFX_Sprite sprite;
  MenuState menu;
  menu.open = true;
  menu.page = MenuPage::Root;
  menu.presentation_duration_us = 200000U;
  menu.cursor = 1;
  menu.viewport_start = 0;
  menu.presentation_cause = MenuPresentationCause::Navigate;
  menu.presentation_direction = 1;
  menu.presentation_progress = 0;
  for (ThemeRenderer* theme : themes) {
    menu.presentation_progress = 0;
    theme->composeMenu(sprite, menu);
    const std::vector<std::string> first = g_render_log;
    TEST_ASSERT_TRUE(logContainsText("MENU"));
    TEST_ASSERT_TRUE(theme == &beaconTheme() ? logContainsFragment("LEDS")
                                             : logContainsText("LEDS"));
    assertPanelTextBounded();

    menu.presentation_progress = 3;
    resetLog();
    theme->composeMenu(sprite, menu);
    const std::vector<std::string> settled = g_render_log;
    TEST_ASSERT_FALSE_MESSAGE(
        first == settled,
        theme == &signalEdgeTheme()
            ? "signal motion missing"
            : theme == &ledgerTheme()
                  ? "ledger motion missing"
                  : theme == &beaconTheme() ? "beacon motion missing"
                                             : "instrument motion missing");
    TEST_ASSERT_TRUE(theme == &beaconTheme() ? logContainsFragment("LEDS")
                                             : logContainsText("LEDS"));
    assertPanelTextBounded();
  }

  menu.page = MenuPage::Brightness;
  menu.brightness_candidate = 0;
  for (ThemeRenderer* theme : themes) {
    resetLog();
    theme->composeMenu(sprite, menu);
    TEST_ASSERT_TRUE(logContainsText("10%"));
    TEST_ASSERT_FALSE(logContainsText("0%"));
    assertPanelTextBounded();
  }
}

void test_menu_projection_injects_only_committed_diagnostics_and_preserves_state() {
  AgentProjection projection;
  BoardAdapter board;
  JsonDocument first = snapshot_document(1);
  first["diagnostics"]["error_code"] = "E-2404";
  first["diagnostics"]["account_identity"] = "secret@example.com";
  first["diagnostics"]["host_path"] = "/home/private";
  first["diagnostics"]["raw_error"] = "credential leaked";
  TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));

  SettingsStore settings;
  settings.load();
  MenuController controller(settings);
  controller.resetFromStore();
  controller.click(100);
  controller.rotate(3, 101);
  controller.click(102);
  TEST_ASSERT_EQUAL(static_cast<int>(MenuController::Mode::Health),
                    static_cast<int>(controller.mode()));
  const uint8_t cursor = controller.state().cursor;
  const uint8_t viewport = controller.state().viewport_start;
  const uint32_t activity = controller.lastEncoderActivityUs();

  resetLog();
  projection.renderMenu(board, signalEdgeTheme(), controller.state());
  TEST_ASSERT_TRUE(logContainsText("E-2404"));
  TEST_ASSERT_FALSE(logContainsAny("secret@example.com"));
  TEST_ASSERT_FALSE(logContainsAny("/home/private"));
  TEST_ASSERT_FALSE(logContainsAny("credential leaked"));
  std::vector<int> order = pushOrder();
  TEST_ASSERT_EQUAL_UINT32(1, order.size());
  TEST_ASSERT_EQUAL_INT(3, order[0]);

  JsonDocument update = snapshot_document(2);
  update["diagnostics"]["herdr_status"] = "stale";
  update["diagnostics"]["codex_age"] = "AGE 14M";
  TEST_ASSERT_TRUE(projection.stageSnapshot(update.as<JsonObjectConst>()));
  TEST_ASSERT_TRUE(projection.commitSnapshot(board));
  resetLog();
  projection.renderMenu(board, ledgerTheme(), controller.state());
  TEST_ASSERT_TRUE(logContainsText("STALE"));
  TEST_ASSERT_TRUE(logContainsText("14M"));
  TEST_ASSERT_EQUAL_UINT8(cursor, controller.state().cursor);
  TEST_ASSERT_EQUAL_UINT8(viewport, controller.state().viewport_start);
  TEST_ASSERT_EQUAL_UINT32(activity, controller.lastEncoderActivityUs());
  TEST_ASSERT_TRUE(projection.hasBinding(0));
  JsonDocument intent;
  TEST_ASSERT_TRUE(
      projection.captureFocusIntent(0, "menu-live", intent.to<JsonObject>()));
}

void test_diagnostic_identifier_and_version_admission_is_closed() {
  AgentProjection projection;
  JsonDocument long_suffix = snapshot_document(1);
  long_suffix["diagnostics"]["device_suffix"] = "ABCDEFG";
  TEST_ASSERT_FALSE(
      projection.stageSnapshot(long_suffix.as<JsonObjectConst>()));
  JsonDocument invalid_suffix = snapshot_document(1);
  invalid_suffix["diagnostics"]["session_suffix"] = "ABC_12";
  TEST_ASSERT_FALSE(
      projection.stageSnapshot(invalid_suffix.as<JsonObjectConst>()));
  JsonDocument path_version = snapshot_document(1);
  path_version["diagnostics"]["bridge_version"] = "/home/private";
  TEST_ASSERT_FALSE(
      projection.stageSnapshot(path_version.as<JsonObjectConst>()));
  JsonDocument identity_version = snapshot_document(1);
  identity_version["diagnostics"]["firmware_version"] =
      "secret@example";
  TEST_ASSERT_FALSE(
      projection.stageSnapshot(identity_version.as<JsonObjectConst>()));
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



void test_led_grammar_rest_truth_and_segment_bounds_across_phases() {
  RenderState state;
  state.source_status = "current";
  state.codex.source_state = CodexSourceState::Current;
  state.slots[0].state = TileState::Idle;
  state.slots[1].state = TileState::Settled;
  state.slots[2].state = TileState::Empty;
  LedEvents rest;
  rest.semantic_event = LedSemanticEvent::State;
  rest.semantic_epoch = 90;
  rest.semantic_phase = 3;
  LedSegment segments[kLedGrammarMaxSegments]{};

  const size_t exception_count = exceptionChannelGrammar().frame(
      state, rest, 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_EQUAL_UINT32(0, exception_count);
  const size_t meter_count =
      meterLampsGrammar().frame(state, rest, 0, segments,
                                kLedGrammarMaxSegments);
  for (size_t index = 0; index < meter_count; ++index) {
    TEST_ASSERT_TRUE((segments[index].mask & 0x0E00U) == 0);
  }

  state.slots[0].feedback = TileFeedback::Pending;
  state.slots[0].feedback_phase = 1;
  rest.semantic_event = LedSemanticEvent::Pending;
  rest.semantic_phase = 1;
  const size_t field_count = fieldExtensionGrammar().frame(
      state, rest, 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_LESS_OR_EQUAL_UINT32(kLedGrammarMaxSegments, field_count);
  TEST_ASSERT_EQUAL_UINT16(1U << 1, segments[0].mask);

  const size_t meter_pending = meterLampsGrammar().frame(
      state, rest, 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_LESS_OR_EQUAL_UINT32(kLedGrammarMaxSegments, meter_pending);
  for (size_t index = 0; index < meter_pending; ++index) {
    TEST_ASSERT_TRUE((segments[index].mask & (1U << 1)) == 0);
  }

  state.codex.source_state = CodexSourceState::Current;
  state.codex.primary = 100;
  state.codex.reached_limit = 1;
  rest.semantic_event = LedSemanticEvent::Health;
  rest.semantic_phase = 0;
  for (LedGrammar* grammar : {&railEchoGrammar(), &exceptionChannelGrammar(),
                              &fieldExtensionGrammar(), &meterLampsGrammar()}) {
    const size_t count =
        grammar->frame(state, rest, 0, segments, kLedGrammarMaxSegments);
    TEST_ASSERT_LESS_OR_EQUAL_UINT32(kLedGrammarMaxSegments, count);
  }
  struct EventProbe final : LedGrammar {
    mutable LedEvents seen;
    size_t frame(const RenderState&, const LedEvents& events, uint32_t,
                 LedSegment*, size_t) const override {
      seen = events;
      return 0;
    }
  } probe;
  state.transition_phase = 3;
  LedEvents explicit_start;
  explicit_start.semantic_event = LedSemanticEvent::Pending;
  explicit_start.semantic_epoch = 91;
  explicit_start.semantic_phase = 0;
  LedEngine probe_engine;
  BoardAdapter probe_board;
  probe_engine.setGrammar(probe);
  probe_engine.render(state, explicit_start, 0, probe_board);
  TEST_ASSERT_EQUAL_UINT32(91, probe.seen.semantic_epoch);
  TEST_ASSERT_EQUAL_UINT8(0, probe.seen.semantic_phase);
  state.semantic_event_epoch = 92;
  state.semantic_event_started_us = 100;
  state.semantic_event_phase = 2;
  state.transition_phase = 7;
  LedEvents derived_start;
  probe_engine.render(state, derived_start, 0, probe_board);
  TEST_ASSERT_EQUAL_UINT32(0, probe.seen.semantic_epoch);
  TEST_ASSERT_EQUAL_UINT8(0, probe.seen.semantic_phase);

  state.syncing = true;
  rest.semantic_event = LedSemanticEvent::Sync;
  rest.semantic_epoch = 91;
  for (LedGrammar* grammar : {&railEchoGrammar(), &exceptionChannelGrammar(),
                              &fieldExtensionGrammar(), &meterLampsGrammar()}) {
    LedEngine engine;
    BoardAdapter board;
    engine.setGrammar(*grammar);
    g_led_calls.clear();
    engine.render(state, rest, 0, board);
    TEST_ASSERT_EQUAL_UINT32(1, g_led_calls.size());
    TEST_ASSERT_EQUAL_UINT16(LedEngine::kAllMask, g_led_calls[0].mask);
    TEST_ASSERT_EQUAL_UINT8(0, g_led_calls[0].brightness);
  }
}

void test_menu_open_keeps_focus_feedback_clock_and_l13_decoration() {
  RenderState state;
  state.source_status = "current";
  state.codex.source_state = CodexSourceState::Current;
  state.slots[0].occupied = true;
  state.slots[0].state = TileState::Working;
  state.slots[0].feedback = TileFeedback::Pending;
  state.slots[0].semantic_event_epoch = 7;
  state.slots[0].semantic_event_started_us = 1000;
  state.slots[0].semantic_event_phase = 0;

  LedEvents menu;
  menu.menu_open = true;
  menu.semantic_event = LedSemanticEvent::MenuOpen;
  menu.semantic_epoch = 99;
  menu.semantic_start_us = 900000;

  LedEngine pending_engine;
  BoardAdapter board;
  pending_engine.setGrammar(meterLampsGrammar());
  pending_engine.render(state, menu, 1000, board);
  TEST_ASSERT_EQUAL_UINT8(45, pending_engine.resolved(1).brightness);
  TEST_ASSERT_TRUE(resolvedOn(pending_engine, 13));
  state.slots[0].semantic_event_phase = 1;
  pending_engine.render(state, menu, 1000, board);
  TEST_ASSERT_EQUAL_UINT8(0, pending_engine.resolved(1).brightness);
  TEST_ASSERT_TRUE(resolvedOn(pending_engine, 13));

  state.slots[0].feedback = TileFeedback::Success;
  state.slots[0].semantic_event_phase = 0;
  LedEngine success_engine;
  success_engine.setGrammar(railEchoGrammar());
  success_engine.render(state, menu, 1000, board);
  TEST_ASSERT_EQUAL_UINT8(45, success_engine.resolved(1).brightness);
  TEST_ASSERT_TRUE(resolvedOn(success_engine, 13));
  state.slots[0].semantic_event_phase = 1;
  success_engine.render(state, menu, 1000, board);
  TEST_ASSERT_EQUAL_UINT8(0, success_engine.resolved(1).brightness);
  TEST_ASSERT_TRUE(resolvedOn(success_engine, 13));
}

void test_menu_open_terminal_focus_feedback_uses_event_phase() {
  RenderState state;
  state.source_status = "current";
  state.codex.source_state = CodexSourceState::Current;
  state.slots[0].occupied = true;
  state.slots[0].state = TileState::Working;
  state.slots[0].semantic_event_epoch = 7;
  state.slots[0].semantic_event_started_us = 1000;
  state.slots[0].semantic_event_phase = 0;

  struct TerminalCase {
    TileFeedback feedback;
    LedSemanticEvent event;
  };
  const TerminalCase cases[] = {
      {TileFeedback::Vanished, LedSemanticEvent::Vanished},
      {TileFeedback::Uncertain, LedSemanticEvent::Uncertain},
      {TileFeedback::Failed, LedSemanticEvent::Failed},
  };
  LedEvents menu;
  menu.menu_open = true;
  menu.semantic_event = LedSemanticEvent::MenuOpen;
  menu.semantic_epoch = 99;
  menu.semantic_start_us = 900000;

  for (const TerminalCase& terminal : cases) {
    state.slots[0].feedback = terminal.feedback;
    TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(terminal.event),
                            static_cast<uint8_t>(
                                ledFeedbackSemanticEvent(terminal.feedback)));
    for (LedGrammar* grammar : {&railEchoGrammar(), &exceptionChannelGrammar(),
                                &meterLampsGrammar()}) {
      LedEngine engine;
      BoardAdapter board;
      engine.setGrammar(*grammar);
      state.slots[0].semantic_event_phase = 0;
      engine.render(state, menu, 1000, board);
      TEST_ASSERT_TRUE(engine.resolved(1).brightness > 0);
      TEST_ASSERT_TRUE(resolvedOn(engine, 13));
      state.slots[0].semantic_event_phase = 1;
      engine.render(state, menu, 1000, board);
      TEST_ASSERT_EQUAL_UINT8(0, engine.resolved(1).brightness);
      TEST_ASSERT_TRUE(resolvedOn(engine, 13));
    }
  }
}

void test_led_grammars_keep_distinct_slot_feedback_phases() {
  RenderState state;
  state.source_status = "current";
  state.codex.source_state = CodexSourceState::Current;
  state.slots[0].state = TileState::Working;
  state.slots[0].feedback = TileFeedback::Pending;
  state.slots[0].semantic_event_epoch = 101;
  state.slots[0].semantic_event_started_us = 1000;
  state.slots[0].semantic_event_phase = 1;
  state.slots[1].state = TileState::Idle;
  state.slots[1].feedback = TileFeedback::Failed;
  state.slots[1].semantic_event_epoch = 202;
  state.slots[1].semantic_event_started_us = 2000;
  state.slots[1].semantic_event_phase = 0;

  LedEvents closed;
  LedEvents menu;
  menu.menu_open = true;
  menu.semantic_event = LedSemanticEvent::MenuOpen;
  LedSegment segments[kLedGrammarMaxSegments]{};
  struct GrammarExpectation {
    LedGrammar* grammar;
    uint8_t bright_phase_zero;
  };
  const GrammarExpectation grammars[] = {
      {&railEchoGrammar(), 45},
      {&exceptionChannelGrammar(), 30},
      {&meterLampsGrammar(), 45},
  };
  for (const GrammarExpectation& expectation : grammars) {
    size_t count = expectation.grammar->frame(
        state, closed, 0, segments, kLedGrammarMaxSegments);
    TEST_ASSERT_LESS_OR_EQUAL_UINT32(kLedGrammarMaxSegments, count);
    TEST_ASSERT_EQUAL_UINT8(0, segmentBrightness(segments, count, 1U << 1));
    TEST_ASSERT_EQUAL_UINT8(expectation.bright_phase_zero,
                            segmentBrightness(segments, count, 1U << 4));
    TEST_ASSERT_EQUAL_UINT8(0, segmentBrightness(segments, count, 1U << 13));

    count = expectation.grammar->frame(
        state, menu, 0, segments, kLedGrammarMaxSegments);
    TEST_ASSERT_LESS_OR_EQUAL_UINT32(kLedGrammarMaxSegments, count);
    TEST_ASSERT_EQUAL_UINT8(0, segmentBrightness(segments, count, 1U << 1));
    TEST_ASSERT_EQUAL_UINT8(expectation.bright_phase_zero,
                            segmentBrightness(segments, count, 1U << 4));
    TEST_ASSERT_EQUAL_UINT8(25, segmentBrightness(segments, count, 1U << 13));
  }

  const TileFeedback field_cases[] = {
      TileFeedback::Pending, TileFeedback::Vanished,
      TileFeedback::Uncertain, TileFeedback::Failed,
  };
  for (const TileFeedback feedback : field_cases) {
    state.slots[0].feedback = feedback;
    size_t count = fieldExtensionGrammar().frame(
        state, closed, 0, segments, kLedGrammarMaxSegments);
    TEST_ASSERT_LESS_OR_EQUAL_UINT32(kLedGrammarMaxSegments, count);
    if (feedback == TileFeedback::Pending) {
      TEST_ASSERT_EQUAL_UINT8(45, segmentBrightness(segments, count, 1U << 1));
    } else {
      TEST_ASSERT_EQUAL_UINT8(0, segmentBrightness(segments, count, 1U << 1));
    }
    TEST_ASSERT_EQUAL_UINT8(30, segmentBrightness(segments, count, 1U << 4));
    TEST_ASSERT_EQUAL_UINT8(0, segmentBrightness(segments, count, 1U << 13));

    count = fieldExtensionGrammar().frame(
        state, menu, 0, segments, kLedGrammarMaxSegments);
    TEST_ASSERT_LESS_OR_EQUAL_UINT32(kLedGrammarMaxSegments, count);
    if (feedback == TileFeedback::Pending) {
      TEST_ASSERT_EQUAL_UINT8(45, segmentBrightness(segments, count, 1U << 1));
    } else {
      TEST_ASSERT_EQUAL_UINT8(0, segmentBrightness(segments, count, 1U << 1));
    }
    TEST_ASSERT_EQUAL_UINT8(30, segmentBrightness(segments, count, 1U << 4));
    TEST_ASSERT_EQUAL_UINT8(25, segmentBrightness(segments, count, 1U << 13));
  }

  state.source_status = "stale";
  state.blocked_pulse_high = true;
  const size_t health_count = fieldExtensionGrammar().frame(
      state, menu, 0, segments, kLedGrammarMaxSegments);
  TEST_ASSERT_LESS_OR_EQUAL_UINT32(kLedGrammarMaxSegments, health_count);
  TEST_ASSERT_EQUAL_UINT16((1U << 12) | (1U << 13), segments[0].mask);
  TEST_ASSERT_EQUAL_UINT16(0, segments[0].hue);
  TEST_ASSERT_EQUAL_UINT8(10, segments[0].brightness);
  TEST_ASSERT_EQUAL_UINT8(10, segmentBrightness(segments, health_count, 1U << 13));
}
void test_led_semantic_events_align_grammar_starts_and_fences() {
  RenderState state;

  state.source_status = "current";
  state.codex.source_state = CodexSourceState::Current;
  state.slots[0].occupied = true;
  state.slots[0].state = TileState::Working;
  state.slots[0].feedback = TileFeedback::Pending;
  state.slots[0].feedback_phase = 1;
  state.semantic_event_epoch = 41;

  LedEvents pending;
  pending.semantic_event = LedSemanticEvent::Pending;
  pending.semantic_epoch = 41;
  pending.semantic_phase = 1;
  LedSegment segments[kLedGrammarMaxSegments]{};
  const size_t field_count =
      fieldExtensionGrammar().frame(state, pending, 0, segments,
                                    kLedGrammarMaxSegments);
  TEST_ASSERT_TRUE(field_count > 0);
  TEST_ASSERT_EQUAL_UINT16(1U << 1, segments[0].mask);
  TEST_ASSERT_EQUAL_UINT8(45, segments[0].brightness);

  const size_t exception_count =
      exceptionChannelGrammar().frame(state, pending, 0, segments,
                                      kLedGrammarMaxSegments);
  TEST_ASSERT_EQUAL_UINT32(0, exception_count);

  state.slots[0].feedback = TileFeedback::Success;
  pending.semantic_event = LedSemanticEvent::Focused;
  pending.semantic_epoch = 42;
  pending.semantic_phase = 1;
  const size_t rail_count =
      railEchoGrammar().frame(state, pending, 0, segments,
                              kLedGrammarMaxSegments);
  TEST_ASSERT_EQUAL_UINT32(0, rail_count);

  state.source_status = "stale";
  state.slots[0].feedback = TileFeedback::Disabled;
  state.codex.source_state = CodexSourceState::Stale;
  pending.semantic_event = LedSemanticEvent::Health;
  pending.semantic_epoch = 43;
  pending.semantic_phase = 7;
  for (LedGrammar* grammar : {&railEchoGrammar(), &exceptionChannelGrammar(),
                              &fieldExtensionGrammar(), &meterLampsGrammar()}) {
    const size_t count =
        grammar->frame(state, pending, 0, segments, kLedGrammarMaxSegments);
    TEST_ASSERT_LESS_OR_EQUAL_UINT32(kLedGrammarMaxSegments, count);
    for (size_t index = 0; index < count; ++index) {
      TEST_ASSERT_TRUE(segments[index].hue != 120);
      TEST_ASSERT_TRUE(segments[index].hue != 35);
    }
  }
}

int runAllTests() {
  UNITY_BEGIN();
  RUN_TEST(test_menu_open_keeps_focus_feedback_clock_and_l13_decoration);
  RUN_TEST(test_menu_open_terminal_focus_feedback_uses_event_phase);
  RUN_TEST(test_led_grammars_keep_distinct_slot_feedback_phases);
  RUN_TEST(test_led_grammar_rest_truth_and_segment_bounds_across_phases);
  RUN_TEST(test_led_semantic_events_align_grammar_starts_and_fences);
  RUN_TEST(test_compose_then_flush_commits_generation);
  RUN_TEST(test_null_panel_fails_closed);
  RUN_TEST(test_generation_replacement_clears_feedback);
  RUN_TEST(test_snapshot_commit_keeps_visible_sync_cutout_hidden);
  RUN_TEST(test_capture_phase_and_level_vocabulary_is_bounded_and_deterministic);
  RUN_TEST(test_blocked_renderstate_motion_has_distinct_complete_frames);
  RUN_TEST(test_ledger_and_instrument_blocked_motion_stays_semantic_and_symmetric);
  RUN_TEST(test_capture_slot_cardinality_is_bounded_and_semantic);
  RUN_TEST(test_phase3_capture_scenes_use_production_panel4_renderers);
  RUN_TEST(test_rejected_diagnostics_preserve_committed_generation_and_binding);
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
  RUN_TEST(test_render_state_exposes_passive_hold_candidate_and_owner);
  RUN_TEST(test_passive_owner_survives_focus_and_snapshot_generation_changes);
  RUN_TEST(test_signal_edge_and_ledger_hold_mic_precedence);
  RUN_TEST(test_ledger_hold_mic_geometry_and_precedence);
  RUN_TEST(test_beacon_and_instrument_hold_mic_geometry_and_precedence);
  RUN_TEST(test_hold_capture_scenes_use_production_renderers_without_mutation);
  RUN_TEST(test_hold_cancellation_returns_to_ordinary_focus_feedback);
  RUN_TEST(test_hold_prethreshold_release_never_exposes_cancellation_state);
  RUN_TEST(test_hold_success_expiry_keeps_qualified_candidate_visible);
  RUN_TEST(test_named_focus_failures_preempt_hold_facts);
  RUN_TEST(test_source_fence_preempts_candidate_and_active_owner);
  RUN_TEST(test_lifecycle_events_preempt_hold_presentation);
  RUN_TEST(test_failed_down_and_failed_up_clear_before_report_failure);
  RUN_TEST(test_multiple_agent_keys_capture_without_waiting);
  RUN_TEST(test_settings_fresh_and_legacy_load_without_boot_write);
  RUN_TEST(test_settings_v2_roundtrip_and_bounded_brightness);
  RUN_TEST(test_settings_invalid_records_fall_back_without_write);
  RUN_TEST(test_failed_theme_redraw_enters_sync_and_disables_bindings);
  RUN_TEST(test_settings_failed_replacement_restores_prior_record_and_active_values);
  RUN_TEST(test_ledger_full_vocabulary);
  RUN_TEST(test_beacon_full_vocabulary);
  RUN_TEST(test_instrument_full_vocabulary);
  RUN_TEST(test_theme_redraw_flushes_every_agent_panel);
  RUN_TEST(test_theme_by_id_dispatches_all_four);
  RUN_TEST(test_ledger_empty_and_blocked_inversion);
  RUN_TEST(test_panel4_compositions_are_honest);
  RUN_TEST(test_codex_rows_preserve_null_zero_partial_and_populated_values);
  RUN_TEST(test_codex_source_precedence_clears_or_retains_values_truthfully);
  RUN_TEST(test_codex_limit_layers_without_hiding_source_state);
  RUN_TEST(test_codex_status_cues_do_not_cross_value_rows);
  RUN_TEST(test_codex_exact_theme_geometry_and_shared_baselines);
  RUN_TEST(test_codex_copy_is_tail_ellipsized_inside_safe_inset);
  RUN_TEST(test_codex_only_redraw_preserves_agents_bindings_and_snapshot_identity);
  RUN_TEST(test_codex_only_same_revision_repaints_panel4_without_losing_focus_intent);
  RUN_TEST(test_menu_presentation_is_immediate_bounded_and_reversible);
  RUN_TEST(test_codex_only_same_revision_keeps_open_menu_on_panel4);
  RUN_TEST(test_feedback_and_sync_copy_is_not_duplicated);
  RUN_TEST(test_phase3_capture_scenes_use_production_panel4_renderers);
  RUN_TEST(test_signal_edge_polish_geometry);
  RUN_TEST(test_usage_placeholders_follow_theme_geometry);
  RUN_TEST(test_working_symbols_are_filled_in_every_theme);
  RUN_TEST(test_beacon_pending_uses_large_animated_takeover);
  RUN_TEST(test_pending_feedback_phase_changes_all_theme_render_seams_when_ambient_static);
  RUN_TEST(test_beacon_and_instrument_phase_motion_is_distinct_and_semantically_fixed);
  RUN_TEST(test_beacon_and_instrument_fences_empty_and_codex_are_phase_static);
  RUN_TEST(test_blocked_pulse_cadence_and_phase);
  RUN_TEST(test_ambient_cadence_degrades_under_budget_pressure);
  RUN_TEST(test_main_loop_cadence_bounds_duty_and_does_not_oscillate_static);
  RUN_TEST(test_animation_metrics_bound_duty_and_measure_frame_allocation_pairs);
  RUN_TEST(test_transition_phase_is_bounded_and_interruptible);
  RUN_TEST(test_half_samples_every_second_phase_and_static_keeps_semantics);
  RUN_TEST(test_signal_edge_transition_changes_only_rail_accent);
  RUN_TEST(test_signal_edge_and_ledger_phase_motion_is_distinct_and_semantically_fixed);
  RUN_TEST(test_press_impulse_precedes_pending_render);
  RUN_TEST(test_pending_feedback_advances_at_bounded_300ms_steps);
  RUN_TEST(test_semantic_feedback_events_restart_bounded_clock);
  RUN_TEST(test_beacon_and_instrument_press_impulse_and_exact_focus_outcomes);
  RUN_TEST(test_blocked_tick_produces_changing_complete_frames_at_measured_static_cost);
  RUN_TEST(test_signal_edge_and_ledger_fences_empty_and_codex_are_phase_static);
  RUN_TEST(test_render_state_transition_metadata_is_presentation_only);
  RUN_TEST(test_urgent_generation_cuts_transition_and_fences_bindings);
  RUN_TEST(test_static_commit_flushes_complete_semantics_without_motion);
  RUN_TEST(test_blocked_motion_suppressed_by_fence_and_no_alloc);
  RUN_TEST(test_led_grammars_and_policy);
  RUN_TEST(test_led_policy_clamps_bright_led_count_and_all_off);
  RUN_TEST(test_led_grammar_scene_masks);
  RUN_TEST(test_led_grammars_consume_committed_current_usage_boundaries);
  RUN_TEST(test_meter_lamps_uses_exact_primary_quarter_boundaries);
  RUN_TEST(test_codex_failures_use_health_overlays_and_focus_preempts_them);
  RUN_TEST(test_menu_all_off_and_grammar_switch_keep_led_engine_precedence);
  RUN_TEST(test_blocked_motion_recomposes_blocked_panel_only);
  RUN_TEST(test_product_input_router_orders_simultaneous_frame_without_state);
  RUN_TEST(test_product_router_keeps_direct_keys_live_in_every_menu_mode);
  RUN_TEST(test_simultaneous_direct_keys_precede_click_and_rotation_dispatch);
  RUN_TEST(test_menu_controller_walks_six_clamped_rows_and_all_pages);
  RUN_TEST(test_menu_brightness_previews_confirms_and_reverts_locally);
  RUN_TEST(test_menu_encoder_only_timeout_is_wrap_safe_and_reverts_preview);
  RUN_TEST(test_all_theme_root_viewports_use_exact_three_row_geometry);
  RUN_TEST(test_all_theme_value_and_brightness_pages_use_approved_bands);
  RUN_TEST(test_all_theme_health_and_about_pages_are_fixed_bounded_allowlists);
  RUN_TEST(test_all_theme_menu_motion_is_decorative_and_brightness_safe);
  RUN_TEST(test_menu_projection_injects_only_committed_diagnostics_and_preserves_state);
  RUN_TEST(test_diagnostic_identifier_and_version_admission_is_closed);
  RUN_TEST(test_menu_redraw_is_panel4_only);
  return UNITY_END();
}

int main(int, char**) { return runAllTests(); }
