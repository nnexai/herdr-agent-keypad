#include <unity.h>

#include "metrics/hid_reset_journal.h"

namespace {

void test_completed_cycle_is_preserved_for_next_boot() {
  RetainedHidJournalState retained = {};
  HidResetJournal first(retained);
  first.begin(1);

  first.beginReport(HidReportKind::SpaceDown);
  first.completeReport(true);
  first.beginReport(HidReportKind::Empty);
  first.completeReport(true);
  first.beginLifecycle(3);
  first.completeLifecycle(true);

  HidResetJournal second(retained);
  second.begin(7);
  const HidResetSnapshot snapshot = second.snapshot();

  TEST_ASSERT_EQUAL_UINT32(7, snapshot.reset_reason);
  TEST_ASSERT_EQUAL_UINT32(2, snapshot.current_boot_sequence);
  TEST_ASSERT_TRUE(snapshot.previous_boot_valid);
  TEST_ASSERT_EQUAL_UINT32(1, snapshot.previous_boot_sequence);
  TEST_ASSERT_EQUAL_UINT32(2, snapshot.previous_report_attempts);
  TEST_ASSERT_EQUAL_UINT32(2, snapshot.previous_report_completions);
  TEST_ASSERT_EQUAL_UINT32(1, snapshot.previous_space_down_completions);
  TEST_ASSERT_EQUAL_UINT32(1, snapshot.previous_empty_report_completions);
  TEST_ASSERT_EQUAL_UINT32(static_cast<uint32_t>(HidReportKind::Empty),
                           snapshot.previous_last_report_kind);
  TEST_ASSERT_EQUAL_UINT32(static_cast<uint32_t>(HidOperationStatus::Succeeded),
                           snapshot.previous_last_report_status);
  TEST_ASSERT_EQUAL_UINT32(3, snapshot.previous_last_lifecycle_event);
  TEST_ASSERT_EQUAL_UINT32(static_cast<uint32_t>(HidOperationStatus::Succeeded),
                           snapshot.previous_last_lifecycle_status);
}

void test_interrupted_report_is_visible_after_reset() {
  RetainedHidJournalState retained = {};
  HidResetJournal first(retained);
  first.begin(1);
  first.beginReport(HidReportKind::SpaceDown);

  HidResetJournal second(retained);
  second.begin(8);
  const HidResetSnapshot snapshot = second.snapshot();

  TEST_ASSERT_TRUE(snapshot.previous_boot_valid);
  TEST_ASSERT_EQUAL_UINT32(1, snapshot.previous_report_attempts);
  TEST_ASSERT_EQUAL_UINT32(0, snapshot.previous_report_completions);
  TEST_ASSERT_EQUAL_UINT32(static_cast<uint32_t>(HidReportKind::SpaceDown),
                           snapshot.previous_last_report_kind);
  TEST_ASSERT_EQUAL_UINT32(static_cast<uint32_t>(HidOperationStatus::InFlight),
                           snapshot.previous_last_report_status);
}

void test_corrupt_retained_state_is_discarded() {
  RetainedHidJournalState retained = {};
  HidResetJournal first(retained);
  first.begin(1);
  first.beginReport(HidReportKind::SpaceDown);
  first.completeReport(true);
  retained.checksum ^= 0x1U;

  HidResetJournal second(retained);
  second.begin(9);
  const HidResetSnapshot snapshot = second.snapshot();

  TEST_ASSERT_FALSE(snapshot.previous_boot_valid);
  TEST_ASSERT_EQUAL_UINT32(0, snapshot.previous_report_attempts);
  TEST_ASSERT_EQUAL_UINT32(1, snapshot.current_boot_sequence);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_completed_cycle_is_preserved_for_next_boot);
  RUN_TEST(test_interrupted_report_is_visible_after_reset);
  RUN_TEST(test_corrupt_retained_state_is_discarded);
  return UNITY_END();
}
