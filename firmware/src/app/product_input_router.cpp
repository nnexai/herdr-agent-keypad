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
    append(actions, ProductInputActionKind::EncoderRotate,
           frame.encoder_delta);
  }
  return actions;
}
