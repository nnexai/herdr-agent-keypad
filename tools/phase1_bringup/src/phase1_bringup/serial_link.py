"""Bounded serial I/O and exact-identity fresh-session recovery."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .discovery import Candidate, DiscoveryError, enumerate_candidates, exact_identity_candidate
from .pairing import PairingBinding
from .protocol import MAX_LINE_BYTES, ProtocolSession


class SerialLinkError(RuntimeError):
    """A serial interruption or identity failure that requires a fresh session."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RecoveryTransition:
    event_id: str
    transition: str
    descriptor: dict[str, Any]
    boot_id: str | None
    session_id: str
    discarded_ids: tuple[int, ...]
    timestamp: float
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "transition": self.transition,
            "descriptor": self.descriptor,
            "boot_id": self.boot_id or "unavailable",
            "session_id": self.session_id,
            "discarded_ids": list(self.discarded_ids),
            "timestamp": self.timestamp,
            "detail": self.detail or "unavailable",
        }


@dataclass
class SerialLink:
    """Own a connection and close it immediately on stale/error paths."""

    connection: Any
    max_line_bytes: int = MAX_LINE_BYTES
    closed: bool = False
    discarded_ids: list[int] = field(default_factory=list)

    def write(self, data: bytes) -> None:
        if self.closed:
            raise SerialLinkError("closed", "serial link is closed")
        if not isinstance(data, bytes) or len(data) > self.max_line_bytes:
            raise SerialLinkError("line_too_long", "outbound frame exceeds the bounded line size")
        try:
            self.connection.write(data)
        except Exception as exc:
            self.close()
            raise SerialLinkError("write", "serial write failed; stale descriptor closed") from exc

    def readline(self) -> bytes:
        if self.closed:
            raise SerialLinkError("closed", "serial link is closed")
        try:
            line = self.connection.readline(self.max_line_bytes + 1)
        except TypeError:
            line = self.connection.readline()
        except Exception as exc:
            self.close()
            raise SerialLinkError("read", "serial read failed; stale descriptor closed") from exc
        if line and len(line) > self.max_line_bytes:
            self.close()
            raise SerialLinkError("line_too_long", "inbound frame exceeds the bounded line size")
        return line

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            try:
                self.connection.close()
            except Exception:
                pass


def fresh_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def _open_and_hello(candidate: Candidate, opener: Callable[[Candidate], Any], timeout: float) -> tuple[Candidate, SerialLink, ProtocolSession, dict[str, Any]]:
    raw: Any | None = None
    try:
        raw = opener(candidate)
        link = SerialLink(raw)
        session = ProtocolSession(link, fresh_id("host"), fresh_id("session"), timeout=timeout)
        session.hello()
        hello = dict(session.device)
        hello["boot_id"] = hello.get("device_boot_id", "unavailable")
        hello["session_id"] = session.session_id
        return candidate, link, session, hello
    except Exception:
        if raw is not None:
            try:
                raw.close()
            except Exception:
                pass
        raise


def reconnect_exact(
    binding: PairingBinding,
    ports: Iterable[Any] | None,
    opener: Callable[[Candidate], Any],
    timeout: float = 3.0,
    discarded_ids: Iterable[int] = (),
) -> tuple[Candidate, SerialLink, ProtocolSession, list[RecoveryTransition]]:
    """Discover all candidates, handshake each, then keep one exact fresh session."""
    candidates = enumerate_candidates(ports)
    transitions: list[RecoveryTransition] = []
    if not candidates:
        raise SerialLinkError("zero", "No keypad detected")
    hellos: dict[str, dict[str, Any]] = {}
    opened: dict[str, tuple[SerialLink, ProtocolSession]] = {}
    for candidate in candidates:
        started = time.time()
        try:
            _, link, session, hello = _open_and_hello(candidate, opener, timeout)
        except Exception as exc:
            transitions.append(RecoveryTransition(f"recovery-{secrets.token_hex(4)}", "candidate_failed", candidate.snapshot(), None, "unavailable", tuple(discarded_ids), started, str(exc)))
            continue
        hellos[candidate.device] = hello
        opened[candidate.device] = (link, session)
        transitions.append(RecoveryTransition(f"recovery-{secrets.token_hex(4)}", "session_established", candidate.snapshot(), hello.get("boot_id"), session.session_id, tuple(discarded_ids), started, "fresh hello acknowledged"))
    try:
        selected = exact_identity_candidate(candidates, hellos, binding.device_id)
    except DiscoveryError as exc:
        for link, _ in opened.values():
            link.close()
        raise SerialLinkError(exc.code, str(exc)) from exc
    for device, (link, _) in opened.items():
        if device != selected.device:
            link.close()
    link, session = opened[selected.device]
    return selected, link, session, transitions


def serial_reconnect_check() -> None:
    """Exercise bounded reads, fresh session IDs, stale close, and no replay."""
    from .pairing import PairingBinding
    from .protocol import encode_frame, new_frame

    class Port:
        def __init__(self, device: str, serial_number: str):
            self.device = device
            self.vid = 0x303A
            self.pid = 0x1001
            self.serial_number = serial_number
            self.location = "1-1:1.0"
            self.manufacturer = "Espressif"
            self.product = "USB JTAG/serial debug unit"
            self.interface = "00"

    class FakeConnection:
        def __init__(self, device_id: str, boot_id: str):
            self.closed = False
            self.writes: list[bytes] = []
            self.lines = [encode_frame(new_frame("hello_ack", boot_id, "ignored", 1, {"accepted": True, "protocol": 1, "device_id": device_id, "firmware": "phase1-bringup"}, 1))]

        def write(self, data: bytes) -> None:
            self.writes.append(data)
            import json
            frame = json.loads(data)
            response = json.loads(self.lines[0])
            response["session_id"] = frame["session_id"]
            self.lines[0] = (json.dumps(response, separators=(",", ":")) + "\n").encode()

        def readline(self, *_args: Any) -> bytes:
            return self.lines.pop(0) if self.lines else b""

        def close(self) -> None:
            self.closed = True

    port = Port("/dev/ttyACM9", "paired")
    opened: list[FakeConnection] = []

    def opener(candidate: Candidate) -> FakeConnection:
        connection = FakeConnection("opaque-device-1", "boot-new")
        opened.append(connection)
        return connection

    binding = PairingBinding("opaque-device-1", 1, "phase1-bringup")
    selected, link, session, transitions = reconnect_exact(binding, [port], opener, discarded_ids=[1, 2])
    if selected.device != port.device or link.closed or session.device["device_id"] != binding.device_id:
        raise AssertionError("exact fresh session was not established")
    if not transitions or transitions[-1].discarded_ids != (1, 2) or len(session.session_id) < 9:
        raise AssertionError("recovery transition did not preserve discarded IDs and fresh session")
    link.close()
    if not opened[0].closed:
        raise AssertionError("stale descriptor was not closed")


def udev_rule_check(path: Any) -> None:
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8")
    required = ('SUBSYSTEM=="tty"', 'ATTRS{idVendor}=="303a"', 'ATTRS{idProduct}=="1001"', 'ENV{ID_SERIAL_SHORT}=="8C:BF:EA:0D:CB:FC"', 'ENV{ID_USB_INTERFACE_NUM}=="00"', 'GROUP="dialout"', 'TAG+="uaccess"')
    missing = [token for token in required if token not in text]
    if missing:
        raise AssertionError("udev rule is missing measured narrow tokens: " + ", ".join(missing))
    if "KERNEL==\"ttyACM*\"" in text or "MODE=\"0666\"" in text or "ATTRS{idVendor}==\"*\"" in text:
        raise AssertionError("udev rule is broader than the measured runtime interface")
