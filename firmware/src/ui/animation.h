#pragma once

#include <stdint.h>

// Bounded frame scheduler (R-1). Owns all periodic recomposition: the
// mandatory BLOCKED 1.2 s two-frame pulse and optional per-theme ambient
// cadence. Every frame the scheduler requests is recomposed and flushed as a
// complete frame through the existing projection path; the scheduler itself
// never draws and never allocates.
//
// Budget rule: animation flush time must stay ≤ 30 % of loop wall time. The
// caller feeds measured flush costs (the same micros() deltas ProofMetrics
// sees); when the projected animation load exceeds the budget the cadence
// halves, and if still exceeded ambient freezes to static frames. The BLOCKED
// pulse degrades last.
class AnimationScheduler final {
 public:
  static constexpr uint32_t kBlockedPeriodUs = 1200000UL;  // 1.2 s, LED-synced
  static constexpr uint32_t kBudgetPercent = 30;

  enum class Level : uint8_t { Full = 0, Half, Static };

  void setAmbientPeriod(uint32_t period_us) { ambient_period_us_ = period_us; }

  // Feed one measured per-panel compose+flush cost and the loop wall-time
  // window it occurred in. Degradation is sticky within a window and recovers
  // when the measured load falls back inside the budget.
  void observeFlushCost(uint32_t flush_us, uint32_t loop_window_us) {
    if (loop_window_us == 0) return;
    last_flush_us_ = flush_us;
    // Projected animation duty at the current cadence: one frame of cost per
    // active period. Duty in percent, computed in 64-bit to avoid overflow.
    const uint32_t period = activePeriodUs();
    if (period == 0) return;
    const uint64_t duty = (static_cast<uint64_t>(flush_us) * 100U) / period;
    if (duty > kBudgetPercent) {
      level_ = level_ == Level::Full ? Level::Half : Level::Static;
    } else if (duty * 2 <= kBudgetPercent) {
      // Comfortable margin: step back toward full cadence.
      level_ = level_ == Level::Static ? Level::Half : Level::Full;
    }
  }

  Level level() const { return level_; }

  // BLOCKED phase reference for LED synchronization: both the display pulse
  // and the LED engine derive their on/off half-period from this epoch.
  uint32_t blockedPhaseEpoch() const { return blocked_epoch_us_; }
  uint32_t blockedPhaseEpochUs() const { return blocked_epoch_us_; }
  bool blockedPulseHigh(uint32_t now_us) const {
    return ((now_us - blocked_epoch_us_) / (kBlockedPeriodUs / 2)) % 2 == 0;
  }

  // Returns true when the BLOCKED pulse crossed a half-period boundary since
  // the last call — the caller recomposes+flushes BLOCKED panels then.
  bool blockedFrameDue(uint32_t now_us) {
    if (blocked_epoch_us_ == 0) blocked_epoch_us_ = now_us != 0 ? now_us : 1;
    const uint32_t half = kBlockedPeriodUs / 2;
    const uint32_t phase = (now_us - blocked_epoch_us_) / half;
    if (phase != last_blocked_phase_) {
      last_blocked_phase_ = phase;
      return true;
    }
    return false;
  }

  // Returns true when an ambient frame is due at the current (possibly
  // degraded) cadence. Static level never schedules ambient frames.
  bool ambientFrameDue(uint32_t now_us) {
    if (ambient_period_us_ == 0 || level_ == Level::Static) return false;
    const uint32_t period = activePeriodUs();
    if (next_ambient_us_ == 0) {
      next_ambient_us_ = now_us + period;
      return false;
    }
    if (static_cast<int32_t>(now_us - next_ambient_us_) >= 0) {
      next_ambient_us_ = now_us + period;
      return true;
    }
    return false;
  }

 private:
  uint32_t activePeriodUs() const {
    if (ambient_period_us_ == 0) return 0;
    return level_ == Level::Half ? ambient_period_us_ * 2 : ambient_period_us_;
  }

  uint32_t ambient_period_us_ = 0;
  uint32_t next_ambient_us_ = 0;
  uint32_t blocked_epoch_us_ = 0;
  uint32_t last_blocked_phase_ = 0;
  uint32_t last_flush_us_ = 0;
  Level level_ = Level::Full;
};
