#include <Arduino.h>
#include <ArduinoJson.h>
#include <TKeyboardS3Pro.h>

namespace {
constexpr size_t kMaxLineBytes = 4096;  // includes the trailing LF
constexpr uint32_t kBaud = 115200;
char frame[kMaxLineBytes + 1];
size_t frameLength = 0;
bool frameOverflow = false;
bool probeArmed = false;
String activeStep;
uint32_t txSequence = 0;
String bootId;
String sessionId;

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

void drawStimulus(uint8_t panel) {
  // The official Pro abstraction selects one STM32-owned panel per draw call.
  auto &display = TKeyboardS3Pro.displayAt(panel - 1);
  display.fillScreen(TFT_BLACK);
  display.setTextColor(TFT_CYAN, TFT_BLACK);
  display.setTextSize(3);
  display.drawString("1", 56, 34);
  display.setTextSize(2);
  display.drawString("^", 58, 70);
  display.setTextSize(1);
  display.drawString("PRESS", 46, 104);
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
      !doc["session_id"].is<const char *>() || !doc["seq"].is<uint32_t>() || !doc["payload"].is<JsonObject>()) {
    sendError("invalid_envelope", "closed v1 envelope required", 0);
    return;
  }
  const char *type = doc["type"];
  uint32_t sequence = doc["seq"];
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
    uint8_t panel = payload["panel"];
    if (panel < 1 || panel > 4) {
      sendError("invalid_panel", "panel must be one through four", sequence);
      return;
    }
    activeStep = String(payload["step_id"].as<const char *>());
    drawStimulus(panel);
    JsonDocument reply;
    reply["accepted"] = true;
    reply["step_id"] = activeStep;
    sendFrame("probe_ack", sequence, reply.as<JsonObjectConst>());
    probeArmed = true;
    return;
  }
  sendError("unknown_type", "only hello and probe are accepted by tracer", sequence);
}

void readFrames() {
  while (Serial.available()) {
    char byte = static_cast<char>(Serial.read());
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

void reportKeyTransition() {
  if (!probeArmed || activeStep.isEmpty()) {
    return;
  }
  for (uint8_t key = 0; key < 5; ++key) {
    if (TKeyboardS3Pro.key(key).wasPressed()) {
      JsonDocument event;
      event["kind"] = "key_transition";
      event["step_id"] = activeStep;
      event["key"] = key;
      sendFrame("event", 0, event.as<JsonObjectConst>());
      probeArmed = false;
      return;
    }
  }
}
}  // namespace

void setup() {
  Serial.begin(kBaud);
  TKeyboardS3Pro.begin();
  TKeyboardS3Pro.setBrightness(80);
  TKeyboardS3Pro.fillAllScreens(TFT_BLACK);
  bootId = opaqueId() + "-" + String(millis());
  sessionId = "unbound";
}

void loop() {
  TKeyboardS3Pro.update();
  readFrames();
  reportKeyTransition();
  delay(1);
}
