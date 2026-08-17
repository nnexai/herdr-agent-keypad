#pragma once

#include <ArduinoJson.h>
#include <stddef.h>
#include <stdint.h>

class BoardAdapter;

class AgentProjection final {
 public:
  static constexpr uint8_t kSlotCount = 3;
  static constexpr size_t kTextBytes = 65;
  static constexpr uint32_t kPendingDeadlineUs = 3000000UL;
  static constexpr uint32_t kFeedbackHoldUs = 2000000UL;

  enum class TileState : uint8_t {
    Empty = 0, Blocked, Unseen, Working, Idle, Settled, Unknown,
    Stale, Offline, Unavailable, Sync, Pending, Focused, Rejected,
    Vanished, Uncertain, Failed,
  };
  enum class Feedback : uint8_t { Disabled = 0, Ready, Pending, Success, Rejected, Stale, Offline, Uncertain, Failed };

  AgentProjection();

  // The FrameCodec has already bounded and parsed the admitted payload.  All
  // three records are staged before any active binding can become actionable.
  bool stageSnapshot(JsonObjectConst payload);
  bool commitSnapshot();
  bool commitSnapshot(BoardAdapter& board);
  void tick(BoardAdapter& board, uint32_t now_us);
  bool committed() const { return committed_ && !syncing_; }
  bool syncing() const { return syncing_; }
  bool hasBinding(uint8_t slot) const;
  Feedback feedback(uint8_t slot) const;
  TileState state(uint8_t slot) const;
  const char* title(uint8_t slot) const;
  const char* discriminator(uint8_t slot) const;

  // Capture the immutable binding from a canonical key 0..2 press.  The
  // caller serializes the returned typed payload through the existing codec.
  bool captureFocusIntent(uint8_t key, const char* action_id, JsonObject payload);

  // Apply a host result only when every generation and opaque identity field
  // matches the pending binding.
  bool applyFocusResult(JsonObjectConst payload);

 private:
  struct Binding {
    bool occupied = false;
    char entry_id[kTextBytes] = {};
    char pane_id[kTextBytes] = {};
    char terminal_id[kTextBytes] = {};
    char workspace_id[kTextBytes] = {};
    char tab_id[kTextBytes] = {};
    char agent_session[kTextBytes] = {};
    bool has_agent_session = false;
    uint32_t source_revision = 0;
  };

  struct Tile {
    Binding binding;
    char title[kTextBytes] = "NO AGENT";
    char discriminator[33] = "NO WORKSPACE";
    TileState state = TileState::Empty;
  };

  struct Generation {
    char host_epoch[kTextBytes] = {};
    uint32_t snapshot_revision = 0;
    char source_status[16] = {};
    Tile tiles[kSlotCount] = {};
  };

  bool copyBounded(char* destination, size_t capacity, const char* source, bool allow_empty) const;
  bool copyOptional(char* destination, size_t capacity, JsonVariantConst value, bool& present) const;
  bool copyDisplay(char* destination, size_t capacity, const char* source, const char* fallback) const;
  bool matchingResult(JsonObjectConst payload, const Binding& binding, uint8_t slot) const;
  TileState parseState(const char* state) const;
  void disableActive(BoardAdapter* board);
  bool renderTile(BoardAdapter& board, uint8_t slot, const Tile& tile, Feedback feedback) const;
  void renderSync(BoardAdapter& board) const;

  Generation staged_{};
  Generation committed_generation_{};
  Binding pending_[kSlotCount]{};
  uint32_t pending_action_[kSlotCount]{};
  Feedback feedback_[kSlotCount]{};
  char pending_action_text_[kSlotCount][kTextBytes] = {};
  uint32_t pending_deadline_[kSlotCount]{};
  uint32_t feedback_until_[kSlotCount]{};
  bool staged_valid_ = false;
  bool committed_ = false;
  bool syncing_ = true;
  uint32_t next_action_ = 1;
};
