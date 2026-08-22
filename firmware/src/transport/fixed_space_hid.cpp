#include "fixed_space_hid.h"

#if defined(ARDUINO_USB_MODE) && ARDUINO_USB_MODE == 0

#include <USBHID.h>
#include <USBHIDKeyboard.h>

#include "metrics/hid_reset_journal.h"

namespace {

// Construction registers exactly the bundled standard keyboard descriptor.
// USBHID's implementation is process-global, so this second handle can use the
// same registered report ID while preserving SendReport's completion result.
USBHIDKeyboard descriptor_owner;
USBHID report_transport(HID_ITF_PROTOCOL_KEYBOARD);
bool begun = false;

void ensureBegun() {
  if (begun) return;
  descriptor_owner.begin();
  begun = true;
}

bool sendFixedReport(uint8_t keycode) {
  ensureBegun();
  HidResetJournal& journal = hidResetJournal();
  journal.beginReport(keycode == HID_KEY_SPACE ? HidReportKind::SpaceDown
                                               : HidReportKind::Empty);
  // Do not enqueue a report until the TinyUSB endpoint is mounted. SendReport
  // remains the completion boundary and returns false for transfer failures.
  if (!report_transport.ready()) {
    journal.completeReport(false);
    return false;
  }
  hid_keyboard_report_t report = {};
  report.keycode[0] = keycode;
  const bool completed = report_transport.SendReport(
      HID_REPORT_ID_KEYBOARD, &report, sizeof(report));
  journal.completeReport(completed);
  return completed;
}

}  // namespace

bool FixedSpaceHid::spaceDown() {
  return sendFixedReport(HID_KEY_SPACE);
}

bool FixedSpaceHid::releaseAll() {
  return sendFixedReport(HID_KEY_NONE);
}

bool FixedSpaceHid::ready() {
  ensureBegun();
  return report_transport.ready();
}

#endif
