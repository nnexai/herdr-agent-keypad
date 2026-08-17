#pragma once

#include <ArduinoJson.h>
#include <stddef.h>
#include <stdint.h>

class BoardAdapter;

class AgentProjection final {
 public:
  static constexpr uint8_t kSlotCount = 3;
  static constexpr size_t kTextBytes = 65;

  enum class Feedback : uint8_t { Disabled = 0, Ready, Pending, Success, Rejected };

  AgentProjection();

  // The FrameCodec has already bounded and parsed the admitted payload. This
  // boundary consumes that object, stages all three records, and never makes
  // a partially received generation actionable.
  bool stageSnapshot(JsonObjectConst payload);
  bool commitSnapshot();
  bool committed() const { return committed_; }
  bool hasBinding(uint8_t slot) const;
  Feedback feedback(uint8_t slot) const;

  // Capture the immutable binding from a canonical key 0..2 press. The caller
  // serializes the returned typed payload through the existing FrameCodec.
  bool captureFocusIntent(uint8_t key, const char* action_id, JsonObject payload);

  // Apply a host result only when every bridge-owned generation and opaque
  // identity field matches the pending binding.
  bool applyFocusResult(JsonObjectConst payload);

 private:
  struct Binding {
    bool occupied = false;
    char entry_id[kTextBytes] = {};
    char pane_id[kTextBytes] = {};
    char terminal_id[kTextBytes] = {};
    char agent_session[kTextBytes] = {};
    bool has_agent_session = false;
    uint32_t source_revision = 0;
  };

  struct Generation {
    char host_epoch[kTextBytes] = {};
    uint32_t snapshot_revision = 0;
    char source_status[16] = {};
    Binding bindings[kSlotCount] = {};
  };

  bool copyBounded(char* destination, size_t capacity, const char* source, bool allow_empty) const;
  bool copyOptional(char* destination, size_t capacity, JsonVariantConst value, bool& present) const;
  bool matchingResult(JsonObjectConst payload, const Binding& binding, uint8_t slot) const;

  Generation staged_{};
  Generation committed_generation_{};
  Binding pending_[kSlotCount]{};
  uint32_t pending_action_[kSlotCount]{};
  Feedback feedback_[kSlotCount]{};
  char pending_action_text_[kSlotCount][kTextBytes] = {};
  bool staged_valid_ = false;
  bool committed_ = false;
  uint32_t next_action_ = 1;
};
