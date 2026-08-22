#include <stdint.h>

#include <unity.h>

#include "../../firmware/src/board/board_adapter.h"

namespace board_stub {
bool next_down[5] = {};
bool next_pressed[5] = {};
bool next_released[5] = {};
uint32_t update_count = 0;
}  // namespace board_stub

namespace {

PhysicalMap verified_map() {
  PhysicalMap map;
  map.loadVerified();
  return map;
}

void setUp() {}
void tearDown() {}

void test_one_sample_exposes_press_down_and_release() {
  board_stub::reset();
  PhysicalMap map = verified_map();
  BoardAdapter adapter;
  TEST_ASSERT_TRUE(adapter.begin(map));

  board_stub::sample(0, true, true, false);
  adapter.update(100U);
  TEST_ASSERT_EQUAL_UINT8(0x01U, adapter.agentPressedMask());
  TEST_ASSERT_EQUAL_UINT8(0x01U, adapter.agentDownMask());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentReleasedMask());
  TEST_ASSERT_TRUE(adapter.wasPressed(0));
  TEST_ASSERT_TRUE(adapter.isDown(0));

  uint32_t latched_at = 0;
  TEST_ASSERT_TRUE(adapter.consumePressed(0, &latched_at));
  TEST_ASSERT_EQUAL_UINT32(100U, latched_at);
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentPressedMask());
  TEST_ASSERT_TRUE(adapter.isDown(0));

  board_stub::sample(0, true, false, false);
  adapter.update(200U);
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentPressedMask());
  TEST_ASSERT_EQUAL_UINT8(0x01U, adapter.agentDownMask());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentReleasedMask());

  board_stub::sample(0, false, false, true);
  adapter.update(300U);
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentPressedMask());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentDownMask());
  TEST_ASSERT_EQUAL_UINT8(0x01U, adapter.agentReleasedMask());
  TEST_ASSERT_TRUE(adapter.consumeReleased(0));
  TEST_ASSERT_FALSE(adapter.consumeReleased(0));

  board_stub::sample(0, false, false, false);
  adapter.update(400U);
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentReleasedMask());
  TEST_ASSERT_FALSE(adapter.isDown(0));
}

void test_edge_timestamp_survives_later_down_polls_until_consumed() {
  board_stub::reset();
  PhysicalMap map = verified_map();
  BoardAdapter adapter;
  TEST_ASSERT_TRUE(adapter.begin(map));

  board_stub::sample(1, true, true, false);
  adapter.update(0xFFFFFFF0U);
  TEST_ASSERT_EQUAL_UINT32(0xFFFFFFF0U, adapter.inputLatchedAt());

  board_stub::sample(1, true, false, false);
  adapter.update(0x00000010U);
  TEST_ASSERT_TRUE(adapter.isDown(1));
  TEST_ASSERT_EQUAL_UINT32(0xFFFFFFF0U, adapter.inputLatchedAt());

  uint32_t latched_at = 0;
  TEST_ASSERT_TRUE(adapter.consumePressed(1, &latched_at));
  TEST_ASSERT_EQUAL_UINT32(0xFFFFFFF0U, latched_at);
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentPressedMask());
}

void test_invalid_map_never_exposes_actionable_lifecycle() {
  board_stub::reset();
  PhysicalMap map;
  BoardAdapter adapter;
  TEST_ASSERT_FALSE(adapter.begin(map));

  board_stub::sample(0, true, true, false);
  adapter.update(123U);
  TEST_ASSERT_FALSE(adapter.ready());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentPressedMask());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentDownMask());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentReleasedMask());
  TEST_ASSERT_FALSE(adapter.wasPressed(0));
  TEST_ASSERT_FALSE(adapter.isDown(0));
  TEST_ASSERT_FALSE(adapter.consumePressed(0));
  TEST_ASSERT_FALSE(adapter.consumeReleased(0));
  TEST_ASSERT_EQUAL_UINT32(0U, board_stub::update_calls());
}

void test_adapter_uses_one_official_update_per_sample() {
  board_stub::reset();
  PhysicalMap map = verified_map();
  BoardAdapter adapter;
  TEST_ASSERT_TRUE(adapter.begin(map));

  board_stub::sample(2, true, true, false);
  adapter.update(10U);
  TEST_ASSERT_EQUAL_UINT32(1U, board_stub::update_calls());
  TEST_ASSERT_EQUAL_UINT8(0x04U, adapter.agentPressedMask());

  board_stub::sample(2, true, false, false);
  adapter.update(20U);
  TEST_ASSERT_EQUAL_UINT32(2U, board_stub::update_calls());
  TEST_ASSERT_EQUAL_UINT8(0x04U, adapter.agentDownMask());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentReleasedMask());
}

}  // namespace

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_one_sample_exposes_press_down_and_release);
  RUN_TEST(test_edge_timestamp_survives_later_down_polls_until_consumed);
  RUN_TEST(test_invalid_map_never_exposes_actionable_lifecycle);
  RUN_TEST(test_adapter_uses_one_official_update_per_sample);
  return UNITY_END();
}
