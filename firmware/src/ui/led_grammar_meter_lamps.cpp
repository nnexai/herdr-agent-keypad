#include "led_grammar.h"

#include <string.h>

namespace {
constexpr uint16_t kBacklights = (1U << 1) | (1U << 4) | (1U << 7) | (1U << 10) | (1U << 13);
constexpr uint16_t kKeyMasks[3] = {(1U << 1), (1U << 4), (1U << 7)};
constexpr uint16_t kLamps = (1U << 0) | (1U << 2) | (1U << 3) | (1U << 6);

void add(LedSegment* out, size_t& count, size_t cap, uint16_t mask,
         uint16_t hue, uint8_t saturation, uint8_t brightness) {
  if (mask == 0 || count >= cap || brightness == 0) return;
  out[count++] = {mask, hue, saturation, brightness};
}

uint8_t brightness(TileState state, bool pulse_high) {
  switch (state) {
    case TileState::Blocked: return pulse_high ? 40 : 10;
    case TileState::Unseen: return 30;
    case TileState::Working: return 18;
    case TileState::Idle: return 8;
    default: return 0;
  }
}

uint16_t hue(TileState state) {
  switch (state) {
    case TileState::Blocked: return 350;
    case TileState::Unseen: return 195;
    case TileState::Working: return 35;
    case TileState::Idle: return 105;
    default: return 0;
  }
}

bool unhealthy(const char* status) {
  return status != nullptr && (strcmp(status, "stale") == 0 ||
                               strcmp(status, "offline") == 0 ||
                               strcmp(status, "unavailable") == 0);
}

class MeterLamps final : public LedGrammar {
 public:
  size_t frame(const RenderState& state, const LedEvents& events,
               uint32_t now_us, LedSegment* out, size_t capacity) const override {
    size_t count = 0;
    if (unhealthy(state.source_status)) {
      add(out, count, capacity, static_cast<uint16_t>(kBacklights | kLamps), 0, 100, 10);
    } else {
      for (uint8_t slot = 0; slot < RenderState::kSlotCount; ++slot) {
        const RenderState::Slot& tile = state.slots[slot];
        uint16_t color = hue(tile.state);
        uint8_t value = brightness(tile.state, state.blocked_pulse_high);
        if (tile.feedback == TileFeedback::Pending) { color = 185; value = 45; }
        else if (tile.feedback == TileFeedback::Success) { color = 120; value = 45; }
        else if (tile.feedback != TileFeedback::Disabled && tile.feedback != TileFeedback::Ready) { color = 0; value = 45; }
        add(out, count, capacity, kKeyMasks[slot], color, 100, value);
      }
    }
    if (events.menu_open && !unhealthy(state.source_status)) add(out, count, capacity, 1U << 13, 180, 100, 25);
    // Meter and remaining accents remain dark: no usage data exists in Phase 02.2.
    return count;
  }
};
}  // namespace

LedGrammar& meterLampsGrammar() {
  static MeterLamps grammar;
  return grammar;
}

LedGrammar& ledGrammarById(LedGrammarId id) {
  switch (id) {
    case LedGrammarId::RailEcho: return railEchoGrammar();
    case LedGrammarId::Exception: return exceptionChannelGrammar();
    case LedGrammarId::FieldExtension: return fieldExtensionGrammar();
    case LedGrammarId::MeterLamps: return meterLampsGrammar();
    default: return railEchoGrammar();
  }
}
