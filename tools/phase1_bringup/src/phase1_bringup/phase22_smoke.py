"""Bounded Phase 02.2 device smoke driver.

The driver deliberately separates machine observations from operator sightings.
It can emit a complete pending evidence skeleton without opening hardware, or run
against an explicitly supplied USB serial device and collect protocol/metrics
facts while prompting for the five physical observations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

THEMES = ("SIGNAL EDGE", "LEDGER", "BEACON", "INSTRUMENT")
GRAMMARS = ("RAIL ECHO", "EXCEPTION", "FIELD EXT", "METER+LAMPS")
STATES = ("blocked", "finished", "working", "idle", "settled", "unknown", "empty")
FENCES = ("stale", "offline", "unavailable")


def fnv1a64(payload: bytes) -> str:
    value = 0xCBF29CE484222325
    for byte in payload:
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016x}"


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def encode_frame(frame_type: str, boot_id: str, session_id: str, sequence: int,
                 payload: dict[str, Any], *, version: int = 2,
                 reply_to: int | None = None) -> bytes:
    payload_bytes = canonical_payload(payload)
    frame: dict[str, Any] = {
        "boot_id": boot_id,
        "digest": fnv1a64(payload_bytes),
        "payload": payload,
        "reply_to": reply_to,
        "seq": sequence,
        "session_id": session_id,
        "type": frame_type,
        "v": version,
    }
    return (json.dumps(frame, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def snapshot_payload(revision: int, *, source_status: str = "current",
                     states: tuple[str, str, str] = ("blocked", "working", "idle")) -> dict[str, Any]:
    agents: list[dict[str, Any]] = []
    for slot, state in enumerate(states):
        occupied = state != "empty"
        agents.append({
            "slot": slot,
            "entry_id": f"phase22-entry-{slot}" if occupied else "",
            "title": f"Phase22 Agent {slot + 1}" if occupied else "NO AGENT",
            "discriminator": f"repo-{slot + 1}" if occupied else "NO WORKSPACE",
            "state": state,
            "pane_id": f"phase22-pane-{slot}" if occupied else "",
            "terminal_id": f"phase22-terminal-{slot}" if occupied else "",
            "agent_session": None,
            "source_revision": revision if occupied else 0,
        })
    return {
        "host_epoch": "phase22-smoke-epoch",
        "snapshot_revision": revision,
        "source_status": source_status,
        "agents": agents,
    }


@dataclass
class HumanSighting:
    id: str
    expected: str
    result: str = "pending"
    notes: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "expected": self.expected, "result": self.result, "notes": self.notes}


@dataclass
class SmokeEvidence:
    firmware_commit: str = "unavailable"
    binary_sha256: str = "unavailable"
    machine_facts: dict[str, Any] = field(default_factory=dict)
    combinations: list[dict[str, Any]] = field(default_factory=list)
    sightings: list[HumanSighting] = field(default_factory=list)
    focus_feedback: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def skeleton(cls) -> "SmokeEvidence":
        evidence = cls()
        evidence.combinations = [
            {"theme": theme, "grammar": grammar, "result": "pending", "notes": ""}
            for theme in THEMES for grammar in GRAMMARS
        ]
        evidence.sightings = [
            HumanSighting("legibility", "All four themes keep titles, states, and 8 px metadata legible."),
            HumanSighting("instrument-arcs", "Instrument ring strokes and gaps are clean on the physical panels."),
            HumanSighting("brightness-ladder", "LED ladder is perceptible and comfortable under USB power."),
            HumanSighting("beacon-banding", "Beacon stepped field has acceptable RGB565 banding."),
            HumanSighting("accent-attribution", "Inter-key and above-key accents are physically attributable."),
            HumanSighting("no-black-flash", "Theme changes, menu overlay, refresh, and animation show no black flash or mixed actionable generation."),
            HumanSighting("blocked-phase", "BLOCKED display motion and LED pulse remain visibly in phase."),
            HumanSighting("fence", "STALE/OFFLINE/UNAVAILABLE visibly fence the old content."),
            HumanSighting("persistence", "A confirmed non-default pair survives reboot."),
            HumanSighting("fallback", "Invalid stored values fall back to Signal Edge + Rail Echo without write-back."),
        ]
        return evidence

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "phase22-device-evidence-v1",
            "status": "pass" if all(item.result == "Y" for item in self.sightings) and all(item["result"] == "Y" for item in self.combinations) else "pending",
            "lineage": {"firmware_commit": self.firmware_commit, "binary_sha256": self.binary_sha256},
            "machine_facts": self.machine_facts,
            "combinations": self.combinations,
            "sightings": [item.as_dict() for item in self.sightings],
            "focus_feedback": self.focus_feedback,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n"
        path.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")


class DeviceSession:
    def __init__(self, connection: Any, *, timeout: float = 2.0) -> None:
        self.connection = connection
        self.timeout = timeout
        self.boot_id = "host-boot"
        self.session_id = "host-session-" + secrets.token_hex(6)
        self.sequence = 0

    def _read_frame(self, deadline: float) -> dict[str, Any]:
        while time.monotonic() < deadline:
            line = self.connection.readline()
            if not line:
                continue
            try:
                frame = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(frame, dict):
                return frame
        raise TimeoutError("timed out waiting for keypad frame")

    def send(self, frame_type: str, payload: dict[str, Any], *, version: int = 2) -> int:
        self.sequence += 1
        self.connection.write(encode_frame(frame_type, self.boot_id, self.session_id, self.sequence, payload, version=version))
        return self.sequence

    def wait_for_type(self, frame_type: str, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            frame = self._read_frame(deadline)
            if frame.get("type") == frame_type:
                return frame

    def request(self, frame_type: str, payload: dict[str, Any], *, version: int = 2) -> dict[str, Any]:
        sequence = self.send(frame_type, payload, version=version)
        deadline = time.monotonic() + self.timeout
        while True:
            frame = self._read_frame(deadline)
            if frame.get("reply_to") == sequence:
                if frame.get("type") == "error":
                    raise RuntimeError(f"device rejected {frame_type}: {frame.get('payload')}")
                return frame

    def hello(self) -> dict[str, Any]:
        response = self.request("hello", {"device_id": "phase22-smoke", "firmware": "phase22-smoke", "protocol": 1}, version=1)
        self.boot_id = str(response.get("boot_id", ""))
        if not self.boot_id:
            raise RuntimeError("hello_ack did not provide device boot identity")
        return response


def prompt(label: str, expected: str) -> HumanSighting:
    print(f"\n{label}\nExpected: {expected}")
    result = input("Physical result [Y/N]: ").strip().upper()
    while result not in {"Y", "N"}:
        result = input("Enter Y or N: ").strip().upper()
    notes = input("Notes (optional): ").strip()
    return HumanSighting(label, expected, result, notes)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_device(port: str, output: Path, firmware: Path | None = None) -> int:
    evidence = SmokeEvidence.skeleton()
    if firmware is not None:
        evidence.binary_sha256 = sha256_file(firmware)
    try:
        return _run_device(port, output, evidence)
    except (EOFError, TimeoutError) as exc:
        evidence.machine_facts["checkpoint"] = {
            "status": "incomplete",
            "reason": str(exc),
            "operator_action": "rerun after completing the requested physical interaction",
        }
        evidence.write(output)
        print(f"Smoke checkpoint incomplete; evidence skeleton saved to {output}: {exc}", file=sys.stderr)
        return 2


def _run_device(port: str, output: Path, evidence: SmokeEvidence) -> int:
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pyserial is required for --port device runs") from exc
    with serial.Serial(port, 115200, timeout=0.25) as connection:
        session = DeviceSession(connection)
        hello = session.hello()
        evidence.machine_facts["hello_ack"] = hello.get("payload", {})
        revision = 1
        for state in STATES:
            response = session.request("agent_snapshot", snapshot_payload(revision, states=(state, "empty", "empty")))
            evidence.machine_facts[f"snapshot_{state}"] = response.get("payload", {})
            revision += 1
        for status in FENCES:
            response = session.request("agent_snapshot", snapshot_payload(revision, source_status=status))
            evidence.machine_facts[f"fence_{status}"] = response.get("payload", {})
            revision += 1
        current = session.request("agent_snapshot", snapshot_payload(revision))
        evidence.machine_facts["current_snapshot"] = current.get("payload", {})

        print("\nFocus feedback: press the occupied KEY-1 when prompted.")
        for scenario, outcome, focused in (("success", "accepted", True), ("failure", "rejected", False), ("uncertain", None, False)):
            input(f"Press ENTER, then press KEY-1 for the {scenario} scenario...")
            intent = session.wait_for_type("focus_intent", 10.0)
            payload = dict(intent.get("payload", {}))
            if outcome is not None:
                payload["outcome"] = outcome
                payload["focused"] = focused
                session.send("focus_result", payload)
            else:
                time.sleep(3.2)
            evidence.focus_feedback.append({
                "scenario": scenario,
                "intent_received": bool(payload),
                "result_sent": outcome is not None,
                "expected_feedback": "FOCUSED" if scenario == "success" else "REJECTED" if scenario == "failure" else "UNCERTAIN",
            })

        evidence.machine_facts["metrics"] = session.request("metrics", {"request": "proof"}, version=1).get("payload", {})
        for combination in evidence.combinations:
            sighting = prompt(
                f"Combination {combination['theme']} + {combination['grammar']}",
                "Select this pair through the encoder menu; agent keys remain direct and the panel-4 menu is complete.",
            )
            combination["result"] = sighting.result
            combination["notes"] = sighting.notes
            combination["metrics"] = session.request("metrics", {"request": "proof"}, version=1).get("payload", {})
        evidence.sightings = [prompt(item.id, item.expected) for item in evidence.sightings]
    evidence.write(output)
    return 0 if evidence.as_dict()["status"] == "pass" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="explicit /dev/serial/by-id path; required for hardware run")
    parser.add_argument("--firmware", type=Path, help="flashed firmware.bin for SHA-256 lineage")
    parser.add_argument("--output", type=Path, required=True, help="JSON evidence output path")
    parser.add_argument("--skeleton", action="store_true", help="write a pending evidence skeleton without opening hardware")
    args = parser.parse_args(argv)
    if args.skeleton:
        SmokeEvidence.skeleton().write(args.output)
        return 0
    if not args.port:
        parser.error("--port is required unless --skeleton is used")
    return run_device(args.port, args.output, args.firmware)


if __name__ == "__main__":
    raise SystemExit(main())
