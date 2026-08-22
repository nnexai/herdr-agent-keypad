"""Measured USB candidate discovery; descriptors never authorize a device."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

EXPECTED_VID = 0x303A
EXPECTED_PID = 0x1001
EXPECTED_SERIAL = "8C:BF:EA:0D:CB:FC"
EXPECTED_CDC_INTERFACE = "01"
EXPECTED_HID_INTERFACE = "00"


class DiscoveryError(RuntimeError):
    """A discovery state that must not select a device."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Candidate:
    """A USB candidate snapshot. ``device`` is always discovery-only."""

    device: str
    vid: int | None
    pid: int | None
    serial_number: str | None
    location: str | None
    manufacturer: str | None
    product: str | None
    interface: str | None

    @property
    def compatible(self) -> bool:
        return (
            self.vid == EXPECTED_VID
            and self.pid == EXPECTED_PID
            and self.serial_number == EXPECTED_SERIAL
            and _interface_number(self.interface, self.location) == EXPECTED_CDC_INTERFACE
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "vid": self.vid,
            "pid": self.pid,
            "serial_number": self.serial_number,
            "location": self.location,
            "manufacturer": self.manufacturer,
            "product": self.product,
            "interface": self.interface,
            "compatible": self.compatible,
        }


def _interface_number(value: Any, location: Any = None) -> str | None:
    """Normalize pyserial's ``ifNN`` or Linux location interface number."""
    for raw in (value, location):
        if raw is None:
            continue
        text = str(raw)
        if text.startswith("if"):
            text = text[2:]
        elif ":" in text:
            text = text.rsplit(":", 1)[1]
            if "." in text:
                text = text.rsplit(".", 1)[1]
        if text.isdigit():
            return f"{int(text):02d}"
    return None


def candidate_from_port(port: Any) -> Candidate:
    location = getattr(port, "location", None)
    return Candidate(
        device=str(getattr(port, "device", "")),
        vid=getattr(port, "vid", None),
        pid=getattr(port, "pid", None),
        serial_number=getattr(port, "serial_number", None),
        location=location,
        manufacturer=getattr(port, "manufacturer", None),
        product=getattr(port, "product", None),
        interface=_interface_number(getattr(port, "interface", None), location),
    )


def enumerate_candidates(ports: Iterable[Any] | None = None) -> list[Candidate]:
    """Return measured compatible candidates without selecting one.

    The returned list is intentionally not ordered for authorization. A caller
    must complete the application hello and exact identity check before opening
    a candidate; descriptor/path equality and first-match order are insufficient.
    """
    if ports is None:
        import serial.tools.list_ports

        ports = serial.tools.list_ports.comports()
    candidates = [candidate_from_port(port) for port in ports if getattr(port, "device", None)]
    return [candidate for candidate in candidates if candidate.compatible]


def require_candidate_set(candidates: Iterable[Candidate]) -> list[Candidate]:
    result = list(candidates)
    if not result:
        raise DiscoveryError("zero", "No keypad detected")
    return result


def exact_identity_candidate(
    candidates: Iterable[Candidate],
    hello_by_device: dict[str, dict[str, Any]],
    expected_device_id: str,
) -> Candidate:
    """Authorize exactly one candidate by its application hello identity."""
    candidate_list = require_candidate_set(candidates)
    matches: list[Candidate] = []
    for candidate in candidate_list:
        hello = hello_by_device.get(candidate.device)
        if not isinstance(hello, dict):
            continue
        if hello.get("device_id") == expected_device_id and hello.get("protocol") == 1:
            matches.append(candidate)
    if len(candidate_list) > 1 and len(matches) != 1:
        raise DiscoveryError("ambiguous", "Multiple compatible keypads detected. Disconnect other candidates and retry; no device was paired.")
    if len(matches) != 1:
        raise DiscoveryError("mismatch", "The connected keypad does not match the paired device. Reconnect the paired keypad.")
    return matches[0]


def discovery_check() -> None:
    class Port:
        def __init__(self, device: str, location: str):
            self.device = device
            self.vid = EXPECTED_VID
            self.pid = EXPECTED_PID
            self.serial_number = EXPECTED_SERIAL
            self.location = location
            self.manufacturer = "Espressif"
            self.product = "USB composite CDC + keyboard"
            self.interface = "if01"

    first = Port("/dev/ttyACM9", "1-2:1.1")
    second = Port("/dev/ttyACM0", "1-1:1.1")
    candidates = enumerate_candidates([first, second])
    if [candidate.device for candidate in candidates] != ["/dev/ttyACM9", "/dev/ttyACM0"]:
        raise AssertionError("candidate descriptor facts were not preserved")
    try:
        exact_identity_candidate(
            candidates,
            {
                first.device: {"device_id": "paired", "protocol": 1},
                second.device: {"device_id": "paired", "protocol": 1},
            },
            "paired",
        )
    except DiscoveryError as exc:
        if exc.code != "ambiguous":
            raise
    else:
        raise AssertionError("two exact identities must fail closed")
    chosen = exact_identity_candidate(
        candidates,
        {
            first.device: {"device_id": "other", "protocol": 1},
            second.device: {"device_id": "paired", "protocol": 1},
        },
        "paired",
    )
    if chosen.device != second.device:
        raise AssertionError("exact application identity did not select the paired candidate")
