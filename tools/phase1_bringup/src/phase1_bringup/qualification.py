"""Frozen product-shaped USB qualification profile and adapter-neutral runner.

This module deliberately owns no serial discovery and never opens a device.  A
qualification caller supplies a byte-stream link and records the resulting
traffic separately; this keeps the protocol/transport boundary testable without
allowing a CLI self-check to perform hardware I/O.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .protocol import MAX_LINE_BYTES, PROTOCOL_VERSION

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
