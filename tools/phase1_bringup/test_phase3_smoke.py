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
    FINAL_EDGE_ASSUMPTIONS,
    HUMAN_ROWS,
    PHASE32_DEVICE_ROW_IDS,
    PHASE32_MACHINE_ROW_FOR_DEVICE,
    PHASE32_OPERATOR_PROMPTS,
    ROOT,
    _phase31_sidecar,
    _phase32_checkpoint_template,
    _phase32_load_checkpoint,
    _phase32_capture_input_until,
    _phase32_capture_lifecycle_until,
    _phase32_stop_observer,
    _Phase32DeviceRemoved,
    _Phase32ObserverCapture,
    _phase32_save_checkpoint,
    _phase32_row_hash,
    PHASE32_FAILURE_EVENTS,
    PHASE32_HOLD_SCENES,
    PHASE32_LED_EVENTS,
    PHASE32_SOURCE_EVENTS,
    phase32_descriptor_tuple,
    phase32_descriptor_tuple_sha256,
    phase32_led_rows,
    phase32_source_digest,
    phase32_deployment_id_for,
    validate_phase31_current_deployment_identity,
    validate_phase31_reset_epoch,
    validate_phase32_composite_lineage,
    validate_phase32_deployment,
    validate_phase32_deployment_file,
    validate_phase32_device_evidence,
    validate_phase32_defect_ledger,
    validate_phase32_gate,
    validate_phase32_led_rows,
    build_final_qualification,
    run_guided,
    finalize_evidence,
    sha256_file,
    write_json,
    write_phase32_final_artifacts,
)
import phase1_bringup.phase3_smoke as phase3_smoke
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

class Phase32LogicalEvidenceTests(unittest.TestCase):
    deployment_id = "phase32-deployment"
    firmware_sha256 = "f" * 64
    deployment_lock_sha256 = "d" * 64

    def test_phase32_led_rows_cover_all_grammars_and_closed_semantics(self):
        rows = phase32_led_rows(
            self.deployment_id,
            self.firmware_sha256,
            self.deployment_lock_sha256,
        )
        self.assertEqual(
            len(rows),
            4 * len(PHASE32_LED_EVENTS),
        )
        self.assertEqual(
            {row["grammar"] for row in rows},
            {"rail-echo", "exception", "field-extension", "meter-lamps"},
        )
        self.assertEqual(
            {row["event"] for row in rows},
            set(PHASE32_LED_EVENTS),
        )
        validate_phase32_led_rows(
            rows,
            self.deployment_id,
            self.firmware_sha256,
            self.deployment_lock_sha256,
        )
        for row in rows:
            self.assertEqual(len(row["content_sha256"]), 64)
            self.assertFalse(row["physical_claim"])

    def test_phase32_led_rows_reject_stale_owner_and_physical_claims(self):
        rows = phase32_led_rows(
            self.deployment_id,
            self.firmware_sha256,
            self.deployment_lock_sha256,
        )
        mutations = (
            ("owner-after-other-focus", {"owner_slot": None}, "owner"),
            ("rejected", {"active_owner": True}, "failure"),
            ("source-offline", {"active_owner": True}, "source"),
            ("lifecycle-clear", {"active_owner": True}, "lifecycle"),
            ("pending", {"deployment_id": "stale"}, "deployment"),
            ("active-owner", {"physical_claim": True}, "physical"),
        )
        for event, changes, message in mutations:
            with self.subTest(event=event):
                candidate = [dict(row) for row in rows]
                target = next(row for row in candidate if row["event"] == event)
                target.update(changes)
                target["content_sha256"] = _phase32_row_hash(target)
                with self.assertRaisesRegex(ValueError, message):
                    validate_phase32_led_rows(
                        candidate,
                        self.deployment_id,
                        self.firmware_sha256,
                        self.deployment_lock_sha256,
                    )
        missing = rows[:-1]
        with self.assertRaisesRegex(ValueError, "matrix"):
            validate_phase32_led_rows(
                missing,
                self.deployment_id,
                self.firmware_sha256,
                self.deployment_lock_sha256,
            )

    def test_phase32_scene_constants_keep_all_theme_levels_and_failure_fences(self):
        self.assertEqual(
            PHASE32_HOLD_SCENES,
            (
                "hold-pending",
                "space-active-owner",
                "cancellation-return",
                "owner-after-other-focus",
                "failure-preemption",
                "lifecycle-clear",
            ),
        )
        self.assertIn("timeout", PHASE32_FAILURE_EVENTS)
        self.assertEqual(
            PHASE32_SOURCE_EVENTS,
            ("source-stale", "source-offline", "source-unavailable"),
        )
class Phase32QualificationRunnerTests(unittest.TestCase):
    def test_phase32_human_prompt_is_capped_and_stress_is_not_manual(self) -> None:
        self.assertEqual(len(PHASE32_OPERATOR_PROMPTS), 3)
        threshold_prompt = PHASE32_OPERATOR_PROMPTS[0][1]
        self.assertIn("24 gestures total", threshold_prompt)
        self.assertNotIn("180", threshold_prompt)
        self.assertNotIn("300", threshold_prompt)
        self.assertIn("all four themes", PHASE32_OPERATOR_PROMPTS[1][1])
        self.assertIn("unplug/replug", PHASE32_OPERATOR_PROMPTS[2][1])
        self.assertIn("never touches live Herdr", PHASE32_OPERATOR_PROMPTS[1][1])
    def test_phase32_evdev_observer_grabs_keyboard_without_leaking_space_to_prompt(self) -> None:
        class Selector:
            def register(self, _fd: int, _mask: int) -> None:
                return None

            def select(self, _timeout: float) -> list[object]:
                stop.set()
                return []

            def close(self) -> None:
                return None

        stop = __import__("threading").Event()
        stop.set()
        with (
            patch("phase1_bringup.phase3_smoke.os.open", return_value=7),
            patch("phase1_bringup.phase3_smoke.os.close"),
            patch("phase1_bringup.phase3_smoke.fcntl.ioctl") as ioctl,
            patch("phase1_bringup.phase3_smoke.selectors.DefaultSelector", return_value=Selector()),
        ):
            self.assertEqual(
                _phase32_capture_input_until(Path("/dev/input/event-test"), stop),
                [],
            )
        self.assertEqual(
            ioctl.call_args_list,
            [
                ((7, phase3_smoke._EVIOCGRAB, 1), {}),
                ((7, phase3_smoke._EVIOCGRAB, 0), {}),
            ],
        )
    def test_phase32_fixture_controller_keeps_snapshot_and_exact_focus_round_trip_live(self) -> None:
        completed = __import__("threading").Event()

        class FakeUsb:
            pending_focus_capacity = 16

            def __init__(self) -> None:
                self.closed = True
                self.session_id = "qualification-session"
                self.candidate = SimpleNamespace(serial_number="SERIAL")
                self.device = {}
                self.snapshot: dict[str, object] | None = None
                self.frames: list[dict[str, object]] = []
                self.results: list[dict[str, object]] = []

            @property
            def connected(self) -> bool:
                return not self.closed

            def connect(self) -> dict[str, object]:
                self.closed = False
                self.device = {
                    "hello": {
                        "device_id": "paired-device",
                        "firmware": "production",
                        "protocol": 1,
                        "boot_id": "boot-1",
                        "session_id": self.session_id,
                    },
                    "transitions": [],
                }
                return self.device

            def request_metrics(self, *, reset: bool) -> dict[str, object]:
                self.assert_open()
                if not reset:
                    raise AssertionError("qualification metrics must reset at initial admission")
                return {"accepted": True}

            def publish_snapshot(self, payload: dict[str, object]) -> dict[str, object]:
                self.assert_open()
                self.snapshot = payload
                agents = payload["agents"]
                assert isinstance(agents, list)
                exact_payloads = [
                    {
                        "action_id": f"exact-action-{index}",
                        "host_epoch": payload["host_epoch"],
                        "snapshot_revision": payload["snapshot_revision"],
                        "slot": agent["slot"],
                        "entry_id": agent["entry_id"],
                        "pane_id": agent["pane_id"],
                        "terminal_id": agent["terminal_id"],
                        "agent_session": agent["agent_session"],
                        "source_revision": agent["source_revision"],
                    }
                    for index, agent in enumerate(agents, 1)
                ]
                stale = dict(
                    exact_payloads[0],
                    action_id="stale-action",
                    entry_id="wrong-entry",
                )
                self.frames = [
                    {
                        "type": "focus_intent",
                        "session_id": self.session_id,
                        "payload": focus_payload,
                    }
                    for focus_payload in (*exact_payloads, stale)
                ]
                return {
                    "accepted": True,
                    "host_epoch": payload["host_epoch"],
                    "snapshot_revision": payload["snapshot_revision"],
                }

            def poll(self) -> dict[str, object] | None:
                self.assert_open()
                return self.frames.pop(0) if self.frames else None

            def send_focus_result(self, payload: dict[str, object]) -> None:
                self.assert_open()
                self.results.append(payload)
                if len(self.results) == 4:
                    completed.set()

            def assert_open(self) -> None:
                if self.closed:
                    raise AssertionError("fixture controller closed its exact USB session")

            def close(self) -> None:
                self.closed = True

        fake_usb = FakeUsb()
        args = SimpleNamespace(
            binding=Path("/qualification/binding.json"),
            run_id="controller-regression",
            timeout=0.1,
        )
        with patch("herdr_keypad.usb.UsbDeviceSession", return_value=fake_usb):
            with phase3_smoke.phase32_live_bridge(args) as controller:
                self.assertTrue(completed.wait(1.0))
                controller.assert_batch("presentation")
                self.assertFalse(controller.evidence()["live_herdr_connected"])
                controller.assert_running()
                self.assertIsNotNone(fake_usb.snapshot)
                assert fake_usb.snapshot is not None
                self.assertEqual(len(fake_usb.snapshot["agents"]), 3)
                self.assertEqual(
                    [(result["action_id"], result["outcome"], result["focused"]) for result in fake_usb.results],
                    [
                        ("exact-action-1", "accepted", True),
                        ("exact-action-2", "accepted", True),
                        ("exact-action-3", "accepted", True),
                        ("stale-action", "stale_target", False),
                    ],
                )
                accepted = fake_usb.results[0]
                first = fake_usb.snapshot["agents"][0]
                self.assertEqual(accepted["host_epoch"], fake_usb.snapshot["host_epoch"])
                self.assertEqual(accepted["snapshot_revision"], fake_usb.snapshot["snapshot_revision"])
                self.assertEqual(accepted["entry_id"], first["entry_id"])
            self.assertTrue(fake_usb.closed)
    def test_phase32_measured_evidence_fails_closed_without_runtime_context(self) -> None:
        controller = object.__new__(phase3_smoke._Phase32FixtureController)
        with self.assertRaisesRegex(RuntimeError, "runtime context"):
            controller.measured_evidence()

    def test_phase32_fixture_controller_reconnects_exact_and_republishes_snapshot(self) -> None:
        from herdr_keypad.usb import UsbSessionError

        republished = __import__("threading").Event()

        class ReconnectingUsb:
            def __init__(self) -> None:
                self.closed = True
                self.connect_count = 0
                self.disconnected_once = False
                self.session_id: str | None = None
                self.candidate = SimpleNamespace(serial_number="SERIAL")
                self.snapshots: list[tuple[str, int]] = []

            @property
            def connected(self) -> bool:
                return not self.closed

            def connect(self) -> dict[str, object]:
                self.connect_count += 1
                self.closed = False
                self.session_id = f"session-{self.connect_count}"
                return {
                    "hello": {
                        "device_id": "paired-device",
                        "firmware": "production",
                        "protocol": 1,
                        "boot_id": f"boot-{self.connect_count}",
                        "session_id": self.session_id,
                    },
                    "transitions": [],
                }

            def request_metrics(self, *, reset: bool) -> dict[str, object]:
                if not reset:
                    raise AssertionError("initial qualification metrics were not reset")
                return {"accepted": True}

            def publish_snapshot(self, payload: dict[str, object]) -> dict[str, object]:
                identity = (payload["host_epoch"], payload["snapshot_revision"])
                self.snapshots.append(identity)
                if len(self.snapshots) == 2:
                    republished.set()
                return {
                    "accepted": True,
                    "host_epoch": identity[0],
                    "snapshot_revision": identity[1],
                }

            def poll(self) -> None:
                if not self.disconnected_once:
                    self.disconnected_once = True
                    raise UsbSessionError("io", "simulated exact-device disconnect")
                return None

            def send_focus_result(self, _payload: dict[str, object]) -> None:
                raise AssertionError("no focus frame was scheduled in reconnect test")

            def close(self) -> None:
                self.closed = True
                self.session_id = None

        fake_usb = ReconnectingUsb()
        args = SimpleNamespace(
            binding=Path("/qualification/binding.json"),
            run_id="controller-reconnect",
            timeout=0.1,
        )
        with patch("herdr_keypad.usb.UsbDeviceSession", return_value=fake_usb):
            with phase3_smoke.phase32_live_bridge(args) as controller:
                self.assertTrue(republished.wait(1.0))
                controller.assert_running()
                self.assertEqual(fake_usb.connect_count, 2)
                self.assertEqual(fake_usb.snapshots[0], fake_usb.snapshots[1])
            self.assertTrue(fake_usb.closed)


    def test_phase32_qualification_keeps_fixture_controller_live_through_every_prompt(self) -> None:
        class FakeUsb:
            def __init__(self) -> None:
                self.closed = True
                self.device = {
                    "hello": {
                        "device_id": "paired-device",
                        "firmware": "production",
                        "protocol": 1,
                        "boot_id": "boot-1",
                        "session_id": "session-1",
                    },
                    "transitions": [],
                }
                self.candidate = SimpleNamespace(serial_number="SERIAL")

            def connect(self) -> dict[str, object]:
                self.closed = False
                return self.device

            def request_metrics(self, *, reset: bool) -> dict[str, object]:
                self.assert_open()
                if not reset:
                    raise AssertionError("qualification metrics reset was not requested")
                return {"accepted": True}

            def assert_open(self) -> None:
                if self.closed:
                    raise AssertionError("qualification closed the CDC controller before prompts")

            def close(self) -> None:
                self.closed = True

        class FakeController:
            def __init__(self) -> None:
                self.usb = FakeUsb()
                self.hello = self.usb.device
                self.device_metrics = {"accepted": True}
                self.serial_number = "SERIAL"
                self.active = False
                self.health_checks = 0
                self.batches: list[str] = []

            def start(self) -> "FakeController":
                self.usb.connect()
                self.active = True
                return self

            def close(self) -> None:
                self.active = False
                self.usb.close()

            def __enter__(self) -> "FakeController":
                return self.start()

            def __exit__(self, *_args: object) -> None:
                self.close()

            def assert_running(self) -> None:
                if not self.active:
                    raise AssertionError("qualification focus/snapshot controller is not active")
                self.usb.assert_open()
                self.health_checks += 1
            def assert_batch(self, step_id: str) -> None:
                self.assert_running()
                self.batches.append(step_id)
            def connection_marker(self) -> tuple[int, dict[str, str]]:
                return 1, {"boot_id": "boot-1", "session_id": "session-1"}

            def wait_for_connection(
                self, marker: int, timeout: float
            ) -> tuple[int, dict[str, str]]:
                raise AssertionError(
                    f"patched lifecycle observer unexpectedly waited after {marker=} {timeout=}"
                )


            def evidence(self) -> dict[str, object]:
                return {
                    "mode": "controlled-fixture",
                    "live_herdr_connected": False,
                    "accepted_focus_slots": [0, 1, 2],
                }
            def measured_evidence(self, **_context: object) -> dict[str, object]:
                return {}

        deployment = {
            "deployment_id": "phase32-controller",
            "firmware_sha256": "f" * 64,
            "descriptor_tuple": {"vid": 0x303A, "pid": 0x1001},
        }
        logical = {
            "status": "pass",
            "deployment_id": deployment["deployment_id"],
            "firmware_sha256": deployment["firmware_sha256"],
            "deployment_lock_sha256": "a" * 64,
        }
        controller = FakeController()
        prompt_states: list[tuple[bool, bool]] = []

        def answer(_prompt: str) -> str:
            prompt_states.append((controller.active, controller.usb.closed))
            controller.assert_running()
            return "Y"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(
                binding=root / "binding.json",
                decision=root / "decision.json",
                firmware=root / "firmware.bin",
                deployment=root / "deployment.json",
                logical_evidence=root / "logical.json",
                output_root=root / "output",
                run_id="controller-regression",
                checkpoint=root / "checkpoint.json",
                timeout=0.1,
            )
            with (
                patch("phase1_bringup.phase3_smoke.require_inherited_bridge_lock"),
                patch(
                    "phase1_bringup.phase3_smoke.validate_phase32_deployment_file",
                    return_value=deployment,
                ),
                patch(
                    "phase1_bringup.phase3_smoke.validate_phase32_framebuffer_evidence_file",
                    return_value=logical,
                ),
                patch("phase1_bringup.phase3_smoke._phase31_sidecar", return_value="a" * 64),
                patch("phase1_bringup.phase3_smoke._phase32_run_automated_preflight", return_value=[]),
                patch(
                    "phase1_bringup.phase3_smoke.phase32_live_bridge",
                    return_value=controller,
                    create=True,
                ),
                patch("herdr_keypad.usb.UsbDeviceSession", return_value=controller.usb),
                patch(
                    "phase1_bringup.composite_qualification._find_guided_keyboard_event",
                    return_value=root / "event0",
                ),
                patch(
                    "phase1_bringup.phase3_smoke._phase32_start_observer",
                    return_value=(object(), object(), object()),
                ),
                patch(
                    "phase1_bringup.phase3_smoke._phase32_start_lifecycle_observer",
                    return_value=(object(), object(), object()),
                ),
                patch(
                    "phase1_bringup.phase3_smoke._phase32_stop_observer",
                    return_value={
                        "interval_id": "test",
                        "complete": True,
                        "events": [{"type": "EV_KEY", "value": 0}],
                    },
                ),
                patch("phase1_bringup.phase3_smoke.validate_input_trace", return_value={"state": "UP"}),
                patch("phase1_bringup.phase3_smoke.build_final_qualification", return_value={}),
                patch(
                    "phase1_bringup.phase3_smoke.write_phase32_final_artifacts",
                    return_value={"qualification_sha256": "b" * 64, "gate_sha256": "c" * 64},
                ),
                patch("builtins.input", side_effect=answer),
            ):
                self.assertEqual(phase3_smoke.run_phase32_qualification(args), 0)

        self.assertEqual(prompt_states, [(True, False)] * len(PHASE32_OPERATOR_PROMPTS))
        self.assertGreaterEqual(controller.health_checks, len(PHASE32_OPERATOR_PROMPTS))
        self.assertEqual(controller.batches, [step_id for step_id, _prompt in PHASE32_OPERATOR_PROMPTS])
        self.assertFalse(controller.active)
        self.assertTrue(controller.usb.closed)

    def test_phase32_checkpoint_round_trip_preserves_only_completed_batches(self) -> None:
        deployment = {
            "deployment_id": "phase32-checkpoint",
            "firmware_sha256": "f" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qualification-checkpoint.json"
            checkpoint = _phase32_checkpoint_template("run-checkpoint", deployment, "a" * 64)
            checkpoint["completed_steps"] = ["threshold-calibration"]
            checkpoint["observations"] = {
                row_id: {
                    "answer": "Y",
                    "prompt": "operator observed",
                    "observed_at_unix_ms": 123,
                }
                for row_id in ("D-01", "D-02", "D-03", "D-04", "D-05")
            }
            checkpoint["input_events"] = [
                {
                    "type": "EV_KEY",
                    "code": "KEY_SPACE",
                    "value": 0,
                    "monotonic_ns": 1,
                }
            ]
            checkpoint["input_intervals"] = [
                {
                    "interval_id": "threshold-calibration",
                    "complete": True,
                    "events": [{"type": "EV_KEY", "value": 0}],
                }
            ]
            _phase32_save_checkpoint(path, checkpoint)
            resumed = _phase32_load_checkpoint(
                path,
                "run-checkpoint",
                deployment,
                "a" * 64,
            )

        self.assertEqual(resumed["completed_steps"], ["threshold-calibration"])
        self.assertEqual(resumed["observations"]["D-01"]["answer"], "Y")
        self.assertEqual(resumed["input_events"][0]["value"], 0)

    def test_phase32_checkpoint_rejects_completed_batch_without_observations(self) -> None:
        deployment = {
            "deployment_id": "phase32-checkpoint",
            "firmware_sha256": "f" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qualification-checkpoint.json"
            checkpoint = _phase32_checkpoint_template("run-checkpoint", deployment, "a" * 64)
            checkpoint["completed_steps"] = ["threshold-calibration"]
            _phase32_save_checkpoint(path, checkpoint)
            with self.assertRaisesRegex(RuntimeError, "physical observations"):
                _phase32_load_checkpoint(
                    path,
                    "run-checkpoint",
                    deployment,
                    "a" * 64,
                )

    def test_phase32_evdev_observer_fails_closed_on_error_timeout_or_empty_capture(self) -> None:
        observer = SimpleNamespace(join=lambda timeout: None, is_alive=lambda: False)
        failed = _Phase32ObserverCapture("presentation", 1)
        failed.error = OSError("read failed")
        failed.complete = False
        with self.assertRaisesRegex(RuntimeError, "failed"):
            _phase32_stop_observer(SimpleNamespace(set=lambda: None), observer, failed)

        timed_out = _Phase32ObserverCapture("lifecycle", 1)
        timed_out.complete = True
        timed_out.events = [{"type": "EV_KEY", "value": 0}]
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            _phase32_stop_observer(
                SimpleNamespace(set=lambda: None),
                SimpleNamespace(join=lambda timeout: None, is_alive=lambda: True),
                timed_out,
            )

        empty = _Phase32ObserverCapture("threshold-calibration", 1)
        empty.complete = True
        empty.ended_monotonic_ns = 2
        with self.assertRaisesRegex(RuntimeError, "no required transition"):
            _phase32_stop_observer(SimpleNamespace(set=lambda: None), observer, empty)

    def test_phase32_lifecycle_observer_requires_exact_return_fresh_boot_and_final_up(self) -> None:
        observer = SimpleNamespace(join=lambda timeout: None, is_alive=lambda: False)
        stop = SimpleNamespace(set=lambda: None)
        incomplete = _Phase32ObserverCapture("lifecycle", 1)
        incomplete.complete = True
        incomplete.ended_monotonic_ns = 2
        incomplete.initial_boot_id = "boot-1"
        incomplete.initial_session_id = "session-1"
        incomplete.events = [{"type": "EV_KEY", "code": "KEY_SPACE", "value": 0}]
        with self.assertRaisesRegex(RuntimeError, "replacement"):
            _phase32_stop_observer(stop, observer, incomplete)

        stale = _Phase32ObserverCapture("lifecycle", 1)
        stale.complete = True
        stale.ended_monotonic_ns = 2
        stale.initial_boot_id = "boot-1"
        stale.initial_session_id = "session-1"
        stale.events = [
            {"type": "DEVICE_REMOVED", "verified": True, "monotonic_ns": 2},
            {
                "type": "REMOUNT",
                "verified": True,
                "empty": True,
                "boot_id": "boot-1",
                "session_id": "session-2",
                "monotonic_ns": 3,
            },
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 0, "monotonic_ns": 4},
        ]
        with self.assertRaisesRegex(RuntimeError, "fresh boot"):
            _phase32_stop_observer(stop, observer, stale)

        stuck = _Phase32ObserverCapture("lifecycle", 1)
        stuck.complete = True
        stuck.ended_monotonic_ns = 2
        stuck.initial_boot_id = "boot-1"
        stuck.initial_session_id = "session-1"
        stuck.events = [
            {"type": "DEVICE_REMOVED", "verified": True, "monotonic_ns": 2},
            {
                "type": "REMOUNT",
                "verified": True,
                "empty": False,
                "boot_id": "boot-2",
                "session_id": "session-2",
                "monotonic_ns": 3,
            },
        ]
        with self.assertRaisesRegex(RuntimeError, "KEY_SPACE UP"):
            _phase32_stop_observer(stop, observer, stuck)
    def test_phase32_lifecycle_observer_continues_on_exact_replacement_node(self) -> None:
        stop = __import__("threading").Event()
        old_path = Path("/dev/input/event12")
        new_path = Path("/dev/input/event19")

        def capture(
            event_path: Path,
            _stop: object,
            *,
            on_ready: object = None,
        ) -> list[dict[str, object]]:
            if event_path == old_path:
                raise _Phase32DeviceRemoved([
                    {
                        "type": "EV_KEY",
                        "code": "KEY_SPACE",
                        "value": 1,
                        "monotonic_ns": 1,
                    }
                ])
            self.assertEqual(event_path, new_path)
            self.assertIsNotNone(on_ready)
            on_ready(7)
            stop.set()
            return [
                {
                    "type": "EV_KEY",
                    "code": "KEY_SPACE",
                    "value": 0,
                    "monotonic_ns": 4,
                }
            ]

        with (
            patch(
                "phase1_bringup.phase3_smoke._phase32_capture_input_until",
                side_effect=capture,
            ),
            patch(
                "phase1_bringup.phase3_smoke._phase32_space_is_up",
                return_value=True,
            ),
            patch(
                "phase1_bringup.composite_qualification._find_guided_keyboard_event",
                return_value=new_path,
            ) as discover,
        ):
            events = _phase32_capture_lifecycle_until(
                old_path,
                stop,
                vid_pid="303a:1001",
                serial_number="8C:BF:EA:0D:CB:FC",
                connection_marker=1,
                wait_for_connection=lambda marker, _timeout: (
                    marker + 1,
                    {"boot_id": "boot-2", "session_id": "session-2"},
                ),
                timeout=1.0,
            )

        self.assertEqual(
            [event["type"] for event in events],
            ["EV_KEY", "DEVICE_REMOVED", "REMOUNT", "EV_KEY"],
        )
        remount = events[2]
        self.assertEqual(remount["event_path"], str(new_path))
        self.assertEqual(remount["boot_id"], "boot-2")
        self.assertEqual(remount["session_id"], "session-2")
        self.assertTrue(remount["empty"])
        discover.assert_called_once_with(
            "303a:1001",
            "8C:BF:EA:0D:CB:FC",
            timeout=1.0,
            require_serial=True,
        )


    def test_phase32_non_lifecycle_observer_rejects_node_replacement(self) -> None:
        observer = SimpleNamespace(join=lambda timeout: None, is_alive=lambda: False)
        captured = _Phase32ObserverCapture("presentation", 1)
        captured.complete = True
        captured.ended_monotonic_ns = 2
        captured.events = [
            {"type": "DEVICE_REMOVED", "verified": True, "monotonic_ns": 2},
            {"type": "REMOUNT", "verified": True, "empty": True, "monotonic_ns": 3},
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 0, "monotonic_ns": 4},
        ]
        with self.assertRaisesRegex(RuntimeError, "replaced"):
            _phase32_stop_observer(
                SimpleNamespace(set=lambda: None), observer, captured
            )

class Phase32PhysicalGateTests(unittest.TestCase):
    @staticmethod
    def _deployment() -> dict[str, object]:
        return {
            "deployment_id": "phase32-final",
            "firmware_sha256": "f" * 64,
            "deployment_lock_sha256": "a" * 64,
        }
    @classmethod
    def _qualification(cls) -> dict[str, object]:
        rows = [
            {
                "id": row_id,
                "applicable": True,
                "required_count": 1,
                "observed_count": 1,
                "status": "pass",
            }
            for row_id in sorted(set(PHASE32_MACHINE_ROW_FOR_DEVICE.values()))
        ]
        return {"status": "pass", "rows": rows}

    @classmethod
    def _evidence(cls) -> dict[str, object]:
        deployment = cls._deployment()
        qualification = cls._qualification()
        qualification_rows = {
            row["id"]: row for row in qualification["rows"]
        }
        return {
            "schema_version": 1,
            "kind": "phase03.2-device-evidence",
            "status": "pass",
            "deployment_id": deployment["deployment_id"],
            "firmware_sha256": deployment["firmware_sha256"],
            "deployment_lock_sha256": deployment["deployment_lock_sha256"],
            "qualification_sha256": "b" * 64,
            "threshold_ms": 550,
            "edge_assumptions": [dict(item) for item in FINAL_EDGE_ASSUMPTIONS],
            "rows": [
                {
                    "id": row_id,
                    "source": "physical-observation",
                    "machine_invariant": {
                        "row_id": machine_id,
                        "row_sha256": _phase32_row_hash(qualification_rows[machine_id]),
                    },
                    "result": "pass",
                    "observation": {
                        "kind": "typed",
                        "result": "pass",
                        "value": {"answer": "Y"},
                    },
                    "physical_claim": True,
                }
                for row_id in PHASE32_DEVICE_ROW_IDS
                for machine_id in (PHASE32_MACHINE_ROW_FOR_DEVICE[row_id],)
            ],
            "oracle_state": "UP",
        }

    def test_phase32_device_evidence_is_typed_and_deployment_bound(self) -> None:
        deployment = self._deployment()
        evidence = validate_phase32_device_evidence(
            self._evidence(),
            deployment,
            self._qualification(),
            deployment_lock_sha256=deployment["deployment_lock_sha256"],
            qualification_sha256="b" * 64,
        )
        self.assertEqual(evidence["status"], "pass")
        candidate = self._evidence()
        candidate["rows"][0]["source"] = "machine"
        with self.assertRaisesRegex(ValueError, "physical"):
            validate_phase32_device_evidence(
                candidate,
                deployment,
                self._qualification(),
                deployment_lock_sha256=deployment["deployment_lock_sha256"],
                qualification_sha256="b" * 64,
            )
        candidate = self._evidence()
        candidate["rows"][0]["machine_invariant"]["row_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "machine invariant"):
            validate_phase32_device_evidence(
                candidate,
                deployment,
                self._qualification(),
                deployment_lock_sha256=deployment["deployment_lock_sha256"],
                qualification_sha256="b" * 64,
            )

    def test_phase32_defect_ledger_and_gate_reject_open_oracle(self) -> None:
        deployment = self._deployment()
        ledger = {
            "schema_version": 1,
            "kind": "phase03.2-defect-ledger",
            "status": "pass",
            "deployment_id": deployment["deployment_id"],
            "deployment_lock_sha256": deployment["deployment_lock_sha256"],
            "qualification_sha256": "b" * 64,
            "device_evidence_sha256": "e" * 64,
            "defects": [],
            "history": [],
        }
        self.assertEqual(
            validate_phase32_defect_ledger(
                ledger,
                deployment,
                deployment_lock_sha256=deployment["deployment_lock_sha256"],
                qualification_sha256="b" * 64,
                device_evidence_sha256="e" * 64,
            )["defects"],
            [],
        )
        ledger["defects"] = [{"id": "D-FAIL", "status": "open"}]
        with self.assertRaisesRegex(ValueError, "defect"):
            validate_phase32_defect_ledger(
                ledger,
                deployment,
                deployment_lock_sha256=deployment["deployment_lock_sha256"],
                qualification_sha256="b" * 64,
                device_evidence_sha256="e" * 64,
            )
        gate = {
            "schema_version": 1,
            "kind": "phase03.2-phase4-gate",
            "status": "fail",
            "deployment_id": deployment["deployment_id"],
            "oracle_state": "DOWN",
        }
        with self.assertRaisesRegex(ValueError, "gate"):
            validate_phase32_gate(
                gate,
                deployment,

                {"status": "pass"},
                self._evidence(),
                {"status": "pass", "defects": []},
                require_oracle_up=True,
            )
    def test_phase32_final_writer_preserves_failed_staging_without_partial_final_set(self) -> None:
        deployment_path = ROOT / "artifacts/phase03.2/03.2-FINAL-DEPLOYMENT.json"
        logical_path = ROOT / "artifacts/phase03.2/03.2-FRAMEBUFFER-EVIDENCE.json"
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            output_root = Path(directory) / "final"
            with self.assertRaisesRegex(RuntimeError, "staging failed"):
                write_phase32_final_artifacts(
                    output_root,
                    deployment_path,
                    logical_path,
                    {},
                    {},
                )
            self.assertFalse(output_root.exists())
            staging = list(output_root.parent.glob(f".{output_root.name}.qualification-staging-*"))
            self.assertEqual(len(staging), 1)
            self.assertTrue(staging[0].is_dir())
    def test_phase32_final_writer_publishes_checkable_sidecars(self) -> None:
        deployment_path = ROOT / "artifacts/phase03.2/03.2-FINAL-DEPLOYMENT.json"
        logical_path = ROOT / "artifacts/phase03.2/03.2-FRAMEBUFFER-EVIDENCE.json"
        qualification = json.loads(
            (ROOT / "artifacts/phase03.2/03.2-FINAL-QUALIFICATION.json").read_text(
                encoding="ascii"
            )
        )
        evidence = json.loads(
            (ROOT / "artifacts/phase03.2/03.2-DEVICE-EVIDENCE.json").read_text(
                encoding="ascii"
            )
        )
        observations = {
            row["id"]: {
                "answer": row["observation"]["value"]["answer"],
                "prompt": row["observation"]["value"]["prompt"],
                "observed_at_unix_ms": row["observation"]["observed_at_unix_ms"],
            }
            for row in evidence["rows"]
        }
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            output_root = Path(directory) / "final"
            write_phase32_final_artifacts(
                output_root,
                deployment_path,
                logical_path,
                qualification,
                observations,
            )
            for path in output_root.glob("*.json"):
                sidecar = path.with_suffix(path.suffix + ".sha256")
                digest, target = sidecar.read_text(encoding="ascii").strip().split()
                self.assertEqual(digest, sha256_file(path))
                self.assertEqual(target, path.relative_to(ROOT).as_posix())

    def test_phase32_gate_rejects_wrong_schema_before_hash_join(self) -> None:
        deployment = self._deployment()
        gate = {
            "schema_version": 2,
            "kind": "phase03.2-phase4-gate",
            "status": "pass",
        }
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_phase32_gate(
                gate,
                deployment,
                {"status": "pass"},
                self._evidence(),
                {"status": "pass", "defects": []},
            )

if __name__ == "__main__":
    unittest.main()
