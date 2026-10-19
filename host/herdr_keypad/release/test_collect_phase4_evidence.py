from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from host.herdr_keypad.release.collect_phase4_evidence import (
    EvidenceError,
    REQUIRED_SOURCE_FILES,
    TARGETS,
    collect_evidence,
    verify_checksum,
    write_evidence,
)


COMMIT = "a" * 40
RUN_ID = "123456"
REF = "refs/heads/main"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def producer(root: Path, name: str) -> None:
    target = TARGETS[name]
    directory = root / name
    (directory / "bin").mkdir(parents=True)
    archive_name = f"herdr-keypad-{target}.tar.gz"
    provenance_name = f"provenance-{target}.txt"
    archive = f"archive-{name}".encode()
    binary = f"binary-{name}".encode()
    archive_hash = digest(archive)
    binary_hash = digest(binary)
    source_a = "1" * 64
    source_b = "2" * 64
    binary_a = "3" * 64
    binary_b = "4" * 64
    (directory / archive_name).write_bytes(archive)
    (directory / "bin/herdr-keypad").write_bytes(binary)
    (directory / "herdr-plugin.toml").write_text("id = \"fixture\"\n", encoding="ascii")
    (directory / "LIFECYCLE.md").write_text("# Lifecycle\n", encoding="ascii")
    (directory / "source-a.sha256").write_text(f"{source_a}  source-a.tar\n", encoding="ascii")
    (directory / "source-b.sha256").write_text(f"{source_b}  source-b.tar\n", encoding="ascii")
    (directory / "binary-a.sha256").write_text(f"{binary_a}  binary-a\n", encoding="ascii")
    (directory / "binary-b.sha256").write_text(f"{binary_b}  binary-b\n", encoding="ascii")
    manifest = {
        "schema_version": 1,
        "source": {"revision": COMMIT},
        "target": {"triple": target},
        "binary": {"sha256": binary_hash},
        "reproducibility": {"status": "passed", "equal": True},
        "tests": {"status": "passed"},
        "signing": {"status": "not-run"},
        "notarization": {"status": "not-run"},
    }
    write_json(directory / "release-manifest.json", manifest)
    manifest_hash = digest((directory / "release-manifest.json").read_bytes())
    provenance = (
        f"source_revision={COMMIT}\nsource_a_sha256={source_a}\nsource_b_sha256={source_b}\n"
        f"binary_a_sha256={binary_a}\nbinary_b_sha256={binary_b}\n"
    )
    (directory / provenance_name).write_text(provenance, encoding="ascii")
    provenance_hash = digest((directory / provenance_name).read_bytes())
    record = {
        "schema_version": 1,
        "kind": "phase04-producer",
        "source_revision": COMMIT,
        "workflow_run_id": RUN_ID,
        "workflow_ref": REF,
        "target": target,
        "archive_name": archive_name,
        "archive_sha256": archive_hash,
        "manifest_name": "release-manifest.json",
        "manifest_sha256": manifest_hash,
        "provenance_name": provenance_name,
        "provenance_sha256": provenance_hash,
        "binary_sha256": binary_hash,
        "source_a_sha256": source_a,
        "source_b_sha256": source_b,
        "binary_a_sha256": binary_a,
        "binary_b_sha256": binary_b,
        "reproducibility": {"status": "passed"},
        "tests": {"status": "passed"},
        "resource": {"status": "passed"},
    }
    write_json(directory / f"phase04-{name}-evidence.json", record)


def contract(root: Path) -> None:
    directory = root / "contract"
    directory.mkdir()
    write_json(
        directory / "phase04-linux-contract.json",
        {
            "schema_version": 1,
            "kind": "phase04-contract",
            "source_revision": COMMIT,
            "workflow_run_id": RUN_ID,
            "workflow_ref": REF,
            "target": TARGETS["linux"],
            "tests": {"status": "passed", "output_sha256": "5" * 64, "output_bytes": 128},
            "resource": {"status": "passed", "output_sha256": "6" * 64, "output_bytes": 64},
            "production_smoke": {"status": "passed", "output_sha256": "7" * 64, "output_bytes": 32},
        },
    )


def source_root(root: Path) -> None:
    for relative in REQUIRED_SOURCE_FILES.values():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"evidence source {relative}\n".encode())


def valid_tree() -> tuple[Path, Path]:
    temporary = Path(tempfile.mkdtemp(prefix="phase04-collector-test-"))
    inputs = temporary / "inputs"
    inputs.mkdir()
    producer(inputs, "linux")
    producer(inputs, "macos")
    contract(inputs)
    source = temporary / "source"
    source_root(source)
    return inputs, source


class CollectorTests(unittest.TestCase):
    def test_valid_inputs_produce_bounded_hash_linked_record_and_sidecar(self) -> None:
        inputs, source = valid_tree()
        try:
            result = collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
            self.assertEqual(result["kind"], "phase04-release-evidence")
            self.assertEqual(set(result["checks"]), {f"RUST-0{i}" for i in range(1, 9)} | {f"D-{i:02d}" for i in range(1, 23)})
            output = inputs.parent / "phase04-release-evidence.json"
            checksum = inputs.parent / "phase04-release-evidence.json.sha256"
            write_evidence(result, output, checksum)
            verify_checksum(output, checksum)
            self.assertEqual(result["signing"]["status"], "not-run")
            self.assertEqual(result["physical_acceptance"]["scope"], "Phase 5")
        finally:
            shutil.rmtree(inputs.parent)

    def test_missing_target_or_contract_fails_closed(self) -> None:
        for missing in ("macos", "contract"):
            inputs, source = valid_tree()
            try:
                shutil.rmtree(inputs / missing)
                with self.assertRaises(EvidenceError):
                    collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
            finally:
                shutil.rmtree(inputs.parent)

    def test_duplicate_target_foreign_name_and_unexpected_file_fail_closed(self) -> None:
        inputs, source = valid_tree()
        try:
            shutil.copy2(inputs / "linux/phase04-linux-evidence.json", inputs / "linux/phase04-linux-evidence-copy.json")
            with self.assertRaises(EvidenceError):
                collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
        finally:
            shutil.rmtree(inputs.parent)

        inputs, source = valid_tree()
        try:
            record = inputs / "linux/phase04-linux-evidence.json"
            value = json.loads(record.read_text())
            value["archive_name"] = "foreign.tar.gz"
            write_json(record, value)
            with self.assertRaises(EvidenceError):
                collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
        finally:
            shutil.rmtree(inputs.parent)

    def test_wrong_commit_run_ref_and_tampered_hash_fail_closed(self) -> None:
        for field, value in (("source_revision", "b" * 40), ("workflow_run_id", "999"), ("workflow_ref", "refs/tags/foreign")):
            inputs, source = valid_tree()
            try:
                record_path = inputs / "linux/phase04-linux-evidence.json"
                record = json.loads(record_path.read_text())
                record[field] = value
                write_json(record_path, record)
                with self.assertRaises(EvidenceError):
                    collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
            finally:
                shutil.rmtree(inputs.parent)

        inputs, source = valid_tree()
        try:
            archive = inputs / "linux/herdr-keypad-x86_64-unknown-linux-gnu.tar.gz"
            archive.write_bytes(b"tampered")
            with self.assertRaises(EvidenceError):
                collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
        finally:
            shutil.rmtree(inputs.parent)

    def test_missing_clean_build_provenance_is_rejected(self) -> None:
        inputs, source = valid_tree()
        try:
            manifest = inputs / "linux/release-manifest.json"
            value = json.loads(manifest.read_text())
            value["reproducibility"] = {"status": "not-run", "equal": False}
            write_json(manifest, value)
            with self.assertRaises(EvidenceError):
                collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
        finally:
            shutil.rmtree(inputs.parent)

    def test_missing_provenance_privacy_and_oversized_records_fail_closed(self) -> None:
        inputs, source = valid_tree()
        try:
            (inputs / "linux/provenance-x86_64-unknown-linux-gnu.txt").unlink()
            with self.assertRaises(EvidenceError):
                collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
        finally:
            shutil.rmtree(inputs.parent)

        inputs, source = valid_tree()
        try:
            record_path = inputs / "linux/phase04-linux-evidence.json"
            record = json.loads(record_path.read_text())
            record["account_identity"] = "private"
            write_json(record_path, record)
            with self.assertRaises(EvidenceError):
                collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
        finally:
            shutil.rmtree(inputs.parent)

        inputs, source = valid_tree()
        try:
            record_path = inputs / "linux/phase04-linux-evidence.json"
            record = json.loads(record_path.read_text())
            record["tests"]["command_id"] = "x" * 140_000
            write_json(record_path, record)
            with self.assertRaises(EvidenceError):
                collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
        finally:
            shutil.rmtree(inputs.parent)

    def test_absent_or_tampered_checksum_fails_closed(self) -> None:
        inputs, source = valid_tree()
        try:
            result = collect_evidence(inputs, source, source_revision=COMMIT, workflow_run_id=RUN_ID, workflow_ref=REF)
            output = inputs.parent / "phase04-release-evidence.json"
            checksum = inputs.parent / "phase04-release-evidence.json.sha256"
            write_evidence(result, output, checksum)
            checksum.unlink()
            with self.assertRaises(EvidenceError):
                verify_checksum(output, checksum)
            checksum.write_text("0" * 64 + "  phase04-release-evidence.json\n", encoding="ascii")
            with self.assertRaises(EvidenceError):
                verify_checksum(output, checksum)
        finally:
            shutil.rmtree(inputs.parent)


if __name__ == "__main__":
    unittest.main()
