# Phase 1: Physical Keypad and Proven Transport — Final Pattern Map

**Mapped:** 2026-08-16  
**State:** Reconciled to strict-split Plans 01-01 through 01-08  
**Analogs found:** none; the repository has planning inputs but no implementation source

The plan set is authoritative for the final implementation layout below. Every path uses the isolated `tools/phase1_bringup` src-layout package approved by the Walking Skeleton. Research and UI contracts remain the implementation fallback because there is no neighboring code convention to copy.

## Final File Classification

| File | Role / flow | Plan | Pattern source |
|---|---|---:|---|
| `platformio.ini` | reproducible hardware/native/selected build composition | 01, 05, 07, 08 | RESEARCH dependency and single-transport constraints |
| `firmware/src/main.cpp` | actual firmware composition/controller | 01, 02, 04, 06, 07, 08 | RESEARCH cooperative-loop pattern |
| `firmware/src/board/board_adapter.h` | Pro-only provider interface | 02 | RESEARCH official board wrapper |
| `firmware/src/board/board_adapter.cpp` | sequential Pro-only provider | 02 | RESEARCH official board wrapper |
| `firmware/src/board/physical_map.h` | observed/unavailable physical model | 02 | CONTEXT D-03, RESEARCH physical map |
| `firmware/src/ui/bringup_renderer.h` | bounded header-only renderer | 02 | UI-SPEC device surface |
| `firmware/src/protocol/protocol.h` | consolidated bounded codec/session API | 05 | RESEARCH protocol/session contract |
| `firmware/src/protocol/protocol.cpp` | consolidated bounded codec/session implementation | 05 | RESEARCH protocol/session contract |
| `firmware/src/transport/link.h` | byte/link-event-only interface | 06 | RESEARCH single adapter boundary |
| `firmware/src/transport/usb_cdc.cpp` | USB adapter | 06, 08 | D-05 through D-08 |
| `firmware/src/transport/wifi_tls.cpp` | conditional station/mutual-TLS adapter | 07, 08 | D-08 fallback/security research |
| `firmware/src/metrics/proof_metrics.h` | fixed-width proof metrics | 06 | D-05/D-06 research |
| `firmware/src/security/pairing_credentials.h` | transactional credential API | 07 | security threat boundary |
| `firmware/src/security/pairing_credentials.cpp` | encrypted-NVS station/TLS lifecycle | 07 | security threat boundary |
| `protocol/schema/v1.json` | closed v1 protocol schema | 01, 05 | RESEARCH bounded NDJSON |
| `protocol/fixtures/v1-golden.json` | canonical valid/typed-invalid fixtures | 05 | cross-language parity |
| `test/protocol/test_main.cpp` | PlatformIO native production-code fixture runner | 05 | runnable golden verification |
| `tools/phase1_bringup/pyproject.toml` | Python 3.11 src-layout package | 01 | Walking Skeleton host environment |
| `tools/phase1_bringup/requirements.lock` | pinned pyserial 3.5 | 01 | RESEARCH dependency gate |
| `tools/phase1_bringup/src/phase1_bringup/__main__.py` | exact module CLI/controller | 01, 03, 04, 08 | D-01/D-02 guided command |
| `tools/phase1_bringup/src/phase1_bringup/guide.py` | eleven-gate guided state machine | 03, 04 | D-02/UI-SPEC |
| `tools/phase1_bringup/src/phase1_bringup/ui.py` | approved 80x24 terminal UI | 03 | UI-SPEC host surface |
| `tools/phase1_bringup/src/phase1_bringup/protocol.py` | host codec/session and fixture runner | 03, 05 | shared v1 contract |
| `tools/phase1_bringup/src/phase1_bringup/discovery.py` | descriptor-only candidate discovery | 04 | D-10/D-11 |
| `tools/phase1_bringup/src/phase1_bringup/pairing.py` | physical device pairing and conditional no-echo provisioning | 04, 07 | D-10 and fallback credential boundary |
| `tools/phase1_bringup/src/phase1_bringup/serial_link.py` | exact-device bounded USB link/recovery | 04 | D-07/D-11/D-12 |
| `tools/phase1_bringup/src/phase1_bringup/evidence.py` | atomic immutable evidence writer/verifier | 01, 03, 04, 08 | evidence-first qualification |
| `tools/phase1_bringup/src/phase1_bringup/qualification.py` | frozen profile/result/link validator | 06, 07 | D-05/D-06/D-08 |
| `tools/phase1_bringup/src/phase1_bringup/wifi_tls.py` | conditional host mutual-TLS link/negative checks | 07 | fallback security contract |
| `tools/phase1_bringup/ARCHIVED` | final secret-free archive marker | 08 | D-04 |
| `host/udev/99-herdr-keypad.rules` | measured narrow ordinary-user policy | 04 | D-09 |

## Deliberate Consolidations

### Header-only `bringup_renderer.h`

The final plans intentionally omit `bringup_renderer.cpp`. `BringupRenderer` owns no independent state or resource lifetime: it is a small bounded set of fixed-width render inputs and short drawing operations called sequentially through `BoardAdapter`. Keeping that contract header-only makes the renderer states and their 128x128 bounds visible at the call site and avoids a second table/translation unit. This is deliberate, not an omitted implementation. If implementation growth introduces independent state or large drawing bodies, the executor must stop rather than silently create a second convention; a source split would require a plan change.

### Consolidated `protocol.{h,cpp}`

The final plans intentionally consolidate the earlier proposed `frame_codec.{h,cpp}` and `session.{h,cpp}` into `protocol.{h,cpp}`. FrameCodec and ProtocolSession share one fixed buffer policy, typed rejection enum, digest/correlation rules, and session-owned sequence/deduplication state. A single bounded module keeps those invariants atomic and is still independently exercised by the native production-code fixture harness. `Link` remains separate and carries bytes/events only, preserving transport neutrality. This is a deliberate consolidation, not collapsed test coverage.

### Relocated host package

All stale `host/bringup/*` and `host/pyproject.toml` mappings are replaced by `tools/phase1_bringup/*`. The temporary utility is intentionally isolated from permanent host/product code, runs only as `tools/phase1_bringup/.venv/bin/python -m phase1_bringup`, uses a src layout, and is archived after Phase 1. `host/` retains only the measured udev policy because that is host-system configuration rather than Python package code.

## File-Specific Contracts

### Build and composition

`platformio.ini` pins pioarduino 55.03.311, Arduino-ESP32 3.3.11, immutable official T-Keyboard-S3-Pro 0.1.0 source, verified ButtonSense commit, and Hardware CDC flags. It also defines:

- `native`: PlatformIO native + Unity, `test_filter = protocol`, production `firmware/src/protocol/protocol.cpp`, exact project fixture path.
- `wifi-candidate`: includes `wifi_tls.cpp`, excludes `usb_cdc.cpp`, and makes `main.cpp` instantiate only `WifiTlsLink`.
- final selected environments: mutually exclusive source filters/build selector; invalid/both/missing selection fails; the unselected implementation/object/symbol is absent.

`firmware/src/main.cpp` is always the actual consumer/composition point. It receives exactly one static `Link` implementation and passes it to the same ProtocolSession/guide loop. There is no runtime registry, dormant alternate, hybrid arbitration, or failover.

### Sequential hardware and UI

Use only the pinned official `TKeyboardS3Pro` abstraction and returned ButtonSense objects. Call regular update, access one panel at a time, clear stale content, keep inactive panels at WAIT, and represent meaning with labels/geometry in addition to color. Host text cannot change the fixed 4 px inset or 128x128 layout. Physical PASS always requires current-step machine fact plus explicit human Y; acknowledgements never establish physical truth.

### Bounded protocol and native proof

The order is:

```text
count encoded bytes -> reject overlong -> parse -> closed schema/version
-> boot/session/sequence/digest/correlation -> typed dispatch
```

`test/protocol/test_main.cpp` must open the exact `protocol/fixtures/v1-golden.json`, fail on missing/empty input, iterate every vector, and exercise production `protocol.cpp`. Host `protocol.py` consumes the same schema/fixture. Fresh boot/session discards uncertain work; no debug text enters the framed stream.

### Exact-device binding and recovery

Descriptor facts narrow candidates only. A fresh challenge displayed on the intended keypad authorizes stable opaque `device_id`; zero, many, mismatch, incompatible, and look-alike cases fail closed. The measured udev rule grants ordinary-user access without wildcarding ACM devices. Reset, normal flash/reset, port move, endpoint renumbering, and utility restart close stale endpoints and establish fresh exact-device sessions without replay. Full reboot/suspend/product resynchronization remain Phase 4.

### Evidence-first qualification and exact selection

EvidenceWriter atomically writes, hashes, reopens, schema-validates, and hash-validates real artifacts; failed attempts are immutable. Qualification freezes and hashes `artifacts/phase1/qualification-manifest.json` before traffic. Its common matrix has distinct rows for software reset, normal flash/reset, same-port reconnect, different-port reconnect, forced endpoint renumbering when available, host-utility restart, and reset/unplug. Every candidate result contains every row; only genuine transport-inapplicability receives a reasoned `N/A`. Each immutable run traffic result embeds the exact manifest path/hash and schema/fixture hashes. `latest/result.json` is only a pointer containing an immutable target path/hash.

The runnable resolver validates pointer schema/hash, rejects escape/symlinks, opens and hash-validates the concrete target, and emits a fixed lock before any dependent read. Selection consumes that lock, the exact frozen manifest, and validated USB/Wi-Fi eligibility locks; it never consumes a mutable summary. USB wins on strict pass; Wi-Fi is eligible only after hash-validated repeatable remediated USB failure and then must pass the identical complete profile. The immutable selection lock names exactly `selected-usb` or `selected-wifi`. The build resolver validates it, reads only the selected adapter source, invokes that exact environment, and proves the unselected source/object/symbol absent. The exact final binary is then flashed and run through the frozen physical qualification; its new immutable result cross-hashes the final firmware build, selection, and manifest. Only validation of that strict result permits ARCHIVED. No post-hoc threshold rewrite is permitted.

### Conditional station/TLS credential lifecycle

Only the evidence-eligible Wi-Fi branch may collect credentials. `pairing.py` uses bounded no-echo input and a fresh physically confirmed exact-device USB session. Supported station input is bounded SSID plus explicit supported network-auth material; malformed/unsupported/overflow input fails before transfer. Device storage is encrypted, generation-versioned, staged, readback-verified, and atomically activated only after AP authentication, IP acquisition, and mutual TLS. Update and clear require fresh confirmation. Any transfer/AP/TLS/commit failure rolls back to prior generation or none and clears staging.

SSID, passphrase/PSK, private keys, certificate bodies, secret-bearing errors, and reversible encodings never appear in UI, logs, evidence, results, summaries, or ARCHIVED. Evidence contains only opaque generation identifiers, public fingerprints, redacted outcomes, timestamps, and hashes. Positive/negative and canary scans cover create/update/clear, malformed/oversized input, stale/mismatched session, every partial-failure boundary, AP-auth rejection, untrusted host/device, wrong device_id, changed peer, and reconnect.

## Shared UI and Error Vocabulary

Apply the complete `01-UI-SPEC.md` contract: fixed Identify → Displays → Keys → Encoder → LEDs → Brightness → Reboot → Pair → Recover → Traffic → Selection order; exact `No keypad detected` and blocked/selection copy; one active instruction; elapsed bounded operations; disabled confirmation until stable; 80x24 minimum; long host text wraps and prior evidence scrolls; displayed identity is abbreviated; inactive panels show WAIT. Distinguish `observed`, `recorded`, `acknowledged`, `selected`, and literal `unavailable`. Errors state the problem, safe next action, and whether evidence was preserved without echoing secrets.

## No Analog Found

No implementation files existed when mapping. Executors must follow the pinned official APIs, `01-RESEARCH.md`, `01-UI-SPEC.md`, the threat models, and these final path/contract assignments rather than inventing a neighboring convention. The strict-split plan boundaries are vertical and sequential: tracer; firmware physical surface; host-confirmed map; exact-device recovery; runnable protocol parity; USB qualification; conditional Wi-Fi security qualification; exact selection/composition/archive.
