#include <Arduino.h>
#include <ArduinoJson.h>
#include <TKeyboardS3Pro.h>
#if defined(ARDUINO_USB_MODE) && ARDUINO_USB_MODE == 0
#include <USB.h>
#endif
#include <esp_system.h>

#include <string.h>
#include <cstdio>

#include "board/board_adapter.h"
#include "board/physical_map.h"
#include "metrics/proof_metrics.h"
#include "metrics/hid_reset_journal.h"
#include "protocol/protocol.h"
#include "transport/link.h"
#include "transport/fixed_space_hid.h"
#include "ui/bringup_renderer.h"
#include "app/agent_projection.h"
#include "app/settings_store.h"
#include "app/menu_controller.h"
#include "app/product_input_router.h"
#include "ui/theme.h"
#include "app/hold_controller.h"
#include "ui/led_engine.h"

namespace {
constexpr size_t kMaxLineBytes = phase1::protocol::kMaxLineBytes;
constexpr uint32_t kBaud = 115200;
char inputFrame[kMaxLineBytes + 1];
char payloadScratch[kMaxLineBytes + 1];
char encodedFrame[kMaxLineBytes + 1];
size_t frameLength = 0;
bool frameOverflow = false;
uint32_t txSequence = 0;
bool encoderResponsePending = false;
uint32_t encoderInputAt = 0;
AnimationScheduler::Level lastAnimationLevel = AnimationScheduler::Level::Full;
String bootId;
String deviceId;
BoardAdapter board;
BringupRenderer renderer;
PhysicalMap physicalMap;
AgentProjection agentProjection;
SettingsStore settingsStore;
MenuController menuController(settingsStore);
LedEngine ledEngine;
ThemeId presentedTheme = ThemeId::SignalEdge;
UsbCdcLink usbLink;
FixedSpaceHid fixedSpaceHid;
ProofMetrics proofMetrics;
HoldController holdController(fixedSpaceHid, HoldController::kMeasuredThresholdUs,
                              &proofMetrics);
phase1::protocol::ProtocolSession protocolSession("", "", phase1::protocol::kQueueCapacity);
// Result contains the bounded payload buffer; persistent storage avoids
// exhausting the Arduino loop task stack during frame admission.
phase1::protocol::Result admission;

// Input arming is deliberately separate from the physical map. Until a user
// confirms the observation, the firmware only knows that an input changed.
enum class ArmedInput : uint8_t { None = 0, Key, Encoder, EncoderClick };
ArmedInput armedInput = ArmedInput::None;
uint8_t expectedKey = 0;
String activeStep;

bool usb_link_sampled = false;
bool usb_link_connected = false;

#if defined(ARDUINO_USB_MODE) && ARDUINO_USB_MODE == 0
void onUsbEvent(void*, esp_event_base_t event_base, int32_t event_id, void*) {
  if (event_base != ARDUINO_USB_EVENTS) return;
  switch (event_id) {
    case ARDUINO_USB_STARTED_EVENT:
      (void)holdController.onLifecycle(HoldController::LifecycleEvent::UsbMount);
      break;
    case ARDUINO_USB_STOPPED_EVENT:
      (void)holdController.onLifecycle(HoldController::LifecycleEvent::UsbStopped);
      break;
    case ARDUINO_USB_SUSPEND_EVENT:
      (void)holdController.onLifecycle(HoldController::LifecycleEvent::UsbSuspend);
      break;
    case ARDUINO_USB_RESUME_EVENT:
      (void)holdController.onLifecycle(HoldController::LifecycleEvent::UsbResume);
      break;
    default:
      break;
  }
}
#endif

void observeUsbLinkLifecycle() {
  const bool connected = usbLink.connected();
  if (!usb_link_sampled) {
    usb_link_sampled = true;
    usb_link_connected = connected;
    return;
  }
  if (connected == usb_link_connected) return;
  usb_link_connected = connected;
  const HoldController::LifecycleEvent event = connected
      ? HoldController::LifecycleEvent::UsbMount
      : HoldController::LifecycleEvent::Disconnect;
  (void)holdController.onLifecycle(event);
}

String opaqueId() {
  char value[33];
  uint64_t mac = ESP.getEfuseMac();
  snprintf(value, sizeof(value), "%08lx%08lx", static_cast<unsigned long>(mac >> 32),
           static_cast<unsigned long>(mac & 0xffffffffULL));
  return String(value);
}
String freshBootId(const String &stableDeviceId) {
  // ESP32-S3 hardware RNG is available before the USB/session handshake and
  // remains independent from the stable eFuse identity.
  const uint32_t nonce = esp_random();
  char suffix[9];
  snprintf(suffix, sizeof(suffix), "%08lx", static_cast<unsigned long>(nonce));
  return stableDeviceId + "-" + String(suffix);
}

void recordRejection(phase1::protocol::RejectReason reason) {
  switch (reason) {
    case phase1::protocol::RejectReason::Duplicate:
      proofMetrics.recordDuplicate();
      break;
    case phase1::protocol::RejectReason::OutOfOrder:
      proofMetrics.recordOutOfOrder();
      break;
    case phase1::protocol::RejectReason::DigestMismatch:
      proofMetrics.recordDigestMismatch();
      break;
    case phase1::protocol::RejectReason::EmptyLine:
    case phase1::protocol::RejectReason::MissingLf:
    case phase1::protocol::RejectReason::LineTooLong:
    case phase1::protocol::RejectReason::InvalidUtf8:
    case phase1::protocol::RejectReason::InvalidJson:
      proofMetrics.recordMalformed();
      break;
    default:
      proofMetrics.recordRejected();
      break;
  }
}

void sendFrame(const char *type, uint32_t replyTo, JsonObjectConst payload,
               bool countMetrics = true) {
  const size_t payloadLength = serializeJson(payload, payloadScratch, sizeof(payloadScratch) - 1);
  if (payloadLength == 0 || payloadLength + 1 > kMaxLineBytes || !protocolSession.active()) return;
  phase1::protocol::Frame outgoing;

  outgoing.version = (strcmp(type, "snapshot_ack") == 0 || strcmp(type, "focus_intent") == 0 ||
                      strcmp(type, "focus_result") == 0 || strcmp(type, "agent_snapshot") == 0) ? 2 : 1;
  strncpy(outgoing.type, type, sizeof(outgoing.type) - 1);
  strncpy(outgoing.boot_id, bootId.c_str(), sizeof(outgoing.boot_id) - 1);
  strncpy(outgoing.session_id, protocolSession.session_id(), sizeof(outgoing.session_id) - 1);
  outgoing.sequence = txSequence + 1;
  outgoing.reply_to = replyTo;
  outgoing.has_reply_to = replyTo != 0;
  phase1::protocol::FrameCodec::format_digest(
      phase1::protocol::FrameCodec::digest_payload(payloadScratch, payloadLength), outgoing.digest);

  size_t encodedLength = 0;
  if (!phase1::protocol::FrameCodec::encode(outgoing, payloadScratch, payloadLength,
                                             encodedFrame, sizeof(encodedFrame), encodedLength)) {
    return;
  }
  if (usbLink.write(reinterpret_cast<const uint8_t *>(encodedFrame), encodedLength) != encodedLength) {
    return;
  }
  // Durable sequence and proof counters advance only after the complete line
  // has been accepted by the link.
  txSequence = outgoing.sequence;
  if (countMetrics) {
    proofMetrics.recordSent();
    if (strcmp(type, "hello_ack") == 0 || strcmp(type, "probe_ack") == 0 ||
        strcmp(type, "metrics_ack") == 0) {
      proofMetrics.recordAcknowledged();
    }
  }
}

void sendError(const char *code, const char *detail, uint32_t replyTo) {
  JsonDocument payload;
  payload["code"] = code;
  payload["detail"] = detail;
  sendFrame("error", replyTo, payload.as<JsonObjectConst>());
}

void render(BringupState state, uint8_t panel, uint8_t brightness = 0,
            const char *challenge = nullptr) {
  if (!board.ready()) return;
  RenderRequest request;
  request.state = state;
  request.active_panel = panel;
  request.expected_key = expectedKey;
  request.brightness_percent = brightness;
  if (challenge != nullptr) {
    strncpy(request.challenge, challenge, sizeof(request.challenge) - 1);
    request.challenge[sizeof(request.challenge) - 1] = '\0';
  }
  const uint32_t started = micros();
  renderer.render(board, request);
  proofMetrics.observeDisplayFlush(micros() - started);
}

enum class StimulusKind : uint8_t {
  Invalid = 0, Map, Key, EncoderCw, EncoderCcw, EncoderClick, Brightness, Led,
  Pair, Pass, Fail, LinkLost, Wait, Reboot,
};

bool parseSingleIndex(const char *text, const char *prefix, uint8_t maximum, uint8_t &index) {
  const size_t prefixLength = strlen(prefix);
  if (strncmp(text, prefix, prefixLength) != 0) return false;
  const char *digits = text + prefixLength;
  if (digits[0] < '0' || digits[0] > '9') return false;
  uint16_t parsed = static_cast<uint16_t>(digits[0] - '0');
  if (digits[1] != '\0') {
    if (digits[1] < '0' || digits[1] > '9' || digits[2] != '\0') return false;
    parsed = static_cast<uint16_t>(parsed * 10U + (digits[1] - '0'));
  }
  if (parsed > maximum) return false;
  index = static_cast<uint8_t>(parsed);
  return true;
}

StimulusKind classifyStimulus(const char *stimulus, uint8_t &value) {
  value = 0;
  if (strcmp(stimulus, "1 ^ CYAN") == 0) {
    value = 1;
    return StimulusKind::Map;
  }
  if (parseSingleIndex(stimulus, "PANEL-", 4, value) && value >= 1) return StimulusKind::Map;
  if (parseSingleIndex(stimulus, "KEY-", 4, value) && value >= 1) return StimulusKind::Key;
  if (strcmp(stimulus, "ENC-CW") == 0) return StimulusKind::EncoderCw;
  if (strcmp(stimulus, "ENC-CCW") == 0) return StimulusKind::EncoderCcw;
  if (strcmp(stimulus, "ENC-CLICK") == 0) return StimulusKind::EncoderClick;
  if (strcmp(stimulus, "BRIGHTNESS-LOW") == 0) { value = 10; return StimulusKind::Brightness; }
  if (strcmp(stimulus, "BRIGHTNESS-MEDIUM") == 0) { value = 50; return StimulusKind::Brightness; }
  if (strcmp(stimulus, "BRIGHTNESS-HIGH") == 0) { value = 100; return StimulusKind::Brightness; }
  if (strcmp(stimulus, "LED-OFF") == 0) { value = 15; return StimulusKind::Led; }
  if (strcmp(stimulus, "LED-ALL") == 0) { value = 14; return StimulusKind::Led; }
  if (parseSingleIndex(stimulus, "LED-", 13, value)) return StimulusKind::Led;
  if (strncmp(stimulus, "PAIR-", 5) == 0 && stimulus[5] != '\0') return StimulusKind::Pair;
  if (strcmp(stimulus, "PASS") == 0) return StimulusKind::Pass;
  if (strcmp(stimulus, "FAIL") == 0) return StimulusKind::Fail;
  if (strcmp(stimulus, "LINK-LOST") == 0) return StimulusKind::LinkLost;
  if (strcmp(stimulus, "WAIT") == 0) return StimulusKind::Wait;
  if (strcmp(stimulus, "REBOOT") == 0) return StimulusKind::Reboot;
  return StimulusKind::Invalid;
}

bool applyStimulus(const char *stimulus, uint8_t &panel) {
  uint8_t value = 0;
  const StimulusKind kind = classifyStimulus(stimulus, value);
  panel = 1;
  armedInput = ArmedInput::None;

  switch (kind) {
    case StimulusKind::Map:
      panel = value;
      render(BringupState::Map, panel);
      return true;
    case StimulusKind::Key:
      if (!board.mapKeyLabel(value, expectedKey)) return false;
      armedInput = ArmedInput::Key;
      render(BringupState::Press, panel);
      return true;
    case StimulusKind::EncoderCw:
      armedInput = ArmedInput::Encoder;
      render(BringupState::TurnCw, panel);
      return true;
    case StimulusKind::EncoderCcw:
      armedInput = ArmedInput::Encoder;
      render(BringupState::TurnCcw, panel);
      return true;
    case StimulusKind::EncoderClick:
      if (!board.mapEncoderClick(expectedKey)) return false;
      armedInput = ArmedInput::EncoderClick;
      render(BringupState::Click, panel);
      return true;
    case StimulusKind::Brightness:
      board.setBrightness(value);
      render(BringupState::Brightness, panel, value);
      return true;
    case StimulusKind::Led: {
      const uint16_t ledMask = value == 14 ? 0x3FFF : (value == 15 ? 0 : static_cast<uint16_t>(1U << value));
      board.setLeds(0, 100, value == 15 ? 0 : 32, ledMask);
      render(BringupState::Map, panel);
      return true;
    }
    case StimulusKind::Pair:
      render(BringupState::Pair, panel, 0, stimulus + 5);
      return true;
    case StimulusKind::Pass: render(BringupState::Pass, panel); return true;
    case StimulusKind::Fail: render(BringupState::Fail, panel); return true;
    case StimulusKind::LinkLost: render(BringupState::LinkLost, panel); return true;
    case StimulusKind::Wait: render(BringupState::Wait, 0); return true;
    case StimulusKind::Reboot: render(BringupState::Pass, panel); return true;
    case StimulusKind::Invalid:
    default: return false;
  }
}

void completeAdmission() {
  protocolSession.complete();
  proofMetrics.observeQueue(protocolSession.pending_count());
}

bool parseCaptureRequest(const char* stimulus, uint8_t& panel, ThemeRenderer*& renderer,
                         CaptureScene& scene, CaptureLevel& level, uint8_t& phase) {
  renderer = nullptr;
  scene = CaptureScene::Current;
  level = CaptureLevel::Full;
  phase = 0;
  if (stimulus == nullptr || strncmp(stimulus, "CAPTURE:", 8) != 0 ||
      stimulus[8] < '0' || stimulus[8] > '3') {
    return false;
  }
  panel = static_cast<uint8_t>(stimulus[8] - '0');
  if (stimulus[9] == '\0') return true;
  if (stimulus[9] != ':' || stimulus[10] < '0' || stimulus[10] > '3' ||
      stimulus[11] != ':' || stimulus[12] == '\0') {
    return false;
  }
  renderer = &themeById(static_cast<ThemeId>(stimulus[10] - '0'));
  const char scene_token = stimulus[12];
  switch (scene_token) {
    case 'C': scene = CaptureScene::Current; break;
    case 'B': scene = CaptureScene::Blocked; break;
    case 'U': scene = CaptureScene::Unseen; break;
    case 'W': scene = CaptureScene::Working; break;
    case 'I': scene = CaptureScene::Idle; break;
    case 'S': scene = CaptureScene::Settled; break;
    case 'Q': scene = CaptureScene::Unknown; break;
    case 'E': scene = CaptureScene::Empty; break;
    case 'T': scene = CaptureScene::Stale; break;
    case 'O': scene = CaptureScene::Offline; break;
    case 'A': scene = CaptureScene::Unavailable; break;
    case 'P': scene = CaptureScene::Pending; break;
    case 'F': scene = CaptureScene::Focused; break;
    case 'R': scene = CaptureScene::Rejected; break;
    case 'V': scene = CaptureScene::Vanished; break;
    case 'N': scene = CaptureScene::Uncertain; break;
    case 'X': scene = CaptureScene::Failed; break;
    case 'Y': scene = CaptureScene::Sync; break;
    case 'M': scene = CaptureScene::MenuTheme; break;
    case 'L': scene = CaptureScene::MenuLed; break;
    case 'c': scene = CaptureScene::CodexCurrent; break;
    case 'p': scene = CaptureScene::CodexPartial; break;
    case 's': scene = CaptureScene::CodexStale; break;
    case 'u': scene = CaptureScene::CodexUnavailable; break;
    case 'a': scene = CaptureScene::CodexAuthRequired; break;
    case 'o': scene = CaptureScene::CodexOffline; break;
    case 'h': scene = CaptureScene::HostOffline; break;
    case 'l': scene = CaptureScene::CodexLimit; break;
    case 'g': scene = CaptureScene::CodexLong; break;
    case 'D': scene = CaptureScene::CopilotCurrent; break;
    case 'G': scene = CaptureScene::CopilotStale; break;
    case 'H': scene = CaptureScene::CopilotAuthRequired; break;
    case 'J': scene = CaptureScene::CopilotUnavailable; break;
    case 'K': scene = CaptureScene::CopilotLimit; break;
    case 'r': scene = CaptureScene::CopilotAllowed; break;
    case 'y': scene = CaptureScene::UsageUnavailable; break;
    case 'j': scene = CaptureScene::HoldPending; break;
    case 'k': scene = CaptureScene::SpaceActiveOwner; break;
    case 'q': scene = CaptureScene::CancellationReturn; break;
    case 'v': scene = CaptureScene::OwnerAfterOtherFocus; break;
    case 'x': scene = CaptureScene::FailurePreemption; break;
    case 'z': scene = CaptureScene::LifecycleClear; break;
    case '0':
      scene = panel == 3 ? CaptureScene::MenuRoot0 : CaptureScene::SlotsZero;
      break;
    case '1':
      scene = panel == 3 ? CaptureScene::MenuRoot1 : CaptureScene::SlotsOne;
      break;
    case '2':
      scene = panel == 3 ? CaptureScene::MenuRoot2 : CaptureScene::SlotsTwo;
      break;
    case '3':
      scene = panel == 3 ? CaptureScene::MenuRoot3 : CaptureScene::SlotsThree;
      break;
    case '4': scene = CaptureScene::MenuRoot4; break;
    case '5': scene = CaptureScene::MenuRoot5; break;
    case 'b': scene = CaptureScene::MenuBrightness; break;
    case 'e': scene = CaptureScene::MenuHealth; break;
    case 'd': scene = CaptureScene::MenuAbout; break;
    default: return false;
  }
  const size_t scene_length = strlen(stimulus + 12);
  if (scene_length == 1) return true;
  if (scene_length != 5 || stimulus[13] != ':' || stimulus[15] != ':' ||
      stimulus[14] == '\0' || stimulus[16] == '\0' || stimulus[17] != '\0') {
    return false;
  }
  switch (stimulus[14]) {
    case 'F': level = CaptureLevel::Full; break;
    case 'H': level = CaptureLevel::Half; break;
    case 'S': level = CaptureLevel::Static; break;
    default: return false;
  }
  if (stimulus[16] < '0' || stimulus[16] > '7') return false;
  phase = static_cast<uint8_t>(stimulus[16] - '0');
  return true;
}
bool streamCapturedPanel() {
  static constexpr size_t kPixelBytes = 128U * 128U * sizeof(uint16_t);
  static constexpr size_t kChunkBytes = 1024U;
  const char header[] = "SCREENSHOT-RGB565\n";
  if (usbLink.write(reinterpret_cast<const uint8_t *>(header), sizeof(header) - 1) != sizeof(header) - 1) return false;
  const uint8_t *bytes = reinterpret_cast<const uint8_t *>(agentProjection.capturePixels());
  if (bytes == nullptr) return false;
  for (size_t offset = 0; offset < kPixelBytes; offset += kChunkBytes) {
    const size_t count = (kPixelBytes - offset) < kChunkBytes ? (kPixelBytes - offset) : kChunkBytes;
    if (usbLink.write(bytes + offset, count) != count) return false;
  }
  return true;
}


void dispatchAdmission(const phase1::protocol::Result &admission) {
  if (!admission.accepted) {
    recordRejection(admission.reason);
    const uint32_t replyTo = admission.frame.sequence;
    sendError(phase1::protocol::rejection_name(admission.reason),
              "frame rejected before dispatch", replyTo);
    return;
  }
  if (admission.session_transition) {
    txSequence = 0;
    (void)holdController.onLifecycle(HoldController::LifecycleEvent::SessionReplacement);
  }
  proofMetrics.observeQueue(protocolSession.pending_count());

  JsonDocument payload;
  if (deserializeJson(payload, admission.frame.payload_text, admission.frame.payload_length)) {
    sendError("invalid_payload", "admitted payload could not be materialized", admission.frame.sequence);
    completeAdmission();
    return;
  }
  const char *type = admission.frame.type;
  if (strcmp(type, "agent_snapshot") == 0) {
    JsonObjectConst snapshot = payload.as<JsonObjectConst>();
    const uint32_t render_started = micros();
    const bool staged = agentProjection.stageSnapshot(snapshot);
    const MenuState& menu_state = menuController.state();
    const bool theme_preview = menuController.editing() && menu_state.cursor == 0;
    ThemeRenderer& panel4_theme = themeById(
        theme_preview ? menuController.activeTheme() : menuController.storedTheme());
    const bool committed =
        staged && agentProjection.commitSnapshot(board, panel4_theme, menu_state);
    const uint32_t reveal_elapsed = micros() - render_started;
    proofMetrics.observeDisplayFlush(reveal_elapsed);
    proofMetrics.observeReveal(reveal_elapsed);
    proofMetrics.sampleRuntime();
    JsonDocument reply;
    reply["accepted"] = committed;
    reply["host_epoch"] = snapshot["host_epoch"].as<const char*>();
    reply["reason"] = committed ? "committed" : "rejected";
    reply["snapshot_revision"] = snapshot["snapshot_revision"].as<uint32_t>();
    reply["source_status"] = snapshot["source_status"].as<const char*>();
    sendFrame("snapshot_ack", admission.frame.sequence, reply.as<JsonObjectConst>());
    completeAdmission();
    return;
  }
  if (strcmp(type, "focus_result") == 0) {
    const uint8_t slot = payload["slot"].as<uint8_t>();
    const char* action_id = payload["action_id"].as<const char*>();
    const AgentProjection::Feedback before =
        slot < AgentProjection::kSlotCount ? agentProjection.feedback(slot) :
                                               AgentProjection::Feedback::Disabled;
    const bool admitted = agentProjection.applyFocusResult(payload.as<JsonObjectConst>());
    holdController.observeFocusResult(slot, action_id, admitted, micros());
    if (slot < AgentProjection::kSlotCount && agentProjection.feedback(slot) != before) {
      // Failure, uncertainty, and success are semantic outcomes: publish their
      // complete frame immediately instead of waiting for ambient cadence.
      agentProjection.renderFeedback(board, slot);
    }
    completeAdmission();
    return;
  }
  if (strcmp(type, "focus_intent") == 0 || strcmp(type, "snapshot_ack") == 0) {
    sendError("invalid_direction", "device accepts snapshots and focus results only", admission.frame.sequence);
    completeAdmission();
    return;
  }
  if (strcmp(type, "hello") == 0) {
    JsonDocument reply;
    reply["accepted"] = true;
    reply["device_id"] = deviceId;
    reply["firmware"] = "phase1-bringup";
    reply["protocol"] = 1;
    JsonArray capabilities = reply["capabilities"].to<JsonArray>();
    capabilities.add("copilot_usage");
    sendFrame("hello_ack", admission.frame.sequence, reply.as<JsonObjectConst>());
    completeAdmission();
    return;
  }
  if (strcmp(type, "metrics") == 0) {
    const char *request = payload["request"].as<const char *>();
    if (request == nullptr || (strcmp(request, "proof") != 0 && strcmp(request, "reset") != 0)) {
      sendError("invalid_metrics", "metrics request must be proof or reset", admission.frame.sequence);
      completeAdmission();
      return;
    }
    proofMetrics.normalizeUntouchedSamples();
    const HidResetSnapshot& hid_reset = hidResetJournal().snapshot();
    JsonDocument reply;
    reply["acknowledged"] = proofMetrics.acknowledged;
    reply["allocation_stable"] = proofMetrics.allocation_stable;
    reply["animation_duty_max_percent"] = proofMetrics.animation_duty_max_percent;
    reply["candidate_transitions"] = proofMetrics.candidate_transitions;
    reply["chord_lockouts"] = proofMetrics.chord_lockouts;
    reply["compose_flush_max_us"] = proofMetrics.compose_flush_max_us;
    reply["degraded_frames"] = proofMetrics.degraded_frames;
    reply["digest_mismatch"] = proofMetrics.digest_mismatch;
    reply["duplicate"] = proofMetrics.duplicate;
    reply["eligibility_events"] = proofMetrics.eligibility_events;
    reply["eligibility_to_down_max_us"] =
        proofMetrics.eligibility_to_down_max_us;
    reply["first_encoder_response_us"] = proofMetrics.first_encoder_response_us;
    reply["first_press_response_us"] = proofMetrics.first_press_response_us;
    reply["focus_result_to_eligibility_max_us"] =
        proofMetrics.focus_result_to_eligibility_max_us;
    reply["frame_count"] = proofMetrics.frame_count;
    reply["full_frames"] = proofMetrics.full_frames;
    reply["half_frames"] = proofMetrics.half_frames;
    reply["hid_not_ready"] = proofMetrics.hid_not_ready;
    reply["hid_send_failures"] = proofMetrics.hid_send_failures;
    reply["hold_poll_gap_max_us"] = proofMetrics.hold_poll_gap_max_us;
    reply["largest_free_block"] = proofMetrics.largest_free_block;
    reply["level_changes"] = proofMetrics.level_changes;
    reply["lifecycle_clears"] = proofMetrics.lifecycle_clears;
    reply["loop_wall_max_us"] = proofMetrics.loop_wall_max_us;
    reply["malformed"] = proofMetrics.malformed;
    reply["max_display_flush_us"] = proofMetrics.max_display_flush_us;
    reply["max_key_poll_gap_us"] = proofMetrics.max_key_poll_gap_us;
    reply["minimum_free_heap"] = proofMetrics.minimum_free_heap;
    reply["out_of_order"] = proofMetrics.out_of_order;
    reply["owner_transitions"] = proofMetrics.owner_transitions;
    reply["parser_high_water"] = proofMetrics.parser_high_water;
    reply["physical_release_to_up_max_us"] =
        proofMetrics.physical_release_to_up_max_us;
    reply["queue_high_water"] = proofMetrics.queue_high_water;
    reply["received"] = proofMetrics.received;
    reply["rejected"] = proofMetrics.rejected;
    reply["release_all_attempts"] = proofMetrics.release_all_attempts;
    reply["release_all_failures"] = proofMetrics.release_all_failures;
    reply["reset_reason"] = hid_reset.reset_reason;
    reply["retained_boot_sequence"] = hid_reset.current_boot_sequence;
    reply["retained_previous_boot_sequence"] =
        hid_reset.previous_boot_sequence;
    reply["retained_previous_boot_valid"] =
        hid_reset.previous_boot_valid ? 1U : 0U;
    reply["retained_previous_empty_report_completions"] =
        hid_reset.previous_empty_report_completions;
    reply["retained_previous_last_lifecycle_event"] =
        hid_reset.previous_last_lifecycle_event;
    reply["retained_previous_last_lifecycle_status"] =
        hid_reset.previous_last_lifecycle_status;
    reply["retained_previous_last_report_kind"] =
        hid_reset.previous_last_report_kind;
    reply["retained_previous_last_report_status"] =
        hid_reset.previous_last_report_status;
    reply["retained_previous_lifecycle_clears"] =
        hid_reset.previous_lifecycle_clears;
    reply["retained_previous_report_attempts"] =
        hid_reset.previous_report_attempts;
    reply["retained_previous_report_completions"] =
        hid_reset.previous_report_completions;
    reply["retained_previous_space_down_completions"] =
        hid_reset.previous_space_down_completions;
    reply["reveal_max_us"] = proofMetrics.reveal_max_us;
    reply["sent"] = proofMetrics.sent;
    reply["skipped_frames"] = proofMetrics.skipped_frames;
    reply["space_down_completions"] = proofMetrics.space_down_completions;
    reply["space_down_requests"] = proofMetrics.space_down_requests;
    reply["space_up_completions"] = proofMetrics.space_up_completions;
    reply["space_up_requests"] = proofMetrics.space_up_requests;
    reply["static_frames"] = proofMetrics.static_frames;
    reply["threshold_crossings"] = proofMetrics.threshold_crossings;
    reply["watchdog_reset"] = proofMetrics.watchdog_reset;
    sendFrame("metrics_ack", admission.frame.sequence, reply.as<JsonObjectConst>(), false);
    completeAdmission();
    if (strcmp(request, "reset") == 0) proofMetrics.resetCounters();
    return;
  }
  if (strcmp(type, "probe") == 0) {
    const char *step = payload["step_id"].as<const char *>();
    const char *stimulus = payload["stimulus"].as<const char *>();
    const uint8_t requestedPanel = payload["panel"].as<uint8_t>();
    if (!board.ready()) {
      sendError("board_not_ready", "board initialization failed; probe not executed", admission.frame.sequence);
      completeAdmission();
      return;
    }
    uint8_t capturePanel = 0;
    ThemeRenderer* captureTheme = nullptr;
    CaptureScene captureScene = CaptureScene::Current;
    CaptureLevel captureLevel = CaptureLevel::Full;
    uint8_t capturePhase = 0;
    if (parseCaptureRequest(stimulus, capturePanel, captureTheme, captureScene,
                            captureLevel, capturePhase)) {
      if (!agentProjection.capturePanel(capturePanel, captureTheme, captureScene,
                                         captureLevel, capturePhase)) {
        sendError("capture_failed", "panel composition unavailable", admission.frame.sequence);
        completeAdmission();
        return;
      }
      JsonDocument reply;
      reply["accepted"] = true;
      reply["step_id"] = "screen-capture";
      sendFrame("probe_ack", admission.frame.sequence, reply.as<JsonObjectConst>());
      completeAdmission();
      streamCapturedPanel();
      return;
    }
    activeStep = step;
    uint8_t stimulatedPanel = requestedPanel;
    if (!applyStimulus(stimulus, stimulatedPanel)) {
      sendError("invalid_stimulus", "bounded bring-up stimulus is not recognized", admission.frame.sequence);
      completeAdmission();
      return;
    }
    JsonDocument reply;
    reply["accepted"] = true;
    reply["step_id"] = activeStep;
    sendFrame("probe_ack", admission.frame.sequence, reply.as<JsonObjectConst>());
    completeAdmission();
    if (strcmp(stimulus, "REBOOT") == 0) {
      // The accepted composite descriptor advertises a one-millisecond HID
      // interrupt interval. SendReport already waits for completion; this
      // measured drain delay lets the host consume the empty report before
      // the MCU reset tears down the interface.
      (void)holdController.onLifecycle(HoldController::LifecycleEvent::ControlledReset);
      delay(1);
      ESP.restart();
    }
    return;
  }
  sendError("unknown_type", "admitted frame is not a runtime request", admission.frame.sequence);
  completeAdmission();
}

bool readFrame() {
  bool processed = false;
  while (usbLink.available() > 0) {
    uint8_t byte = 0;
    if (usbLink.read(&byte, 1) != 1) break;
    if (byte == '\n') {
      if (frameOverflow) {
        protocolSession.accept(reinterpret_cast<const uint8_t *>(inputFrame),
                               kMaxLineBytes + 1, admission);
      } else {
        inputFrame[frameLength] = '\n';
        protocolSession.accept(reinterpret_cast<const uint8_t *>(inputFrame),
                               frameLength + 1, admission);
      }
      proofMetrics.recordReceived();
      dispatchAdmission(admission);
      frameLength = 0;
      frameOverflow = false;
      processed = true;
      break;
    }
    if (frameOverflow) continue;
    if (frameLength + 1 >= sizeof(inputFrame)) {
      frameOverflow = true;
      continue;
    }
    inputFrame[frameLength++] = static_cast<char>(byte);
    proofMetrics.observeParser(frameLength);
  }
  proofMetrics.observeQueue(protocolSession.pending_count());
  return processed;
}

void reportKeyTransition(uint8_t rawKey) {
  JsonDocument event;
  event["key"] = rawKey;
  event["kind"] = "key_transition";
  event["step_id"] = activeStep;
  sendFrame("event", 0, event.as<JsonObjectConst>());
}

void reportEncoderTransition(const char *direction) {
  JsonDocument event;
  event["direction"] = direction;
  event["kind"] = "encoder_transition";
  event["step_id"] = activeStep;
  sendFrame("event", 0, event.as<JsonObjectConst>());
}

void reportAgentKey(uint8_t key, uint32_t edge_latched_at_us) {
  if (!agentProjection.committed() || !board.ready() ||
      key >= AgentProjection::kSlotCount) {
    return;
  }
  const uint32_t response_started = micros();
  const uint32_t metric_started =
      edge_latched_at_us != 0 ? edge_latched_at_us : response_started;
  char actionId[32] = {};
  JsonDocument intent;
  std::snprintf(actionId, sizeof(actionId), "device-%lu-%u",
                static_cast<unsigned long>(response_started),
                static_cast<unsigned>(key));
  if (agentProjection.captureFocusIntent(key, actionId,
                                         intent.to<JsonObject>())) {
    agentProjection.renderFeedback(board, key);
    proofMetrics.observeFirstPressResponse(micros() - metric_started);
    sendFrame("focus_intent", 0, intent.as<JsonObjectConst>());
    holdController.registerPress(key, actionId, edge_latched_at_us);
  }
}

void reportInput() {
  if (!board.ready() || armedInput == ArmedInput::None || activeStep.isEmpty()) return;
  if (armedInput == ArmedInput::Key) {
    if (board.consumePressed(expectedKey)) {
      reportKeyTransition(expectedKey);
      armedInput = ArmedInput::None;
    }
    return;
  }
  if (armedInput == ArmedInput::Encoder) {
    const int32_t delta = static_cast<int32_t>(board.encoderDelta());
    if (delta > 0) {
      board.consumeEncoderDelta();
      reportEncoderTransition("cw");
      armedInput = ArmedInput::None;
    } else if (delta < 0) {
      board.consumeEncoderDelta();
      reportEncoderTransition("ccw");
      armedInput = ArmedInput::None;
    }
  } else if (armedInput == ArmedInput::EncoderClick && board.consumePressed(expectedKey)) {
    reportKeyTransition(expectedKey);
    armedInput = ArmedInput::None;
  }
}

void refreshMenuPresentation() {
  if (!menuController.takeDirty()) return;
  const ThemeId stored_theme = menuController.storedTheme();
  const bool theme_changed = stored_theme != presentedTheme;
  ThemeRenderer& candidate = themeById(stored_theme);
  if (theme_changed) {
    const bool applied = !agentProjection.committed() || agentProjection.redrawTiles(board, candidate);
    if (applied) {
      agentProjection.setTheme(candidate);
      agentProjection.animation().setAmbientPeriod(agentProjection.theme().ambientPeriodUs());
      presentedTheme = stored_theme;
    }
  }
  ledEngine.setGrammar(ledGrammarById(menuController.activeGrammar()));
  const bool theme_preview = menuController.editing() && menuController.state().cursor == 0;
  ThemeRenderer& menu_theme = themeById(theme_preview ? menuController.activeTheme() : stored_theme);
  agentProjection.renderMenu(board, menu_theme, menuController.state());
  if (encoderResponsePending) {
    proofMetrics.observeFirstEncoderResponse(micros() - encoderInputAt);
    encoderResponsePending = false;
  }
}
ProductInputFrame captureProductInput(uint32_t now_us) {
  ProductInputFrame frame;
  if (!board.ready()) return frame;
  for (uint8_t slot = 0; slot < ProductInputFrame::kAgentSlotCount; ++slot) {
    frame.agent_pressed[slot] =
        board.consumePressed(slot, &frame.agent_latched_at_us[slot]);
    frame.agent_down[slot] = board.isDown(slot);
    frame.agent_released[slot] = board.consumeReleased(slot);
  }
  frame.encoder_clicked =
      board.consumePressed(4, &frame.encoder_click_latched_at_us);
  frame.encoder_delta = static_cast<int32_t>(
      board.consumeEncoderDelta(&frame.encoder_delta_latched_at_us));
  if (frame.encoder_clicked && frame.encoder_click_latched_at_us == 0) {
    frame.encoder_click_latched_at_us = now_us;
  }
  if (frame.encoder_delta != 0 && frame.encoder_delta_latched_at_us == 0) {
    frame.encoder_delta_latched_at_us = now_us;
  }
  for (uint8_t slot = 0; slot < ProductInputFrame::kAgentSlotCount; ++slot) {
    if (frame.agent_pressed[slot] && frame.agent_latched_at_us[slot] == 0) {
      frame.agent_latched_at_us[slot] = now_us;
    }
  }
  return frame;
}

void applyBrightnessIntent() {
  uint8_t brightness = 0;
  if (menuController.takeBrightnessIntent(brightness)) {
    board.setBrightness(brightness);
  }
}

void dispatchProductInput(const ProductInputActions& actions,
                          const ProductInputFrame& input,
                          uint32_t now_us) {
  for (uint8_t index = 0; index < actions.count; ++index) {
    const ProductInputAction& action = actions[index];
    switch (action.kind) {
      case ProductInputActionKind::AgentSlot: {
        const uint8_t slot = static_cast<uint8_t>(action.value);
        reportAgentKey(slot, input.agent_latched_at_us[slot]);
        break;
      }
      case ProductInputActionKind::EncoderClick:
        if (menuController.click(now_us)) {
          encoderResponsePending = true;
          encoderInputAt = input.encoder_click_latched_at_us != 0
                               ? input.encoder_click_latched_at_us
                               : now_us;
        }
        break;
      case ProductInputActionKind::EncoderRotate:
        if (menuController.rotate(action.value, now_us)) {
          encoderResponsePending = true;
          encoderInputAt = input.encoder_delta_latched_at_us != 0
                               ? input.encoder_delta_latched_at_us
                               : now_us;
        }
        break;
    }
  }
  applyBrightnessIntent();
}
void dispatchAvailableProductInput(uint32_t now_us) {
  reportInput();
  const ProductInputFrame input = captureProductInput(now_us);
  const ProductInputActions actions = ProductInputRouter::route(input);
  dispatchProductInput(actions, input, now_us);
  const bool hid_ready = usbLink.connected() && fixedSpaceHid.ready();
  holdController.observeFrame(input, now_us, hid_ready);
}
}  // namespace
void setup() {
  const esp_reset_reason_t reset_reason = esp_reset_reason();
  beginHidResetJournal(static_cast<uint32_t>(reset_reason));
  proofMetrics.watchdog_reset =
      reset_reason == ESP_RST_INT_WDT || reset_reason == ESP_RST_TASK_WDT ||
      reset_reason == ESP_RST_WDT;
#if defined(ARDUINO_USB_MODE) && ARDUINO_USB_MODE == 0
  USB.onEvent(onUsbEvent);
#endif
  usbLink.begin(kBaud, sizeof(inputFrame));
#if defined(ARDUINO_USB_MODE) && ARDUINO_USB_MODE == 0
  // Composite mode registers CDC first, then the fixed keyboard descriptor,
  // and starts the shared USB device only after both interfaces exist.
  (void)fixedSpaceHid.ready();
  USB.begin();
#endif
  physicalMap.loadVerified();
  board.begin(physicalMap);
  settingsStore.load();
  menuController.resetFromStore();
  agentProjection.setHoldController(holdController);
  agentProjection.setTheme(themeById(menuController.storedTheme()));
  presentedTheme = menuController.storedTheme();
  agentProjection.animation().setAmbientPeriod(agentProjection.theme().ambientPeriodUs());
  ledEngine.setGrammar(ledGrammarById(menuController.storedGrammar()));
  deviceId = opaqueId();
  bootId = freshBootId(deviceId);
  protocolSession.reset(bootId.c_str(), "");
  if (board.ready()) {
    board.setBrightness(menuController.storedBrightness());
    render(BringupState::Wait, 0);
    agentProjection.renderMenu(board, themeById(menuController.storedTheme()), menuController.state());
  }
}

void loop() {
  const uint32_t loop_started = micros();
  const uint32_t now = loop_started;
  // Lifecycle release is the first operation in both cooperative poll paths:
  // it clears local authority before CDC admission, rendering, or LEDs.
  observeUsbLinkLifecycle();
  board.update(now);
  dispatchAvailableProductInput(now);
  if (menuController.expire(now)) applyBrightnessIntent();

  const bool admission_processed = readFrame();
  if (admission_processed) {
    const uint32_t after_admission = micros();
    board.update(after_admission);
    dispatchAvailableProductInput(after_admission);
  } else {
    const uint32_t free_heap_before = ESP.getFreeHeap();
    const uint32_t largest_before =
        heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
    const AnimationScheduler::Level rendered_level =
        agentProjection.animation().level();
    const uint32_t tick_started = micros();
    agentProjection.tick(board, now, menuController.open());
    const uint32_t tick_finished = micros();
    const uint32_t tick_cost = tick_finished - tick_started;
    const bool frame_observed =
        agentProjection.animation().consumeFrameObservation();
    if (frame_observed) {
      proofMetrics.observeAnimationAllocation(
          free_heap_before, largest_before, ESP.getFreeHeap(),
          heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
      agentProjection.animation().observeFlushCostAt(tick_cost, tick_finished);
      proofMetrics.observeAnimationFrame(
          tick_cost, agentProjection.animation().lastLoopWindowUs(),
          static_cast<uint8_t>(rendered_level));
    } else if (agentProjection.animation().level() ==
               AnimationScheduler::Level::Static) {
      proofMetrics.recordSkippedFrame();
    }
    if (agentProjection.animation().level() != lastAnimationLevel) {
      proofMetrics.recordAnimationLevelChange();
      proofMetrics.beginAnimationLevelEpoch();
      lastAnimationLevel = agentProjection.animation().level();
    }
    if (frame_observed &&
        rendered_level != AnimationScheduler::Level::Full) {
      proofMetrics.recordDegradedFrame();
    }
  }

  refreshMenuPresentation();
  LedEvents led_events;
  led_events.menu_open = menuController.open();
  if (led_events.menu_open) {
    led_events.semantic_event = LedSemanticEvent::MenuOpen;
    led_events.semantic_start_us = menuController.state().presentation_started_us;
    led_events.semantic_epoch = led_events.semantic_start_us != 0
                                    ? led_events.semantic_start_us
                                    : 1;
  }
  ledEngine.render(agentProjection.renderState(now), led_events, now, board);
  proofMetrics.observeKeyPollGap(board.takeMaxPollGapUs());
  proofMetrics.sampleRuntime();
  delay(1);
  proofMetrics.observeLoopWall(micros() - loop_started);
}
