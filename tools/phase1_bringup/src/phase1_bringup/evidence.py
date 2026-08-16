"""Atomic, immutable evidence persistence for the Phase 1 tracer."""
from __future__ import annotations

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


class EvidenceWriter:
    """Write one immutable manifest/result pair and verify it after reopening.

    A target directory is never overwritten. If a write fails, the attempted
    files and error are retained under a unique ``failed-attempt-*`` directory.
    """

    def __init__(self, root: Path, run_id: str):
        if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
            raise ValueError("run_id must be a single non-empty path component")
        self.root = Path(root)
        self.run_id = run_id
        self.directory = self.root / run_id

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
    manifest = {
        "schema_version": 1,
        "kind": "manifest",
        "run_id": run_id,
        "status": "self-check",
        "protocol": {"version": 1, "max_line_bytes_including_lf": 4096},
        "environment": {"python": "verified", "pyserial": "3.5"},
    }
    result = {
        "schema_version": 1,
        "kind": "result",
        "run_id": run_id,
        "status": "pass",
        "physical_observation": "unavailable",
        "transport": {"type": "self-check", "acknowledged": True},
    }
    path = writer.write(manifest, result)
    reopened = EvidenceWriter(root, run_id)
    reopened.verify()
    return path
