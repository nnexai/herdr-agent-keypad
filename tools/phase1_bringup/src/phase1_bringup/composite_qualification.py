"""Fail-closed Phase 03.2 composite CDC plus fixed-Space qualification.

The module deliberately has no configurable key or host-injection boundary.  Linux
input, udev, and descriptor observation stay private; callers can only freeze the
matrix, record one bounded run, and verify immutable evidence or a terminal
PASS/REJECT decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import selectors
import struct
import subprocess
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evidence import atomic_write_pair

SCHEMA_VERSION = 1
MANIFEST_KIND = "composite-qualification-manifest"
RESULT_KIND = "composite-qualification-result"
TRAFFIC_KIND = "composite-traffic"
INPUT_KIND = "composite-input-events"
DECISION_KIND = "composite-decision"
CALIBRATION_CANDIDATES_MS = (500, 525, 550, 575, 600)
AGENT_KEYS = (0, 1, 2)
LATENCY_TARGET_P95_MS = 80
LATENCY_HARD_MAX_MS = 120
MAX_INPUT_EVENTS = 100_000
STRESS_COUNTS = {
    "short": 90,
    "authorized_hold": 90,
    "delayed_ack_threshold_first": 30,
    "early_release": 30,
    "overlap": 30,
    "stale_failure_session_lifecycle": 30,
}
STRICT_COUNTERS = (
    "unexpected_reject",
    "duplicate",
    "out_of_order",
    "malformed",
    "digest_mismatch",
    "queue_failure",
    "short_write",
)
ROW_COUNTS = {
    "build-controller": 1,
    "usb-identity": 6,
    "exact-pairing": 1,
    "threshold-calibration": 204,
    "immediate-focus-short-separation": 90,
    "focus-before-hid-ordering": 180,
    "release-before-ack": 120,
    "stale-failure-source-session": 220,
    "repeat-behavior": 12,
    "active-owner-independence": 30,
    "cdc-under-hid": 4000,
    "physical-release": 12,
    "usb-removal": 5,
    "controlled-reset": 5,
    "suspend-resume": 5,
    "reconnect-session": 10,
    "normal-flashing": 5,
    "boot-recovery": 1,
    "input-latency": 12,
    "mixed-stress": 300,
}
PLAN00_DEFERRED_ROWS = {
    "immediate-focus-short-separation": "Production focus-result authorization does not exist in the isolated feasibility tracer; mandatory Plan 09 gate after Plans 01-08.",
    "focus-before-hid-ordering": "Production focus/threshold ordering does not exist in the isolated feasibility tracer; mandatory Plan 09 gate after Plans 01-08.",
    "release-before-ack": "Production focus-result cancellation does not exist in the isolated feasibility tracer; mandatory Plan 09 gate after Plans 01-08.",
    "stale-failure-source-session": "Production outcome/session rejection does not exist in the isolated feasibility tracer; mandatory Plan 09 gate after Plans 01-08.",
    "active-owner-independence": "Production overlap/chord ownership does not exist in the isolated feasibility tracer; mandatory Plan 09 gate after Plans 01-08.",
    "usb-removal": "Active-controller removal safety requires the production controller; mandatory Plan 09 gate after Plans 01-08.",
    "controlled-reset": "Controller reset fencing requires the production controller; mandatory Plan 09 gate after Plans 01-08.",
    "suspend-resume": "Active-controller suspend/resume fencing requires the production controller; mandatory Plan 09 gate after Plans 01-08.",
    "reconnect-session": "Production stale-session reconnect fencing does not exist in the isolated feasibility tracer; mandatory Plan 09 gate after Plans 01-08.",
    "mixed-stress": "Mixed production-controller stress is mandatory in Plan 09 after Plans 01-08.",
}
DETERMINISTIC_ROWS = tuple(
    row for row in ROW_COUNTS
    if row != "mixed-stress" and row not in PLAN00_DEFERRED_ROWS
)
REQUIRED_RUN_FILES = (
    "manifest.json",
    "result.json",
    "traffic.json",
    "input-events.json",
    "usb-descriptors.txt",
    "SHA256SUMS",
)
_INPUT_EVENT = struct.Struct("llHHI")
_EV_KEY = 0x01
_KEY_SPACE = 57
FINAL_QUALIFICATION_SCHEMA_VERSION = 1
FINAL_QUALIFICATION_KIND = "phase03.2-final-qualification"
FINAL_SHARED_THRESHOLD_MS = 550
FINAL_CDC_MAX_LINE_BYTES = 4096
FINAL_LATENCY_TARGET_P95_MS = 80
FINAL_LATENCY_HARD_MAX_MS = 120
FINAL_STRESS_COUNTS = dict(STRESS_COUNTS)
FINAL_ROW_COUNTS = {
    "build-controller": 1,
    "usb-identity": 6,
    "exact-pairing": 1,
    "threshold-calibration": 204,
    "immediate-focus-short-separation": 90,
    "focus-before-hid-ordering": 180,
    "release-before-ack": 120,
    "stale-failure-source-session": 220,
    "repeat-behavior": 30,
    "active-owner-independence": 30,
    "cdc-under-hid": 4000,
    "physical-release": 90,
    "usb-removal": 5,
    "controlled-reset": 5,
    "suspend-resume": 5,
    "reconnect-session": 10,
    "normal-flashing": 5,
    "boot-recovery": 1,
    "input-latency": 100,
    "mixed-stress": 300,
}
FINAL_EDGE_ASSUMPTIONS = (
    {
        "id": "EA-01",
        "requirement": "HOLD-01",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "occupied and non-actionable short gestures with immediate focus and zero HID-down observation",
    },
    {
        "id": "EA-02",
        "requirement": "HOLD-02",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "ack-before-threshold and threshold-before-ack with exact action, binding, session, and threshold reconciliation",
    },
    {
        "id": "EA-03",
        "requirement": "HOLD-03",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "release and every stale, failure, source, and session path must remain monotonic and HID-up",
    },
    {
        "id": "EA-04",
        "requirement": "HOLD-04",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "threshold equality, one-poll edge, and same-poll chord boundaries use explicit wrap-safe transitions",
    },
    {
        "id": "EA-05",
        "requirement": "HOLD-04",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "empty-first release/removal/reset/suspend/resume/reconnect lifecycle observations and all-keys-up rearm",
    },
    {
        "id": "EA-06",
        "requirement": "HOLD-04",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "all six ordered owner/other-key pairs, owner release, and no ownership transfer",
    },
    {
        "id": "EA-07",
        "requirement": "HOLD-05",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "exact deployment identity, descriptor stability, CDC/HID lifecycle, flashing, recovery, latency, and stuck-key rows",
    },
    {
        "id": "EA-08",
        "requirement": "SAFE-02",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "closed protocol and fixed-Space negative matrix reject generic action, key, macro, text, and provider authority",
    },
    {
        "id": "EA-09",
        "requirement": "SAFE-02",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "4096-byte-including-LF v2 envelope, overlong rejection, and next-valid-frame recovery",
    },
    {
        "id": "EA-10",
        "requirement": "SAFE-02",
        "status": "ASSUMED_UNRESOLVED",
        "backstop": "bounded CDC traffic during active HID, focus changes, lifecycle interruption, and seeded mixed stress",
    },
)
FINAL_STRICT_COUNTERS = STRICT_COUNTERS


def _final_failure(message: str) -> None:
    raise CompositeQualificationError(f"final production qualification {message}")
FINAL_AUTOMATED_CONTRACTS = {
    "native-hold-controller": "pass",
    "native-board-adapter": "pass",
    "native-agent-projection": "pass",
    "native-protocol": "pass",
    "host-integration": "pass",
    "logical-evidence": "pass",
    "descriptor-pair": "pass",
    "linux-input-oracle": "pass",
    "firmware-metrics": "pass",
    "lifecycle-matrix": "pass",
    "seeded-stress": "pass",
}


def _validate_final_rows(rows: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(rows, list):
        _final_failure("rows must be a list")
    mapped: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str):
            _final_failure("row is not an object with an id")
        row_id = str(row["id"])
        if row_id in mapped:
            _final_failure("rows contain a duplicate id")
        mapped[row_id] = row
    if tuple(mapped) != tuple(FINAL_ROW_COUNTS):
        _final_failure("row matrix differs from the restored production matrix")
    for row_id, required in FINAL_ROW_COUNTS.items():
        row = mapped[row_id]
        if (
            row.get("applicable") is not True
            or row.get("required_count") != required
            or row.get("observed_count") != required
            or row.get("status") != "pass"
        ):
            _final_failure(f"row {row_id} is incomplete or failed")
    return mapped


def _validate_final_latency(latency: Any) -> None:
    if not isinstance(latency, Mapping):
        _final_failure("latency evidence is missing")
    for name in ("eligible_to_down", "release_to_up"):
        sample = latency.get(name)
        if not isinstance(sample, Mapping):
            _final_failure(f"{name} latency evidence is missing")
        values = sample.get("samples_ms")
        if (
            not isinstance(values, list)
            or len(values) < FINAL_ROW_COUNTS["input-latency"]
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value < 0
                for value in values
            )
        ):
            _final_failure(f"{name} latency requires at least 100 non-negative samples")
        p95 = _percentile(values, 95)
        maximum = max(values)
        if (
            sample.get("count") != len(values)
            or sample.get("p95_ms") != p95
            or sample.get("max_ms") != maximum
            or p95 > FINAL_LATENCY_TARGET_P95_MS
            or maximum > FINAL_LATENCY_HARD_MAX_MS
        ):
            _final_failure(f"{name} latency exceeds the production bound or is not recomputable")


def _validate_final_cdc(cdc: Any) -> None:
    if not isinstance(cdc, Mapping):
        _final_failure("CDC evidence is missing")
    if cdc.get("maximum_line_bytes_including_lf") != FINAL_CDC_MAX_LINE_BYTES:
        _final_failure("CDC bound is not the production v2 maximum")
    counts = cdc.get("counts")
    if not isinstance(counts, Mapping):
        _final_failure("CDC counters are missing")
    for direction in ("host_to_device", "device_to_host"):
        entry = counts.get(direction)
        if not isinstance(entry, Mapping):
            _final_failure(f"CDC {direction} counters are missing")
        if any(entry.get(name) != 2000 for name in ("expected", "sent", "received", "acknowledged")):
            _final_failure(f"CDC {direction} counters are not exactly equal")
    strict = cdc.get("strict_counters")
    if (
        not isinstance(strict, Mapping)
        or set(strict) != set(FINAL_STRICT_COUNTERS)
        or any(not isinstance(value, int) or isinstance(value, bool) or value != 0 for value in strict.values())
    ):
        _final_failure("CDC strict counters are nonzero or incomplete")
    if cdc.get("overlong_rejected") is not True or cdc.get("next_valid_accepted") is not True:
        _final_failure("CDC overlong recovery is missing")


def _validate_final_gestures(
    reconciliation: Any,
    deployment: Mapping[str, Any],
) -> tuple[int, int]:
    if not isinstance(reconciliation, Mapping):
        _final_failure("gesture reconciliation is missing")
    if (
        reconciliation.get("scheduled_count") != FINAL_ROW_COUNTS["mixed-stress"]
        or reconciliation.get("observed_count") != FINAL_ROW_COUNTS["mixed-stress"]
        or reconciliation.get("mismatches") != []
        or reconciliation.get("scheduled_counts") != FINAL_STRESS_COUNTS
        or reconciliation.get("observed_counts") != FINAL_STRESS_COUNTS
    ):
        _final_failure("gesture scheduled/observed counts are unequal")
    records = reconciliation.get("records")
    if not isinstance(records, list) or len(records) != FINAL_ROW_COUNTS["mixed-stress"]:
        _final_failure("gesture records do not cover the seeded 300-case schedule")
    expected_categories = list(FINAL_STRESS_COUNTS)
    counts: Counter[str] = Counter()
    down_total = 0
    up_total = 0
    for record in records:
        if not isinstance(record, Mapping):
            _final_failure("gesture record is not an object")
        category = record.get("category")
        if category not in FINAL_STRESS_COUNTS:
            _final_failure("gesture record has an unknown category")
        counts[str(category)] += 1
        if (
            not isinstance(record.get("id"), str)
            or not isinstance(record.get("slot"), int)
            or isinstance(record.get("slot"), bool)
            or record["slot"] not in AGENT_KEYS
            or record.get("threshold_ms") != FINAL_SHARED_THRESHOLD_MS
            or not isinstance(record.get("physical_down"), bool)
            or record.get("oracle_after") != "UP"
        ):
            _final_failure("gesture record has an incomplete physical/threshold observation")
        focus = record.get("focus")
        if not isinstance(focus, Mapping):
            _final_failure("gesture record lacks exact focus/session evidence")
        if (
            not isinstance(focus.get("action_id"), str)
            or focus.get("binding_digest") != deployment.get("pair_digest")
            or focus.get("host_epoch") in (None, "")
            or not isinstance(focus.get("snapshot_revision"), int)
            or focus.get("snapshot_revision") <= 0
            or focus.get("usb_session", focus.get("session_id")) != deployment.get("session_id")
            or not isinstance(focus.get("outcome"), str)
            or not isinstance(focus.get("focused"), bool)
            or not isinstance(focus.get("authorized"), bool)
        ):
            _final_failure("gesture record focus/session correlation is incomplete")
        values = record.get("hid_values")
        if not isinstance(values, list) or any(value not in (0, 1, 2) for value in values):
            _final_failure("gesture record HID values are invalid")
        if values.count(1) > 1 or values.count(0) > 1 or (values.count(1) and not values.count(0)):
            _final_failure("gesture record HID down/up sequence is invalid")
        if values.count(1):
            if values.index(1) > values.index(0) or focus.get("authorized") is not True:
                _final_failure("gesture record admitted HID before exact focus authorization")
            down_total += 1
            up_total += values.count(0)
        elif focus.get("authorized") is True and category in {"short", "early_release", "stale_failure_session_lifecycle"}:
            _final_failure("gesture record claims authorization without HID or cancellation evidence")
        firmware = record.get("firmware")
        if not isinstance(firmware, Mapping):
            _final_failure("gesture record firmware metrics are missing")
        if any(
            firmware.get(name) != (1 if values.count(1) else 0)
            for name in ("space_down_requests", "space_down_completions")
        ) or any(
            firmware.get(name) != (1 if values.count(0) else 0)
            for name in ("space_up_requests", "space_up_completions")
        ):
            _final_failure("gesture record firmware counters do not reconcile to HID values")
    expected_down = (
        FINAL_STRESS_COUNTS["authorized_hold"]
        + FINAL_STRESS_COUNTS["delayed_ack_threshold_first"]
    )
    if (
        counts != Counter(FINAL_STRESS_COUNTS)
        or down_total != expected_down
        or up_total != expected_down
    ):
        _final_failure("gesture category or HID totals do not reconcile")
    return down_total, up_total


def validate_final_qualification(
    qualification: Mapping[str, Any],
    deployment: Mapping[str, Any],
    logical_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reopen the strict production matrix without hardware access.

    This is deliberately separate from the Plan 00 feasibility validator.  The
    production gate cannot inherit deferred rows, the 385-byte tracer bound, or
    the 12-sample latency floor.
    """
    contracts = qualification.get("automated_contracts")
    if contracts != FINAL_AUTOMATED_CONTRACTS:
        _final_failure("automated contract suite is incomplete or failed")
    if (
        qualification.get("schema_version") != FINAL_QUALIFICATION_SCHEMA_VERSION
        or qualification.get("kind") != FINAL_QUALIFICATION_KIND
        or qualification.get("status") != "pass"
    ):
        _final_failure("schema/status is not a terminal pass")
    deployment_id = deployment.get("deployment_id")
    firmware_sha256 = deployment.get("firmware_sha256")
    if (
        not isinstance(deployment_id, str)
        or not isinstance(firmware_sha256, str)
        or qualification.get("deployment_id") != deployment_id
        or qualification.get("firmware_sha256") != firmware_sha256
    ):
        _final_failure("deployment or binary lineage is stale")
    if qualification.get("threshold_ms") != FINAL_SHARED_THRESHOLD_MS:
        _final_failure("shared threshold is not the measured 550 ms")
    lock_sha = qualification.get("deployment_lock_sha256")
    if not isinstance(lock_sha, str) or len(lock_sha) != 64:
        _final_failure("deployment lock sidecar hash is missing")
    if logical_evidence is not None and (
        logical_evidence.get("status") != "pass"
        or logical_evidence.get("deployment_id") != deployment_id
        or logical_evidence.get("firmware_sha256") != firmware_sha256
        or logical_evidence.get("deployment_lock_sha256") != lock_sha
    ):
        _final_failure("logical evidence lineage is stale or incomplete")
    expected_deployment = qualification.get("deployment")
    if not isinstance(expected_deployment, Mapping):
        _final_failure("exact deployment tuple is missing")
    for field in (
        "pair_digest", "pairing_record_sha256", "descriptor_tuple_sha256",
        "boot_id", "session_id", "decision_sha256", "decision_manifest_sha256",
    ):
        if expected_deployment.get(field) != deployment.get(field):
            _final_failure(f"exact deployment field {field} differs")
    if (
        expected_deployment.get("protocol_version") != deployment.get("protocol_version")
        or deployment.get("protocol_version") != 1
    ):
        _final_failure("exact deployment protocol differs")
    _validate_final_rows(qualification.get("rows"))
    assumptions = qualification.get("edge_assumptions")
    if assumptions != list(FINAL_EDGE_ASSUMPTIONS):
        _final_failure("edge assumptions or named backstops changed")
    _validate_final_cdc(qualification.get("cdc"))
    _validate_final_latency(qualification.get("latency"))
    down_total, up_total = _validate_final_gestures(
        qualification.get("gesture_reconciliation"), deployment
    )
    metrics = qualification.get("firmware_metrics")
    if (
        not isinstance(metrics, Mapping)
        or metrics.get("status") != "pass"
        or metrics.get("space_down_requests") != down_total
        or metrics.get("space_down_completions") != down_total
        or metrics.get("space_up_requests") != up_total
        or metrics.get("space_up_completions") != up_total
        or metrics.get("strict_counters") != {name: 0 for name in FINAL_STRICT_COUNTERS}
    ):
        _final_failure("firmware metrics do not reconcile to observed HID")
    oracle = qualification.get("input_oracle")
    if (
        not isinstance(oracle, Mapping)
        or oracle.get("state") != "UP"
        or oracle.get("failures") != []
        or not isinstance(oracle.get("events_seen"), int)
        or oracle.get("events_seen") <= 0
    ):
        _final_failure("external Linux input oracle is not UP")
    if qualification.get("open_defects") != []:
        _final_failure("open defect evidence is present")
    return dict(qualification)


class CompositeQualificationError(ValueError):
    """A frozen-matrix, observation, or immutable-lineage violation."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(131072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _addressed_hash(value: Mapping[str, Any], field: str) -> str:
    content = dict(value)
    content.pop(field, None)
    return _sha256_bytes(_canonical_bytes(content))


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompositeQualificationError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CompositeQualificationError(f"{label} must be a JSON object")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompositeQualificationError(f"{label} must be a non-empty string")
    return value


def _safe_file(path: Path, root: Path, label: str) -> Path:
    root = Path(root).resolve()
    candidate = Path(path)
    unresolved = candidate if candidate.is_absolute() else root / candidate
    lexical = Path(os.path.abspath(unresolved))
    if lexical == root or root not in lexical.parents:
        raise CompositeQualificationError(f"{label} escapes its evidence root")
    cursor = lexical
    while cursor != root:
        if cursor.is_symlink():
            raise CompositeQualificationError(f"{label} has a symlink ancestor")
        cursor = cursor.parent
    resolved = lexical.resolve()
    if resolved == root or root not in resolved.parents:
        raise CompositeQualificationError(f"{label} escapes its evidence root")
    if not resolved.is_file():
        raise CompositeQualificationError(f"{label} is not a regular file")
    return resolved


def _validate_source_file(path: Path, label: str) -> dict[str, str]:
    path = Path(path).resolve()
    if not path.is_file() or path.is_symlink():
        raise CompositeQualificationError(f"{label} must be an existing non-symlink file")
    return {"path": path.as_posix(), "sha256": _sha256_file(path)}


def mixed_stress_schedule(seed: int) -> tuple[str, ...]:
    """Return the finite, count-equal D-17 schedule for one recorded seed."""
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0 or seed > 0xFFFFFFFF:
        raise CompositeQualificationError("stress seed must be an unsigned 32-bit integer")
    schedule = [name for name, count in STRESS_COUNTS.items() for _ in range(count)]
    random.Random(seed).shuffle(schedule)
    if len(schedule) != 300 or Counter(schedule) != Counter(STRESS_COUNTS):
        raise AssertionError("internal mixed-stress schedule is not count-equal")
    return tuple(schedule)


def deterministic_calibration_matrix() -> tuple[dict[str, Any], ...]:
    """Generate the amended 30-per-class/per-key synthetic edge-timing matrix."""
    cases: list[dict[str, Any]] = []
    for slot in AGENT_KEYS:
        for sample in range(30):
            durations = {
                "short": 125 + ((slot * 31 + sample * 7) % 250),
                "hold": 650 + ((slot * 29 + sample * 11) % 250),
            }
            for gesture_class, duration_ms in durations.items():
                cases.append({
                    "slot": slot,
                    "gesture_class": gesture_class,
                    "sample": sample,
                    "duration_ms": duration_ms,
                    "candidate_crossings": {
                        str(candidate): duration_ms >= candidate
                        for candidate in CALIBRATION_CANDIDATES_MS
                    },
                })
    if len(cases) != 180:
        raise AssertionError("internal deterministic calibration matrix is incomplete")
    return tuple(cases)


def _frozen_rows(row_counts: Mapping[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_id, count in row_counts.items():
        if row_id in PLAN00_DEFERRED_ROWS:
            rows.append({
                "id": row_id,
                "applicable": False,
                "required": False,
                "required_count": 0,
                "reason": PLAN00_DEFERRED_ROWS[row_id],
            })
        else:
            rows.append({
                "id": row_id,
                "applicable": True,
                "required": True,
                "required_count": count,
            })
    return rows


def freeze_composite_manifest(
    output: Path,
    firmware_binary: Path,
    pairing_record: Path,
    descriptor_expectation: Path,
    *,
    environment: str,
    boot_id: str,
    session_id: str,
    seed: int,
    threshold_ms: int,
    tool_versions: Mapping[str, str],
    controlled_reset_paths: Sequence[str] = ("tracer-controlled-reset",),
) -> dict[str, Any]:
    """Create the pre-traffic matrix once, or reopen the identical immutable file."""
    output = Path(output)
    if output.exists():
        return verify_composite_manifest(output)
    if environment != "composite-feasibility":
        raise CompositeQualificationError("only the isolated composite-feasibility environment may be frozen")
    if threshold_ms not in CALIBRATION_CANDIDATES_MS:
        raise CompositeQualificationError("shared threshold must be one frozen 500-600 ms calibration candidate")
    if not isinstance(tool_versions, Mapping) or not tool_versions or any(
        not isinstance(name, str) or not name or not isinstance(version, str) or not version
        for name, version in tool_versions.items()
    ):
        raise CompositeQualificationError("tool_versions must identify every observer/tool with non-empty strings")
    reset_paths = list(controlled_reset_paths)
    if not reset_paths or len(set(reset_paths)) != len(reset_paths) or any(not isinstance(item, str) or not item for item in reset_paths):
        raise CompositeQualificationError("controlled reset paths must be a non-empty unique string list")
    row_counts = dict(ROW_COUNTS)
    row_counts["controlled-reset"] = 5 * len(reset_paths)
    schedule = mixed_stress_schedule(seed)
    pairing_source = _validate_source_file(pairing_record, "pairing record")
    pairing_source["pair_digest"] = pairing_source["sha256"]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "environment": environment,
        "firmware_binary": _validate_source_file(firmware_binary, "firmware binary"),
        "pairing_record": pairing_source,
        "descriptor_expectation": _validate_source_file(descriptor_expectation, "descriptor expectation"),
        "exact_deployment": {
            "boot_id": _require_string(boot_id, "boot_id"),
            "session_id": _require_string(session_id, "session_id"),
        },
        "interfaces": {
            "cdc": 1,
            "standard_keyboard_hid": 1,
            "other_hid_usages": 0,
            "fixed_key": "KEY_SPACE",
        },
        "tool_versions": dict(sorted(tool_versions.items())),
        "calibration": {
            "candidate_thresholds_ms": list(CALIBRATION_CANDIDATES_MS),
            "selected_shared_threshold_ms": threshold_ms,
            "keys": list(AGENT_KEYS),
            "physical_initial_short_per_key": 3,
            "physical_initial_hold_per_key": 3,
            "physical_final_short_per_key": 1,
            "physical_final_hold_per_key": 1,
            "deterministic_short_per_key": 30,
            "deterministic_hold_per_key": 30,
            "deterministic_candidate_thresholds_ms": list(CALIBRATION_CANDIDATES_MS),
            "limitation": "No claim of 30 human short samples with zero crossings or 30 human holds all activating.",
        },
        "row_counts": row_counts,
        "rows": _frozen_rows(row_counts),
        "controlled_reset_paths": reset_paths,
        "descriptor_stability": {
            "upload_reenumerations": 5,
            "software_resets": 0,
            "unplug_replugs": 0,
        },
        "cdc": {
            "steady_frames_each_direction": 1000,
            "burst_repetitions": 10,
            "burst_frames_each_direction": 100,
            "maximum_line_bytes_including_lf": 385,
        },
        "latency_limits_ms": {
            "eligible_to_down_p95": LATENCY_TARGET_P95_MS,
            "eligible_to_down_hard_max": LATENCY_HARD_MAX_MS,
            "release_to_up_p95": LATENCY_TARGET_P95_MS,
            "release_to_up_hard_max": LATENCY_HARD_MAX_MS,
        },
        "stress": {
            "seed": seed,
            "counts": dict(STRESS_COUNTS),
            "total": len(schedule),
            "schedule_sha256": _sha256_bytes(_canonical_bytes(list(schedule))),
            "requires_deterministic_pass": list(DETERMINISTIC_ROWS),
        },
        "first_failure_policy": {
            "classes": ["harness_setup", "product"],
            "maximum_product_corrections": 1,
            "clean_boot_and_fresh_session_required": True,
            "matching_invariant_required_for_reject": True,
        },
        "evidence_requirements": {
            "external_descriptor_observer": True,
            "external_udev_observer": True,
            "external_linux_evdev_observer": True,
            "input_values": [0, 1, 2],
            "final_oracle_state": "UP",
            "immutable_run_files": list(REQUIRED_RUN_FILES),
        },
        "edge_assumptions": [{
            "id": "EA-07",
            "classification": "unclassified",
            "status": "ASSUMED_UNRESOLVED",
            "backstop": "frozen row matrix, applicability reasons, and exact-device terminal decision",
        }],
    }
    manifest["manifest_sha256"] = _addressed_hash(manifest, "manifest_sha256")
    content = _canonical_bytes(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        return verify_composite_manifest(output)
    return verify_composite_manifest(output)


def validate_composite_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("kind") != MANIFEST_KIND:
        raise CompositeQualificationError("composite manifest schema/kind mismatch")
    if manifest.get("manifest_sha256") != _addressed_hash(manifest, "manifest_sha256"):
        raise CompositeQualificationError("composite manifest addressed hash mismatch")
    if manifest.get("environment") != "composite-feasibility":
        raise CompositeQualificationError("manifest does not name the isolated feasibility environment")
    for label in ("firmware_binary", "pairing_record", "descriptor_expectation"):
        entry = manifest.get(label)
        if not isinstance(entry, Mapping) or len(entry.get("sha256", "")) != 64 or not isinstance(entry.get("path"), str):
            raise CompositeQualificationError(f"manifest {label} lineage is incomplete")
    pairing_entry = manifest["pairing_record"]
    if pairing_entry.get("pair_digest") != pairing_entry.get("sha256"):
        raise CompositeQualificationError("manifest exact-pair digest is missing or inconsistent")
    if manifest.get("interfaces") != {
        "cdc": 1,
        "standard_keyboard_hid": 1,
        "other_hid_usages": 0,
        "fixed_key": "KEY_SPACE",
    }:
        raise CompositeQualificationError("manifest interface set is not exactly CDC plus fixed Space keyboard HID")
    calibration = manifest.get("calibration")
    if not isinstance(calibration, Mapping) or calibration.get("candidate_thresholds_ms") != list(CALIBRATION_CANDIDATES_MS) or calibration.get("selected_shared_threshold_ms") not in CALIBRATION_CANDIDATES_MS:
        raise CompositeQualificationError("manifest calibration thresholds are incomplete")
    physical_counts = {
        "physical_initial_short_per_key": 3,
        "physical_initial_hold_per_key": 3,
        "physical_final_short_per_key": 1,
        "physical_final_hold_per_key": 1,
        "deterministic_short_per_key": 30,
        "deterministic_hold_per_key": 30,
    }
    if calibration.get("keys") != list(AGENT_KEYS) or any(
        calibration.get(name) != count for name, count in physical_counts.items()
    ):
        raise CompositeQualificationError("manifest revised physical/deterministic calibration counts are incomplete")
    if calibration.get("deterministic_candidate_thresholds_ms") != list(CALIBRATION_CANDIDATES_MS):
        raise CompositeQualificationError("manifest deterministic threshold candidates are incomplete")
    if calibration.get("limitation") != "No claim of 30 human short samples with zero crossings or 30 human holds all activating.":
        raise CompositeQualificationError("manifest human-sample limitation is missing")
    reset_paths = manifest.get("controlled_reset_paths")
    expected_counts = dict(ROW_COUNTS)
    if not isinstance(reset_paths, list) or not reset_paths:
        raise CompositeQualificationError("manifest controlled reset paths are missing")
    expected_counts["controlled-reset"] = len(reset_paths) * 5
    if manifest.get("descriptor_stability") != {
        "upload_reenumerations": 5,
        "software_resets": 0,
        "unplug_replugs": 0,
    }:
        raise CompositeQualificationError("manifest scoped descriptor stability changed")
    if manifest.get("row_counts") != expected_counts:
        raise CompositeQualificationError("manifest row counts differ from the bounded D-15 matrix")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or rows != _frozen_rows(expected_counts):
        raise CompositeQualificationError("manifest rows are incomplete, reordered, or not applicable")
    cdc = manifest.get("cdc")
    if cdc != {
        "steady_frames_each_direction": 1000,
        "burst_repetitions": 10,
        "burst_frames_each_direction": 100,
        "maximum_line_bytes_including_lf": 385,
    }:
        raise CompositeQualificationError("manifest CDC bounds changed")
    limits = manifest.get("latency_limits_ms")
    if limits != {
        "eligible_to_down_p95": 80,
        "eligible_to_down_hard_max": 120,
        "release_to_up_p95": 80,
        "release_to_up_hard_max": 120,
    }:
        raise CompositeQualificationError("manifest latency bounds changed")
    stress = manifest.get("stress")
    if not isinstance(stress, Mapping):
        raise CompositeQualificationError("manifest stress profile is missing")
    schedule = mixed_stress_schedule(stress.get("seed"))
    if stress.get("counts") != STRESS_COUNTS or stress.get("total") != 300 or stress.get("requires_deterministic_pass") != list(DETERMINISTIC_ROWS) or stress.get("schedule_sha256") != _sha256_bytes(_canonical_bytes(list(schedule))):
        raise CompositeQualificationError("manifest stress schedule is not finite, seeded, and count-equal")
    policy = manifest.get("first_failure_policy")
    if policy != {
        "classes": ["harness_setup", "product"],
        "maximum_product_corrections": 1,
        "clean_boot_and_fresh_session_required": True,
        "matching_invariant_required_for_reject": True,
    }:
        raise CompositeQualificationError("manifest first-failure policy changed")
    edge = manifest.get("edge_assumptions")
    if not isinstance(edge, list) or not any(item.get("id") == "EA-07" and item.get("status") == "ASSUMED_UNRESOLVED" for item in edge if isinstance(item, Mapping)):
        raise CompositeQualificationError("EA-07 must remain flagged in the frozen evidence")
    return dict(manifest)


def verify_composite_manifest(path: Path) -> dict[str, Any]:
    manifest = validate_composite_manifest(_load_object(Path(path), "composite manifest"))
    for label in ("firmware_binary", "pairing_record", "descriptor_expectation"):
        entry = manifest[label]
        source = Path(entry["path"])
        if not source.is_file() or source.is_symlink() or _sha256_file(source) != entry["sha256"]:
            raise CompositeQualificationError(f"manifest {label} source hash no longer matches")
    return manifest


@dataclass
class _InputOracle:
    state: str = "UP"
    failures: list[str] = field(default_factory=list)
    events_seen: int = 0
    last_monotonic_ns: int = -1

    def accept(self, event: Mapping[str, Any]) -> None:
        if self.events_seen >= MAX_INPUT_EVENTS:
            raise CompositeQualificationError("input trace exceeds its bounded event count")
        timestamp = event.get("monotonic_ns")
        if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < self.last_monotonic_ns:
            self.failures.append("input timestamps are missing or non-monotonic")
            return
        self.last_monotonic_ns = timestamp
        self.events_seen += 1
        event_type = event.get("type")
        if event_type == "EV_KEY":
            if event.get("code") != "KEY_SPACE" or event.get("value") not in (0, 1, 2):
                self.failures.append("observer recorded a non-Space or invalid key event")
                return
            value = event["value"]
            if value == 1:
                if self.state != "UP":
                    self.failures.append("duplicate Space down while oracle was DOWN")
                else:
                    self.state = "DOWN"
            elif value == 0:
                if self.state != "DOWN":
                    self.failures.append("Space up without a matching down")
                else:
                    self.state = "UP"
            elif self.state != "DOWN":
                self.failures.append("host repeat value 2 occurred while oracle was UP")
            return
        if event_type == "DEVICE_REMOVED":
            if event.get("verified") is not True:
                self.failures.append("device removal was not externally verified")
            else:
                self.state = "UP"
            return
        if event_type in {"FRESH_ENUMERATION", "REMOUNT"}:
            if event.get("empty") is not True:
                self.failures.append("fresh input enumeration did not prove an empty state")
            else:
                self.state = "UP"
            return
        if event_type == "SUSPEND":
            if event.get("empty") is not True:
                self.failures.append("suspend did not externally observe release-all")
            else:
                self.state = "UP"
            return
        if event_type == "RESUME":
            if self.state != "UP" or event.get("empty") is not True:
                self.failures.append("input state was active or non-empty after resume")
            return
        self.failures.append("input trace contains an unknown event type")

    def finish(self) -> dict[str, Any]:
        if self.state != "UP":
            self.failures.append("input trace ended DOWN without a Space up or verified teardown")
        return {"state": self.state, "events_seen": self.events_seen, "failures": list(self.failures)}


def validate_input_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the external Linux UP/DOWN oracle; never trust a claimed summary."""
    if trace.get("schema_version") != SCHEMA_VERSION or trace.get("kind") != INPUT_KIND:
        raise CompositeQualificationError("input trace schema/kind mismatch")
    if trace.get("observer") != "linux-evdev" or trace.get("external") is not True or trace.get("complete") is not True or trace.get("deferred") is not False:
        raise CompositeQualificationError("input trace is not complete external evdev evidence")
    events = trace.get("events")
    if not isinstance(events, list) or not events:
        raise CompositeQualificationError("input trace has no external events")
    oracle = _InputOracle()
    for event in events:
        if not isinstance(event, Mapping):
            raise CompositeQualificationError("input trace event is not an object")
        oracle.accept(event)
        if oracle.failures:
            raise CompositeQualificationError(oracle.failures[0])
    summary = oracle.finish()
    if summary["failures"] or summary["state"] != "UP":
        raise CompositeQualificationError(summary["failures"][0] if summary["failures"] else "input oracle did not end UP")
    if trace.get("final_state") != summary["state"] or trace.get("event_count") != summary["events_seen"]:
        raise CompositeQualificationError("input trace claimed oracle summary is not recomputable")
    return summary


class _LinuxInputObserver:
    """Bounded raw evdev reader for one already measured input device."""

    def __init__(self, device: Path, *, max_events: int = MAX_INPUT_EVENTS):
        self._device = Path(device)
        self._max_events = min(max_events, MAX_INPUT_EVENTS)

    def capture(self, seconds: float) -> dict[str, Any]:
        if seconds <= 0 or seconds > 3600:
            raise CompositeQualificationError("input observation duration must be within (0, 3600] seconds")
        fd = os.open(self._device, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        selector = selectors.DefaultSelector()
        events: list[dict[str, Any]] = []
        deadline = time.monotonic() + seconds
        try:
            selector.register(fd, selectors.EVENT_READ)
            while time.monotonic() < deadline and len(events) < self._max_events:
                for _key, _mask in selector.select(min(0.25, max(0.0, deadline - time.monotonic()))):
                    block = os.read(fd, _INPUT_EVENT.size * 64)
                    if not block:
                        events.append({"type": "DEVICE_REMOVED", "verified": True, "monotonic_ns": time.monotonic_ns()})
                        deadline = 0
                        break
                    if len(block) % _INPUT_EVENT.size:
                        raise CompositeQualificationError("evdev observer received a partial input_event")
                    for offset in range(0, len(block), _INPUT_EVENT.size):
                        _sec, _usec, event_type, code, value = _INPUT_EVENT.unpack_from(block, offset)
                        if event_type == _EV_KEY and code == _KEY_SPACE:
                            events.append({"type": "EV_KEY", "code": "KEY_SPACE", "value": value, "monotonic_ns": time.monotonic_ns()})
            if len(events) >= self._max_events:
                raise CompositeQualificationError("evdev observer reached its bounded event limit")
        finally:
            selector.close()
            os.close(fd)
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


class _UsbObserver:
    """Bounded external descriptor and udev observer; no discovery authority."""

    @staticmethod
    def command(argv: Sequence[str], timeout: float = 10.0) -> bytes:
        try:
            completed = subprocess.run(tuple(argv), check=True, capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            raise CompositeQualificationError(f"external observer failed: {' '.join(argv)}: {exc}") from exc
        if not completed.stdout:
            raise CompositeQualificationError(f"external observer returned no evidence: {' '.join(argv)}")
        return completed.stdout

    def descriptors(self, vid_pid: str) -> bytes:
        return self.command(("lsusb", "-v", "-d", vid_pid))

    def udev(self, sys_path: Path) -> dict[str, Any]:
        output = self.command(("udevadm", "info", "--query=property", "--path", str(sys_path)))
        return {"external": True, "complete": True, "observer": "udevadm", "sha256": _sha256_bytes(output)}


def _percentile(values: list[float], percentage: int) -> float:
    ordered = sorted(values)
    return ordered[max(0, (len(ordered) * percentage + 99) // 100 - 1)]


def _validate_latency(result: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    latency = result.get("latency")
    if not isinstance(latency, Mapping):
        raise CompositeQualificationError("run lacks latency evidence")
    limits = manifest["latency_limits_ms"]
    for name, p95_key, max_key in (
        ("eligible_to_down", "eligible_to_down_p95", "eligible_to_down_hard_max"),
        ("release_to_up", "release_to_up_p95", "release_to_up_hard_max"),
    ):
        entry = latency.get(name)
        if not isinstance(entry, Mapping):
            raise CompositeQualificationError(f"run lacks {name} latency evidence")
        samples = entry.get("samples_ms")
        minimum_samples = manifest["row_counts"]["input-latency"]
        if not isinstance(samples, list) or len(samples) < minimum_samples or any(
            not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 for value in samples
        ):
            raise CompositeQualificationError(
                f"run requires at least {minimum_samples} non-negative {name} samples"
            )
        p95 = _percentile(samples, 95)
        maximum = max(samples)
        if entry.get("count") != len(samples) or entry.get("p95_ms") != p95 or entry.get("max_ms") != maximum:
            raise CompositeQualificationError(f"run {name} latency summary is not recomputable")
        if p95 > limits[p95_key] or maximum > limits[max_key]:
            raise CompositeQualificationError(f"run exceeds the frozen {name} latency limit")


def _row_map(result: Mapping[str, Any], manifest: Mapping[str, Any], *, require_pass: bool) -> dict[str, Mapping[str, Any]]:
    rows = result.get("rows")
    if not isinstance(rows, list):
        raise CompositeQualificationError("run rows must be a list")
    mapped: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str) or row["id"] in mapped:
            raise CompositeQualificationError("run has an invalid or duplicate row")
        mapped[row["id"]] = row
    expected = set(manifest["row_counts"])
    if set(mapped) != expected:
        raise CompositeQualificationError("run does not contain every frozen row exactly once")
    if [row["id"] for row in rows] != list(manifest["row_counts"]):
        raise CompositeQualificationError("run rows do not follow the frozen deterministic order")
    manifest_rows = {row["id"]: row for row in manifest["rows"]}
    for row_id, required_count in manifest["row_counts"].items():
        row = mapped[row_id]
        frozen = manifest_rows[row_id]
        if frozen["applicable"] is False:
            if (
                row.get("applicable") is not False
                or row.get("required_count") != 0
                or row.get("observed_count") != 0
                or row.get("status") != "not-applicable"
                or row.get("reason") != frozen["reason"]
            ):
                raise CompositeQualificationError(
                    f"row {row_id} differs from its frozen Plan 09 deferral"
                )
            continue
        if row.get("applicable") is not True or row.get("required_count") != required_count:
            raise CompositeQualificationError(f"row {row_id} differs from its frozen applicability/count")
        if not isinstance(row.get("observed_count"), int) or isinstance(row.get("observed_count"), bool) or row["observed_count"] < 0:
            raise CompositeQualificationError(f"row {row_id} has an invalid observed count")
        if require_pass and (row.get("status") != "pass" or row["observed_count"] != required_count):
            raise CompositeQualificationError(f"PASS row {row_id} is missing, failed, or count-incomplete")
    return mapped


def _validate_traffic(traffic: Mapping[str, Any], manifest: Mapping[str, Any], run_id: str, *, require_pass: bool) -> None:
    if traffic.get("schema_version") != SCHEMA_VERSION or traffic.get("kind") != TRAFFIC_KIND or traffic.get("run_id") != run_id:
        raise CompositeQualificationError("traffic evidence schema/kind/run mismatch")
    counts = traffic.get("counts")
    expected = 1000 + 10 * 100
    if not isinstance(counts, Mapping):
        raise CompositeQualificationError("traffic evidence lacks counters")
    for direction in ("host_to_device", "device_to_host"):
        entry = counts.get(direction)
        if not isinstance(entry, Mapping):
            raise CompositeQualificationError(f"traffic evidence lacks {direction} counters")
        if require_pass and any(entry.get(name) != expected for name in ("expected", "sent", "received", "acknowledged")):
            raise CompositeQualificationError(f"PASS lacks exact CDC equality for {direction}")
    strict = traffic.get("strict_counters")
    if not isinstance(strict, Mapping) or set(strict) != set(STRICT_COUNTERS) or any(not isinstance(value, int) or value < 0 for value in strict.values()):
        raise CompositeQualificationError("traffic strict counters are incomplete")
    if require_pass and any(strict.values()):
        raise CompositeQualificationError("PASS has a nonzero strict CDC counter")
    if traffic.get("maximum_line_bytes_including_lf") != manifest["cdc"]["maximum_line_bytes_including_lf"]:
        raise CompositeQualificationError("traffic evidence changed the bounded CDC line limit")
    if require_pass and (traffic.get("overlong_rejected") is not True or traffic.get("next_valid_accepted") is not True):
        raise CompositeQualificationError("PASS lacks fail-closed overlong-line recovery evidence")


def _validate_result(
    result: Mapping[str, Any], manifest: Mapping[str, Any], traffic: Mapping[str, Any],
    input_trace: Mapping[str, Any], descriptor_bytes: bytes,
) -> None:
    if result.get("schema_version") != SCHEMA_VERSION or result.get("kind") != RESULT_KIND:
        raise CompositeQualificationError("run result schema/kind mismatch")
    run_id = _require_string(result.get("run_id"), "run_id")
    if result.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise CompositeQualificationError("run result does not link the frozen manifest")
    status = result.get("status")
    if status not in {"PASS", "FAIL"}:
        raise CompositeQualificationError("run status must be PASS or FAIL")
    require_pass = status == "PASS"
    rows = _row_map(result, manifest, require_pass=require_pass)
    _validate_traffic(traffic, manifest, run_id, require_pass=require_pass)
    if input_trace.get("run_id") != run_id:
        raise CompositeQualificationError("input trace run_id mismatch")
    if require_pass or input_trace.get("complete") is True:
        oracle = validate_input_trace(input_trace)
        if result.get("input_oracle") != oracle:
            raise CompositeQualificationError("result input oracle summary is not recomputable")
    else:
        if input_trace.get("schema_version") != SCHEMA_VERSION or input_trace.get("kind") != INPUT_KIND:
            raise CompositeQualificationError("failed input trace schema/kind mismatch")
        events = input_trace.get("events")
        if not isinstance(events, list) or len(events) > MAX_INPUT_EVENTS:
            raise CompositeQualificationError("failed input trace is not a bounded event list")
    descriptor = result.get("descriptor_observation")
    if not isinstance(descriptor, Mapping):
        raise CompositeQualificationError("run lacks typed descriptor observation")
    if descriptor.get("sha256") != _sha256_bytes(descriptor_bytes):
        raise CompositeQualificationError("descriptor observation hash mismatch")
    if require_pass and (descriptor.get("external") is not True or descriptor.get("complete") is not True):
        raise CompositeQualificationError("PASS lacks complete external descriptor observation")
    if require_pass and any(descriptor.get(name) != expected for name, expected in {
        "cdc_interfaces": 1,
        "keyboard_hid_interfaces": 1,
        "other_hid_usages": 0,
        "stable_after_resets": manifest["descriptor_stability"]["software_resets"],
        "stable_after_unplugs": manifest["descriptor_stability"]["unplug_replugs"],
        "stable_after_uploads": manifest["descriptor_stability"]["upload_reenumerations"],
    }.items()):
        raise CompositeQualificationError("PASS descriptor/interface set is incomplete or unstable")
    udev = result.get("udev_observation")
    if not isinstance(udev, Mapping):
        raise CompositeQualificationError("run lacks typed udev observation")
    if require_pass and (udev.get("external") is not True or udev.get("complete") is not True):
        raise CompositeQualificationError("PASS lacks complete external udev evidence")
    if require_pass and any(result.get(name) for name in ("blockers", "deferred", "open_defects")):
        raise CompositeQualificationError("PASS has a blocker, deferred fact, or open defect")
    failure_class = result.get("failure_class")
    if require_pass:
        if failure_class is not None or result.get("preflight_status") != "pass" or result.get("clean_boot") is not True:
            raise CompositeQualificationError("PASS lacks clean preflight/boot evidence")
        _validate_latency(result, manifest)
        stress = result.get("stress")
        if manifest["rows"][-1]["applicable"] is False:
            if stress != {
                "status": "not-applicable",
                "reason": manifest["rows"][-1]["reason"],
            }:
                raise CompositeQualificationError("Plan 00 stress deferral differs from the frozen manifest")
        else:
            schedule = mixed_stress_schedule(manifest["stress"]["seed"])
            if not isinstance(stress, Mapping) or stress.get("started_after_deterministic_pass") is not True:
                raise CompositeQualificationError("mixed stress ran before deterministic lifecycle rows passed")
            if any(rows[name].get("status") != "pass" for name in DETERMINISTIC_ROWS):
                raise CompositeQualificationError("mixed stress prerequisites did not pass")
            if stress.get("schedule_sha256") != _sha256_bytes(_canonical_bytes(list(schedule))) or stress.get("scheduled_counts") != STRESS_COUNTS or stress.get("observed_counts") != STRESS_COUNTS or stress.get("invariant_failures") != []:
                raise CompositeQualificationError("mixed stress is incomplete, unequal, or has an invariant failure")
    else:
        if failure_class not in {"harness_setup", "product"}:
            raise CompositeQualificationError("failed run must classify its first failure")
        failure = result.get("first_failure")
        if not isinstance(failure, Mapping) or failure.get("row_id") not in rows or not isinstance(failure.get("invariant"), str) or not failure["invariant"]:
            raise CompositeQualificationError("failed run does not preserve its first failing invariant")
        if failure_class == "product" and result.get("preflight_status") != "pass":
            raise CompositeQualificationError("product failure is forbidden when preflight did not pass")


def _parse_sums(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise CompositeQualificationError("invalid SHA256SUMS entry")
        name = Path(parts[1])
        if name.is_absolute() or ".." in name.parts or name.name == "SHA256SUMS" or name.as_posix() in expected:
            raise CompositeQualificationError("SHA256SUMS contains an unsafe or duplicate path")
        expected[name.as_posix()] = parts[0]
    return expected


def verify_composite_run(directory: Path, *, manifest_path: Path | None = None) -> dict[str, Any]:
    directory = Path(directory).resolve()
    if not directory.is_dir() or directory.is_symlink():
        raise CompositeQualificationError("composite run must be a non-symlink directory")
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if actual != set(REQUIRED_RUN_FILES):
        raise CompositeQualificationError("immutable run file set is missing, extra, or nested")
    sums = _parse_sums(directory / "SHA256SUMS")
    hashed_files = set(REQUIRED_RUN_FILES) - {"SHA256SUMS"}
    if set(sums) != hashed_files:
        raise CompositeQualificationError("SHA256SUMS does not cover the exact immutable run file set")
    for name, digest in sums.items():
        if _sha256_file(directory / name) != digest:
            raise CompositeQualificationError(f"immutable run hash mismatch for {name}")
    manifest = validate_composite_manifest(_load_object(directory / "manifest.json", "run manifest"))
    if manifest_path is not None:
        frozen = verify_composite_manifest(manifest_path)
        if manifest != frozen or _sha256_file(directory / "manifest.json") != _sha256_file(manifest_path):
            raise CompositeQualificationError("run manifest is not the exact frozen manifest")
    result = _load_object(directory / "result.json", "run result")
    traffic = _load_object(directory / "traffic.json", "run traffic")
    input_trace = _load_object(directory / "input-events.json", "run input trace")
    descriptor_bytes = (directory / "usb-descriptors.txt").read_bytes()
    if not descriptor_bytes:
        raise CompositeQualificationError("run descriptor capture is empty")
    _validate_result(result, manifest, traffic, input_trace, descriptor_bytes)
    if result["run_id"] != directory.name or traffic.get("run_id") != directory.name:
        raise CompositeQualificationError("immutable run directory does not match its run_id")
    return {
        "directory": directory,
        "manifest": manifest,
        "result": result,
        "traffic": traffic,
        "input_trace": input_trace,
        "hashes": {**sums, "SHA256SUMS": _sha256_file(directory / "SHA256SUMS")},
    }


def record_composite_run(
    manifest_path: Path,
    evidence_root: Path,
    run_id: str,
    result: Mapping[str, Any],
    traffic: Mapping[str, Any],
    input_trace: Mapping[str, Any],
    usb_descriptors: bytes,
) -> Path:
    """Write one exact immutable run; a failed write is preserved for diagnosis."""
    if not isinstance(run_id, str) or not run_id or any(token in run_id for token in ("/", "\\")) or run_id in {".", ".."}:
        raise CompositeQualificationError("run_id must be one non-empty path component")
    manifest = verify_composite_manifest(manifest_path)
    root = Path(evidence_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / run_id
    if target.exists():
        raise CompositeQualificationError(f"immutable run already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=root))
    try:
        files = {
            "manifest.json": _canonical_bytes(manifest),
            "result.json": _canonical_bytes(dict(result)),
            "traffic.json": _canonical_bytes(dict(traffic)),
            "input-events.json": _canonical_bytes(dict(input_trace)),
            "usb-descriptors.txt": bytes(usb_descriptors),
        }
        for name, content in files.items():
            (temporary / name).write_bytes(content)
        checksums = "".join(f"{_sha256_file(temporary / name)}  {name}\n" for name in sorted(files)).encode("ascii")
        (temporary / "SHA256SUMS").write_bytes(checksums)
        temporary.rename(target)
        verified = verify_composite_run(target, manifest_path=manifest_path)
        if verified["result"].get("run_id") != run_id:
            raise CompositeQualificationError("recorded run_id mismatch")
        return target
    except Exception as exc:
        if temporary.exists():
            failed = root / f"failed-attempt-{run_id}-{time.time_ns()}"
            temporary.rename(failed)
            raise CompositeQualificationError(f"evidence write preserved as {failed}: {exc}") from exc
        if target.exists():
            failed = root / f"failed-attempt-{run_id}-{time.time_ns()}"
            target.rename(failed)
            raise CompositeQualificationError(f"evidence write preserved as {failed}: {exc}") from exc
        raise


def _run_link(run: Mapping[str, Any], root: Path) -> dict[str, Any]:
    directory = Path(run["directory"])
    hashes = run["hashes"]
    return {
        "path": directory.relative_to(root).as_posix(),
        "result_sha256": hashes["result.json"],
        "traffic_sha256": hashes["traffic.json"],
        "input_events_sha256": hashes["input-events.json"],
        "usb_descriptors_sha256": hashes["usb-descriptors.txt"],
        "checksums_sha256": hashes["SHA256SUMS"],
        "boot_id": run["result"].get("boot_id"),
        "session_id": run["result"].get("session_id"),
    }


def write_terminal_decision(
    output: Path,
    manifest_path: Path,
    *,
    status: str,
    run_directory: Path | None = None,
    first_failure_directory: Path | None = None,
    retest_directory: Path | None = None,
    correction: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one immutable PASS or D-16 reproducible-product REJECT decision."""
    output = Path(output).resolve()
    sidecar = output.with_suffix(output.suffix + ".sha256")
    if output.exists() or sidecar.exists():
        raise CompositeQualificationError("terminal composite decision already exists and cannot be replaced")
    root = output.parent
    manifest_path = _safe_file(manifest_path, root, "decision manifest")
    manifest = verify_composite_manifest(manifest_path)
    decision: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": DECISION_KIND,
        "status": status,
        "terminal": True,
        "manifest_path": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": manifest["manifest_sha256"],
        "deployment": {
            "firmware_binary_sha256": manifest["firmware_binary"]["sha256"],
            "pairing_record_sha256": manifest["pairing_record"]["sha256"],
            "pair_digest": manifest["pairing_record"]["pair_digest"],
            "descriptor_expectation_sha256": manifest["descriptor_expectation"]["sha256"],
        },
    }
    if status == "PASS":
        if run_directory is None or any(value is not None for value in (first_failure_directory, retest_directory, correction)):
            raise CompositeQualificationError("PASS requires exactly one clean run and no correction lineage")
        run = verify_composite_run(_safe_file(Path(run_directory) / "result.json", root, "PASS run").parent, manifest_path=manifest_path)
        if run["result"]["status"] != "PASS":
            raise CompositeQualificationError("terminal PASS does not link a passing run")
        decision["run"] = _run_link(run, root)
    elif status == "REJECT":
        if first_failure_directory is None or retest_directory is None or correction is None or run_directory is not None:
            raise CompositeQualificationError("REJECT requires first failure, one correction, and clean retest")
        first = verify_composite_run(_safe_file(Path(first_failure_directory) / "result.json", root, "first failure run").parent, manifest_path=manifest_path)
        retest = verify_composite_run(_safe_file(Path(retest_directory) / "result.json", root, "retest run").parent, manifest_path=manifest_path)
        first_result = first["result"]
        retest_result = retest["result"]
        if first_result.get("status") != "FAIL" or retest_result.get("status") != "FAIL" or first_result.get("failure_class") != "product" or retest_result.get("failure_class") != "product":
            raise CompositeQualificationError("REJECT requires two preserved product failures")
        first_failure = first_result.get("first_failure", {})
        repeated_failure = retest_result.get("first_failure", {})
        if first_failure.get("invariant") != repeated_failure.get("invariant") or first_failure.get("row_id") != repeated_failure.get("row_id"):
            raise CompositeQualificationError("REJECT retest did not reproduce the same product invariant")
        if retest_result.get("clean_boot") is not True or first_result.get("boot_id") == retest_result.get("boot_id") or first_result.get("session_id") == retest_result.get("session_id"):
            raise CompositeQualificationError("REJECT retest lacks a clean boot and fresh session")
        if not isinstance(correction, Mapping) or correction.get("count") != 1 or not isinstance(correction.get("target"), str) or not correction["target"] or not isinstance(correction.get("description"), str) or not correction["description"]:
            raise CompositeQualificationError("REJECT correction lineage must name exactly one targeted correction")
        rerun_rows = retest_result.get("rerun_rows")
        if not isinstance(rerun_rows, list) or set(rerun_rows) != set(manifest["row_counts"]):
            raise CompositeQualificationError("REJECT retest did not rerun the complete affected gate")
        decision["first_failure"] = _run_link(first, root)
        decision["correction"] = dict(correction)
        decision["retest"] = _run_link(retest, root)
        decision["reproduced_invariant"] = {
            "row_id": first_failure["row_id"],
            "invariant": first_failure["invariant"],
        }
    else:
        raise CompositeQualificationError("terminal decision status must be PASS or REJECT")
    decision["decision_sha256"] = _addressed_hash(decision, "decision_sha256")
    content = _canonical_bytes(decision)
    digest = hashlib.sha256(content).hexdigest().encode("ascii") + b"\n"
    atomic_write_pair(output, content, digest)
    return verify_composite_decision(output, require_terminal=True, require_immutable_lineage=True)


def _verify_run_link(link: Any, root: Path, manifest_path: Path, label: str) -> dict[str, Any]:
    if not isinstance(link, Mapping):
        raise CompositeQualificationError(f"decision lacks {label} run linkage")
    run_result = _safe_file(Path(link.get("path", "")) / "result.json", root, label)
    run = verify_composite_run(run_result.parent, manifest_path=manifest_path)
    expected = _run_link(run, root)
    if dict(link) != expected:
        raise CompositeQualificationError(f"decision {label} run hash/identity lineage mismatch")
    return run


def verify_composite_decision(
    path: Path, *, require_terminal: bool = False, require_immutable_lineage: bool = False,
) -> dict[str, Any]:
    """Reopen a terminal decision and every linked byte without hardware access."""
    path = Path(path).resolve()
    decision = _load_object(path, "composite decision")
    if decision.get("schema_version") != SCHEMA_VERSION or decision.get("kind") != DECISION_KIND:
        raise CompositeQualificationError("composite decision schema/kind mismatch")
    if decision.get("decision_sha256") != _addressed_hash(decision, "decision_sha256"):
        raise CompositeQualificationError("composite decision addressed hash mismatch")
    if require_terminal and decision.get("terminal") is not True:
        raise CompositeQualificationError("composite decision is not terminal")
    if decision.get("status") not in {"PASS", "REJECT"} or decision.get("terminal") is not True:
        raise CompositeQualificationError("decision must be one terminal PASS or REJECT")
    root = path.parent
    manifest_path = _safe_file(Path(decision.get("manifest_path", "")), root, "decision manifest")
    manifest = verify_composite_manifest(manifest_path)
    if decision.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise CompositeQualificationError("decision manifest hash lineage mismatch")
    if decision.get("deployment") != {
        "firmware_binary_sha256": manifest["firmware_binary"]["sha256"],
        "pairing_record_sha256": manifest["pairing_record"]["sha256"],
        "pair_digest": manifest["pairing_record"]["pair_digest"],
        "descriptor_expectation_sha256": manifest["descriptor_expectation"]["sha256"],
    }:
        raise CompositeQualificationError("decision exact deployment lineage mismatch")
    if decision["status"] == "PASS":
        if any(name in decision for name in ("first_failure", "correction", "retest", "reproduced_invariant")):
            raise CompositeQualificationError("PASS contains forbidden failure/correction lineage")
        run = _verify_run_link(decision.get("run"), root, manifest_path, "PASS")
        if run["result"]["status"] != "PASS":
            raise CompositeQualificationError("decision PASS links a non-passing run")
    else:
        if "run" in decision:
            raise CompositeQualificationError("REJECT contains a PASS run field")
        first = _verify_run_link(decision.get("first_failure"), root, manifest_path, "first failure")
        retest = _verify_run_link(decision.get("retest"), root, manifest_path, "retest")
        correction = decision.get("correction")
        repeated = decision.get("reproduced_invariant")
        first_failure = first["result"].get("first_failure", {})
        retest_failure = retest["result"].get("first_failure", {})
        if first["result"].get("failure_class") != "product" or retest["result"].get("failure_class") != "product":
            raise CompositeQualificationError("harness/setup failure cannot reject composite")
        same_failure = (
            first_failure.get("row_id") == retest_failure.get("row_id")
            and first_failure.get("invariant") == retest_failure.get("invariant")
        )
        if not same_failure or repeated != {
            "row_id": first_failure.get("row_id"), "invariant": first_failure.get("invariant")
        }:
            raise CompositeQualificationError("REJECT does not reproduce one matching product invariant")
        if not isinstance(correction, Mapping) or correction.get("count") != 1:
            raise CompositeQualificationError("REJECT does not preserve exactly one correction")
        if retest["result"].get("clean_boot") is not True or first["result"].get("boot_id") == retest["result"].get("boot_id") or first["result"].get("session_id") == retest["result"].get("session_id"):
            raise CompositeQualificationError("REJECT does not link a clean fresh-session retest")
        if set(retest["result"].get("rerun_rows", ())) != set(manifest["row_counts"]):
            raise CompositeQualificationError("REJECT retest did not cover the affected gate")
    if require_immutable_lineage:
        sidecar = path.with_suffix(path.suffix + ".sha256")
        try:
            fields = sidecar.read_text(encoding="ascii").split()
        except (OSError, UnicodeError) as exc:
            raise CompositeQualificationError(f"decision checksum sidecar is unavailable: {exc}") from exc
        if len(fields) != 1 or fields[0] != _sha256_file(path):
            raise CompositeQualificationError("decision checksum sidecar mismatch")
    return decision


def _require_guided_bridge_lock() -> None:
    try:
        from .serial_link import require_inherited_bridge_lock

        require_inherited_bridge_lock()
    except RuntimeError as exc:
        raise CompositeQualificationError(
            f"exclusive bridge lock is required for guided composite preflight: {exc}"
        ) from exc


def _run_guided_command(argv: tuple[str, ...], cwd: Path) -> bytes:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        output = getattr(exc, "stdout", b"") or b""
        detail = output.decode("utf-8", errors="replace")[-4000:]
        raise CompositeQualificationError(
            f"guided composite command failed: {' '.join(argv)}"
            + (f"\n{detail}" if detail else "")
        ) from exc
    return completed.stdout


def _serial_ports() -> list[Any]:
    try:
        from serial.tools import list_ports
    except ImportError as exc:
        raise CompositeQualificationError("pyserial is unavailable for composite discovery") from exc
    return list(list_ports.comports())


def _exact_paired_port(binding_path: Path) -> tuple[Any, dict[str, Any]]:
    from .pairing import PairingStore
    from .serial_link import reconnect_exact

    binding = PairingStore(binding_path).load()
    if binding is None:
        raise CompositeQualificationError(f"pairing binding is missing: {binding_path}")

    def opener(candidate: Any) -> Any:
        try:
            import serial
        except ImportError as exc:
            raise CompositeQualificationError("pyserial is unavailable for exact pairing") from exc
        return serial.Serial(candidate.device, 115200, timeout=0.2, write_timeout=2.0)

    try:
        selected, link, session, _transitions = reconnect_exact(
            binding, ports=None, opener=opener, timeout=5.0
        )
    except Exception as exc:
        raise CompositeQualificationError(
            f"current selected-usb exact pairing preflight failed: {exc}"
        ) from exc
    try:
        hello = dict(session.device)
        if (
            hello.get("device_id") != binding.device_id
            or hello.get("protocol") != binding.protocol
            or hello.get("firmware") != binding.firmware
        ):
            raise CompositeQualificationError(
                "current selected-usb hello differs from the exact pairing binding"
            )
        return selected, hello
    finally:
        link.close()


def _wait_for_composite_port(previous: Any, timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    previous_serial = getattr(previous, "serial_number", None)
    previous_path = getattr(previous, "device", None)
    previous_pid = getattr(previous, "pid", None)
    normalized_previous_serial = (
        "".join(character for character in previous_serial.casefold() if character.isalnum())
        if isinstance(previous_serial, str)
        else None
    )
    while time.monotonic() < deadline:
        candidates = [
            port
            for port in _serial_ports()
            if getattr(port, "device", None)
            and getattr(port, "vid", None) is not None
            and getattr(port, "pid", None) is not None
        ]
        exact_serial = [
            port
            for port in candidates
            if normalized_previous_serial
            and isinstance(getattr(port, "serial_number", None), str)
            and "".join(
                character
                for character in port.serial_number.casefold()
                if character.isalnum()
            )
            == normalized_previous_serial
        ]
        if len(exact_serial) == 1:
            return exact_serial[0]
        changed_espressif = [
            port
            for port in candidates
            if getattr(port, "vid", None) == 0x303A
            and (
                getattr(port, "device", None) != previous_path
                or getattr(port, "pid", None) != previous_pid
            )
        ]
        if len(changed_espressif) == 1:
            return changed_espressif[0]
        time.sleep(0.2)
    raise CompositeQualificationError(
        "composite CDC did not enumerate as one unambiguous exact-device candidate"
    )


def _capture_guided_descriptors(vid_pid: str) -> bytes:
    return _UsbObserver().descriptors(vid_pid)


def _udev_properties(device: Path) -> dict[str, str]:
    output = _UsbObserver.command(
        ("udevadm", "info", "--query=property", "--name", str(device))
    )
    properties: dict[str, str] = {}
    for line in output.decode("utf-8", errors="strict").splitlines():
        name, separator, value = line.partition("=")
        if separator and name:
            properties[name] = value
    return properties


def _find_guided_keyboard_event(
    vid_pid: str, usb_serial: str | None, timeout: float = 20.0
) -> Path:
    vid, pid = vid_pid.split(":", 1)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches: list[Path] = []
        for event in sorted(Path("/dev/input").glob("event*")):
            try:
                properties = _udev_properties(event)
            except CompositeQualificationError:
                continue
            if (
                properties.get("ID_INPUT_KEYBOARD") == "1"
                and properties.get("ID_VENDOR_ID", "").lower() == vid
                and properties.get("ID_MODEL_ID", "").lower() == pid
                and (
                    not usb_serial
                    or properties.get("ID_SERIAL_SHORT") in {usb_serial, None}
                )
            ):
                matches.append(event)
        if len(matches) == 1:
            try:
                fd = os.open(matches[0], os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            except PermissionError:
                # logind applies the uaccess ACL after the input node appears.
                # Keep the bounded discovery window alive across that transient.
                pass
            except OSError as exc:
                raise CompositeQualificationError(
                    f"Linux evdev observer cannot read {matches[0]}: {exc}"
                ) from exc
            else:
                os.close(fd)
                return matches[0]
        if len(matches) > 1:
            raise CompositeQualificationError(
                "composite HID observer found multiple matching keyboard event devices"
            )
        time.sleep(0.2)
    raise CompositeQualificationError(
        "composite HID did not expose one readable Linux keyboard event device"
    )


def _probe_guided_status(cdc_path: str, timeout: float = 8.0) -> dict[str, Any]:
    try:
        import serial
    except ImportError as exc:
        raise CompositeQualificationError("pyserial is unavailable for tracer preflight") from exc
    deadline = time.monotonic() + timeout
    try:
        connection = serial.Serial(
            cdc_path, 115200, timeout=0.2, write_timeout=2.0
        )
    except Exception as exc:
        raise CompositeQualificationError(
            f"composite CDC observer could not open {cdc_path}: {exc}"
        ) from exc
    try:
        connection.reset_input_buffer()
        while time.monotonic() < deadline:
            connection.write(b'{"op":"status","id":"guided-preflight"}\n')
            connection.flush()
            response_deadline = min(deadline, time.monotonic() + 1.0)
            while time.monotonic() < response_deadline:
                raw = connection.readline()
                if not raw:
                    continue
                try:
                    message = json.loads(raw.decode("ascii"))
                except (UnicodeError, json.JSONDecodeError):
                    continue
                if (
                    isinstance(message, dict)
                    and message.get("event") == "status"
                    and message.get("id") == "guided-preflight"
                ):
                    if message.get("requires_clean_release") is True:
                        time.sleep(0.1)
                        break
                    return message
        raise CompositeQualificationError(
            "composite CDC did not return a clean-release status before timeout"
        )
    finally:
        connection.close()


def prepare_guided_composite_preflight(
    project_root: Path,
    binding_path: Path,
    evidence_root: Path,
    run_id: str,
) -> dict[str, Any]:
    """Build recovery + tracer, upload once, and freeze the exact observer checkpoint."""
    _require_guided_bridge_lock()
    if (
        not isinstance(run_id, str)
        or not run_id
        or any(token in run_id for token in ("/", "\\"))
        or run_id in {".", ".."}
    ):
        raise CompositeQualificationError("guided run_id must be one path component")
    root = Path(project_root).resolve()
    binding_path = Path(binding_path).resolve()
    evidence_root = Path(evidence_root).resolve()
    if evidence_root == root or root not in evidence_root.parents:
        raise CompositeQualificationError("guided evidence root must be inside the project")
    receipt_path = evidence_root / f"{run_id}-preflight.json"
    descriptors_path = evidence_root / f"{run_id}-usb-descriptors.txt"
    if receipt_path.exists() or descriptors_path.exists():
        raise CompositeQualificationError(
            "guided preflight artifacts already exist and cannot be overwritten"
        )
    python = root / "tools/phase1_bringup/.venv/bin/python3"
    if not python.exists():
        raise CompositeQualificationError("project-local Python/PlatformIO environment is missing")

    previous, previous_hello = _exact_paired_port(binding_path)
    commands = [
        (str(python), "-m", "platformio", "run", "-e", "selected-usb"),
        (str(python), "-m", "platformio", "run", "-e", "composite-feasibility"),
        (
            str(python),
            "-m",
            "platformio",
            "run",
            "-e",
            "composite-feasibility",
            "-t",
            "upload",
        ),
    ]
    command_hashes: list[str] = []
    for command in commands:
        command_hashes.append(_sha256_bytes(_run_guided_command(command, root)))

    recovery = root / ".pio/build/selected-usb/firmware.bin"
    composite = root / ".pio/build/composite-feasibility/firmware.bin"
    for path, label in ((recovery, "selected-usb recovery"), (composite, "composite")):
        if not path.is_file() or path.is_symlink():
            raise CompositeQualificationError(f"{label} firmware binary is missing after build")

    port = _wait_for_composite_port(previous)
    vid = getattr(port, "vid", None)
    pid = getattr(port, "pid", None)
    if not isinstance(vid, int) or not isinstance(pid, int):
        raise CompositeQualificationError("composite CDC lacks a measured VID/PID")
    vid_pid = f"{vid:04x}:{pid:04x}"
    descriptor_bytes = _capture_guided_descriptors(vid_pid)
    if not descriptor_bytes:
        raise CompositeQualificationError("composite descriptor capture is empty")
    event_path = _find_guided_keyboard_event(
        vid_pid, getattr(port, "serial_number", None)
    )
    status = _probe_guided_status(str(port.device))
    if (
        status.get("usb_started") is not True
        or status.get("usb_suspended") is not False
        or status.get("hid_ready") is not True
        or status.get("space_active") is not False
        or status.get("requires_clean_release") is not False
    ):
        raise CompositeQualificationError(
            "composite tracer preflight is not clean, HID-ready, and Space-UP"
        )

    binding_bytes = binding_path.read_bytes()
    descriptor_sha = _sha256_bytes(descriptor_bytes)
    observed_ns = time.time_ns()
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "composite-guided-preflight",
        "run_id": run_id,
        "current_row": "exact-pairing",
        "current_step": "physical-key-challenge",
        "project_root": root.as_posix(),
        "binding_path": binding_path.as_posix(),
        "pairing_record_sha256": _sha256_bytes(binding_bytes),
        "paired_device_id": previous_hello.get("device_id"),
        "previous_application_hello": previous_hello,
        "recovery_firmware_sha256": _sha256_file(recovery),
        "composite_firmware_sha256": _sha256_file(composite),
        "build_upload_output_sha256": command_hashes,
        "cdc_path": str(port.device),
        "keyboard_event_path": event_path.as_posix(),
        "usb": {
            "vid_pid": vid_pid,
            "serial": getattr(port, "serial_number", None),
            "manufacturer": getattr(port, "manufacturer", None),
            "product": getattr(port, "product", None),
            "descriptor_sha256": descriptor_sha,
        },
        "status": status,
        "observed_usb_boot_id": "usb-observation:"
        + _sha256_bytes(
            descriptor_bytes
            + _canonical_bytes(status)
            + str(observed_ns).encode("ascii")
        )[:32],
        "qualification_session_id": "cdc-session:"
        + _sha256_bytes(
            f"{run_id}\0{port.device}\0{observed_ns}".encode("utf-8")
        )[:32],
        "observer_ready": {
            "lsusb": True,
            "udevadm": True,
            "linux_evdev_readable": True,
            "cdc_status": True,
            "oracle_state": "UP",
        },
        "immediate_action": "Press and release physical agent key 1 exactly once.",
    }
    evidence_root.mkdir(parents=True, exist_ok=True)
    try:
        with descriptors_path.open("xb") as stream:
            stream.write(descriptor_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        with receipt_path.open("xb") as stream:
            stream.write(_canonical_bytes(receipt))
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        for path in (receipt_path, descriptors_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    return receipt


def wait_for_guided_pairing_challenge(
    receipt: Mapping[str, Any], evidence_root: Path, timeout: float = 600.0
) -> Path:
    """Observe one exact physical key-1 down/up pair while the bridge lock stays held."""
    _require_guided_bridge_lock()
    if receipt.get("current_row") != "exact-pairing":
        raise CompositeQualificationError(
            "guided pairing challenge requires the exact-pairing preflight row"
        )
    run_id = _require_string(receipt.get("run_id"), "guided run_id")
    cdc_path = _require_string(receipt.get("cdc_path"), "guided CDC path")
    output = Path(evidence_root).resolve() / f"{run_id}-pairing-challenge.json"
    if output.exists():
        raise CompositeQualificationError(
            "guided pairing challenge already exists and cannot be overwritten"
        )
    try:
        import serial
    except ImportError as exc:
        raise CompositeQualificationError(
            "pyserial is unavailable for the physical pairing challenge"
        ) from exc
    try:
        connection = serial.Serial(
            cdc_path, 115200, timeout=0.2, write_timeout=2.0
        )
    except Exception as exc:
        raise CompositeQualificationError(
            f"guided pairing challenge could not open {cdc_path}: {exc}"
        ) from exc
    events: list[dict[str, Any]] = []
    saw_down = False
    deadline = time.monotonic() + timeout
    try:
        connection.reset_input_buffer()
        while time.monotonic() < deadline:
            raw = connection.readline()
            if not raw:
                continue
            try:
                message = json.loads(raw.decode("ascii"))
            except (UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(message, dict) or message.get("event") != "key":
                continue
            slot = message.get("slot")
            state = message.get("state")
            if slot != 0 or state not in {"down", "up"}:
                raise CompositeQualificationError(
                    "physical pairing challenge observed the wrong key or state"
                )
            events.append({
                "slot": slot,
                "state": state,
                "device_at_us": message.get("at_us"),
                "host_monotonic_ns": time.monotonic_ns(),
            })
            if state == "down":
                if saw_down:
                    raise CompositeQualificationError(
                        "physical pairing challenge observed duplicate key down"
                    )
                saw_down = True
            elif not saw_down:
                raise CompositeQualificationError(
                    "physical pairing challenge observed key up before down"
                )
            else:
                break
        else:
            raise CompositeQualificationError(
                "physical pairing challenge timed out before key-1 down/up"
            )
    finally:
        connection.close()
    challenge = {
        "schema_version": SCHEMA_VERSION,
        "kind": "composite-guided-pairing-challenge",
        "run_id": run_id,
        "row_id": "exact-pairing",
        "step_id": "physical-key-challenge",
        "paired_device_id": receipt.get("paired_device_id"),
        "pairing_record_sha256": receipt.get("pairing_record_sha256"),
        "composite_firmware_sha256": receipt.get("composite_firmware_sha256"),
        "usb": receipt.get("usb"),
        "cdc_path": cdc_path,
        "events": events,
        "status": "pass",
    }
    with output.open("xb") as stream:
        stream.write(_canonical_bytes(challenge))
        stream.flush()
        os.fsync(stream.fileno())
    return output


def run_composite_qualification(
    manifest_path: Path, bundle_path: Path, evidence_root: Path, run_id: str
) -> Path:
    """Record one bounded matrix run produced by the private external observers."""
    bundle = _load_object(bundle_path, "composite run bundle")
    if bundle.get("schema_version") != SCHEMA_VERSION or bundle.get("kind") != "composite-run-bundle":
        raise CompositeQualificationError("composite run bundle schema/kind mismatch")
    descriptor_path = _safe_file(Path(bundle.get("usb_descriptors_path", "")), Path(bundle_path).resolve().parent, "bundle descriptors")
    return record_composite_run(
        manifest_path,
        evidence_root,
        run_id,
        bundle.get("result", {}),
        bundle.get("traffic", {}),
        bundle.get("input_trace", {}),
        descriptor_path.read_bytes(),
    )
