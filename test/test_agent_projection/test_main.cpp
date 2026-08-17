#include <ArduinoJson.h>
#include <unity.h>
#include "../../firmware/src/app/agent_projection.h"
#include "../../firmware/src/board/board_adapter.h"
namespace { Display displays[4]; bool missing_panel = false;
JsonDocument snapshot_document(uint32_t revision) {
  JsonDocument document; JsonObject root = document.to<JsonObject>();
  root["host_epoch"] = "native-epoch"; root["snapshot_revision"] = revision; root["source_status"] = "current";
  JsonArray agents = root["agents"].to<JsonArray>();
  for (uint8_t slot = 0; slot < 3; ++slot) { JsonObject agent = agents.add<JsonObject>();
    agent["slot"] = slot; agent["entry_id"] = slot == 0 ? "entry-0" : ""; agent["title"] = slot == 0 ? "Agent" : "NO AGENT";
    agent["discriminator"] = slot == 0 ? "repo" : "NO WORKSPACE"; agent["state"] = slot == 0 ? "working" : "empty";
    agent["pane_id"] = slot == 0 ? "pane-0" : ""; agent["terminal_id"] = slot == 0 ? "term-0" : ""; agent["agent_session"] = nullptr;
    agent["source_revision"] = slot == 0 ? 1 : 0; agent["workspace_id"] = nullptr; agent["tab_id"] = nullptr; }
  return document;
} }
Display* BoardAdapter::displayAt(uint8_t index) { if (index >= 3 || (missing_panel && index == 1)) return nullptr; return &displays[index]; }
void test_compose_then_flush_commits_generation() { AgentProjection projection; JsonDocument document = snapshot_document(1); TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>())); BoardAdapter board; TEST_ASSERT_TRUE(projection.commitSnapshot(board)); TEST_ASSERT_TRUE(projection.committed()); TEST_ASSERT_TRUE(projection.hasBinding(0)); TEST_ASSERT_FALSE(projection.hasBinding(1)); }
void test_null_panel_fails_closed() { AgentProjection projection; JsonDocument document = snapshot_document(2); TEST_ASSERT_TRUE(projection.stageSnapshot(document.as<JsonObjectConst>())); BoardAdapter board; missing_panel = true; TEST_ASSERT_FALSE(projection.commitSnapshot(board)); TEST_ASSERT_FALSE(projection.committed()); TEST_ASSERT_FALSE(projection.hasBinding(0)); missing_panel = false; }
void test_generation_replacement_clears_feedback() { AgentProjection projection; JsonDocument first = snapshot_document(1); JsonDocument second = snapshot_document(2); BoardAdapter board; TEST_ASSERT_TRUE(projection.stageSnapshot(first.as<JsonObjectConst>())); TEST_ASSERT_TRUE(projection.commitSnapshot(board)); TEST_ASSERT_TRUE(projection.stageSnapshot(second.as<JsonObjectConst>())); TEST_ASSERT_TRUE(projection.commitSnapshot(board)); TEST_ASSERT_EQUAL(static_cast<int>(AgentProjection::Feedback::Ready), static_cast<int>(projection.feedback(0))); }
int main(int, char**) { UNITY_BEGIN(); RUN_TEST(test_compose_then_flush_commits_generation); RUN_TEST(test_null_panel_fails_closed); RUN_TEST(test_generation_replacement_clears_feedback); return UNITY_END(); }
