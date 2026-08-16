"""Bounded v1 protocol/session helpers shared by host and firmware fixtures."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

MAX_LINE_BYTES = 4096
PROTOCOL_VERSION = 1
FRAME_TYPES = {"hello", "hello_ack", "probe", "probe_ack", "event", "error", "metrics", "metrics_ack"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{16}$")

PAYLOAD_KEYS: dict[str, set[str]] = {
    "hello": {"device_id", "firmware", "protocol"},
    "hello_ack": {"accepted", "device_id", "firmware", "protocol"},
    "probe": {"panel", "step_id", "stimulus"},
    "probe_ack": {"accepted", "step_id"},
    "event": {"key", "direction", "kind", "step_id"},
    "error": {"code", "detail"},
    "metrics": {"request"},
    "metrics_ack": {"acknowledged", "digest_mismatch", "duplicate", "largest_free_block", "malformed", "max_display_flush_us", "max_key_poll_gap_us", "minimum_free_heap", "out_of_order", "parser_high_water", "queue_high_water", "received", "rejected", "sent", "watchdog_reset"},
}


class ProtocolError(ValueError):
    """A validation failure with the stable typed rejection code."""

    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        super().__init__(detail or code)


@dataclass(frozen=True)
class ProtocolResult:
    accepted: bool
    reason: str
    frame: dict[str, Any] | None = None
    dispatched: bool = False


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_string(value: Any, name: str, maximum: int = 64) -> None:
    if not isinstance(value, str) or not (1 <= len(value) <= maximum) or not ID_PATTERN.fullmatch(value):
        raise ProtocolError("invalid_identifier", f"{name} must be a bounded opaque identifier")


def _payload_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    digest = 0xCBF29CE484222325
    for byte in canonical:
        digest ^= byte
        digest = (digest * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{digest:016x}"


def validate_frame(frame: Any) -> dict[str, Any]:
    if not isinstance(frame, dict):
        raise ProtocolError("invalid_envelope", "frame must be an object")
    required = {"v", "type", "boot_id", "session_id", "seq", "reply_to", "digest", "payload"}
    if set(frame) != required:
        raise ProtocolError("unknown_field", "frame envelope is closed")
    if not _is_int(frame["v"]) or frame["v"] != PROTOCOL_VERSION:
        raise ProtocolError("invalid_version", "only protocol v1 is accepted")
    if not isinstance(frame["type"], str):
        raise ProtocolError("unknown_type", "frame type must be a string")
    if frame["type"] not in FRAME_TYPES:
        raise ProtocolError("unknown_type", "frame type is not in the closed v1 set")
    _require_string(frame["boot_id"], "boot_id")
    _require_string(frame["session_id"], "session_id")
    if not _is_int(frame["seq"]) or not 1 <= frame["seq"] <= 0xFFFFFFFF:
        raise ProtocolError("invalid_sequence", "seq must be a positive uint32")
    if frame["reply_to"] is not None and (not _is_int(frame["reply_to"]) or not 1 <= frame["reply_to"] <= 0xFFFFFFFF):
        raise ProtocolError("invalid_reply_to", "reply_to must be null or a positive uint32")
    if not isinstance(frame["digest"], str) or not DIGEST_PATTERN.fullmatch(frame["digest"]):
        raise ProtocolError("invalid_digest", "digest must be a lowercase 64-bit hex value")
    frame_type = frame["type"]
    payload = frame["payload"]
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_payload", "payload must be an object")
    if frame_type != "event" and set(payload) != PAYLOAD_KEYS[frame_type]:
        raise ProtocolError("invalid_shape", f"{frame_type} payload is closed")
    if frame_type == "event" and not {"kind", "step_id"}.issubset(payload):
        raise ProtocolError("invalid_shape", "event payload requires kind and step_id")
    if frame_type in {"hello", "hello_ack"} and payload.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolError("invalid_shape", "payload protocol must be v1")
    if frame_type == "hello":
        _require_string(payload["device_id"], "device_id")
        _require_string(payload["firmware"], "firmware", 64)
    elif frame_type == "hello_ack":
        if not isinstance(payload["accepted"], bool):
            raise ProtocolError("invalid_shape", "hello_ack accepted must be boolean")
        _require_string(payload["device_id"], "device_id")
        _require_string(payload["firmware"], "firmware", 64)
    elif frame_type == "probe":
        _require_string(payload["step_id"], "step_id")
        if not _is_int(payload["panel"]) or not 1 <= payload["panel"] <= 4:
            raise ProtocolError("invalid_shape", "probe panel must be one through four")
        if not isinstance(payload["stimulus"], str) or not 1 <= len(payload["stimulus"]) <= 64:
            raise ProtocolError("invalid_shape", "probe stimulus must be bounded")
    elif frame_type == "probe_ack":
        if not isinstance(payload["accepted"], bool):
            raise ProtocolError("invalid_shape", "probe_ack accepted must be boolean")
        _require_string(payload["step_id"], "step_id")
    elif frame_type == "event":
        kind = payload.get("kind")
        if kind == "key_transition":
            if set(payload) != {"key", "kind", "step_id"}:
                raise ProtocolError("invalid_shape", "key events require key, kind, and step_id")
            _require_string(payload["step_id"], "step_id")
            if not _is_int(payload["key"]) or not 0 <= payload["key"] <= 4:
                raise ProtocolError("invalid_shape", "event key is invalid")
        elif kind == "encoder_transition":
            if set(payload) != {"direction", "kind", "step_id"}:
                raise ProtocolError("invalid_shape", "encoder events require direction, kind, and step_id")
            _require_string(payload["step_id"], "step_id")
            if payload["direction"] not in {"cw", "ccw"}:
                raise ProtocolError("invalid_shape", "encoder direction is invalid")
        else:
            raise ProtocolError("invalid_shape", "event kind is invalid")
    elif frame_type == "error":
        _require_string(payload["code"], "error code", 64)
        if not isinstance(payload["detail"], str) or not 1 <= len(payload["detail"]) <= 128:
            raise ProtocolError("invalid_shape", "error detail must be bounded")
    elif frame_type == "metrics":
        if not isinstance(payload["request"], str) or payload["request"] not in {"proof", "reset"}:
            raise ProtocolError("invalid_shape", "metrics request must be proof or reset")
    elif frame_type == "metrics_ack":
        if any(not _is_int(payload[name]) or payload[name] < 0 for name in PAYLOAD_KEYS["metrics_ack"]):
            raise ProtocolError("invalid_shape", "metrics_ack values must be non-negative integers")
    if frame["digest"] != _payload_digest(payload):
        raise ProtocolError("digest_mismatch", "payload digest does not match canonical payload")
    return frame


def encode_frame(frame: dict[str, Any]) -> bytes:
    validate_frame(frame)
    encoded = (json.dumps(frame, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    if len(encoded) > MAX_LINE_BYTES:
        raise ProtocolError("line_too_long", "encoded frame exceeds 4096 bytes including LF")
    return encoded


def classify_line(line: bytes) -> ProtocolResult:
    if not line:
        return ProtocolResult(False, "empty_line")
    if len(line) > MAX_LINE_BYTES:
        return ProtocolResult(False, "line_too_long")
    if not line.endswith(b"\n"):
        return ProtocolResult(False, "missing_lf")
    try:
        frame = json.loads(line[:-1].decode("utf-8"))
    except UnicodeDecodeError:
        return ProtocolResult(False, "invalid_utf8")
    except (json.JSONDecodeError, RecursionError):
        return ProtocolResult(False, "invalid_json")
    try:
        validated = validate_frame(frame)
    except ProtocolError as exc:
        return ProtocolResult(False, exc.code)
    return ProtocolResult(True, "ok", validated)


def decode_frame(line: bytes) -> dict[str, Any]:
    result = classify_line(line)
    if not result.accepted:
        raise ProtocolError(result.reason)
    assert result.frame is not None
    return result.frame


def new_frame(
    frame_type: str,
    boot_id: str,
    session_id: str,
    seq: int,
    payload: dict[str, Any],
    reply_to: int | None = None,
) -> dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "type": frame_type,
        "boot_id": boot_id,
        "session_id": session_id,
        "seq": seq,
        "reply_to": reply_to,
        "digest": _payload_digest(payload),
        "payload": payload,
    }


@dataclass(frozen=True)
class MachineFact:
    """A device fact; it describes acknowledgement, never physical correctness."""

    status: str
    received_at: float
    reply_seq: int | None = None
    detail: str = ""


class ProtocolSession:
    """One bounded session over a serial-like connection."""

    def __init__(
        self,
        connection: Any,
        boot_id: str,
        session_id: str,
        timeout: float = 10.0,
        queue_limit: int = 16,
    ):
        self.connection = connection
        self.timeout = timeout
        self.queue_limit = queue_limit
        self.reset(boot_id, session_id)

    def reset(self, boot_id: str, session_id: str) -> None:
        _require_string(boot_id, "boot_id")
        _require_string(session_id, "session_id")
        self.boot_id = boot_id
        self.session_id = session_id
        self.next_seq = 0
        self.last_received_seq = 0
        self._seen: list[int] = []
        self.pending: list[dict[str, Any]] = []
        self.device: dict[str, Any] = {}

    def prime_received(self, sequence: int) -> None:
        if not 0 <= sequence <= 0xFFFFFFFF:
            raise ValueError("invalid prior sequence")
        self.last_received_seq = sequence
        self._seen = [sequence] if sequence else []

    def send(self, frame_type: str, payload: dict[str, Any]) -> int:
        candidate = self.next_seq + 1
        frame = new_frame(frame_type, self.boot_id, self.session_id, candidate, payload)
        encoded = encode_frame(frame)
        self.connection.write(encoded)
        # SerialLink.write returns only after all bytes are accepted. Keep
        # durable session accounting unchanged on any short/failing write.
        self.next_seq = candidate
        return candidate

    def accept(self, line: bytes, dispatch: bool = True) -> ProtocolResult:
        result = classify_line(line)
        if not result.accepted:
            return result
        assert result.frame is not None
        frame = result.frame
        if frame["boot_id"] != self.boot_id:
            return ProtocolResult(False, "boot_mismatch", frame)
        if frame["session_id"] != self.session_id:
            return ProtocolResult(False, "session_mismatch", frame)
        sequence = frame["seq"]
        if sequence in self._seen:
            return ProtocolResult(False, "duplicate", frame)
        if sequence <= self.last_received_seq:
            return ProtocolResult(False, "out_of_order", frame)
        if dispatch and len(self.pending) >= self.queue_limit:
            return ProtocolResult(False, "queue_full", frame)
        self.last_received_seq = sequence
        self._seen.append(sequence)
        if len(self._seen) > self.queue_limit:
            self._seen.pop(0)
        if dispatch:
            self.pending.append(frame)
        return ProtocolResult(True, "ok", frame, dispatch)

    def complete(self) -> bool:
        if not self.pending:
            return False
        self.pending.pop(0)
        return True

    def pending_count(self) -> int:
        return len(self.pending)
    def discard_pending(self) -> int:
        discarded = len(self.pending)
        self.pending.clear()
        return discarded

    def _receive(self) -> dict[str, Any] | None:
        line = self.connection.readline()
        if not line:
            return None
        result = self.accept(line, dispatch=False)
        if not result.accepted:
            raise ProtocolError(result.reason)
        assert result.frame is not None
        return result.frame

    def request(self, frame_type: str, payload: dict[str, Any], allowed: Iterable[str]) -> tuple[dict[str, Any], MachineFact]:
        request_seq = self.send(frame_type, payload)
        deadline = time.monotonic() + self.timeout
        allowed_set = set(allowed)
        while time.monotonic() < deadline:
            frame = self._receive()
            if frame is None:
                continue
            if frame["type"] == "error":
                raise ProtocolError(frame["payload"]["code"], frame["payload"]["detail"])
            if frame["type"] in allowed_set and frame["reply_to"] == request_seq:
                accepted = frame["payload"].get("accepted", True)
                fact = MachineFact("acknowledged" if accepted else "rejected", time.time(), frame["seq"])
                return frame, fact
        raise TimeoutError(f"timed out waiting for {frame_type} acknowledgement")

    def hello(self) -> MachineFact:
        request_seq = self.send("hello", {"device_id": "host", "firmware": "phase1-host", "protocol": PROTOCOL_VERSION})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            line = self.connection.readline()
            if not line:
                continue
            result = classify_line(line)
            if not result.accepted:
                raise ProtocolError(result.reason)
            assert result.frame is not None
            frame = result.frame
            if frame["session_id"] != self.session_id:
                raise ProtocolError("session_mismatch")
            if frame["type"] == "error":
                raise ProtocolError(frame["payload"]["code"], frame["payload"]["detail"])
            if frame["type"] != "hello_ack" or frame["reply_to"] != request_seq:
                raise ProtocolError("invalid_shape", "hello acknowledgement did not match the hello request")
            self.boot_id = frame["boot_id"]
            self.prime_received(frame["seq"])
            payload = frame["payload"]
            fact = MachineFact("acknowledged" if payload.get("accepted", True) else "rejected", time.time(), frame["seq"])
            self.device = {
                "hello_ack": payload,
                "device_id": payload["device_id"],
                "firmware": payload["firmware"],
                "protocol": payload["protocol"],
                "device_boot_id": frame["boot_id"],
                "device_session_id": frame["session_id"],
            }
            return fact
        raise TimeoutError("timed out waiting for hello acknowledgement")

    def stimulate(self, step_id: str, panel: int, stimulus: str) -> MachineFact:
        _, fact = self.request("probe", {"step_id": step_id, "panel": panel, "stimulus": stimulus}, {"probe_ack"})
        return fact

    def wait_event(
        self,
        step_id: str,
        timeout: float = 60.0,
        *,
        expected_kind: str | None = None,
        expected_key: int | None = None,
        expected_direction: str | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self._receive()
            if frame is None:
                continue
            if frame["type"] == "event" and frame["payload"]["step_id"] == step_id:
                payload = frame["payload"]
                if expected_kind is not None and payload.get("kind") != expected_kind:
                    raise ProtocolError("unexpected_event", f"expected {expected_kind}, received {payload.get('kind')}")
                if expected_key is not None and payload.get("key") != expected_key:
                    raise ProtocolError("unexpected_event", f"expected key {expected_key}, received {payload.get('key')}")
                if expected_direction is not None and payload.get("direction") != expected_direction:
                    raise ProtocolError("unexpected_event", f"expected direction {expected_direction}, received {payload.get('direction')}")
                return frame
            if frame["type"] == "error":
                raise ProtocolError(frame["payload"]["code"], frame["payload"]["detail"])
        raise TimeoutError("timed out waiting for matching physical input transition")


def protocol_golden_check(fixture_path: Any, schema_path: Any) -> int:
    """Run every repository vector through the same host codec/session rules."""
    fixture = json.loads(open(fixture_path, encoding="utf-8").read())
    schema = json.loads(open(schema_path, encoding="utf-8").read())
    if schema.get("x-max-encoded-line-bytes-including-lf") != MAX_LINE_BYTES:
        raise AssertionError("schema bound drift")
    if "digest" not in schema.get("required", []):
        raise AssertionError("schema digest requirement missing")
    vectors = fixture.get("vectors")
    if not isinstance(vectors, list) or not vectors:
        raise AssertionError("golden fixture is empty")
    for vector in vectors:
        line_value = vector.get("line")
        if line_value == "synthetic:oversized":
            line = b"x" * MAX_LINE_BYTES + b"\n"
        elif isinstance(line_value, str):
            line = line_value.encode("ascii")
        else:
            raise AssertionError(f"{vector.get('id')}: missing line")
        expected = vector["expected"]
        session = ProtocolSession(None, vector.get("expected_boot_id", "boot-a"), vector.get("expected_session_id", "session-a"), queue_limit=4)
        session.prime_received(int(vector.get("prior_seq", 0)))
        result = session.accept(line)
        if result.reason != expected["reason"] or result.accepted != (expected["outcome"] == "accepted"):
            raise AssertionError(f"{vector.get('id')}: host {result.reason}, expected {expected['reason']}")
        if result.dispatched != bool(expected.get("dispatch", False)):
            raise AssertionError(f"{vector.get('id')}: dispatch mismatch")
    return len(vectors)

def protocol_bootstrap_check() -> None:
    """Check device-boot adoption and strict post-bootstrap identity."""

    class BootstrapLink:
        def __init__(self, wrong_session: bool = False) -> None:
            self.pending: list[bytes] = []
            self.wrong_session = wrong_session

        def write(self, data: bytes) -> int:
            request = decode_frame(data)
            session_id = "wrong-session" if self.wrong_session else request["session_id"]
            payload = {"accepted": True, "device_id": "device", "firmware": "phase1-bringup", "protocol": PROTOCOL_VERSION}
            self.pending.append(encode_frame(new_frame("hello_ack", "device-boot", session_id, 1, payload, reply_to=request["seq"])))
            return len(data)

        def readline(self) -> bytes:
            return self.pending.pop(0) if self.pending else b""

    session = ProtocolSession(BootstrapLink(), "host-nonce", "session-a", timeout=0.01)
    session.hello()
    if session.boot_id != "device-boot":
        raise AssertionError("hello bootstrap did not adopt the device boot id")
    wrong_boot = new_frame("hello_ack", "other-device", "session-a", 2, {"accepted": True, "device_id": "device", "firmware": "phase1-bringup", "protocol": PROTOCOL_VERSION}, reply_to=1)
    if session.accept(encode_frame(wrong_boot)).reason != "boot_mismatch":
        raise AssertionError("post-bootstrap boot identity was not strict")
    try:
        ProtocolSession(BootstrapLink(wrong_session=True), "host-nonce", "session-a", timeout=0.01).hello()
    except ProtocolError as exc:
        if exc.code != "session_mismatch":
            raise AssertionError("wrong-session hello was rejected with the wrong code") from exc
    else:
        raise AssertionError("wrong-session hello acknowledgement was accepted")

    class EventLink:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.pending = [encode_frame(new_frame("event", "device-boot", "session-a", 2, payload))]

        def readline(self) -> bytes:
            return self.pending.pop(0) if self.pending else b""

    event_session = ProtocolSession(EventLink({"direction": "cw", "kind": "encoder_transition", "step_id": "PREFLIGHT-1"}), "device-boot", "session-a", timeout=0.01)
    event_session.prime_received(1)
    event_session.wait_event("PREFLIGHT-1", expected_kind="encoder_transition", expected_direction="cw")
    mismatch_session = ProtocolSession(EventLink({"direction": "ccw", "kind": "encoder_transition", "step_id": "PREFLIGHT-1"}), "device-boot", "session-a", timeout=0.01)
    mismatch_session.prime_received(1)
    try:
        mismatch_session.wait_event("PREFLIGHT-1", expected_kind="encoder_transition", expected_direction="cw")
    except ProtocolError as exc:
        if exc.code != "unexpected_event":
            raise AssertionError("unexpected input direction used the wrong rejection code") from exc
    else:
        raise AssertionError("unexpected encoder direction was accepted")
    malformed_base = new_frame("metrics", "device-boot", "session-a", 3, {"request": "proof"})
    malformed_cases = (
        ({**malformed_base, "v": True}, "invalid_version"),
        ({**malformed_base, "type": []}, "unknown_type"),
        ({**malformed_base, "payload": {"request": []}}, "invalid_shape"),
    )
    for malformed, expected in malformed_cases:
        line = (json.dumps(malformed, separators=(",", ":")) + "\n").encode("utf-8")
        result = classify_line(line)
        if result.reason != expected or result.accepted:
            raise AssertionError(f"malformed discriminant escaped typed rejection: {expected}")
