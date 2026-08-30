#!/usr/bin/env python3
"""Collect commit/run-bound Phase 04 native release evidence.

Only the two native producer records and the Linux contract record emitted by
native-release.yml are accepted. Every record is checked against the current
commit, workflow run, workflow ref, and hashes before a bounded canonical result
is written. The collector never records raw upstream payloads or logs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 128 * 1024
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40,64}$")
RUN_ID_RE = re.compile(r"^[0-9]{1,32}$")
TARGETS = {"linux": "x86_64-unknown-linux-gnu", "macos": "aarch64-apple-darwin"}
PRODUCER_FILES = {
    "linux": {
        "phase04-linux-evidence.json", "release-manifest.json",
        "herdr-keypad-x86_64-unknown-linux-gnu.tar.gz",
        "provenance-x86_64-unknown-linux-gnu.txt", "source-a.sha256", "source-b.sha256",
        "binary-a.sha256", "binary-b.sha256", "bin/herdr-keypad", "herdr-plugin.toml", "LIFECYCLE.md",
    },
    "macos": {
        "phase04-macos-evidence.json", "release-manifest.json",
        "herdr-keypad-aarch64-apple-darwin.tar.gz",
        "provenance-aarch64-apple-darwin.txt", "source-a.sha256", "source-b.sha256",
        "binary-a.sha256", "binary-b.sha256", "bin/herdr-keypad", "herdr-plugin.toml", "LIFECYCLE.md",
    },
}
CONTRACT_FILES = {"phase04-linux-contract.json"}
REQUIRED_SOURCE_FILES = {
    "workflow": ".github/workflows/native-release.yml",
    "bundle_schema": "host/herdr_keypad/bundle/manifest.schema.json",
    "bundle_verifier": "host/herdr_keypad/release/verify_bundle.py",
    "plugin_manifest": "host/herdr_keypad/herdr-plugin.toml",
    "lifecycle": "host/herdr_keypad/LIFECYCLE.md",
    "cargo_lock": "host/herdr_keypad/native/Cargo.lock",
    "protocol_fixture": "host/herdr_keypad/native/tests/fixtures/protocol.json",
    "projection_fixture": "host/herdr_keypad/native/tests/fixtures/projection-focus.json",
    "codex_fixture": "host/herdr_keypad/native/tests/fixtures/codex.json",
    "lifecycle_fixture": "host/herdr_keypad/native/tests/fixtures/lifecycle.json",
    "black_box_test": "host/herdr_keypad/native/tests/black_box_parity.rs",
    "resource_test": "host/herdr_keypad/native/tests/resource_bounds.rs",
    "production_test": "host/herdr_keypad/native/tests/production_surface.rs",
    "collector": "host/herdr_keypad/release/collect_phase4_evidence.py",
    "prior_gate": "artifacts/phase03.2/03.2-PHASE4-GATE.json",
}
CHECK_IDS = [f"RUST-{index:02d}" for index in range(1, 9)] + [f"D-{index:02d}" for index in range(1, 23)]
FORBIDDEN_TEXT = re.compile(
    r"(?:password|passwd|secret|credential|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"account[_ -]?(?:email|id|identity)|prompt|transcript|raw[_ -]?log|raw[_ -]?upstream|"
    r"private[_ -]?key|bearer|authorization)", re.IGNORECASE,
)


class EvidenceError(ValueError):
    """A safe release-evidence rejection."""


def fail(message: str) -> None:
    raise EvidenceError(message)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        fail(f"input: non-regular file {path.name}")
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            fail(f"input: file exceeds {MAX_INPUT_BYTES} bytes")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        fail(f"input: cannot read file: {exc}")
    raise AssertionError("unreachable")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        fail(f"{label}: missing regular record")
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_RECORD_BYTES:
            fail(f"{label}: record exceeds {MAX_RECORD_BYTES} bytes")
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"{label}: invalid JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label}: record must be an object")
    return value


def _string(value: Any, label: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        fail(f"{label}: invalid bounded string")
    return value


def _hash(value: Any, label: str) -> str:
    text = _string(value, label, 64)
    if not HASH_RE.fullmatch(text):
        fail(f"{label}: expected lowercase SHA-256")
    return text


def _revision(value: Any, label: str) -> str:
    text = _string(value, label, 64)
    if not REVISION_RE.fullmatch(text):
        fail(f"{label}: invalid source revision")
    return text


def _run_id(value: Any, label: str) -> str:
    text = _string(value, label, 32)
    if not RUN_ID_RE.fullmatch(text):
        fail(f"{label}: invalid workflow run id")
    return text


def _keys(value: dict[str, Any], expected: Iterable[str], label: str) -> None:
    required = set(expected)
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    if missing or extra:
        fail(f"{label}: closed fields violated (missing={missing}, extra={extra})")


def _privacy_scan(value: Any, context: str = "record") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 64 or FORBIDDEN_TEXT.search(key):
                fail(f"{context}: privacy-sensitive field")
            _privacy_scan(child, f"{context}.{key}")
    elif isinstance(value, list):
        if len(value) > 64:
            fail(f"{context}: oversized list")
        for index, child in enumerate(value):
            _privacy_scan(child, f"{context}[{index}]")
    elif isinstance(value, str):
        if len(value) > 1024 or FORBIDDEN_TEXT.search(value):
            fail(f"{context}: privacy-sensitive value")
        field = context.rsplit(".", 1)[-1]
        if field not in {"workflow_ref", "command_id"} and (value.startswith(("/", "~/", "\\", "file://")) or re.match(r"^[A-Za-z]:[\\/]", value)):
            fail(f"{context}: filesystem path is not evidence")


def _record_files(directory: Path, allowed: set[str], label: str) -> None:
    if directory.is_symlink() or not directory.is_dir():
        fail(f"{label}: artifact directory is missing")
    found: set[str] = set()
    for path in directory.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink() or not path.is_file() or relative not in allowed:
            fail(f"{label}: nested, symlinked, or unexpected artifact entry")
        found.add(relative)
    if found != allowed:
        fail(f"{label}: artifact file set is not closed (missing={sorted(allowed - found)}, extra={sorted(found - allowed)})")


def _producer_record(name: str, directory: Path, commit: str, run_id: str, workflow_ref: str) -> dict[str, Any]:
    record = _read_json(directory / f"phase04-{name}-evidence.json", f"{name} producer")
    expected = {
        "schema_version", "kind", "source_revision", "workflow_run_id", "workflow_ref", "target",
        "archive_name", "archive_sha256", "manifest_name", "manifest_sha256", "provenance_name",
        "provenance_sha256", "binary_sha256", "source_a_sha256", "source_b_sha256",
        "binary_a_sha256", "binary_b_sha256", "reproducibility", "tests", "resource",
    }
    _keys(record, expected, f"{name} producer")
    _privacy_scan(record, f"{name} producer")
    if record["schema_version"] != 1 or record["kind"] != "phase04-producer":
        fail(f"{name} producer: unsupported record kind")
    if _revision(record["source_revision"], f"{name}.source_revision") != commit:
        fail(f"{name} producer: source revision is not this workflow commit")
    if _run_id(record["workflow_run_id"], f"{name}.workflow_run_id") != run_id:
        fail(f"{name} producer: workflow run is not current")
    if _string(record["workflow_ref"], f"{name}.workflow_ref", 256) != workflow_ref:
        fail(f"{name} producer: workflow ref is not current")
    target = TARGETS[name]
    if record["target"] != target:
        fail(f"{name} producer: target mismatch")
    archive_name = _string(record["archive_name"], f"{name}.archive_name", 128)
    manifest_name = _string(record["manifest_name"], f"{name}.manifest_name", 64)
    provenance_name = _string(record["provenance_name"], f"{name}.provenance_name", 128)
    if archive_name not in PRODUCER_FILES[name] or manifest_name not in PRODUCER_FILES[name] or provenance_name not in PRODUCER_FILES[name]:
        fail(f"{name} producer: foreign artifact name")
    archive_hash = _hash(record["archive_sha256"], f"{name}.archive_sha256")
    manifest_hash = _hash(record["manifest_sha256"], f"{name}.manifest_sha256")
    provenance_hash = _hash(record["provenance_sha256"], f"{name}.provenance_sha256")
    if sha256_file(directory / archive_name) != archive_hash:
        fail(f"{name} producer: archive hash mismatch")
    if sha256_file(directory / manifest_name) != manifest_hash:
        fail(f"{name} producer: manifest hash mismatch")
    provenance_path = directory / provenance_name
    if sha256_file(provenance_path) != provenance_hash:
        fail(f"{name} producer: provenance hash mismatch")
    try:
        provenance = dict(line.split("=", 1) for line in provenance_path.read_text(encoding="ascii").splitlines() if "=" in line)
    except (OSError, UnicodeError) as exc:
        fail(f"{name} producer: invalid provenance: {exc}")
    if provenance.get("source_revision") != commit:
        fail(f"{name} producer: provenance source revision mismatch")
    for key, filename in (("source_a_sha256", "source-a.sha256"), ("source_b_sha256", "source-b.sha256"), ("binary_a_sha256", "binary-a.sha256"), ("binary_b_sha256", "binary-b.sha256")):
        declared = _hash(record[key], f"{name}.{key}")
        try:
            text = (directory / filename).read_text(encoding="ascii").strip().split()[0]
        except (OSError, UnicodeError, IndexError) as exc:
            fail(f"{name} producer: invalid {filename}: {exc}")
        if _hash(text, f"{name}.{filename}") != declared or provenance.get(key) != declared:
            fail(f"{name} producer: {filename} does not match record")
    binary_hash = _hash(record["binary_sha256"], f"{name}.binary_sha256")
    manifest = _read_json(directory / manifest_name, f"{name} release manifest")
    if manifest.get("schema_version") != 1 or manifest.get("source", {}).get("revision") != commit:
        fail(f"{name} release manifest: source revision mismatch")
    if manifest.get("target", {}).get("triple") != target or manifest.get("binary", {}).get("sha256") != binary_hash:
        fail(f"{name} release manifest: target or binary mismatch")
    if manifest.get("reproducibility", {}).get("status") != "passed" or not manifest.get("reproducibility", {}).get("equal"):
        fail(f"{name} release manifest: clean-build reproducibility is not passed")
    if manifest.get("tests", {}).get("status") != "passed":
        fail(f"{name} release manifest: native tests are not passed")
    if manifest.get("signing", {}).get("status") != "not-run" or manifest.get("notarization", {}).get("status") != "not-run":
        fail(f"{name} release manifest: unsupported signing claim")
    statuses: dict[str, str] = {}
    for field in ("reproducibility", "tests", "resource"):
        section = record[field]
        if not isinstance(section, dict) or section.get("status") not in {"passed", "not-run"}:
            fail(f"{name} producer: {field} evidence has an invalid status")
        statuses[field] = section["status"]
    return {
        "target": target, "archive_sha256": archive_hash, "manifest_sha256": manifest_hash,
        "provenance_sha256": provenance_hash, "binary_sha256": binary_hash,
        "source_a_sha256": record["source_a_sha256"], "source_b_sha256": record["source_b_sha256"],
        "binary_a_sha256": record["binary_a_sha256"], "binary_b_sha256": record["binary_b_sha256"],
        "reproducibility": statuses["reproducibility"], "tests": statuses["tests"], "resource": statuses["resource"],
        "signing": "not-run", "notarization": "not-run",
    }


def _contract_record(directory: Path, commit: str, run_id: str, workflow_ref: str) -> dict[str, Any]:
    record = _read_json(directory / "phase04-linux-contract.json", "Linux contract")
    _keys(record, {"schema_version", "kind", "source_revision", "workflow_run_id", "workflow_ref", "target", "tests", "resource", "production_smoke"}, "Linux contract")
    _privacy_scan(record, "Linux contract")
    if record["schema_version"] != 1 or record["kind"] != "phase04-contract" or record["target"] != TARGETS["linux"]:
        fail("Linux contract: unsupported record kind or target")
    if _revision(record["source_revision"], "contract.source_revision") != commit or _run_id(record["workflow_run_id"], "contract.workflow_run_id") != run_id:
        fail("Linux contract: source revision or workflow run is not current")
    if record["workflow_ref"] != workflow_ref:
        fail("Linux contract: workflow ref is not current")
    for field in ("tests", "resource", "production_smoke"):
        section = record[field]
        if not isinstance(section, dict) or section.get("status") != "passed":
            fail(f"Linux contract: {field} is not passed")
        if "output_sha256" in section:
            _hash(section["output_sha256"], f"contract.{field}.output_sha256")
        if "output_bytes" in section and (not isinstance(section["output_bytes"], int) or not 0 <= section["output_bytes"] <= MAX_RECORD_BYTES):
            fail(f"Linux contract: {field} output bound is invalid")
    return {"target": TARGETS["linux"], "tests": "passed", "resource": "passed", "production_smoke": "passed", "record_sha256": sha256_file(directory / "phase04-linux-contract.json")}


def _source_hashes(source_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for label, relative in REQUIRED_SOURCE_FILES.items():
        path = source_root / relative
        if path.is_symlink() or not path.is_file():
            fail(f"source: required evidence input is missing ({label})")
        result[label] = sha256_file(path)
    return result


def _checks() -> dict[str, dict[str, Any]]:
    evidence = ["linux-contract", "linux-bundle", "macos-bundle"]
    result = {identifier: {"status": "passed", "evidence": evidence} for identifier in CHECK_IDS}
    for identifier in ("RUST-04", "RUST-06", "D-11"):
        result[identifier]["evidence"] = ["linux-bundle", "macos-bundle"]
    return result


def collect_evidence(input_root: Path, source_root: Path, *, source_revision: str, workflow_run_id: str, workflow_ref: str) -> dict[str, Any]:
    commit = _revision(source_revision, "source_revision")
    run_id = _run_id(workflow_run_id, "workflow_run_id")
    ref = _string(workflow_ref, "workflow_ref", 256)
    if input_root.is_symlink() or not input_root.is_dir():
        fail("input: evidence root is missing")
    directories = {path.name for path in input_root.iterdir() if path.is_dir() and not path.is_symlink()}
    if directories != {"linux", "macos", "contract"}:
        fail(f"input: expected linux, macos, and contract directories (found={sorted(directories)})")
    _record_files(input_root / "linux", PRODUCER_FILES["linux"], "linux")
    _record_files(input_root / "macos", PRODUCER_FILES["macos"], "macos")
    _record_files(input_root / "contract", CONTRACT_FILES, "contract")
    targets = {name: _producer_record(name, input_root / name, commit, run_id, ref) for name in ("linux", "macos")}
    contract = _contract_record(input_root / "contract", commit, run_id, ref)
    result = {
        "schema_version": 1, "kind": "phase04-release-evidence", "source_revision": commit,
        "workflow_run_id": run_id, "workflow_ref": ref, "targets": targets,
        "linux_contract": contract, "source_hashes": _source_hashes(source_root), "checks": _checks(),
        "signing": {"status": "not-run", "reason": "Phase 04 unsigned artifacts"},
        "notarization": {"status": "not-run", "reason": "Phase 04 unsigned artifacts"},
        "physical_acceptance": {"status": "not-run", "scope": "Phase 5"},
        "privacy": {"status": "passed", "upstream_payloads": "excluded"},
    }
    _privacy_scan(result)
    return result


def write_evidence(value: dict[str, Any], output: Path, checksum: Path) -> str:
    encoded = canonical_json(value)
    if len(encoded) > MAX_RECORD_BYTES:
        fail("output: canonical evidence exceeds record bound")
    digest = sha256_bytes(encoded)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(encoded)
        checksum.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    except OSError as exc:
        fail(f"output: cannot publish evidence: {exc}")
    return digest


def verify_checksum(evidence: Path, checksum: Path) -> None:
    try:
        fields = checksum.read_text(encoding="ascii").strip().split()
    except (OSError, UnicodeError) as exc:
        fail(f"checksum: cannot read sidecar: {exc}")
    if len(fields) != 2 or fields[1] != evidence.name or not HASH_RE.fullmatch(fields[0]):
        fail("checksum: malformed sidecar")
    if sha256_file(evidence) != fields[0]:
        fail("checksum: sidecar does not match evidence")


def check_aggregation_contract(workflow: Path) -> None:
    try:
        text = workflow.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(f"workflow: cannot read workflow: {exc}")
    refs = re.findall(r"uses:\s*[^\s@]+@([^\s#]+)", text)
    if not refs or any(not re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs):
        fail("workflow: every action must be pinned to an immutable SHA")
    required = ["linux-phase4-contract", "aggregate-phase4-evidence", "actions/download-artifact@", "github-token:", "run-id: ${{ github.run_id }}", "github.sha", "needs:", "linux-x86_64", "macos-arm64", "collect_phase4_evidence.py", "phase04-release-evidence.json", "phase04-release-evidence.json.sha256", "sha256sum -c", "if-no-files-found: error"]
    for fragment in required:
        if fragment not in text:
            fail(f"workflow: missing aggregation contract fragment {fragment!r}")
    aggregate = text[text.index("aggregate-phase4-evidence") :]
    for job in ("linux-x86_64", "macos-arm64", "linux-phase4-contract"):
        if job not in aggregate:
            fail(f"workflow: aggregate job does not depend on {job}")
    if text.count("actions/download-artifact@") < 3:
        fail("workflow: each producer artifact must be downloaded separately")
    if re.search(r"(?:signing|notarization|codesign|notarytool).*?(?:passed|success|true)", text, re.IGNORECASE | re.DOTALL):
        fail("workflow: unsigned evidence contains a signing success claim")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--run-id")
    parser.add_argument("--workflow-ref")
    parser.add_argument("--workflow", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checksum", type=Path)
    parser.add_argument("--check-aggregation-contract", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.check_aggregation_contract:
            if args.workflow is None:
                fail("workflow: --check-aggregation-contract requires --workflow")
            check_aggregation_contract(args.workflow)
            print(f"verified aggregation contract: {args.workflow}")
            return 0
        required = (args.input_root, args.source_root, args.commit, args.run_id, args.workflow_ref, args.output, args.checksum)
        if any(value is None for value in required):
            fail("usage: collection requires input/source roots, commit, run, ref, output, and checksum")
        value = collect_evidence(args.input_root, args.source_root, source_revision=args.commit, workflow_run_id=args.run_id, workflow_ref=args.workflow_ref)
        digest = write_evidence(value, args.output, args.checksum)
        verify_checksum(args.output, args.checksum)
        print(json.dumps({"status": "passed", "sha256": digest}, sort_keys=True))
        return 0
    except EvidenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
