#pragma once

#include <stdint.h>

// Bounded frame scheduler (R-1). Owns all periodic recomposition: the
// mandatory BLOCKED 1.2 s two-frame pulse, semantic transitions, and optional
// per-theme ambient cadence. Every frame requested here is recomposed and
// flushed as a complete frame through AgentProjection; the scheduler itself
// never draws and never allocates.
class AnimationScheduler final {
 public:
  static constexpr uint32_t kBlockedPeriodUs = 1200000UL;
  static constexpr uint8_t kBlockedPhaseCount = 8;
  static constexpr uint32_t kTransitionDurationUs = 200000UL;
  static constexpr uint32_t kBudgetPercent = 30;
  static constexpr uint8_t kTransitionPhaseCount = 4;
  static constexpr uint8_t kNeutralPhase = 0;

  enum class Level : uint8_t { Full = 0, Half, Static };

  void setAmbientPeriod(uint32_t period_us) {
    ambient_period_us_ = period_us;
    next_ambient_us_ = 0;
    last_frame_completed_at_us_ = 0;
    ambient_phase_ = kNeutralPhase;
  }

  void setLevel(Level level) {
    level_ = level;
    if (level_ == Level::Static && transition_active_) {
      interruptTransition(transition_epoch_);
    }
  }
  // Deterministic seam for callers that already measured the complete
  // compose+flush window.
  void observeFlushCost(uint32_t flush_us, uint32_t loop_window_us) {
    if (loop_window_us == 0) return;
    recordObservation(flush_us, loop_window_us);
    applyPressure(flush_us);
  }

  // A frame is observed at completion. Completion-to-completion elapsed time
  // contains the current single-threaded compose+flush cost, unlike the old
  // loop-start cadence pairing. The first sample uses at least its own cost.
  void observeFlushCostAt(uint32_t flush_us, uint32_t completed_at_us) {
    uint32_t window = activePeriodUs();
    if (last_frame_completed_at_us_ != 0) {
      window = completed_at_us - last_frame_completed_at_us_;
    }
    last_frame_completed_at_us_ = completed_at_us;
    recordObservation(flush_us, window);
    applyPressure(flush_us);
  }

  Level level() const { return level_; }
  uint32_t lastFlushUs() const { return last_flush_us_; }
  uint32_t lastLoopWindowUs() const { return last_loop_window_us_; }
  uint32_t lastDutyPercent() const { return last_duty_percent_; }

  // A complete frame marks the observation window for main-loop metrics.
  void beginFrameWindow() { frame_composed_ = false; }
  void noteCompleteFrame() const { frame_composed_ = true; }
  bool consumeFrameObservation() {
    const bool composed = frame_composed_;
    frame_composed_ = false;
    return composed;
  }

  bool beginTransition(uint32_t epoch, uint32_t now_us) {
    transition_epoch_ = epoch;
    transition_started_us_ = now_us;
    transition_active_ = true;
    transition_last_phase_ = kNeutralPhase;
    return true;
  }

  // Urgent semantic changes and newer generations discard all decorative
  // progress. The event epoch is retained only as a presentation correlation.
  bool interruptTransition(uint32_t epoch) {
    transition_epoch_ = epoch;
    transition_started_us_ = 0;
    transition_active_ = false;
    transition_last_phase_ = kNeutralPhase;
    return true;
  }

  void resetTransition() { interruptTransition(0); }
  bool transitionActive() const { return transition_active_; }
  uint32_t transitionEpoch() const { return transition_epoch_; }

  uint8_t transitionProgress(uint32_t now_us) const {
    if (!transition_active_) return kNeutralPhase;
    const int32_t signed_elapsed = static_cast<int32_t>(now_us - transition_started_us_);
    if (signed_elapsed < 0) return kNeutralPhase;
    const uint32_t elapsed = static_cast<uint32_t>(signed_elapsed);
    if (elapsed >= kTransitionDurationUs) return kTransitionPhaseCount - 1;
    const uint32_t phase = (static_cast<uint64_t>(elapsed) * kTransitionPhaseCount) /
                           kTransitionDurationUs;
    return static_cast<uint8_t>(phase < kTransitionPhaseCount ? phase : kTransitionPhaseCount - 1);
  }
  bool transitionDue(uint32_t now_us) {
    if (!transition_active_) return false;
    const int32_t signed_elapsed = static_cast<int32_t>(now_us - transition_started_us_);
    if (signed_elapsed < 0) return false;
    const uint8_t phase = transitionProgress(now_us);
    const bool due = phase != transition_last_phase_ ||
                     static_cast<uint32_t>(signed_elapsed) >= kTransitionDurationUs;
    if (!due) return false;
    transition_last_phase_ = phase;
    if (static_cast<uint32_t>(signed_elapsed) >= kTransitionDurationUs) {
      transition_active_ = false;
      transition_last_phase_ = kNeutralPhase;
    }
    return true;
  }

  uint8_t presentationPhase() const {
    if (level_ == Level::Static) return kNeutralPhase;
    if (transition_active_) return transition_last_phase_;
    return ambient_phase_;
  }

  uint8_t presentationPhase(uint32_t now_us) const {
    if (level_ == Level::Static) return kNeutralPhase;
    if (transition_active_) return transitionProgress(now_us);
    return ambient_phase_;
  }

  // BLOCKED phase reference for LED synchronization. Eight complete samples
  // per 1.2 s cycle keep the warning urgent while allowing themes to move
  // continuously instead of blinking between two static frames.
  uint32_t blockedPhaseEpoch() const { return blocked_epoch_us_; }
  uint32_t blockedPhaseEpochUs() const { return blocked_epoch_us_; }
  uint8_t blockedPhase(uint32_t now_us) const {
    if (blocked_epoch_us_ == 0) return 0;
    const uint32_t step = kBlockedPeriodUs / kBlockedPhaseCount;
    return static_cast<uint8_t>(((now_us - blocked_epoch_us_) / step) %
                                kBlockedPhaseCount);
  }
  bool blockedPulseHigh(uint32_t now_us) const {
    return blockedPhase(now_us) < kBlockedPhaseCount / 2U;
  }

  // Returns true when BLOCKED crossed a presentation phase boundary.
  bool blockedFrameDue(uint32_t now_us) {
    if (blocked_epoch_us_ == 0) blocked_epoch_us_ = now_us != 0 ? now_us : 1;
    const uint32_t step = kBlockedPeriodUs / kBlockedPhaseCount;
    const uint32_t phase = (now_us - blocked_epoch_us_) / step;
    if (phase != last_blocked_phase_) {
      last_blocked_phase_ = phase;
      return true;
    }
    return false;
  }

  // Full samples at the theme cadence, Half doubles only ambient cadence,
  // Static never schedules ambient work. Semantic frames are not gated here.
  bool ambientFrameDue(uint32_t now_us) {
    if (ambient_period_us_ == 0 || level_ == Level::Static) return false;
    const uint32_t period = activePeriodUs();
    if (next_ambient_us_ == 0) {
      next_ambient_us_ = now_us + period;
      return false;
    }
    if (static_cast<int32_t>(now_us - next_ambient_us_) >= 0) {
      next_ambient_us_ = now_us + period;
      ambient_phase_ = static_cast<uint8_t>(
          (ambient_phase_ + (level_ == Level::Half ? 2U : 1U)) % 8U);
      return true;
    }
    return false;
  }

  uint32_t activePeriodUs() const { return periodForLevel(level_); }

 private:
  static uint32_t dutyPercent(uint32_t flush_us, uint32_t window_us) {
    if (window_us == 0 || flush_us >= window_us) return 100;
    return static_cast<uint32_t>(
        (static_cast<uint64_t>(flush_us) * 100U) / window_us);
  }

  uint32_t periodForLevel(Level level) const {
    if (ambient_period_us_ == 0 || level == Level::Static) return 0;
    if (level != Level::Half) return ambient_period_us_;
    return ambient_period_us_ > UINT32_MAX / 2U
               ? UINT32_MAX
               : ambient_period_us_ * 2U;
  }

  void recordObservation(uint32_t flush_us, uint32_t window_us) {
    if (window_us < flush_us) window_us = flush_us;
    if (window_us == 0) window_us = 1;
    last_flush_us_ = flush_us;
    last_loop_window_us_ = window_us;
    last_duty_percent_ = dutyPercent(flush_us, window_us);
  }

  void applyPressure(uint32_t flush_us) {
    if (level_ == Level::Static) {
      const uint32_t recovery_window = periodForLevel(Level::Half);
      if (recovery_window != 0 &&
          dutyPercent(flush_us, recovery_window) <= kBudgetPercent / 2U) {
        level_ = Level::Half;
        next_ambient_us_ = 0;
      }
      return;
    }
    if (last_duty_percent_ > kBudgetPercent) {
      if (level_ == Level::Full) {
        level_ = Level::Half;
      } else {
        level_ = Level::Static;
        interruptTransition(transition_epoch_);
      }
    } else if (level_ == Level::Half &&
               last_duty_percent_ <= kBudgetPercent / 2U) {
      level_ = Level::Full;
    }
  }

  uint32_t ambient_period_us_ = 0;
  uint32_t next_ambient_us_ = 0;
  uint8_t ambient_phase_ = kNeutralPhase;
  uint32_t blocked_epoch_us_ = 0;
  uint32_t last_blocked_phase_ = 0;
  uint32_t last_flush_us_ = 0;
  uint32_t last_loop_window_us_ = 0;
  uint32_t last_duty_percent_ = 0;
  uint32_t last_frame_completed_at_us_ = 0;
  uint32_t transition_started_us_ = 0;
  uint32_t transition_epoch_ = 0;
  uint8_t transition_last_phase_ = kNeutralPhase;
  bool transition_active_ = false;
  mutable bool frame_composed_ = false;
  Level level_ = Level::Full;
};
