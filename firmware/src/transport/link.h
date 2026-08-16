#pragma once

#include <stddef.h>
#include <stdint.h>

// Byte/event boundary only.  Protocol parsing, sequencing, digest checks, and
// qualification policy remain above this interface so another adapter can use
// the same session contract without a second interpretation.
class Link {
 public:
  virtual ~Link() = default;
  virtual void begin(uint32_t baud) = 0;
  virtual int available() const = 0;
  virtual size_t read(uint8_t *destination, size_t capacity) = 0;
  virtual size_t write(const uint8_t *source, size_t length) = 0;
  virtual bool connected() const = 0;
  virtual void close() = 0;
};

class UsbCdcLink final : public Link {
 public:
  void begin(uint32_t baud) override;
  int available() const override;
  size_t read(uint8_t *destination, size_t capacity) override;
  size_t write(const uint8_t *source, size_t length) override;
  bool connected() const override;
  void close() override;
};
