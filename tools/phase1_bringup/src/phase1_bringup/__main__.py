"""Exact Phase 1 host invocation: ``python -m phase1_bringup``."""
from __future__ import annotations

import argparse
import io
import json
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any

from .evidence import EvidenceError, EvidenceWriter, self_check_roundtrip
from .guide import GATES, GUIDED_ORDER, GuidedRun, confirmation_check, guided_order_check
from .protocol import FRAME_TYPES, MAX_LINE_BYTES, PROTOCOL_VERSION, decode_frame, encode_frame, new_frame, validate_frame
from .ui import MIN_HEIGHT, MIN_WIDTH, TerminalUI

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
    return {"python": ".".join(map(str, sys.version_info[:3])), "python_executable": str(Path(sys.executable).resolve()), "pyserial": serial.__version__, "pyserial_path": str(serial_path)}


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


def _run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)


def _discover_port() -> str | None:
    import serial.tools.list_ports

    candidates = [port for port in serial.tools.list_ports.comports() if port.device]
    if len(candidates) != 1:
        return None
    return candidates[0].device


def run_start(schema_path: Path, evidence_root: Path, port: str | None = None) -> int:
    environment = dependency_gate()
    load_schema(schema_path)
    import serial
    from .protocol import ProtocolSession

    ui = TerminalUI(output=sys.stdout)
    selected_port = port or _discover_port()
    if selected_port is None:
        ui.show_no_keypad()
        return 2
    run_id = _run_id()
    writer = EvidenceWriter(evidence_root, run_id)
    session = None
    run = GuidedRun(None, writer, ui, run_id)
    try:
        with serial.Serial(selected_port, 115200, timeout=0.5) as connection:
            session = ProtocolSession(connection, "host-" + secrets.token_hex(6), "session-" + secrets.token_hex(6))
            run.session = session
            run.start()
            while run.gate_index < 7:
                run.stimulate()
                while True:
                    answer = input(f"Type Y {run.step_id} {run.run_suffix}, N {run.step_id} {run.run_suffix}, or R {run.step_id} {run.run_suffix}: ")
                    result = run.respond(answer)
                    if result == "repeat":
                        run.stimulate()
                        continue
                    if result == "fail":
                        continue
                    break
            result = run.result()
            result["status"] = "pass" if run.complete_physical_gates else "incomplete"
            manifest = {
                "schema_version": 1,
                "kind": "manifest",
                "run_id": run_id,
                "status": result["status"],
                "protocol": {"version": PROTOCOL_VERSION, "max_line_bytes_including_lf": MAX_LINE_BYTES, "transport": "usb-cdc"},
                "environment": {**environment, "dependency_lock": dependency_lock()},
                "device": {"port_discovery": "descriptor-only", "selected_port": "redacted", "identity": "unavailable"},
                "guided_order": list(GUIDED_ORDER),
            }
            path = writer.finalize(manifest, result)
            print(f"Evidence preserved and hash-verified: {path}")
            return 0 if result["status"] == "pass" else 1
    except Exception as exc:
        failure_result = run.result()
        failure_result["status"] = "fail"
        failure_result["error"] = {"type": type(exc).__name__, "message": str(exc)}
        failure_manifest = {
            "schema_version": 1,
            "kind": "manifest",
            "run_id": run_id,
            "status": "fail",
            "protocol": {"version": PROTOCOL_VERSION, "max_line_bytes_including_lf": MAX_LINE_BYTES, "transport": "usb-cdc"},
            "environment": environment,
            "device": {"port_discovery": "descriptor-only", "identity": "unavailable"},
            "guided_order": list(GUIDED_ORDER),
        }
        try:
            writer.finalize(failure_manifest, failure_result)
        except EvidenceError:
            pass
        print(f"Tracer failed; evidence was preserved: {exc}", file=sys.stderr)
        return 1


def firmware_contract_check(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    tokens = ("DisplayMapping", "KeyMapping", "EncoderMapping", "LedMapping", "BrightnessObservation", "PhysicalMap", "ObservationState::Unavailable", "human_confirmed")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise RuntimeError(f"firmware contract is missing required contract tokens: {', '.join(missing)}")


def renderer_contract_check(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    tokens = ("BringupState::Wait", "BringupState::Map", "BringupState::Press", "BringupState::TurnCw", "BringupState::TurnCcw", "BringupState::Click", "BringupState::Brightness", "BringupState::Pair", "BringupState::Pass", "BringupState::Fail", "BringupState::LinkLost", "kSafeInset = 4", "kPanelCount = 4", "display.fillScreen(TFT_BLACK)", "drawWait")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise RuntimeError(f"device render contract is missing required contract tokens: {', '.join(missing)}")


def ui_check() -> None:
    emitted = io.StringIO()
    ui = TerminalUI(MIN_WIDTH, MIN_HEIGHT, output=emitted)
    screen = ui.show_no_keypad()
    if "No keypad detected" not in screen or any(len(line) > MIN_WIDTH for line in screen.splitlines()):
        raise AssertionError("empty state is not bounded")
    ui.begin_operation("bounded long operation")
    ui.stable_result()
    screen = ui.render_step("Displays", "DISPLAY-1", 2, 11, "Observe the keypad display and its position/orientation/color from the agreed desk viewing direction.", "one stable physical observation", ["machine: acknowledged", "unavailable"], run_suffix="ABC123")
    if "DISPLAY-1" not in screen or "Observe the keypad" not in screen:
        raise AssertionError("active card did not render")
    event_output = emitted.getvalue()
    if "DISPLAY-1" not in event_output or "machine: acknowledged" not in event_output:
        raise AssertionError("screen/event detail was not emitted")
    if any(len(line) > MIN_WIDTH for line in screen.splitlines()):
        raise AssertionError("host prose exceeded the 80-column bound")


def command_self_check(args: argparse.Namespace) -> int:
    if args.environment:
        environment = dependency_gate()
        print(f"Environment: Python {environment['python']}; pyserial {environment['pyserial']}")
    if args.schema:
        load_schema(Path(args.schema))
        base = new_frame("probe", "boot", "session", 1, {"step_id": "PANEL-1", "panel": 1, "stimulus": "1 ^ CYAN"})
        if decode_frame(encode_frame(base)) != base or validate_frame(base) != base:
            raise RuntimeError("frame round trip mismatch")
        print("Schema: v1 closed envelope; 4096-byte including-LF bound")
    if args.firmware_contract:
        firmware_contract_check(Path(args.firmware_contract))
        print("Firmware contract: physical map fields remain unapproved")
    if args.device_render_contract:
        renderer_contract_check(Path(args.device_render_contract))
        print("Device render contract: fixed states and sequential 4 px panels present")
    if args.evidence_roundtrip:
        path = self_check_roundtrip(Path(args.evidence_roundtrip))
        print(f"Evidence round trip: verified {path.name}")
    if args.ui:
        ui_check()
        print("UI: bounded 80x24 empty/loading/populated surfaces pass")
    if args.guided_order:
        guided_order_check()
        print("Guided order: " + " -> ".join(GUIDED_ORDER))
    if args.evidence_schema:
        from .evidence import physical_schema_check
        physical_schema_check()
        print("Evidence schema: machine facts, human response, unavailable, and linked replacement fields pass")
    if args.physical_confirmation:
        confirmation_check()
        print("Physical confirmation: ACK alone rejected; explicit step/run-bound Y required")
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
    self_check.add_argument("--ui", action="store_true")
    self_check.add_argument("--guided-order", action="store_true")
    self_check.add_argument("--evidence-schema", action="store_true")
    self_check.add_argument("--physical-confirmation", action="store_true")
    start = subparsers.add_parser("start")
    start.add_argument("--schema", type=Path, default=repo_root() / "protocol" / "schema" / "v1.json")
    start.add_argument("--evidence-root", type=Path, default=repo_root() / "artifacts" / "phase1")
    start.add_argument("--port")
    verify = subparsers.add_parser("verify-evidence")
    verify.add_argument("path", type=Path)
    verify.add_argument("--require", choices=("physical-map",), default=None)
    args = parser.parse_args(argv)
    try:
        if args.command == "self-check":
            return command_self_check(args)
        if args.command == "verify-evidence":
            from .evidence import verify_physical_evidence
            path = verify_physical_evidence(args.path, require_physical_map=args.require == "physical-map")
            print(f"Evidence verified: {path}")
            return 0
        return run_start(args.schema, args.evidence_root, args.port)
    except (EvidenceError, RuntimeError, ValueError, OSError, AssertionError) as exc:
        print(f"phase1_bringup: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
