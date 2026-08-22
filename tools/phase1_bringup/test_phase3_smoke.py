from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from phase1_bringup.phase3_smoke import (
    HUMAN_ROWS,
    ROOT,
    _phase31_sidecar,
    finalize_evidence,
    phase32_descriptor_tuple,
    phase32_descriptor_tuple_sha256,
    phase32_source_digest,
    phase32_deployment_id_for,
    validate_phase32_composite_lineage,
    validate_phase32_deployment,
    validate_phase32_deployment_file,
    run_guided,
    sha256_file,
    validate_phase31_current_deployment_identity,
    validate_phase31_reset_epoch,
    write_json,
)
from phase1_bringup.protocol import classify_line, new_frame


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
        deployment = evidence["deployment"]
        firmware_path = root / "firmware.bin"
        firmware_path.write_bytes(b"phase3-finalize-fixture")
        fixture_sha256 = sha256_file(firmware_path)
        deployment["binary_sha256"] = fixture_sha256
        if "firmware_sha256" in deployment:
            deployment["firmware_sha256"] = fixture_sha256
        evidence_path = root / "evidence.json"
        write_json(evidence_path, evidence, checksum=True)
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
            firmware=firmware_path,
            publication_receipt=receipt_path,
        )

    def test_finalize_binds_fresh_receipt_and_closes_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            args = self.fixture(Path(directory))
            with patch("phase1_bringup.phase3_smoke.validate_evidence", return_value=0):
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
    def test_metrics_ack_legacy_shape_is_typed_rejection(self):
        legacy = {
            name: 1 for name in (
                "acknowledged", "digest_mismatch", "duplicate",
                "largest_free_block", "malformed", "max_display_flush_us",
                "max_key_poll_gap_us", "minimum_free_heap", "out_of_order",
                "parser_high_water", "queue_high_water", "received",
                "rejected", "sent", "watchdog_reset",
            )
        }
        line = (json.dumps(new_frame(
            "metrics_ack", "boot-a", "session-a", 1, legacy,
        ), sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        result = classify_line(line)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "invalid_shape")


class Phase31SecurityGuardTests(unittest.TestCase):
    def test_serial_guard_requires_inherited_exact_lock(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            lock = runtime / "herdr-keypad" / "bridge.lock"
            lock.parent.mkdir()
            fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                os.dup2(fd, 9)
                command = [
                    sys.executable,
                    "-c",
                    "from phase1_bringup.serial_link import require_inherited_bridge_lock; require_inherited_bridge_lock()",
                ]
                environment = os.environ.copy()
                environment["XDG_RUNTIME_DIR"] = str(runtime)
                environment["PYTHONPATH"] = str(ROOT / "tools/phase1_bringup/src")
                rejected = subprocess.run(
                    command, cwd=ROOT, env=environment, pass_fds=(9,),
                    capture_output=True, text=True,
                )
                self.assertNotEqual(rejected.returncode, 0)
                environment["HERDR_KEYPAD_EXCLUSIVE_LOCK"] = "1"
                accepted = subprocess.run(
                    command, cwd=ROOT, env=environment, pass_fds=(9,),
                    capture_output=True, text=True,
                )
                self.assertEqual(accepted.returncode, 0, accepted.stderr)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                os.close(9)

    def test_current_evidence_redacts_prompts_and_keeps_all_passes(self):
        evidence_path = ROOT / "artifacts/phase03.1/03.1-DEVICE-EVIDENCE.json"
        evidence = json.loads(evidence_path.read_text(encoding="ascii"))
        observations = evidence["physical_observations"]
        self.assertEqual(len(observations), 25)
        self.assertTrue(all(row["result"] == "pass" for row in observations))
        self.assertTrue(all("prompt" not in row.get("observation", {}) for row in observations))
        self.assertEqual(
            sha256_file(evidence_path),
            evidence_path.with_suffix(".json.sha256").read_text(encoding="ascii").split()[0],
        )
        ledger_path = ROOT / "artifacts/phase03.1/03.1-DEFECT-LEDGER.json"
        self.assertEqual(
            sha256_file(ledger_path),
            ledger_path.with_suffix(".json.sha256").read_text(encoding="ascii").split()[0],
        )

    def test_defect_ledger_sidecar_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_text("{}", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "sidecar is missing"):
                _phase31_sidecar(path, "defect ledger")


class Phase31DeploymentLockTests(unittest.TestCase):
    def _fake_session(self, *, device_id: str = "device-1", boot_id: str = "boot-2",
                      session_id: str = "session-2") -> tuple[object, object, object]:
        binding = SimpleNamespace(device_id="device-1", firmware="phase1-bringup", protocol=1)
        candidate = SimpleNamespace(serial_number="USB-SERIAL", device="/dev/paired")
        link = SimpleNamespace(close=lambda: None)
        session = SimpleNamespace(
            device={
                "device_id": device_id,
                "firmware": "phase1-bringup",
                "protocol": 1,
                "device_boot_id": boot_id,
            },
            session_id=session_id,
        )
        return binding, candidate, link, session

    def test_phase31_deploy_lock_binds_pair_digest_and_post_upload_identity(self):
        from phase1_bringup.phase3_smoke import (
            deployment_id_for,
            fresh_deployment,
        )
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            firmware = Path(directory) / "firmware.bin"
            firmware.write_bytes(b"new selected-usb firmware")
            binding, candidate, link, session = self._fake_session()
            with (
                patch("phase1_bringup.phase3_smoke.PairingStore") as store_type,
                patch(
                    "phase1_bringup.phase3_smoke.reconnect_exact",
                    return_value=(candidate, link, session, {}),
                ),
            ):
                store_type.return_value.load.return_value = binding
                deployment = fresh_deployment(Path(directory) / "binding.json", firmware, 0.1)
            self.assertEqual(deployment["platformio_environment"], "selected-usb")
            self.assertEqual(deployment["upload_result"], "pass")
            self.assertEqual(deployment["firmware_sha256"], sha256_file(firmware))
            self.assertEqual(deployment["boot_id"], "boot-2")
            self.assertEqual(deployment["session_id"], "session-2")
            self.assertEqual(
                deployment["deployment_id"], deployment_id_for(deployment)
            )
            self.assertEqual(len(deployment["pair_identity_digest"]), 64)

    def test_phase31_deploy_lock_rejects_wrong_pair_and_stale_binary(self):
        from phase1_bringup.phase3_smoke import (
            deployment_id_for,
            validate_deployment,
        )
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            root = Path(directory)
            firmware = root / "firmware.bin"
            firmware.write_bytes(b"selected-usb firmware")
            record = {
                "platformio_environment": "selected-usb",
                "binary_path": "artifacts/firmware.bin",
                "firmware_sha256": sha256_file(firmware),
                "binary_sha256": sha256_file(firmware),
                "upload_result": "pass",
                "paired_device_id": "device-1",
                "pair_identity_digest": "digest",
                "hello_firmware": "phase1-bringup",
                "protocol_version": 1,
                "fresh_boot_id": "boot-2",
                "fresh_session_id": "session-2",
                "boot_id": "boot-2",
                "session_id": "session-2",
                "usb_serial": "USB-SERIAL",
                "observed_at_unix_ms": 1,
            }
            record["deployment_id"] = deployment_id_for(record)
            with self.assertRaisesRegex(ValueError, "pair identity"):
                validate_deployment(record, firmware, device_id="other-device")
            firmware.write_bytes(b"stale replacement")
            with self.assertRaisesRegex(ValueError, "firmware binary hash"):
                validate_deployment(record, firmware, device_id="device-1")
class Phase31CurrentDeploymentTests(unittest.TestCase):
    def identity(self) -> tuple[dict[str, object], dict[str, object]]:
        deployment = {
            "deployment_id": "deployment-1",
            "firmware_sha256": "f" * 64,
            "paired_device_id": "device-1",
            "pair_identity_digest": "p" * 64,
            "hello_firmware": "phase1-bringup",
            "protocol_version": 1,
            "boot_id": "boot-1",
        }
        publication = {
            "binary_sha256": "f" * 64,
            "hello": {
                "device_id": "device-1",
                "firmware": "phase1-bringup",
                "protocol": 1,
                "boot_id": "boot-1",
                "session_id": "session-2",
            },
            "snapshot_ack": {
                "accepted": True,
                "snapshot_revision": 7,
            },
        }
        return deployment, publication

    def test_phase31_current_deployment_accepts_exact_hello_and_publication(self):
        deployment, publication = self.identity()
        accepted = validate_phase31_current_deployment_identity(
            deployment,
            {
                "device_id": "device-1",
                "firmware": "phase1-bringup",
                "protocol": 1,
                "device_boot_id": "boot-1",
            },
            "session-1",
            publication,
        )
        self.assertEqual(accepted["deployment_id"], "deployment-1")
        self.assertEqual(accepted["publication_snapshot_revision"], 7)

    def test_phase31_current_deployment_accepts_rotated_boot_epoch(self):
        deployment, publication = self.identity()
        hello = {
            "device_id": "device-1",
            "firmware": "phase1-bringup",
            "protocol": 1,
            "device_boot_id": "boot-rotated",
        }
        publication["hello"]["boot_id"] = "boot-rotated"
        accepted = validate_phase31_current_deployment_identity(
            deployment, hello, "session-rotated", publication
        )
        self.assertEqual(accepted["boot_id"], "boot-rotated")
        self.assertEqual(accepted["session_id"], "session-rotated")

    def test_phase31_current_deployment_rejects_wrong_device_or_hash(self):
        deployment, publication = self.identity()
        for field, value, message in (
            ("device_id", "other-device", "device identity"),
            ("firmware", "old-firmware", "firmware"),
        ):
            with self.subTest(field=field):
                hello = {
                    "device_id": "device-1",
                    "firmware": "phase1-bringup",
                    "protocol": 1,
                    "device_boot_id": "boot-1",
                }
                hello[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate_phase31_current_deployment_identity(
                        deployment, hello, "session-1", publication
                    )
        publication["binary_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "firmware hash"):
            validate_phase31_current_deployment_identity(
                deployment,
                {
                    "device_id": "device-1",
                    "firmware": "phase1-bringup",
                    "protocol": 1,
                    "device_boot_id": "boot-1",
                },
                "session-1",
                publication,
            )

    def test_phase31_reset_epoch_requires_changed_boot_and_session(self):
        previous = {
            "device_id": "device-1",
            "boot_id": "boot-1",
            "session_id": "session-1",
        }
        current = {**previous, "session_id": "session-2"}
        with self.assertRaisesRegex(ValueError, "fresh boot"):
            validate_phase31_reset_epoch(previous, current)
        current["boot_id"] = "boot-2"
        transition = validate_phase31_reset_epoch(previous, current)
        self.assertEqual(transition["to_boot_id"], "boot-2")

    def test_phase31_physical_metrics_ack_includes_full_protocol_shape(self):
        source = (ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
        required = (
            "minimum_free_heap", "largest_free_block", "max_key_poll_gap_us",
            "parser_high_water", "queue_high_water", "out_of_order", "received",
            "compose_flush_max_us", "frame_count", "allocation_stable",
        )
        for name in required:
            with self.subTest(name=name):
                self.assertIn(f'reply["{name}"]', source)
        ordered = (
            "acknowledged", "allocation_stable", "animation_duty_max_percent",
            "compose_flush_max_us", "degraded_frames", "digest_mismatch",
            "duplicate", "first_encoder_response_us", "first_press_response_us",
            "frame_count", "full_frames", "half_frames", "largest_free_block",
            "level_changes", "loop_wall_max_us", "malformed", "max_display_flush_us",
            "max_key_poll_gap_us", "minimum_free_heap", "out_of_order",
            "parser_high_water", "queue_high_water", "received", "rejected",
            "reveal_max_us", "sent", "skipped_frames", "static_frames",
            "watchdog_reset",
        )
        offsets = [source.index(f'reply["{name}"]') for name in ordered]
        self.assertEqual(offsets, sorted(offsets))

    def test_phase31_current_deployment_rejects_unacknowledged_or_wrong_publication(self):
        deployment, publication = self.identity()
        publication["snapshot_ack"]["accepted"] = False
        with self.assertRaisesRegex(ValueError, "publication"):
            validate_phase31_current_deployment_identity(
                deployment,
                {
                    "device_id": "device-1",
                    "firmware": "phase1-bringup",
                    "protocol": 1,
                    "device_boot_id": "boot-1",
                },
                "session-1",
                publication,
            )



class Phase31CaptureTests(unittest.TestCase):
    def test_phase31_capture_rejects_failed_manifest_before_strict_validation(self):
        from phase1_bringup.phase3_smoke import validate_phase31_framebuffer_manifest

        deployment = {
            "deployment_id": "deployment",
            "firmware_sha256": "firmware",
        }
        with self.assertRaisesRegex(ValueError, "status"):
            validate_phase31_framebuffer_manifest(
                {"schema_version": 1, "kind": "phase03.1-framebuffer-evidence",
                 "status": "blocked", "deployment": deployment},
                deployment,
            )

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
    def test_phase31_machine_metrics_require_complete_safe_observations(self):
        from phase1_bringup.phase3_smoke import (
            PHASE31_METRIC_FIELDS, _phase31_metrics,
            _validate_phase31_machine_metrics,
        )
        metrics = {name: 1 for name in PHASE31_METRIC_FIELDS}
        metrics["frame_count"] = 3
        metrics["full_frames"] = 1
        metrics["half_frames"] = 1
        metrics["static_frames"] = 1
        _validate_phase31_machine_metrics(_phase31_metrics(metrics))
        metrics["allocation_stable"] = 0
        with self.assertRaisesRegex(ValueError, "allocation"):
            _validate_phase31_machine_metrics(_phase31_metrics(metrics))
        metrics["allocation_stable"] = 1
        metrics["first_press_response_us"] = 120001
        with self.assertRaisesRegex(ValueError, "ceiling"):
            _validate_phase31_machine_metrics(_phase31_metrics(metrics))
        metrics["first_press_response_us"] = 1
        metrics["max_key_poll_gap_us"] = 120001
        with self.assertRaisesRegex(ValueError, "ceiling"):
            _validate_phase31_machine_metrics(_phase31_metrics(metrics))


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
        metrics["frame_count"] = 3
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


    def test_phase31_budget_lock_records_quality_failure_and_gap(self):
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
        metrics["frame_count"] = 3
        metrics["first_encoder_response_us"] = 1
        metrics["animation_duty_max_percent"] = 1
        metrics["allocation_stable"] = 1
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
                    "result": "failed" if observation_id == "smoothness" else "pass",
                    "method": "exact-device",
                }
                for observation_id in (
                    "blocked-cycle", "direct-key-response", "encoder-response",
                    "display-led-alignment", "smoothness", "brightness-power",
                )
            ],
        }
        lock = phase31_lock_from_baseline(baseline)
        self.assertEqual(lock["status"], "blocked")
        self.assertEqual(lock["baseline_quality"]["status"], "failed")
        self.assertEqual(lock["baseline_quality"]["failed_observation_ids"], ["smoothness"])
        self.assertFalse(lock["baseline_quality"]["resource_failures"])
        self.assertEqual(lock["limits"]["press_response_us"], 120000)
        self.assertEqual(lock["resource_headroom"]["target_period_us"], 33334)
    def test_phase31_budget_lock_rejects_invalid_machine_metrics(self):
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
        metrics["frame_count"] = 3
        observations = [
            {"id": observation_id, "result": "pass", "method": "exact-device"}
            for observation_id in (
                "blocked-cycle", "direct-key-response", "encoder-response",
                "display-led-alignment", "smoothness", "brightness-power",
            )
        ]
        baseline = {
            "schema_version": 1,
            "kind": "phase03.1-baseline-profile",
            "deployment": {"deployment_id": "deployment"},
            "metrics": metrics,
            "measurement_window": {"started_unix_ms": 1, "ended_unix_ms": 2},
            "samples": [{"id": "sample", "metrics": metrics}],
            "observations": observations,
        }
        invalid = (
            ("frame_count", 1, "reconcile"),
            ("max_key_poll_gap_us", 0, "zero"),
            ("allocation_stable", 0, "allocation"),
            ("max_key_poll_gap_us", 120001, "ceiling"),
        )
        for field, value, message in invalid:
            with self.subTest(field=field, value=value):
                candidate = dict(baseline)
                candidate["metrics"] = dict(metrics)
                candidate["metrics"][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    phase31_lock_from_baseline(candidate)


class Phase32DeploymentLockTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object], Path]:
        decision = json.loads(
            (ROOT / "artifacts/phase03.2/composite-decision.json").read_text(
                encoding="ascii"
            )
        )
        manifest = json.loads(
            (ROOT / "artifacts/phase03.2/composite-manifest.json").read_text(
                encoding="ascii"
            )
        )
        firmware = root / "firmware.bin"
        firmware.write_bytes(b"phase32 selected-usb fixture")
        source_paths = [ROOT / "platformio.ini", ROOT / "firmware/src/main.cpp"]
        source_files = [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)}
            for path in source_paths
        ]
        descriptor = phase32_descriptor_tuple()
        deployment: dict[str, object] = {
            "schema_version": 1,
            "kind": "phase03.2-final-deployment",
            "phase": "03.2",
            "platformio_environment": "selected-usb",
            "binary_path": str(firmware.relative_to(ROOT)),
            "binary_sha256": sha256_file(firmware),
            "firmware_sha256": sha256_file(firmware),
            "source_files": source_files,
            "source_sha256": phase32_source_digest(source_paths),
            "upload_result": "pass",
            "paired_device_id": "0000fccb0deabf8c",
            "pair_digest": decision["deployment"]["pair_digest"],
            "pair_identity_digest": decision["deployment"]["pair_digest"],
            "pairing_record_sha256": decision["deployment"]["pairing_record_sha256"],
            "hello_firmware": "phase1-bringup",
            "protocol_version": 1,
            "fresh_boot_id": "phase32-boot-2",
            "fresh_session_id": "phase32-session-2",
            "boot_id": "phase32-boot-2",
            "session_id": "phase32-session-2",
            "observed_at_unix_ms": 2,
            "decision_sha256": decision["decision_sha256"],
            "decision_manifest_sha256": decision["manifest_sha256"],
            "composite_firmware_sha256": decision["deployment"]["firmware_binary_sha256"],
            "descriptor_expectation_sha256": decision["deployment"]["descriptor_expectation_sha256"],
            "descriptor_tuple": descriptor,
            "descriptor_tuple_sha256": phase32_descriptor_tuple_sha256(descriptor),
        }
        deployment["deployment_id"] = phase32_deployment_id_for(deployment)
        return deployment, decision, manifest, firmware

    def test_phase32_lineage_reopens_terminal_pass_and_descriptor_tuple(self):
        binding_path = Path.home() / ".config/herdr/keypad-binding.json"
        lineage = validate_phase32_composite_lineage(
            ROOT / "artifacts/phase03.2/composite-decision.json",
            binding_path,
        )
        self.assertEqual(lineage["decision"]["status"], "PASS")
        self.assertEqual(lineage["descriptor"]["cdc_control_interface"], 1)
        self.assertEqual(lineage["descriptor"]["cdc_data_interface"], 2)

    def test_phase32_deployment_rejects_every_stale_lineage_fact(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            deployment, decision, manifest, firmware = self._fixture(Path(directory))
            binding = SimpleNamespace(
                device_id="0000fccb0deabf8c", firmware="phase1-bringup", protocol=1
            )
            cases = (
                ("pair", "pair_digest", "0" * 64, "pair digest"),
                ("descriptor", "descriptor_tuple_sha256", "0" * 64, "descriptor tuple"),
                ("decision", "decision_sha256", "0" * 64, "decision"),
                ("source", "source_sha256", "0" * 64, "source"),
                ("firmware", "hello_firmware", "old-firmware", "firmware"),
                ("protocol", "protocol_version", 2, "protocol"),
            )
            for name, field, value, message in cases:
                with self.subTest(name=name):
                    candidate = dict(deployment)
                    candidate[field] = value
                    with self.assertRaisesRegex(ValueError, message):
                        validate_phase32_deployment(
                            candidate, firmware, decision, manifest, binding
                        )
            previous = dict(deployment)
            with self.assertRaisesRegex(ValueError, "fresh boot"):
                validate_phase32_deployment(
                    deployment, firmware, decision, manifest, binding, previous=previous
                )
            previous["boot_id"] = "phase32-boot-old"
            with self.assertRaisesRegex(ValueError, "fresh session"):
                validate_phase32_deployment(
                    deployment, firmware, decision, manifest, binding, previous=previous
                )

    def test_phase32_deployment_file_reopens_sidecar_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            root = Path(directory)
            deployment, _decision, _manifest, firmware = self._fixture(root)
            deployment_path = root / "deployment.json"
            write_json(deployment_path, deployment, checksum=True)
            reopened = validate_phase32_deployment_file(
                deployment_path,
                firmware=firmware,
                decision_path=ROOT / "artifacts/phase03.2/composite-decision.json",
                binding_path=Path.home() / ".config/herdr/keypad-binding.json",
            )
            self.assertEqual(reopened["deployment_id"], deployment["deployment_id"])
            deployment_path.write_text(
                deployment_path.read_text(encoding="ascii").replace(
                    "phase32-session-2", "tampered-session"
                ),
                encoding="ascii",
            )
            with self.assertRaisesRegex(ValueError, "checksum"):
                validate_phase32_deployment_file(
                    deployment_path,
                    firmware=firmware,
                    decision_path=ROOT / "artifacts/phase03.2/composite-decision.json",
                    binding_path=Path.home() / ".config/herdr/keypad-binding.json",
                )
if __name__ == "__main__":
    unittest.main()
