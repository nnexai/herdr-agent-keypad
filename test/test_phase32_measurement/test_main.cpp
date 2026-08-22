#include <chrono>
#include <cstdlib>
#include <fstream>
#include <string>

#include <unity.h>

#include "../../firmware/src/app/hold_controller.h"
#include "../../firmware/src/app/product_input_router.h"
#include "../../firmware/src/transport/fixed_space_hid.h"

namespace {
int g_space_down = 0;
int g_release_all = 0;
bool g_hid_ready = true;

struct Observation {
  int down = 0;
  int up = 0;
  ProofMetrics metrics;
  bool passed = false;
};

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

uint64_t observed_now_ns() {
  return static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
}

Observation execute_category(const std::string& category, uint8_t slot,
                             uint32_t threshold_us = 550000U) {
  reset_hid();
  FixedSpaceHid hid;
  ProofMetrics metrics;
  HoldController controller(hid, threshold_us, &metrics);
  const uint8_t bit = static_cast<uint8_t>(1U << slot);
  const uint8_t other_slot = static_cast<uint8_t>((slot + 1U) % 3U);
  const uint8_t other_bit = static_cast<uint8_t>(1U << other_slot);
  const char* action = "measurement-action";
  const char* other_action = "measurement-other";
  const uint32_t threshold_at = 1000U + threshold_us;
  std::string mode = category;
  if (mode == "short") mode = "short_press";
  if (mode == "overlap") mode = "overlap_chord";
  if (mode == "stale_failure_session_lifecycle") {
    mode = "stale_failure_session";
  }

  if (mode == "overlap_chord") {
    const bool first = controller.registerPress(slot, action, 1000);
    const bool second = controller.registerPress(other_slot, other_action, 1000);
    controller.observeFrame(input(static_cast<uint8_t>(bit | other_bit),
                                  static_cast<uint8_t>(bit | other_bit), 0),
                            1000, true);
    controller.observeFocusResult(slot, action, true, 1100);
    controller.observeFocusResult(other_slot, other_action, true, 1100);
    controller.observeFrame(input(0, static_cast<uint8_t>(bit | other_bit), 0),
                            threshold_at, true);
    controller.observeFrame(input(0, 0, static_cast<uint8_t>(bit | other_bit)),
                            threshold_at + 1U, true);
    Observation result{g_space_down, g_release_all, metrics, false};
    result.passed = first && second && result.down == 0 && !controller.active() &&
                    metrics.chord_lockouts == 1;
    return result;
  }

  const bool registered = controller.registerPress(slot, action, 1000);
  controller.observeFrame(input(bit, bit, 0, 1000), 1000, true);
  if (mode == "short_press") {
    controller.observeFocusResult(slot, action, true, 1100);
    controller.observeFrame(input(0, 0, bit), 100000, true);
  } else if (mode == "authorized_hold") {
    controller.observeFocusResult(slot, action, true, 1100);
    controller.observeFrame(input(0, bit, 0), threshold_at, true);
    controller.observeFrame(input(0, 0, bit), threshold_at + 1U, true);
  } else if (mode == "delayed_ack_threshold_first") {
    controller.observeFrame(input(0, bit, 0), threshold_at, true);
    controller.observeFocusResult(slot, action, true, threshold_at + 1U);
    controller.observeFrame(input(0, bit, 0), threshold_at + 1U, true);
    controller.observeFrame(input(0, 0, bit), threshold_at + 2U, true);
  } else if (mode == "early_release") {
    controller.observeFrame(input(0, 0, bit), 2000, true);
    controller.observeFocusResult(slot, action, true, 3000);
    controller.observeFrame(input(0, 0, 0), threshold_at, true);
  } else if (mode == "stale_failure_session") {
    controller.observeFocusResult(slot, "stale-action", true, 1100);
    controller.observeFocusResult(slot, action, false, 1200);
    controller.observeFrame(input(0, bit, 0), threshold_at, true);
    controller.observeFrame(input(0, 0, bit), threshold_at + 1U, true);
    if (category == "stale_failure_session_lifecycle") {
      const bool cleared = controller.onLifecycle(
          HoldController::LifecycleEvent::SessionReplacement);
      controller.observeFrame(input(0, 0, 0), threshold_at + 2U, true);
      Observation result{g_space_down, 0, metrics, false};
      result.passed = registered && cleared && g_release_all == 1 &&
                      result.down == 0 && !controller.active() &&
                      metrics.lifecycle_clears == 1 &&
                      metrics.release_all_failures == 0;
      return result;
    }
  } else if (mode == "repeat_behavior") {
    controller.observeFocusResult(slot, action, true, 1100);
    controller.observeFrame(input(0, bit, 0), threshold_at, true);
    for (uint8_t repeat = 0; repeat < 5; ++repeat) {
      controller.observeFrame(input(0, bit, 0), threshold_at + 10U + repeat,
                              true);
    }
    controller.observeFrame(input(0, 0, bit), threshold_at + 20U, true);
  } else if (mode == "owner_independence") {
    controller.observeFocusResult(slot, action, true, 1100);
    controller.observeFrame(input(0, bit, 0), threshold_at, true);
    const bool replacement = controller.registerPress(other_slot, other_action,
                                                       threshold_at + 10U);
    controller.observeFrame(input(other_bit, static_cast<uint8_t>(bit | other_bit), 0),
                            threshold_at + 10U, true);
    controller.observeFocusResult(other_slot, other_action, true,
                                  threshold_at + 11U);
    controller.observeFrame(input(0, static_cast<uint8_t>(bit | other_bit), 0),
                            threshold_at + 550010U, true);
    controller.observeFrame(input(0, other_bit, bit), threshold_at + 550011U,
                            true);
    controller.observeFrame(input(0, 0, other_bit), threshold_at + 550012U,
                            true);
    Observation result{g_space_down, g_release_all, metrics, false};
    result.passed = registered && !replacement && result.down == 1 &&
                    result.up == 1 && !controller.active();
    return result;
  } else if (mode == "physical_release") {
    controller.observeFocusResult(slot, action, true, 1100);
    controller.observeFrame(input(0, bit, 0), threshold_at, true);
    controller.observeFrame(input(0, 0, bit), threshold_at + 100U, true);
  } else {
    return Observation{g_space_down, g_release_all, metrics, false};
  }

  const bool expects_hold = mode == "authorized_hold" ||
                            mode == "delayed_ack_threshold_first" ||
                            mode == "repeat_behavior" ||
                            mode == "physical_release";
  Observation result{g_space_down, g_release_all, metrics, false};
  result.passed = registered && !controller.active() &&
                  result.down == (expects_hold ? 1 : 0) &&
                  result.up == (expects_hold ? 1 : 0) &&
                  metrics.space_down_requests == (expects_hold ? 1U : 0U) &&
                  metrics.space_down_completions == (expects_hold ? 1U : 0U) &&
                  metrics.space_up_requests == (expects_hold ? 1U : 0U) &&
                  metrics.space_up_completions == (expects_hold ? 1U : 0U) &&
                  metrics.hid_send_failures == 0 &&
                  metrics.release_all_failures == 0;
  return result;
}

Observation execute_lifecycle(HoldController::LifecycleEvent event, uint8_t slot) {
  reset_hid();
  FixedSpaceHid hid;
  ProofMetrics metrics;
  HoldController controller(hid, 550000U, &metrics);
  const uint8_t bit = static_cast<uint8_t>(1U << slot);
  const char* action = "lifecycle-action";
  const bool registered = controller.registerPress(slot, action, 1000);
  controller.observeFrame(input(bit, bit, 0, 1000), 1000, true);
  controller.observeFocusResult(slot, action, true, 1100);
  controller.observeFrame(input(0, bit, 0), 551000, true);
  const bool released = controller.onLifecycle(event);
  controller.observeFrame(input(0, 0, bit), 551001, true);
  Observation result{g_space_down, g_release_all, metrics, false};
  result.passed = registered && released && result.down == 1 && result.up == 1 &&
                  !controller.active() && !controller.hasCandidate() &&
                  metrics.lifecycle_clears == 1 &&
                  metrics.release_all_failures == 0;
  return result;
}

void emit(std::ofstream& output, const char* kind, const std::string& row_id,
          int index, const std::string& category, int slot,
          const Observation& observation) {
  output << kind << ',' << row_id << ',' << index << ',' << category << ','
         << slot << ',' << observation.down << ',' << observation.up << ','
         << observation.metrics.space_down_requests << ','
         << observation.metrics.space_down_completions << ','
         << observation.metrics.space_up_requests << ','
         << observation.metrics.space_up_completions << ','
         << observation.metrics.eligibility_to_down_max_us << ','
         << observation.metrics.physical_release_to_up_max_us << ','
         << (observation.passed ? 1 : 0) << ',' << observed_now_ns() << '\n';
}

void emit_repeated(std::ofstream& output, const std::string& row_id,
                   int count, const std::string& category) {
  for (int index = 0; index < count; ++index) {
    const uint8_t slot = static_cast<uint8_t>(index % 3);
    emit(output, "row", row_id, index, category, slot,
         execute_category(category, slot));
  }
}

void test_emit_phase32_measurements() {
  const char* output_path = std::getenv("PHASE32_MEASUREMENT_OUTPUT");
  const char* schedule_path = std::getenv("PHASE32_MEASUREMENT_SCHEDULE");
  TEST_ASSERT_NOT_NULL(output_path);
  TEST_ASSERT_NOT_NULL(schedule_path);
  std::ofstream output(output_path, std::ios::trunc);
  std::ifstream schedule(schedule_path);
  TEST_ASSERT_TRUE(output.good());
  TEST_ASSERT_TRUE(schedule.good());
  output << "P32M1\n";

  int calibration_index = 0;
  constexpr int thresholds_ms[] = {500, 525, 550, 575, 600};
  for (uint8_t slot = 0; slot < 3; ++slot) {
    for (int sample = 0; sample < 60; ++sample) {
      const bool hold = sample >= 30;
      const int threshold_ms = thresholds_ms[sample % 5];
      Observation observation = execute_category(
          hold ? "authorized_hold" : "short_press", slot,
          static_cast<uint32_t>(threshold_ms * 1000));
      emit(output, "calibration", "threshold-calibration", calibration_index++,
           hold ? "hold" : "short", slot, observation);
    }
  }

  emit_repeated(output, "immediate-focus-short-separation", 90, "short_press");
  for (int index = 0; index < 180; ++index) {
    const std::string category = index % 2 == 0
                                     ? "authorized_hold"
                                     : "delayed_ack_threshold_first";
    emit(output, "row", "focus-before-hid-ordering", index, category,
         index % 3, execute_category(category, static_cast<uint8_t>(index % 3)));
  }
  emit_repeated(output, "release-before-ack", 120, "early_release");
  emit_repeated(output, "stale-failure-source-session", 220,
                "stale_failure_session");
  emit_repeated(output, "repeat-behavior", 30, "repeat_behavior");
  emit_repeated(output, "active-owner-independence", 30,
                "owner_independence");
  emit_repeated(output, "physical-release", 90, "physical_release");

  for (int index = 0; index < 5; ++index) {
    emit(output, "row", "usb-removal", index, "usb_stopped", index % 3,
         execute_lifecycle(HoldController::LifecycleEvent::UsbStopped,
                           static_cast<uint8_t>(index % 3)));
    emit(output, "row", "controlled-reset", index, "controlled_reset",
         index % 3,
         execute_lifecycle(HoldController::LifecycleEvent::ControlledReset,
                           static_cast<uint8_t>(index % 3)));
    emit(output, "row", "suspend-resume", index, "suspend_resume",
         index % 3,
         execute_lifecycle(HoldController::LifecycleEvent::UsbSuspend,
                           static_cast<uint8_t>(index % 3)));
  }
  for (int index = 0; index < 10; ++index) {
    emit(output, "row", "reconnect-session", index, "session_replacement",
         index % 3,
         execute_lifecycle(HoldController::LifecycleEvent::SessionReplacement,
                           static_cast<uint8_t>(index % 3)));
  }
  emit_repeated(output, "input-latency", 100, "physical_release");

  std::string category;
  int stress_index = 0;
  while (std::getline(schedule, category)) {
    if (category.empty()) continue;
    emit(output, "stress", "mixed-stress", stress_index, category,
         stress_index % 3,
         execute_category(category, static_cast<uint8_t>(stress_index % 3)));
    ++stress_index;
  }
  TEST_ASSERT_EQUAL_INT(300, stress_index);
  output.flush();
  TEST_ASSERT_TRUE(output.good());
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
  RUN_TEST(test_emit_phase32_measurements);
  return UNITY_END();
}
