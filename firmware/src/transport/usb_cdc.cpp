#include "link.h"

#include <Arduino.h>

void UsbCdcLink::begin(uint32_t baud) { Serial.begin(baud); }

int UsbCdcLink::available() const { return Serial.available(); }

size_t UsbCdcLink::read(uint8_t *destination, size_t capacity) {
  if (destination == nullptr || capacity == 0) return 0;
  size_t count = 0;
  while (count < capacity && Serial.available() > 0) {
    const int value = Serial.read();
    if (value < 0) break;
    destination[count++] = static_cast<uint8_t>(value);
  }
  return count;
}

size_t UsbCdcLink::write(const uint8_t *source, size_t length) {
  if (source == nullptr || length == 0 || !connected()) return 0;
  size_t written = 0;
  while (written < length) {
    const size_t count = Serial.write(source + written, length - written);
    if (count == 0 || count > length - written) {
      close();
      return 0;
    }
    written += count;
  }
  return written;
}

bool UsbCdcLink::connected() const { return static_cast<bool>(Serial); }

void UsbCdcLink::close() { Serial.flush(); }
