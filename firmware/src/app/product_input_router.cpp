#include "product_input_router.h"

namespace {
void append(ProductInputActions& actions, ProductInputActionKind kind,
            int32_t value) {
  if (actions.count >= ProductInputActions::kCapacity) return;
  actions.items[actions.count++] = {kind, value};
}
}  // namespace

ProductInputActions ProductInputRouter::route(const ProductInputFrame& frame) {
  ProductInputActions actions;
  for (uint8_t slot = 0; slot < ProductInputFrame::kAgentSlotCount; ++slot) {
    if (frame.agent_pressed[slot]) {
      append(actions, ProductInputActionKind::AgentSlot, slot);
    }
  }
  if (frame.encoder_clicked) {
    append(actions, ProductInputActionKind::EncoderClick, 0);
  }
  if (frame.encoder_delta != 0) {
    const int32_t direction = frame.encoder_delta > 0 ? 1 : -1;
    const uint32_t magnitude = frame.encoder_delta > 0
                                   ? static_cast<uint32_t>(frame.encoder_delta)
                                   : static_cast<uint32_t>(-
                                         static_cast<int64_t>(frame.encoder_delta));
    const uint32_t bounded =
        magnitude > ProductInputActions::kMaxEncoderDetents
            ? ProductInputActions::kMaxEncoderDetents
            : magnitude;
    for (uint32_t detent = 0; detent < bounded; ++detent) {
      append(actions, ProductInputActionKind::EncoderRotate, direction);
    }
  }
  return actions;
}
