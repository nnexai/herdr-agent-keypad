#include "agent_projection.h"

#include <Arduino.h>
#include <string.h>

#include "../board/board_adapter.h"
#include "../ui/theme.h"

namespace {
constexpr const char* kSourceStatuses[] = {"current", "empty", "stale", "unavailable", "offline"};
constexpr const char* kStates[] = {"empty", "working", "idle", "blocked", "finished", "settled", "unknown"};
constexpr uint16_t kBackground = 0x1122;  // #0B0F14

LGFX_Sprite g_composition;
bool g_composition_ready = false;

bool ensureComposition() {
  if (g_composition_ready) return true;
  g_composition.setPsram(true);
  g_composition.setColorDepth(16);
  g_composition_ready = g_composition.createSprite(128, 128) != nullptr;
  if (g_composition_ready) g_composition.fillScreen(kBackground);
  return g_composition_ready;
}

bool listed(const char* value, const char* const* values, size_t count) {
  if (value == nullptr) return false;
  for (size_t index = 0; index < count; ++index) if (strcmp(value, values[index]) == 0) return true;
  return false;
}

bool printable(const char* value, bool allow_empty) {
  if (value == nullptr || (!allow_empty && value[0] == '\0')) return false;
  for (size_t index = 0; value[index] != '\0'; ++index) {
    const unsigned char byte = static_cast<unsigned char>(value[index]);
    if (byte < 0x20 || byte >= 0x80) return false;
  }
  return true;
}

bool elapsed(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}
}  // namespace

AgentProjection::AgentProjection() : feedback_{} {
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) feedback_[slot] = Feedback::Disabled;
}

ThemeRenderer& AgentProjection::theme() const {
  return theme_ != nullptr ? *theme_ : signalEdgeTheme();
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

bool AgentProjection::copyDisplay(char* destination, size_t capacity, const char* source, const char* fallback) const {
  if (source == nullptr || source[0] == '\0') source = fallback;
  if (source == nullptr || destination == nullptr || capacity < 4) return false;
  size_t length = strlen(source);
  if (length >= capacity) {
    length = capacity - 1;
    destination[length - 3] = '.';
    destination[length - 2] = '.';
    destination[length - 1] = '.';
    destination[length] = '\0';
    for (size_t index = 0; index < length - 3; ++index) {
      const unsigned char byte = static_cast<unsigned char>(source[index]);
      if (byte < 0x20 || byte >= 0x80) return false;
      destination[index] = source[index];
    }
    return true;
  }
  return copyBounded(destination, capacity, source, false);
}

AgentProjection::TileState AgentProjection::parseState(const char* state) const {
  if (state == nullptr) return TileState::Unknown;
  if (strcmp(state, "empty") == 0) return TileState::Empty;
  if (strcmp(state, "blocked") == 0) return TileState::Blocked;
  if (strcmp(state, "finished") == 0) return TileState::Unseen;
  if (strcmp(state, "working") == 0) return TileState::Working;
  if (strcmp(state, "idle") == 0) return TileState::Idle;
  if (strcmp(state, "settled") == 0) return TileState::Settled;
  return strcmp(state, "unknown") == 0 ? TileState::Unknown : TileState::Unknown;
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
  if (committed_ && strcmp(committed_generation_.host_epoch, staged_.host_epoch) == 0 &&
      revision <= committed_generation_.snapshot_revision) {
    staged_valid_ = false;
    return false;
  }
  staged_.snapshot_revision = revision;
  bool seen[kSlotCount] = {};
  for (JsonObjectConst agent : agents) {
    const uint8_t slot = agent["slot"].as<uint8_t>();
    if (slot >= kSlotCount || seen[slot]) { staged_valid_ = false; return false; }
    seen[slot] = true;
    const char* state = agent["state"].as<const char*>();
    if (!listed(state, kStates, sizeof(kStates) / sizeof(kStates[0]))) { staged_valid_ = false; return false; }
    Tile& tile = staged_.tiles[slot];
    tile = Tile();
    tile.state = parseState(state);
    const bool empty = tile.state == TileState::Empty;
    const char* entry_id = agent["entry_id"].as<const char*>();
    const char* pane_id = agent["pane_id"].as<const char*>();
    const char* terminal_id = agent["terminal_id"].as<const char*>();
    bool workspace_present = false;
    bool tab_present = false;
    if (!copyBounded(tile.binding.entry_id, sizeof(tile.binding.entry_id), entry_id, empty) ||
        !copyBounded(tile.binding.pane_id, sizeof(tile.binding.pane_id), pane_id, empty) ||
        !copyBounded(tile.binding.terminal_id, sizeof(tile.binding.terminal_id), terminal_id, empty) ||
        !copyOptional(tile.binding.workspace_id, sizeof(tile.binding.workspace_id), agent["workspace_id"], workspace_present) ||
        !copyOptional(tile.binding.tab_id, sizeof(tile.binding.tab_id), agent["tab_id"], tab_present) ||
        !copyOptional(tile.binding.agent_session, sizeof(tile.binding.agent_session), agent["agent_session"], tile.binding.has_agent_session) ||
        !copyDisplay(tile.title, sizeof(tile.title), agent["title"].as<const char*>(), "NO AGENT") ||
        !copyDisplay(tile.discriminator, sizeof(tile.discriminator), agent["discriminator"].as<const char*>(), "NO WORKSPACE")) {
      staged_valid_ = false;
      return false;
    }
    tile.binding.source_revision = agent["source_revision"].as<uint32_t>();
    tile.binding.occupied = !empty;
    if (tile.binding.occupied && tile.binding.source_revision == 0) { staged_valid_ = false; return false; }
    if (!tile.binding.occupied && tile.binding.source_revision != 0) { staged_valid_ = false; return false; }
  }
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) if (!seen[slot]) { staged_valid_ = false; return false; }
  staged_valid_ = true;
  return true;
}

void AgentProjection::disableActive(BoardAdapter* board) {
  committed_ = false;
  syncing_ = true;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    pending_[slot] = Binding();
    pending_action_[slot] = 0;
    pending_action_text_[slot][0] = '\0';
    pending_deadline_[slot] = 0;
    feedback_until_[slot] = 0;
    feedback_[slot] = Feedback::Disabled;
  }
  if (board != nullptr) renderSync(*board);
}
bool AgentProjection::commitSnapshot() {
  if (!staged_valid_) return false;
  committed_generation_ = staged_;
  committed_ = true;
  syncing_ = false;
  staged_valid_ = false;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    pending_[slot] = Binding();
    pending_action_[slot] = 0;
    feedback_[slot] = (committed_generation_.tiles[slot].binding.occupied && strcmp(committed_generation_.source_status, "current") == 0)
                          ? Feedback::Ready : Feedback::Disabled;
  }
  return true;
}
bool AgentProjection::commitSnapshot(BoardAdapter& board) {
  if (!staged_valid_ || !ensureComposition()) return false;
  // Per-panel direct-cut reveal (R-2): panels flip old-complete -> new-complete
  // sequentially with no SYNC veil for ordinary refreshes.  Bindings deactivate
  // here at stage time and activate only after the third flush, so a press
  // during the reveal window can never bind to mixed pixels.  Boot, session
  // reset, and any compose/flush failure keep the SYNC presentation.
  disableActive(nullptr);
  committed_generation_ = staged_;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    if (!renderTile(board, slot, staged_.tiles[slot], Feedback::Disabled)) {
      staged_valid_ = false;
      syncing_ = true;
      renderSync(board);  // best-effort fail-closed SYNC on all panels
      return false;
    }
  }
  return commitSnapshot();
}

bool AgentProjection::renderSync(BoardAdapter& board) const {
  if (!ensureComposition()) return false;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    Display* display = board.displayAt(slot);
    if (display == nullptr) return false;
    theme().composeSync(g_composition);
    g_composition.pushSprite(display, 0, 0);
  }
  return true;
}

bool AgentProjection::renderTile(BoardAdapter& board, uint8_t slot, const Tile& tile, Feedback feedback) const {
  Display* display = board.displayAt(slot);
  if (display == nullptr || !ensureComposition()) return false;
  RenderState state;
  state.source_status = committed_generation_.source_status;
  state.syncing = syncing_;
  state.blocked_pulse_high = animation_.blockedPulseHigh(micros());
  RenderState::Slot& out = state.slots[slot];
  out.occupied = tile.binding.occupied;
  out.title = tile.title;
  out.discriminator = tile.discriminator;
  out.state = tile.state;
  out.feedback = feedback;
  theme().composeTile(g_composition, slot, state);
  g_composition.pushSprite(display, 0, 0);
  return true;
}

void AgentProjection::tick(BoardAdapter& board, uint32_t now_us) {
  if (!committed_ || syncing_) return;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    if (pending_action_[slot] != 0 && elapsed(now_us, pending_deadline_[slot])) {
      pending_action_[slot] = 0;
      pending_[slot] = Binding();
      feedback_[slot] = Feedback::Uncertain;
      feedback_until_[slot] = now_us + kFeedbackHoldUs;
      renderTile(board, slot, committed_generation_.tiles[slot], feedback_[slot]);
    } else if (pending_action_[slot] == 0 && feedback_until_[slot] != 0 && elapsed(now_us, feedback_until_[slot])) {
      feedback_until_[slot] = 0;
      feedback_[slot] = (committed_generation_.tiles[slot].binding.occupied &&
                         strcmp(committed_generation_.source_status, "current") == 0)
                            ? Feedback::Ready : Feedback::Disabled;
      renderTile(board, slot, committed_generation_.tiles[slot], feedback_[slot]);
    }
  }

  // Bounded animation (R-1): the scheduler decides when a frame is due; every
  // frame is a complete recomposition flushed through the normal path.
  // Semantic dominance: fences suppress all motion; per-slot feedback
  // suppresses that slot's motion (Pending keeps its own spinner cadence via
  // the BLOCKED clock so it still steps, bounded).
  const bool fenced = strcmp(committed_generation_.source_status, "current") != 0;
  const bool blocked_frame = animation_.blockedFrameDue(now_us);
  const bool ambient_frame = animation_.ambientFrameDue(now_us);
  if (fenced || (!blocked_frame && !ambient_frame)) return;
  const uint8_t ambient_mask = ambient_frame ? theme().ambientTick(now_us) : 0;
  for (uint8_t slot = 0; slot < kSlotCount; ++slot) {
    const bool feedback_active = feedback_[slot] != Feedback::Ready && feedback_[slot] != Feedback::Disabled;
    const bool blocked_dirty = blocked_frame && committed_generation_.tiles[slot].state == TileState::Blocked;
    const bool ambient_dirty = (ambient_mask & static_cast<uint8_t>(1U << slot)) != 0;
    const bool pending_dirty = blocked_frame && feedback_[slot] == Feedback::Pending;
    if (feedback_active && !pending_dirty) continue;
    if (blocked_dirty || pending_dirty || (ambient_dirty && !feedback_active)) {
      renderTile(board, slot, committed_generation_.tiles[slot], feedback_[slot]);
    }
  }
}

void AgentProjection::renderFeedback(BoardAdapter& board, uint8_t slot) {
  if (slot < kSlotCount && committed_ && !syncing_) renderTile(board, slot, committed_generation_.tiles[slot], feedback_[slot]);
}

bool AgentProjection::hasBinding(uint8_t slot) const {
  const Feedback feedback = slot < kSlotCount ? feedback_[slot] : Feedback::Disabled;
  const bool actionable = feedback == Feedback::Ready || feedback == Feedback::Success;
  return committed_ && !syncing_ && slot < kSlotCount && committed_generation_.tiles[slot].binding.occupied &&
         strcmp(committed_generation_.source_status, "current") == 0 && actionable;
}

AgentProjection::Feedback AgentProjection::feedback(uint8_t slot) const { return slot < kSlotCount ? feedback_[slot] : Feedback::Disabled; }
AgentProjection::TileState AgentProjection::state(uint8_t slot) const { return slot < kSlotCount ? committed_generation_.tiles[slot].state : TileState::Unavailable; }
const char* AgentProjection::title(uint8_t slot) const { return slot < kSlotCount ? committed_generation_.tiles[slot].title : ""; }
const char* AgentProjection::discriminator(uint8_t slot) const { return slot < kSlotCount ? committed_generation_.tiles[slot].discriminator : ""; }

bool AgentProjection::captureFocusIntent(uint8_t key, const char* action_id, JsonObject payload) {
  if (!committed_ || syncing_ || key >= kSlotCount || action_id == nullptr || !hasBinding(key) || pending_action_[key] != 0 ||
      !copyBounded(pending_action_text_[key], sizeof(pending_action_text_[key]), action_id, false)) return false;
  pending_[key] = committed_generation_.tiles[key].binding;
  pending_action_[key] = next_action_++;
  if (next_action_ == 0) next_action_ = 1;
  pending_deadline_[key] = micros() + kPendingDeadlineUs;
  feedback_[key] = Feedback::Pending;
  payload["action_id"] = pending_action_text_[key];
  if (pending_[key].has_agent_session) payload["agent_session"] = pending_[key].agent_session; else payload["agent_session"] = nullptr;
  payload["entry_id"] = pending_[key].entry_id;
  payload["host_epoch"] = committed_generation_.host_epoch;
  payload["pane_id"] = pending_[key].pane_id;
  payload["slot"] = key;
  payload["snapshot_revision"] = committed_generation_.snapshot_revision;
  payload["source_revision"] = pending_[key].source_revision;
  payload["terminal_id"] = pending_[key].terminal_id;
  return true;
}

bool AgentProjection::matchingResult(JsonObjectConst payload, const Binding& binding, uint8_t slot) const {
  const char* entry = payload["entry_id"].as<const char*>();
  const char* pane = payload["pane_id"].as<const char*>();
  const char* terminal = payload["terminal_id"].as<const char*>();
  if (payload["slot"].as<uint8_t>() != slot || entry == nullptr || pane == nullptr || terminal == nullptr ||
      strcmp(entry, binding.entry_id) != 0 || strcmp(pane, binding.pane_id) != 0 || strcmp(terminal, binding.terminal_id) != 0 ||
      payload["source_revision"].as<uint32_t>() != binding.source_revision) return false;
  const JsonVariantConst session = payload["agent_session"];
  if (binding.has_agent_session) return !session.isNull() && strcmp(session.as<const char*>(), binding.agent_session) == 0;
  return session.isNull();
}

bool AgentProjection::applyFocusResult(JsonObjectConst payload) {
  const uint8_t slot = payload["slot"].as<uint8_t>();
  const char* action = payload["action_id"].as<const char*>();
  const char* epoch = payload["host_epoch"].as<const char*>();
  const char* outcome = payload["outcome"].as<const char*>();
  if (!committed_ || syncing_ || slot >= kSlotCount || pending_action_[slot] == 0 || action == nullptr || epoch == nullptr || outcome == nullptr ||
      strcmp(action, pending_action_text_[slot]) != 0 || strcmp(epoch, committed_generation_.host_epoch) != 0 ||
      payload["snapshot_revision"].as<uint32_t>() != committed_generation_.snapshot_revision || !matchingResult(payload, pending_[slot], slot)) return false;
  pending_action_[slot] = 0;
  pending_[slot] = Binding();
  if (strcmp(outcome, "accepted") == 0 && payload["focused"].as<bool>()) feedback_[slot] = Feedback::Success;
  else if (strcmp(outcome, "stale_target") == 0) feedback_[slot] = Feedback::Stale;
  else if (strcmp(outcome, "vanished") == 0 || strcmp(outcome, "not_found") == 0) feedback_[slot] = Feedback::Vanished;
  else if (strcmp(outcome, "herdr_offline") == 0) feedback_[slot] = Feedback::Offline;
  else if (strcmp(outcome, "timeout") == 0 || strcmp(outcome, "uncertain") == 0) feedback_[slot] = Feedback::Uncertain;
  else if (strcmp(outcome, "failed") == 0) feedback_[slot] = Feedback::Failed;
  else feedback_[slot] = Feedback::Rejected;
  feedback_until_[slot] = micros() + (feedback_[slot] == Feedback::Success ? kSuccessHoldUs : kFeedbackHoldUs);
  return feedback_[slot] == Feedback::Success;
}
