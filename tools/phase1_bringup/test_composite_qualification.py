from __future__ import annotations

import io
import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from phase1_bringup.composite_qualification import (
    CompositeQualificationError,
    FINAL_AUTOMATED_CONTRACTS,
    FINAL_EDGE_ASSUMPTIONS,
    FINAL_ROW_COUNTS,
    FINAL_STRESS_COUNTS,
    INPUT_KIND,
    RESULT_KIND,
    PLAN00_DEFERRED_ROWS,
    ROW_COUNTS,
    SCHEMA_VERSION,
    deterministic_calibration_matrix,
    mixed_stress_schedule,
    STRESS_COUNTS,
    TRAFFIC_KIND,
    freeze_composite_manifest,
    record_composite_run,
    validate_final_qualification,
    validate_input_trace,
    verify_composite_decision,
    verify_composite_run,
    write_terminal_decision,
)
from phase1_bringup import composite_qualification as composite_module


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


class CompositeFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.firmware = root / "composite.bin"
        self.pairing = root / "pairing.json"
        self.descriptor_expectation = root / "descriptor-expectation.txt"
        self.descriptor_capture = b"exact composite descriptor capture\n"
        self.firmware.write_bytes(b"fixed Space composite firmware")
        self.pairing.write_text('{"device_id":"exact-keypad"}\n', encoding="ascii")
        self.descriptor_expectation.write_text("one CDC plus one standard keyboard HID\n", encoding="ascii")
        self.manifest_path = root / "composite-manifest.json"
        self.manifest = freeze_composite_manifest(
            self.manifest_path,
            self.firmware,
            self.pairing,
            self.descriptor_expectation,
            environment="composite-feasibility",
            boot_id="frozen-boot",
            session_id="frozen-session",
            seed=0x03200,
            threshold_ms=550,
            tool_versions={"lsusb": "usbutils-018", "udevadm": "systemd-259", "evdev": "linux-7.1"},
        )

    def trace(self, run_id: str) -> dict[str, object]:
        events = [
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 1, "monotonic_ns": 10},
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 2, "monotonic_ns": 11},
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 0, "monotonic_ns": 12},
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": INPUT_KIND,
            "run_id": run_id,
            "observer": "linux-evdev",
            "external": True,
            "complete": True,
            "deferred": False,
            "events": events,
            "event_count": len(events),
            "final_state": "UP",
        }

    def traffic(self, run_id: str) -> dict[str, object]:
        direction = {"expected": 2000, "sent": 2000, "received": 2000, "acknowledged": 2000}
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": TRAFFIC_KIND,
            "run_id": run_id,
            "counts": {"host_to_device": dict(direction), "device_to_host": dict(direction)},
            "strict_counters": {
                "unexpected_reject": 0,
                "duplicate": 0,
                "out_of_order": 0,
                "malformed": 0,
                "digest_mismatch": 0,
                "queue_failure": 0,
                "short_write": 0,
            },
            "maximum_line_bytes_including_lf": 385,
            "overlong_rejected": True,
            "next_valid_accepted": True,
        }

    def rows(self, failed_row: str | None = None) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        frozen = {row["id"]: row for row in self.manifest["rows"]}
        for row_id, required in self.manifest["row_counts"].items():
            if frozen[row_id]["applicable"] is False:
                rows.append({
                    "id": row_id,
                    "applicable": False,
                    "required_count": 0,
                    "observed_count": 0,
                    "status": "not-applicable",
                    "reason": frozen[row_id]["reason"],
                })
            else:
                rows.append({
                    "id": row_id,
                    "applicable": True,
                    "required_count": required,
                    "observed_count": 1 if row_id == failed_row else required,
                    "status": "fail" if row_id == failed_row else "pass",
                })
        return rows

    def result(
        self,
        run_id: str,
        *,
        status: str = "PASS",
        failure_class: str | None = None,
        failure_row: str = "usb-removal",
        invariant: str = "Space remained DOWN after verified USB removal",
        boot_id: str = "run-boot",
        session_id: str = "run-session",
    ) -> dict[str, object]:
        schedule = mixed_stress_schedule(self.manifest["stress"]["seed"])
        result: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "kind": RESULT_KIND,
            "run_id": run_id,
            "manifest_sha256": self.manifest["manifest_sha256"],
            "status": status,
            "failure_class": failure_class,
            "preflight_status": "pass",
            "clean_boot": True,
            "boot_id": boot_id,
            "session_id": session_id,
            "rows": self.rows(failure_row if status == "FAIL" else None),
            "input_oracle": {"state": "UP", "events_seen": 3, "failures": []},
            "descriptor_observation": {
                "external": True,
                "complete": True,
                "sha256": hashlib.sha256(self.descriptor_capture).hexdigest(),
                "cdc_interfaces": 1,
                "keyboard_hid_interfaces": 1,
                "other_hid_usages": 0,
                "stable_after_resets": 0,
                "stable_after_unplugs": 0,
                "stable_after_uploads": 5,
            },
            "udev_observation": {"external": True, "complete": True, "observer": "udevadm"},
            "blockers": [],
            "deferred": [],
            "open_defects": [],
            "latency": {
                "eligible_to_down": {"samples_ms": [10] * 12, "count": 12, "p95_ms": 10, "max_ms": 10},
                "release_to_up": {"samples_ms": [12] * 12, "count": 12, "p95_ms": 12, "max_ms": 12},
            },
            "stress": {
                "status": "not-applicable",
                "reason": self.manifest["rows"][-1]["reason"],
            },
        }
        if status == "FAIL":
            result["first_failure"] = {"row_id": failure_row, "invariant": invariant}
            result["rerun_rows"] = list(self.manifest["row_counts"])
        return result

    def run(
        self,
        run_id: str,
        *,
        status: str = "PASS",
        failure_class: str | None = None,
        boot_id: str = "run-boot",
        session_id: str = "run-session",
    ) -> Path:
        return record_composite_run(
            self.manifest_path,
            self.root,
            run_id,
            self.result(
                run_id,
                status=status,
                failure_class=failure_class,
                boot_id=boot_id,
                session_id=session_id,
            ),
            self.traffic(run_id),
            self.trace(run_id),
            self.descriptor_capture,
        )


class CompositeManifestAndScheduleTests(unittest.TestCase):
    def test_manifest_freezes_exact_matrix_space_boundary_and_ea07(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CompositeFixture(Path(directory))
            self.assertEqual(set(fixture.manifest["row_counts"]), set(ROW_COUNTS))
            self.assertEqual(
                fixture.manifest["interfaces"],
                {"cdc": 1, "standard_keyboard_hid": 1, "other_hid_usages": 0, "fixed_key": "KEY_SPACE"},
            )
            self.assertEqual(fixture.manifest["edge_assumptions"][0]["status"], "ASSUMED_UNRESOLVED")
            self.assertEqual(fixture.manifest["row_counts"]["threshold-calibration"], 204)
            self.assertEqual(
                fixture.manifest["calibration"],
                {
                    "candidate_thresholds_ms": [500, 525, 550, 575, 600],
                    "selected_shared_threshold_ms": 550,
                    "keys": [0, 1, 2],
                    "physical_initial_short_per_key": 3,
                    "physical_initial_hold_per_key": 3,
                    "physical_final_short_per_key": 1,
                    "physical_final_hold_per_key": 1,
                    "deterministic_short_per_key": 30,
                    "deterministic_hold_per_key": 30,
                    "deterministic_candidate_thresholds_ms": [500, 525, 550, 575, 600],
                    "limitation": "No claim of 30 human short samples with zero crossings or 30 human holds all activating.",
                },
            )
            deferred = {
                row["id"]: row["reason"]
                for row in fixture.manifest["rows"]
                if row["applicable"] is False
            }
            self.assertEqual(deferred, PLAN00_DEFERRED_ROWS)
            self.assertTrue(all("Plan 09" in reason for reason in deferred.values()))

    def test_revised_calibration_moves_repetition_to_deterministic_edges(self) -> None:
        cases = deterministic_calibration_matrix()
        self.assertEqual(len(cases), 180)
        self.assertEqual(
            Counter((case["slot"], case["gesture_class"]) for case in cases),
            Counter({
                (slot, gesture_class): 30
                for slot in (0, 1, 2)
                for gesture_class in ("short", "hold")
            }),
        )
        for case in cases:
            crossings = case["candidate_crossings"]
            if case["gesture_class"] == "short":
                self.assertFalse(any(crossings.values()))
            else:
                self.assertTrue(all(crossings.values()))


    def test_stress_schedule_is_seeded_finite_and_count_equal(self) -> None:
        first = mixed_stress_schedule(1234)
        self.assertEqual(first, mixed_stress_schedule(1234))
        self.assertNotEqual(first, mixed_stress_schedule(1235))
        self.assertEqual(len(first), 300)
        self.assertEqual(Counter(first), Counter(STRESS_COUNTS))


class LinuxInputOracleTests(unittest.TestCase):
    def trace(self, events: list[dict[str, object]]) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": INPUT_KIND,
            "observer": "linux-evdev",
            "external": True,
            "complete": True,
            "deferred": False,
            "events": events,
            "event_count": len(events),
            "final_state": "UP",
        }

    def test_repeat_value_two_does_not_transition_state(self) -> None:
        summary = validate_input_trace(self.trace([
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 1, "monotonic_ns": 1},
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 2, "monotonic_ns": 2},
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 2, "monotonic_ns": 3},
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 0, "monotonic_ns": 4},
        ]))
        self.assertEqual(summary["state"], "UP")

    def test_verified_removal_clears_down_and_fresh_remount_is_empty(self) -> None:
        trace = self.trace([
            {"type": "EV_KEY", "code": "KEY_SPACE", "value": 1, "monotonic_ns": 1},
            {"type": "DEVICE_REMOVED", "verified": True, "monotonic_ns": 2},
            {"type": "REMOUNT", "empty": True, "monotonic_ns": 3},
        ])
        self.assertEqual(validate_input_trace(trace)["state"], "UP")

    def test_unverified_removal_resume_active_missing_up_and_duplicate_down_fail(self) -> None:
        cases = (
            ("not externally verified", [
                {"type": "EV_KEY", "code": "KEY_SPACE", "value": 1, "monotonic_ns": 1},
                {"type": "DEVICE_REMOVED", "verified": False, "monotonic_ns": 2},
            ]),
            ("active or non-empty after resume", [
                {"type": "EV_KEY", "code": "KEY_SPACE", "value": 1, "monotonic_ns": 1},
                {"type": "RESUME", "empty": True, "monotonic_ns": 2},
            ]),
            ("ended DOWN", [
                {"type": "EV_KEY", "code": "KEY_SPACE", "value": 1, "monotonic_ns": 1},
            ]),
            ("duplicate Space down", [
                {"type": "EV_KEY", "code": "KEY_SPACE", "value": 1, "monotonic_ns": 1},
                {"type": "EV_KEY", "code": "KEY_SPACE", "value": 1, "monotonic_ns": 2},
            ]),
        )
        for error, events in cases:
            with self.subTest(error=error), self.assertRaisesRegex(CompositeQualificationError, error):
                validate_input_trace(self.trace(events))


class FailClosedRunTests(unittest.TestCase):
    def test_complete_pass_reopens_with_every_immutable_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CompositeFixture(Path(directory))
            checked = verify_composite_run(fixture.run("pass-run"), manifest_path=fixture.manifest_path)
            self.assertEqual(checked["result"]["status"], "PASS")
            self.assertEqual(set(checked["hashes"]), {
                "manifest.json", "result.json", "traffic.json", "input-events.json", "usb-descriptors.txt", "SHA256SUMS"
            })

    def test_missing_row_nonzero_counter_descriptor_down_or_deferred_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CompositeFixture(Path(directory))
            cases: list[tuple[str, dict[str, object], dict[str, object], dict[str, object]]] = []
            missing = fixture.result("missing")
            missing["rows"] = missing["rows"][:-1]
            cases.append(("missing", missing, fixture.traffic("missing"), fixture.trace("missing")))
            counter = fixture.traffic("counter")
            counter["strict_counters"]["duplicate"] = 1
            cases.append(("counter", fixture.result("counter"), counter, fixture.trace("counter")))
            descriptor = fixture.result("descriptor")
            descriptor["descriptor_observation"]["keyboard_hid_interfaces"] = 0
            cases.append(("descriptor", descriptor, fixture.traffic("descriptor"), fixture.trace("descriptor")))
            down = fixture.result("down")
            down_trace = fixture.trace("down")
            down_trace["events"] = [{"type": "EV_KEY", "code": "KEY_SPACE", "value": 1, "monotonic_ns": 1}]
            down_trace["event_count"] = 1
            down_trace["final_state"] = "DOWN"
            down["input_oracle"] = {"state": "DOWN", "events_seen": 1, "failures": []}
            cases.append(("down", down, fixture.traffic("down"), down_trace))
            deferred = fixture.result("deferred")
            deferred["deferred"] = ["stuck-key evidence awaits manual review"]
            cases.append(("deferred", deferred, fixture.traffic("deferred"), fixture.trace("deferred")))
            for name, result, traffic, trace in cases:
                with self.subTest(name=name), self.assertRaises(CompositeQualificationError):
                    record_composite_run(
                        fixture.manifest_path,
                        fixture.root,
                        name,
                        result,
                        traffic,
                        trace,
                        fixture.descriptor_capture,
                    )


class GuidedCompositePreflightTests(unittest.TestCase):
    def test_preflight_builds_recovery_and_composite_upload_then_freezes_exact_observers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools/phase1_bringup/.venv/bin").mkdir(parents=True)
            platformio = root / "tools/phase1_bringup/.venv/bin/python3"
            platformio.write_bytes(b"python")
            (root / ".pio/build/selected-usb").mkdir(parents=True)
            (root / ".pio/build/composite-feasibility").mkdir(parents=True)
            recovery = root / ".pio/build/selected-usb/firmware.bin"
            composite = root / ".pio/build/composite-feasibility/firmware.bin"
            recovery.write_bytes(b"recovery")
            composite.write_bytes(b"composite")
            binding = root / "pairing.json"
            binding.write_text(
                '{"device_id":"0000fccb0deabf8c","protocol":1,"firmware":"phase1-bringup"}\n',
                encoding="ascii",
            )
            event = root / "event-keyboard"
            event.write_bytes(b"")
            commands: list[tuple[str, ...]] = []

            def run_command(argv: tuple[str, ...], _cwd: Path) -> bytes:
                commands.append(argv)
                return b"ok\n"

            before = [SimpleNamespace(device="/dev/ttyACM0", serial_number="exact-serial", vid=0x303A, pid=0x1001)]
            after = [SimpleNamespace(
                device="/dev/ttyACM0",
                serial_number="exactserial",
                vid=0x303A,
                pid=0x1001,
                manufacturer="Espressif",
                product="Composite tracer",
            )]
            with (
                patch.object(composite_module, "_require_guided_bridge_lock"),
                patch.object(
                    composite_module,
                    "_exact_paired_port",
                    return_value=(
                        before[0],
                        {
                            "device_id": "0000fccb0deabf8c",
                            "protocol": 1,
                            "firmware": "phase1-bringup",
                        },
                    ),
                ),
                patch.object(composite_module, "_serial_ports", return_value=after),
                patch.object(composite_module, "_run_guided_command", side_effect=run_command),
                patch.object(composite_module, "_capture_guided_descriptors", return_value=b"exact descriptors\n"),
                patch.object(composite_module, "_find_guided_keyboard_event", return_value=event),
                patch.object(
                    composite_module,
                    "_probe_guided_status",
                    return_value={
                        "event": "status",
                        "usb_started": True,
                        "usb_suspended": False,
                        "hid_ready": True,
                        "space_active": False,
                        "requires_clean_release": False,
                    },
                ),
            ):
                receipt = composite_module.prepare_guided_composite_preflight(
                    root,
                    binding,
                    root / "artifacts/phase03.2",
                    "run-exact-001",
                )

            self.assertEqual(
                commands,
                [
                    (str(platformio), "-m", "platformio", "run", "-e", "selected-usb"),
                    (str(platformio), "-m", "platformio", "run", "-e", "composite-feasibility"),
                    (
                        str(platformio),
                        "-m",
                        "platformio",
                        "run",
                        "-e",
                        "composite-feasibility",
                        "-t",
                        "upload",
                    ),
                ],
            )
            self.assertEqual(receipt["run_id"], "run-exact-001")
            self.assertEqual(receipt["current_row"], "exact-pairing")
            self.assertEqual(receipt["cdc_path"], "/dev/ttyACM0")
            self.assertEqual(receipt["usb"]["vid_pid"], "303a:1001")
            self.assertEqual(receipt["status"]["space_active"], False)
            self.assertEqual(
                json.loads(
                    (root / "artifacts/phase03.2/run-exact-001-preflight.json").read_text(
                        encoding="ascii"
                    )
                ),
                receipt,
            )
            self.assertEqual(
                (root / "artifacts/phase03.2/run-exact-001-usb-descriptors.txt").read_bytes(),
                b"exact descriptors\n",
            )

    def test_keyboard_observer_retries_transient_uaccess_delay(self) -> None:
        event = Path("/dev/input/event13")
        properties = {
            "ID_INPUT_KEYBOARD": "1",
            "ID_VENDOR_ID": "303a",
            "ID_MODEL_ID": "1001",
            "ID_SERIAL_SHORT": "exactserial",
        }
        with (
            patch.object(Path, "glob", return_value=[event]),
            patch.object(composite_module, "_udev_properties", return_value=properties),
            patch.object(
                composite_module.os,
                "open",
                side_effect=[PermissionError(13, "permission denied"), 7],
            ) as open_device,
            patch.object(composite_module.os, "close") as close_device,
        ):
            selected = composite_module._find_guided_keyboard_event(
                "303a:1001", "exactserial", timeout=1.0
            )

        self.assertEqual(selected, event)
        self.assertEqual(open_device.call_count, 2)
        close_device.assert_called_once_with(7)


    def test_cli_reports_only_the_current_exact_pairing_action(self) -> None:
        from phase1_bringup.__main__ import main

        receipt = {
            "run_id": "run-exact-001",
            "current_row": "exact-pairing",
            "current_step": "physical-key-challenge",
            "immediate_action": "Press and release physical agent key 1 exactly once.",
        }
        output = io.StringIO()
        with (
            patch.object(
                composite_module,
                "prepare_guided_composite_preflight",
                return_value=receipt,
            ),
            patch.object(
                composite_module,
                "wait_for_guided_pairing_challenge",
                return_value=Path("/repo/artifacts/phase03.2/run-exact-001-pairing-challenge.json"),
            ),
            redirect_stdout(output),
        ):
            status = main([
                "composite-preflight",
                "--project-root",
                "/repo",
                "--binding",
                "/binding.json",
                "--evidence-root",
                "/repo/artifacts/phase03.2",
                "--run-id",
                "run-exact-001",
            ])
        self.assertEqual(status, 0)
        self.assertEqual(
            output.getvalue(),
            "COMPOSITE CHECKPOINT run=run-exact-001 row=exact-pairing "
            "step=physical-key-challenge\n"
            "ACTION: Press and release physical agent key 1 exactly once.\n"
            "COMPOSITE PHYSICAL ACTION VERIFIED: "
            "/repo/artifacts/phase03.2/run-exact-001-pairing-challenge.json\n",
        )


    def test_preflight_fails_before_commands_without_exclusive_bridge_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(
                composite_module,
                "_require_guided_bridge_lock",
                side_effect=CompositeQualificationError("exclusive bridge lock is required"),
            ), self.assertRaisesRegex(CompositeQualificationError, "exclusive bridge lock"):
                composite_module.prepare_guided_composite_preflight(
                    root,
                    root / "pairing.json",
                    root / "artifacts/phase03.2",
                    "run-exact-001",
                )


class TerminalDecisionTests(unittest.TestCase):
    def test_pass_binds_manifest_run_binary_descriptor_pair_trace_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CompositeFixture(Path(directory))
            run = fixture.run("pass-run")
            decision_path = fixture.root / "composite-decision.json"
            decision = write_terminal_decision(decision_path, fixture.manifest_path, status="PASS", run_directory=run)
            self.assertEqual(decision["status"], "PASS")
            self.assertEqual(decision["run"]["input_events_sha256"], hashlib.sha256((run / "input-events.json").read_bytes()).hexdigest())
            checked = verify_composite_decision(decision_path, require_terminal=True, require_immutable_lineage=True)
            self.assertEqual(checked["decision_sha256"], decision["decision_sha256"])

    def test_cli_verifies_decision_without_opening_hardware(self) -> None:
        from phase1_bringup.__main__ import main

        with tempfile.TemporaryDirectory() as directory:
            fixture = CompositeFixture(Path(directory))
            decision_path = fixture.root / "composite-decision.json"
            write_terminal_decision(
                decision_path,
                fixture.manifest_path,
                status="PASS",
                run_directory=fixture.run("pass-run"),
            )
            output = io.StringIO()
            with redirect_stdout(output):
                status = main([
                    "composite-verify-decision",
                    "--decision",
                    str(decision_path),
                    "--require-terminal",
                    "--require-immutable-lineage",
                ])
            self.assertEqual(status, 0)
            self.assertIn("Composite decision verified: PASS", output.getvalue())

    def test_decision_rejects_path_escape_and_hash_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside_directory:
            fixture = CompositeFixture(Path(directory))
            decision_path = fixture.root / "composite-decision.json"
            write_terminal_decision(decision_path, fixture.manifest_path, status="PASS", run_directory=fixture.run("pass-run"))
            decision = json.loads(decision_path.read_text(encoding="ascii"))
            decision["run"]["path"] = str(Path(outside_directory))
            unhashed = {key: value for key, value in decision.items() if key != "decision_sha256"}
            decision["decision_sha256"] = hashlib.sha256(canonical_bytes(unhashed)).hexdigest()
            decision_path.write_bytes(canonical_bytes(decision))
            with self.assertRaisesRegex(CompositeQualificationError, "escapes"):
                verify_composite_decision(decision_path)

    def test_harness_failure_cannot_produce_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CompositeFixture(Path(directory))
            first = fixture.run("first", status="FAIL", failure_class="harness_setup", boot_id="boot-a", session_id="session-a")
            retest = fixture.run("retest", status="FAIL", failure_class="product", boot_id="boot-b", session_id="session-b")
            with self.assertRaisesRegex(CompositeQualificationError, "product failures"):
                write_terminal_decision(
                    fixture.root / "composite-decision.json",
                    fixture.manifest_path,
                    status="REJECT",
                    first_failure_directory=first,
                    retest_directory=retest,
                    correction={"count": 1, "target": "USB lifecycle release", "description": "one bounded correction"},
                )

    def test_reject_requires_one_correction_clean_fresh_retest_and_matching_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CompositeFixture(Path(directory))
            first = fixture.run("first", status="FAIL", failure_class="product", boot_id="boot-a", session_id="session-a")
            retest = fixture.run("retest", status="FAIL", failure_class="product", boot_id="boot-b", session_id="session-b")
            decision = write_terminal_decision(
                fixture.root / "composite-decision.json",
                fixture.manifest_path,
                status="REJECT",
                first_failure_directory=first,
                retest_directory=retest,
                correction={"count": 1, "target": "USB lifecycle release", "description": "send and drain the fixed empty report"},
            )
            self.assertEqual(decision["status"], "REJECT")
            self.assertEqual(decision["reproduced_invariant"]["row_id"], "usb-removal")

    def test_first_failure_artifact_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CompositeFixture(Path(directory))
            first = fixture.run("first", status="FAIL", failure_class="product")
            before = (first / "SHA256SUMS").read_bytes()
            with self.assertRaisesRegex(CompositeQualificationError, "already exists"):
                fixture.run("first", status="FAIL", failure_class="product")
            self.assertEqual((first / "SHA256SUMS").read_bytes(), before)
class FinalProductionQualificationTests(unittest.TestCase):
    @staticmethod
    def _deployment() -> dict[str, object]:
        return {
            "deployment_id": "final-deployment",
            "firmware_sha256": "f" * 64,
            "pair_digest": "p" * 64,
            "pairing_record_sha256": "p" * 64,
            "descriptor_tuple_sha256": "d" * 64,
            "boot_id": "boot-final",
            "session_id": "session-final",
            "decision_sha256": "c" * 64,
            "decision_manifest_sha256": "m" * 64,
            "protocol_version": 1,
            "paired_device_id": "device-final",
        }

    @classmethod
    def _qualification(cls) -> dict[str, object]:
        deployment = cls._deployment()
        categories: list[str] = []
        for category, count in FINAL_STRESS_COUNTS.items():
            categories.extend([category] * count)
        gestures = []
        for index, category in enumerate(categories):
            down = category in {"authorized_hold", "delayed_ack_threshold_first"}
            gestures.append({
                "id": f"gesture-{index:03d}",
                "category": category,
                "slot": index % 3,
                "threshold_ms": 550,
                "physical_down": True,
                "focus": {
                    "action_id": f"action-{index:03d}",
                    "binding_digest": deployment["pair_digest"],
                    "host_epoch": "epoch-final",
                    "snapshot_revision": index + 1,
                    "usb_session": deployment["session_id"],
                    "outcome": "accepted" if down else "rejected",
                    "focused": down,
                    "authorized": down,
                },
                "hid_values": [1, 2, 0] if down else [],
                "firmware": {
                    "space_down_requests": 1 if down else 0,
                    "space_down_completions": 1 if down else 0,
                    "space_up_requests": 1 if down else 0,
                    "space_up_completions": 1 if down else 0,
                },
                "oracle_after": "UP",
            })
        rows = [
            {
                "id": row_id,
                "applicable": True,
                "required_count": required,
                "observed_count": required,
                "status": "pass",
            }
            for row_id, required in FINAL_ROW_COUNTS.items()
        ]
        return {
            "schema_version": 1,
            "kind": "phase03.2-final-qualification",
            "status": "pass",
            "automated_contracts": dict(FINAL_AUTOMATED_CONTRACTS),
            "deployment_id": deployment["deployment_id"],
            "firmware_sha256": deployment["firmware_sha256"],
            "deployment_lock_sha256": "l" * 64,
            "threshold_ms": 550,
            "rows": rows,
            "edge_assumptions": [dict(item) for item in FINAL_EDGE_ASSUMPTIONS],
            "gesture_reconciliation": {
                "scheduled_count": 300,
                "observed_count": 300,
                "scheduled_counts": dict(FINAL_STRESS_COUNTS),
                "observed_counts": dict(FINAL_STRESS_COUNTS),
                "mismatches": [],
                "records": gestures,
            },
            "input_oracle": {"state": "UP", "events_seen": 600, "failures": []},
            "firmware_metrics": {
                "status": "pass",
                "space_down_requests": 120,
                "space_down_completions": 120,
                "space_up_requests": 120,
                "space_up_completions": 120,
                "strict_counters": {name: 0 for name in (
                    "unexpected_reject", "duplicate", "out_of_order", "malformed",
                    "digest_mismatch", "queue_failure", "short_write",
                )},
            },
            "cdc": {
                "maximum_line_bytes_including_lf": 4096,
                "counts": {
                    "host_to_device": {
                        "expected": 2000, "sent": 2000, "received": 2000, "acknowledged": 2000,
                    },
                    "device_to_host": {
                        "expected": 2000, "sent": 2000, "received": 2000, "acknowledged": 2000,
                    },
                },
                "strict_counters": {name: 0 for name in (
                    "unexpected_reject", "duplicate", "out_of_order", "malformed",
                    "digest_mismatch", "queue_failure", "short_write",
                )},
                "overlong_rejected": True,
                "next_valid_accepted": True,
            },
            "latency": {
                name: {"samples_ms": [1] * 100, "count": 100, "p95_ms": 1, "max_ms": 1}
                for name in ("eligible_to_down", "release_to_up")
            },
            "deployment": {
                "pair_digest": deployment["pair_digest"],
                "pairing_record_sha256": deployment["pairing_record_sha256"],
                "descriptor_tuple_sha256": deployment["descriptor_tuple_sha256"],
                "boot_id": deployment["boot_id"],
                "session_id": deployment["session_id"],
                "decision_sha256": deployment["decision_sha256"],
                "decision_manifest_sha256": deployment["decision_manifest_sha256"],
                "protocol_version": 1,
            },
            "open_defects": [],

        }
    def test_phase32_final_gate_reconciles_production_matrix_and_lineage(self) -> None:
        deployment = self._deployment()
        logical = {
            "status": "pass",
            "deployment_id": deployment["deployment_id"],
            "firmware_sha256": deployment["firmware_sha256"],
            "deployment_lock_sha256": "l" * 64,
        }
        checked = validate_final_qualification(self._qualification(), deployment, logical)
        self.assertEqual(checked["status"], "pass")

    def test_phase32_final_gate_rejects_stale_threshold_or_gesture_observation(self) -> None:
        deployment = self._deployment()
        logical = {
            "status": "pass",
            "deployment_id": deployment["deployment_id"],
            "firmware_sha256": deployment["firmware_sha256"],
            "deployment_lock_sha256": "l" * 64,
        }
        stale = self._qualification()
        stale["threshold_ms"] = 525
        with self.assertRaisesRegex(CompositeQualificationError, "threshold"):
            validate_final_qualification(stale, deployment, logical)
        invalid = self._qualification()
        invalid["gesture_reconciliation"]["records"][0]["hid_values"] = [1, 0]
        with self.assertRaisesRegex(CompositeQualificationError, "gesture"):
            validate_final_qualification(invalid, deployment, logical)



if __name__ == "__main__":
    unittest.main()
