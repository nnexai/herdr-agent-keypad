#!/usr/bin/env python3
"""Capture one composed 128x128 keypad panel directly from the USB framebuffer."""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "phase1_bringup" / "src"))

from phase1_bringup.pairing import PairingStore
from phase1_bringup.serial_link import reconnect_exact

PIXELS = 128 * 128
BYTES = PIXELS * 2
HEADER = b"SCREENSHOT-RGB565\n"

THEMES = {
    "signal-edge": "0",
    "ledger": "1",
    "beacon": "2",
    "instrument": "3",
}
SCENES = {
    "current": "C",
    "blocked": "B",
    "unseen": "U",
    "working": "W",
    "idle": "I",
    "settled": "S",
    "unknown": "Q",
    "empty": "E",
    "stale": "T",
    "offline": "O",
    "unavailable": "A",
    "pending": "P",
    "focused": "F",
    "rejected": "R",
    "vanished": "V",
    "uncertain": "N",
    "failed": "X",
    "sync": "Y",
    "menu-theme": "M",
    "menu-led": "L",
    "codex-current": "c",
    "codex-partial": "p",
    "codex-stale": "s",
    "codex-unavailable": "u",
    "codex-auth": "a",
    "codex-offline": "o",
    "host-offline": "h",
    "codex-limit": "l",
    "codex-long": "g",
    "menu-root-0": "0",
    "menu-root-1": "1",
    "menu-root-2": "2",
    "menu-root-3": "3",
    "menu-root-4": "4",
    "menu-root-5": "5",
    "menu-brightness": "b",
    "menu-health": "e",
    "menu-about": "d",
    "slots-0": "0",
    "slots-1": "1",
    "slots-2": "2",
    "slots-3": "3",
}
LEVELS = {"full": "F", "half": "H", "static": "S"}


def read_exact(connection: object, count: int, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while len(data) < count and time.monotonic() < deadline:
        chunk = connection.read(count - len(data))  # type: ignore[attr-defined]
        if chunk:
            data.extend(chunk)
    if len(data) != count:
        raise TimeoutError(f"screenshot payload truncated: {len(data)}/{count} bytes")
    return bytes(data)


def ppm_from_rgb565(raw: bytes) -> bytes:
    pixels = bytearray(PIXELS * 3)
    for index in range(PIXELS):
        value = (raw[index * 2] << 8) | raw[index * 2 + 1]
        r = ((value >> 11) & 0x1F) * 255 // 31
        g = ((value >> 5) & 0x3F) * 255 // 63
        b = (value & 0x1F) * 255 // 31
        offset = index * 3
        pixels[offset:offset + 3] = bytes((r, g, b))
    return f"P6\n128 128\n255\n".encode("ascii") + pixels


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("panel", type=int, choices=range(4), help="zero-based panel index")
    parser.add_argument("output", type=Path)
    parser.add_argument("--binding", type=Path, default=Path.home() / ".config/herdr/keypad-binding.json")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--theme", choices=THEMES)
    parser.add_argument("--scene", choices=SCENES, default="current")
    parser.add_argument("--level", choices=LEVELS, default="full")
    parser.add_argument("--phase", type=int, choices=range(8), default=0)
    args = parser.parse_args()

    binding = PairingStore(args.binding).load()
    if binding is None:
        raise RuntimeError(f"pairing binding missing: {args.binding}")
    selected, link, session, _ = reconnect_exact(
        binding,
        ports=None,
        opener=lambda candidate: __import__("serial").Serial(candidate.device, 115200, timeout=0.2, write_timeout=2.0),
        timeout=args.timeout,
    )
    try:
        hello_firmware = session.device.get("firmware")
        hello_protocol = session.device.get("protocol")
        if hello_firmware != binding.firmware or hello_protocol != binding.protocol:
            raise RuntimeError(
                "fresh hello does not match paired firmware/protocol identity"
            )
        stimulus = f"CAPTURE:{args.panel}"
        if (
            args.theme is not None
            or args.scene != "current"
            or args.level != "full"
            or args.phase != 0
        ):
            theme = THEMES[args.theme or "signal-edge"]
            stimulus = (
                f"{stimulus}:{theme}:{SCENES[args.scene]}:"
                f"{LEVELS[args.level]}:{args.phase}"
            )
        payload = {"panel": args.panel + 1, "step_id": "screen-capture", "stimulus": stimulus}
        frame, _fact = session.request("probe", payload, {"probe_ack"})
        if not frame["payload"].get("accepted"):
            raise RuntimeError("device rejected screen capture")
        marker = read_exact(link.connection, len(HEADER), args.timeout)
        if marker != HEADER:
            raise RuntimeError(f"unexpected capture marker: {marker!r}")
        raw = read_exact(link.connection, BYTES, args.timeout)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(ppm_from_rgb565(raw))
        args.output.with_suffix(args.output.suffix + ".rgb565").write_bytes(raw)
        print(f"captured panel {args.panel} from {selected.device} to {args.output}")
    finally:
        link.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
