## User Constraints

### Locked Decisions

## Implementation Decisions

### Bring-up Experience
- **D-01:** The primary Phase 1 validation path is a host-driven utility that exercises both the keypad hardware and the host transport.
- **D-02:** The utility runs one guided sequence rather than requiring the operator to discover and invoke independent checks.
- **D-03:** The guided run requires explicit human confirmation for every physical control and observable: each display and its orientation, each matching key, encoder click/direction, each relevant LED, brightness changes, and reboot behavior. Software must not infer that a physically observed result was correct.
- **D-04:** After the run passes and its evidence is preserved, archive the bring-up utility rather than maintaining it as a supported product diagnostic mode or folding it into the later bridge CLI.

### USB Proof Bar
- **D-05:** USB qualifies only as a strict bounded link: the defined proof run permits no unexplained frame loss, duplication, corruption, or out-of-order acceptance. Expected reset or unplug interruptions are acceptable only when reconnection is clean and uncertain in-flight work is discarded rather than replayed.
- **D-06:** Exercise realistic v1 traffic plus bounded peaks: expected snapshot/status cadence, worst-case legal frame sizes, rapid bidirectional bursts, and concurrent display/input activity. Maximum-rate stress unrelated to the product workload is not the acceptance target.
- **D-07:** Flashing and normal runtime use the same physical USB connection. After flashing or resetting, the runtime endpoint must return and be rediscovered without manual port selection.
- **D-08:** Select the single Wi-Fi fallback only for a repeatable failure on the delivered unit that still breaks the strict bounded-link bar after documented cable, USB-mode, permission, and host-binding remediation. Setup inconvenience alone does not disqualify USB.

### Recovery and Device Linking
- **D-09:** One privileged Linux setup is acceptable during Phase 1 development. The transport and identity design must nevertheless preserve an unprivileged later user experience, including first use with a new keypad; permanent root-only operation is not acceptable.
- **D-10:** A new keypad uses physical first-use pairing. The host stores an opaque device identity after explicit confirmation instead of trusting a transient port path or any matching device automatically. — **Reversibility:** costly — changing the pairing identity after later host and firmware work would require coordinated protocol and persisted-binding migration.
- **D-11:** After pairing, the host automatically rebinds only the exact paired keypad across device reset, unplug/replug, USB port changes, and endpoint renumbering. Look-alike or ambiguous devices fail closed rather than replacing the stored binding.
- **D-12:** The Phase 1 recovery proof covers device reset, unplug/replug on another USB port, endpoint renumbering, and host-utility restart. Full host reboot, suspend/resume, and cross-component product recovery remain later acceptance work.

### Agent Discretion
- Exact proof duration, legal frame bounds, burst profile, and measurement thresholds, provided they defend D-05 and D-06 with recorded evidence.
- The concrete unprivileged discovery mechanism and one-time development permission setup, provided runtime does not require root and no transient `/dev/tty*` path becomes device identity.
- The physical pairing challenge and confirmation representation, provided the user explicitly confirms the keypad and the resulting identity is opaque and stable.
- The evidence file format and archive layout; the unselected “Evidence record” gray area is left to standard project conventions.

### Deferred Ideas (OUT OF SCOPE)

- Full host reboot, suspend/resume, independent component recovery, and complete product resynchronization remain Phase 4 acceptance work.
- A permanently supported diagnostic mode or bridge maintenance command was considered and rejected for Phase 1; the guided utility is archived after evidence capture.

> The constraints above are copied verbatim from `.planning/phases/01-physical-keypad-and-proven-transport/01-CONTEXT.md:14-39,87-90`. [VERIFIED: .planning/phases/01-physical-keypad-and-proven-transport/01-CONTEXT.md:14-39,87-90]

## Research Metadata

**Phase:** 1 — Physical Keypad and Proven Transport  
**Researched:** 2026-08-16  
**Domain:** ESP32-S3/STM32 display-keypad bring-up, Linux USB CDC discovery, and bounded bidirectional framing  
**Overall confidence:** MEDIUM — official board and platform sources establish the intended APIs, but the delivered PCB/STM32 revision, physical map, USB descriptors, permissions, re-enumeration, and traffic performance are measurements that can only be established on the connected unit during execution.

## Summary

Phase 1 should be planned as an evidence-producing vertical bring-up, not as a generic firmware scaffold. The official Pro library models a host board with four 128×128 GC9107 displays, five STM32-read keys, fourteen STM32-driven RGB LEDs, and a GPIO rotary encoder; it explicitly warns that the shared panels must be selected and drawn one at a time. [CITED: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library] The library documentation does **not** establish the delivered unit's physical panel order, visible orientation, key-to-panel correspondence, LED positions, encoder push mapping, or PCB/STM32 firmware revision; those remain execution measurements and must be captured rather than inferred. [VERIFIED: .planning/ROADMAP.md:18-28]

Use the official board abstraction and prove USB first. The legacy official board configuration enables `ARDUINO_USB_MODE=1` and `ARDUINO_USB_CDC_ON_BOOT=1`, while Espressif documents USB CDC as both a host/device communication class and a firmware-flashing path. [CITED: https://raw.githubusercontent.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro/arduino-esp32-libs_V2.0.14/platformio.ini] [CITED: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/usb_cdc.html] These sources establish feasibility, not suitability on this cable, connector, firmware build, Linux host, or delivered board. Selection therefore happens only after the guided physical map, identity/re-enumeration suite, and sustained framed-traffic gate produce recorded evidence.

**Primary recommendation:** Plan one guided host-driven run with four ordered gates—immutable stack/revision capture, human-confirmed physical map, exact-device pairing/recovery, and a strict bounded traffic run—then select USB if and only if every USB criterion passes; otherwise remediate and repeat, and only after a repeatable unresolved failure run the same gate over one device-initiated authenticated Wi-Fi stream. Never implement or select a hybrid link.

## Phase Requirements

| ID | Description | Research support |
|---|---|---|
| HARD-01 | “The user can run the firmware on the connected LILYGO T-Keyboard S3 Pro with all four displays, their matching keys, the rotary encoder click, orientation, brightness control, reboot behavior, and the selected host link verified against a recorded physical map.” [VERIFIED: .planning/REQUIREMENTS.md:12-12] | The physical-map schema and guided sequence below require explicit human confirmation for every named observable and record delivered revisions, pins/APIs used, and reboot outcomes. |
| HARD-03 | “The connected device and host exchange bounded, versioned messages reliably over the transport selected by physical bring-up, with USB preferred unless measured behavior disqualifies it.” [VERIFIED: .planning/REQUIREMENTS.md:14-14] | The protocol envelope, traffic profile, strict counters, interruption semantics, USB remediation gate, and single Wi-Fi branch below make selection measurable and prevent a hybrid implementation. |

## Architectural Responsibility Map

| Capability | Primary owner | Secondary owner | Rationale |
|---|---|---|---|
| Delivered revision inventory | Guided host utility/evidence writer | Human operator | Software records queried identifiers; the operator records visible PCB markings and confirms the exact connected unit. |
| Physical panel/key/LED/orientation map | Firmware board adapter | Guided host utility + human operator | Firmware labels one logical observable at a time; the host sequences and records explicit confirmation. |
| Brightness and reboot proof | Firmware board adapter | Guided host utility | Firmware performs bounded commands; host records requested values, boot/session identity, and human-observed result. |
| Protocol framing/session state | Transport-neutral firmware and host protocol modules | USB or Wi-Fi adapter | Version, bounds, sequence, acknowledgements, and reset semantics must not depend on the selected byte stream. |
| USB enumeration and permissions | Host transport/discovery adapter | Linux udev | Device-node names are discovery artifacts; the stored pairing identity is application-level and physically confirmed. |
| Transport qualification | Host proof runner | Firmware metrics endpoint | Host owns expected counts/timing and evidence; firmware reports accepted/rejected sequence and resource/input/display metrics. |
| Transport selection | Evidence gate | Human-readable evidence record | USB passes or a repeatable remediated failure triggers one Wi-Fi fallback; no runtime arbitration exists. |

## Standard Stack

### Core

| Component | Pin for the plan | Purpose | Evidence and planning consequence |
|---|---|---|---|
| LILYGO T-Keyboard-S3-Pro Library | `0.1.0` tag/immutable commit | Displays, STM32-mediated keys/LEDs, encoder, brightness, discovery | The official manifest says `"version": "0.1.0"`; the README requires Arduino core 3.x and exposes the Pro-specific abstraction. Pin an immutable revision and do not follow `master`. [CITED: https://raw.githubusercontent.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library/master/library.json] [CITED: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library] |
| Arduino-ESP32 | `3.3.11` | Firmware runtime and native USB CDC | The official tagged release exists; keep the build flags explicit because USB personality changes enumeration behavior. [CITED: https://github.com/espressif/arduino-esp32/releases/tag/3.3.11] |
| pioarduino platform-espressif32 | `55.03.311` release artifact | Reproducible PlatformIO carrier for Arduino-ESP32 3.3.11 | The release identifies Arduino 3.3.11/ESP-IDF 5.5.5; use an immutable release URL rather than a moving branch. [CITED: https://github.com/pioarduino/platform-espressif32/releases/tag/55.03.311] |
| Python | Existing project target `>=3.11` | Guided host utility and evidence writer | Use standard-library JSON, timing, hashing, TLS, and file persistence; add only serial access for the USB branch. [VERIFIED: .planning/research/STACK.md:24-24] |
| pyserial | `3.5` | USB enumeration/open/read/write | PyPI reports 3.5 as latest and pyserial documents `serial.tools.list_ports` metadata including USB identity fields. [CITED: https://pypi.org/project/pyserial/3.5/] [CITED: https://pyserial.readthedocs.io/en/latest/tools.html] |

### Official board surface to use

- `TKeyboardS3Pro.begin()`, regular `update()`, `display1`…`display4`/`displayAt()`, `screenCount()`, `setBrightness()`, `key(0..4)`, `encoder.delta()`/`encoderPosition()`, and `setLeds()` are the intended high-level surface. [CITED: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library]
- The host is documented as four panels on CS1…CS4 with the encoder occupying the fifth panel position; the library still exposes five key states separately. [CITED: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library] Therefore the planner must not equate `key(4)` with encoder click until the delivered unit proves that correspondence.
- The STM32 owns the panel chip-selects, key reads, and LEDs over I²C; the official wrapper handles the required panel selection behavior. [CITED: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library] Do not substitute raw GPIO assumptions from the non-Pro T-Keyboard.

### ButtonSense compatibility gate

The board manifest requires ButtonSense `^1.0.0`, and ButtonSense's own manifest says `"version": "1.0.0"`; however, the only visible upstream tag is `0.1.0` at commit `b1aeb22a73c523b37ebd11bee54000b77484f76c`. [CITED: https://raw.githubusercontent.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library/master/library.json] [CITED: https://raw.githubusercontent.com/lbuque/ButtonSense/master/library.json] [CITED: https://github.com/lbuque/ButtonSense/tags] This is a reproducibility blocker, not evidence that the API is incompatible.

Plan a pre-bring-up dependency gate that records the actual resolved ButtonSense source commit, verifies the headers and methods used by the pinned board-library tag, and then replaces the semantic range with that immutable source. If resolution cannot satisfy the board tag unchanged, stop and document the exact compiler/API mismatch before patching; do not silently vendor an unrecorded fork. No package-install or legitimacy commands were run in this research because the assignment explicitly requires skipping validation commands.

## Architecture Patterns

### One guided state machine, not independent demos

Use one host-owned sequence with durable step results:

1. **Identify:** record firmware/build/library commits; operator records photographed/transcribed PCB revision and any STM32/keyboard markings; firmware reports discovered I²C address(es) and STM32 firmware version if the official API returns it.
2. **Map:** show a unique number, arrow, and color on exactly one panel; require the operator to record physical position and correct visible orientation; prompt its matching physical key; then map encoder clockwise/counter-clockwise/click and each relevant LED one at a time.
3. **Behavior:** command brightness at dark-but-visible, middle, and high bounded values; record human confirmation; reset by software and by the normal flash/reset path; record startup screen, reset cause, boot/session change, brightness behavior, and time until the runtime endpoint returns.
4. **Pair/recover:** display a short random challenge on the keypad, require exact host-side confirmation, store the stable opaque protocol `device_id`, and prove exact-device rebinding through reset, unplug/replug on another port, endpoint renumbering, and host-utility restart.
5. **Traffic:** run the proposed bounded profile below while cycling all four displays, polling keys/encoder, and updating relevant LEDs; then execute controlled interruptions and prove clean new-session recovery.
6. **Select/archive:** emit a machine-readable record plus a concise human summary; archive the utility only after all selected-transport gates pass.

The operator must confirm observables; a firmware response can prove only that a command was accepted, not that a panel was upright, the intended LED illuminated, or the physical control matched the displayed position. [VERIFIED: .planning/phases/01-physical-keypad-and-proven-transport/01-CONTEXT.md:17-20]

### Physical map record

The record should contain, at minimum:

| Area | Required fields |
|---|---|
| Unit identity | evidence schema version; run ID/time; firmware commit/build ID; board-library commit; Arduino/platform pins; ButtonSense resolved commit; visible PCB/keyboard revision; STM32 firmware version or explicit `unavailable`; photo filenames/hashes if captured |
| Displays | logical object/index; CS/panel index reported by library; physical position described from a fixed viewing orientation; test glyph; top-edge arrow result; rotation value used; color result; operator confirmation |
| Keys | raw/library index; physical position; associated display physical position; press/release/click observation; bounce/duplicate count during guided presses; operator confirmation |
| Encoder | clockwise delta sign; counter-clockwise delta sign; detents per prompted movement; click key/event index; operator confirmation |
| LEDs | library LED index/mask; physical position; requested hue/brightness; operator confirmation; which LEDs are relevant to v1 |
| Brightness | requested value; visible result; lowest usable value selected for proof; behavior across reset; whether persistence is absent/present (observation only—persistent preference remains later work) |
| Reboot | trigger type; reset cause if available; old/new boot ID; time to boot screen; time to rediscovery/handshake; stale descriptor closed; uncertain in-flight frame discarded |

Record observed values, including surprises; do not overwrite the evidence with a corrected assumed map. The source-controlled board adapter should then be generated/edited from the approved record so logical slot order and input binding share one map.

### Stable identity and re-enumeration

Linux udev manages device-node permissions and can create meaningful symlinks because kernel-assigned names depend on discovery order. [CITED: https://www.freedesktop.org/software/systemd/man/latest/udev.html] pyserial port enumeration exposes descriptor fields such as device path, VID, PID, serial number, location, manufacturer, product, and interface when the OS supplies them. [CITED: https://pyserial.readthedocs.io/en/latest/tools.html]

Use those descriptors only to discover candidates. Pair through an application handshake whose stable opaque `device_id` is derived from device-stable hardware identity or otherwise survives the project's normal flash/reset flow; prove that property by reflashing/resetting during this phase. The host displays a random challenge, the device renders it physically, and the user confirms before the host stores the binding. On later discovery, candidates must complete the versioned hello and return the exact stored `device_id`; zero, multiple, or mismatched candidates fail closed. A `/dev/serial/by-id` symlink may improve reopening but must not become the persisted trust identity.

The one privileged development step should install a narrow udev permission rule matching the measured runtime interface and then prove an ordinary user can enumerate and open it after unplug/replug. Record the exact pre/post udev properties and rule, but never wildcard all ACM devices or require the guided utility to run as root.

### Transport-neutral session

Use one newline-delimited JSON frame per line over a byte-stream adapter. This matches the existing stack recommendation and keeps USB/Wi-Fi selection below protocol semantics. [VERIFIED: .planning/research/STACK.md:90-101] The proposed Phase 1 envelope is:

```json
{"v":1,"type":"hello|hello_ack|probe|probe_ack|event|error","boot_id":"opaque","session_id":"opaque","seq":1,"reply_to":null,"payload":{}}
```

This is a **proposed contract**, not an observed in-repo enum. Freeze exact allowed `type` values in a schema/codec fixture before firmware and host implementations diverge. Require:

- an explicit protocol version and fail-closed incompatible-version result;
- a maximum encoded line of **4096 bytes including LF** for Phase 1;
- byte-count rejection before JSON allocation/parsing;
- strictly increasing receive sequence within one negotiated session;
- explicit acknowledgements correlated by `reply_to` for every proof frame;
- deterministic payload bytes plus a digest in proof traffic so corruption is detectable even if corrupted JSON remains syntactically valid;
- a bounded duplicate/action cache and bounded queues;
- new `boot_id` on firmware boot and new `session_id` on every handshake;
- no automatic replay of an unacknowledged event across boot/session change;
- protocol output isolated from debug logs (separate interface/channel if available, otherwise only framed records on the selected stream).

4096 bytes and the traffic values below are recommended starting bounds under Agent Discretion. Execution must record actual maximum legal serialized payload and memory/latency results; if a smaller bound is sufficient, reduce it before freezing the v1 protocol rather than raising it casually.

### USB qualification profile

Run the exact same profile on every candidate transport:

1. **Baseline 30 minutes:** one realistic complete four-slot snapshot per second, heartbeat/health at the planned cadence, immediate acknowledgements, and low-rate device events. Cycle all four panels and LEDs while continuously polling keys/encoder.
2. **Worst legal frames:** at least 1,000 frames in each direction at the final maximum encoded size, with deterministic contents and digest verification.
3. **Bounded burst:** 100 frames in each direction over 10 seconds, repeated 10 times while full display redraws and synthetic input reporting run concurrently. This is a product-shaped peak, not an unlimited baud benchmark.
4. **Human input overlap:** during baseline and burst windows, prompt a fixed number of key, encoder-direction, and encoder-click actions; record every expected physical action and corresponding accepted event without inferring physical correctness.
5. **Interruption matrix:** software reset, normal flash/reset, unplug/replug same port, unplug/replug different port, forced endpoint renumbering by another ACM device if available, and host-utility restart. For every case record disconnect detection, rediscovery, handshake time, new session IDs, discarded in-flight IDs, and first accepted post-reconnect sequence.

Pass requires exact equality between expected/sent/acknowledged counters and **zero** unexplained loss, duplicates accepted, digest mismatches, malformed accepted frames, or out-of-order accepted frames. Timeout/latency bounds must be frozen before the run; recommended initial gates are acknowledgement p99 below 250 ms during baseline, below 1 s during bounded bursts/display redraw, and runtime rediscovery plus handshake below 10 s after endpoint return. These latency numbers are planning recommendations and may be tightened or changed before execution, but never after observing a failing run without recording the reason and rerunning from scratch.

Capture minimum free internal heap, largest free block, parser/queue high-water marks, maximum display-flush duration, maximum key-poll gap, and watchdog/reset count alongside transport counters. This separates a serial failure from starvation caused by display or allocation behavior.

### USB selection decision and single Wi-Fi fallback

The branch is deliberately asymmetric:

- **USB passes:** select USB; do not implement Wi-Fi transport and do not leave a dormant hybrid path in the v1 runtime.
- **USB fails:** preserve the first failure; repeat with a known data cable/port, pinned Hardware CDC flags, corrected unprivileged udev permissions, protocol/debug separation, and exact-device rebinding. A failure is disqualifying only if it repeats after the relevant remedies.
- **Remediated USB still fails:** record the recurring signature and select exactly one fallback: device-initiated Wi-Fi station mode carrying the same NDJSON session over one authenticated TLS TCP stream to the host. Use the host's standard-library TLS server and the ESP32 platform's supported TLS client; pair a device-scoped credential/host trust during the same physical confirmation flow. Then rerun the identical traffic and interruption gate, adding AP loss/IP reacquisition and socket recreation. [CITED: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/wifi-driver/overview.html]
- **Wi-Fi does not pass:** Phase 1 is blocked; do not combine two failing transports or build failover arbitration.

Espressif documents that station disconnect can invalidate sockets and that applications must wait for IP acquisition and recreate network state. [CITED: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/wifi-driver/overview.html] The fallback therefore reconnects as a new protocol session and requests full current state; it never resumes a dead socket or replays uncertain actions.

## Don't Hand-Roll

| Problem | Do not build | Use instead | Why |
|---|---|---|---|
| Pro panel/key/LED multiplexing | Raw ESP32 GPIO/CS driver copied from the non-Pro board | Pinned official T-Keyboard-S3-Pro library | The STM32 owns CS, keys, and LEDs and the official wrapper handles one-panel-at-a-time behavior. [CITED: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library] |
| Key debounce/click/hold | A second debounce state machine | The ButtonSense objects returned by the pinned board library after the compatibility gate | One input source prevents raw and debounced paths from disagreeing. [CITED: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library] |
| Linux port naming | Polling or persisting `/dev/ttyACM0` | pyserial enumeration + udev candidate properties + application handshake identity | Kernel discovery order is not identity. [CITED: https://www.freedesktop.org/software/systemd/man/latest/udev.html] |
| Hybrid failover | USB/Wi-Fi arbitration and duplicate-action suppression across simultaneous links | One selected adapter beneath one session protocol | Hybrid is explicitly outside the locked Phase 1 scope. [VERIFIED: .planning/phases/01-physical-keypad-and-proven-transport/01-CONTEXT.md:7-9] |
| Visual verification | Software self-certification that a physical result “looks right” | Guided human confirmation stored beside device counters | Orientation, position, color, and tactile correspondence require observation. [VERIFIED: .planning/phases/01-physical-keypad-and-proven-transport/01-CONTEXT.md:17-20] |
| USB trust | VID/PID, tty number, or first matching device as authentication | Physically confirmed opaque protocol identity | Look-alike and ambiguous devices must fail closed. [VERIFIED: .planning/phases/01-physical-keypad-and-proven-transport/01-CONTEXT.md:29-32] |

## Common Pitfalls

### Assuming the delivered unit is documented V1.1
**What goes wrong:** the map or toolchain is frozen from repository documentation before anyone reads the delivered PCB/keyboard/STM32 markings.  
**Avoidance:** record markings, firmware-reported revision, photos/hashes, flash/PSRAM settings, and actual behavior at the start; call any unavailable field `unavailable`, not V1.1. The repository's documented V1.1 is background evidence, not the delivered revision. [VERIFIED: .planning/research/STACK.md:195-203]

### Treating KEY5 as encoder click without proof
**What goes wrong:** direction works but click is bound to the wrong raw key, or boot behavior is triggered unexpectedly.  
**Avoidance:** map all five library keys and the encoder independently; prompt encoder press while logging raw key transitions; then store the observed click association. The official library documents five keys and encoder direction but does not identify the encoder push as a particular ButtonSense index. [CITED: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library]

### Drawing panels concurrently
**What goes wrong:** wrong panel selection, corruption, flicker, or missed input under load.  
**Avoidance:** use one official Display object at a time and include key-poll-gap metrics during all-panel redraw. The official README calls multi-panel selection unreliable on this hardware. [CITED: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library]

### Mistaking a powered/flashed connection for a qualified data link
**What goes wrong:** CDC disappears after reset, a stale file descriptor hangs, debug output enters the parser, or runtime requires manual port selection.  
**Avoidance:** pin USB personality flags, isolate logs, close on disconnect, rediscover and re-handshake by exact paired identity, and run the interruption matrix. [CITED: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/usb_cdc.html]

### Unbounded reads before validation
**What goes wrong:** a missing LF or malicious/corrupt peer grows memory until reset; JSON allocation delays display/input work.  
**Avoidance:** cap encoded bytes before parse, reuse buffers, reject overlong frames, and record queue/parser high-water marks.

### Replaying uncertain work after reconnect
**What goes wrong:** an input sent immediately before reset is performed twice or attributed to a new host/device session.  
**Avoidance:** boot/session IDs scope sequence numbers and acknowledgement caches; discard uncertain in-flight work and require a deliberate new action. [VERIFIED: .planning/phases/01-physical-keypad-and-proven-transport/01-CONTEXT.md:22-26]

### Lowering the gate after seeing results
**What goes wrong:** transport selection becomes a narrative rather than measured evidence.  
**Avoidance:** freeze duration, frame maximum, profile, counters, and latency thresholds in the run manifest before the qualifying run; preserve every failed manifest/result pair.

## Evidence and Validation Architecture

`.planning/config.json` contains `"nyquist_validation": false`, so the standard automated Nyquist Validation Architecture section is intentionally omitted. [VERIFIED: .planning/config.json:99-101] Phase 1 still requires execution evidence because HARD-01 is physically observable and HARD-03 is a measured transport contract.

The planner should create these validation seams:

| Seam | Automated evidence | Human/physical evidence | Phase gate |
|---|---|---|---|
| Protocol codec | Cross-language golden valid/invalid/oversized/version/sequence fixtures; exact counters | None | Host and firmware agree on every fixture before hardware traffic |
| Board mapping | Firmware reports logical IDs/events and emits one-at-a-time test patterns | Operator confirms panel position/orientation, matching key, encoder direction/click, LED position, brightness | Every row confirmed; no inferred rows |
| Identity/discovery | Candidate descriptor snapshots; hello device ID; ambiguity/mismatch tests; unprivileged open | Operator confirms first-use challenge on the intended keypad | Same opaque ID survives reset/reflash/port move; ambiguous fails closed |
| Sustained traffic | Deterministic payload digest, send/receive/ack/sequence counters, timing/resource metrics | Prompted input actions during concurrent load | Strict zero-error bar and frozen timing bounds |
| Recovery | Boot/session IDs, descriptor changes, reconnect timings, discarded in-flight IDs | Operator performs unplug/replug and observes boot/display behavior | Each required interruption yields a clean new session |
| Selection | Signed/hashed manifest plus result and remediation history | Human-readable selection summary | USB selected on pass; otherwise one tested Wi-Fi stream selected on pass; hybrid never selected |

### Measurements explicitly deferred to execution

No physical-device or host validation commands were run in this research, per the assignment. The following cannot honestly be filled in before execution: delivered PCB and keyboard revision; STM32 firmware revision; physical display/key/LED map; encoder click index and direction sign; correct rotation; brightness usability and reset behavior; actual USB connector/interface; VID/PID/serial/interface/by-id values; Fedora permissions/udev group behavior; reset/flash/unplug re-enumeration; actual frame-size memory headroom; sustained latency/error counters; and final USB-versus-Wi-Fi selection.

A plan that pre-populates any of those as passed is invalid. Wave 0 should define the schema/fixtures and freeze the proof manifest; the first hardware wave fills the map and USB identity; the qualification wave produces the traffic/recovery evidence and transport decision; the final task archives the utility and evidence only after the selected link passes.

## Security Domain

| ASVS area | Applies | Phase 1 control |
|---|---|---|
| V2 Authentication | Limited/local device pairing | Explicit physical challenge and exact opaque device identity; never trust first matching USB device. |
| V3 Session Management | Yes, protocol session only | Fresh boot/session IDs; bounded sequence and dedupe state; discard uncertain work across reconnect. |
| V4 Access Control | Yes, host device access | Narrow udev permissions; ordinary-user runtime; mismatched/ambiguous devices fail closed. |
| V5 Validation | Yes | Bound line bytes before allocation; schema/type/version/sequence validation; reject malformed/unknown/oversized frames without executing an action. |
| V6 Cryptography | Only if Wi-Fi fallback is selected | Use platform TLS and host certificate validation plus a device-scoped credential; do not invent cryptography or disable verification. |

The Phase 1 protocol must expose only bring-up/probe operations and bounded input events. It must not proxy shell commands, raw Herdr methods, credentials, prompts, transcripts, or arbitrary host actions. [VERIFIED: .planning/PROJECT.md] USB device-node access is a local security boundary, not proof of device identity; Wi-Fi adds a LAN boundary and therefore requires authenticated TLS if selected.

## Environment Availability

Availability probing was intentionally not performed because the assignment says to skip all validation commands. The planner must not assume the delivered device is attached, PlatformIO dependencies resolve, pyserial is installed, the user has unprivileged CDC access, or Wi-Fi credentials/test infrastructure are available. Each is a first execution checkpoint with recorded output. There is no acceptable fallback for an unavailable delivered keypad because HARD-01 and HARD-03 require physical evidence.

## Assumptions Log

| # | Claim | Risk if wrong | Required resolution |
|---|---|---|---|
| A1 | [ASSUMED] A 4096-byte encoded line is sufficient for every legal Phase 1 message. | A late larger frame changes memory and protocol bounds. | Serialize worst legal fixtures before freezing the schema; reduce or raise once, record rationale, then rerun proof. |
| A2 | [ASSUMED] The proposed 30-minute/burst/latency profile represents realistic v1 load with adequate margin. | A too-light gate misses failures or a too-strict gate rejects usable USB. | Freeze from actual planned snapshot/event cadence before qualification; preserve the chosen manifest. |
| A3 | [ASSUMED] A stable opaque protocol device ID can be derived or stored so it survives the project's normal flash/reset process. | Pairing breaks after firmware updates or can bind a look-alike unit. | Prove identity across flash, reset, port change, and host restart before making it the persisted contract. |
| A4 | [ASSUMED] Device-initiated authenticated TLS TCP is the single feasible Wi-Fi fallback if USB is disqualified. | Provisioning, memory, or certificate handling may fail the same phase gate. | Implement/test only after repeatable remediated USB failure; block Phase 1 if it does not pass. |

## Open Questions for Execution, Not Pre-Planning Debate

1. What exact PCB/keyboard markings and STM32 firmware version are on the delivered unit?
2. Which logical display/key/LED indices map to each physical position, and which key event is the encoder click?
3. What rotation makes each panel upright from the agreed desk viewing direction?
4. What brightness values are usable, what is the deterministic power-on/reset value, and does any current firmware/library behavior persist it?
5. Which USB connector and interface provide both flashing and runtime CDC, and what VID/PID/serial/interface/by-id properties appear before and after flash/reset?
6. Which narrow udev rule yields unprivileged first-use and later opens without admitting unrelated ACM devices?
7. Does the paired application identity remain exact and stable across flash/reset/unplug/port changes while ambiguity fails closed?
8. What final legal frame bound and product-shaped traffic profile fit with measured internal heap, display latency, and key-poll latency?
9. Does USB pass the frozen strict gate after documented remediation? If not, what exact repeatable failure justifies running the one Wi-Fi fallback?

## Sources

### Primary — official/current
- LILYGO official T-Keyboard-S3-Pro library repository and README: https://github.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library
- LILYGO board-library manifest: https://raw.githubusercontent.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro-Library/master/library.json
- LILYGO legacy official PlatformIO configuration: https://raw.githubusercontent.com/Xinyuan-LilyGO/T-Keyboard-S3-Pro/arduino-esp32-libs_V2.0.14/platformio.ini
- ButtonSense manifest and tags: https://raw.githubusercontent.com/lbuque/ButtonSense/master/library.json and https://github.com/lbuque/ButtonSense/tags
- Espressif Arduino USB CDC documentation: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/usb_cdc.html
- Espressif ESP32-S3 USB Serial/JTAG documentation: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/usb-serial-jtag-console.html
- Espressif ESP32-S3 Wi-Fi driver overview: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/wifi-driver/overview.html
- systemd udev documentation: https://www.freedesktop.org/software/systemd/man/latest/udev.html
- pyserial port tools: https://pyserial.readthedocs.io/en/latest/tools.html

### In-repository authority
- `.planning/phases/01-physical-keypad-and-proven-transport/01-CONTEXT.md:7-39,87-90`
- `.planning/REQUIREMENTS.md:10-14`
- `.planning/ROADMAP.md:18-29`
- `.planning/PROJECT.md`
- `.planning/research/STACK.md`
- `.planning/research/ARCHITECTURE.md`
- `.planning/research/PITFALLS.md`

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — official pins and APIs are sourced, but ButtonSense resolution and delivered-board compatibility remain execution gates.
- Physical mapping: LOW before execution — official topology is known; delivered mapping and revision are deliberately unmeasured.
- USB architecture: MEDIUM — platform feasibility and Linux discovery mechanisms are documented; actual enumeration and reliability are unmeasured.
- Protocol/evidence architecture: MEDIUM — prescriptive and testable, with proposed bounds explicitly logged as assumptions until fixtures and hardware runs freeze them.
- Wi-Fi fallback: LOW until triggered and tested — it must not be selected merely from generic platform support.

**Research date:** 2026-08-16  
**Valid until:** 2026-09-15 for stack pins; physical evidence remains valid only for the recorded unit/build/cable/host combination.
