#pragma once

#include <stdint.h>

struct ProductInputFrame {
  static constexpr uint8_t kAgentSlotCount = 3;

  bool agent_pressed[kAgentSlotCount]{};
  bool encoder_clicked = false;
  int32_t encoder_delta = 0;
  // Timestamp from the board adapter's single poll/latch seam.
  uint32_t latched_at_us = 0;
};

enum class ProductInputActionKind : uint8_t {
  AgentSlot = 0,
  EncoderClick,
  EncoderRotate,
};

struct ProductInputAction {
  ProductInputActionKind kind = ProductInputActionKind::AgentSlot;
  int32_t value = 0;
};

struct ProductInputActions {
  static constexpr uint8_t kMaxEncoderDetents = 8;
  static constexpr uint8_t kCapacity =
      ProductInputFrame::kAgentSlotCount + 1 + kMaxEncoderDetents;

  ProductInputAction items[kCapacity]{};
  uint8_t count = 0;

  const ProductInputAction& operator[](uint8_t index) const {
    return items[index];
  }
};

// Pure ordering seam for one captured hardware frame. It owns no hardware,
// controller state, focus state, timer, queue, or authorization path.
class ProductInputRouter final {
 public:
  static ProductInputActions route(const ProductInputFrame& frame);
};
