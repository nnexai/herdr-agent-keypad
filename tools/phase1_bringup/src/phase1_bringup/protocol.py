"""Bounded v1 protocol/session helpers shared by the guided host run."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

MAX_LINE_BYTES = 4096
PROTOCOL_VERSION = 1
FRAME_TYPES = {"hello", "hello_ack", "probe", "probe_ack", "event", "error"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_string(value: Any, name: str, maximum: int = 64) -> None:
    if not isinstance(value, str) or not (1 <= len(value) <= maximum) or not ID_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a bounded opaque identifier")


def validate_frame(frame: Any) -> dict[str, Any]:
    if not isinstance(frame, dict):
        raise ValueError("frame must be an object")
    required = {"v", "type", "boot_id", "session_id", "seq", "reply_to", "payload"}
    if set(frame) != required:
        raise ValueError("frame envelope is closed")
    if frame["v"] != PROTOCOL_VERSION or frame["type"] not in FRAME_TYPES:
        raise ValueError("unsupported protocol version or frame type")
    _require_string(frame["boot_id"], "boot_id")
    _require_string(frame["session_id"], "session_id")
    if not _is_int(frame["seq"]) or not 1 <= frame["seq"] <= 0xFFFFFFFF:
        raise ValueError("seq must be a positive uint32")
    if frame["reply_to"] is not None and (not _is_int(frame["reply_to"]) or not 1 <= frame["reply_to"] <= 0xFFFFFFFF):
        raise ValueError("reply_to must be null or a positive uint32")
    payload = frame["payload"]
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    expected: dict[str, set[str]] = {
        "hello": {"device_id", "firmware", "protocol"},
        "hello_ack": {"accepted", "protocol", "device_id", "firmware"},
        "probe": {"step_id", "panel", "stimulus"},
        "probe_ack": {"accepted", "step_id"},
        "event": {"kind", "step_id", "key"},
        "error": {"code", "detail"},
    }
    if set(payload) != expected[frame["type"]]:
        raise ValueError(f"{frame['type']} payload is closed")
    if frame["type"] in {"hello", "hello_ack"} and payload.get("protocol") != PROTOCOL_VERSION:
        raise ValueError("payload protocol must be v1")
    if frame["type"] == "hello" and any(not isinstance(payload[name], str) or not payload[name] for name in ("device_id", "firmware")):
        raise ValueError("hello identity fields must be non-empty strings")
    if frame["type"] == "hello_ack":
        if not isinstance(payload["accepted"], bool):
            raise ValueError("hello_ack accepted must be boolean")
        if any(not isinstance(payload[name], str) or not payload[name] for name in ("device_id", "firmware")):
            raise ValueError("hello_ack identity fields must be non-empty strings")
    if frame["type"] == "probe":
        if not isinstance(payload["step_id"], str) or not payload["step_id"]:
            raise ValueError("probe step_id must be non-empty")
        if not _is_int(payload["panel"]) or not 1 <= payload["panel"] <= 4:
            raise ValueError("probe panel must be one through four")
        if not isinstance(payload["stimulus"], str) or not 1 <= len(payload["stimulus"]) <= 64:
            raise ValueError("probe stimulus must be bounded")
    if frame["type"] == "probe_ack":
        if not isinstance(payload["accepted"], bool) or not isinstance(payload["step_id"], str) or not payload["step_id"]:
            raise ValueError("probe_ack fields are invalid")
    if frame["type"] == "event":
        if payload["kind"] != "key_transition":
            raise ValueError("event kind is invalid")
        _require_string(payload["step_id"], "event step_id")
        if not _is_int(payload["key"]) or not 0 <= payload["key"] <= 4:
            raise ValueError("event key is invalid")
    if frame["type"] == "error" and any(not isinstance(payload[name], str) or not payload[name] for name in ("code", "detail")):
        raise ValueError("error fields must be non-empty strings")
    return frame


def encode_frame(frame: dict[str, Any]) -> bytes:
    validate_frame(frame)
    encoded = (json.dumps(frame, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > MAX_LINE_BYTES:
        raise ValueError("encoded frame exceeds 4096 bytes including LF")
    return encoded


def decode_frame(line: bytes) -> dict[str, Any]:
    if len(line) == 0 or len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
        raise ValueError("line must include LF and fit the 4096-byte bound")
    try:
        frame = json.loads(line[:-1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON frame") from exc
    return validate_frame(frame)


def new_frame(frame_type: str, boot_id: str, session_id: str, seq: int, payload: dict[str, Any], reply_to: int | None = None) -> dict[str, Any]:
    return {"v": PROTOCOL_VERSION, "type": frame_type, "boot_id": boot_id, "session_id": session_id, "seq": seq, "reply_to": reply_to, "payload": payload}


@dataclass(frozen=True)
class MachineFact:
    """A device fact; it describes acknowledgement, never physical correctness."""

    status: str
    received_at: float
    reply_seq: int | None = None
    detail: str = ""


class ProtocolSession:
    """One bounded session over a serial-like connection."""

    def __init__(self, connection: Any, boot_id: str, session_id: str, timeout: float = 10.0):
        self.connection = connection
        self.boot_id = boot_id
        self.session_id = session_id
        self.timeout = timeout
        self.next_seq = 0
        self.last_received_seq = 0
        self.device: dict[str, Any] = {}

    def send(self, frame_type: str, payload: dict[str, Any]) -> int:
        self.next_seq += 1
        frame = new_frame(frame_type, self.boot_id, self.session_id, self.next_seq, payload)
        self.connection.write(encode_frame(frame))
        return self.next_seq

    def _receive(self) -> dict[str, Any] | None:
        line = self.connection.readline()
        if not line:
            return None
        frame = decode_frame(line)
        if frame["session_id"] != self.session_id:
            raise RuntimeError("session correlation mismatch")
        if frame["seq"] <= self.last_received_seq:
            raise RuntimeError("out-of-order or duplicate frame received")
        self.last_received_seq = frame["seq"]
        return frame
    def request(self, frame_type: str, payload: dict[str, Any], allowed: Iterable[str]) -> tuple[dict[str, Any], MachineFact]:
        request_seq = self.send(frame_type, payload)
        deadline = time.monotonic() + self.timeout
        allowed_set = set(allowed)
        while time.monotonic() < deadline:
            frame = self._receive()
            if frame is None:
                continue
            if frame["type"] == "error":
                raise RuntimeError(f"device rejected frame: {frame['payload']['code']}")
            if frame["type"] in allowed_set and frame["reply_to"] == request_seq:
                accepted = frame["payload"].get("accepted", True)
                fact = MachineFact("acknowledged" if accepted else "rejected", time.time(), frame["seq"])
                return frame, fact
        raise TimeoutError(f"timed out waiting for {frame_type} acknowledgement")

    def hello(self) -> MachineFact:
        frame, fact = self.request("hello", {"device_id": "host", "firmware": "phase1-host", "protocol": PROTOCOL_VERSION}, {"hello_ack"})
        payload = frame["payload"]
        self.device = {
            "hello_ack": payload,
            "device_id": payload["device_id"],
            "firmware": payload["firmware"],
            "protocol": payload["protocol"],
        }
        return fact

    def stimulate(self, step_id: str, panel: int, stimulus: str) -> MachineFact:
        _, fact = self.request("probe", {"step_id": step_id, "panel": panel, "stimulus": stimulus}, {"probe_ack"})
        return fact

    def wait_event(self, step_id: str, timeout: float = 60.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self._receive()
            if frame is None:
                continue
            if frame["type"] == "event" and frame["payload"]["step_id"] == step_id:
                return frame
            if frame["type"] == "error":
                raise RuntimeError(f"device rejected probe: {frame['payload']['code']}")
        raise TimeoutError("timed out waiting for matching physical key transition")
