# Stack Research

**Domain:** USB-connected ESP32-S3 display keypad plus local herdr/Codex bridge
**Project:** Herdr Agent Keypad
**Researched:** 2026-08-16
**Confidence:** MEDIUM

## Recommendation in One Sentence

Use **Arduino-ESP32 3.3.11** on the official **LILYGO T-Keyboard-S3-Pro Library 0.1.0**, built reproducibly with **PlatformIO Core 6.1.19 + pioarduino platform-espressif32 55.03.311**, and pair it over **native USB CDC/Serial-JTAG with newline-delimited JSON** to a **Python 3.11+ herdr plugin process** using the public herdr 0.8.0 socket API, `pyserial 3.5`, and a separately supervised `codex app-server` 0.147.0 collector.

This prescription is deliberately host-heavy: herdr state, ordering, Codex authentication, and rate-limit interpretation stay on Linux; firmware renders a normalized snapshot and emits bounded focus requests.

## Recommended Stack

### Core Technologies

| Technology | Version / pin | Purpose | Why Recommended | Confidence |
|---|---|---|---|---|
| LILYGO T-Keyboard-S3 Pro host | Hardware MCU/keyboard V1.1; confirm delivered revision | Four physical 128×128 agent tiles, keys, encoder, LEDs | Official hardware repository identifies ESP32-S3-R8, 16 MB flash, 8 MB OPI PSRAM, STM32G030F6 coprocessor, GC9107 panels and four host panels when the fifth position contains the encoder. This is the actual required device, not a generic development board. | MEDIUM — official repository; delivered revision and mappings still require physical confirmation |
| Arduino-ESP32 | 3.3.11 (ESP-IDF 5.5.5) | Firmware framework, native USB CDC, Wi-Fi, tasks and device drivers | The new official board library explicitly requires Arduino core 3.x. Arduino is the shortest supported path to real hardware; 3.3.11 is the current tagged core and is the version carried by pioarduino 55.03.311. | MEDIUM — official tags/releases cross-checked |
| LILYGO T-Keyboard-S3-Pro Library | 0.1.0, tag commit `c46c4cb5752c04bca417c1f959dac6f5acdb5142` | Board abstraction | It encapsulates the non-obvious STM32-controlled chip selects, keys and LEDs and exposes the four host panels as independent LovyanGFX devices (`display1`…`display4`), plus `key(i)`, `encoder`, brightness and LED APIs. It also documents the 400 kHz I²C and one-panel-at-a-time constraints. | MEDIUM — official library tag and manifest |
| PlatformIO Core + pioarduino platform-espressif32 | Core 6.1.19; platform release URL/tag 55.03.311 | Reproducible firmware build and dependency lock | 55.03.311 explicitly packages Arduino-ESP32 3.3.11 with ESP-IDF 5.5.5. Pin the release ZIP rather than a moving branch. This avoids official PlatformIO's current Arduino-ESP32 2.x lag. | MEDIUM — pioarduino release metadata; pioarduino is community-maintained |
| Python | `>=3.11` | herdr plugin/bridge runtime | Matches the installed inbox plugin's recommendation and implementation style. `asyncio`, Unix sockets, JSON, subprocess supervision, `tomllib`, timestamps and threading are in the standard library, keeping the host bridge small and inspectable. | MEDIUM — installed plugin and Python standard-library contract |
| herdr public API | Target 0.8.0; require `>=0.8.0,<0.9` until schema checked | Agent snapshot/events/focus and plugin lifecycle | Current official docs expose versioned schema generation, NDJSON over Unix sockets, `agent.list`, `events.subscribe`, `session.snapshot`, metadata tokens and `agent.focus`. A narrow version range is warranted because the bridge depends on exact result fields. | MEDIUM — official 0.8.0 documentation |
| Codex CLI/app-server | 0.147.0 initially; generate schema from the installed binary | Truthful subscription-rate-limit collector | `codex app-server` is the supported local protocol boundary. Stable stdio JSONL supports `account/rateLimits/read` after `initialize`/`initialized`; the response includes primary/secondary windows and optional multi-bucket, credits, plan and spend-control data. Keep the existing ChatGPT login on the host. | MEDIUM — official release and source; backend availability is account-dependent |
| Device transport | USB Serial/JTAG CDC, 115200 baud, NDJSON application framing | Bidirectional snapshot/action link | The device is already USB-powered. The official board's PlatformIO config sets `ARDUINO_USB_MODE=1` and `ARDUINO_USB_CDC_ON_BOOT=1`, directly evidencing this path. CDC avoids Wi-Fi provisioning, LAN discovery and device credentials in v1. | MEDIUM — official board config; must be proven on the connected unit |

### Firmware Supporting Libraries

| Library | Version / pin | Purpose | When to Use | Confidence |
|---|---|---|---|---|
| LovyanGFX | 1.2.26 | Text, sprites and primitives on the GC9107 panels | Use only through the board library's `display1`…`display4`/`displayAt()` objects so the STM32-owned CS sequencing remains correct. Draw one panel at a time. | MEDIUM — official library dependency plus upstream release |
| ButtonSense | Manifest version 1.0.0; resolve and lock exact package/commit before implementation | Debounce, press/release/hold and combos | Use via `TKeyboardS3Pro.key(i)` and `keyManager()`, not raw I²C key polling. **Version evidence is inconsistent:** ButtonSense `library.json` says 1.0.0 while the public Git tag is 0.1.0; do not claim a reproducible lock until PlatformIO resolution is captured. | LOW for the exact distributable version; MEDIUM for its required API |
| ArduinoJson | 7.4.3 | Bounded parsing/serialization of normalized NDJSON messages | Use for the small device protocol only. 7.4.3 is current and includes a numeric-conversion buffer-overrun fix. Reject oversized frames before parsing. | MEDIUM — official release |
| Arduino `USB`/`Serial` support | Included with Arduino-ESP32 3.3.11 | Native USB CDC endpoint | Use fixed Hardware CDC and JTAG (`ARDUINO_USB_MODE=1`, `ARDUINO_USB_CDC_ON_BOOT=1`) rather than custom TinyUSB classes. | MEDIUM — Espressif and board docs |

### Host Supporting Libraries and APIs

| Library / API | Version | Purpose | When to Use | Confidence |
|---|---|---|---|---|
| Python standard library | Python 3.11+ | herdr Unix socket, Codex subprocess JSONL, supervision, config and timers | Use `asyncio.open_unix_connection()` for herdr, `asyncio.create_subprocess_exec()` for Codex, and ordinary JSON objects at both boundaries. | MEDIUM |
| pyserial | 3.5 | Configure and read `/dev/ttyACM*`, timeouts and reconnect | Use a dedicated blocking serial thread feeding the bridge event loop. This is simpler and better-supported on current Python than adding `pyserial-asyncio`. Match devices through a stable `/dev/serial/by-id/` path or udev rule, not whichever `ttyACM` number appears first. | MEDIUM — official PyPI version; current-Python behavior still needs local proof |
| herdr raw socket API | 0.8.0 schema | Bootstrap, event subscription and focus | On connect, obtain `agent.list` (or snapshot as appropriate), subscribe to relevant pane/agent events, then refresh after reconnect. Read metadata tokens supplied by `herdr-agent-inbox`. Send `agent.focus` with the chosen pane target only; never invoke settle/unread actions. | MEDIUM |
| `herdr-agent-inbox` metadata projection | Installed revision `de409f683262` | Authoritative title and inbox ordering | Mirror the plugin TUI's verified algorithm: read each `agent.list` row's `tokens.rank`, sort ascending, then `state_change_seq` descending; display `title`/`tokens.title`, status, age/since and flag. If `rank` is absent, report inbox data unavailable rather than invent a second priority model. | MEDIUM for this installed revision; LOW as a future stable cross-plugin contract |
| Codex stable app-server protocol | Codex 0.147.0 schema generated by that binary | Subscription-window snapshots | Spawn `codex app-server --stdio`; send one `initialize`, then `initialized`, then `account/rateLimits/read`. Normalize `rateLimits`, optional `rateLimitsByLimitId`, `rateLimitResetCredits`, timestamps and null/unavailable fields. Treat `account/rateLimits/updated` as sparse and merge only into a known snapshot or refetch. | MEDIUM |

## Exact Hardware and Abstraction Evidence

The official 0.1.0 board library documents the host as ESP32-S3 with 16 MB flash and 8 MB OPI PSRAM. An STM32G030F6 sits on I²C and owns display chip-selects, key reads and 14 WS2812C LEDs. The four host displays are GC9107 128×128 IPS panels sharing SPI; the host's fifth CS position is occupied by the encoder. The library's relevant stable surface is:

- `TKeyboardS3Pro.begin()` and `update()`;
- `display1`…`display4`, `displayAt()`, `screenCount()` and `setBrightness()`;
- `key(0..4)` returning ButtonSense objects and `keyManager()`;
- `encoder.delta()` / `encoderPosition()`;
- `setLeds()` and lower-level LED calls.

Do not bypass this layer. The STM32 requires a double CS-register write, LCD CS is unreliable at 1 MHz I²C, and the official library therefore uses 400 kHz and one display at a time. Any renderer assuming four independently wired TFT chip-select GPIOs is wrong for the Pro.

The older official hardware repository documents MCU and keyboard PCB V1.1 and contains examples pinned to Arduino-ESP32 2.0.14. Those examples are useful hardware evidence but are **not** the framework baseline for new firmware: the newer official 0.1.0 driver requires core 3.x.

## Herdr Inbox and Focus Contract

### Verified read path

1. herdr 0.8.0 exposes NDJSON on `HERDR_SOCKET_PATH` and publishes its exact installed schema through `herdr api schema --json`.
2. The inbox daemon reports `title`, `rank`, `age`, `since`, and `flag` as pane metadata tokens and installs an `agent.view.set` sort.
3. Official herdr docs state that `agent.view.set` does **not** reorder `agent.list`; therefore the bridge must perform the same projection as the inbox's own TUI: `(tokens.rank ascending, state_change_seq descending)`.
4. The top three rows from that ordered list become the three agent keys. Missing rank metadata is an integration error/stale state, not permission to recompute priorities from raw status.

### Verified focus-write complication

`agent.focus` is the supported public focusing method. However, the installed inbox daemon's `_on_focus()` clears a manually set unread flag after a focus event (outside its 1.5-second guard). That is a real conflict with a strict interpretation of “selection focuses only and must not mutate inbox state.” Choosing a different herdr focus command is not a proven fix because focus events are what trigger the daemon behavior.

**Prescription:** retain `agent.focus` as the only device action, but do not declare the non-mutation acceptance criterion solved until the inbox plugin exposes device-safe focus semantics or stops treating focus as unread acknowledgement. The keypad bridge itself must never call `settle`, `unread`, `clear`, or the inbox control socket. This is an API/semantics question, not a transport choice.

## Codex `account/rateLimits/read` Contract

For the pinned Codex app-server version:

- The default supported transport is stdio NDJSON; WebSocket listening is explicitly experimental/unsupported.
- Every connection must send one `initialize` request and then an `initialized` notification before other methods.
- `account/rateLimits/read` is a stable ChatGPT-account method. It returns `rateLimits`, optional `rateLimitsByLimitId`, and optional `rateLimitResetCredits`.
- A rate-limit snapshot may contain `primary`, `secondary`, `credits`, `individualLimit`, `spendControlReached`, `planType`, and `rateLimitReachedType`; each window contains `usedPercent`, optional `windowDurationMins`, and optional Unix-seconds `resetsAt`.
- The method describes ChatGPT/Codex subscription limits. API-key auth is a separate account mode and must not be presented as subscription quota data.
- The app-server can generate TypeScript or JSON Schema specific to the installed Codex binary. Generate/inspect that schema during implementation and normalize optional fields; do not vendor a hand-copied response type from `main` as timeless.

The bridge should own polling, last-success timestamps and stale/unavailable state. Firmware should receive only normalized percentages, reset timestamps, labels and observation time—never Codex credentials or raw auth responses.

## Transport Decision

| Criterion | USB CDC (recommended) | Wi-Fi | Hybrid USB + Wi-Fi |
|---|---|---|---|
| Board/framework evidence | Official board config enables native USB CDC; ESP32-S3 has USB Serial/JTAG | Arduino-ESP32 supports 2.4 GHz Wi-Fi; board hardware lists Wi-Fi | Both primitives exist, but no official board-level hybrid protocol |
| v1 setup | Plug in, stable Linux device identity/udev | Requires SSID provisioning, addressing/discovery and reconnect policy | Requires both setups and a precedence/failover state machine |
| Security | Local device node permissions; no network credential on firmware | Needs device Wi-Fi credential and authenticated local service | Both attack/configuration surfaces |
| Reliability model | Enumeration, disconnect/reconnect, line framing | AP changes, DHCP/mDNS, RF and LAN reachability | Split-brain/duplicate action risk unless one link is authoritative |
| Remote/updatable future | Limited to host cable | Natural fit for LAN HTTP/WebSocket/OTA | Useful only if requirements later demand cable data plus LAN management |
| Recommendation | **Use for v1** | Keep as a later transport adapter if physical USB proves unsuitable or remote use becomes required | **Do not build in v1** |

Use a compact versioned NDJSON envelope over CDC, with monotonic snapshot sequence numbers, action request IDs, explicit acknowledgements, maximum line length, and full snapshot replacement after reconnect. These are protocol properties, not a reason to add a network stack.

## Development Tools

| Tool | Version / use | Notes |
|---|---|---|
| PlatformIO Core | 6.1.19 | Pin project platform URL and every direct firmware dependency; commit the generated lock once implementation begins. |
| pioarduino platform-espressif32 | 55.03.311 release ZIP | Provides the required Arduino-ESP32 3.3.11/ESP-IDF 5.5.5 pair. It is a community distribution, so keep the URL immutable and make the alternative Arduino CLI path documented in build configuration, not runtime code. |
| herdr schema generator | from targeted herdr 0.8.x binary | Treat `herdr api schema --json` as the truth for request/result shapes. |
| Codex schema generator | from targeted Codex 0.147.0 binary | `codex app-server generate-json-schema --out …` emits a version-matched stable schema. Do not opt into experimental fields for this collector. |
| Linux udev `/dev/serial/by-id` | host facility | Use stable USB identity and least-privilege device access; never auto-open the first `ttyACM*`. Exact VID/PID/serial identity remains to be measured on the device. |

## Installation Baseline

Illustrative pinned firmware configuration (the exact board flags must be confirmed on physical bring-up):

```ini
[env:t_keyboard_s3_pro]
platform = https://github.com/pioarduino/platform-espressif32/releases/download/55.03.311/platform-espressif32.zip
board = esp32-s3-devkitc-1
framework = arduino
monitor_speed = 115200
board_upload.flash_size = 16MB
board_build.memory_type = qio_opi
build_flags =
  -D ARDUINO_USB_MODE=1
  -D ARDUINO_USB_CDC_ON_BOOT=1
lib_deps =
  https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library.git#0.1.0
  lovyan03/LovyanGFX@1.2.26
  bblanchon/ArduinoJson@7.4.3
  lbuque/ButtonSense@^1.0.0
```

Host runtime baseline:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install pyserial==3.5
```

The ButtonSense line is intentionally not called fully reproducible until its registry resolution is captured: upstream's manifest says 1.0.0 while its GitHub tag says 0.1.0. Replace the range with the exact resolved source/commit in the implementation lock.

## Alternatives Considered

| Recommended | Alternative | When the Alternative Is Justified |
|---|---|---|
| Arduino-ESP32 + official board library | ESP-IDF + community T-Keyboard S3 Pro BSP | Only after official Arduino bring-up is proven and a concrete requirement needs ESP-IDF-only facilities. The BSP is community-maintained and would replace the official abstraction. |
| pioarduino 55.03.311 | Arduino CLI with Espressif board package 3.3.11 | Prefer this if project policy disallows the pioarduino fork. It is more directly vendor-supported but requires separately recreating the board's flash/PSRAM/USB flags and dependency locking. |
| USB CDC | Wi-Fi HTTP/WebSocket | Use Wi-Fi if later requirements include untethered network data, remote host placement or cable-free operation. It is not needed for a USB-powered desk device. |
| Python 3.11+ | Rust/Go/Node host service | Use another runtime only if the herdr plugin ecosystem adopts it or a standalone multi-platform server becomes the product. Python already matches the installed plugin and keeps socket/Codex glue small. |
| pyserial blocking worker | pyserial-asyncio 0.6 | Consider only after proving it on the actual Python runtime; its last release is from 2021 and its published classifiers stop at Python 3.8. |
| Simple LovyanGFX renderer | LVGL | Use LVGL only if the product grows into nested widgets/navigation/animations whose state management outweighs its memory, build and rendering complexity. Four fixed tiles do not. |

## What NOT to Use

| Avoid | Why | Use Instead |
|---|---|---|
| Official PlatformIO `platform-espressif32` 7.0.1 for this build | Its Arduino package is 2.0.17, while the current official board library requires Arduino core 3.x. | Pinned pioarduino 55.03.311 or Arduino CLI core 3.3.11 |
| Old official `arduino-esp32-libs_V2.0.14` examples as the production base | They predate the new unified board library and encode older display stacks/versions. | T-Keyboard-S3-Pro Library 0.1.0 on Arduino 3.3.11 |
| TFT_eSPI/Arduino_GFX/raw panel CS control | The Pro's CS lines are multiplexed by STM32 with hardware-specific timing/latching quirks. A second display abstraction bypasses the supported path. | Board library's LovyanGFX display objects |
| LVGL for v1 | Adds a full UI framework where four bounded tile renderers suffice. The old repo's LVGL 8.3.5 example is not evidence that it is needed. | LovyanGFX primitives/sprites |
| Direct ChatGPT backend HTTP calls or credentials on ESP32 | Private backend contracts change and firmware would hold high-value credentials. | Host-side Codex app-server collector and normalized device data |
| Screen scraping Codex TUI | Brittle, loses nullability/schema, and cannot distinguish stale data honestly. | `account/rateLimits/read` |
| Reading `state.json`, `history.jsonl`, or inbox control socket from the keypad bridge | These are plugin-private persistence/control details and mutations risk violating focus-only semantics. | herdr `agent.list` metadata tokens and public `agent.focus` |
| Reimplementing blocked/unseen/working/idle/settled priority from raw agent status | Creates a competing source of truth and will drift from the installed inbox. | Consume `tokens.rank`; fail visibly if unavailable |
| Custom USB OTG/TinyUSB class | Unnecessary endpoint complexity and may conflict with the shared ESP32-S3 USB PHY/debugging setup. | Fixed USB Serial/JTAG CDC |
| MQTT, SQLite, web server, or device authentication in v1 | None is required for one directly attached device with a host-authoritative snapshot; each adds state/configuration. | In-memory host cache + versioned USB NDJSON |
| Hybrid link in v1 | Two links create failover, duplication and split-brain action semantics before either is proven. | USB primary; add a transport interface only when a second transport is actually required |

## Version Compatibility and Evidence

| Component | Compatible With | Evidence / caveat |
|---|---|---|
| T-Keyboard-S3-Pro Library 0.1.0 | Arduino-ESP32 3.x; LovyanGFX `^1.1.0`; ButtonSense `^1.0.0` | Official README and `library.json`; only published board-library tag is 0.1.0. |
| pioarduino 55.03.311 | Arduino-ESP32 3.3.11; ESP-IDF 5.5.5 | Release name states the exact pair. |
| LovyanGFX 1.2.26 | Board library dependency floor `^1.1.0` | Current release satisfies the manifest range. Physical multi-panel behavior still relies on the board wrapper. |
| ButtonSense manifest 1.0.0 | Board library dependency `^1.0.0` | GitHub tag discrepancy (0.1.0) is unresolved; lock resolved artifact/commit before coding. |
| ArduinoJson 7.4.3 | Arduino-ESP32 3.3.11 | Independent protocol dependency; current security-fix release. |
| herdr-agent-inbox installed revision `de409f683262` | herdr `>=0.7.0`, Python 3.11 recommended | README plus local source. `rank` token behavior is verified for this revision, not promised as a stable third-party API. |
| Proposed bridge | herdr `>=0.8.0,<0.9` | Current 0.8.0 docs provide snapshot/schema/event facilities. Validate generated schema for the installed binary during implementation. |
| Codex 0.147.0 | Its own generated stable app-server schema | `main` can evolve independently; pin executable and generate matching schema. |
| pyserial 3.5 | Python 3.11+ target | Widely used but old metadata does not prove every future Python version; verify on target host. |

## Verified Facts vs. Open Questions

### Verified facts

- The official 0.1.0 board library supports four host panel objects, five keys, encoder, LEDs and chained boards and requires Arduino core 3.x.
- The official board's legacy build configuration enables USB CDC on boot; native USB serial is viable in principle.
- Current herdr docs expose the raw methods and generated schema needed for snapshots/events/focus.
- The installed inbox's own TUI sorts `agent.list` by reported `rank` then descending `state_change_seq`.
- Codex app-server 0.147.0 documents a stable `account/rateLimits/read` method and version-specific schema generation.

### Unresolved and must be answered on the real installation/hardware

1. **Delivered board identity:** confirm PCB revision, host/module role, four-panel/encoder mapping, screen orientation, USB VID/PID/serial identity, PSRAM and flash settings. The old custom PlatformIO board JSON itself says 8 MB while its project config overrides 16 MB, so do not trust that JSON unchanged.
2. **ButtonSense lock:** resolve the manifest/tag mismatch and capture an immutable dependency source.
3. **Focus semantics:** current inbox source clears manual unread on focus. A product decision or inbox-plugin API change is required before claiming focus is non-mutating.
4. **Rank-token stability:** `tokens.rank` is verified in the installed revision but not documented as a stable cross-plugin contract. Pin the inbox revision or upstream a read-only ordered-snapshot contract.
5. **Actual Codex auth/account:** verify the host's active Codex auth is ChatGPT-backed and which optional buckets/credit fields the account returns; never fabricate missing fields.
6. **USB runtime behavior:** verify enumeration after reset, reconnect, simultaneous flashing/logging/data, maximum safe frame size, and stable device identification on the connected Fedora/Linux host.
7. **Herdr exact schema:** generate it from the installed binary before implementation; this research uses the current 0.8.0 documentation rather than an observed local schema.

## Sources

All web sources retrieved **2026-08-16**. Primary/official sources are preferred; confidence remains MEDIUM because physical-device and installed-runtime checks were intentionally not run during research.

- LILYGO official board library README — hardware and abstractions: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library/blob/master/README.md
- LILYGO official board library manifest — version/dependencies: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library/blob/master/library.json
- LILYGO official board library tag 0.1.0: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library/tags
- LILYGO official hardware repository — PCB revisions, parts, older software baseline: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro
- Official legacy PlatformIO config — USB CDC flags and board settings: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro/blob/arduino-esp32-libs_V2.0.14/platformio.ini
- Espressif Arduino-ESP32 3.3.11 tag: https://github.com/espressif/arduino-esp32/releases/tag/3.3.11
- Espressif Arduino USB CDC documentation: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/usb_cdc.html
- Espressif ESP32-S3 USB device documentation: https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_device.html
- pioarduino platform-espressif32 55.03.311 release: https://github.com/pioarduino/platform-espressif32/releases/tag/55.03.311
- Official PlatformIO platform-espressif32 releases: https://github.com/platformio/platform-espressif32/releases
- LovyanGFX 1.2.26 release: https://github.com/lovyan03/LovyanGFX/releases/tag/1.2.26
- ButtonSense manifest and tags: https://github.com/lbuque/ButtonSense/blob/master/library.json and https://github.com/lbuque/ButtonSense/tags
- ArduinoJson 7.4.3 release: https://github.com/bblanchon/ArduinoJson/releases/tag/v7.4.3
- herdr 0.8.0 socket API: https://herdr.dev/docs/socket-api/
- herdr CLI reference: https://herdr.dev/docs/cli-reference/
- Installed `herdr-agent-inbox` README and source revision `de409f683262` (local primary evidence): `/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262/README.md`, `daemon.py`, `inbox_tui.py`
- OpenAI Codex app-server protocol: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md
- OpenAI Codex v2 account schema source: https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/account.rs
- OpenAI Codex 0.147.0 release: https://github.com/openai/codex/releases/tag/rust-v0.147.0
- pyserial 3.5: https://pypi.org/project/pyserial/
- pyserial-asyncio 0.6 (alternative not recommended): https://pypi.org/project/pyserial-asyncio/

---
*Stack research for: Herdr Agent Keypad*
*Researched: 2026-08-16*
