"""Exact Phase 1 host invocation: ``python -m phase1_bringup``."""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any

from .evidence import EvidenceError, EvidenceWriter, self_check_roundtrip

MAX_LINE_BYTES = 4096
PROTOCOL_VERSION = 1
FRAME_TYPES = {"hello", "hello_ack", "probe", "probe_ack", "event", "error"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def package_root() -> Path:
    return repo_root() / "tools" / "phase1_bringup"


def load_schema(path: Path) -> dict[str, Any]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    if schema.get("x-max-encoded-line-bytes-including-lf") != MAX_LINE_BYTES:
        raise ValueError("schema does not freeze the 4096-byte including-LF bound")
    if schema.get("properties", {}).get("v", {}).get("const") != PROTOCOL_VERSION:
        raise ValueError("schema does not freeze protocol v1")
    if set(schema.get("properties", {}).get("type", {}).get("enum", [])) != FRAME_TYPES:
        raise ValueError("schema frame type set is not closed")
    if schema.get("additionalProperties") is not False:
        raise ValueError("schema envelope must reject unknown properties")
    return schema


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
        "hello_ack": {"accepted", "protocol"},
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
    if frame["type"] == "hello_ack" and not isinstance(payload["accepted"], bool):
        raise ValueError("hello_ack accepted must be boolean")
    if frame["type"] == "probe":
        if not isinstance(payload["step_id"], str) or not payload["step_id"]:
            raise ValueError("probe step_id must be non-empty")
        if not _is_int(payload["panel"]) or not 1 <= payload["panel"] <= 4:
            raise ValueError("probe panel must be one through four")
        if not isinstance(payload["stimulus"], str) or not 1 <= len(payload["stimulus"]) <= 64:
            raise ValueError("probe stimulus must be bounded")
    if frame["type"] == "probe_ack":
        if not isinstance(payload["accepted"], bool) or not isinstance(payload["step_id"], str):
            raise ValueError("probe_ack fields are invalid")
    if frame["type"] == "event":
        if payload["kind"] != "key_transition" or not isinstance(payload["step_id"], str):
            raise ValueError("event kind or step_id is invalid")
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


def dependency_gate() -> dict[str, str]:
    expected_venv = (package_root() / ".venv").resolve()
    actual_prefix = Path(sys.prefix).resolve()
    if actual_prefix != expected_venv:
        raise RuntimeError("run only from tools/phase1_bringup/.venv/bin/python")
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required")
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("pyserial 3.5 is not installed in the plan-owned environment") from exc
    if getattr(serial, "__version__", None) != "3.5":
        raise RuntimeError("the plan-owned environment must resolve pyserial 3.5 exactly")
    serial_path = Path(serial.__file__).resolve()
    if expected_venv not in serial_path.parents:
        raise RuntimeError("pyserial resolved outside the plan-owned environment")
    return {
        "python": ".".join(map(str, sys.version_info[:3])),
        "python_executable": str(Path(sys.executable).resolve()),
        "pyserial": serial.__version__,
        "pyserial_path": str(serial_path),
    }


def dependency_lock() -> dict[str, Any]:
    return {
        "platformio": "https://github.com/pioarduino/platform-espressif32/releases/download/55.03.311/platform-espressif32.zip",
        "arduino_esp32": "3.3.11",
        "board_library": "T-Keyboard-S3-Pro-Library@c46c4cb5752c04bca417c1f959dac6f5acdb5142",
        "buttonsense": "ButtonSense@b1aeb22a73c523b37ebd11bee54000b77484f76c",
        "lovyangfx": "1.2.26",
        "arduinojson": "7.4.3",
        "usb_flags": ["ARDUINO_USB_MODE=1", "ARDUINO_USB_CDC_ON_BOOT=1"],
    }


def new_frame(frame_type: str, boot_id: str, session_id: str, seq: int, payload: dict[str, Any], reply_to: int | None = None) -> dict[str, Any]:
    return {"v": 1, "type": frame_type, "boot_id": boot_id, "session_id": session_id, "seq": seq, "reply_to": reply_to, "payload": payload}


def _run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)


def _human_confirmation(step_id: str) -> str:
    print("Observe the keypad, then choose: [Y] Pass  [N] Fail  [R] Repeat.")
    while True:
        answer = input(f"[{step_id}] type Y {step_id}, N {step_id}, or R {step_id}: ").strip().upper().split()
        if len(answer) == 2 and answer[0] in {"Y", "N", "R"} and answer[1] == step_id:
            return answer[0]
        print(f"Enter alone cannot confirm. Type one action followed by the visible step identifier {step_id}.")


def _discover_port() -> str | None:
    import serial.tools.list_ports

    candidates = list(serial.tools.list_ports.comports())
    if len(candidates) != 1:
        return None
    return candidates[0].device


def run_start(schema_path: Path, evidence_root: Path, port: str | None = None) -> int:
    environment = dependency_gate()
    load_schema(schema_path)
    import serial

    selected_port = port or _discover_port()
    if selected_port is None:
        print("No keypad detected")
        return 2
    run_id = _run_id()
    boot_id = "host-" + secrets.token_hex(6)
    session_id = "session-" + secrets.token_hex(6)
    writer = EvidenceWriter(evidence_root, run_id)
    machine: dict[str, Any] = {"hello": "not started", "probe": "not started", "event": "not started"}
    physical = "unavailable"
    try:
        with serial.Serial(selected_port, 115200, timeout=0.5) as connection:
            seq = 0
            seq += 1
            hello = new_frame("hello", boot_id, session_id, seq, {"device_id": "host", "firmware": "phase1-host", "protocol": 1})
            connection.write(encode_frame(hello))
            hello_ack = _receive_correlated(connection, session_id, seq, {"hello_ack"})
            machine["hello"] = {"acknowledged": True, "reply": hello_ack["seq"]}
            step_id = "PANEL-1"
            seq += 1
            probe = new_frame("probe", boot_id, session_id, seq, {"step_id": step_id, "panel": 1, "stimulus": "1 ^ CYAN"})
            connection.write(encode_frame(probe))
            probe_ack = _receive_correlated(connection, session_id, seq, {"probe_ack"})
            machine["probe"] = {"acknowledged": probe_ack["payload"]["accepted"], "reply": probe_ack["seq"], "step_id": step_id}
            while True:
                event = _receive_event(connection, session_id, step_id)
                machine["event"] = {"received": True, "key": event["payload"]["key"], "step_id": step_id}
                action = _human_confirmation(step_id)
                if action == "R":
                    seq += 1
                    connection.write(encode_frame(new_frame("probe", boot_id, session_id, seq, {"step_id": step_id, "panel": 1, "stimulus": "1 ^ CYAN"})))
                    _receive_correlated(connection, session_id, seq, {"probe_ack"})
                    continue
                physical = "confirmed" if action == "Y" else "failed"
                print("Observation recorded as PASS." if action == "Y" else "Observation recorded as FAIL. Correct the issue or repeat this step before qualification.")
                break
        status = "pass" if physical == "confirmed" and machine["event"] != "not started" else "fail"
        manifest = {"schema_version": 1, "kind": "manifest", "run_id": run_id, "status": status, "protocol": {"version": 1, "max_line_bytes_including_lf": MAX_LINE_BYTES, "transport": "usb-cdc"}, "environment": {**environment, "dependency_lock": dependency_lock()}, "device": {"port_discovery": "descriptor-only", "selected_port": "redacted"}}
        result = {"schema_version": 1, "kind": "result", "run_id": run_id, "status": status, "physical_observation": physical, "machine_facts": machine, "transport": {"type": "usb-cdc", "bounded": True, "version": 1, "correlated": True}}
        writer.write(manifest, result)
        print("Evidence preserved and hash-verified.")
        return 0 if status == "pass" else 1
    except Exception as exc:
        failure_manifest = {"schema_version": 1, "kind": "manifest", "run_id": run_id, "status": "fail", "protocol": {"version": 1, "max_line_bytes_including_lf": MAX_LINE_BYTES}, "environment": environment, "device": {"port_discovery": "descriptor-only"}}
        failure_result = {"schema_version": 1, "kind": "result", "run_id": run_id, "status": "fail", "physical_observation": physical, "machine_facts": machine, "error": {"type": type(exc).__name__, "message": str(exc)}}
        try:
            writer.write(failure_manifest, failure_result)
        except EvidenceError:
            pass
        print(f"Tracer failed; evidence was preserved: {exc}", file=sys.stderr)
        return 1


def _receive_line(connection: Any) -> dict[str, Any] | None:
    line = connection.readline()
    if not line:
        return None
    return decode_frame(line)


def _receive_correlated(connection: Any, session_id: str, request_seq: int, allowed: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        frame = _receive_line(connection)
        if frame is None:
            continue
        if frame["session_id"] != session_id:
            raise RuntimeError("session correlation mismatch")
        if frame["type"] == "error":
            raise RuntimeError(f"device rejected frame: {frame['payload']['code']}")
        if frame["type"] in allowed and frame["reply_to"] == request_seq:
            return frame
    raise TimeoutError("timed out waiting for correlated acknowledgement")

def _receive_event(connection: Any, session_id: str, step_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        frame = _receive_line(connection)
        if frame is None:
            continue
        if frame["session_id"] != session_id:
            raise RuntimeError("session correlation mismatch")
        if frame["type"] == "event" and frame["payload"]["step_id"] == step_id:
            return frame
        if frame["type"] == "error":
            raise RuntimeError(f"device rejected probe: {frame['payload']['code']}")
    raise TimeoutError("timed out waiting for matching physical key transition")


def _contract_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"{label} is not readable: {path}") from exc


def _require_contract_tokens(text: str, tokens: tuple[str, ...], label: str) -> None:
    missing = [token for token in tokens if token not in text]
    if missing:
        raise RuntimeError(f"{label} is missing required contract tokens: {', '.join(missing)}")


def firmware_contract_check(path: Path) -> None:
    text = _contract_text(path, "firmware contract")
    _require_contract_tokens(
        text,
        (
            "DisplayMapping",
            "KeyMapping",
            "EncoderMapping",
            "LedMapping",
            "BrightnessObservation",
            "PhysicalMap",
            "ObservationState::Unavailable",
            "human_confirmed",
        ),
        "firmware contract",
    )


def renderer_contract_check(path: Path) -> None:
    text = _contract_text(path, "device render contract")
    _require_contract_tokens(
        text,
        (
            "BringupState::Wait",
            "BringupState::Map",
            "BringupState::Press",
            "BringupState::TurnCw",
            "BringupState::TurnCcw",
            "BringupState::Click",
            "BringupState::Brightness",
            "BringupState::Pair",
            "BringupState::Pass",
            "BringupState::Fail",
            "BringupState::LinkLost",
            "kSafeInset = 4",
            "kPanelCount = 4",
            "display.fillScreen(TFT_BLACK)",
            "drawWait",
        ),
        "device render contract",
    )


def command_self_check(args: argparse.Namespace) -> int:
    if args.environment:
        environment = dependency_gate()
        print(f"Environment: Python {environment['python']}; pyserial {environment['pyserial']}")
    if args.schema:
        load_schema(Path(args.schema))
        print("Schema: v1 closed envelope; 4096-byte including-LF bound")
        base = new_frame("probe", "boot", "session", 1, {"step_id": "PANEL-1", "panel": 1, "stimulus": "1 ^ CYAN"})
        if decode_frame(encode_frame(base)) != base:
            raise RuntimeError("frame round trip mismatch")
    if args.firmware_contract:
        firmware_contract_check(Path(args.firmware_contract))
        print("Firmware contract: physical map fields remain unapproved")
    if args.device_render_contract:
        renderer_contract_check(Path(args.device_render_contract))
        print("Device render contract: fixed states and sequential 4 px panels present")
    if args.evidence_roundtrip:
        path = self_check_roundtrip(Path(args.evidence_roundtrip))
        print(f"Evidence round trip: verified {path.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phase1_bringup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    self_check = subparsers.add_parser("self-check")
    self_check.add_argument("--environment", action="store_true")
    self_check.add_argument("--schema", type=Path)
    self_check.add_argument("--firmware-contract", type=Path)
    self_check.add_argument("--device-render-contract", type=Path)
    self_check.add_argument("--evidence-roundtrip", type=Path)
    start = subparsers.add_parser("start")
    start.add_argument("--schema", type=Path, default=repo_root() / "protocol" / "schema" / "v1.json")
    start.add_argument("--evidence-root", type=Path, default=repo_root() / "artifacts" / "phase1")
    start.add_argument("--port")
    args = parser.parse_args(argv)
    try:
        if args.command == "self-check":
            return command_self_check(args)
        return run_start(args.schema, args.evidence_root, args.port)
    except (EvidenceError, RuntimeError, ValueError, OSError) as exc:
        print(f"phase1_bringup: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
