"""Bounded v1 protocol/session helpers shared by host and firmware fixtures."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

MAX_LINE_BYTES = 4096
MAX_JSON_NESTING = 8
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
    "metrics_ack": {
        "acknowledged", "allocation_stable", "animation_duty_max_percent",
        "candidate_transitions", "chord_lockouts", "compose_flush_max_us",
        "degraded_frames", "digest_mismatch", "duplicate", "eligibility_events",
        "eligibility_to_down_max_us", "first_encoder_response_us",
        "first_press_response_us", "focus_result_to_eligibility_max_us",
        "frame_count", "full_frames", "half_frames", "hid_not_ready",
        "hid_send_failures", "hold_poll_gap_max_us", "largest_free_block",
        "level_changes", "lifecycle_clears", "loop_wall_max_us", "malformed",
        "max_display_flush_us", "max_key_poll_gap_us", "minimum_free_heap",
        "out_of_order", "owner_transitions", "parser_high_water",
        "physical_release_to_up_max_us", "queue_high_water", "received",
        "rejected", "release_all_attempts", "release_all_failures",
        "reset_reason", "retained_boot_sequence",
        "retained_previous_boot_sequence", "retained_previous_boot_valid",
        "retained_previous_empty_report_completions",
        "retained_previous_last_lifecycle_event",
        "retained_previous_last_lifecycle_status",
        "retained_previous_last_report_kind",
        "retained_previous_last_report_status",
        "retained_previous_lifecycle_clears",
        "retained_previous_report_attempts",
        "retained_previous_report_completions",
        "retained_previous_space_down_completions", "reveal_max_us", "sent",
        "skipped_frames", "space_down_completions", "space_down_requests",
        "space_up_completions", "space_up_requests", "static_frames",
        "threshold_crossings", "watchdog_reset",
    },
}

class DuplicateKeyError(ValueError):
    """Raised when a JSON object contains a duplicate member name."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def _load_json(text: str | bytes) -> Any:
    return json.loads(text, object_pairs_hook=_reject_duplicate_pairs)


def _check_nesting(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_NESTING:
        raise ProtocolError("invalid_json", "JSON nesting exceeds the bounded parser limit")
    if isinstance(value, dict):
        for child in value.values():
            _check_nesting(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_nesting(child, depth + 1)


def _require_ascii_text(value: Any, name: str, maximum: int) -> None:
    if not isinstance(value, str) or not (1 <= len(value) <= maximum) or any(ord(char) >= 0x80 for char in value):
        raise ProtocolError("invalid_shape", f"{name} must be bounded ASCII text")


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
    elif frame_type == "event" and not {"kind", "step_id"}.issubset(payload):
        raise ProtocolError("invalid_shape", "event payload requires kind and step_id")
    if frame_type in {"hello", "hello_ack"} and payload.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolError("invalid_shape", "payload protocol must be v1")
    if frame_type == "hello":
        _require_string(payload["device_id"], "device_id")
        _require_ascii_text(payload["firmware"], "firmware", 64)
    elif frame_type == "hello_ack":
        if not isinstance(payload["accepted"], bool):
            raise ProtocolError("invalid_shape", "hello_ack accepted must be boolean")
        _require_string(payload["device_id"], "device_id")
        _require_ascii_text(payload["firmware"], "firmware", 64)
    elif frame_type == "probe":
        _require_string(payload["step_id"], "step_id")
        if not _is_int(payload["panel"]) or not 1 <= payload["panel"] <= 4:
            raise ProtocolError("invalid_shape", "probe panel must be one through four")
        _require_ascii_text(payload["stimulus"], "probe stimulus", 64)
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
        _require_ascii_text(payload["detail"], "error detail", 128)
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
        frame = _load_json(line[:-1].decode("utf-8"))
        _check_nesting(frame)
    except UnicodeDecodeError:
        return ProtocolResult(False, "invalid_utf8")
    except DuplicateKeyError:
        return ProtocolResult(False, "duplicate_key")
    except (json.JSONDecodeError, RecursionError, ProtocolError) as exc:
        return ProtocolResult(False, getattr(exc, "code", "invalid_json"))
    if isinstance(frame, dict) and frame.get("v") == V2_PROTOCOL_VERSION:
        return classify_v2_line(line)
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
V2_PROTOCOL_VERSION = 2
V2_FRAME_TYPES = {"agent_snapshot", "snapshot_ack", "focus_intent", "focus_result"}
V2_SOURCE_STATUSES = {"current", "empty", "stale", "unavailable", "offline"}
V2_CODEX_STATES = {"current", "stale", "unavailable", "auth_required", "codex_offline", "host_offline"}
V2_LINK_STATES = {"current", "offline"}
V2_OUTCOMES = {"accepted", "rejected", "stale_target", "not_found", "herdr_offline", "timeout", "uncertain", "vanished", "failed"}
V2_AGENT_SNAPSHOT_FIELDS = {"host_epoch", "snapshot_revision", "source_status", "agents"}
V2_CODEX_FIELDS = {"source_state", "primary", "secondary", "reset_text", "observation_age", "reached_limit", "error_code"}
V2_DIAGNOSTIC_FIELDS = {
    "link_status", "herdr_status", "codex_status", "sync_age", "codex_age",
    "firmware_version", "protocol_version", "bridge_version",
    "device_suffix", "session_suffix", "revision_suffix", "error_code",
}
V2_ERROR_CODES = {""} | {f"E-{number:04d}" for number in range(2400, 2411)}


def _v2_text(value: Any, name: str, maximum: int, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value) or any(ord(char) >= 0x80 for char in value):
        raise ProtocolError("invalid_shape", f"{name} must be bounded ASCII text")


def _v2_opaque(value: Any, name: str, *, allow_empty: bool = False) -> None:
    _v2_text(value, name, 64, allow_empty=allow_empty)
    if value and any(char in "\r\n\t" or ord(char) < 0x21 for char in value):
        raise ProtocolError("invalid_identifier", f"{name} contains disallowed opaque bytes")


def _v2_uint(value: Any, name: str, *, zero: bool = False) -> None:
    if not _is_int(value) or value < (0 if zero else 1) or value > 0xFFFFFFFF:
        raise ProtocolError("invalid_shape", f"{name} must be a bounded uint32")


def _v2_identity(payload: dict[str, Any], *, empty: bool = False) -> None:
    _v2_opaque(payload["pane_id"], "pane_id", allow_empty=empty)
    _v2_opaque(payload["terminal_id"], "terminal_id", allow_empty=empty)
    session = payload["agent_session"]
    if session is not None:
        _v2_opaque(session, "agent_session")
    _v2_uint(payload["source_revision"], "source_revision", zero=empty)
    if not empty and (not payload["pane_id"] or not payload["terminal_id"] or payload["source_revision"] == 0):
        raise ProtocolError("invalid_identity", "occupied identity is incomplete")


def _v2_percent(value: Any, name: str) -> None:
    if value is not None and (not _is_int(value) or not 0 <= value <= 100):
        raise ProtocolError("invalid_shape", f"{name} must be null or an integer percentage")


def _v2_status(value: Any, name: str, allowed: set[str]) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise ProtocolError("invalid_shape", f"{name} is invalid")


def _v2_error_code(value: Any, name: str) -> None:
    _v2_text(value, name, 16, allow_empty=True)
    if value not in V2_ERROR_CODES:
        raise ProtocolError("invalid_shape", f"{name} is not an allowlisted diagnostic code")


def _v2_suffix(value: Any, name: str) -> None:
    _v2_text(value, name, 6)
    if any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for char in value):
        raise ProtocolError("invalid_shape", f"{name} must be an uppercase bounded suffix")


def _v2_codex(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != V2_CODEX_FIELDS:
        raise ProtocolError("unknown_field", "codex view is closed")
    _v2_status(value["source_state"], "codex source_state", V2_CODEX_STATES)
    _v2_percent(value["primary"], "codex primary")
    _v2_percent(value["secondary"], "codex secondary")
    _v2_text(value["reset_text"], "codex reset_text", 32)
    _v2_text(value["observation_age"], "codex observation_age", 16)
    if value["reached_limit"] is not None and not isinstance(value["reached_limit"], bool):
        raise ProtocolError("invalid_shape", "codex reached_limit must be null or boolean")
    _v2_error_code(value["error_code"], "codex error_code")
    if value["error_code"] == "E-2401" and (
        value["source_state"] != "unavailable"
        or value["primary"] is not None
        or value["secondary"] is not None
        or value["reset_text"] != "RESET N/A"
        or value["reached_limit"] is not None
    ):
        raise ProtocolError("invalid_shape", "bucket-unavailable Codex state cannot claim capacity")


def _v2_diagnostics(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != V2_DIAGNOSTIC_FIELDS:
        raise ProtocolError("unknown_field", "diagnostics view is closed")
    _v2_status(value["link_status"], "diagnostics link_status", V2_LINK_STATES)
    _v2_status(value["herdr_status"], "diagnostics herdr_status", V2_SOURCE_STATUSES)
    _v2_status(value["codex_status"], "diagnostics codex_status", V2_CODEX_STATES)
    _v2_text(value["sync_age"], "diagnostics sync_age", 16)
    _v2_text(value["codex_age"], "diagnostics codex_age", 16)
    _v2_text(value["firmware_version"], "diagnostics firmware_version", 16)
    if not _is_int(value["protocol_version"]) or value["protocol_version"] != V2_PROTOCOL_VERSION:
        raise ProtocolError("invalid_shape", "diagnostics protocol_version must be v2")
    _v2_text(value["bridge_version"], "diagnostics bridge_version", 16)
    for key in ("device_suffix", "session_suffix", "revision_suffix"):
        _v2_suffix(value[key], f"diagnostics {key}")
    _v2_error_code(value["error_code"], "diagnostics error_code")


def validate_v2_payload(frame_type: str, payload: Any) -> dict[str, Any]:
    expected = {
        "agent_snapshot": V2_AGENT_SNAPSHOT_FIELDS,
        "snapshot_ack": {"accepted", "host_epoch", "snapshot_revision", "source_status", "reason"},
        "focus_intent": {"action_id", "host_epoch", "snapshot_revision", "slot", "entry_id", "pane_id", "terminal_id", "agent_session", "source_revision"},
        "focus_result": {"action_id", "outcome", "host_epoch", "snapshot_revision", "slot", "entry_id", "pane_id", "terminal_id", "agent_session", "source_revision", "focused"},
    }
    if frame_type not in expected:
        raise ProtocolError("unknown_type", "v2 type is not in the closed product set")
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_payload", "v2 payload must be an object")
    allowed = expected[frame_type]
    if frame_type == "agent_snapshot":
        extended = V2_AGENT_SNAPSHOT_FIELDS | {"codex", "diagnostics"}
        if set(payload) != extended:
            raise ProtocolError("unknown_field" if set(payload) - extended else "invalid_shape", "v2 payload is closed")
    elif set(payload) != allowed:
        raise ProtocolError("unknown_field" if not set(payload).issubset(allowed) else "invalid_shape", "v2 payload is closed")
    _v2_opaque(payload["host_epoch"], "host_epoch")
    _v2_uint(payload["snapshot_revision"], "snapshot_revision")
    if frame_type in {"agent_snapshot", "snapshot_ack"}:
        if payload["source_status"] not in V2_SOURCE_STATUSES:
            raise ProtocolError("invalid_shape", "source_status is invalid")
    if frame_type == "agent_snapshot":
        agents = payload["agents"]
        if not isinstance(agents, list) or len(agents) != 3:
            raise ProtocolError("invalid_shape", "agent_snapshot requires exactly three slots")
        seen: set[int] = set()
        required = {"slot", "entry_id", "title", "discriminator", "since", "age", "state", "pane_id", "terminal_id", "agent_session", "source_revision"}
        for agent in agents:
            if not isinstance(agent, dict) or set(agent) != required:
                raise ProtocolError("unknown_field", "agent slot is closed")
            slot = agent["slot"]
            if not _is_int(slot) or not 0 <= slot < 3 or slot in seen:
                raise ProtocolError("invalid_shape", "agent slots must be unique in 0..2")
            seen.add(slot)
            if agent["state"] not in {"empty", "working", "idle", "blocked", "finished", "settled", "unknown"}:
                raise ProtocolError("invalid_shape", "agent state is invalid")
            empty = agent["state"] == "empty"
            _v2_opaque(agent["entry_id"], "entry_id", allow_empty=empty)
            _v2_text(agent["title"], "title", 64)
            _v2_text(agent["discriminator"], "discriminator", 32)
            _v2_text(agent["since"], "since", 16, allow_empty=True)
            _v2_text(agent["age"], "age", 16, allow_empty=True)
            _v2_identity(agent, empty=empty)
        if seen != {0, 1, 2}:
            raise ProtocolError("invalid_shape", "agent slots must be 0, 1, and 2")
        if set(payload) == V2_AGENT_SNAPSHOT_FIELDS | {"codex", "diagnostics"}:
            _v2_codex(payload["codex"])
            _v2_diagnostics(payload["diagnostics"])
    elif frame_type == "snapshot_ack":
        if not isinstance(payload["accepted"], bool):
            raise ProtocolError("invalid_shape", "snapshot_ack accepted must be boolean")
        _v2_text(payload["reason"], "reason", 64)
    elif frame_type == "focus_intent":
        _v2_opaque(payload["action_id"], "action_id")
        if not _is_int(payload["slot"]) or not 0 <= payload["slot"] < 3:
            raise ProtocolError("invalid_shape", "focus slot must be 0..2")
        _v2_opaque(payload["entry_id"], "entry_id")
        _v2_identity(payload)
    elif frame_type == "focus_result":
        _v2_opaque(payload["action_id"], "action_id")
        if payload["outcome"] not in V2_OUTCOMES:
            raise ProtocolError("invalid_shape", "focus outcome is invalid")
        if not isinstance(payload["focused"], bool):
            raise ProtocolError("invalid_shape", "focused acknowledgement must be boolean")
        if not _is_int(payload["slot"]) or not 0 <= payload["slot"] < 3:
            raise ProtocolError("invalid_shape", "focus result slot must be 0..2")
        _v2_opaque(payload["entry_id"], "entry_id")
        _v2_identity(payload)
    return payload



def new_v2_frame(
    frame_type: str,
    boot_id: str,
    session_id: str,
    seq: int,
    payload: dict[str, Any],
    reply_to: int | None = None,
) -> dict[str, Any]:
    validate_v2_payload(frame_type, payload)
    return {
        "v": V2_PROTOCOL_VERSION,
        "type": frame_type,
        "boot_id": boot_id,
        "session_id": session_id,
        "seq": seq,
        "reply_to": reply_to,
        "digest": _payload_digest(payload),
        "payload": payload,
    }


def validate_v2_frame(frame: Any) -> dict[str, Any]:
    if not isinstance(frame, dict):
        raise ProtocolError("invalid_envelope", "frame must be an object")
    required = {"v", "type", "boot_id", "session_id", "seq", "reply_to", "digest", "payload"}
    if set(frame) != required:
        raise ProtocolError("unknown_field", "frame envelope is closed")
    if not _is_int(frame["v"]) or frame["v"] != V2_PROTOCOL_VERSION:
        raise ProtocolError("invalid_version", "only protocol v2 is accepted")
    if frame["type"] not in V2_FRAME_TYPES:
        raise ProtocolError("unknown_type", "frame type is not in the closed v2 set")
    _require_string(frame["boot_id"], "boot_id")
    _require_string(frame["session_id"], "session_id")
    if not _is_int(frame["seq"]) or not 1 <= frame["seq"] <= 0xFFFFFFFF:
        raise ProtocolError("invalid_sequence", "seq must be a positive uint32")
    if frame["reply_to"] is not None and (not _is_int(frame["reply_to"]) or not 1 <= frame["reply_to"] <= 0xFFFFFFFF):
        raise ProtocolError("invalid_reply_to", "reply_to must be null or a positive uint32")
    if not isinstance(frame["digest"], str) or not DIGEST_PATTERN.fullmatch(frame["digest"]):
        raise ProtocolError("invalid_digest", "digest must be a lowercase 64-bit hex value")
    validate_v2_payload(frame["type"], frame["payload"])
    if frame["digest"] != _payload_digest(frame["payload"]):
        raise ProtocolError("digest_mismatch", "payload digest does not match canonical payload")
    return frame


def encode_v2_frame(frame: dict[str, Any]) -> bytes:
    validate_v2_frame(frame)
    encoded = (json.dumps(frame, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    if len(encoded) > MAX_LINE_BYTES:
        raise ProtocolError("line_too_long", "encoded frame exceeds 4096 bytes including LF")
    return encoded


def classify_v2_line(line: bytes) -> ProtocolResult:
    if not line:
        return ProtocolResult(False, "empty_line")
    if len(line) > MAX_LINE_BYTES:
        return ProtocolResult(False, "line_too_long")
    if not line.endswith(b"\n"):
        return ProtocolResult(False, "missing_lf")
    try:
        frame = _load_json(line[:-1].decode("utf-8"))
        _check_nesting(frame)
        validated = validate_v2_frame(frame)
    except UnicodeDecodeError:
        return ProtocolResult(False, "invalid_utf8")
    except DuplicateKeyError:
        return ProtocolResult(False, "duplicate_key")
    except (json.JSONDecodeError, RecursionError):
        return ProtocolResult(False, "invalid_json")
    except ProtocolError as exc:
        return ProtocolResult(False, exc.code)
    return ProtocolResult(True, "ok", validated)



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
        expected_kind: str | None = None,
        expected_key: int | None = None,
        expected_direction: str | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
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
    """Run every vector through Draft 2020-12 and the host codec/session."""
    from jsonschema import Draft202012Validator

    fixture = _load_json(open(fixture_path, encoding="utf-8").read())
    schema = _load_json(open(schema_path, encoding="utf-8").read())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    if schema.get("x-max-encoded-line-bytes-including-lf") != MAX_LINE_BYTES:
        raise AssertionError("schema bound drift")
    vectors = fixture.get("vectors")
    if not isinstance(vectors, list) or not vectors:
        raise AssertionError("golden fixture is empty")
    for vector in vectors:
        line_value = vector.get("line")
        schema_outcome = "not_evaluated"
        if line_value == "synthetic:oversized":
            line = b"x" * MAX_LINE_BYTES + b"\n"
            schema_outcome = "invalid"
        elif isinstance(line_value, str):
            line = line_value.encode("utf-8")
        else:
            raise AssertionError(f"{vector.get('id')}: missing line")
        expected = vector["expected"]
        try:
            parsed = _load_json(line[:-1].decode("utf-8")) if line.endswith(b"\n") else None
        except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError, RecursionError):
            parsed = None
        if parsed is not None:
            schema_outcome = "valid" if validator.is_valid(parsed) else "invalid"
        if expected.get("schema") is not None and expected["schema"] != schema_outcome:
            raise AssertionError(f"{vector.get('id')}: schema {schema_outcome}, expected {expected['schema']}")
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
