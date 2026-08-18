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
  void fillScreen(uint16_t) { g_render_log.push_back("fillScreen"); }
  void setTextColor(uint16_t, uint16_t) {}
  void setTextSize(uint8_t) {}
  void drawString(const char* value, int32_t, int32_t) {
    if (value != nullptr && (std::strcmp(value, "SYNC") == 0 || std::strcmp(value, "UPDATING") == 0)) {
      ++g_sync_draw_count;
    }
    g_render_log.push_back(std::string("text:") + (value != nullptr ? value : ""));
  }
  void drawRect(int32_t, int32_t, int32_t, int32_t, uint16_t) { g_render_log.push_back("drawRect"); }
  void fillRect(int32_t, int32_t, int32_t, int32_t, uint16_t) { g_render_log.push_back("fillRect"); }
  void drawLine(int32_t, int32_t, int32_t, int32_t, uint16_t) { g_render_log.push_back("drawLine"); }
  void fillCircle(int32_t, int32_t, int32_t, uint16_t) { g_render_log.push_back("fillCircle"); }
  void drawCircle(int32_t, int32_t, int32_t, uint16_t) { g_render_log.push_back("drawCircle"); }
  void pushSprite(Display* display, int32_t, int32_t) {
    g_render_log.push_back("push:" + std::to_string(displayIndexOf(display)));
  }
};

namespace button { class ButtonSense {}; }
class TKeyboardS3ProClass {};
static TKeyboardS3ProClass TKeyboardS3Pro;

// In-memory Preferences stub matching the subset of the ESP32 Arduino API the
// firmware uses.  g_nvs survives across Preferences instances like real NVS.
inline std::map<std::string, uint32_t> g_nvs;
inline uint32_t g_nvs_write_count = 0;

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
    g_nvs[key] = value;
    ++g_nvs_write_count;
    return sizeof(uint32_t);
  }
  size_t putUChar(const char* key, uint8_t value) {
    if (!open_ || read_only_) return 0;
    g_nvs[key] = value;
    ++g_nvs_write_count;
    return sizeof(uint8_t);
  }

 private:
  bool open_ = false;
  bool read_only_ = false;
};
