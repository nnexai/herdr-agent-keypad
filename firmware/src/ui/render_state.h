#pragma once

#include <stdint.h>

// Shared presentation state consumed by every ThemeRenderer and LED grammar.
// Built by AgentProjection from its committed generation — never a second
// snapshot cache and never host-authoritative data beyond bounded display
// strings and opaque state.

enum class ThemeId : uint8_t { SignalEdge = 0, Ledger, Beacon, Instrument };
constexpr uint8_t kThemeCount = 4;

enum class LedGrammarId : uint8_t { RailEcho = 0, Exception, FieldExtension, MeterLamps };
constexpr uint8_t kLedGrammarCount = 4;

enum class TileState : uint8_t {
  Empty = 0, Blocked, Unseen, Working, Idle, Settled, Unknown,
  Stale, Offline, Unavailable, Sync, Pending, Focused, Rejected,
  Vanished, Uncertain, Failed,
};

enum class TileFeedback : uint8_t {
  Disabled = 0, Ready, Pending, Success, Rejected, Stale, Vanished,
  Offline, Uncertain, Failed,
};

struct RenderState {
  static constexpr uint8_t kSlotCount = 3;

  struct Slot {
    bool occupied = false;
    const char* title = "";
    const char* discriminator = "";
    TileState state = TileState::Empty;
    TileFeedback feedback = TileFeedback::Disabled;
  };

  Slot slots[kSlotCount];
  const char* source_status = "";
  bool syncing = false;
};
