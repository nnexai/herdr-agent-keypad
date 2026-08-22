#include "hid_reset_journal.h"

#ifdef ARDUINO
#include <Arduino.h>
#include <esp_attr.h>

namespace {
portMUX_TYPE journal_mux = portMUX_INITIALIZER_UNLOCKED;
#define JOURNAL_ENTER() portENTER_CRITICAL(&journal_mux)
#define JOURNAL_EXIT() portEXIT_CRITICAL(&journal_mux)
RTC_NOINIT_ATTR RetainedHidJournalState retained_hid_journal;
}  // namespace
#else
namespace {
#define JOURNAL_ENTER()
#define JOURNAL_EXIT()
RetainedHidJournalState retained_hid_journal = {};
}  // namespace
#endif

namespace {

uint32_t checksum(const RetainedHidJournalState& state) {
  constexpr uint32_t kOffset = 2166136261U;
  constexpr uint32_t kPrime = 16777619U;
  uint32_t value = kOffset;
  const uint32_t words[] = {
      state.magic,
      state.version,
      state.boot_sequence,
      state.report_attempts,
      state.report_completions,
      state.space_down_completions,
      state.empty_report_completions,
      state.last_report_kind,
      state.last_report_status,
      state.lifecycle_clears,
      state.last_lifecycle_event,
      state.last_lifecycle_status,
  };
  for (const uint32_t word : words) {
    for (uint8_t shift = 0; shift < 32; shift = static_cast<uint8_t>(shift + 8)) {
      value ^= static_cast<uint8_t>(word >> shift);
      value *= kPrime;
    }
  }
  return value;
}

uint32_t nextSequence(uint32_t previous) {
  ++previous;
  return previous == 0 ? 1 : previous;
}

HidResetJournal production_journal(retained_hid_journal);

}  // namespace

bool HidResetJournal::valid() const {
  return retained_.magic == kMagic && retained_.version == kVersion &&
         retained_.checksum == checksum(retained_);
}

void HidResetJournal::commit() { retained_.checksum = checksum(retained_); }

void HidResetJournal::begin(uint32_t reset_reason) {
  JOURNAL_ENTER();
  const bool previous_valid = valid();
  snapshot_ = HidResetSnapshot();
  snapshot_.reset_reason = reset_reason;
  snapshot_.previous_boot_valid = previous_valid;
  if (previous_valid) {
    snapshot_.previous_boot_sequence = retained_.boot_sequence;
    snapshot_.previous_report_attempts = retained_.report_attempts;
    snapshot_.previous_report_completions = retained_.report_completions;
    snapshot_.previous_space_down_completions =
        retained_.space_down_completions;
    snapshot_.previous_empty_report_completions =
        retained_.empty_report_completions;
    snapshot_.previous_last_report_kind = retained_.last_report_kind;
    snapshot_.previous_last_report_status = retained_.last_report_status;
    snapshot_.previous_lifecycle_clears = retained_.lifecycle_clears;
    snapshot_.previous_last_lifecycle_event = retained_.last_lifecycle_event;
    snapshot_.previous_last_lifecycle_status = retained_.last_lifecycle_status;
    snapshot_.current_boot_sequence = nextSequence(retained_.boot_sequence);
  }

  retained_ = {};
  retained_.magic = kMagic;
  retained_.version = kVersion;
  retained_.boot_sequence = snapshot_.current_boot_sequence;
  commit();
  JOURNAL_EXIT();
}

void HidResetJournal::beginReport(HidReportKind kind) {
  JOURNAL_ENTER();
  ++retained_.report_attempts;
  retained_.last_report_kind = static_cast<uint32_t>(kind);
  retained_.last_report_status =
      static_cast<uint32_t>(HidOperationStatus::InFlight);
  commit();
  JOURNAL_EXIT();
}

void HidResetJournal::completeReport(bool succeeded) {
  JOURNAL_ENTER();
  ++retained_.report_completions;
  if (succeeded) {
    if (retained_.last_report_kind ==
        static_cast<uint32_t>(HidReportKind::SpaceDown)) {
      ++retained_.space_down_completions;
    } else if (retained_.last_report_kind ==
               static_cast<uint32_t>(HidReportKind::Empty)) {
      ++retained_.empty_report_completions;
    }
  }
  retained_.last_report_status = static_cast<uint32_t>(
      succeeded ? HidOperationStatus::Succeeded : HidOperationStatus::Failed);
  commit();
  JOURNAL_EXIT();
}

void HidResetJournal::beginLifecycle(uint32_t event) {
  JOURNAL_ENTER();
  ++retained_.lifecycle_clears;
  retained_.last_lifecycle_event = event;
  retained_.last_lifecycle_status =
      static_cast<uint32_t>(HidOperationStatus::InFlight);
  commit();
  JOURNAL_EXIT();
}

void HidResetJournal::completeLifecycle(bool succeeded) {
  JOURNAL_ENTER();
  retained_.last_lifecycle_status = static_cast<uint32_t>(
      succeeded ? HidOperationStatus::Succeeded : HidOperationStatus::Failed);
  commit();
  JOURNAL_EXIT();
}

void beginHidResetJournal(uint32_t reset_reason) {
  production_journal.begin(reset_reason);
}

HidResetJournal& hidResetJournal() { return production_journal; }
