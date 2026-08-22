#pragma once

#include <stdint.h>

#include "product_input_router.h"
#include "../transport/fixed_space_hid.h"

// Focus-authorized, fixed-Space hold state.  This controller is deliberately
// allocation-free and owns one local candidate plus one physical HID owner.
// It never accepts a keycode, text value, macro, or protocol command.
class HoldController final {
 public:
  static constexpr uint8_t kSlotCount = ProductInputFrame::kAgentSlotCount;
  static constexpr uint32_t kMeasuredThresholdUs = 550000U;
  static constexpr uint8_t kActionIdBytes = 32;

  explicit HoldController(FixedSpaceHid& hid,
                          uint32_t threshold_us = kMeasuredThresholdUs);

  // Called only after the existing projection successfully captures and sends
  // the exact focus intent.  A press is not a hold authorization by itself.
  bool registerPress(uint8_t slot, const char* action_id,
                     uint32_t edge_latched_at_us);

  // The result has already passed AgentProjection's exact correlation check.
  // A failed exact result monotonically cancels the matching candidate.
  void observeFocusResult(uint8_t slot, const char* action_id, bool admitted);

  // Consume one complete hardware frame.  The caller supplies the HID/link
  // readiness observed for this cooperative-loop turn.
  void observeFrame(const ProductInputFrame& frame, uint32_t now_us,
                    bool hid_ready);

  // Clear local authority for disconnect, session replacement, reset, and
  // suspend.  An active owner receives one best-effort release-all report.
  void cancelAll();

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
  uint32_t generation_ = 0;
  bool chord_lockout_ = false;
  Candidate candidate_;
  Owner owner_;

  uint32_t nextGeneration();
  void invalidateCandidate();
  void releaseOwner();
  bool actionMatches(const char* action_id) const;
  void tryActivate(uint32_t now_us, bool hid_ready);
};
