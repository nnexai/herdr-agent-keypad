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
void test_complete_tap_between_main_updates_is_latched() {
  board_stub::reset();
  PhysicalMap map = verified_map();
  BoardAdapter adapter;
  TEST_ASSERT_TRUE(adapter.begin(map));

  board_stub::sample(0, true, false, false);
  adapter.captureRawKeySampleForTest(100U);
  board_stub::sample(0, false, false, false);
  adapter.captureRawKeySampleForTest(110U);

  adapter.update(200U);
  uint32_t latched_at = 0;
  TEST_ASSERT_TRUE(adapter.consumePressed(0, &latched_at));
  TEST_ASSERT_EQUAL_UINT32(100U, latched_at);
  TEST_ASSERT_TRUE(adapter.consumeReleased(0));
  TEST_ASSERT_FALSE(adapter.isDown(0));
}



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

void test_same_poll_pairs_preserve_chord_and_one_sample_timestamp() {
  const uint8_t pairs[3][2] = {{0, 1}, {0, 2}, {1, 2}};
  for (uint8_t pair_index = 0; pair_index < 3; ++pair_index) {
    board_stub::reset();
    PhysicalMap map = verified_map();
    BoardAdapter adapter;
    TEST_ASSERT_TRUE(adapter.begin(map));

    const uint8_t first = pairs[pair_index][0];
    const uint8_t second = pairs[pair_index][1];
    const uint8_t expected_mask =
        static_cast<uint8_t>((1U << first) | (1U << second));
    const uint32_t timestamp = static_cast<uint32_t>(100U + pair_index);
    board_stub::sample(first, true, true, false);
    board_stub::sample(second, true, true, false);
    adapter.update(timestamp);

    TEST_ASSERT_EQUAL_UINT8(expected_mask, adapter.agentPressedMask());
    TEST_ASSERT_EQUAL_UINT8(expected_mask, adapter.agentDownMask());
    TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentReleasedMask());
    TEST_ASSERT_EQUAL_UINT32(timestamp, adapter.inputLatchedAt());

    uint32_t latched_at = 0;
    TEST_ASSERT_TRUE(adapter.consumePressed(second, &latched_at));
    TEST_ASSERT_EQUAL_UINT32(timestamp, latched_at);
    TEST_ASSERT_TRUE(adapter.consumePressed(first, &latched_at));
    TEST_ASSERT_EQUAL_UINT32(timestamp, latched_at);
    TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentPressedMask());
    TEST_ASSERT_EQUAL_UINT32(1U, board_stub::update_calls());
  }
}

void test_sequential_edges_keep_timestamps_and_release_until_consumed() {
  board_stub::reset();
  PhysicalMap map = verified_map();
  BoardAdapter adapter;
  TEST_ASSERT_TRUE(adapter.begin(map));

  board_stub::sample(0, true, true, false);
  adapter.update(0xFFFFFFF0U);
  board_stub::sample(0, true, false, false);
  board_stub::sample(1, true, true, false);
  adapter.update(0x00000010U);

  TEST_ASSERT_EQUAL_UINT8(0x03U, adapter.agentPressedMask());
  TEST_ASSERT_EQUAL_UINT8(0x03U, adapter.agentDownMask());
  TEST_ASSERT_EQUAL_UINT32(0xFFFFFFF0U, adapter.inputLatchedAt());

  uint32_t latched_at = 0;
  TEST_ASSERT_TRUE(adapter.consumePressed(1, &latched_at));
  TEST_ASSERT_EQUAL_UINT32(0x00000010U, latched_at);
  TEST_ASSERT_EQUAL_UINT32(0xFFFFFFF0U, adapter.inputLatchedAt());
  TEST_ASSERT_TRUE(adapter.consumePressed(0, &latched_at));
  TEST_ASSERT_EQUAL_UINT32(0xFFFFFFF0U, latched_at);
  TEST_ASSERT_EQUAL_UINT32(0U, adapter.inputLatchedAt());

  board_stub::sample(0, false, false, true);
  board_stub::sample(1, true, false, false);
  adapter.update(0x00000020U);
  TEST_ASSERT_EQUAL_UINT8(0x02U, adapter.agentDownMask());
  TEST_ASSERT_EQUAL_UINT8(0x01U, adapter.agentReleasedMask());

  board_stub::sample(0, false, false, false);
  board_stub::sample(1, true, false, false);
  adapter.update(0x00000030U);
  TEST_ASSERT_EQUAL_UINT8(0x01U, adapter.agentReleasedMask());
  TEST_ASSERT_TRUE(adapter.consumeReleased(0));
}

void test_repeated_down_samples_do_not_repeat_press_or_release_edges() {
  for (uint8_t slot = 0; slot < 3; ++slot) {
    board_stub::reset();
    PhysicalMap map = verified_map();
    BoardAdapter adapter;
    TEST_ASSERT_TRUE(adapter.begin(map));

    board_stub::sample(slot, true, true, false);
    adapter.update(100U);
    TEST_ASSERT_TRUE(adapter.consumePressed(slot));

    board_stub::sample(slot, true, false, false);
    adapter.update(200U);
    TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentPressedMask());
    TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(1U << slot),
                            adapter.agentDownMask());
    TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentReleasedMask());

    board_stub::sample(slot, false, false, true);
    adapter.update(300U);
    TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(1U << slot),
                            adapter.agentReleasedMask());

    board_stub::sample(slot, false, false, false);
    adapter.update(400U);
    TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(1U << slot),
                            adapter.agentReleasedMask());
    TEST_ASSERT_TRUE(adapter.consumeReleased(slot));
  }
}

void test_map_failure_clears_pending_lifecycle_and_stays_closed() {
  board_stub::reset();
  PhysicalMap map = verified_map();
  BoardAdapter adapter;
  TEST_ASSERT_TRUE(adapter.begin(map));

  board_stub::sample(0, true, true, false);
  adapter.update(100U);
  TEST_ASSERT_EQUAL_UINT8(0x01U, adapter.agentPressedMask());

  map.keys[0].has_library_index = false;
  board_stub::sample(0, true, false, false);
  adapter.update(200U);

  TEST_ASSERT_FALSE(adapter.ready());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentPressedMask());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentDownMask());
  TEST_ASSERT_EQUAL_UINT8(0x00U, adapter.agentReleasedMask());
  TEST_ASSERT_EQUAL_UINT32(0U, adapter.inputLatchedAt());
  TEST_ASSERT_FALSE(adapter.consumePressed(0));
  TEST_ASSERT_FALSE(adapter.consumeReleased(0));
  TEST_ASSERT_EQUAL_UINT32(1U, board_stub::update_calls());
}

}  // namespace

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_complete_tap_between_main_updates_is_latched);
  RUN_TEST(test_one_sample_exposes_press_down_and_release);
  RUN_TEST(test_edge_timestamp_survives_later_down_polls_until_consumed);
  RUN_TEST(test_invalid_map_never_exposes_actionable_lifecycle);
  RUN_TEST(test_adapter_uses_one_official_update_per_sample);
  RUN_TEST(test_same_poll_pairs_preserve_chord_and_one_sample_timestamp);
  RUN_TEST(test_sequential_edges_keep_timestamps_and_release_until_consumed);
  RUN_TEST(test_repeated_down_samples_do_not_repeat_press_or_release_edges);
  RUN_TEST(test_map_failure_clears_pending_lifecycle_and_stays_closed);
  return UNITY_END();
}
