#include "agent_projection.h"

#include <Arduino.h>
#include <string.h>

namespace {
constexpr const char* kSourceStatuses[] = {"current", "empty", "stale", "unavailable", "offline"};
constexpr const char* kStates[] = {"empty", "working", "idle", "blocked", "finished", "settled", "unknown"};

bool listed(const char* value, const char* const* values, size_t count) {
  for (size_t index = 0; index < count; ++index) {
    if (strcmp(value, values[index]) == 0) return true;
  }
  return false;
}

bool printable(const char* value, bool allow_empty) {
  if (value == nullptr || (!allow_empty && value[0] == '\0')) return false;
  for (size_t index = 0; value[index] != '\0'; ++index) {
    const unsigned char byte = static_cast<unsigned char>(value[index]);
    if (byte < 0x21 || byte >= 0x80) return false;
  }
  return true;
}
}  // namespace

AgentProjection::AgentProjection() : feedback_{} {
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) feedback_[slot] = Feedback::Disabled;
}

bool AgentProjection::copyBounded(char* destination, size_t capacity, const char* source, bool allow_empty) const {
  if (destination == nullptr || source == nullptr || strlen(source) >= capacity || !printable(source, allow_empty)) return false;
  strncpy(destination, source, capacity - 1);
  destination[capacity - 1] = '\0';
  return true;
}

bool AgentProjection::copyOptional(char* destination, size_t capacity, JsonVariantConst value, bool& present) const {
  if (value.isNull()) {
    destination[0] = '\0';
    present = false;
    return true;
  }
  const char* text = value.as<const char*>();
  if (!copyBounded(destination, capacity, text, false)) return false;
  present = true;
  return true;
}

bool AgentProjection::stageSnapshot(JsonObjectConst payload) {
  const char* epoch = payload["host_epoch"].as<const char*>();
  const char* source_status = payload["source_status"].as<const char*>();
  const uint32_t revision = payload["snapshot_revision"].as<uint32_t>();
  JsonArrayConst agents = payload["agents"].as<JsonArrayConst>();
  if (!copyBounded(staged_.host_epoch, sizeof(staged_.host_epoch), epoch, false) ||
      !copyBounded(staged_.source_status, sizeof(staged_.source_status), source_status, false) ||
      !listed(source_status, kSourceStatuses, sizeof(kSourceStatuses) / sizeof(kSourceStatuses[0])) ||
      revision == 0 || agents.isNull() || agents.size() != kSlotCount) {
    staged_valid_ = false;
    return false;
  }
  staged_.snapshot_revision = revision;
  for (uint8_t index = 0; index < kSlotCount; ++index) staged_.bindings[index] = Binding();
  for (JsonObjectConst agent : agents) {
    const uint8_t slot = agent["slot"].as<uint8_t>();
    if (slot >= kSlotCount || staged_.bindings[slot].entry_id[0] != '\0') {
      staged_valid_ = false;
      return false;
    }
    const char* state = agent["state"].as<const char*>();
    const bool empty = state != nullptr && strcmp(state, "empty") == 0;
    if (state == nullptr || !listed(state, kStates, sizeof(kStates) / sizeof(kStates[0]))) {
      staged_valid_ = false;
      return false;
    }
    Binding& binding = staged_.bindings[slot];
    const char* entry_id = agent["entry_id"].as<const char*>();
    const char* pane_id = agent["pane_id"].as<const char*>();
    const char* terminal_id = agent["terminal_id"].as<const char*>();
    if (!copyBounded(binding.entry_id, sizeof(binding.entry_id), entry_id, empty) ||
        !copyBounded(binding.pane_id, sizeof(binding.pane_id), pane_id, empty) ||
        !copyBounded(binding.terminal_id, sizeof(binding.terminal_id), terminal_id, empty) ||
        !copyOptional(binding.agent_session, sizeof(binding.agent_session), agent["agent_session"], binding.has_agent_session)) {
      staged_valid_ = false;
      return false;
    }
    binding.source_revision = agent["source_revision"].as<uint32_t>();
    binding.occupied = !empty;
    if (binding.occupied && (binding.source_revision == 0 || staged_.source_status != "current")) {
      staged_valid_ = false;
      return false;
    }
    if (!binding.occupied && binding.source_revision != 0) {
      staged_valid_ = false;
      return false;
    }
  }
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    if (staged_.bindings[slot].entry_id[0] == '\0' && staged_.bindings[slot].occupied) {
      staged_valid_ = false;
      return false;
    }
  }
  staged_valid_ = true;
  return true;
}

bool AgentProjection::commitSnapshot() {
  if (!staged_valid_) return false;
  committed_generation_ = staged_;
  committed_ = true;
  staged_valid_ = false;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    pending_[slot] = Binding();
    pending_action_[slot] = 0;
    feedback_[slot] = committed_generation_.bindings[slot].occupied && committed_generation_.source_status[0] == 'c'
                          ? Feedback::Ready : Feedback::Disabled;
  }
  return true;
}

bool AgentProjection::hasBinding(uint8_t slot) const {
  return committed_ && slot < kSlotCount && committed_generation_.bindings[slot].occupied &&
         strcmp(committed_generation_.source_status, "current") == 0;
}

AgentProjection::Feedback AgentProjection::feedback(uint8_t slot) const {
  return slot < kSlotCount ? feedback_[slot] : Feedback::Disabled;
}

bool AgentProjection::captureFocusIntent(uint8_t key, const char* action_id, JsonObject payload) {
  if (!committed_ || key >= kSlotCount || action_id == nullptr || !hasBinding(key) || pending_action_[key] != 0 ||
      !copyBounded(pending_action_text_[key], sizeof(pending_action_text_[key]), action_id, false)) return false;
  pending_[key] = committed_generation_.bindings[key];
  pending_action_[key] = next_action_++;
  if (next_action_ == 0) next_action_ = 1;
  feedback_[key] = Feedback::Pending;
  payload["action_id"] = pending_action_text_[key];
  payload["host_epoch"] = committed_generation_.host_epoch;
  payload["snapshot_revision"] = committed_generation_.snapshot_revision;
  payload["slot"] = key;
  payload["entry_id"] = pending_[key].entry_id;
  payload["pane_id"] = pending_[key].pane_id;
  payload["terminal_id"] = pending_[key].terminal_id;
  if (pending_[key].has_agent_session) payload["agent_session"] = pending_[key].agent_session;
  else payload["agent_session"] = nullptr;
  payload["source_revision"] = pending_[key].source_revision;
  return true;
}

bool AgentProjection::matchingResult(JsonObjectConst payload, const Binding& binding, uint8_t slot) const {
  if (payload["slot"].as<uint8_t>() != slot || strcmp(payload["entry_id"].as<const char*>(), binding.entry_id) != 0 ||
      strcmp(payload["pane_id"].as<const char*>(), binding.pane_id) != 0 ||
      strcmp(payload["terminal_id"].as<const char*>(), binding.terminal_id) != 0 ||
      payload["source_revision"].as<uint32_t>() != binding.source_revision || !payload["focused"].as<bool>() ||
      strcmp(payload["outcome"].as<const char*>(), "accepted") != 0) return false;
  const JsonVariantConst session = payload["agent_session"];
  if (binding.has_agent_session) return !session.isNull() && strcmp(session.as<const char*>(), binding.agent_session) == 0;
  return session.isNull();
}

bool AgentProjection::applyFocusResult(JsonObjectConst payload) {
  const uint8_t slot = payload["slot"].as<uint8_t>();
  if (!committed_ || slot >= kSlotCount || pending_action_[slot] == 0 ||
      strcmp(payload["action_id"].as<const char*>(), pending_action_text_[slot]) != 0 ||
      strcmp(payload["host_epoch"].as<const char*>(), committed_generation_.host_epoch) != 0 ||
      payload["snapshot_revision"].as<uint32_t>() != committed_generation_.snapshot_revision) return false;
  const bool matched = matchingResult(payload, pending_[slot], slot);
  pending_action_[slot] = 0;
  pending_[slot] = Binding();
  feedback_[slot] = matched ? Feedback::Success : Feedback::Rejected;
  return matched;
}
