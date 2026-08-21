#pragma once

#include <Arduino.h>
#include <stdint.h>

#include <esp_heap_caps.h>

// Fixed-width measurements at the protocol/link boundary. Protocol queue
// counters are measured in pending frames; transport bytes are intentionally
// not mixed into queue_high_water. The Phase 03.1 fields are monotonic
// maxima/counters only: no per-frame history crosses the USB boundary.
struct ProofMetrics {
  uint32_t sent = 0;
  uint32_t received = 0;
  uint32_t acknowledged = 0;
  uint32_t rejected = 0;
  uint32_t duplicate = 0;
  uint32_t out_of_order = 0;
  uint32_t malformed = 0;
  uint32_t digest_mismatch = 0;
  uint32_t watchdog_reset = 0;
  uint32_t minimum_free_heap = UINT32_MAX;
  uint32_t largest_free_block = UINT32_MAX;
  uint32_t parser_high_water = 0;
  uint32_t queue_high_water = 0;  // pending protocol frames, never transport bytes
  uint32_t max_display_flush_us = 0;
  uint32_t max_key_poll_gap_us = 0;

  // Phase 03.1 bounded presentation and input evidence.
  uint32_t loop_wall_max_us = 0;
  uint32_t compose_flush_max_us = 0;
  uint32_t frame_count = 0;
  uint32_t full_frames = 0;
  uint32_t half_frames = 0;
  uint32_t static_frames = 0;
  uint32_t level_changes = 0;
  uint32_t skipped_frames = 0;
  uint32_t degraded_frames = 0;
  uint32_t reveal_max_us = 0;
  uint32_t first_press_response_us = 0;
  uint32_t first_encoder_response_us = 0;
  uint32_t animation_duty_max_percent = 0;
  uint32_t allocation_stable = 1;

  void recordSent() { ++sent; }
  void recordReceived() { ++received; }
  void recordAcknowledged() { ++acknowledged; }
  void recordRejected() { ++rejected; }
  void recordDuplicate() { ++duplicate; }
  void recordOutOfOrder() { ++out_of_order; }
  void recordMalformed() { ++malformed; ++rejected; }
  void recordDigestMismatch() { ++digest_mismatch; ++rejected; }

  void resetCounters() {
    sent = 0;
    received = 0;
    acknowledged = 0;
    rejected = 0;
    duplicate = 0;
    out_of_order = 0;
    malformed = 0;
    digest_mismatch = 0;
    watchdog_reset = 0;
    parser_high_water = 0;
    queue_high_water = 0;
    loop_wall_max_us = 0;
    compose_flush_max_us = 0;
    frame_count = 0;
    full_frames = 0;
    half_frames = 0;
    static_frames = 0;
    level_changes = 0;
    skipped_frames = 0;
    degraded_frames = 0;
    reveal_max_us = 0;
    first_press_response_us = 0;
    first_encoder_response_us = 0;
    animation_duty_max_percent = 0;
    allocation_stable = 1;
    allocation_samples_ = 0;
    allocation_reference_heap_ = 0;
    allocation_reference_largest_ = 0;
  }

  void observeParser(size_t bytes) {
    if (bytes > parser_high_water) parser_high_water = static_cast<uint32_t>(bytes);
  }
  void observeQueue(size_t frames) {
    constexpr size_t kProtocolQueueCapacity = 16;
    if (frames > kProtocolQueueCapacity) frames = kProtocolQueueCapacity;
    if (frames > queue_high_water) queue_high_water = static_cast<uint32_t>(frames);
  }
  void observeDisplayFlush(uint32_t elapsed_us) {
    if (elapsed_us > max_display_flush_us) max_display_flush_us = elapsed_us;
  }
  void observeKeyPollGap(uint32_t elapsed_us) {
    if (elapsed_us > max_key_poll_gap_us) max_key_poll_gap_us = elapsed_us;
  }
  void observeLoopWall(uint32_t elapsed_us) {
    if (elapsed_us > loop_wall_max_us) loop_wall_max_us = elapsed_us;
  }
  void observeAnimationFrame(uint32_t compose_flush_us,
                             uint32_t loop_window_us,
                             uint8_t level) {
    if (compose_flush_us > compose_flush_max_us) compose_flush_max_us = compose_flush_us;
    ++frame_count;
    if (level == 0) ++full_frames;
    else if (level == 1) ++half_frames;
    else ++static_frames;
    if (loop_window_us != 0) {
      const uint32_t duty = static_cast<uint32_t>(
          (static_cast<uint64_t>(compose_flush_us) * 100U) / loop_window_us);
      if (duty > animation_duty_max_percent) animation_duty_max_percent = duty;
    }
  }
  void recordAnimationLevelChange() { ++level_changes; }
  void recordSkippedFrame() { ++skipped_frames; }
  void recordDegradedFrame() { ++degraded_frames; }
  void observeReveal(uint32_t elapsed_us) {
    if (elapsed_us > reveal_max_us) reveal_max_us = elapsed_us;
  }
  void observeFirstPressResponse(uint32_t elapsed_us) {
    if (elapsed_us > first_press_response_us) first_press_response_us = elapsed_us;
  }
  void observeFirstEncoderResponse(uint32_t elapsed_us) {
    if (elapsed_us > first_encoder_response_us) first_encoder_response_us = elapsed_us;
  }
  void observeAllocation(uint32_t free_heap, uint32_t largest) {
    if (allocation_samples_ == 0) {
      allocation_reference_heap_ = free_heap;
      allocation_reference_largest_ = largest;
    } else if (free_heap != allocation_reference_heap_ ||
               largest != allocation_reference_largest_) {
      allocation_stable = 0;
    }
    ++allocation_samples_;
  }
  void sampleRuntime() {
    const uint32_t free_heap = ESP.getFreeHeap();
    const uint32_t largest = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
    if (free_heap < minimum_free_heap) minimum_free_heap = free_heap;
    if (largest < largest_free_block) largest_free_block = largest;
    observeAllocation(free_heap, largest);
  }

  void normalizeUntouchedSamples() {
    if (minimum_free_heap == UINT32_MAX) minimum_free_heap = ESP.getFreeHeap();
    if (largest_free_block == UINT32_MAX) largest_free_block = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  }

 private:
  uint32_t allocation_samples_ = 0;
  uint32_t allocation_reference_heap_ = 0;
  uint32_t allocation_reference_largest_ = 0;
};
