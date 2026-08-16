"""Atomic, immutable evidence persistence for the Phase 1 tracer."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class EvidenceError(RuntimeError):
    """Raised when durable evidence cannot be verified."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def _validate_json_object(path: Path, expected_kind: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{expected_kind} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceError(f"{expected_kind} must be a JSON object")
    if data.get("schema_version") != 1:
        raise EvidenceError(f"{expected_kind} has unsupported schema_version")
    if data.get("kind") != expected_kind:
        raise EvidenceError(f"{expected_kind} kind mismatch")
    return data


_ROW_FIELDS = {"row_id", "run_id", "step_id", "gate", "machine_status", "machine_reply_seq", "human_response", "physical_status", "observed_value", "timestamp"}
_MACHINE_STATUSES = {"acknowledged", "observed", "rejected", "failed", "surprising", "unavailable"}
_HUMAN_RESPONSES = {"Y", "N", "R"}
_PHYSICAL_STATUSES = {"pass", "failed", "repeated", "unavailable", "surprising"}
MACHINE_BATCH_GATES = ("IDENTIFY", "DISPLAYS", "KEYS", "ENCODER", "LEDS", "BRIGHTNESS", "REBOOT")
MACHINE_BATCH_GATE_NAMES = {gate.title() if gate != "LEDS" else "LEDs" for gate in MACHINE_BATCH_GATES}


def _validate_machine_observation(observation: Any, expected_run_id: str) -> dict[str, Any]:
    if not isinstance(observation, dict):
        raise EvidenceError("machine observation must be an object")
    required = {"row_id", "run_id", "step_id", "gate", "machine_status", "machine_reply_seq", "observed_value", "timestamp"}
    if not required.issubset(observation):
        raise EvidenceError("machine observation is missing required fields")
    if observation["run_id"] != expected_run_id or not isinstance(observation["row_id"], str) or not observation["row_id"]:
        raise EvidenceError("machine observation identity is invalid")
    if observation["gate"] not in MACHINE_BATCH_GATE_NAMES:
        raise EvidenceError("machine observation gate is invalid")
    if observation["machine_status"] not in _MACHINE_STATUSES:
        raise EvidenceError("machine observation status is invalid")
    if observation["observed_value"] is None:
        raise EvidenceError("machine observation observed_value must use literal unavailable")
    if not isinstance(observation["timestamp"], (int, float)):
        raise EvidenceError("machine observation timestamp is invalid")
    if "human_response" in observation or "physical_status" in observation:
        raise EvidenceError("machine observation must not contain physical confirmation fields")
    return observation

def _validate_physical_row(row: Any, expected_run_id: str | None = None) -> dict[str, Any]:
    if not isinstance(row, dict) or not _ROW_FIELDS.issubset(row):
        raise EvidenceError("physical row is missing required evidence fields")
    if not isinstance(row["row_id"], str) or not row["row_id"]:
        raise EvidenceError("physical row row_id must be non-empty")
    if expected_run_id is not None and row.get("run_id") != expected_run_id:
        raise EvidenceError("physical row run_id mismatch")
    if not isinstance(row["step_id"], str) or not row["step_id"] or not isinstance(row["gate"], str) or not row["gate"]:
        raise EvidenceError("physical row step identity is invalid")
    if row["machine_status"] not in _MACHINE_STATUSES:
        raise EvidenceError("physical row machine_status is invalid")
    if row["human_response"] not in _HUMAN_RESPONSES:
        raise EvidenceError("physical row human_response is invalid")
    if row["physical_status"] not in _PHYSICAL_STATUSES:
        raise EvidenceError("physical row physical_status is invalid")
    if row["observed_value"] is None:
        raise EvidenceError("physical row observed_value must use literal unavailable")
    if not isinstance(row["timestamp"], (int, float)):
        raise EvidenceError("physical row timestamp is invalid")
    if row["human_response"] == "Y" and row["physical_status"] == "pass" and row["machine_status"] != "acknowledged":
        raise EvidenceError("physical PASS requires a current acknowledged machine fact")
    return row


def _validate_physical_map(result: dict[str, Any], require_rows: bool = True) -> None:
    physical_map = result.get("physical_map")
    if not isinstance(physical_map, dict):
        raise EvidenceError("result is missing physical_map")
    rows = physical_map.get("rows")
    if not isinstance(rows, list) or (require_rows and not rows):
        raise EvidenceError("physical_map rows must be a non-empty list")
    seen: set[str] = set()
    for row in rows:
        checked = _validate_physical_row(row, result.get("run_id"))
        if checked["row_id"] in seen:
            raise EvidenceError("physical row ids must be unique")
        seen.add(checked["row_id"])
    guided_order = physical_map.get("guided_order")
    if guided_order is not None and (not isinstance(guided_order, list) or guided_order != ["Identify", "Displays", "Keys", "Encoder", "LEDs", "Brightness", "Reboot", "Pair", "Recover", "Traffic", "Selection"]):
        raise EvidenceError("physical_map guided order is not the fixed eleven-gate sequence")


class EvidenceWriter:
    """Write one immutable manifest/result pair and verify it after reopening.

    A target directory is never overwritten. Rows are accumulated in memory until
    ``finalize``; each row is append-only and a typed replacement links old/new
    records rather than modifying an existing observation.
    """

    def __init__(self, root: Path, run_id: str):
        if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
            raise ValueError("run_id must be a single non-empty path component")
        self.root = Path(root)
        self.run_id = run_id
        self.directory = self.root / run_id
        self._rows: list[dict[str, Any]] = []
        self._row_ids: set[str] = set()
        self._finalized = False

    def record_row(self, row: dict[str, Any]) -> None:
        self.record_rows([row])

    def record_rows(self, rows: list[dict[str, Any]]) -> None:
        """Append a complete group after validating every row."""
        if self._finalized:
            raise EvidenceError("immutable evidence is already finalized")
        candidates = [copy.deepcopy(row) for row in rows]
        candidate_ids: set[str] = set()
        for candidate in candidates:
            _validate_physical_row(candidate, self.run_id)
            if candidate["row_id"] in self._row_ids or candidate["row_id"] in candidate_ids:
                raise EvidenceError("physical row id already exists")
            candidate_ids.add(candidate["row_id"])
        self._rows.extend(candidates)
        self._row_ids.update(candidate_ids)

    def replace_row(self, old_row_id: str, replacement: dict[str, Any], typed_confirmation: str) -> None:
        if typed_confirmation != "REPLACE":
            raise EvidenceError("typed REPLACE is required to add a replacement observation")
        if not any(row["row_id"] == old_row_id for row in self._rows):
            raise EvidenceError("replacement target row does not exist")
        candidate = copy.deepcopy(replacement)
        _validate_physical_row(candidate, self.run_id)
        if candidate["row_id"] in self._row_ids:
            raise EvidenceError("replacement row id already exists")
        candidate["replaces"] = old_row_id
        candidate["replacement_token"] = "REPLACE"
        self._rows.append(candidate)
        self._row_ids.add(candidate["row_id"])
    def finalize(self, manifest: dict[str, Any], result: dict[str, Any]) -> Path:
        if self._finalized:
            raise EvidenceError("evidence directory already finalized")
        final_result = copy.deepcopy(result)
        physical_map = final_result.setdefault("physical_map", {})
        if not isinstance(physical_map, dict):
            raise EvidenceError("physical_map must be an object")
        physical_map.setdefault("rows", copy.deepcopy(self._rows))
        _validate_physical_map(final_result, require_rows=final_result.get("status") not in {"fail", "incomplete"})
        path = self.write(manifest, final_result)
        self._finalized = True
        return path

    def write(self, manifest: dict[str, Any], result: dict[str, Any]) -> Path:
        if self.directory.exists():
            raise EvidenceError(f"evidence directory already exists: {self.directory}")
        attempt: Path | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=False)
            _atomic_bytes(self.directory / "manifest.json", _canonical_bytes(manifest))
            _atomic_bytes(self.directory / "result.json", _canonical_bytes(result))
            manifest_hash = _sha256(self.directory / "manifest.json")
            result_hash = _sha256(self.directory / "result.json")
            checksums = f"{manifest_hash}  manifest.json\n{result_hash}  result.json\n".encode("ascii")
            _atomic_bytes(self.directory / "SHA256SUMS", checksums)
            self.verify()
            return self.directory
        except Exception as exc:
            if self.directory.exists():
                attempt = self.root / f"failed-attempt-{self.run_id}-{time.time_ns()}"
                os.replace(self.directory, attempt)
                _fsync_directory(self.root)
            raise EvidenceError(f"evidence write preserved as {attempt}: {exc}") from exc

    def verify(self) -> dict[str, dict[str, Any]]:
        manifest_path = self.directory / "manifest.json"
        result_path = self.directory / "result.json"
        sums_path = self.directory / "SHA256SUMS"
        if not all(path.is_file() for path in (manifest_path, result_path, sums_path)):
            raise EvidenceError("manifest.json, result.json, and SHA256SUMS are required")
        manifest = _validate_json_object(manifest_path, "manifest")
        result = _validate_json_object(result_path, "result")
        if manifest.get("run_id") != self.run_id or result.get("run_id") != self.run_id:
            raise EvidenceError("evidence run_id mismatch")
        if "physical_map" in result:
            _validate_physical_map(result, require_rows=result.get("status") not in {"fail", "incomplete"})
        expected: dict[str, str] = {}
        for line in sums_path.read_text(encoding="ascii").splitlines():
            parts = line.split()
            if len(parts) != 2 or parts[1] not in {"manifest.json", "result.json"}:
                raise EvidenceError("invalid SHA256SUMS entry")
            expected[parts[1]] = parts[0]
        if set(expected) != {"manifest.json", "result.json"}:
            raise EvidenceError("SHA256SUMS must contain exactly manifest.json and result.json")
        for name in expected:
            actual = _sha256(self.directory / name)
            if actual != expected[name]:
                raise EvidenceError(f"hash mismatch for {name}")
        return {"manifest": manifest, "result": result}


def self_check_roundtrip(root: Path) -> Path:
    """Exercise the production writer and reopening verifier with real files."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    run_id = f"self-check-{time.time_ns()}"
    writer = EvidenceWriter(root, run_id)
    manifest = {"schema_version": 1, "kind": "manifest", "run_id": run_id, "status": "self-check", "protocol": {"version": 1, "max_line_bytes_including_lf": 4096}, "environment": {"python": "verified", "pyserial": "3.5"}}
    result = {"schema_version": 1, "kind": "result", "run_id": run_id, "status": "pass", "physical_observation": "unavailable", "transport": {"type": "self-check", "acknowledged": True}}
    path = writer.write(manifest, result)
    EvidenceWriter(root, run_id).verify()
    return path


def physical_schema_check() -> None:
    """Check schema and replacement invariants without creating physical evidence."""
    with tempfile.TemporaryDirectory() as directory:
        writer = EvidenceWriter(Path(directory), "schema-check")
        row = {"row_id": "schema-check:1", "run_id": "schema-check", "step_id": "IDENTIFY", "gate": "Identify", "machine_status": "acknowledged", "machine_reply_seq": 1, "human_response": "Y", "physical_status": "pass", "observed_value": "unavailable", "timestamp": time.time()}
        writer.record_row(row)
        replacement = dict(row, row_id="schema-check:2", observed_value={"device": "observed"})
        writer.replace_row(row["row_id"], replacement, "REPLACE")
        manifest = {"schema_version": 1, "kind": "manifest", "run_id": "schema-check", "status": "pass"}
        result = {"schema_version": 1, "kind": "result", "run_id": "schema-check", "status": "pass", "physical_map": {"rows": writer._rows, "guided_order": ["Identify", "Displays", "Keys", "Encoder", "LEDs", "Brightness", "Reboot", "Pair", "Recover", "Traffic", "Selection"]}}
        writer.finalize(manifest, result)
        checked = EvidenceWriter(Path(directory), "schema-check").verify()["result"]["physical_map"]["rows"]
        if len(checked) != 2 or checked[1].get("replaces") != row["row_id"]:
            raise AssertionError("replacement history is not linked and immutable")


def parse_group_responses(spec: str, run_id: str) -> dict[str, str]:
    """Parse exactly one bounded response for each machine batch gate."""
    if not isinstance(spec, str) or not spec.strip():
        raise EvidenceError("confirm-batch requires --groups for every machine gate")
    run_suffix = run_id[-6:].upper()
    parsed: dict[str, str] = {}
    for item in spec.split(","):
        item = item.strip()
        if not item or "=" not in item:
            raise EvidenceError("groups must use GATE=Y,N,R entries")
        gate, value = (part.strip().upper() for part in item.split("=", 1))
        if gate not in MACHINE_BATCH_GATES:
            raise EvidenceError(f"unknown machine gate in groups: {gate}")
        if gate in parsed:
            raise EvidenceError(f"duplicate machine gate in groups: {gate}")
        action, separator, supplied_suffix = value.partition("@")
        if action not in {"Y", "N", "R"}:
            raise EvidenceError(f"invalid group response for {gate}; use Y, N, or R")
        if separator and supplied_suffix != run_suffix:
            raise EvidenceError(f"run suffix mismatch for {gate}; expected {run_suffix}")
        parsed[gate] = action
    missing = [gate for gate in MACHINE_BATCH_GATES if gate not in parsed]
    if missing:
        raise EvidenceError("missing group responses: " + ", ".join(missing))
    return parsed


def verify_machine_run(path: Path) -> dict[str, Any]:
    """Verify a machine-only batch artifact and reject physical claims."""
    candidate = verify_physical_evidence(path)
    checked = EvidenceWriter(candidate.parent, candidate.name).verify()
    manifest = checked["manifest"]
    result = checked["result"]
    if manifest.get("workflow") != "batch-machine-only" or result.get("mode") != "machine-only":
        raise EvidenceError("evidence target is not a machine-only batch run")
    if manifest.get("run_id") != result.get("run_id") or result.get("physical_confirmation") is not False:
        raise EvidenceError("machine-only artifact identity or physical-confirmation marker is invalid")
    if "physical_map" in result:
        raise EvidenceError("machine-only artifact must not contain a physical_map")
    observations = result.get("machine_observations")
    if not isinstance(observations, list) or not observations:
        raise EvidenceError("machine-only artifact has no machine observations")
    seen: set[str] = set()
    gates: set[str] = set()
    for observation in observations:
        checked_observation = _validate_machine_observation(observation, str(result["run_id"]))
        if checked_observation["row_id"] in seen:
            raise EvidenceError("machine observation row ids must be unique")
        seen.add(checked_observation["row_id"])
        gates.add(str(checked_observation["gate"]).upper())
    if gates != {name.upper() for name in MACHINE_BATCH_GATE_NAMES}:
        raise EvidenceError("machine-only artifact does not cover all seven machine gates")
    return checked


def verify_physical_evidence(path: Path, require_physical_map: bool = False) -> Path:
    """Reopen a concrete immutable run and optionally require physical-map rows."""
    candidate = Path(path)
    if candidate.is_file() and candidate.name == "result.json":
        candidate = candidate.parent
    if not candidate.is_dir():
        raise EvidenceError(f"evidence target does not exist: {path}")
    result_path = candidate / "result.json"
    if not result_path.is_file():
        raise EvidenceError("evidence target must be a concrete run directory")
    writer = EvidenceWriter(candidate.parent, candidate.name)
    checked = writer.verify()
    if require_physical_map:
        _validate_physical_map(checked["result"])
    return candidate
