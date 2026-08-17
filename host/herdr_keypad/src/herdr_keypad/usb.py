"""Exact paired USB CDC runtime built on the Phase 1 discovery/session seam."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

_ROOT = Path(__file__).resolve().parents[4]
_TOOLS_SRC = _ROOT / "tools" / "phase1_bringup" / "src"
import sys
if str(_TOOLS_SRC) not in sys.path:
    sys.path.insert(0, str(_TOOLS_SRC))

from phase1_bringup.discovery import Candidate
from phase1_bringup.pairing import PairingBinding, PairingStore
from phase1_bringup.serial_link import SerialLink, SerialLinkError, reconnect_exact
from phase1_bringup import protocol as v1_protocol

from .bridge import MAX_LINE_BYTES, validate_v2_payload


class UsbSessionError(RuntimeError):
    """The selected USB session is unavailable or failed closed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class UsbDeviceSession:
    """Own one fresh v2 session for the exact read-only paired binding.

    Candidate enumeration, hello validation, full writes/reads, and stale
    descriptor closure are delegated to the Phase 1 production seam. This
    adapter only adds v2 message sequencing on the already admitted link.
    """

    def __init__(
        self,
        binding_path: str | os.PathLike[str] | None = None,
        *,
        ports: Iterable[Any] | None = None,
        opener: Callable[[Candidate], Any] | None = None,
        timeout: float = 3.0,
        pair_store: PairingStore | None = None,
    ) -> None:
        self.binding_path = Path(binding_path or os.path.expanduser("~/.config/herdr/keypad-binding.json"))
        self.ports = ports
        self.opener = opener or self._open_serial
        self.timeout = timeout
        self.pair_store = pair_store or PairingStore(self.binding_path)
        self.binding: PairingBinding | None = None
        self.candidate: Candidate | None = None
        self.link: SerialLink | None = None
        self.session: Any | None = None
        self.device: dict[str, Any] = {}
        self.closed = True
        self._pending_focus: list[dict[str, Any]] = []
        self.pending_focus_capacity = 16

    @staticmethod
    def _open_serial(candidate: Candidate) -> Any:
        try:
            import serial
        except ImportError as exc:  # pragma: no cover - environment failure
            raise UsbSessionError("pyserial_missing", "locked pyserial is required") from exc
        return serial.Serial(candidate.device, 115200, timeout=0.2, write_timeout=2.0)

    @property
    def connected(self) -> bool:
        return not self.closed and self.link is not None and not self.link.closed and self.session is not None

    @property
    def device_id(self) -> str | None:
        value = self.device.get("device_id")
        return value if isinstance(value, str) else None

    def connect(self) -> dict[str, Any]:
        binding = self.pair_store.load()
        self._pending_focus.clear()
        if binding is None:
            raise UsbSessionError("binding_missing", "paired keypad binding is missing")
        self.binding = binding
        try:
            selected, link, session, transitions = reconnect_exact(
                binding, self.ports, self.opener, timeout=self.timeout
            )
        except (SerialLinkError, OSError, TimeoutError, ValueError) as exc:
            self.close()
            code = getattr(exc, "code", "unavailable")
            raise UsbSessionError(str(code), str(exc)) from exc
        hello = dict(session.device)
        if hello.get("device_id") != binding.device_id:
            link.close()
            raise UsbSessionError("identity_mismatch", "application hello did not match the stored binding")
        if hello.get("protocol") != 1:
            link.close()
            raise UsbSessionError("incompatible", "paired keypad did not acknowledge the Phase 1 protocol")

        self.candidate = selected
        self.link = link
        self.session = session
        self.device = {"hello": hello, "transitions": [t.detail for t in transitions]}
        self.closed = False
        return dict(self.device)
    @property
    def session_id(self) -> str | None:
        return self.session.session_id if self.session is not None else None

    def _require_open(self) -> tuple[SerialLink, Any]:
        if not self.connected:
            raise UsbSessionError("closed", "USB session is not connected")
        assert self.link is not None and self.session is not None
        return self.link, self.session

    def request_v2(self, frame_type: str, payload: Mapping[str, Any], allowed: Iterable[str]) -> dict[str, Any]:
        link, session = self._require_open()
        payload_dict = dict(payload)
        validate_v2_payload(frame_type, payload_dict)
        sequence = session.next_seq + 1
        frame = v1_protocol.new_v2_frame(
            frame_type,
            session.boot_id,
            session.session_id,
            sequence,
            payload_dict,
        )
        try:
            link.write(v1_protocol.encode_v2_frame(frame))
            session.next_seq = sequence
            deadline = time.monotonic() + self.timeout
            allowed_set = set(allowed)
            while time.monotonic() < deadline:
                line = link.readline()
                if not line:
                    continue
                parsed = v1_protocol.classify_v2_line(line)
                if not parsed.accepted or parsed.frame is None:
                    raise UsbSessionError("protocol", parsed.reason)
                response = parsed.frame
                if response["boot_id"] != session.boot_id or response["session_id"] != session.session_id:
                    raise UsbSessionError("session_mismatch", "v2 response belongs to another USB session")
                if response["seq"] <= session.last_received_seq:
                    raise UsbSessionError("out_of_order", "v2 response sequence is stale")
                session.last_received_seq = response["seq"]
                if response["type"] == "focus_intent":
                    if len(self._pending_focus) >= self.pending_focus_capacity:
                        self.close()
                        raise UsbSessionError("queue_overflow", "pending focus queue is full")
                    self._pending_focus.append(dict(response))
                    continue
                if response["type"] in allowed_set and response["reply_to"] == sequence:
                    return dict(response["payload"])
            raise UsbSessionError("timeout", f"timed out waiting for {frame_type} acknowledgement")
        except UsbSessionError:
            self._pending_focus.clear()
            raise
        except (SerialLinkError, OSError, TimeoutError) as exc:
            self._pending_focus.clear()
            self.close()
            raise UsbSessionError("io", str(exc)) from exc

    def publish_snapshot(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.request_v2("agent_snapshot", payload, {"snapshot_ack"})

    def send_focus_result(self, payload: Mapping[str, Any]) -> None:
        link, session = self._require_open()
        payload_dict = dict(payload)
        validate_v2_payload("focus_result", payload_dict)
        sequence = session.next_seq + 1
        frame = v1_protocol.new_v2_frame("focus_result", session.boot_id, session.session_id, sequence, payload_dict)
        try:
            link.write(v1_protocol.encode_v2_frame(frame))
            session.next_seq = sequence
        except (SerialLinkError, OSError, TimeoutError) as exc:
            self.close()
            raise UsbSessionError("io", str(exc)) from exc

    def clear_pending_focus(self) -> None:
        self._pending_focus.clear()

    @property
    def pending_focus_count(self) -> int:
        return len(self._pending_focus)

    def poll(self) -> dict[str, Any] | None:
        link, session = self._require_open()
        if self._pending_focus:
            return self._pending_focus.pop(0)
        try:
            line = link.readline()
        except SerialLinkError as exc:
            self.close()
            raise UsbSessionError(exc.code, str(exc)) from exc
        if not line:
            return None
        parsed = v1_protocol.classify_v2_line(line)
        if not parsed.accepted or parsed.frame is None:
            self._pending_focus.clear()
            raise UsbSessionError("protocol", parsed.reason)
        frame = parsed.frame
        if frame["boot_id"] != session.boot_id or frame["session_id"] != session.session_id:
            self._pending_focus.clear()
            raise UsbSessionError("session_mismatch", "v2 event belongs to another USB session")
        if frame["seq"] <= session.last_received_seq:
            self._pending_focus.clear()
            raise UsbSessionError("out_of_order", "v2 event sequence is stale")
        session.last_received_seq = frame["seq"]
        return frame

    def close(self) -> None:
        self._pending_focus.clear()
        if self.link is not None:
            self.link.close()
        self.link = None
        self.session = None
        self.candidate = None
        self.closed = True

    def __enter__(self) -> "UsbDeviceSession":
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def binding_is_stable(path: str | os.PathLike[str]) -> bool:
    """Read-only check used by startup/acceptance paths."""
    try:
        binding = PairingStore(Path(path)).load()
    except Exception:
        return False
    return binding is not None and binding.device_id != "host"
