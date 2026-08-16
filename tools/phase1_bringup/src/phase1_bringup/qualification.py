"""Frozen product-shaped USB qualification profile and adapter-neutral runner.

This module owns the frozen profile and can optionally execute the operator
qualification command.  Self-checks never discover ports or open a device.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .protocol import MAX_LINE_BYTES, PROTOCOL_VERSION
from .pairing import PairingStore
from .serial_link import reconnect_exact

PROFILE_ID = "usb-v1-product-shaped"
MANIFEST_SCHEMA_VERSION = 1
STRICT_COUNTERS = (
    "sent",
    "received",
    "acknowledged",
    "rejected",
    "duplicate",
    "out_of_order",
    "malformed",
    "digest_mismatch",
    "watchdog_reset",
)
RESOURCE_METRICS = (
    "minimum_free_heap",
    "largest_free_block",
    "parser_high_water",
    "queue_high_water",
    "max_display_flush_us",
    "max_key_poll_gap_us",
)
INTERRUPTION_ROWS = (
    "software-reset",
    "normal-flash-reset",
    "same-port-reconnect",
    "different-port-reconnect",
    "forced-endpoint-renumbering",
    "host-utility-restart",
    "reset-unplug",
)


class QualificationError(ValueError):
    """A frozen-profile, metrics, or evidence-lineage violation."""


class ByteLink(Protocol):
    """Transport-neutral byte/event boundary; no protocol interpretation."""

    def write(self, data: bytes) -> int: ...

    def read(self, size: int = 4096, timeout: float | None = None) -> bytes: ...

    def close(self) -> None: ...


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _interruption_row(name: str) -> dict[str, Any]:
    return {
        "id": name,
        "applicable": True,
        "required": True,
        "close_endpoint": True,
        "discard_in_flight_ids": True,
        "rediscover_exact_device": True,
        "fresh_boot_and_session": True,
        "first_post_reconnect_sequence": True,
        "na_reason": None,
    }


def frozen_profile(schema_path: Path, fixture_path: Path) -> dict[str, Any]:
    """Build the deterministic profile that must be hashed before traffic."""
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "qualification-manifest",
        "profile_id": PROFILE_ID,
        "status": "frozen",
        "protocol": {
            "version": PROTOCOL_VERSION,
            "max_line_bytes_including_lf": MAX_LINE_BYTES,
            "schema_sha256": sha256_file(Path(schema_path)),
            "fixture_sha256": sha256_file(Path(fixture_path)),
        },
        "baseline": {
            "duration_seconds": 30 * 60,
            "snapshot_status_per_second": 1,
            "expected_snapshots": 30 * 60,
            "directions": ["host_to_device", "device_to_host"],
        },
        "final_maximum": {
            "frames_each_direction": 1000,
            "payload_bound": "final_protocol_maximum",
            "digest_required": True,
        },
        "burst": {
            "frames_each_direction": 100,
            "window_seconds": 10,
            "repetitions": 10,
            "digest_required": True,
        },
        "concurrent_workload": {
            "display_panels": 4,
            "display_mode": "continuous_sequential",
            "led_mode": "continuous",
            "key_polling": "continuous",
            "encoder_polling": "continuous",
            "physical_overlap_required": True,
            "overlap_must_be_observed": True,
        },
        "gates": {
            "exact_counter_equality": ["expected", "sent", "acknowledged", "received"],
            "zero_strict_failures": list(STRICT_COUNTERS[3:]),
            "resource_metrics_required": list(RESOURCE_METRICS),
            "latency_limits_ms": {
                "baseline_ack_p99": 250,
                "burst_ack_p99": 1000,
                "endpoint_return_and_handshake": 10000,
            },
            "physical_overlap_confirmation": "required_and_not_inferred_from_counters",
        },
        "interruption_matrix": [_interruption_row(name) for name in INTERRUPTION_ROWS],
    }


def _addressed_hash(manifest: Mapping[str, Any]) -> str:
    content = dict(manifest)
    content.pop("manifest_sha256", None)
    return sha256_bytes(content)


def freeze_manifest(output: Path, schema_path: Path, fixture_path: Path) -> dict[str, Any]:
    """Create the immutable manifest once, or reopen and verify an existing one."""
    output = Path(output)
    if output.exists():
        manifest = load_manifest(output)
        expected = _addressed_hash(manifest)
        if manifest.get("manifest_sha256") != expected:
            raise QualificationError("existing qualification manifest hash does not match content")
        return manifest
    manifest = frozen_profile(schema_path, fixture_path)
    manifest["manifest_sha256"] = _addressed_hash(manifest)
    output.write_bytes(_canonical_bytes(manifest))
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"qualification manifest is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise QualificationError("qualification manifest must be an object")
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION or manifest.get("kind") != "qualification-manifest":
        raise QualificationError("qualification manifest schema/kind is unsupported")
    if manifest.get("profile_id") != PROFILE_ID or manifest.get("status") != "frozen":
        raise QualificationError("qualification profile is not the frozen USB product-shaped profile")
    protocol = manifest.get("protocol")
    if not isinstance(protocol, Mapping) or protocol.get("version") != PROTOCOL_VERSION or protocol.get("max_line_bytes_including_lf") != MAX_LINE_BYTES:
        raise QualificationError("manifest protocol bound does not match v1/4096")
    if not isinstance(manifest.get("manifest_sha256"), str) or manifest["manifest_sha256"] != _addressed_hash(manifest):
        raise QualificationError("qualification manifest SHA-256 address is invalid")
    baseline = manifest.get("baseline")
    if not isinstance(baseline, Mapping) or baseline.get("duration_seconds") != 1800 or baseline.get("snapshot_status_per_second") != 1 or baseline.get("expected_snapshots") != 1800:
        raise QualificationError("baseline must be exactly 30 minutes at one snapshot/status per second")
    maximum = manifest.get("final_maximum")
    if not isinstance(maximum, Mapping) or maximum.get("frames_each_direction") != 1000 or maximum.get("digest_required") is not True:
        raise QualificationError("final-maximum phase must send at least 1000 digest-checked frames each direction")
    burst = manifest.get("burst")
    if not isinstance(burst, Mapping) or burst.get("frames_each_direction") != 100 or burst.get("window_seconds") != 10 or burst.get("repetitions") != 10:
        raise QualificationError("burst phase must be 100 frames each direction over 10 seconds repeated 10 times")
    workload = manifest.get("concurrent_workload")
    if not isinstance(workload, Mapping) or workload.get("display_panels") != 4 or workload.get("display_mode") != "continuous_sequential" or workload.get("physical_overlap_required") is not True or workload.get("overlap_must_be_observed") is not True:
        raise QualificationError("full four-display/input workload and observed physical overlap are required")
    gates = manifest.get("gates")
    if not isinstance(gates, Mapping) or gates.get("exact_counter_equality") != ["expected", "sent", "acknowledged", "received"]:
        raise QualificationError("strict exact counter-equality gate is missing")
    if gates.get("zero_strict_failures") != list(STRICT_COUNTERS[3:]) or gates.get("resource_metrics_required") != list(RESOURCE_METRICS):
        raise QualificationError("strict failure/resource metric gate is incomplete")
    limits = gates.get("latency_limits_ms")
    if limits != {"baseline_ack_p99": 250, "burst_ack_p99": 1000, "endpoint_return_and_handshake": 10000}:
        raise QualificationError("latency limits changed from the frozen pre-traffic values")
    rows = manifest.get("interruption_matrix")
    if not isinstance(rows, list) or [row.get("id") for row in rows if isinstance(row, Mapping)] != list(INTERRUPTION_ROWS) or len(rows) != len(INTERRUPTION_ROWS):
        raise QualificationError("interruption matrix is incomplete or reordered")
    for row in rows:
        if not isinstance(row, Mapping) or any(row.get(field) is not True for field in ("required", "close_endpoint", "discard_in_flight_ids", "rediscover_exact_device", "fresh_boot_and_session", "first_post_reconnect_sequence")):
            raise QualificationError("interruption row does not require close/discard/fresh exact recovery")
    return dict(manifest)


def qualification_manifest_check(path: Path) -> dict[str, Any]:
    """CLI/self-check entry point; it performs no device or serial I/O."""
    return validate_manifest(load_manifest(Path(path)))




def validate_qualification_result(result: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    """Reject any PASS that lacks measured strict counters or firmware metrics."""
    validate_manifest(manifest)
    if result.get("status") != "pass":
        return
    if result.get("strict_failure_counters_available") is not True or result.get("resource_metrics_available") is not True:
        raise QualificationError("qualification PASS is forbidden without firmware strict counters and resource metrics")
    if result.get("qualification_blockers"):
        raise QualificationError("qualification PASS has unresolved blockers")
    counters = result.get("counters")
    expected = int(manifest["baseline"]["expected_snapshots"]) + int(manifest["final_maximum"]["frames_each_direction"]) + int(manifest["burst"]["frames_each_direction"]) * int(manifest["burst"]["repetitions"])
    if not isinstance(counters, Mapping) or any(counters.get(name) != expected for name in ("expected", "sent", "received", "acknowledged")):
        raise QualificationError("qualification PASS does not have exact expected/sent/received/acknowledged equality")
    if any(counters.get(name) != 0 for name in STRICT_COUNTERS[3:]):
        raise QualificationError("qualification PASS has a non-zero strict failure counter")
    metrics = result.get("metrics")
    if not isinstance(metrics, Mapping) or any(metrics.get(name) is None for name in RESOURCE_METRICS):
        raise QualificationError("qualification PASS lacks complete resource/input/display metrics")
    if result.get("physical_overlap") != "Y":
        raise QualificationError("qualification PASS lacks explicit physical overlap confirmation")
@dataclass
class QualificationCounters:
    """Strict traffic counters kept independent from any concrete adapter."""

    values: dict[str, int] = field(default_factory=lambda: {name: 0 for name in STRICT_COUNTERS})

    def increment(self, name: str, amount: int = 1) -> None:
        if name not in STRICT_COUNTERS or amount < 0:
            raise QualificationError(f"unknown or negative qualification counter: {name}")
        self.values[name] += amount


@dataclass
class QualificationRunner:
    """Validate a frozen profile and collect adapter-neutral traffic evidence.

    The runner never discovers ports, prompts for physical confirmation, starts
    a device, or interprets a transport-specific handle.
    """
    manifest: Mapping[str, Any]
    counters: QualificationCounters = field(default_factory=QualificationCounters)
    metrics: dict[str, int | float | None] = field(default_factory=dict)
    overlap_confirmed: bool = False
    interruption_results: list[Mapping[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        validate_manifest(self.manifest)
        self.metrics.setdefault("minimum_free_heap", None)
        self.metrics.setdefault("largest_free_block", None)
        self.metrics.setdefault("parser_high_water", None)
        self.metrics.setdefault("queue_high_water", None)
        self.metrics.setdefault("max_display_flush_us", None)
        self.metrics.setdefault("max_key_poll_gap_us", None)

    @property
    def manifest_sha256(self) -> str:
        return str(self.manifest["manifest_sha256"])

    def exchange(self, link: ByteLink, frames: Sequence[bytes], expected_replies: int) -> None:
        """Send/read bytes through a link without assigning protocol semantics."""
        for frame in frames:
            sent = link.write(frame)
            self.counters.increment("sent")
            if sent != len(frame):
                raise QualificationError("link short write before qualification traffic completed")
        for _ in range(expected_replies):
            reply = link.read(MAX_LINE_BYTES, timeout=1.0)
            if not reply:
                raise QualificationError("link returned no reply for expected qualification frame")
            self.counters.increment("received")

    def record_interruption(self, result: Mapping[str, Any]) -> None:
        row_id = result.get("id")
        expected = [row.get("id") for row in self.manifest["interruption_matrix"]]
        if row_id not in expected or any(existing.get("id") == row_id for existing in self.interruption_results):
            raise QualificationError("interruption result is unknown or duplicated")
        self.interruption_results.append(dict(result))

    def validate_result(self, expected: Mapping[str, int]) -> None:
        for name in ("sent", "received", "acknowledged"):
            if self.counters.values[name] != expected.get(name):
                raise QualificationError(f"strict counter mismatch for {name}")
        if any(self.counters.values[name] != 0 for name in STRICT_COUNTERS[3:]):
            raise QualificationError("strict qualification failure counter is non-zero")
        if not self.overlap_confirmed:
            raise QualificationError("physical overlap must be explicitly confirmed, never inferred from counters")
        if any(self.metrics.get(name) is None for name in RESOURCE_METRICS):
            raise QualificationError("complete resource/input/display metrics are required")
        expected_rows = set(INTERRUPTION_ROWS)
        actual_rows = {str(row.get("id")) for row in self.interruption_results}
        if actual_rows != expected_rows:
            raise QualificationError("qualification result does not close every frozen interruption row")

    def linkage(self, traffic_sha256: str, traffic_path: str) -> dict[str, Any]:
        if not isinstance(traffic_sha256, str) or len(traffic_sha256) != 64:
            raise QualificationError("immutable traffic SHA-256 is required")
        if not traffic_path or traffic_path.startswith("/"):
            raise QualificationError("traffic path must be a concrete relative immutable path")
        return {
            "manifest_sha256": self.manifest_sha256,
            "manifest_profile": PROFILE_ID,
            "traffic_sha256": traffic_sha256,
            "traffic_path": traffic_path,
        }


def _operator_checkpoint(label: str, instruction: str) -> str:
    """Require an explicit operator response; never infer a physical result."""
    print(f"\n[{label}] {instruction}")
    print("Enter Y=pass, N=fail, R=repeat, U=unavailable: ", end="", flush=True)
    response = input().strip().upper()
    if response not in {"Y", "N", "R", "U"}:
        raise QualificationError(f"{label} requires exactly Y, N, R, or U")
    return response


class _RecordingConnection:
    """Record immutable bytes around the existing SerialLink boundary."""

    def __init__(self, link: Any, traffic: list[dict[str, Any]], phase: str = "traffic") -> None:
        self.link = link
        self.traffic = traffic
        self.phase = phase

    def write(self, data: bytes) -> int | None:
        self.traffic.append({"direction": "host_to_device", "phase": self.phase, "timestamp": time.time(), "bytes": data.hex()})
        result = self.link.write(data)
        return len(data) if result is None else int(result)

    def readline(self) -> bytes:
        value = self.link.readline()
        if value:
            self.traffic.append({"direction": "device_to_host", "phase": self.phase, "timestamp": time.time(), "bytes": value.hex()})
        return value

    def close(self) -> None:
        self.link.close()


def run_qualification(
    manifest_path: Path,
    transport: str,
    evidence_root: Path,
    binding_path: Path,
) -> int:
    """Run the operator-owned USB proof and atomically preserve its outcome.

    This is intentionally the only CLI path that opens hardware.  It uses the
    established exact-identity recovery helper for every reconnect and asks
    for explicit physical responses at overlap and interruption checkpoints.
    """

    manifest = qualification_manifest_check(Path(manifest_path))
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)
    binding = PairingStore(Path(binding_path)).load()
    if binding is None:
        raise QualificationError("no exact paired keypad binding exists; run pair before qualify")
    try:
        import serial
    except ImportError as exc:
        raise QualificationError("pyserial 3.5 is required in the plan-owned environment") from exc

    traffic: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    link: Any | None = None
    session: Any | None = None
    status = "incomplete"
    expected_frames = 0
    acknowledged = 0
    failure_counts = {name: 0 for name in STRICT_COUNTERS[3:]}
    run_error: str | None = None
    device_metrics: dict[str, int] | None = None
    metrics_query_error: str | None = None
    overlap = "U"
    overlap_reason: str | None = "not confirmed"
    try:
        def opener(candidate: Any) -> Any:
            return serial.Serial(candidate.device, baudrate=115200, timeout=0.2, write_timeout=3)

        candidate, base_link, session, recovery = reconnect_exact(binding, None, opener, timeout=3.0)
        link = base_link
        recording = _RecordingConnection(base_link, traffic, phase="preflight")
        session.connection = recording
        transitions.extend(item.as_dict() for item in recovery)
        for panel in range(1, 5):
            session.stimulate(f"PREFLIGHT-{panel}", panel, "BRIGHTNESS-HIGH")
        session.request("metrics", {"request": "reset"}, {"metrics_ack"})
        recording.phase = "traffic"
        overlap = _operator_checkpoint(
            "physical-overlap",
            "The paired keypad is active after preflight writes. Keep all four displays/LEDs active and continuously poll keys and encoder while you perform the prompted key/encoder actions. Confirm every expected action is physically observed; counters cannot answer this.",
        )
        if overlap == "N":
            raise QualificationError("physical overlap was rejected by the operator")
        if overlap == "U":
            overlap_reason = input("Explain why physical overlap is unavailable (required): ").strip()
            if not overlap_reason:
                raise QualificationError("physical overlap U requires a reason")
        baseline_count = int(manifest["baseline"]["expected_snapshots"])
        final_count = int(manifest["final_maximum"]["frames_each_direction"])
        burst_count = int(manifest["burst"]["frames_each_direction"])
        burst_repetitions = int(manifest["burst"]["repetitions"])
        burst_window = float(manifest["burst"]["window_seconds"])
        expected_frames = 0
        def proof_frame(stimulus: str, delay: float = 0.0) -> None:
            nonlocal expected_frames, acknowledged
            expected_frames += 1
            try:
                session.stimulate(f"QUALIFY-{expected_frames}", (expected_frames % 4) + 1, stimulus)
            except Exception as exc:
                code = str(getattr(exc, "code", "rejected"))
                if code in failure_counts:
                    failure_counts[code] += 1
                else:
                    failure_counts["rejected"] += 1
                raise
            acknowledged += 1
            if delay:
                time.sleep(delay)

        for index in range(baseline_count):
            proof_frame("WAIT", 1.0 if index < baseline_count - 1 else 0.0)
        for _ in range(final_count):
            proof_frame("PANEL-4")
        for _ in range(burst_repetitions):
            started = time.monotonic()
            for _ in range(burst_count):
                proof_frame("BRIGHTNESS-HIGH")
            remaining = burst_window - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)

        recording.phase = "metrics"
        try:
            metrics_frame, _ = session.request("metrics", {"request": "proof"}, {"metrics_ack"})
            device_metrics = {name: int(metrics_frame["payload"][name]) for name in RESOURCE_METRICS + STRICT_COUNTERS}
        except Exception as exc:
            metrics_query_error = str(exc)
        recording.phase = "traffic"

        for row in INTERRUPTION_ROWS:
            response = _operator_checkpoint(
                row,
                "Perform this interruption on the paired unit, then wait for the runtime endpoint to return and exact-device handshake to complete. The utility will close stale state and discard in-flight IDs before rediscovery.",
            )
            if response == "R":
                response = _operator_checkpoint(row, "Repeat the interruption and physical observation.")
            reason = None
            if response == "U":
                reason = input(f"Explain why {row} is unavailable (required): ").strip()
                if not reason:
                    raise QualificationError(f"{row} U requires a reason")
            transitions.append({"id": row, "response": response, "reason": reason, "timestamp": time.time(), "candidate": candidate.snapshot()})
            if response == "Y":
                link.close()
                candidate, link, session, recovery = reconnect_exact(
                    binding,
                    None,
                    opener,
                    timeout=3.0,
                    discarded_ids=list(range(1, expected_frames + 1)),
                )
                recording = _RecordingConnection(link, traffic)
                session.connection = recording
                transitions.extend(item.as_dict() for item in recovery)

    except Exception as exc:
        status = "fail"
        run_error = str(exc)
        transitions.append({"id": "qualification-error", "response": "U", "reason": run_error, "timestamp": time.time()})
    finally:
        if link is not None:
            link.close()

    observed_sent = sum(1 for item in traffic if item.get("direction") == "host_to_device" and item.get("phase") == "traffic")
    observed_received = sum(1 for item in traffic if item.get("direction") == "device_to_host" and item.get("phase") == "traffic")
    firmware_failures = {
        name: (device_metrics.get(name) if device_metrics is not None else None)
        for name in STRICT_COUNTERS[3:]
    }
    counters = {
        "expected": expected_frames,
        "sent": observed_sent,
        "received": observed_received,
        "acknowledged": acknowledged,
        **firmware_failures,
    }
    metrics = {name: (device_metrics.get(name) if device_metrics is not None else None) for name in RESOURCE_METRICS}
    blockers: list[str] = []
    if device_metrics is None:
        blockers.extend(["firmware_proof_metrics_unavailable", "firmware_strict_failure_counters_unavailable"])
    if metrics_query_error:
        blockers.append("metrics_query_error:" + metrics_query_error)
    if run_error:
        blockers.append("qualification_error:" + run_error)
    row_observations = [item for item in transitions if "response" in item]
    rows_ok = {item.get("id") for item in row_observations} == set(INTERRUPTION_ROWS) and all(item.get("response") == "Y" or (item.get("response") == "U" and item.get("reason")) for item in row_observations)
    strict_ok = device_metrics is not None and all(counters.get(name) == 0 for name in STRICT_COUNTERS[3:])
    traffic_ok = counters["expected"] == expected_frames and counters["sent"] == expected_frames and counters["received"] == expected_frames and counters["acknowledged"] == expected_frames
    metrics_ok = device_metrics is not None and all(metrics.get(name) is not None for name in RESOURCE_METRICS)
    if overlap == "Y" and rows_ok and strict_ok and traffic_ok and metrics_ok and not blockers:
        status = "pass"

    traffic_bytes = _canonical_bytes(traffic)
    traffic_hash = hashlib.sha256(traffic_bytes).hexdigest()
    result = {
        "schema_version": 1,
        "kind": "result",
        "run_id": run_id,
        "status": status,
        "transport": transport,
        "physical_overlap": overlap,
        "physical_overlap_reason": overlap_reason,
        "counters": counters,
        "strict_failure_counters_available": device_metrics is not None,
        "resource_metrics_available": device_metrics is not None,
        "qualification_blockers": blockers,
        "metrics": metrics,
        "interruption_matrix": transitions,
        "qualification": {
            "manifest_sha256": manifest["manifest_sha256"],
            "manifest_profile": PROFILE_ID,
            "traffic_sha256": traffic_hash,
            "traffic_path": "traffic.json",
        },
    }
    from .evidence import EvidenceWriter

    run_manifest = {
        "schema_version": 1,
        "kind": "manifest",
        "run_id": run_id,
        "workflow": "qualification",
        "qualification_manifest_sha256": manifest["manifest_sha256"],
        "status": "frozen-before-traffic",
    }
    EvidenceWriter(Path(evidence_root), run_id).write(run_manifest, result, {"traffic.json": traffic_bytes})
    print(f"Qualification result: {Path(evidence_root) / run_id} ({status})")
    return 0 if status == "pass" else 1
