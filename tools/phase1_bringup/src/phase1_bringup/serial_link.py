"""Bounded serial I/O and exact-identity fresh-session recovery."""
from __future__ import annotations

import fcntl
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .discovery import Candidate, DiscoveryError, enumerate_candidates, exact_identity_candidate
from .pairing import PairingBinding
from .protocol import MAX_LINE_BYTES, ProtocolSession


def phase31_bridge_lock_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return Path(runtime or (Path.home() / ".cache")) / "herdr-keypad" / "bridge.lock"


def require_inherited_bridge_lock() -> None:
    """Require the run-exclusive bridge lock before opening an exact device."""
    if os.environ.get("HERDR_KEYPAD_EXCLUSIVE_LOCK") != "1":
        raise RuntimeError("Phase 03.1 serial requires run-exclusive bridge lock")
    fd_path = "/proc/self/fd/9"
    try:
        if fcntl.fcntl(9, fcntl.F_GETFD) & fcntl.FD_CLOEXEC:
            raise RuntimeError("Phase 03.1 serial lock fd 9 was not inherited")
        target = os.readlink(fd_path)
    except (OSError, ValueError) as exc:
        raise RuntimeError("Phase 03.1 serial lock fd 9 is not inherited") from exc
    expected = os.fspath(phase31_bridge_lock_path())
    if target != expected:
        raise RuntimeError("Phase 03.1 serial lock fd 9 does not name the bridge lock")
    try:
        fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise RuntimeError("Phase 03.1 serial bridge lock is not held") from exc


class SerialLinkError(RuntimeError):
    """A serial interruption or identity failure that requires a fresh session."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


RECOVERY_ACTIONS = (
    "software-reset",
    "normal-flash-reset",
    "same-port-reconnect",
    "different-port-reconnect",
    "forced-endpoint-renumbering",
    "host-utility-restart",
    "reset-unplug",
)

_RECOVERY_ACTION_ALIASES = {
    "reset": "software-reset",
    "normal-flash-reset": "normal-flash-reset",
    "port-move": "different-port-reconnect",
    "endpoint-renumber": "forced-endpoint-renumbering",
    "utility-restart": "host-utility-restart",
}

_RECOVERY_EXPECTATIONS = {
    "software-reset": {"boot_changed": True, "session_changed": True, "endpoint": "same"},
    "normal-flash-reset": {"boot_changed": True, "session_changed": True, "endpoint": "same"},
    "same-port-reconnect": {"boot_changed": True, "session_changed": True, "endpoint": "same"},
    "different-port-reconnect": {"boot_changed": True, "session_changed": True, "endpoint": "different"},
    "forced-endpoint-renumbering": {"boot_changed": True, "session_changed": True, "endpoint": "renumbered"},
    "host-utility-restart": {"boot_changed": False, "session_changed": True, "endpoint": "same"},
    "reset-unplug": {"boot_changed": True, "session_changed": True, "endpoint": "same"},
}


def canonical_recovery_action(action: str) -> str:
    if not isinstance(action, str):
        raise SerialLinkError("invalid_action", "recovery action must be text")
    canonical = _RECOVERY_ACTION_ALIASES.get(action, action)
    if canonical not in RECOVERY_ACTIONS:
        raise SerialLinkError("invalid_action", f"unsupported recovery action: {action}")
    return canonical

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
    action: str | None = None
    pre: dict[str, Any] | None = None
    post: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        value = {
            "event_id": self.event_id,
            "transition": self.transition,
            "descriptor": self.descriptor,
            "boot_id": self.boot_id or "unavailable",
            "session_id": self.session_id,
            "discarded_ids": list(self.discarded_ids),
            "timestamp": self.timestamp,
            "detail": self.detail or "unavailable",
        }
        if self.action is not None:
            value["action"] = self.action
        if self.pre is not None:
            value["pre"] = self.pre
        if self.post is not None:
            value["post"] = self.post
        return value


def validate_recovery_action_event(event: Any, action: str, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate one measured, action-specific interruption transition."""
    action = canonical_recovery_action(action)
    if not isinstance(event, dict):
        raise SerialLinkError("invalid_transition", "recovery transition must be an object")
    required = {"event_id", "action", "pre", "post", "descriptor", "discarded_ids", "detail"}
    if not required.issubset(event) or event["action"] != action:
        raise SerialLinkError("invalid_transition", "recovery transition action facts are incomplete")
    pre, post = event["pre"], event["post"]
    for label, value in (("pre", pre), ("post", post)):
        if not isinstance(value, dict) or not isinstance(value.get("device_id"), str) or not value["device_id"]:
            raise SerialLinkError("invalid_transition", f"{label} device identity is missing")
        if not isinstance(value.get("boot_id"), str) or not value["boot_id"]:
            raise SerialLinkError("invalid_transition", f"{label} boot identity is missing")
        if not isinstance(value.get("session_id"), str) or not value["session_id"]:
            raise SerialLinkError("invalid_transition", f"{label} session identity is missing")
        if not isinstance(value.get("endpoint"), dict):
            raise SerialLinkError("invalid_transition", f"{label} endpoint facts are missing")
    if pre["device_id"] != post["device_id"]:
        raise SerialLinkError("identity_mismatch", "recovery changed the paired device identity")
    if previous is not None and pre["session_id"] != previous.get("session_id"):
        raise SerialLinkError("session_mismatch", "recovery precondition does not name the active session")
    expected = _RECOVERY_EXPECTATIONS[action]
    if expected["boot_changed"] and pre["boot_id"] == post["boot_id"]:
        raise SerialLinkError("boot_unchanged", f"{action} requires a fresh device boot")
    if not expected["boot_changed"] and not pre["boot_id"] == post["boot_id"]:
        raise SerialLinkError("boot_unexpected", f"{action} must not claim a device reboot")
    if pre["session_id"] == post["session_id"]:
        raise SerialLinkError("session_unchanged", f"{action} requires a fresh host session")
    before_endpoint = pre["endpoint"]
    after_endpoint = post["endpoint"]
    if expected["endpoint"] == "same" and before_endpoint != after_endpoint:
        raise SerialLinkError("endpoint_mismatch", f"{action} requires the same endpoint")
    if expected["endpoint"] == "different" and before_endpoint == after_endpoint:
        raise SerialLinkError("endpoint_mismatch", f"{action} requires a different endpoint")
    if expected["endpoint"] == "renumbered" and before_endpoint.get("path") == after_endpoint.get("path"):
        raise SerialLinkError("endpoint_mismatch", f"{action} requires endpoint renumbering")
    discarded = event["discarded_ids"]
    if not isinstance(discarded, list) or not discarded or any(not isinstance(item, int) or item < 0 for item in discarded):
        raise SerialLinkError("discarded_ids_missing", "uncertain in-flight IDs must be explicitly discarded")
    if not isinstance(event["descriptor"], dict) or event["descriptor"].get("device_id") not in {pre["device_id"], post["device_id"]}:
        raise SerialLinkError("identity_mismatch", "descriptor is not bound to the paired opaque identity")
    return event


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
        if not isinstance(data, bytes) or not data or len(data) > self.max_line_bytes:
            raise SerialLinkError("line_too_long", "outbound frame exceeds the bounded line size")
        offset = 0
        try:
            while offset < len(data):
                count = self.connection.write(data[offset:])
                if not isinstance(count, int) or count <= 0 or count > len(data) - offset:
                    raise SerialLinkError("short_write", "serial write did not accept the complete frame")
                offset += count
        except SerialLinkError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise SerialLinkError("write", "serial write failed; stale descriptor closed") from exc

    def readline(self) -> bytes:
        if self.closed:
            raise SerialLinkError("closed", "serial link is closed")
        try:
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

        def write(self, data: bytes) -> int:
            self.writes.append(data)
            import json
            frame = json.loads(data)
            response = json.loads(self.lines[0])
            response["session_id"] = frame["session_id"]
            self.lines[0] = (json.dumps(response, separators=(",", ":")) + "\n").encode()
            return len(data)

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
    class ShortConnection:
        def __init__(self):
            self.closed = False

        def write(self, data: bytes) -> int:
            return max(0, len(data) - 1)

        def close(self) -> None:
            self.closed = True

    short = ShortConnection()
    try:
        SerialLink(short).write(b"abcd")
    except SerialLinkError as exc:
        if exc.code != "short_write" or not short.closed:
            raise AssertionError("short write did not close the stale descriptor")
    else:
        raise AssertionError("short write was accepted")

    class FailingReadConnection:
        def __init__(self):
            self.closed = False

        def readline(self, *_args: Any) -> bytes:
            if _args:
                raise TypeError("legacy readline signature")
            raise OSError("descriptor failed")

        def close(self) -> None:
            self.closed = True

    failing = FailingReadConnection()
    try:
        SerialLink(failing).readline()
    except SerialLinkError as exc:
        if exc.code != "read" or not failing.closed:
            raise AssertionError("read exception did not close the stale descriptor")
    else:
        raise AssertionError("read exception was accepted")
def recovery_action_matrix_check() -> None:
    """Exercise every named D-12 action and its distinct transition invariant."""
    base = {
        "event_id": "recovery-test",
        "descriptor": {"device_id": "opaque-device-1", "path": "/dev/ttyACM0"},
        "discarded_ids": [1, 2],
        "detail": "measured",
    }
    for action in RECOVERY_ACTIONS:
        expectation = _RECOVERY_EXPECTATIONS[action]
        pre_endpoint = {"path": "/dev/ttyACM0", "location": "1-1:1.0"}
        post_endpoint = dict(pre_endpoint)
        if expectation["endpoint"] == "different":
            post_endpoint["path"] = "/dev/ttyACM1"
        elif expectation["endpoint"] == "renumbered":
            post_endpoint["path"] = "/dev/ttyACM2"
        event = {
            **base,
            "action": action,
            "pre": {
                "device_id": "opaque-device-1",
                "boot_id": "boot-before" if expectation["boot_changed"] else "boot-stable",
                "session_id": "session-before",
                "endpoint": pre_endpoint,
            },
            "post": {
                "device_id": "opaque-device-1",
                "boot_id": "boot-after" if expectation["boot_changed"] else "boot-stable",
                "session_id": "session-after",
                "endpoint": post_endpoint,
            },
        }
        validate_recovery_action_event(event, action)
        for field, replacement in (
            ("action", "software-reset" if action != "software-reset" else "reset-unplug"),
            ("discarded_ids", []),
        ):
            invalid = dict(event, **{field: replacement})
            try:
                validate_recovery_action_event(invalid, action)
            except SerialLinkError:
                pass
            else:
                raise AssertionError(f"{action} accepted invalid {field} facts")
    same_port = {
        **base,
        "action": "different-port-reconnect",
        "pre": {"device_id": "opaque-device-1", "boot_id": "a", "session_id": "s1", "endpoint": {"path": "/dev/ttyACM0"}},
        "post": {"device_id": "opaque-device-1", "boot_id": "b", "session_id": "s2", "endpoint": {"path": "/dev/ttyACM0"}},
    }
    try:
        validate_recovery_action_event(same_port, "different-port-reconnect")
    except SerialLinkError:
        pass
    else:
        raise AssertionError("different-port action accepted unchanged endpoint")


def udev_rule_check(path: Any) -> None:
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8")
    required = ('SUBSYSTEM=="tty"', 'ATTRS{idVendor}=="303a"', 'ATTRS{idProduct}=="1001"', 'ENV{ID_SERIAL_SHORT}=="8C:BF:EA:0D:CB:FC"', 'ENV{ID_USB_INTERFACE_NUM}=="01"', 'GROUP="dialout"', 'TAG+="uaccess"')
    missing = [token for token in required if token not in text]
    if missing:
        raise AssertionError("udev rule is missing measured narrow tokens: " + ", ".join(missing))
    if "KERNEL==\"ttyACM*\"" in text or "MODE=\"0666\"" in text or "ATTRS{idVendor}==\"*\"" in text:
        raise AssertionError("udev rule is broader than the measured runtime interface")
