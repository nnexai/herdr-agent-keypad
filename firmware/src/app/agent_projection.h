#pragma once

#include <ArduinoJson.h>
#include <stddef.h>
#include <stdint.h>

#include "../ui/animation.h"
#include "../ui/render_state.h"

class BoardAdapter;
class ThemeRenderer;
struct MenuState;

enum class CaptureScene : uint8_t {
  Current = 0,
  Blocked,
  Unseen,
  Working,
  Idle,
  Settled,
  Unknown,
  Empty,
  Stale,
  Offline,
  Unavailable,
  Pending,
  Focused,
  Rejected,
  Vanished,
  Uncertain,
  Failed,
  Sync,
  MenuTheme,
  MenuLed,
  CodexCurrent,
  CodexPartial,
  CodexStale,
  CodexUnavailable,
  CodexAuthRequired,
  CodexOffline,
  HostOffline,
  CodexLimit,
  CodexLong,
  MenuRoot0,
  MenuRoot1,
  MenuRoot2,
  MenuRoot3,
  MenuRoot4,
  MenuRoot5,
  MenuBrightness,
  MenuHealth,
  MenuAbout,
  SlotsZero,
  SlotsOne,
  SlotsTwo,
  SlotsThree,
};
using CaptureLevel = AnimationScheduler::Level;
static constexpr uint8_t kCapturePhaseCount = 8;
class AgentProjection final {
 public:
  static constexpr uint8_t kSlotCount = 3;
  static constexpr size_t kTextBytes = 65;
  static constexpr uint32_t kPendingDeadlineUs = 3000000UL;
  static constexpr uint32_t kPendingStepUs = 300000UL;
  static constexpr uint32_t kFeedbackHoldUs = 2000000UL;
  // Success feedback is deliberately shorter than the failure family (D-15).
  static constexpr uint32_t kSuccessHoldUs = 800000UL;
  using Feedback = TileFeedback;
  using TileState = ::TileState;

  AgentProjection();

  // Presentation is delegated to the active theme; staging, commit fencing,
  // bindings, and flush ownership stay here.
  void setTheme(ThemeRenderer& theme) { theme_ = &theme; }
  ThemeRenderer& theme() const;
  RenderState renderState(uint32_t now_us) const;
  AnimationScheduler& animation() { return animation_; }
  const AnimationScheduler& animation() const { return animation_; }

  // The FrameCodec has already bounded and parsed the admitted payload.  All
  // three records are staged before any active binding can become actionable.
  bool stageSnapshot(JsonObjectConst payload);
  bool commitSnapshot();
  bool commitSnapshot(BoardAdapter& board);
  bool commitSnapshot(BoardAdapter& board, ThemeRenderer& panel4_theme,
                      const MenuState& menu);
  void tick(BoardAdapter& board, uint32_t now_us);
  void renderMenu(BoardAdapter& board, ThemeRenderer& theme, const MenuState& menu) const;
  // Recompose every committed agent tile after a confirmed theme change.
  // The candidate is installed only after all complete frames flush.
  bool redrawTiles(BoardAdapter& board);
  bool redrawTiles(BoardAdapter& board, ThemeRenderer& candidate);
  // Developer capture seam: compose one live or deterministic fixture panel
  // without flushing it, then expose the existing PSRAM-backed RGB565 sprite
  // for a bounded USB dump.
  bool capturePanel(uint8_t panel, ThemeRenderer* renderer = nullptr,
                    CaptureScene scene = CaptureScene::Current,
                    CaptureLevel level = CaptureLevel::Full,
                    uint8_t phase = 0);
  const uint16_t* capturePixels() const;
  bool committed() const { return committed_ && !syncing_; }
  void renderFeedback(BoardAdapter& board, uint8_t slot);
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
    char since[17] = "-";
    char age[17] = "-";
    TileState state = TileState::Empty;
  };

  struct Generation {
    char host_epoch[kTextBytes] = {};
    uint32_t snapshot_revision = 0;
    char source_status[16] = {};
    Tile tiles[kSlotCount] = {};
    char codex_source_state[20] = "unavailable";
    int16_t codex_primary = -1;
    int16_t codex_secondary = -1;
    char codex_reset_text[33] = "RESET N/A";
    char codex_observation_age[17] = "AGE N/A";
    int8_t codex_reached_limit = -1;
    char codex_error_code[17] = {};
    char diagnostics_link_status[16] = "offline";
    char diagnostics_herdr_status[16] = "unavailable";
    char diagnostics_codex_status[20] = "unavailable";
    char diagnostics_sync_age[17] = "AGE N/A";
    char diagnostics_codex_age[17] = "AGE N/A";
    char diagnostics_firmware_version[17] = "UNAVAL";
    uint8_t diagnostics_protocol_version = 2;
    char diagnostics_bridge_version[17] = "UNAVAL";
    char diagnostics_device_suffix[7] = "UNAVAL";
    char diagnostics_session_suffix[7] = "UNAVAL";
    char diagnostics_revision_suffix[7] = "UNAVAL";
    char diagnostics_error_code[17] = {};
  };
  bool copyBounded(char* destination, size_t capacity, const char* source, bool allow_empty) const;
  bool copyOptional(char* destination, size_t capacity, JsonVariantConst value, bool& present) const;
  bool copyDisplay(char* destination, size_t capacity, const char* source, const char* fallback) const;
  bool matchingResult(JsonObjectConst payload, const Binding& binding, uint8_t slot) const;
  TileState parseState(const char* state) const;
  void disableActive(BoardAdapter* board);
  bool renderTile(BoardAdapter& board, uint8_t slot, const Tile& tile, Feedback feedback) const;
  bool renderTileAt(BoardAdapter& board, uint8_t slot, const Tile& tile,
                    Feedback feedback, uint32_t now_us) const;
  bool renderTile(BoardAdapter& board, ThemeRenderer& theme, uint8_t slot,
                  const Tile& tile, Feedback feedback) const;
  bool renderTileAt(BoardAdapter& board, ThemeRenderer& theme, uint8_t slot,
                    const Tile& tile, Feedback feedback, uint32_t now_us) const;
  bool renderTile(BoardAdapter& board, ThemeRenderer& theme,
                  const Generation& generation, uint8_t slot,
                  const Tile& tile, Feedback feedback) const;
  bool renderTileAt(BoardAdapter& board, ThemeRenderer& theme,
                    const Generation& generation, uint8_t slot,
                    const Tile& tile, Feedback feedback, uint32_t now_us) const;
  bool renderSync(BoardAdapter& board) const;

  Generation staged_{};
  Generation committed_generation_{};
  Binding pending_[kSlotCount]{};
  uint32_t pending_action_[kSlotCount]{};
  Feedback feedback_[kSlotCount]{};
  bool press_impulse_[kSlotCount]{};
  uint8_t feedback_phase_[kSlotCount]{};
  char pending_action_text_[kSlotCount][kTextBytes] = {};
  uint32_t pending_deadline_[kSlotCount]{};
  uint32_t pending_step_[kSlotCount]{};
  uint32_t feedback_until_[kSlotCount]{};
  bool staged_valid_ = false;
  bool staged_codex_only_ = false;
  bool committed_ = false;
  bool syncing_ = true;
  uint32_t next_action_ = 1;
  ThemeRenderer* theme_ = nullptr;
  AnimationScheduler animation_{};
  uint32_t semantic_event_epoch_ = 0;
  bool transition_after_commit_ = false;
};
