---
quick_id: 260831-0hp
status: complete
completed: 2026-08-31
commit: c41b764
scope: firmware
---

# Copilot usage theme presentation

Copilot panel 4 now uses each firmware theme's own composition instead of sharing one generic layout. Signal Edge keeps its rail, Ledger uses rows and rules, Beacon uses circular indicators, and Instrument uses bezel ticks and a gauge.

Credit values below 10,000 remain exact. Larger values use compact `K` or `M` notation, including the deterministic `625K / 1.5M` fixture used for device verification.

## Files changed

- `firmware/src/app/agent_projection.cpp`
- `firmware/src/ui/theme_beacon.cpp`
- `firmware/src/ui/theme_common.h`
- `firmware/src/ui/theme_instrument.cpp`
- `firmware/src/ui/theme_ledger.cpp`

No host, protocol, or production tooling source changed.

## Verification

- `platformio test -e native-agent-projection`: 116/116 passed.
- `platformio run -e selected-usb`: passed; 588,715 flash bytes and 84,772 RAM bytes reported.
- Uploaded the selected USB firmware to the paired ESP32-S3; flash verification passed.
- Captured panel 4 from the paired device for Signal Edge, Ledger, Beacon, and Instrument in current, hard-limit, and auth-required Copilot scenes.
- Captures showed complete `625K` and `1.5M` values inside every theme's safe bounds. Limit and auth-required labels also remained complete.

Framebuffer captures were temporary verification files under `/tmp` and were not added to the repository.
