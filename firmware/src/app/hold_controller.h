#pragma once

#include <stdint.h>

#include "product_input_router.h"
#include "../metrics/proof_metrics.h"
#include "../transport/fixed_space_hid.h"

// Focus-authorized, fixed-Space hold state. This controller is deliberately
// allocation-free and owns one local candidate plus one physical HID owner.
// It never accepts a keycode, text value, macro, or protocol command.
class HoldController final {
 public:
  static constexpr uint8_t kSlotCount = ProductInputFrame::kAgentSlotCount;
  static constexpr uint32_t kMeasuredThresholdUs = 550000U;
  static constexpr uint8_t kActionIdBytes = 32;

  enum class LifecycleEvent : uint8_t {
    Disconnect = 0,
    SessionReplacement,
    ControlledReset,
    UsbStopped,
    UsbSuspend,
    UsbResume,
    UsbMount,
    HidFailure,
  };

  struct PresentationState {
    uint8_t candidate_slot = 0xFF;
    bool threshold_qualified = false;
    uint8_t owner_slot = 0xFF;
    uint32_t lifecycle_cleared_epoch = 0;
    bool lifecycle_blocked = false;
    bool empty_report_complete = true;
  };

  explicit HoldController(FixedSpaceHid& hid,
                          uint32_t threshold_us = kMeasuredThresholdUs,
                          ProofMetrics* metrics = nullptr);

  // Called only after the existing projection successfully captures and sends
  // the exact focus intent. A press is not a hold authorization by itself.
  bool registerPress(uint8_t slot, const char* action_id,
                     uint32_t edge_latched_at_us);

  // The result has already passed AgentProjection's exact correlation check.
  // A failed exact result monotonically cancels the matching candidate.
  void observeFocusResult(uint8_t slot, const char* action_id, bool admitted);

  // Consume one complete hardware frame. The caller supplies the HID/link
  // readiness observed for this cooperative-loop turn.
  void observeFrame(const ProductInputFrame& frame, uint32_t now_us,
                    bool hid_ready);

  // Clear authority before every lifecycle release attempt. Empty-report
  // completion and a subsequent all-keys-up frame are both required before a
  // new candidate can be registered.
  bool onLifecycle(LifecycleEvent event);

  // Compatibility entry point for the existing disconnect/session-loss path.
  void cancelAll() { (void)onLifecycle(LifecycleEvent::Disconnect); }

  // Passive presentation-only state. The returned value cannot authorize,
  // clear, or extend a candidate or owner.
  PresentationState presentation() const;

  bool hasCandidate() const { return candidate_.valid; }
  bool active() const { return owner_.active; }
  uint8_t candidateSlot() const { return candidate_.valid ? candidate_.slot : 0xFF; }
  uint8_t ownerSlot() const { return owner_.active ? owner_.slot : 0xFF; }

 private:
  struct Candidate {
    bool valid = false;
    uint8_t slot = 0;
    char action_id[kActionIdBytes] = {};
    uint32_t edge_latched_at_us = 0;
    uint32_t generation = 0;
    bool down = false;
    bool threshold_qualified = false;
    bool admitted = false;
  };

  struct Owner {
    bool active = false;
    uint8_t slot = 0;
    uint32_t generation = 0;
  };

  FixedSpaceHid& hid_;
  uint32_t threshold_us_;
  ProofMetrics* metrics_;
  uint32_t generation_ = 0;
  uint32_t lifecycle_cleared_epoch_ = 0;
  bool chord_lockout_ = false;
  bool lifecycle_blocked_ = false;
  bool empty_report_complete_ = true;
  bool all_keys_up_ = true;
  Candidate candidate_;
  Owner owner_;

  uint32_t nextGeneration();
  void invalidateCandidate();
  void releaseOwner(uint8_t released_mask, uint32_t now_us);
  bool actionMatches(const char* action_id) const;
  bool attemptEmptyReport();
  void finishLifecycleIfReady(uint8_t down_mask);
  void tryActivate(uint32_t now_us, bool hid_ready);
};
