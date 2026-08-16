#include <Arduino.h>
#include <ArduinoJson.h>
#include <TKeyboardS3Pro.h>

#include <string.h>

#include "board/board_adapter.h"
#include "board/physical_map.h"
#include "ui/bringup_renderer.h"

namespace {
constexpr size_t kMaxLineBytes = 4096;  // includes the trailing LF
constexpr uint32_t kBaud = 115200;
char frame[kMaxLineBytes + 1];
size_t frameLength = 0;
bool frameOverflow = false;
uint32_t txSequence = 0;
String bootId;
String sessionId;
BoardAdapter board;
BringupRenderer renderer;
PhysicalMap physicalMap;

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

void sendFrame(const char *type, uint32_t replyTo, JsonObjectConst payload) {
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
  doc["payload"] = payload;
  size_t encoded = measureJson(doc) + 1;
  if (encoded > kMaxLineBytes) {
    return;
  }
  serializeJson(doc, Serial);
  Serial.write('\n');
}

void sendError(const char *code, const char *detail, uint32_t replyTo) {
  JsonDocument payload;
  payload["code"] = code;
  payload["detail"] = detail;
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
  renderer.render(board, request);
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
  if (parseSingleIndex(stimulus, "KEY-", 4, value)) {
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
  if (parseSingleIndex(stimulus, "LED-", 9, value)) {
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
      expectedKey = value;
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
      !doc["payload"].is<JsonObject>()) {
    sendError("invalid_envelope", "closed v1 envelope required", 0);
    return;
  }
  const char *type = doc["type"];
  const uint32_t sequence = doc["seq"];
  JsonObject payload = doc["payload"].as<JsonObject>();
  if (strcmp(type, "hello") == 0) {
    sessionId = String(doc["session_id"].as<const char *>());
    JsonDocument reply;
    reply["accepted"] = true;
    reply["protocol"] = 1;
    sendFrame("hello_ack", sequence, reply.as<JsonObjectConst>());
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
  sendError("unknown_type", "only hello and probe are accepted by tracer", sequence);
}

void readFrames() {
  while (Serial.available()) {
    const char byte = static_cast<char>(Serial.read());
    if (byte == '\n') {
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
    if (frameOverflow) {
      continue;
    }
    if (frameLength + 1 >= sizeof(frame)) {
      frameOverflow = true;
      continue;
    }
    frame[frameLength++] = byte;
  }
}

void reportInput() {
  if (armedInput == ArmedInput::None || activeStep.isEmpty()) {
    return;
  }
  if (armedInput == ArmedInput::Key) {
    for (uint8_t key = 0; key < 5; ++key) {
      if (board.key(key).wasPressed()) {
        JsonDocument event;
        event["kind"] = "key_transition";
        event["step_id"] = activeStep;
        event["key"] = key;
        sendFrame("event", 0, event.as<JsonObjectConst>());
        armedInput = ArmedInput::None;
        return;
      }
    }
    return;
  }

  // Encoder direction and click are deliberately only detected locally.  The
  // v1 tracer schema has no encoder event type, and fabricating a key index
  // would turn machine acknowledgement into an unapproved physical map.
  if (armedInput == ArmedInput::Encoder && board.encoderDelta() != 0) {
    armedInput = ArmedInput::None;
  } else if (armedInput == ArmedInput::EncoderClick) {
    for (uint8_t key = 0; key < 5; ++key) {
      if (board.key(key).wasPressed()) {
        armedInput = ArmedInput::None;
        return;
      }
    }
  }
}
}  // namespace

void setup() {
  Serial.begin(kBaud);
  const bool boardReady = board.begin();
  board.setBrightness(80);
  board.clearDisplays(TFT_BLACK);
  bootId = opaqueId() + "-" + String(millis());
  sessionId = "unbound";
  render(boardReady ? BringupState::Wait : BringupState::LinkLost, 0);
}

void loop() {
  board.update();
  readFrames();
  reportInput();
  delay(1);
}
