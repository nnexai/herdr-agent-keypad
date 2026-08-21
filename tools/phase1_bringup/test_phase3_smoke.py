from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from phase1_bringup.phase3_smoke import (
    HUMAN_ROWS,
    ROOT,
    finalize_evidence,
    run_guided,
    sha256_file,
    write_json,
)


class FakeLiveBridge:
    def __init__(self) -> None:
        self.active = False

    def __enter__(self) -> "FakeLiveBridge":
        self.active = True
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.active = False

    def poll(self) -> None:
        return None


class Phase3GuidedRunTests(unittest.TestCase):
    def test_guided_run_keeps_live_bridge_during_physical_prompt(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            root = Path(directory)
            evidence = json.loads(
                (ROOT / "artifacts/phase3/03-DEVICE-EVIDENCE.json").read_text(encoding="utf-8")
            )
            for row in evidence["physical_observations"]:
                if row["id"] in HUMAN_ROWS:
                    row["result"] = "pass"
            target = next(
                row for row in evidence["physical_observations"]
                if row["id"] == "direct-agent-keys-from-root"
            )
            target["result"] = "pending"
            target["observation"] = None
            args = SimpleNamespace(
                binding=root / "binding.json",
                firmware=root / "firmware.bin",
                tracer=root / "tracer.json",
                evidence=root / "evidence.json",
                timeout=0.1,
            )
            bridge = FakeLiveBridge()
            fresh = {
                "device_id": evidence["deployment"]["paired_device_id"],
                "firmware": evidence["deployment"]["hello_firmware"],
                "protocol": evidence["deployment"]["protocol_version"],
                "session_id": "session-guided",
            }

            def answer(_prompt: str) -> str:
                self.assertTrue(bridge.active)
                return "Y"

            with (
                patch(
                    "phase1_bringup.phase3_smoke.preflight_run",
                    return_value=(evidence, fresh),
                ),
                patch(
                    "phase1_bringup.phase3_smoke.guided_bridge",
                    return_value=bridge,
                ),
                patch("builtins.input", side_effect=answer),
            ):
                self.assertEqual(run_guided(args), 0)
            self.assertFalse(bridge.active)


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
                "boot_id": "rebooted-device-boot",
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
            self.assertEqual(resync["observation"]["boot_id"], "rebooted-device-boot")
            self.assertEqual(
                sha256_file(args.evidence),
                args.evidence.with_suffix(".json.sha256").read_text().split()[0],
            )

    def test_finalize_rejects_receipt_older_than_observations(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            args = self.fixture(Path(directory), receipt_time=100)
            with self.assertRaisesRegex(RuntimeError, "does not postdate"):
                finalize_evidence(args)

    def test_finalize_rejects_invalid_revision_and_publication_identity(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            root = Path(directory)
            cases = (
                ("negative-revision", "revision", -1, "not acknowledged"),
                ("boolean-revision", "revision", True, "not acknowledged"),
                ("missing-boot", "boot_id", "", "identity is invalid"),
                ("missing-session", "session_id", "", "identity is invalid"),
            )
            for index, (name, field, value, error) in enumerate(cases):
                with self.subTest(name=name):
                    case_root = root / str(index)
                    case_root.mkdir()
                    args = self.fixture(case_root)
                    receipt = json.loads(args.publication_receipt.read_text(encoding="ascii"))
                    if field == "revision":
                        receipt["snapshot_ack"]["snapshot_revision"] = value
                    else:
                        receipt["hello"][field] = value
                    args.publication_receipt.write_text(json.dumps(receipt), encoding="ascii")
                    with self.assertRaisesRegex(RuntimeError, error):
                        finalize_evidence(args)

class Phase31ProfileTests(unittest.TestCase):
    def test_phase31_profile_preserves_unavailable_physical_observation(self):
        from phase1_bringup.phase3_smoke import phase31_lock_from_baseline, validate_phase31_baseline

        baseline = {
            "schema_version": 1,
            "kind": "phase03.1-baseline-profile",
            "deployment": {"deployment_id": "deployment"},
            "metrics": {
                name: 1 for name in (
                    "loop_wall_max_us", "compose_flush_max_us", "frame_count",
                    "full_frames", "half_frames", "static_frames", "level_changes",
                    "skipped_frames", "degraded_frames", "reveal_max_us",
                    "first_press_response_us", "first_encoder_response_us",
                    "max_key_poll_gap_us", "minimum_free_heap", "largest_free_block",
                    "parser_high_water", "queue_high_water", "allocation_stable",
                    "animation_duty_max_percent",
                )
            },
            "observations": [
                {
                    "id": observation_id,
                    "result": "unavailable" if observation_id == "brightness-power" else "pass",
                    "method": "not measured",
                }
                for observation_id in (
                    "blocked-cycle", "direct-key-response", "encoder-response",
                    "display-led-alignment", "smoothness", "brightness-power",
                )
            ],
        }
        baseline["measurement_window"] = {"started_unix_ms": 1, "ended_unix_ms": 2}
        baseline["samples"] = [{"id": "sample", "metrics": baseline["metrics"]}]
        validate_phase31_baseline(baseline)
        with self.assertRaisesRegex(ValueError, "physical observation"):
            phase31_lock_from_baseline(baseline)


class Phase31BudgetLockTests(unittest.TestCase):
    def test_phase31_budget_lock_caps_measurements_and_keeps_ids(self):
        from phase1_bringup.phase3_smoke import phase31_lock_from_baseline

        metrics = {
            name: 1 for name in (
                "loop_wall_max_us", "compose_flush_max_us", "frame_count",
                "full_frames", "half_frames", "static_frames", "level_changes",
                "skipped_frames", "degraded_frames", "reveal_max_us",
                "first_press_response_us", "first_encoder_response_us",
                "max_key_poll_gap_us", "minimum_free_heap", "largest_free_block",
                "parser_high_water", "queue_high_water", "allocation_stable",
                "animation_duty_max_percent",
            )
        }
        baseline = {
            "schema_version": 1,
            "kind": "phase03.1-baseline-profile",
            "deployment": {"deployment_id": "deployment"},
            "metrics": metrics,
            "measurement_window": {"started_unix_ms": 1, "ended_unix_ms": 2},
            "samples": [{"id": "sample", "metrics": metrics}],
            "observations": [
                {
                    "id": observation_id,
                    "result": "pass",
                    "method": "exact-device",
                }
                for observation_id in (
                    "blocked-cycle", "direct-key-response", "encoder-response",
                    "display-led-alignment", "smoothness", "brightness-power",
                )
            ],
        }
        lock = phase31_lock_from_baseline(baseline)
        self.assertLessEqual(lock["ceilings"]["ordinary_transition_us"], 250000)
        self.assertLessEqual(lock["limits"]["ordinary_transition_us"], 250000)
        self.assertEqual(
            lock["limits"]["source_observation_ids"],
            ["blocked-cycle", "direct-key-response", "encoder-response",
             "display-led-alignment", "smoothness", "brightness-power"],
        )
        self.assertIn("Beacon", lock["cadence_us"])
        self.assertLessEqual(lock["limits"]["animation_duty_percent"], 30)


    def test_phase31_budget_lock_rejects_measurement_above_hard_ceiling(self):
        from phase1_bringup.phase3_smoke import phase31_lock_from_baseline

        metrics = {name: 1 for name in (
            "loop_wall_max_us", "compose_flush_max_us", "frame_count",
            "full_frames", "half_frames", "static_frames", "level_changes",
            "skipped_frames", "degraded_frames", "reveal_max_us",
            "first_press_response_us", "first_encoder_response_us",
            "max_key_poll_gap_us", "minimum_free_heap", "largest_free_block",
            "parser_high_water", "queue_high_water", "allocation_stable",
            "animation_duty_max_percent",
        )}
        metrics["first_press_response_us"] = 120001
        baseline = {
            "schema_version": 1,
            "kind": "phase03.1-baseline-profile",
            "deployment": {"deployment_id": "deployment"},
            "metrics": metrics,
            "measurement_window": {"started_unix_ms": 1, "ended_unix_ms": 2},
            "samples": [{"id": "sample", "metrics": metrics}],
            "observations": [
                {
                    "id": observation_id,
                    "result": "pass",
                    "method": "exact-device",
                }
                for observation_id in (
                    "blocked-cycle", "direct-key-response", "encoder-response",
                    "display-led-alignment", "smoothness", "brightness-power",
                )
            ],
        }
        with self.assertRaisesRegex(ValueError, "press"):
            phase31_lock_from_baseline(baseline)


if __name__ == "__main__":
    unittest.main()
