#pragma once
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
#include <vector>

inline uint32_t g_sync_draw_count = 0;

// Bounded call log proving compose-then-flush ordering: every sprite draw op
// appends an entry; every pushSprite appends "push:<panel>".  Tests assert
// that each panel's draws precede its single push and that flush order is
// sequential.
inline std::vector<std::string> g_render_log;

class Display {
 public:
  void fillScreen(uint16_t) {}
  void setTextColor(uint16_t, uint16_t) {}
  void setTextSize(uint8_t) {}
  void drawString(const char*, int32_t, int32_t) {}
  void drawRect(int32_t, int32_t, int32_t, int32_t, uint16_t) {}
  void drawLine(int32_t, int32_t, int32_t, int32_t, uint16_t) {}
  void fillCircle(int32_t, int32_t, int32_t, uint16_t) {}
  void drawCircle(int32_t, int32_t, int32_t, uint16_t) {}
};

// Identity of a display for push logging; defined by the test harness.
int displayIndexOf(Display* display);

class LGFX_Sprite {
 public:
  void setPsram(bool) {}
  void setColorDepth(uint8_t) {}
  void* createSprite(int32_t, int32_t) { return this; }
  uint16_t* getBuffer() { return pixels_; }
  const uint16_t* getBuffer() const { return pixels_; }
  void fillScreen(uint16_t) { g_render_log.push_back("fillScreen"); }
  void setTextColor(uint16_t, uint16_t) {}
  void setTextSize(uint8_t) {}
  void drawString(const char* value, int32_t x, int32_t y) {
    if (value != nullptr && (std::strcmp(value, "SYNC") == 0 || std::strcmp(value, "UPDATING") == 0)) {
      ++g_sync_draw_count;
    }
    const char* text = value != nullptr ? value : "";
    g_render_log.push_back(std::string("text:") + text);
    g_render_log.push_back(std::string("textAt:") + text + ":" +
                           std::to_string(x) + ":" + std::to_string(y));
  }
  void drawRect(int32_t x, int32_t y, int32_t w, int32_t h, uint16_t) {
    g_render_log.push_back("drawRect:" + std::to_string(x) + ":" + std::to_string(y) + ":" +
                           std::to_string(w) + ":" + std::to_string(h));
  }
  void fillRect(int32_t x, int32_t y, int32_t w, int32_t h, uint16_t) {
    g_render_log.push_back("fillRect:" + std::to_string(x) + ":" + std::to_string(y) + ":" +
                           std::to_string(w) + ":" + std::to_string(h));
  }
  void drawLine(int32_t x0, int32_t y0, int32_t x1, int32_t y1, uint16_t) {
    g_render_log.push_back("drawLine:" + std::to_string(x0) + ":" + std::to_string(y0) + ":" +
                           std::to_string(x1) + ":" + std::to_string(y1));
  }
  void fillCircle(int32_t x, int32_t y, int32_t r, uint16_t) {
    g_render_log.push_back("fillCircle:" + std::to_string(x) + ":" + std::to_string(y) + ":" +
                           std::to_string(r));
  }
  void drawCircle(int32_t x, int32_t y, int32_t r, uint16_t) {
    g_render_log.push_back("drawCircle:" + std::to_string(x) + ":" + std::to_string(y) + ":" +
                           std::to_string(r));
  }
  void fillTriangle(int32_t x0, int32_t y0, int32_t x1, int32_t y1,
                    int32_t x2, int32_t y2, uint16_t) {
    g_render_log.push_back("fillTriangle:" + std::to_string(x0) + ":" + std::to_string(y0) + ":" +
                           std::to_string(x1) + ":" + std::to_string(y1) + ":" +
                           std::to_string(x2) + ":" + std::to_string(y2));
  }
  void drawPixel(int32_t, int32_t, uint16_t) {}
  void pushSprite(Display* display, int32_t, int32_t) {
    g_render_log.push_back("push:" + std::to_string(displayIndexOf(display)));
  }
 private:
  uint16_t pixels_[128 * 128]{};
};

namespace button { class ButtonSense {}; }
class TKeyboardS3ProClass {};
static TKeyboardS3ProClass TKeyboardS3Pro;

// In-memory Preferences stub matching the subset of the ESP32 Arduino API the
// firmware uses.  g_nvs survives across Preferences instances like real NVS.
inline std::map<std::string, uint32_t> g_nvs;
inline uint32_t g_nvs_write_count = 0;
inline int32_t g_nvs_fail_on_write = -1;
inline uint32_t g_nvs_write_attempt = 0;

class Preferences {
 public:
  bool begin(const char*, bool read_only = false) {
    read_only_ = read_only;
    open_ = true;
    return true;
  }
  void end() { open_ = false; }
  bool isKey(const char* key) { return open_ && g_nvs.count(key) != 0; }
  uint32_t getUInt(const char* key, uint32_t fallback = 0) {
    if (!open_ || g_nvs.count(key) == 0) return fallback;
    return g_nvs[key];
  }
  uint8_t getUChar(const char* key, uint8_t fallback = 0) {
    return static_cast<uint8_t>(getUInt(key, fallback));
  }
  size_t putUInt(const char* key, uint32_t value) {
    if (!open_ || read_only_) return 0;
    if (g_nvs_fail_on_write >= 0 &&
        g_nvs_write_attempt++ == static_cast<uint32_t>(g_nvs_fail_on_write)) {
      return 0;
    }
    g_nvs[key] = value;
    ++g_nvs_write_count;
    return sizeof(uint32_t);
  }
  size_t putUChar(const char* key, uint8_t value) {
    if (!open_ || read_only_) return 0;
    if (g_nvs_fail_on_write >= 0 &&
        g_nvs_write_attempt++ == static_cast<uint32_t>(g_nvs_fail_on_write)) {
      return 0;
    }
    g_nvs[key] = value;
    ++g_nvs_write_count;
    return sizeof(uint8_t);
  }
  bool remove(const char* key) {
    if (!open_ || read_only_) return false;
    g_nvs.erase(key);
    ++g_nvs_write_count;
    return true;
  }


 private:
  bool open_ = false;
  bool read_only_ = false;
};
