#pragma once

#include <stdint.h>

enum class HidReportKind : uint32_t {
  None = 0,
  SpaceDown = 1,
  Empty = 2,
};

enum class HidOperationStatus : uint32_t {
  None = 0,
  InFlight = 1,
  Succeeded = 2,
  Failed = 3,
};

// POD layout stored in RTC no-init memory on the ESP32-S3. The checksum makes
// power-on garbage fail closed instead of being reported as a previous boot.
struct RetainedHidJournalState {
  uint32_t magic;
  uint32_t version;
  uint32_t boot_sequence;
  uint32_t report_attempts;
  uint32_t report_completions;
  uint32_t space_down_completions;
  uint32_t empty_report_completions;
  uint32_t last_report_kind;
  uint32_t last_report_status;
  uint32_t lifecycle_clears;
  uint32_t last_lifecycle_event;
  uint32_t last_lifecycle_status;
  uint32_t checksum;
};

struct HidResetSnapshot {
  uint32_t reset_reason = 0;
  uint32_t current_boot_sequence = 1;
  bool previous_boot_valid = false;
  uint32_t previous_boot_sequence = 0;
  uint32_t previous_report_attempts = 0;
  uint32_t previous_report_completions = 0;
  uint32_t previous_space_down_completions = 0;
  uint32_t previous_empty_report_completions = 0;
  uint32_t previous_last_report_kind = 0;
  uint32_t previous_last_report_status = 0;
  uint32_t previous_lifecycle_clears = 0;
  uint32_t previous_last_lifecycle_event = 0;
  uint32_t previous_last_lifecycle_status = 0;
};

class HidResetJournal final {
 public:
  explicit HidResetJournal(RetainedHidJournalState& retained)
      : retained_(retained) {}

  void begin(uint32_t reset_reason);
  void beginReport(HidReportKind kind);
  void completeReport(bool succeeded);
  void beginLifecycle(uint32_t event);
  void completeLifecycle(bool succeeded);

  const HidResetSnapshot& snapshot() const { return snapshot_; }

 private:
  static constexpr uint32_t kMagic = 0x4849444aU;  // HIDJ
  static constexpr uint32_t kVersion = 1;

  bool valid() const;
  void commit();

  RetainedHidJournalState& retained_;
  HidResetSnapshot snapshot_;
};

// Production singleton. beginHidResetJournal() must run before USB startup.
void beginHidResetJournal(uint32_t reset_reason);
HidResetJournal& hidResetJournal();
