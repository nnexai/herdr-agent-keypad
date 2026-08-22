#include <stdint.h>

#include <unity.h>

#include "../../firmware/src/app/hold_controller.h"
#include "../../firmware/src/app/product_input_router.h"
#include "../../firmware/src/transport/fixed_space_hid.h"

namespace {
int g_space_down = 0;
int g_release_all = 0;
bool g_hid_ready = true;

ProductInputFrame input(uint8_t pressed, uint8_t down, uint8_t released,
                        uint32_t edge = 1000) {
  ProductInputFrame frame;
  for (uint8_t slot = 0; slot < ProductInputFrame::kAgentSlotCount; ++slot) {
    frame.agent_pressed[slot] = (pressed & (1U << slot)) != 0;
    frame.agent_down[slot] = (down & (1U << slot)) != 0;
    frame.agent_released[slot] = (released & (1U << slot)) != 0;
    frame.agent_latched_at_us[slot] = frame.agent_pressed[slot] ? edge : 0;
  }
  return frame;
}

void reset_hid() {
  g_space_down = 0;
  g_release_all = 0;
  g_hid_ready = true;
}


void test_short_press_never_emits_space() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", 1000));
  controller.observeFrame(input(1, 1, 0, 1000), 1000, true);
  controller.observeFrame(input(0, 1, 0), 550999, true);
  controller.observeFrame(input(0, 0, 1), 551000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
  TEST_ASSERT_EQUAL_INT(0, g_release_all);
}

void test_ack_before_threshold_activates_once_at_equality_and_releases_once() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", 1000));
  controller.observeFrame(input(1, 1, 0, 1000), 1000, true);
  controller.observeFocusResult(0, "action-a", true);
  controller.observeFrame(input(0, 1, 0), 550999, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
  controller.observeFrame(input(0, 1, 0), 551000, true);
  controller.observeFrame(input(0, 1, 0), 700000, true);
  TEST_ASSERT_EQUAL_INT(1, g_space_down);
  controller.observeFrame(input(0, 0, 1), 700001, true);
  controller.observeFrame(input(0, 0, 0), 700002, true);
  TEST_ASSERT_EQUAL_INT(1, g_release_all);
}

void test_threshold_before_ack_waits_for_exact_success() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(1, "action-b", 1000));
  controller.observeFrame(input(2, 2, 0, 1000), 1000, true);
  controller.observeFrame(input(0, 2, 0), 551000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
  controller.observeFocusResult(1, "action-b", true);
  controller.observeFrame(input(0, 2, 0), 551001, true);
  TEST_ASSERT_EQUAL_INT(1, g_space_down);
}

void test_same_poll_chord_results_are_focus_only() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", 1000));
  TEST_ASSERT_TRUE(controller.registerPress(1, "action-b", 1000));
  controller.observeFrame(input(3, 3, 0, 1000), 1000, true);
  controller.observeFocusResult(0, "action-a", true);
  controller.observeFocusResult(1, "action-b", true);
  controller.observeFrame(input(0, 3, 0), 551000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
}

void test_threshold_before_ack_single_key_activates_after_result() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(1, "action-b", 1000));
  controller.observeFrame(input(2, 2, 0, 1000), 1000, true);
  controller.observeFrame(input(0, 0, 2), 2000, false);
  TEST_ASSERT_TRUE(controller.registerPress(1, "action-b2", 3000));
  controller.observeFrame(input(2, 2, 0, 3000), 3000, true);
  controller.observeFrame(input(0, 2, 0), 553000, true);
  controller.observeFocusResult(1, "action-b2", true);
  controller.observeFrame(input(0, 2, 0), 553001, true);
  TEST_ASSERT_EQUAL_INT(1, g_space_down);
}

void test_failed_or_mismatched_result_cannot_activate() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", 1000));
  controller.observeFrame(input(1, 1, 0, 1000), 1000, true);
  controller.observeFocusResult(0, "wrong-action", true);
  controller.observeFocusResult(0, "action-a", false);
  controller.observeFrame(input(0, 1, 0), 551000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
}


void test_release_before_authorization_is_monotonic() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(2, "action-c", 1000));
  controller.observeFrame(input(4, 4, 0, 1000), 1000, true);
  controller.observeFrame(input(0, 0, 4), 2000, true);
  controller.observeFocusResult(2, "action-c", true);
  controller.observeFrame(input(0, 0, 0), 600000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
  TEST_ASSERT_EQUAL_INT(0, g_release_all);
}

void test_newest_sequential_candidate_replaces_only_hold_authority() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", 1000));
  controller.observeFrame(input(1, 1, 0, 1000), 1000, true);
  TEST_ASSERT_TRUE(controller.registerPress(1, "action-b", 2000));
  controller.observeFrame(input(2, 3, 0, 2000), 2000, true);
  controller.observeFocusResult(0, "action-a", true);
  controller.observeFrame(input(0, 3, 0), 551000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
  controller.observeFocusResult(1, "action-b", true);
  controller.observeFrame(input(0, 3, 0), 552000, true);
  TEST_ASSERT_EQUAL_INT(1, g_space_down);
}

void test_same_poll_chord_locks_until_all_keys_up() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", 1000));
  TEST_ASSERT_TRUE(controller.registerPress(1, "action-b", 1000));
  controller.observeFrame(input(3, 3, 0, 1000), 1000, true);
  controller.observeFocusResult(0, "action-a", true);
  controller.observeFocusResult(1, "action-b", true);
  controller.observeFrame(input(0, 3, 0), 551000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
  controller.observeFrame(input(0, 0, 3), 552000, true);
  TEST_ASSERT_TRUE(controller.registerPress(2, "action-c", 553000));
  controller.observeFrame(input(4, 4, 0, 553000), 553000, true);
  controller.observeFocusResult(2, "action-c", true);
  controller.observeFrame(input(0, 4, 0), 1103000, true);
  TEST_ASSERT_EQUAL_INT(1, g_space_down);
}

void test_owner_is_stable_and_never_transfers() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", 1000));
  controller.observeFrame(input(1, 1, 0, 1000), 1000, true);
  controller.observeFocusResult(0, "action-a", true);
  controller.observeFrame(input(0, 1, 0), 551000, true);
  TEST_ASSERT_EQUAL_INT(1, g_space_down);
  TEST_ASSERT_FALSE(controller.registerPress(1, "action-b", 600000));
  controller.observeFrame(input(2, 3, 0, 600000), 600000, true);
  controller.observeFocusResult(1, "action-b", true);
  controller.observeFrame(input(0, 3, 0), 1151000, true);
  TEST_ASSERT_EQUAL_INT(1, g_space_down);
  controller.observeFrame(input(0, 2, 1), 1152000, true);
  TEST_ASSERT_EQUAL_INT(1, g_release_all);
  controller.observeFrame(input(0, 0, 2), 1153000, true);
  TEST_ASSERT_TRUE(controller.registerPress(1, "action-b2", 1154000));
  controller.observeFrame(input(2, 2, 0, 1154000), 1154000, true);
  controller.observeFocusResult(1, "action-b2", true);
  controller.observeFrame(input(0, 2, 0), 1704000, true);
  TEST_ASSERT_EQUAL_INT(2, g_space_down);
}

void test_hid_failure_does_not_leave_active_owner_or_retry() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", 1000));
  controller.observeFrame(input(1, 1, 0, 1000), 1000, true);
  controller.observeFocusResult(0, "action-a", true);
  g_hid_ready = false;
  controller.observeFrame(input(0, 1, 0), 551000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
  g_hid_ready = true;
  controller.observeFrame(input(0, 1, 0), 700000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
}
void test_wrap_safe_threshold_equality() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  const uint32_t edge = UINT32_MAX - 100U;
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", edge));
  controller.observeFrame(input(1, 1, 0, edge), edge, true);
  controller.observeFocusResult(0, "action-a", true);
  controller.observeFrame(input(0, 1, 0), edge + 550000U, true);
  TEST_ASSERT_EQUAL_INT(1, g_space_down);
}

void test_unavailable_hid_cancels_candidate_and_owner() {
  FixedSpaceHid hid;
  HoldController controller(hid, 550000);
  TEST_ASSERT_TRUE(controller.registerPress(0, "action-a", 1000));
  controller.observeFrame(input(1, 1, 0, 1000), 1000, false);
  controller.observeFocusResult(0, "action-a", true);
  controller.observeFrame(input(0, 1, 0), 551000, true);
  TEST_ASSERT_EQUAL_INT(0, g_space_down);
}

}  // namespace
void setUp() { reset_hid(); }
void tearDown() {}

bool FixedSpaceHid::spaceDown() {
  if (!g_hid_ready) return false;
  ++g_space_down;
  return true;
}

bool FixedSpaceHid::releaseAll() {
  ++g_release_all;
  return g_hid_ready;
}

bool FixedSpaceHid::ready() { return g_hid_ready; }

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_short_press_never_emits_space);
  RUN_TEST(test_ack_before_threshold_activates_once_at_equality_and_releases_once);
  RUN_TEST(test_threshold_before_ack_waits_for_exact_success);
  RUN_TEST(test_threshold_before_ack_single_key_activates_after_result);
  RUN_TEST(test_same_poll_chord_results_are_focus_only);
  RUN_TEST(test_failed_or_mismatched_result_cannot_activate);
  RUN_TEST(test_release_before_authorization_is_monotonic);
  RUN_TEST(test_newest_sequential_candidate_replaces_only_hold_authority);
  RUN_TEST(test_same_poll_chord_locks_until_all_keys_up);
  RUN_TEST(test_owner_is_stable_and_never_transfers);
  RUN_TEST(test_hid_failure_does_not_leave_active_owner_or_retry);
  RUN_TEST(test_wrap_safe_threshold_equality);
  RUN_TEST(test_unavailable_hid_cancels_candidate_and_owner);
  return UNITY_END();
}
