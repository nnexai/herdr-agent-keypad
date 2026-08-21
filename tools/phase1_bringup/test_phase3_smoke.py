from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from phase1_bringup.phase3_smoke import (
    HUMAN_ROWS,
    ROOT,
    finalize_evidence,
    sha256_file,
    write_json,
)


class Phase3FinalizeTests(unittest.TestCase):
    def fixture(self, root: Path, *, receipt_time: int = 200) -> SimpleNamespace:
        source = ROOT / "artifacts/phase3/03-DEVICE-EVIDENCE.json"
        evidence = json.loads(source.read_text(encoding="utf-8"))
        rows = {row["id"]: row for row in evidence["physical_observations"]}
        for row_id in HUMAN_ROWS:
            rows[row_id]["result"] = "pass"
            rows[row_id]["observation"] = {
                "answer": "Y",
                "prompt": "bounded physical observation",
                "observed_at_unix_ms": 100,
                "fresh_hello_session_id": "session-physical",
            }
        evidence_path = root / "evidence.json"
        write_json(evidence_path, evidence, checksum=True)
        deployment = evidence["deployment"]
        receipt = {
            "schema_version": 1,
            "kind": "phase3-bridge-publication-receipt",
            "published_at_unix_ms": receipt_time,
            "binary_sha256": deployment["binary_sha256"],
            "hello": {
                "device_id": deployment["paired_device_id"],
                "firmware": deployment["hello_firmware"],
                "protocol": deployment["protocol_version"],
                "boot_id": deployment["fresh_boot_id"],
                "session_id": "session-bridge",
                "usb_serial": deployment["usb_serial"],
            },
            "snapshot_ack": {"accepted": True, "snapshot_revision": 9},
        }
        receipt_path = root / "publication.json"
        receipt_path.write_text(json.dumps(receipt), encoding="ascii")
        return SimpleNamespace(
            evidence=evidence_path,
            firmware=ROOT / deployment["binary_path"],
            publication_receipt=receipt_path,
        )

    def test_finalize_binds_fresh_receipt_and_closes_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            args = self.fixture(Path(directory))
            self.assertEqual(finalize_evidence(args), 0)
            evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "pass")
            resync = next(
                row for row in evidence["physical_observations"]
                if row["id"] == "fresh-bridge-resync-after-acceptance"
            )
            self.assertEqual(resync["source"], "machine")
            self.assertTrue(resync["observation"]["accepted"])
            self.assertEqual(
                sha256_file(args.evidence),
                args.evidence.with_suffix(".json.sha256").read_text().split()[0],
            )

    def test_finalize_rejects_receipt_older_than_observations(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            args = self.fixture(Path(directory), receipt_time=100)
            with self.assertRaisesRegex(RuntimeError, "does not postdate"):
                finalize_evidence(args)


if __name__ == "__main__":
    unittest.main()
