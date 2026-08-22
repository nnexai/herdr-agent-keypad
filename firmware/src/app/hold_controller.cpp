#include "hold_controller.h"

#include <string.h>

namespace {
uint8_t bitCount(uint8_t value) {
  uint8_t count = 0;
  while (value != 0) {
    count = static_cast<uint8_t>(count + (value & 1U));
    value = static_cast<uint8_t>(value >> 1U);
  }
  return count;
}

bool elapsedAtLeast(uint32_t now_us, uint32_t edge_us, uint32_t duration_us) {
  return static_cast<uint32_t>(now_us - edge_us) >= duration_us;
}
}  // namespace

HoldController::HoldController(FixedSpaceHid& hid, uint32_t threshold_us)
    : hid_(hid),
      threshold_us_(threshold_us == 0 ? kMeasuredThresholdUs : threshold_us) {}

uint32_t HoldController::nextGeneration() {
  ++generation_;
  if (generation_ == 0) generation_ = 1;
  return generation_;
}

void HoldController::invalidateCandidate() {
  if (!candidate_.valid) return;
  nextGeneration();
  candidate_ = Candidate();
}

bool HoldController::actionMatches(const char* action_id) const {
  return candidate_.valid && action_id != nullptr &&
         strcmp(candidate_.action_id, action_id) == 0;
}

bool HoldController::registerPress(uint8_t slot, const char* action_id,
                                   uint32_t edge_latched_at_us) {
  if (slot >= kSlotCount || action_id == nullptr || action_id[0] == '\0' ||
      owner_.active || chord_lockout_) {
    return false;
  }
  const size_t length = strlen(action_id);
  if (length >= sizeof(candidate_.action_id)) return false;

  // Replacing a candidate is a local HID decision only.  Earlier presses have
  // already emitted their independent exact focus intents and remain owned by
  // AgentProjection for result/failure presentation.
  if (candidate_.valid) invalidateCandidate();
  candidate_ = Candidate();
  candidate_.valid = true;
  candidate_.slot = slot;
  memcpy(candidate_.action_id, action_id, length + 1);
  candidate_.edge_latched_at_us = edge_latched_at_us;
  candidate_.generation = nextGeneration();
  return true;
}

void HoldController::observeFocusResult(uint8_t slot, const char* action_id,
                                        bool admitted) {
  if (slot >= kSlotCount || !actionMatches(action_id)) return;
  if (!admitted) {
    invalidateCandidate();
    return;
  }
  candidate_.admitted = true;
}

void HoldController::releaseOwner() {
  if (!owner_.active) return;
  // Clear local authority even if the endpoint is currently unavailable.  A
  // later frame/session cannot transfer this physical owner to another key.
  hid_.releaseAll();
  owner_ = Owner();
}

void HoldController::cancelAll() {
  invalidateCandidate();
  releaseOwner();
  chord_lockout_ = false;
  nextGeneration();
}

void HoldController::tryActivate(uint32_t now_us, bool hid_ready) {
  if (!hid_ready || owner_.active || !candidate_.valid || !candidate_.down ||
      chord_lockout_) {
    return;
  }
  if (!candidate_.threshold_qualified) {
    candidate_.threshold_qualified = elapsedAtLeast(
        now_us, candidate_.edge_latched_at_us, threshold_us_);
  }
  if (!candidate_.threshold_qualified || !candidate_.admitted) return;

  // The candidate is consumed only after a successful fixed Space report.
  if (!hid_.spaceDown()) {
    invalidateCandidate();
    return;
  }
  owner_.active = true;
  owner_.slot = candidate_.slot;
  owner_.generation = candidate_.generation;
  candidate_ = Candidate();
}

void HoldController::observeFrame(const ProductInputFrame& frame,
                                  uint32_t now_us, bool hid_ready) {
  uint8_t pressed_mask = 0;
  uint8_t down_mask = 0;
  uint8_t released_mask = 0;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    if (frame.agent_pressed[slot]) pressed_mask |= static_cast<uint8_t>(1U << slot);
    if (frame.agent_down[slot]) down_mask |= static_cast<uint8_t>(1U << slot);
    if (frame.agent_released[slot]) released_mask |= static_cast<uint8_t>(1U << slot);
  }

  // A same-poll chord is determined from the captured frame, before any slot
  // can become an owner.  It remains locked until the physical set is empty.
  if (bitCount(pressed_mask) >= 2) {
    chord_lockout_ = true;
    invalidateCandidate();
  }

  if (owner_.active &&
      ((released_mask & static_cast<uint8_t>(1U << owner_.slot)) != 0 ||
       (down_mask & static_cast<uint8_t>(1U << owner_.slot)) == 0)) {
    releaseOwner();
  }
  if (candidate_.valid &&
      ((released_mask & static_cast<uint8_t>(1U << candidate_.slot)) != 0 ||
       (down_mask & static_cast<uint8_t>(1U << candidate_.slot)) == 0)) {
    invalidateCandidate();
  }

  if (down_mask == 0) chord_lockout_ = false;
  if (!hid_ready) {
    cancelAll();
    return;
  }

  if (candidate_.valid) candidate_.down =
      (down_mask & static_cast<uint8_t>(1U << candidate_.slot)) != 0;
  tryActivate(now_us, hid_ready);
}
