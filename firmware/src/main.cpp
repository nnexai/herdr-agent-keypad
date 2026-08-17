#include <Arduino.h>
#include <ArduinoJson.h>
#include <TKeyboardS3Pro.h>
#include <esp_system.h>

#include <string.h>
#include <cstdio>

#include "board/board_adapter.h"
#include "board/physical_map.h"
#include "metrics/proof_metrics.h"
#include "protocol/protocol.h"
#include "transport/link.h"
#include "ui/bringup_renderer.h"
#include "app/agent_projection.h"

namespace {
constexpr size_t kMaxLineBytes = phase1::protocol::kMaxLineBytes;
constexpr uint32_t kBaud = 115200;
char inputFrame[kMaxLineBytes + 1];
char payloadScratch[kMaxLineBytes + 1];
char encodedFrame[kMaxLineBytes + 1];
size_t frameLength = 0;
bool frameOverflow = false;
uint32_t txSequence = 0;
uint32_t lastKeyPollAt = 0;
String bootId;
String deviceId;
BoardAdapter board;
BringupRenderer renderer;
PhysicalMap physicalMap;
AgentProjection agentProjection;
UsbCdcLink usbLink;
ProofMetrics proofMetrics;
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

void dispatchAdmission(const phase1::protocol::Result &admission) {
  if (!admission.accepted) {
    recordRejection(admission.reason);
    const uint32_t replyTo = admission.frame.sequence;
    sendError(phase1::protocol::rejection_name(admission.reason),
              "frame rejected before dispatch", replyTo);
    return;
  }
  if (admission.session_transition) txSequence = 0;
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
    const bool staged = agentProjection.stageSnapshot(snapshot);
    const bool committed = staged && agentProjection.commitSnapshot(board);
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
    agentProjection.applyFocusResult(payload.as<JsonObjectConst>());
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
    JsonDocument reply;
    reply["acknowledged"] = proofMetrics.acknowledged;
    reply["digest_mismatch"] = proofMetrics.digest_mismatch;
    reply["duplicate"] = proofMetrics.duplicate;
    reply["largest_free_block"] = proofMetrics.largest_free_block;
    reply["malformed"] = proofMetrics.malformed;
    reply["max_display_flush_us"] = proofMetrics.max_display_flush_us;
    reply["max_key_poll_gap_us"] = proofMetrics.max_key_poll_gap_us;
    reply["minimum_free_heap"] = proofMetrics.minimum_free_heap;
    reply["out_of_order"] = proofMetrics.out_of_order;
    reply["parser_high_water"] = proofMetrics.parser_high_water;
    reply["queue_high_water"] = proofMetrics.queue_high_water;
    reply["received"] = proofMetrics.received;
    reply["rejected"] = proofMetrics.rejected;
    reply["sent"] = proofMetrics.sent;
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
      delay(25);
      ESP.restart();
    }
    return;
  }
  sendError("unknown_type", "admitted frame is not a runtime request", admission.frame.sequence);
  completeAdmission();
}

void readFrames() {
  while (usbLink.available() > 0) {
    uint8_t byte = 0;
    if (usbLink.read(&byte, 1) != 1) break;
    if (byte == '\n') {
      if (frameOverflow) {
        protocolSession.accept(reinterpret_cast<const uint8_t *>(inputFrame), kMaxLineBytes + 1, admission);
      } else {
        inputFrame[frameLength] = '\n';
        protocolSession.accept(reinterpret_cast<const uint8_t *>(inputFrame), frameLength + 1, admission);
      }
      proofMetrics.recordReceived();
      dispatchAdmission(admission);
      frameLength = 0;
      frameOverflow = false;
      continue;
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

void reportAgentKey() {
  if (!agentProjection.committed() || !board.ready()) return;
  for (uint8_t key = 0; key < AgentProjection::kSlotCount; ++key) {
    if (!board.wasPressed(key)) continue;
    char actionId[32] = {};
    std::snprintf(actionId, sizeof(actionId), "device-%lu", static_cast<unsigned long>(micros()));
    JsonDocument intent;
    if (agentProjection.captureFocusIntent(key, actionId, intent.to<JsonObject>())) {
      agentProjection.renderFeedback(board, key);
      sendFrame("focus_intent", 0, intent.as<JsonObjectConst>());
    }
  }
}

void reportInput() {
  if (!board.ready() || armedInput == ArmedInput::None || activeStep.isEmpty()) return;
  if (armedInput == ArmedInput::Key) {
    if (board.wasPressed(expectedKey)) {
      reportKeyTransition(expectedKey);
      armedInput = ArmedInput::None;
    }
    return;
  }
  if (armedInput == ArmedInput::Encoder) {
    const int32_t delta = board.encoderDelta();
    if (delta > 0) {
      reportEncoderTransition("cw");
      armedInput = ArmedInput::None;
    } else if (delta < 0) {
      reportEncoderTransition("ccw");
      armedInput = ArmedInput::None;
    }
  } else if (armedInput == ArmedInput::EncoderClick && board.wasPressed(expectedKey)) {
    reportKeyTransition(expectedKey);
    armedInput = ArmedInput::None;
  }
}
}  // namespace

void setup() {
  usbLink.begin(kBaud, sizeof(inputFrame));
  physicalMap.loadVerified();
  board.begin(physicalMap);
  deviceId = opaqueId();
  bootId = freshBootId(deviceId);
  protocolSession.reset(bootId.c_str(), "");
  if (board.ready()) {
    board.setBrightness(80);
    render(BringupState::Wait, 0);
  }
  proofMetrics.sampleRuntime();
}

void loop() {
  const uint32_t now = micros();
  board.update();
  readFrames();
  if (lastKeyPollAt != 0) proofMetrics.observeKeyPollGap(now - lastKeyPollAt);
  lastKeyPollAt = now;
  agentProjection.tick(board, now);
  reportAgentKey();
  proofMetrics.sampleRuntime();
  delay(1);
}
