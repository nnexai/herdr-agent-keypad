#include "hold_controller.h"

#include <string.h>

#ifdef ARDUINO
#include "metrics/hid_reset_journal.h"
#endif

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

HoldController::HoldController(FixedSpaceHid& hid, uint32_t threshold_us,
                               ProofMetrics* metrics)
    : hid_(hid),
      threshold_us_(threshold_us == 0 ? kMeasuredThresholdUs : threshold_us),
      metrics_(metrics) {}
void HoldController::recordPollGap(uint32_t now_us) {
  if (poll_sampled_ && metrics_ != nullptr) {
    metrics_->observeHoldPollGap(static_cast<uint32_t>(now_us - last_poll_at_us_));
  }
  last_poll_at_us_ = now_us;
  poll_sampled_ = true;
}

void HoldController::markEligible(uint32_t now_us) {
  if (!candidate_.valid || candidate_.eligible ||
      !candidate_.threshold_qualified || !candidate_.admitted) {
    return;
  }
  candidate_.eligible = true;
  candidate_.eligible_at_us = now_us;
  if (metrics_ != nullptr) {
    metrics_->recordEligibility();
    if (candidate_.admitted_at_us != 0 && now_us != 0) {
      metrics_->observeFocusResultToEligibility(
          static_cast<uint32_t>(now_us - candidate_.admitted_at_us));
    }
  }
}

void HoldController::observeThreshold(uint32_t now_us) {
  if (!candidate_.valid || !candidate_.down ||
      candidate_.threshold_qualified ||
      !elapsedAtLeast(now_us, candidate_.edge_latched_at_us, threshold_us_)) {
    return;
  }
  candidate_.threshold_qualified = true;
  candidate_.threshold_crossed_at_us = now_us;
  if (metrics_ != nullptr) metrics_->recordThresholdCrossing();
  markEligible(now_us);
}


uint32_t HoldController::nextGeneration() {
  ++generation_;
  if (generation_ == 0) generation_ = 1;
  return generation_;
}

void HoldController::invalidateCandidate() {
  if (!candidate_.valid) return;
  if (metrics_ != nullptr) metrics_->recordCandidateTransition();
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
      owner_.active || chord_lockout_ || lifecycle_blocked_) {
    return false;
  }
  const size_t length = strlen(action_id);
  if (length >= sizeof(candidate_.action_id)) return false;

  // Replacing a candidate is a local HID decision only. Earlier presses have
  // already emitted their independent exact focus intents and remain owned by
  // AgentProjection for result/failure presentation.
  if (candidate_.valid) invalidateCandidate();
  if (metrics_ != nullptr) metrics_->recordCandidateTransition();
  candidate_ = Candidate();
  candidate_.valid = true;
  candidate_.slot = slot;
  memcpy(candidate_.action_id, action_id, length + 1);
  candidate_.edge_latched_at_us = edge_latched_at_us;
  candidate_.generation = nextGeneration();
  all_keys_up_ = false;
  return true;
}

void HoldController::observeFocusResult(uint8_t slot, const char* action_id,
                                        bool admitted, uint32_t result_at_us) {
  if (slot >= kSlotCount || !actionMatches(action_id)) return;
  if (!admitted) {
    invalidateCandidate();
    return;
  }
  candidate_.admitted = true;
  candidate_.admitted_at_us = result_at_us;
  markEligible(result_at_us);
}

bool HoldController::attemptEmptyReport() {
  // Callers clear candidate and owner before entering this method. The result
  // is the only authority for whether lifecycle rearming may continue.
  const bool completed = hid_.releaseAll();
  empty_report_complete_ = completed;
  if (metrics_ != nullptr) metrics_->recordReleaseAll(completed);
  return completed;
}

bool HoldController::onLifecycle(LifecycleEvent event) {
  // Clear all local authority before attempting any report. This ordering is
  // required even when the endpoint has disappeared and SendReport fails.
#ifdef ARDUINO
  hidResetJournal().beginLifecycle(static_cast<uint32_t>(event));
#endif
  if (metrics_ != nullptr) metrics_->recordLifecycleClear();
  invalidateCandidate();
  if (owner_.active && metrics_ != nullptr) metrics_->recordOwnerTransition();
  owner_ = Owner();
  chord_lockout_ = false;
  lifecycle_blocked_ = true;
  empty_report_complete_ = false;
  all_keys_up_ = false;
  ++lifecycle_cleared_epoch_;
  if (lifecycle_cleared_epoch_ == 0) lifecycle_cleared_epoch_ = 1;
  const bool completed = attemptEmptyReport();
#ifdef ARDUINO
  hidResetJournal().completeLifecycle(completed);
#endif
  return completed;
}

void HoldController::releaseOwner(uint8_t /*released_mask*/, uint32_t /*now_us*/) {
  // Clear ownership before trying to send the up report. A failed transfer
  // must never leave a logical owner that can be inherited by another key.
  if (metrics_ != nullptr) {
    metrics_->recordOwnerTransition();
    metrics_->observePhysicalReleaseToUp(0);
  }
  owner_ = Owner();
  invalidateCandidate();
  lifecycle_blocked_ = true;
  all_keys_up_ = false;
  empty_report_complete_ = false;
  const bool completed = attemptEmptyReport();
  if (metrics_ != nullptr) metrics_->recordSpaceUp(completed);
}

void HoldController::finishLifecycleIfReady(uint8_t down_mask) {
  all_keys_up_ = down_mask == 0;
  if (lifecycle_blocked_ && empty_report_complete_ && all_keys_up_) {
    lifecycle_blocked_ = false;
  }
}

void HoldController::tryActivate(uint32_t now_us, bool hid_ready) {
  if (!hid_ready || owner_.active || !candidate_.valid || !candidate_.down ||
      chord_lockout_ || lifecycle_blocked_) {
    return;
  }
  observeThreshold(now_us);
  if (!candidate_.eligible) return;

  if (metrics_ != nullptr) {
    const uint32_t elapsed = candidate_.eligible_at_us == 0
                                 ? 0
                                 : static_cast<uint32_t>(
                                       now_us - candidate_.eligible_at_us);
    metrics_->observeEligibilityToDown(elapsed);
  }

  // The candidate is consumed only after a successful fixed Space report.
  const bool completed = hid_.spaceDown();
  if (metrics_ != nullptr) metrics_->recordSpaceDown(completed);
  if (!completed) {
    invalidateCandidate();
    (void)onLifecycle(LifecycleEvent::HidFailure);
    return;
  }
  if (metrics_ != nullptr) {
    metrics_->recordOwnerTransition();
    metrics_->recordCandidateTransition();
  }
  owner_.active = true;
  owner_.slot = candidate_.slot;
  owner_.generation = candidate_.generation;
  candidate_ = Candidate();
}

void HoldController::observeFrame(const ProductInputFrame& frame,
                                  uint32_t now_us, bool hid_ready) {
  recordPollGap(now_us);
  uint8_t pressed_mask = 0;
  uint8_t down_mask = 0;
  uint8_t released_mask = 0;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    if (frame.agent_pressed[slot]) pressed_mask |= static_cast<uint8_t>(1U << slot);
    if (frame.agent_down[slot]) down_mask |= static_cast<uint8_t>(1U << slot);
    if (frame.agent_released[slot]) released_mask |= static_cast<uint8_t>(1U << slot);
  }

  // A same-poll chord is determined from the captured frame, before any slot
  // can become an owner. It remains locked until the physical set is empty.
  if (bitCount(pressed_mask) >= 2) {
    if (!chord_lockout_ && metrics_ != nullptr) metrics_->recordChordLockout();
    chord_lockout_ = true;
    invalidateCandidate();
  }

  if (owner_.active &&
      ((released_mask & static_cast<uint8_t>(1U << owner_.slot)) != 0 ||
       (down_mask & static_cast<uint8_t>(1U << owner_.slot)) == 0)) {
    releaseOwner(released_mask, now_us);
  }
  if (candidate_.valid &&
      ((released_mask & static_cast<uint8_t>(1U << candidate_.slot)) != 0 ||
       (down_mask & static_cast<uint8_t>(1U << candidate_.slot)) == 0)) {
    invalidateCandidate();
  }

  if (!hid_ready) {
    if (metrics_ != nullptr) metrics_->recordHidNotReady();
    // A not-ready endpoint cancels an unowned candidate but does not invent a
    // lifecycle block. An active owner, however, is fail-closed immediately.
    if (owner_.active) {
      (void)onLifecycle(LifecycleEvent::HidFailure);
    } else {
      invalidateCandidate();
    }
    finishLifecycleIfReady(down_mask);
    return;
  }

  if (lifecycle_blocked_ && !empty_report_complete_) {
    // Retrying an empty report is safe only after authority has already been
    // cleared. The all-up frame below still gates rearming.
    (void)attemptEmptyReport();
  }
  finishLifecycleIfReady(down_mask);
  if (chord_lockout_ && down_mask == 0) chord_lockout_ = false;
  if (lifecycle_blocked_) return;

  if (candidate_.valid) {
    candidate_.down =
        (down_mask & static_cast<uint8_t>(1U << candidate_.slot)) != 0;
    observeThreshold(now_us);
  }
  tryActivate(now_us, hid_ready);
}

HoldController::PresentationState HoldController::presentation() const {
  PresentationState state;
  state.candidate_slot = candidate_.valid ? candidate_.slot : 0xFF;
  state.threshold_qualified =
      (candidate_.valid && candidate_.threshold_qualified) || owner_.active;
  state.owner_slot = owner_.active ? owner_.slot : 0xFF;
  state.lifecycle_cleared_epoch = lifecycle_cleared_epoch_;
  state.lifecycle_blocked = lifecycle_blocked_;
  state.empty_report_complete = empty_report_complete_;
  return state;
}
