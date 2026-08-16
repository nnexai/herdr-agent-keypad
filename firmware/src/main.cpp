#include <Arduino.h>
#include <ArduinoJson.h>
#include <TKeyboardS3Pro.h>

#include <string.h>

#include "board/board_adapter.h"
#include "board/physical_map.h"
#include "ui/bringup_renderer.h"
#include "transport/link.h"
#include "metrics/proof_metrics.h"

namespace {
constexpr size_t kMaxLineBytes = 4096;  // includes the trailing LF
constexpr uint32_t kBaud = 115200;
char frame[kMaxLineBytes + 1];
char payloadScratch[kMaxLineBytes + 1];
size_t frameLength = 0;
bool frameOverflow = false;
uint32_t txSequence = 0;
uint32_t lastKeyPollAt = 0;
String bootId;
String sessionId;
String deviceId;
BoardAdapter board;
BringupRenderer renderer;
PhysicalMap physicalMap;
UsbCdcLink usbLink;
ProofMetrics proofMetrics;

// Input arming is deliberately separate from the physical map.  Until a user
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

uint64_t payloadDigest(const char *payload, size_t length) {
  uint64_t digest = 0xcbf29ce484222325ULL;
  for (size_t index = 0; index < length; ++index) {
    digest ^= static_cast<uint8_t>(payload[index]);
    digest *= 0x100000001b3ULL;
  }
  return digest;
}

void formatDigest(uint64_t digest, char output[17]) {
  snprintf(output, 17, "%016llx", static_cast<unsigned long long>(digest));
}

void sendFrame(const char *type, uint32_t replyTo, JsonObjectConst payload, bool countMetrics = true) {
  const size_t payloadLength = serializeJson(payload, payloadScratch, sizeof(payloadScratch) - 1);
  if (payloadLength + 1 > kMaxLineBytes) return;
  char digest[17];
  formatDigest(payloadDigest(payloadScratch, payloadLength), digest);
  JsonDocument doc;
  doc["v"] = 1;
  doc["type"] = type;
  doc["boot_id"] = bootId;
  doc["session_id"] = sessionId;
  doc["seq"] = ++txSequence;
  if (replyTo == 0) {
    doc["reply_to"] = nullptr;
  } else {
    doc["reply_to"] = replyTo;
  }
  doc["digest"] = digest;
  doc["payload"] = payload;
  const size_t encoded = serializeJson(doc, frame, sizeof(frame) - 1);
  if (encoded + 1 > kMaxLineBytes) return;
  frame[encoded] = '\n';
  if (usbLink.write(reinterpret_cast<const uint8_t *>(frame), encoded + 1) == encoded + 1) {
    if (countMetrics) {
      proofMetrics.recordSent();
      if (strcmp(type, "hello_ack") == 0 || strcmp(type, "probe_ack") == 0 ||
          strcmp(type, "metrics_ack") == 0) {
        proofMetrics.recordAcknowledged();
      }
    }
  }
}

void sendError(const char *code, const char *detail, uint32_t replyTo) {
  JsonDocument payload;
  payload["code"] = code;
  payload["detail"] = detail;
  if (strcmp(code, "invalid_json") == 0 || strcmp(code, "line_too_long") == 0) {
    proofMetrics.recordMalformed();
  } else if (strcmp(code, "digest_mismatch") == 0) {
    proofMetrics.recordDigestMismatch();
  } else {
    proofMetrics.recordRejected();
  }
  sendFrame("error", replyTo, payload.as<JsonObjectConst>());
}

void render(BringupState state, uint8_t panel, uint8_t brightness = 0,
            const char *challenge = nullptr) {
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
  Invalid = 0,
  Map,
  Key,
  EncoderCw,
  EncoderCcw,
  EncoderClick,
  Brightness,
  Led,
  Pair,
  Pass,
  Fail,
  LinkLost,
  Wait,
  Reboot,
};

bool parseSingleIndex(const char *text, const char *prefix, uint8_t maximum, uint8_t &index) {
  const size_t prefixLength = strlen(prefix);
  if (strncmp(text, prefix, prefixLength) != 0) {
    return false;
  }
  const char *digits = text + prefixLength;
  if (digits[0] < '0' || digits[0] > '9') {
    return false;
  }
  uint16_t parsed = static_cast<uint16_t>(digits[0] - '0');
  if (digits[1] != '\0') {
    if (digits[1] < '0' || digits[1] > '9' || digits[2] != '\0') {
      return false;
    }
    parsed = static_cast<uint16_t>(parsed * 10U + (digits[1] - '0'));
  }
  if (parsed > maximum) {
    return false;
  }
  index = static_cast<uint8_t>(parsed);
  return true;
}

StimulusKind classifyStimulus(const char *stimulus, uint8_t &value) {
  value = 0;
  // D-01 tracer spelling remains accepted for the walking skeleton.
  if (strcmp(stimulus, "1 ^ CYAN") == 0) {
    value = 1;
    return StimulusKind::Map;
  }
  if (parseSingleIndex(stimulus, "PANEL-", 4, value) && value >= 1) {
    return StimulusKind::Map;
  }
  if (parseSingleIndex(stimulus, "KEY-", 4, value) && value >= 1) {
    return StimulusKind::Key;
  }
  if (strcmp(stimulus, "ENC-CW") == 0) {
    return StimulusKind::EncoderCw;
  }
  if (strcmp(stimulus, "ENC-CCW") == 0) {
    return StimulusKind::EncoderCcw;
  }
  if (strcmp(stimulus, "ENC-CLICK") == 0) {
    return StimulusKind::EncoderClick;
  }
  if (strcmp(stimulus, "BRIGHTNESS-LOW") == 0) {
    value = 10;
    return StimulusKind::Brightness;
  }
  if (strcmp(stimulus, "BRIGHTNESS-MEDIUM") == 0) {
    value = 50;
    return StimulusKind::Brightness;
  }
  if (strcmp(stimulus, "BRIGHTNESS-HIGH") == 0) {
    value = 100;
    return StimulusKind::Brightness;
  }
  if (parseSingleIndex(stimulus, "LED-", 13, value)) {
    return StimulusKind::Led;
  }
  if (strncmp(stimulus, "PAIR-", 5) == 0 && stimulus[5] != '\0') {
    return StimulusKind::Pair;
  }
  if (strcmp(stimulus, "PASS") == 0) {
    return StimulusKind::Pass;
  }
  if (strcmp(stimulus, "FAIL") == 0) {
    return StimulusKind::Fail;
  }
  if (strcmp(stimulus, "LINK-LOST") == 0) {
    return StimulusKind::LinkLost;
  }
  if (strcmp(stimulus, "WAIT") == 0) {
    return StimulusKind::Wait;
  }
  if (strcmp(stimulus, "REBOOT") == 0) {
    return StimulusKind::Reboot;
  }
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
      // Operator KEY-1..KEY-4 map to raw library key indices 0..3.
      expectedKey = static_cast<uint8_t>(value - 1);
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
      // The encoder click is the fifth raw library input (key index 4).
      // It is observed only; never interpret it as BOOT0/reset.
      expectedKey = 4;
      armedInput = ArmedInput::EncoderClick;
      render(BringupState::Click, panel);
      return true;
    case StimulusKind::Brightness:
      board.setBrightness(value);
      render(BringupState::Brightness, panel, value);
      return true;
    case StimulusKind::Led:
      // LED positions remain unapproved.  This paints exactly one library LED
      // without claiming which physical position it illuminates.
      board.setLeds(0, 100, 32, static_cast<uint16_t>(1U << value));
      render(BringupState::Map, panel);
      return true;
    case StimulusKind::Pair:
      render(BringupState::Pair, panel, 0, stimulus + 5);
      return true;
    case StimulusKind::Pass:
      render(BringupState::Pass, panel);
      return true;
    case StimulusKind::Fail:
      render(BringupState::Fail, panel);
      return true;
    case StimulusKind::LinkLost:
      render(BringupState::LinkLost, panel);
      return true;
    case StimulusKind::Wait:
      render(BringupState::Wait, 0);
      return true;
    case StimulusKind::Reboot:
      render(BringupState::Pass, panel);
      return true;
    case StimulusKind::Invalid:
    default:
      return false;
  }
}

void handleFrame(char *line, size_t length) {
  if (length == 0 || length + 1 > kMaxLineBytes) {
    sendError("line_too_long", "encoded line exceeds 4096 bytes including LF", 0);
    return;
  }
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, line, length);
  if (error) {
    sendError("invalid_json", "frame rejected before dispatch", 0);
    return;
  }
  if (doc["v"] != 1 || !doc["type"].is<const char *>() || !doc["boot_id"].is<const char *>() ||
      !doc["session_id"].is<const char *>() || !doc["seq"].is<uint32_t>() ||
      !doc["digest"].is<const char *>() || !doc["payload"].is<JsonObject>()) {
    sendError("invalid_envelope", "closed v1 envelope required", 0);
    return;
  }
  JsonObject payload = doc["payload"].as<JsonObject>();
  const size_t payloadLength = serializeJson(payload, payloadScratch, sizeof(payloadScratch) - 1);
  char calculatedDigest[17];
  formatDigest(payloadDigest(payloadScratch, payloadLength), calculatedDigest);
  if (strcmp(doc["digest"].as<const char *>(), calculatedDigest) != 0) {
    sendError("digest_mismatch", "payload digest does not match canonical payload", 0);
    return;
  }
  const char *type = doc["type"];
  const uint32_t sequence = doc["seq"];
  if (strcmp(type, "hello") == 0) {
    sessionId = String(doc["session_id"].as<const char *>());
    JsonDocument reply;
    reply["accepted"] = true;
    reply["device_id"] = deviceId;
    reply["firmware"] = "phase1-bringup";
    reply["protocol"] = 1;
    sendFrame("hello_ack", sequence, reply.as<JsonObjectConst>());
    return;
  }
  if (strcmp(type, "metrics") == 0) {
    const char *request = payload["request"].as<const char *>();
    if (request == nullptr || (strcmp(request, "proof") != 0 && strcmp(request, "reset") != 0)) {
      sendError("invalid_metrics", "metrics request must be proof or reset", sequence);
      return;
    }
    if (strcmp(request, "reset") == 0) {
      JsonDocument reply;
      reply["acknowledged"] = 0;
      reply["digest_mismatch"] = 0;
      reply["duplicate"] = 0;
      reply["largest_free_block"] = 0;
      reply["malformed"] = 0;
      reply["max_display_flush_us"] = proofMetrics.max_display_flush_us;
      reply["max_key_poll_gap_us"] = proofMetrics.max_key_poll_gap_us;
      reply["minimum_free_heap"] = proofMetrics.minimum_free_heap;
      reply["out_of_order"] = 0;
      reply["parser_high_water"] = 0;
      reply["queue_high_water"] = 0;
      reply["received"] = 0;
      reply["rejected"] = 0;
      reply["sent"] = 0;
      reply["watchdog_reset"] = 0;
      sendFrame("metrics_ack", sequence, reply.as<JsonObjectConst>(), false);
      proofMetrics.resetCounters();
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
    sendFrame("metrics_ack", sequence, reply.as<JsonObjectConst>(), false);
    return;
  }
  if (strcmp(type, "probe") == 0) {
    if (!payload["step_id"].is<const char *>() || !payload["panel"].is<uint8_t>() ||
        !payload["stimulus"].is<const char *>()) {
      sendError("invalid_probe", "step_id, panel, and stimulus are required", sequence);
      return;
    }
    const uint8_t requestedPanel = payload["panel"];
    if (requestedPanel < 1 || requestedPanel > 4) {
      sendError("invalid_panel", "panel must be one through four", sequence);
      return;
    }
    activeStep = String(payload["step_id"].as<const char *>());
    uint8_t stimulatedPanel = requestedPanel;
    if (!applyStimulus(payload["stimulus"].as<const char *>(), stimulatedPanel)) {
      sendError("invalid_stimulus", "bounded bring-up stimulus is not recognized", sequence);
      return;
    }
    JsonDocument reply;
    reply["accepted"] = true;
    reply["step_id"] = activeStep;
    sendFrame("probe_ack", sequence, reply.as<JsonObjectConst>());
    if (strcmp(payload["stimulus"].as<const char *>(), "REBOOT") == 0) {
      delay(25);
      ESP.restart();
    }
    return;
  }
  sendError("unknown_type", "only hello, probe, and metrics are accepted by tracer", sequence);
}

void readFrames() {
  while (usbLink.available() > 0) {
    uint8_t byte = 0;
    if (usbLink.read(&byte, 1) != 1) break;
    if (byte == '\n') {
      proofMetrics.recordReceived();
      if (!frameOverflow) {
        frame[frameLength] = '\0';
        handleFrame(frame, frameLength);
      } else {
        sendError("line_too_long", "encoded line exceeds 4096 bytes including LF", 0);
      }
      frameLength = 0;
      frameOverflow = false;
      continue;
    }
    if (frameOverflow) continue;
    if (frameLength + 1 >= sizeof(frame)) {
      frameOverflow = true;
      continue;
    }
    frame[frameLength++] = static_cast<char>(byte);
    proofMetrics.observeParser(frameLength);
  }
  proofMetrics.observeQueue(static_cast<size_t>(usbLink.available()));
}

void reportKeyTransition(uint8_t rawKey) {
  JsonDocument event;
  event["key"] = rawKey;
  event["kind"] = "key_transition";
  event["step_id"] = activeStep;
  sendFrame("event", 0, event.as<JsonObjectConst>());
}

void reportInput() {
  if (armedInput == ArmedInput::None || activeStep.isEmpty()) {
    return;
  }
  if (armedInput == ArmedInput::Key) {
    if (board.key(expectedKey).wasPressed()) {
      reportKeyTransition(expectedKey);
      armedInput = ArmedInput::None;
    }
    return;
  }

  // Encoder direction is intentionally only detected locally.  The encoder
  // click is a validated transition from raw library key index 4; it is
  // observed as input only and can never invoke BOOT0/reset.
  if (armedInput == ArmedInput::Encoder && board.encoderDelta() != 0) {
    armedInput = ArmedInput::None;
  } else if (armedInput == ArmedInput::EncoderClick && board.key(4).wasPressed()) {
    reportKeyTransition(4);
    armedInput = ArmedInput::None;
  }
}
}  // namespace

void setup() {
  usbLink.begin(kBaud);
  const bool boardReady = board.begin();
  board.setBrightness(80);
  board.clearDisplays(TFT_BLACK);
  deviceId = opaqueId();
  bootId = deviceId + "-" + String(millis());
  proofMetrics.sampleRuntime();
  render(boardReady ? BringupState::Wait : BringupState::LinkLost, 0);
}

void loop() {
  board.update();
  readFrames();
  const uint32_t now = micros();
  if (lastKeyPollAt != 0) proofMetrics.observeKeyPollGap(now - lastKeyPollAt);
  lastKeyPollAt = now;
  reportInput();
  proofMetrics.sampleRuntime();
  delay(1);
}
