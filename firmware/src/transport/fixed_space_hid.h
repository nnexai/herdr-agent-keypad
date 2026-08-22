#pragma once

// Phase 03.2's complete HID authority boundary. Callers cannot supply a
// keycode, report, string, macro, provider, or command.
class FixedSpaceHid final {
 public:
  bool spaceDown();
  bool releaseAll();
  bool ready();
};
