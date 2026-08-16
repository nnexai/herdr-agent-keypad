#pragma once

#include <Arduino.h>
#include <stdint.h>

#include <esp_heap_caps.h>

// Fixed-width measurements at the protocol/link boundary.  This type contains
// no transport or protocol policy; callers decide when a byte/event occurred.
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
  uint32_t queue_high_water = 0;
  uint32_t max_display_flush_us = 0;
  uint32_t max_key_poll_gap_us = 0;

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
  }

  void observeParser(size_t bytes) {
    if (bytes > parser_high_water) parser_high_water = static_cast<uint32_t>(bytes);
  }
  void observeQueue(size_t bytes) {
    if (bytes > queue_high_water) queue_high_water = static_cast<uint32_t>(bytes);
  }
  void observeDisplayFlush(uint32_t elapsed_us) {
    if (elapsed_us > max_display_flush_us) max_display_flush_us = elapsed_us;
  }
  void observeKeyPollGap(uint32_t elapsed_us) {
    if (elapsed_us > max_key_poll_gap_us) max_key_poll_gap_us = elapsed_us;
  }
  void sampleRuntime() {
    const uint32_t free_heap = ESP.getFreeHeap();
    const uint32_t largest = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
    if (free_heap < minimum_free_heap) minimum_free_heap = free_heap;
    if (largest < largest_free_block) largest_free_block = largest;
  }

  void normalizeUntouchedSamples() {
    if (minimum_free_heap == UINT32_MAX) minimum_free_heap = ESP.getFreeHeap();
    if (largest_free_block == UINT32_MAX) largest_free_block = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  }
};
