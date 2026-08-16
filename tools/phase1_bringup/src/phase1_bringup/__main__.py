"""Exact Phase 1 host invocation: ``python -m phase1_bringup``."""
from __future__ import annotations

import argparse
import inspect
import io
import json
import os
import platform
import re
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .discovery import discovery_check
from .evidence import EvidenceError, EvidenceWriter, MACHINE_BATCH_GATES, archive_phase1, build_selected, parse_group_responses, resolve_qualification_pointer, select_transport, selection_self_check, self_check_roundtrip, verify_archive_lock, verify_build_lock, verify_machine_run, verify_physical_evidence, verify_qualification_lock, verify_selection_lock
from .guide import BATCH_GATE_ORDER, GATES, GUIDED_ORDER, RECOVERY_TOUR_STEPS, BatchRun, GuidedRun, batch_key_event_check, batch_no_ack_check, batch_order_check, batch_parser_check, confirmation_check, guided_order_check, pairing_ui_check, recovery_tour_check, recovery_ui_check
from .pairing import pairing_check
from .protocol import FRAME_TYPES, MAX_LINE_BYTES, PROTOCOL_VERSION, decode_frame, encode_frame, new_frame, protocol_bootstrap_check, protocol_golden_check, validate_frame
from .serial_link import reconnect_exact, serial_reconnect_check, udev_rule_check
from .ui import MIN_HEIGHT, MIN_WIDTH, TerminalUI
 
 
def qualification_manifest_check(path: Path) -> None:
    """Verify the frozen qualification manifest and profile invariants."""
    from .qualification import qualification_manifest_check as _check

    _check(path)




def qualification_cli_check() -> None:
    """Ensure the operator command is registered without opening hardware."""
    status = main(["qualify", "--transport", "usb", "--manifest", "/nonexistent/qualification-manifest.json"])
    if status != 2:
        raise AssertionError("qualify command did not fail closed before hardware access")

def qualification_early_rejection_check(manifest_path: Path) -> None:
    """Exercise input-event matching, bounded smoke mode, and overlap-N persistence with fake I/O only."""
    from . import qualification as qualification_module
    from .pairing import PairingStore

    class FakeLink:
        def write(self, data: bytes) -> int:
            return len(data)

        def readline(self) -> bytes:
            return b"ack\n"

        def close(self) -> None:
            return None

    class FakeCandidate:
        def snapshot(self) -> dict[str, str]:
            return {"device": "fake", "vid": "0x303a", "pid": "0x1001"}

    class FakeSession:
        connection: Any

        def stimulate(self, step_id: str, panel: int, stimulus: str) -> None:
            self.connection.write(f"{step_id}:{panel}:{stimulus}\n".encode())
            self.connection.readline()
        def request(self, frame_type: str, payload: dict[str, Any], allowed: set[str]) -> tuple[dict[str, Any], object]:
            self.connection.write(f"{frame_type}:{payload['request']}\n".encode())
            self.connection.readline()
            names = ("acknowledged", "digest_mismatch", "duplicate", "largest_free_block", "malformed", "max_display_flush_us", "max_key_poll_gap_us", "minimum_free_heap", "out_of_order", "parser_high_water", "queue_high_water", "received", "rejected", "sent", "watchdog_reset")
            return {"payload": {name: 0 for name in names}}, object()
        def wait_event(self, step_id: str, **expected: Any) -> dict[str, Any]:
            payload: dict[str, Any] = {"step_id": step_id, "kind": expected["expected_kind"]}
            if "expected_key" in expected:
                payload["key"] = expected["expected_key"]
            if "expected_direction" in expected:
                payload["direction"] = expected["expected_direction"]
            return {"payload": payload}

    def fake_reconnect(*_args: Any, **_kwargs: Any) -> tuple[FakeCandidate, FakeLink, FakeSession, list[Any]]:
        link = FakeLink()
        session = FakeSession()
        session.connection = link
        return FakeCandidate(), link, session, []

    original_load = PairingStore.load
    original_reconnect = qualification_module.reconnect_exact
    original_checkpoint = qualification_module._operator_checkpoint
    checkpoint_labels: list[str] = []
    PairingStore.load = lambda _self: object()
    qualification_module.reconnect_exact = fake_reconnect
    def fake_checkpoint(label: str, _instruction: str) -> str:
        checkpoint_labels.append(label)
        return "N"
    qualification_module._operator_checkpoint = fake_checkpoint
    try:
        with tempfile.TemporaryDirectory() as directory:
            evidence_root = Path(directory)
            status = qualification_module.run_qualification(
                Path(manifest_path),
                "usb",
                evidence_root,
                evidence_root / "binding.json",
            )
            if status != 1:
                raise AssertionError("overlap N must return a failing qualification status")
            result_paths = list(evidence_root.glob("*/result.json"))
            traffic_paths = list(evidence_root.glob("*/traffic.json"))
            if len(result_paths) != 1 or len(traffic_paths) != 1:
                raise AssertionError("overlap N did not preserve an immutable result and traffic file")
            result = json.loads(result_paths[0].read_text(encoding="utf-8"))
            if any(result.get("counters", {}).get(name) != 0 for name in ("sent", "received", "acknowledged")):
                raise AssertionError("preflight traffic contaminated post-reset strict counters")
            traffic = json.loads(traffic_paths[0].read_text(encoding="utf-8"))
            if checkpoint_labels != ["preflight-cues"]:
                raise AssertionError("physical-overlap prompt ordering changed")
            cue_bytes = b"".join(bytes.fromhex(item["bytes"]) for item in traffic if item.get("phase") == "preflight")
            for cue in (b"PANEL-1", b"LED-13", b"LED-ALL", b"LED-OFF", b"BRIGHTNESS-LOW", b"KEY-4", b"ENC-CW", b"ENC-CLICK"):
                if cue not in cue_bytes:
                    raise AssertionError(f"missing preflight cue {cue!r}")
            if result.get("status") != "fail" or result.get("physical_overlap") != "N":
                raise AssertionError("overlap N was not recorded as a non-pass result")
            if not any(item.get("phase") == "preflight" and item.get("direction") == "host_to_device" for item in traffic):
                raise AssertionError("physical-overlap prompt occurred before a preflight device write")
        with tempfile.TemporaryDirectory() as directory:
            evidence_root = Path(directory)
            status = qualification_module.run_qualification(
                Path(manifest_path),
                "usb",
                evidence_root,
                evidence_root / "binding.json",
                smoke_seconds=2,
            )
            smoke_results = list(evidence_root.glob("*/result.json"))
            if len(smoke_results) != 1:
                raise AssertionError("automated smoke mode did not preserve a result")
            smoke_result = json.loads(smoke_results[0].read_text(encoding="utf-8"))
            if status != 0 or smoke_result.get("status") != "incomplete" or smoke_result.get("smoke_status") != "pass":
                raise AssertionError(f"automated smoke mode did not pass (exit {status}): {smoke_result}")
    finally:
        PairingStore.load = original_load
        qualification_module.reconnect_exact = original_reconnect
        qualification_module._operator_checkpoint = original_checkpoint



def qualification_no_false_pass_check(path: Path) -> None:
    """Ensure a PASS cannot be claimed without firmware metrics/counters."""
    from .qualification import load_manifest, validate_qualification_result

    manifest = load_manifest(path)
    fake_pass = {
        "status": "pass",
        "physical_overlap": "Y",
        "counters": {"expected": 3800, "sent": 3800, "received": 3800, "acknowledged": 3800},
        "metrics": {name: None for name in ("minimum_free_heap", "largest_free_block", "parser_high_water", "queue_high_water", "max_display_flush_us", "max_key_poll_gap_us")},
        "strict_failure_counters_available": False,
        "resource_metrics_available": False,
    }
    try:
        validate_qualification_result(fake_pass, manifest)
    except ValueError:
        return
    raise AssertionError("qualification validator accepted a PASS without measured firmware evidence")
ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def package_root() -> Path:
    return repo_root() / "tools" / "phase1_bringup"


def load_schema(path: Path) -> dict[str, Any]:
    from .protocol import _load_json
    from jsonschema import Draft202012Validator

    schema = _load_json(path.read_text(encoding="utf-8"))
    if schema.get("x-max-encoded-line-bytes-including-lf") != MAX_LINE_BYTES:
        raise ValueError("schema does not freeze the 4096-byte including-LF bound")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("schema must declare Draft 2020-12")
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
    if not ((3, 11) <= sys.version_info[:2] < (3, 15)):
        raise RuntimeError("supported Python runtime is 3.11 through 3.14")
    try:
        import serial
        import jsonschema
        from importlib.metadata import version as package_version
    except ImportError as exc:
        raise RuntimeError("pyserial 3.5 and jsonschema 4.25.1 are required in the plan-owned environment") from exc
    if getattr(serial, "__version__", None) != "3.5":
        raise RuntimeError("the plan-owned environment must resolve pyserial 3.5 exactly")
    if package_version("jsonschema") != "4.25.1":
        raise RuntimeError("the plan-owned environment must resolve jsonschema 4.25.1 exactly")
    serial_path = Path(serial.__file__).resolve()
    jsonschema_path = Path(jsonschema.__file__).resolve()
    if expected_venv not in serial_path.parents or expected_venv not in jsonschema_path.parents:
        raise RuntimeError("dependencies resolved outside the plan-owned environment")
    return {
        "python": platform.python_version(),
        "python_executable": str(Path(sys.executable).resolve()),
        "pyserial": serial.__version__,
        "jsonschema": package_version("jsonschema"),
        "pyserial_path": str(serial_path),
        "jsonschema_path": str(jsonschema_path),
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


def _run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)


def _discover_port() -> str | None:
    import serial.tools.list_ports

    candidates = [port for port in serial.tools.list_ports.comports() if port.device]
    if len(candidates) != 1:
        return None
    return candidates[0].device


def run_pair(schema_path: Path, evidence_root: Path, binding_path: Path) -> int:
    """Pair the single physically intended keypad by a fresh displayed challenge."""
    environment = dependency_gate()
    load_schema(schema_path)
    import serial

    from .discovery import enumerate_candidates
    from .pairing import PairingError, PairingStore, new_challenge, pair_exact_candidate
    from .protocol import ProtocolSession

    run_id = _run_id()
    writer = EvidenceWriter(evidence_root, run_id)
    candidates = enumerate_candidates()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "manifest",
        "run_id": run_id,
        "workflow": "pairing",
        "protocol": {"version": PROTOCOL_VERSION, "max_line_bytes_including_lf": MAX_LINE_BYTES, "transport": "usb-cdc"},
        "environment": {**environment, "dependency_lock": dependency_lock()},
        "candidates": [candidate.snapshot() for candidate in candidates],
    }
    result: dict[str, Any] = {"schema_version": 1, "kind": "result", "run_id": run_id, "status": "fail", "pairing": {"status": "not_started"}}
    try:
        if len(candidates) == 0:
            raise PairingError("zero", "No keypad detected")
        if len(candidates) != 1:
            raise PairingError("ambiguous", "Multiple compatible keypads detected. Disconnect other candidates and retry; no device was paired.")
        candidate = candidates[0]
        challenge = new_challenge()
        with serial.Serial(candidate.device, 115200, timeout=0.5) as connection:
            session = ProtocolSession(connection, "host-" + secrets.token_hex(6), "session-" + secrets.token_hex(6))
            session.hello()
            session.stimulate("PAIR", 1, "PAIR-" + challenge)
            print("Confirm that the keypad displays " + challenge + ". Type the challenge to pair this device.")
            typed = input("Challenge: ")
            binding = pair_exact_candidate([candidate], {candidate.device: session.device}, challenge, typed, PairingStore(binding_path), typed == challenge)
        result["status"] = "pass"
        result["pairing"] = {"status": "paired", "device_id": binding.device_id, "device_suffix": binding.device_id[-4:], "protocol": binding.protocol, "firmware": binding.firmware, "challenge": challenge}
        print("Paired with the physically confirmed keypad.")
    except Exception as exc:
        result["pairing"] = {"status": "rejected", "code": getattr(exc, "code", type(exc).__name__), "message": str(exc), "binding_unchanged": True}
        print(str(exc), file=sys.stderr)
    path = writer.write(manifest, result)
    print(f"Pairing evidence preserved and hash-verified: {path}")
    return 0 if result["status"] == "pass" else 1


def run_recover(schema_path: Path, evidence_root: Path, binding_path: Path, interruption: str) -> int:
    """Perform one exact-device, fresh-session recovery without manual port selection."""
    environment = dependency_gate()
    load_schema(schema_path)
    import serial

    from .pairing import PairingStore, PairingError

    run_id = _run_id()
    writer = EvidenceWriter(evidence_root, run_id)
    binding = PairingStore(binding_path).load()
    if binding is None:
        raise PairingError("unpaired", "No paired keypad binding exists; run the physical pairing gate first.")
    discarded_ids = [1]

    def opener(candidate: Any) -> Any:
        return serial.Serial(candidate.device, 115200, timeout=0.5)

    selected, link, session, transitions = reconnect_exact(binding, None, opener, discarded_ids=discarded_ids)
    try:
        for transition in transitions:
            event = transition.as_dict()
            event["detail"] = f"{interruption}: {event['detail']}"
            writer.record_recovery(event)
        result = {
            "schema_version": 1,
            "kind": "result",
            "run_id": run_id,
            "status": "pass",
            "recovery": [transition.as_dict() for transition in transitions],
            "device": {"device_id": binding.device_id, "device_suffix": binding.device_id[-4:], "boot_id": session.device.get("device_boot_id", "unavailable"), "session_id": session.session_id},
            "interruption": interruption,
            "runtime_privilege": "root" if os.geteuid() == 0 else "ordinary-user",
        }
        manifest = {
            "schema_version": 1,
            "kind": "manifest",
            "run_id": run_id,
            "workflow": "recovery",
            "status": "pass",
            "protocol": {"version": PROTOCOL_VERSION, "max_line_bytes_including_lf": MAX_LINE_BYTES, "transport": "usb-cdc"},
            "environment": {**environment, "dependency_lock": dependency_lock()},
            "candidate": selected.snapshot(),
            "paired_identity": binding.device_id,
            "interruption": interruption,
            "in_scope": ["reset", "normal-flash-reset", "port-move", "endpoint-renumber", "utility-restart"],
            "excluded": ["host-reboot", "suspend-resume", "cross-component-product-resync"],
            "runtime_privilege": "root" if os.geteuid() == 0 else "ordinary-user",
        }
        path = writer.write(manifest, result)
        print(f"New session established for exact paired keypad: {session.session_id}")
        print(f"Recovery evidence preserved and hash-verified: {path}")
        return 0
    finally:
        link.close()

def run_recovery_tour(schema_path: Path, evidence_root: Path, binding_path: Path, resume: str | None = None) -> int:
    """Run the operator-owned D-12 tour one explicit response at a time."""
    environment = dependency_gate()
    load_schema(schema_path)
    import serial

    from .pairing import PairingStore, PairingError

    tour_root = Path(evidence_root) / "recovery-tours"
    tour_root.mkdir(parents=True, exist_ok=True)
    if resume is None:
        tour_id = "tour-" + _run_id()
        state = {"tour_id": tour_id, "current_index": 0, "restart_ready": False}
    else:
        tour_id = resume
        state_path = tour_root / f"{tour_id}.state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"recovery tour resume state is unavailable: {exc}") from exc
        if state.get("tour_id") != tour_id:
            raise ValueError("recovery tour resume identity mismatch")
    state_path = tour_root / f"{tour_id}.state.json"
    state_path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    binding = PairingStore(binding_path).load()
    if binding is None:
        raise PairingError("unpaired", "No paired keypad binding exists; run the physical pairing gate first.")

    def opener(candidate: Any) -> Any:
        return serial.Serial(candidate.device, 115200, timeout=0.5)

    while int(state["current_index"]) < len(RECOVERY_TOUR_STEPS):
        index = int(state["current_index"])
        step = RECOVERY_TOUR_STEPS[index]
        if step.key == "utility-restart" and not state.get("restart_ready"):
            state["restart_ready"] = True
            state_path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
            print(f"Recovery tour {tour_id} is paused at the utility-restart checkpoint.")
            print("Exit this process, then rerun exactly:")
            print(f"tools/phase1_bringup/.venv/bin/python -m phase1_bringup recover-tour --resume {tour_id} --schema {schema_path} --evidence-root {evidence_root}")
            return 75
        print(f"\nD-12 step {index + 1}/{len(RECOVERY_TOUR_STEPS)}: {step.title}")
        print("Action: " + step.action)
        print("Checkpoint: " + step.checkpoint)
        allowed = "[Y] confirmed  [N] failed  [R] repeat"
        if step.allow_unavailable:
            allowed += "  [U] unavailable"
        response = input(allowed + ": ").strip().upper()
        valid_responses = {"Y", "N", "R"} | ({"U"} if step.allow_unavailable else set())
        if response not in valid_responses:
            print("Type exactly Y, N, or R" + ("; U means unavailable for this step." if step.allow_unavailable else "."))
            continue
        if response == "R":
            print("Repeating this step; no result was replaced.")
            continue
        if response == "U" and not step.allow_unavailable:
            print("U is only allowed for the endpoint-renumber step.")
            continue

        run_id = f"{tour_id}-step-{index + 1:02d}-{step.key}"
        writer = EvidenceWriter(tour_root / tour_id, run_id)
        manifest = {
            "schema_version": 1,
            "kind": "manifest",
            "run_id": run_id,
            "workflow": "recovery-tour",
            "tour_id": tour_id,
            "step": step.key,
            "human_response": response,
            "environment": {**environment, "dependency_lock": dependency_lock()},
            "paired_identity": binding.device_id,
            "runtime_privilege": "root" if os.geteuid() == 0 else "ordinary-user",
            "excluded": ["host-reboot", "suspend-resume", "cross-component-product-resync"],
        }
        result: dict[str, Any] = {
            "schema_version": 1,
            "kind": "result",
            "run_id": run_id,
            "tour_id": tour_id,
            "step": step.key,
            "human_response": response,
            "physical_pass": False,
            "runtime_privilege": "root" if os.geteuid() == 0 else "ordinary-user",
        }
        if response == "U":
            result.update({"status": "unavailable", "recovery": [], "detail": "operator marked endpoint renumber unavailable; no physical PASS claimed"})
        elif response == "N":
            result.update({"status": "fail", "recovery": [], "detail": "operator reported the checkpoint failed; no physical PASS claimed"})
        else:
            try:
                selected, link, session, transitions = reconnect_exact(binding, None, opener, discarded_ids=[1])
                try:
                    events = []
                    for transition in transitions:
                        event = transition.as_dict()
                        event["detail"] = f"{step.key}: {event['detail']}"
                        writer.record_recovery(event)
                        events.append(event)
                    result.update({
                        "status": "pass",
                        "physical_pass": True,
                        "recovery": events,
                        "device": {"device_id": binding.device_id, "device_suffix": binding.device_id[-4:], "boot_id": session.device.get("device_boot_id", "unavailable"), "session_id": session.session_id},
                    })
                    manifest["candidate"] = selected.snapshot()
                finally:
                    link.close()
            except Exception as exc:
                result.update({"status": "fail", "recovery": [], "detail": f"machine recovery failed: {exc}"})
        path = writer.write(manifest, result)
        print(f"Immutable step evidence: {path}")
        if result["status"] != "pass" and response != "U":
            state_path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
            return 1
        state["current_index"] = index + 1
        state["restart_ready"] = False
        state_path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    state_path.unlink(missing_ok=True)
    print(f"Recovery tour complete: {tour_id}. All available steps have machine recovery and explicit operator confirmation.")
    return 0

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

def run_batch(schema_path: Path, evidence_root: Path, port: str | None = None, dwell_seconds: float = 1.0) -> int:
    """Run the seven physical gates with one explicit confirmation per gate."""
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
    run = BatchRun(None, writer, ui, run_id, dwell_seconds=dwell_seconds)
    try:
        with serial.Serial(selected_port, 115200, timeout=0.5) as connection:
            session = ProtocolSession(connection, "host-" + secrets.token_hex(6), "session-" + secrets.token_hex(6))
            run.session = session
            run.start()
            while not run.complete_physical_gates and not run.stopped:
                run.stimulate_gate()
                while run.pending and not run.stopped:
                    try:
                        answer = input(f"Batch response {run.gate.name.upper()} {run.run_suffix} (Y/N/R): ")
                    except EOFError as exc:
                        raise RuntimeError("batch confirmation input ended before this gate was confirmed") from exc
                    try:
                        result = run.respond(answer)
                    except ValueError as exc:
                        print(f"Batch response rejected: {str(exc)[:160]}", file=sys.stderr)
                        continue
                    if result in {"pass", "fail", "repeat"}:
                        break
            result = run.result()
            manifest = {
                "schema_version": 1,
                "kind": "manifest",
                "run_id": run_id,
                "status": result["status"],
                "workflow": "batch",
                "protocol": {"version": PROTOCOL_VERSION, "max_line_bytes_including_lf": MAX_LINE_BYTES, "transport": "usb-cdc"},
                "environment": {**environment, "dependency_lock": dependency_lock()},
                "device": {"port_discovery": "descriptor-only", "selected_port": "redacted", "identity": "unavailable"},
                "guided_order": list(GUIDED_ORDER),
                "batch_order": list(BATCH_GATE_ORDER),
            }
            path = writer.finalize(manifest, result)
            print(f"Batch evidence preserved and hash-verified: {path}")
            return 0 if result["status"] == "pass" else 1
    except Exception as exc:
        failure_result = run.result()
        failure_result["status"] = "fail"
        failure_result["error"] = {"type": type(exc).__name__, "message": str(exc)[:256]}
        failure_manifest = {
            "schema_version": 1,
            "kind": "manifest",
            "run_id": run_id,
            "status": "fail",
            "workflow": "batch",
            "protocol": {"version": PROTOCOL_VERSION, "max_line_bytes_including_lf": MAX_LINE_BYTES, "transport": "usb-cdc"},
            "environment": environment,
            "device": {"port_discovery": "descriptor-only", "identity": "unavailable"},
            "guided_order": list(GUIDED_ORDER),
            "batch_order": list(BATCH_GATE_ORDER),
        }
        try:
            writer.finalize(failure_manifest, failure_result)
        except EvidenceError:
            pass
        print(f"Batch failed; evidence was preserved: {str(exc)[:256]}", file=sys.stderr)
        return 1

def run_machine_only(schema_path: Path, evidence_root: Path, port: str | None = None, dwell_seconds: float = 1.0) -> int:
    """Capture device observations without reading stdin or authorizing physical PASS."""
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
    run = BatchRun(None, writer, ui, run_id, dwell_seconds=dwell_seconds, machine_only=True)
    try:
        with serial.Serial(selected_port, 115200, timeout=0.5) as connection:
            run.session = ProtocolSession(connection, "host-" + secrets.token_hex(6), "session-" + secrets.token_hex(6))
            run.start()
            while not run.complete_physical_gates:
                run.stimulate_gate()
                run.advance_machine_gate()
            result = run.machine_result()
            manifest = {
                "schema_version": 1,
                "kind": "manifest",
                "run_id": run_id,
                "status": result["status"],
                "workflow": "batch-machine-only",
                "physical_confirmation": False,
                "protocol": {"version": PROTOCOL_VERSION, "max_line_bytes_including_lf": MAX_LINE_BYTES, "transport": "usb-cdc"},
                "environment": {**environment, "dependency_lock": dependency_lock()},
                "device": {"port_discovery": "descriptor-only", "selected_port": "redacted", "identity": "unavailable"},
                "batch_order": list(BATCH_GATE_ORDER),
                "guided_order": list(GUIDED_ORDER),
            }
            path = writer.write(manifest, result)
            print(f"Machine-only batch preserved (no physical PASS): {path}")
            return 0
    except Exception as exc:
        failure_result = run.machine_result()
        failure_result["status"] = "machine-failed"
        failure_result["error"] = {"type": type(exc).__name__, "message": str(exc)[:256]}
        failure_manifest = {
            "schema_version": 1,
            "kind": "manifest",
            "run_id": run_id,
            "status": "machine-failed",
            "workflow": "batch-machine-only",
            "physical_confirmation": False,
            "protocol": {"version": PROTOCOL_VERSION, "max_line_bytes_including_lf": MAX_LINE_BYTES, "transport": "usb-cdc"},
            "environment": environment,
            "device": {"port_discovery": "descriptor-only", "identity": "unavailable"},
            "batch_order": list(BATCH_GATE_ORDER),
            "guided_order": list(GUIDED_ORDER),
        }
        try:
            writer.write(failure_manifest, failure_result)
        except EvidenceError:
            pass
        print(f"Machine-only batch failed; observations preserved: {str(exc)[:256]}", file=sys.stderr)
        return 1


def run_confirm_batch(machine_run_dir: Path, groups: str) -> int:
    """Convert one verified machine run into a separate human-confirmed artifact."""
    checked = verify_machine_run(machine_run_dir)
    manifest = checked["manifest"]
    result = checked["result"]
    run_id = str(result["run_id"])
    responses = parse_group_responses(groups, run_id)
    observations = result["machine_observations"]
    by_gate: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        by_gate.setdefault(str(observation["gate"]).upper(), []).append(observation)
    confirmed_id = f"confirmed-{run_id}-{secrets.token_hex(3)}"
    writer = EvidenceWriter(Path(machine_run_dir).resolve().parent, confirmed_id)
    rows: list[dict[str, Any]] = []
    confirmations: list[dict[str, Any]] = []
    for gate in BATCH_GATE_ORDER:
        gate_key = gate.upper()
        action = responses[gate_key]
        gate_observations = by_gate.get(gate_key, [])
        if not gate_observations:
            raise EvidenceError(f"machine run has no observations for {gate}")
        all_acknowledged = all(item["machine_status"] == "acknowledged" for item in gate_observations)
        if action == "Y" and not all_acknowledged:
            raise EvidenceError(f"group PASS for {gate} requires acknowledged machine evidence for every row")
        physical_status = {"Y": "pass", "N": "failed", "R": "repeated"}[action]
        confirmation = {
            "gate": gate,
            "response": action,
            "run_id": run_id,
            "run_suffix": run_id[-6:],
            "source_machine_run": run_id,
        }
        confirmations.append(confirmation)
        for index, observation in enumerate(gate_observations, start=1):
            observed_value = observation.get("observed_value", "unavailable")
            if observed_value is None:
                observed_value = "unavailable"
            rows.append(
                {
                    "row_id": f"{confirmed_id}:{len(rows) + 1}",
                    "run_id": confirmed_id,
                    "step_id": observation["step_id"],
                    "gate": gate,
                    "machine_status": observation["machine_status"],
                    "machine_reply_seq": observation["machine_reply_seq"],
                    "human_response": action,
                    "physical_status": physical_status,
                    "observed_value": observed_value,
                    "timestamp": time.time(),
                    "machine_observation": {
                        "source_row_id": observation["row_id"],
                        "source_run_id": run_id,
                        "observed_value": observed_value,
                    },
                    "group_confirmation": confirmation,
                }
            )
    writer.record_rows(rows)
    status = "pass" if all(responses[gate] == "Y" for gate in MACHINE_BATCH_GATES) else "fail" if any(responses[gate] == "N" for gate in MACHINE_BATCH_GATES) else "incomplete"
    confirmed_manifest = {
        "schema_version": 1,
        "kind": "manifest",
        "run_id": confirmed_id,
        "status": status,
        "workflow": "batch-confirmed",
        "source_machine_run": run_id,
        "source_machine_checksum": _source_checksum(machine_run_dir),
        "group_confirmations": confirmations,
        "guided_order": list(GUIDED_ORDER),
    }
    confirmed_result = {
        "schema_version": 1,
        "kind": "result",
        "run_id": confirmed_id,
        "status": status,
        "mode": "batch-confirmed",
        "source_machine_run": run_id,
        "physical_confirmation": True,
        "group_confirmations": confirmations,
        "physical_map": {"rows": rows, "guided_order": list(GUIDED_ORDER)},
        "batch_order": list(BATCH_GATE_ORDER),
    }
    path = writer.finalize(confirmed_manifest, confirmed_result)
    print(f"Confirmed batch preserved: {path} ({status})")
    return 0 if status == "pass" else 1


def _source_checksum(path: Path) -> str:
    """Return the immutable source checksum recorded by confirm-batch."""
    import hashlib
    sums = (Path(path) / "SHA256SUMS").read_bytes()
    return hashlib.sha256(sums).hexdigest()


def firmware_contract_check(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    tokens = ("DisplayMapping", "KeyMapping", "EncoderMapping", "LedMapping", "BrightnessObservation", "PhysicalMap", "ObservationState::Unavailable", "human_confirmed")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise RuntimeError(f"firmware contract is missing required contract tokens: {', '.join(missing)}")
    stimulus_source = path.parents[1] / "main.cpp"
    stimulus_text = stimulus_source.read_text(encoding="utf-8")
    required_stimulus = (
        'parseSingleIndex(stimulus, "LED-", 13, value)',
        'parseSingleIndex(stimulus, "KEY-", 4, value) && value >= 1',
        'expectedKey = static_cast<uint8_t>(value - 1)',
        'board.key(4).wasPressed()',
        'reportKeyTransition(4)',
    )
    missing_stimulus = [token for token in required_stimulus if token not in stimulus_text]
    if missing_stimulus:
        raise RuntimeError(f"firmware stimulus contract is missing physical key mapping tokens: {', '.join(missing_stimulus)}")


def renderer_contract_check(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    tokens = ("BringupState::Wait", "BringupState::Map", "BringupState::Press", "BringupState::TurnCw", "BringupState::TurnCcw", "BringupState::Click", "BringupState::Brightness", "BringupState::Pair", "BringupState::Pass", "BringupState::Fail", "BringupState::LinkLost", "kSafeInset = 4", "kPanelCount = 4", "display.fillScreen(TFT_BLACK)", "drawWait", "ENC CLICK", "static_cast<unsigned>(request.expected_key) + 1U")
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


def _sample_machine_run(root: Path, run_id: str = "machine-self-check", rejected_gate: str | None = None) -> Path:
    writer = EvidenceWriter(root, run_id)
    observations = []
    ordinal = 0
    for gate in BATCH_GATE_ORDER:
        gate_rows = next(item.rows for item in GATES if item.name == gate)
        for row in gate_rows:
            ordinal += 1
            observed_value: Any = "unavailable"
            if row.physical_kind in {"key", "encoder_click"}:
                raw_key = 4 if row.physical_kind == "encoder_click" else int(row.step_id.rsplit("-", 1)[1]) - 1
                observed_value = {
                    "event": {"kind": "key_transition", "step_id": row.step_id, "key": raw_key}
                }
            observations.append(
                {
                    "row_id": f"{run_id}:machine:{ordinal}",
                    "run_id": run_id,
                    "step_id": row.step_id,
                    "gate": gate,
                    "machine_status": "rejected" if gate == rejected_gate else "acknowledged",
                    "machine_reply_seq": ordinal,
                    "observed_value": observed_value,
                    "timestamp": time.time(),
                }
            )
    result = {
        "schema_version": 1,
        "kind": "result",
        "run_id": run_id,
        "status": "machine-complete",
        "mode": "machine-only",
        "physical_confirmation": False,
        "machine_observations": observations,
        "batch_order": list(BATCH_GATE_ORDER),
    }
    manifest = {
        "schema_version": 1,
        "kind": "manifest",
        "run_id": run_id,
        "status": "machine-complete",
        "workflow": "batch-machine-only",
        "physical_confirmation": False,
    }
    return writer.write(manifest, result)


def machine_only_no_stdin_check() -> None:
    source = inspect.getsource(run_machine_only)
    if "input(" in source or "sys.stdin" in source:
        raise AssertionError("machine-only capture must never read stdin")
    from .protocol import MachineFact

    class FakeSession:
        def __init__(self):
            self.sequence = 0

        def _fact(self) -> MachineFact:
            self.sequence += 1
            return MachineFact("acknowledged", time.time(), self.sequence)

        def hello(self) -> MachineFact:
            return self._fact()

        def stimulate(self, step_id: str, panel: int, stimulus: str) -> MachineFact:
            return self._fact()

        def wait_event(self, step_id: str) -> dict[str, Any]:
            raw_key = 4 if step_id == "ENCODER-CLICK" else int(step_id.rsplit("-", 1)[1]) - 1
            return {"payload": {"kind": "key_transition", "step_id": step_id, "key": raw_key}}

    with tempfile.TemporaryDirectory() as directory:
        emitted = io.StringIO()
        writer = EvidenceWriter(Path(directory), "machine-no-stdin")
        run = BatchRun(FakeSession(), writer, TerminalUI(output=emitted), "machine-no-stdin", dwell_seconds=0, machine_only=True)
        run.start()
        while not run.complete_physical_gates:
            run.stimulate_gate()
            run.advance_machine_gate()
        result = run.machine_result()
        if result["mode"] != "machine-only" or result["physical_confirmation"] is not False:
            raise AssertionError("machine-only run produced a physical confirmation marker")
        if "Type Y" in emitted.getvalue():
            raise AssertionError("machine-only UI emitted an interactive confirmation prompt")

def machine_artifact_check() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _sample_machine_run(Path(directory))
        checked = verify_machine_run(path)
        result = checked["result"]
        if "physical_map" in result or result.get("physical_confirmation") is not False:
            raise AssertionError("machine-only artifact contains physical confirmation")
        if not any(item["observed_value"] != "unavailable" for item in result["machine_observations"]):
            raise AssertionError("machine observations did not retain details")


def group_parser_check() -> None:
    run_id = "machine-self-check"
    valid = ",".join(f"{gate.upper()}=Y" for gate in BATCH_GATE_ORDER)
    parsed = parse_group_responses(valid, run_id)
    if len(parsed) != len(BATCH_GATE_ORDER):
        raise AssertionError("valid group set was not parsed")
    for invalid in ("", "IDENTIFY=ACK", "UNKNOWN=Y", valid.replace("REBOOT=Y", "")):
        try:
            parse_group_responses(invalid, run_id)
        except EvidenceError:
            continue
        raise AssertionError(f"invalid group set was accepted: {invalid!r}")
    suffix_mismatch = valid.replace("IDENTIFY=Y", "IDENTIFY=Y@WRONG")
    try:
        parse_group_responses(suffix_mismatch, run_id)
    except EvidenceError:
        pass
    else:
        raise AssertionError("mismatched run suffix was accepted")


def confirmed_directory_check() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = _sample_machine_run(root)
        groups = ",".join(f"{gate.upper()}=Y" for gate in BATCH_GATE_ORDER)
        if run_confirm_batch(source, groups) != 0:
            raise AssertionError("all acknowledged groups did not confirm")
        confirmed = sorted(root.glob("confirmed-*"))
        if len(confirmed) != 1:
            raise AssertionError("confirm-batch did not create a separate directory")
        checked = verify_physical_evidence(confirmed[0], require_physical_map=True)
        rows = checked and json.loads((confirmed[0] / "result.json").read_text(encoding="utf-8"))["physical_map"]["rows"]
        if not rows or not all(row.get("group_confirmation") for row in rows):
            raise AssertionError("confirmed rows lost group confirmation metadata")
        if not all(row.get("machine_observation") for row in rows):
            raise AssertionError("confirmed rows lost machine observation details")
        if len(rows) != 30:
            raise AssertionError("confirm-batch physical row count must be 30 (four keys plus encoder click)")
        key_rows = [row for row in rows if row["gate"] == "Keys"]
        if [row["observed_value"]["event"]["key"] for row in key_rows] != [0, 1, 2, 3]:
            raise AssertionError("confirm-batch changed KEY-1..KEY-4 raw index evidence")
        click_rows = [row for row in rows if row["step_id"] == "ENCODER-CLICK"]
        if len(click_rows) != 1 or click_rows[0]["observed_value"]["event"]["key"] != 4:
            raise AssertionError("confirm-batch lost ENC-CLICK raw index 4 evidence")


def confirmation_rejection_check() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = _sample_machine_run(root, rejected_gate="Keys")
        source_bytes = {name: (source / name).read_bytes() for name in ("manifest.json", "result.json", "SHA256SUMS")}
        all_yes = ",".join(f"{gate.upper()}=Y" for gate in BATCH_GATE_ORDER)
        try:
            run_confirm_batch(source, all_yes)
        except EvidenceError:
            pass
        else:
            raise AssertionError("ACK-only PASS was not rejected for a rejected machine gate")
        for action, expected in (("N", "fail"), ("R", "incomplete")):
            before = set(root.glob("confirmed-*"))
            groups = ",".join(f"{gate.upper()}={action if gate == 'Keys' else 'Y'}" for gate in BATCH_GATE_ORDER)
            if run_confirm_batch(source, groups) == 0:
                raise AssertionError(f"group {action} unexpectedly reported physical pass")
            created = set(root.glob("confirmed-*")) - before
            if len(created) != 1:
                raise AssertionError(f"group {action} did not create exactly one separate confirmed artifact")
            confirmed = created.pop()
            checked = json.loads((confirmed / "result.json").read_text(encoding="utf-8"))
            if checked["status"] != expected:
                raise AssertionError(f"group {action} status was not {expected}")
            rows = checked["physical_map"]["rows"]
            repeat_rows = [row for row in rows if row["gate"] == "Keys"]
            if action == "R" and (
                not repeat_rows
                or any(row["human_response"] != "R" or row["physical_status"] != "repeated" for row in repeat_rows)
                or any(row["human_response"] == "R" and row["physical_status"] == "pass" for row in rows)
            ):
                raise AssertionError("group R did not preserve incomplete/repeat semantics without physical PASS")
        if source_bytes != {name: (source / name).read_bytes() for name in source_bytes}:
            raise AssertionError("confirm-batch mutated the immutable machine artifact")

def command_self_check(args: argparse.Namespace) -> int:
    if args.environment:
        environment = dependency_gate()
        print(
            f"Environment: Python {environment['python']} ({environment['python_executable']}); "
            f"pyserial {environment['pyserial']}; jsonschema {environment['jsonschema']}"
        )
    if args.schema:
        load_schema(Path(args.schema))
        if args.schema_draft_2020:
            print("Schema: Draft 2020-12 meta-schema validation passed")
        protocol_bootstrap_check()
        print("Protocol bootstrap: device boot adoption and strict post-bootstrap identity pass")
        base = new_frame("probe", "boot", "session", 1, {"step_id": "PANEL-1", "panel": 1, "stimulus": "1 ^ CYAN"})
        if decode_frame(encode_frame(base)) != base or validate_frame(base) != base:
            raise RuntimeError("frame round trip mismatch")
    if args.protocol_golden:
        if not args.schema:
            raise ValueError("--protocol-golden requires --schema")
        count = protocol_golden_check(Path(args.protocol_golden), Path(args.schema))
        print(f"Protocol golden: verified {count} vectors with Draft 2020-12 and host codec/session")
    if args.discovery:
        discovery_check()
        print("Discovery: descriptor facts are candidate-only; zero/many/mismatch fail closed")
    if args.pairing:
        pairing_check()
        pairing_ui_check()
        print("Pairing: exact fresh challenge and physical confirmation required; old binding preserved on rejection")
    if args.serial_reconnect:
        serial_reconnect_check()
        recovery_ui_check()
        recovery_tour_check()
        print("Serial recovery: bounded I/O, stale close, exact identity, fresh session, discarded IDs, and D-12 tour pass")
    if args.udev_rule:
        udev_rule_check(Path(args.udev_rule))
        print("udev: measured VID/PID/serial/interface rule is narrow and ordinary-user scoped")
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
    if args.batch_order:
        batch_order_check()
        print("Batch order: " + " -> ".join(BATCH_GATE_ORDER))
    if args.batch_parser:
        batch_parser_check()
        print("Batch parser: explicit gate/run-bound Y/N/R accepted; mismatches rejected")
    if args.batch_key_events:
        batch_key_event_check()
        print("Batch key events: KEY-1..KEY-4 map to raw indices 0..3; ENC-CLICK validates raw index 4")
    if args.batch_no_ack_pass:
        batch_no_ack_check()
        print("Batch confirmation: ACK-only group PASS rejected")
    if args.machine_only_no_stdin:
        machine_only_no_stdin_check()
        print("Machine-only: no stdin path present")
    if args.machine_artifact:
        machine_artifact_check()
        print("Machine artifact: immutable observations with no physical PASS")
    if args.group_parser:
        group_parser_check()
        print("Group parser: exact seven gates, ACK-only/invalid/missing/mismatched rejected")
    if args.confirmed_directory:
        confirmed_directory_check()
        print("Confirmed artifact: separate hash-verified directory with linked details")
    if args.confirmation_rejection:
        confirmation_rejection_check()
        print("Confirmation semantics: Y requires all acknowledgements; N/R preserve non-pass history")
    if args.qualification_manifest:
        qualification_manifest_check(Path(args.qualification_manifest))
        print("Qualification manifest: frozen profile, protocol hashes, and interruption matrix pass")
    if args.qualification_cli:
        qualification_cli_check()
        print("Qualification CLI: registered and fails closed before hardware access")
    if args.qualification_early_rejection:
        qualification_early_rejection_check(Path(args.qualification_manifest))
        print("Qualification early rejection: matched key/encoder events, automated smoke pass, and immutable overlap-N failure")
    if args.qualification_no_false_pass:
        qualification_no_false_pass_check(Path(args.qualification_manifest))
        print("Qualification PASS gate: unavailable firmware evidence cannot pass")
    if args.selection_evidence_exact_path or args.selection_evidence_hash_negative or args.selection_asymmetry:
        selection_self_check(repo_root() / "artifacts" / "phase1" / "locks" / "usb-eligibility.json")
        print("Selection evidence: exact immutable path, hash rejection, and USB-first asymmetry pass")
    if args.firmware_composition_lock:
        verify_build_lock(args.firmware_composition_lock)
        print("Firmware composition: selected-usb contains exactly one adapter and no Wi-Fi artifact")
 
    return 0
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phase1_bringup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    self_check = subparsers.add_parser("self-check", help="run narrow protocol, UI, evidence, and batch checks")
    self_check.add_argument("--environment", action="store_true")
    self_check.add_argument("--schema", type=Path)
    self_check.add_argument("--protocol-golden", type=Path, help="run the shared host golden fixture")
    self_check.add_argument("--schema-draft-2020", action="store_true", help="report Draft 2020-12 meta-schema validation")
    self_check.add_argument("--firmware-contract", type=Path)
    self_check.add_argument("--device-render-contract", type=Path)
    self_check.add_argument("--discovery", action="store_true", help="check fail-closed measured USB candidate handling")
    self_check.add_argument("--pairing", action="store_true", help="check exact challenge pairing and immutable binding")
    self_check.add_argument("--serial-reconnect", action="store_true", help="check fresh exact-device serial recovery")
    self_check.add_argument("--udev-rule", type=Path, help="check measured narrow udev rule")
    self_check.add_argument("--evidence-roundtrip", type=Path)
    self_check.add_argument("--ui", action="store_true")
    self_check.add_argument("--guided-order", action="store_true")
    self_check.add_argument("--evidence-schema", action="store_true")
    self_check.add_argument("--physical-confirmation", action="store_true")
    self_check.add_argument("--batch-order", action="store_true", help="check fixed physical batch gate order and row counts")
    self_check.add_argument("--batch-parser", action="store_true", help="check explicit gate/run-bound group responses")
    self_check.add_argument("--batch-key-events", action="store_true", help="check KEY-1..KEY-4 raw indices 0..3 and ENC-CLICK raw index 4")
    self_check.add_argument("--batch-no-ack-pass", action="store_true", help="check ACK-only group PASS is rejected")
    self_check.add_argument("--machine-only-no-stdin", action="store_true", help="check machine-only capture has no stdin path")
    self_check.add_argument("--machine-artifact", action="store_true", help="check machine-only artifact semantics and verification")
    self_check.add_argument("--qualification-early-rejection", action="store_true", help="check preflight activity and immutable overlap-N failure")
    self_check.add_argument("--qualification-no-false-pass", action="store_true", help="reject PASS without measured firmware metrics/counters")
    self_check.add_argument("--group-parser", action="store_true", help="check exact group parsing and mismatch rejection")
    self_check.add_argument("--confirmed-directory", action="store_true", help="check confirmed artifact creation and linked details")
    self_check.add_argument("--confirmation-rejection", action="store_true", help="check Y/N/R confirmation semantics")
    self_check.add_argument("--qualification-manifest", type=Path, help="verify the frozen USB qualification profile")
    self_check.add_argument("--qualification-cli", action="store_true", help="check qualify registration without opening hardware")
    self_check.add_argument("--selection-evidence-exact-path", action="store_true")
    self_check.add_argument("--selection-evidence-hash-negative", action="store_true")
    self_check.add_argument("--selection-asymmetry", action="store_true")
    self_check.add_argument("--firmware-composition-lock", type=Path)
    self_check.add_argument("--exactly-one-adapter", action="store_true")
    self_check.add_argument("--unselected-source-object-symbol-absent", action="store_true")
    freeze = subparsers.add_parser("freeze-manifest", help="create or reopen the deterministic USB qualification manifest")
    freeze.add_argument("--schema", type=Path, default=repo_root() / "protocol" / "schema" / "v1.json")
    freeze.add_argument("--fixture", type=Path, default=repo_root() / "protocol" / "fixtures" / "v1-golden.json")
    freeze.add_argument("--output", type=Path, default=repo_root() / "artifacts" / "phase1" / "qualification-manifest.json")
    qualification = subparsers.add_parser("verify-qualification", help="verify qualification manifest/result hash lineage")
    qualification.add_argument("manifest", type=Path)
    qualification.add_argument("result", type=Path)
    qualification.add_argument("--traffic", type=Path)
    qualification.add_argument("--require-immutable-traffic", action="store_true")
    resolve = subparsers.add_parser("resolve-pointer", help="resolve one immutable qualification result pointer into a lock")
    resolve.add_argument("--pointer", type=Path, required=True)
    resolve.add_argument("--manifest", type=Path, required=True)
    resolve.add_argument("--purpose", required=True)
    resolve.add_argument("--output", type=Path, required=True)
    select = subparsers.add_parser("select", help="select one transport from immutable qualification locks")
    select.add_argument("--manifest", type=Path, required=True)
    select.add_argument("--candidate-lock", type=Path, required=True)
    select.add_argument("--usb-lock", type=Path, required=True)
    select.add_argument("--wifi-lock-if-present", type=Path)
    select.add_argument("--output", type=Path, required=True)
    build = subparsers.add_parser("build-selected", help="build and hash exactly the selected adapter")
    build.add_argument("--selection-lock", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    archive = subparsers.add_parser("archive", help="archive Phase 1 immutable selection and build evidence")
    archive.add_argument("--selection-lock", type=Path, required=True)
    archive.add_argument("--build-lock", type=Path, required=True)
    archive.add_argument("--qualification-lock", type=Path, required=True)
    archive.add_argument("--output", type=Path, required=True)
    qualify = subparsers.add_parser("qualify", help="run the operator-owned frozen USB qualification")
    qualify.add_argument("--transport", choices=("usb",), required=True)
    qualify.add_argument("--manifest", type=Path, required=True)
    qualify.add_argument("--evidence-root", type=Path, default=repo_root() / "artifacts" / "phase1")
    qualify.add_argument("--binding", type=Path, default=Path.home() / ".config" / "herdr" / "keypad-binding.json")
    qualify.add_argument("--smoke-seconds", type=int, help="run a short non-acceptance smoke test instead of the frozen 30-minute soak")
    start = subparsers.add_parser("start", help="run guided mode, or use --batch for seven physical gate confirmations")
    start.add_argument("--batch", action="store_true", help="stimulate Identify through Reboot; Keys are KEY-1..KEY-4 and encoder click is ENC-CLICK")
    start.add_argument("--machine-only", action="store_true", help="with --batch, capture machine observations without stdin or physical PASS")
    start.add_argument("--dwell", type=float, default=1.0, help="bounded visible dwell seconds for non-key batch rows (max 5)")
    start.add_argument("--schema", type=Path, default=repo_root() / "protocol" / "schema" / "v1.json")
    start.add_argument("--evidence-root", type=Path, default=repo_root() / "artifacts" / "phase1")
    start.add_argument("--port")
    verify = subparsers.add_parser("verify-evidence")
    verify.add_argument("path", type=Path)
    verify.add_argument(
        "--require",
        action="append",
        choices=(
            "physical-map",
            "recovery",
            "strict-traffic",
            "immutable-linkage",
            "complete-interruption-matrix",
            "immutable-selection",
            "archived-source",
            "exact-manifest-hash",
            "no-secret-output",
        ),
    )
    confirm = subparsers.add_parser("confirm-batch", help="confirm one immutable machine-only batch artifact")
    confirm.add_argument("machine_run_dir", type=Path, help="concrete machine-only run directory")
    confirm.add_argument("--groups", required=True, help="IDENTIFY=Y,DISPLAYS=Y,KEYS=Y,ENCODER=Y,LEDS=Y,BRIGHTNESS=Y,REBOOT=Y")
    pair = subparsers.add_parser("pair", help="pair exactly one compatible keypad with a fresh physical challenge")
    pair.add_argument("--schema", type=Path, default=repo_root() / "protocol" / "schema" / "v1.json")
    pair.add_argument("--evidence-root", type=Path, default=repo_root() / "artifacts" / "phase1")
    pair.add_argument("--binding", type=Path, default=Path.home() / ".config" / "herdr" / "keypad-binding.json")
    recover = subparsers.add_parser("recover", help="rediscover and handshake the exact paired keypad")
    recover.add_argument("--schema", type=Path, default=repo_root() / "protocol" / "schema" / "v1.json")
    recover.add_argument("--evidence-root", type=Path, default=repo_root() / "artifacts" / "phase1")
    recover.add_argument("--binding", type=Path, default=Path.home() / ".config" / "herdr" / "keypad-binding.json")
    recover.add_argument("--interruption", choices=("reset", "normal-flash-reset", "port-move", "endpoint-renumber", "utility-restart"), required=True)
    tour = subparsers.add_parser("recover-tour", help="operator-run D-12 recovery tour with immutable step evidence")
    tour.add_argument("--schema", type=Path, default=repo_root() / "protocol" / "schema" / "v1.json")
    tour.add_argument("--evidence-root", type=Path, default=repo_root() / "artifacts" / "phase1")
    tour.add_argument("--binding", type=Path, default=Path.home() / ".config" / "herdr" / "keypad-binding.json")
    tour.add_argument("--resume", help="resume a tour ID printed at the utility-restart checkpoint")
    args = parser.parse_args(argv)
    try:
        if args.command == "recover-tour":
            return run_recovery_tour(args.schema, args.evidence_root, args.binding, args.resume)
        if args.command == "self-check":
            return command_self_check(args)
        if args.command == "freeze-manifest":
            from .qualification import freeze_manifest
            manifest = freeze_manifest(args.output, args.schema, args.fixture)
            print(f"Qualification manifest: {args.output} ({manifest['manifest_sha256']})")
            return 0
        if args.command == "verify-qualification":
            from .evidence import verify_qualification_linkage
            checked = verify_qualification_linkage(
                args.manifest,
                args.result,
                args.traffic,
                require_immutable_traffic=args.require_immutable_traffic,
            )
            print(f"Qualification evidence: manifest {checked['manifest']['manifest_sha256']} linked")
            return 0
        if args.command == "qualify":
            from .qualification import run_qualification
            return run_qualification(args.manifest, args.transport, args.evidence_root, args.binding, args.smoke_seconds)
        if args.command == "resolve-pointer":
            lock = resolve_qualification_pointer(args.pointer, args.manifest, args.purpose, args.output)
            print(f"Qualification lock: {args.output} ({lock['result_sha256']})")
            return 0
        if args.command == "select":
            selection = select_transport(
                args.manifest,
                args.candidate_lock,
                args.usb_lock,
                args.wifi_lock_if_present,
                args.output,
            )
            print(selection["rationale"])
            return 0
        if args.command == "build-selected":
            lock = build_selected(args.selection_lock, args.output)
            print(f"Selected build: {lock['environment']} ({lock['binary_sha256']})")
            return 0
        if args.command == "archive":
            lock = archive_phase1(
                args.selection_lock,
                args.build_lock,
                args.qualification_lock,
                args.output,
            )
            print(f"Phase 1 archive: {args.output} ({lock['binary_sha256']})")
            return 0
        if args.command == "recover":
            return run_recover(args.schema, args.evidence_root, args.binding, args.interruption)
        if args.command == "pair":
            return run_pair(args.schema, args.evidence_root, args.binding)
        if args.command == "verify-evidence":
            requirements = set(args.require or ())
            kind = json.loads(args.path.read_text(encoding="utf-8")).get("kind")
            if kind == "selection-lock":
                lock = verify_selection_lock(args.path)
                print(f"Evidence verified: selection lock {args.path} ({lock['result_sha256']})")
            elif kind == "final-build-lock":
                lock = verify_build_lock(args.path)
                print(f"Evidence verified: final build lock {args.path} ({lock['binary_sha256']})")
            elif kind == "phase1-archive-lock":
                lock = verify_archive_lock(args.path)
                print(f"Evidence verified: Phase 1 archive {args.path} ({lock['binary_sha256']})")
            elif requirements & {"strict-traffic", "immutable-linkage", "complete-interruption-matrix"}:
                lock = verify_qualification_lock(args.path, requirements)
                print(f"Evidence verified: qualification lock {args.path} ({lock['result_sha256']})")
            else:
                path = verify_physical_evidence(args.path, require_physical_map="physical-map" in requirements, require_recovery="recovery" in requirements)
                print(f"Evidence verified: {path}")
            return 0
        if args.command == "confirm-batch":
            return run_confirm_batch(args.machine_run_dir, args.groups)
        if args.command == "start":
            if args.machine_only and not args.batch:
                raise ValueError("--machine-only requires --batch")
            if args.batch and args.machine_only:
                return run_machine_only(args.schema, args.evidence_root, args.port, args.dwell)
            return run_batch(args.schema, args.evidence_root, args.port, args.dwell) if args.batch else run_start(args.schema, args.evidence_root, args.port)
        raise ValueError(f"unknown command: {args.command}")
    except (EvidenceError, RuntimeError, ValueError, OSError, AssertionError) as exc:
        print(f"phase1_bringup: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
