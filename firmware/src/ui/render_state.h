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

enum class CodexSourceState : uint8_t {
  Unavailable = 0, Current, Stale, AuthRequired, CodexOffline, HostOffline,
};

struct CodexRenderView {
  CodexSourceState source_state = CodexSourceState::Unavailable;
  int16_t primary = -1;
  int16_t secondary = -1;
  const char* reset_text = "RESET N/A";
  const char* observation_age = "AGE N/A";
  int8_t reached_limit = -1;
  const char* error_code = "";
};

struct DiagnosticsRenderView {
  const char* link_status = "offline";
  const char* herdr_status = "unavailable";
  const char* codex_status = "unavailable";
  const char* sync_age = "AGE N/A";
  const char* codex_age = "AGE N/A";
  const char* firmware_version = "UNAVAL";
  uint8_t protocol_version = 2;
  const char* bridge_version = "UNAVAL";
  const char* device_suffix = "UNAVAL";
  const char* session_suffix = "UNAVAL";
  const char* revision_suffix = "UNAVAL";
  const char* error_code = "";
};

struct RenderState {
  static constexpr uint8_t kSlotCount = 3;

  struct Slot {
    bool occupied = false;
    const char* title = "";
    const char* discriminator = "";
    const char* since = "";
    const char* age = "";
    TileState state = TileState::Empty;
    TileFeedback feedback = TileFeedback::Disabled;
  };
  CodexRenderView codex;
  DiagnosticsRenderView diagnostics;

  Slot slots[kSlotCount];
  const char* source_status = "";
  bool syncing = false;
  // Shared presentation metadata only. These fields are derived from the
  // committed generation and cannot authorize focus or replace host truth.
  bool transition_active = false;
  uint8_t transition_phase = 0;
  uint32_t transition_epoch = 0;
  uint32_t semantic_event_epoch = 0;
  uint8_t ambient_phase = 0;
  // BLOCKED pulse phase from the AnimationScheduler (1.2 s period, LED
  // synced). Themes draw their alternate BLOCKED frame when false.
  bool blocked_pulse_high = true;
};
