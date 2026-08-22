#include <Arduino.h>

#if defined(ARDUINO_USB_MODE) && ARDUINO_USB_MODE == 0

#include <ArduinoJson.h>
#include <TKeyboardS3Pro.h>
#include <USB.h>

#include "transport/fixed_space_hid.h"

namespace {

constexpr size_t kMaxLineBytes = 384;
constexpr uint8_t kAgentKeyCount = 3;

FixedSpaceHid fixed_space;
char input_line[kMaxLineBytes + 1] = {};
size_t input_length = 0;
bool discarding_line = false;
bool space_active = false;
int8_t space_owner = -1;
bool usb_started = false;
bool usb_suspended = false;
bool requires_clean_release = true;

void writeEvent(const char* event, bool ok) {
  JsonDocument document;
  document["event"] = event;
  document["ok"] = ok;
  document["at_us"] = micros();
  serializeJson(document, USBSerial);
  USBSerial.write('\n');
}

void writeKeyEvent(uint8_t slot, const char* state) {
  JsonDocument document;
  document["event"] = "key";
  document["slot"] = slot;
  document["state"] = state;
  document["at_us"] = micros();
  serializeJson(document, USBSerial);
  USBSerial.write('\n');
}

void writeStatus(const char* request_id) {
  JsonDocument document;
  document["event"] = "status";
  if (request_id != nullptr) document["id"] = request_id;
  document["usb_started"] = usb_started;
  document["usb_suspended"] = usb_suspended;
  document["hid_ready"] = fixed_space.ready();
  document["space_active"] = space_active;
  document["space_owner"] = space_owner;
  document["requires_clean_release"] = requires_clean_release;
  document["at_us"] = micros();
  serializeJson(document, USBSerial);
  USBSerial.write('\n');
}

bool releaseSpace(const char* event) {
  const bool completed = fixed_space.releaseAll();
  if (completed) {
    space_active = false;
    space_owner = -1;
  }
  writeEvent(event, completed);
  return completed;
}

void lifecycleRelease(const char* event) {
  // Lifecycle authority clears before the best-effort empty report. A missing
  // bus must never leave firmware believing a key is still owned.
  space_active = false;
  space_owner = -1;
  writeEvent(event, fixed_space.releaseAll());
}

void handleCommand(char* line) {
  JsonDocument request;
  const DeserializationError error = deserializeJson(request, line);
  if (error || !request["op"].is<const char*>()) {
    writeEvent("reject", false);
    return;
  }

  const char* operation = request["op"];
  const char* request_id = request["id"].is<const char*>()
                               ? request["id"].as<const char*>()
                               : nullptr;

  if (strcmp(operation, "echo") == 0) {
    JsonDocument response;
    response["event"] = "echo";
    if (request_id != nullptr) response["id"] = request_id;
    response["at_us"] = micros();
    serializeJson(response, USBSerial);
    USBSerial.write('\n');
    return;
  }

  if (strcmp(operation, "status") == 0) {
    writeStatus(request_id);
    return;
  }

  if (strcmp(operation, "space_down") == 0) {
    if (!request["slot"].is<uint8_t>()) {
      writeEvent("space_down", false);
      return;
    }
    const uint8_t slot = request["slot"].as<uint8_t>();
    const bool permitted = slot < kAgentKeyCount && !space_active &&
                           !requires_clean_release &&
                           TKeyboardS3Pro.key(slot).isPressed() &&
                           fixed_space.ready() && usb_started && !usb_suspended;
    const bool completed = permitted && fixed_space.spaceDown();
    if (completed) {
      space_active = true;
      space_owner = static_cast<int8_t>(slot);
    }
    writeEvent("space_down", completed);
    return;
  }

  if (strcmp(operation, "release") == 0) {
    releaseSpace("release");
    return;
  }

  writeEvent("reject", false);
}

void pollCdc() {
  while (USBSerial.available() > 0) {
    const int value = USBSerial.read();
    if (value < 0) return;
    const char byte = static_cast<char>(value);

    if (discarding_line) {
      if (byte == '\n') {
        discarding_line = false;
        writeEvent("line_too_long", false);
      }
      continue;
    }

    if (byte == '\n') {
      input_line[input_length] = '\0';
      if (input_length > 0) handleCommand(input_line);
      input_length = 0;
      continue;
    }
    if (byte == '\r') continue;

    if (input_length == kMaxLineBytes) {
      input_length = 0;
      discarding_line = true;
      continue;
    }
    input_line[input_length++] = byte;
  }
}

void pollKeys() {
  TKeyboardS3Pro.update();
  bool any_down = false;
  for (uint8_t slot = 0; slot < kAgentKeyCount; ++slot) {
    auto& key = TKeyboardS3Pro.key(slot);
    any_down = any_down || key.isPressed();
    if (key.wasPressed()) writeKeyEvent(slot, "down");
    if (key.wasReleased()) {
      writeKeyEvent(slot, "up");
      if (space_active && space_owner == static_cast<int8_t>(slot)) {
        releaseSpace("owner_release");
      }
    }
  }
  if (!any_down) requires_clean_release = false;
}

void onUsbEvent(void*, esp_event_base_t event_base, int32_t event_id, void*) {
  if (event_base != ARDUINO_USB_EVENTS) return;
  switch (event_id) {
    case ARDUINO_USB_STARTED_EVENT:
      usb_started = true;
      usb_suspended = false;
      space_active = false;
      space_owner = -1;
      requires_clean_release = true;
      break;
    case ARDUINO_USB_STOPPED_EVENT:
      usb_started = false;
      usb_suspended = false;
      space_active = false;
      space_owner = -1;
      requires_clean_release = true;
      break;
    case ARDUINO_USB_SUSPEND_EVENT:
      usb_suspended = true;
      requires_clean_release = true;
      lifecycleRelease("usb_suspend");
      break;
    case ARDUINO_USB_RESUME_EVENT:
      usb_suspended = false;
      requires_clean_release = true;
      lifecycleRelease("usb_resume");
      break;
    default:
      break;
  }
}

}  // namespace

void setup() {
  BoardConfig board_config;
  board_config.enableDisplay = false;
  board_config.enableEncoder = false;
  TKeyboardS3Pro.begin(board_config);

  USB.onEvent(onUsbEvent);
  USBSerial.begin(115200);
  (void)fixed_space.ready();
  USB.begin();
}

void loop() {
  pollKeys();
  pollCdc();

  // A failed first release attempt remains fail-safe and is retried while the
  // physical owner is up. A lifecycle boundary cannot resurrect a held key.
  if (space_active && space_owner >= 0 &&
      !TKeyboardS3Pro.key(static_cast<uint8_t>(space_owner)).isPressed()) {
    releaseSpace("owner_release_retry");
  }
  delay(1);
}

#endif
