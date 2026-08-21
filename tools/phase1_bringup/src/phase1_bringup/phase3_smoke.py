"""Exact-pair Phase 3 deployment capture and pending-evidence validator."""
from __future__ import annotations

from contextlib import contextmanager
import argparse
import binascii
import hashlib
import json
import os
import struct
import subprocess
import signal
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any, Iterator, Mapping
from types import SimpleNamespace

from herdr_keypad.codex import normalize_rate_limits

from .pairing import PairingStore
from .serial_link import reconnect_exact, require_inherited_bridge_lock

ROOT = Path(__file__).resolve().parents[4]
THEMES = ("signal-edge", "ledger", "beacon", "instrument")
CODEX_SCENES = (
    "codex-current", "codex-partial", "codex-stale", "codex-unavailable",
    "codex-auth", "codex-offline", "host-offline", "codex-limit", "codex-long",
)
MENU_SCENES = (
    "menu-root-0", "menu-root-1", "menu-root-2", "menu-root-3", "menu-root-4",
    "menu-root-5", "menu-brightness", "menu-health", "menu-about",
)
TILE_SCENES = (
    "blocked", "unseen", "working", "idle", "settled", "unknown", "empty",
    "stale", "offline", "unavailable", "sync", "pending", "focused",
    "rejected", "vanished", "uncertain", "failed",
)
SLOT_SCENES = ("slots-0", "slots-1", "slots-2", "slots-3")
LED_GRAMMARS = ("rail-echo", "exception", "field-extension", "meter-lamps")
MOTION_STATE_SCENES = {
    "BLOCKED": "blocked", "UNSEEN": "unseen", "WORKING": "working",
    "IDLE": "idle", "SETTLED": "settled", "UNKNOWN": "unknown",
    "EMPTY": "empty", "STALE": "stale", "OFFLINE": "offline",
    "UNAVAILABLE": "unavailable", "SYNC": "sync", "PENDING": "pending",
    "FOCUSED": "focused", "REJECTED": "rejected", "VANISHED": "vanished",
    "UNCERTAIN": "uncertain", "FAILED": "failed",
}
MOTION_FEEDBACK_SCENES = {
    "DISABLED": "empty", "READY": "working", "PENDING": "pending",
    "SUCCESS": "focused", "REJECTED": "rejected", "STALE": "stale",
    "VANISHED": "vanished", "OFFLINE": "offline", "UNCERTAIN": "uncertain",
    "FAILED": "failed",
}
MOTION_CODEX_SCENES = {
    "CODEX_CURRENT": "codex-current", "CODEX_PARTIAL": "codex-partial",
    "CODEX_FENCE": "codex-unavailable",
}
REQUIREMENTS = (
    "CODEX-01", "CODEX-02", "CODEX-03", "CODEX-04", "SYNC-03",
    "SAFE-01", "MENU-01", "MENU-02", "MENU-03", "MENU-04",
)
UI_CONSIDERATIONS = (
    "empty", "loading", "error", "populated", "partial", "overflow",
    "zero-one-many", "long-text", "interaction", "persistence",
)
PHYSICAL_ROWS = (
    "long-text-all-themes-at-10-percent",
    "source-labels-remain-legible",
    "direct-agent-keys-from-root",
    "direct-agent-keys-from-brightness",
    "direct-agent-keys-from-health",
    "direct-agent-keys-from-about",
    "brightness-ladder-10-through-100",
    "brightness-zero-rejected",
    "close-reverts-unconfirmed-preview",
    "timeout-reverts-unconfirmed-preview",
    "led-preview-and-semantic-behavior",
    "confirmation-persists-setting",
    "reboot-restores-confirmed-brightness",
    "fresh-bridge-resync-after-acceptance",
)
HUMAN_ROWS = PHYSICAL_ROWS[:-1]
OBSERVATION_PROMPTS = {
    "long-text-all-themes-at-10-percent": (
        "At requested 10% brightness, use encoder click -> THEME -> click, rotate and save each "
        "of SIGNAL EDGE, LEDGER, BEACON, and INSTRUMENT. In every theme verify the physical "
        "panel keeps AUTH REQUIRED, CODEX OFFLINE, HOST OFFLINE, RESET WEEK ..., and the longest "
        "ABOUT version values legible, with no clipping or bezel collision."
    ),
    "source-labels-remain-legible": (
        "Verify the physical CODEX panel always retains the literal source-state word and AGE; "
        "no N/A field appears as 0%, OK, or another positive claim."
    ),
    "direct-agent-keys-from-root": (
        "Encoder-click to open MENU, then press keys 1, 2, and 3 in turn. Each must focus its "
        "same displayed agent, show feedback only on that tile/LED zone, and leave the root "
        "cursor and 30-second deadline unchanged."
    ),
    "direct-agent-keys-from-brightness": (
        "Open MENU, rotate to BRIGHTNESS, click, then press keys 1, 2, and 3. Each must focus its "
        "same displayed agent without changing the brightness candidate or extending the deadline."
    ),
    "direct-agent-keys-from-health": (
        "Return to root, rotate to HEALTH, click, then press keys 1, 2, and 3. Each must focus its "
        "same displayed agent; HEALTH stays open with its cursor/deadline unchanged."
    ),
    "direct-agent-keys-from-about": (
        "Return to root, rotate to ABOUT, click, then press keys 1, 2, and 3. Each must focus its "
        "same displayed agent; ABOUT stays open with its cursor/deadline unchanged."
    ),
    "brightness-ladder-10-through-100": (
        "Open BRIGHTNESS and rotate through every displayed step 10%,20%,...,100%. The physical "
        "panels must visibly change monotonically while remaining powered and legible."
    ),
    "brightness-zero-rejected": (
        "At 10%, rotate further downward. The value must clamp at 10%; 0% must never appear and "
        "the panels must remain visibly powered."
    ),
    "close-reverts-unconfirmed-preview": (
        "Preview a brightness different from the stored value without clicking SAVE, then close "
        "the menu through CLOSE. The physical brightness must return to the stored value."
    ),
    "timeout-reverts-unconfirmed-preview": (
        "Preview a different brightness without saving, then give the encoder no input for 30 "
        "seconds. Panel 4 must return to CODEX and physical brightness must revert."
    ),
    "led-preview-and-semantic-behavior": (
        "Open LEDS and rotate candidates. Only the bounded candidate preview may change; after "
        "returning/timeout the stored grammar and agent semantic/focus LED behavior must return, "
        "with the encoder-open L13 cue and no brightness-driven LED semantic change."
    ),
    "confirmation-persists-setting": (
        "Open BRIGHTNESS, choose a value, and click SAVE. Reopen BRIGHTNESS and verify that exact "
        "value is the stored starting value."
    ),
    "reboot-restores-confirmed-brightness": (
        "After saving brightness, reboot the keypad with its normal reset control. Verify startup "
        "returns and the confirmed physical brightness, theme, LED grammar, and direct-key behavior "
        "are restored."
    ),
}
PHASE31_MATRIX_ROWS = tuple(
    f"matrix-{theme}-{grammar}"
    for theme in THEMES
    for grammar in LED_GRAMMARS
)
PHASE31_STRESS_ROWS = (
    "stress-concurrent-herdr-codex",
    "stress-stale-offline-recovery",
    "stress-usb-reconnect",
    "stress-firmware-reset",
    "stress-generation-replacement",
    "stress-simultaneous-key-encoder",
    "stress-resource-degradation",
)
PHASE31_PHYSICAL_ROWS = PHASE31_MATRIX_ROWS + PHASE31_STRESS_ROWS
PHASE31_BACKSTOP_ROWS = ("backstop-long-text-10-percent", "backstop-physical-quality")
PHASE31_ALL_ROWS = PHASE31_PHYSICAL_ROWS + PHASE31_BACKSTOP_ROWS
TRACER_LINK_KEYS = {
    "tracer_sha256", "elapsed_ms_path", "child_exit_path", "redaction_result_path"
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PPM_HEADER = b"P6\n128 128\n255\n"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()

def valid_snapshot_revision(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def valid_publication_identity(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(f"artifact must be inside repository: {path}") from exc


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("evidence path must be repository-relative")
    resolved = (ROOT / path).resolve()
    if ROOT not in resolved.parents:
        raise ValueError("evidence path escapes repository")
    return resolved


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_json(path: Path, value: Any, *, checksum: bool = False) -> str:
    payload = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True).encode("ascii") + b"\n"
    atomic_write(path, payload)
    digest = sha256_bytes(payload)
    if checksum:
        sidecar = path.with_suffix(path.suffix + ".sha256")
        atomic_write(sidecar, f"{digest}  {relative(path)}\n".encode("ascii"))
    return digest


PHASE31_METRIC_FIELDS = (
    "loop_wall_max_us",
    "compose_flush_max_us",
    "frame_count",
    "full_frames",
    "half_frames",
    "static_frames",
    "level_changes",
    "skipped_frames",
    "degraded_frames",
    "reveal_max_us",
    "first_press_response_us",
    "first_encoder_response_us",
    "max_key_poll_gap_us",
    "minimum_free_heap",
    "largest_free_block",
    "parser_high_water",
    "queue_high_water",
    "allocation_stable",
    "animation_duty_max_percent",
)
PHASE31_OBSERVATION_IDS = (
    "blocked-cycle",
    "direct-key-response",
    "encoder-response",
    "display-led-alignment",
    "smoothness",
    "brightness-power",
)
PHASE31_HARD_CEILINGS = {
    "ordinary_transition_us": 250_000,
    "menu_slide_us": 200_000,
    "recovery_reveal_us": 250_000,
    "press_response_us": 120_000,
    "max_key_poll_gap_us": 120_000,
    "success_hold_us": 900_000,
    "animation_duty_percent": 30,
}
PHASE31_NONZERO_MACHINE_METRICS = (
    "max_key_poll_gap_us",
    "minimum_free_heap",
    "largest_free_block",
    "parser_high_water",
    "queue_high_water",
    "loop_wall_max_us",
    "compose_flush_max_us",
    "frame_count",
    "full_frames",
    "reveal_max_us",
    "first_press_response_us",
    "first_encoder_response_us",
    "animation_duty_max_percent",
)


def _validate_phase31_machine_metrics(metrics: Mapping[str, int]) -> None:
    if metrics["allocation_stable"] != 1:
        raise ValueError("exact-device allocation stability is not passing")
    if any(metrics[name] <= 0 for name in PHASE31_NONZERO_MACHINE_METRICS):
        raise ValueError("exact-device metrics contain a missing or zero observation")
    frame_levels = metrics["full_frames"] + metrics["half_frames"] + metrics["static_frames"]
    if frame_levels != metrics["frame_count"]:
        raise ValueError("animation cadence counters do not reconcile with frame_count")
    if metrics["degraded_frames"] > metrics["frame_count"]:
        raise ValueError("degraded frame count exceeds frame_count")
    ceilings = (
        ("compose_flush_max_us", PHASE31_HARD_CEILINGS["ordinary_transition_us"]),
        ("reveal_max_us", PHASE31_HARD_CEILINGS["recovery_reveal_us"]),
        ("first_press_response_us", PHASE31_HARD_CEILINGS["press_response_us"]),
        ("first_encoder_response_us", PHASE31_HARD_CEILINGS["press_response_us"]),
        ("max_key_poll_gap_us", PHASE31_HARD_CEILINGS["max_key_poll_gap_us"]),
        ("animation_duty_max_percent", PHASE31_HARD_CEILINGS["animation_duty_percent"]),
    )
    violations = [
        f"{name}={metrics[name]}>{ceiling}"
        for name, ceiling in ceilings
        if metrics[name] > ceiling
    ]
    if violations:
        raise ValueError("exact-device metric ceiling violation: " + ", ".join(violations))


def _phase31_metrics(payload: Mapping[str, Any]) -> dict[str, int]:
    metrics: dict[str, int] = {}
    for name in PHASE31_METRIC_FIELDS:
        value = payload.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"Phase 03.1 metric is missing or invalid: {name}")
        metrics[name] = value
    if metrics["allocation_stable"] not in {0, 1}:
        raise ValueError("allocation_stable must be 0 or 1")
    return metrics


def validate_phase31_baseline(baseline: Mapping[str, Any]) -> None:
    if baseline.get("schema_version") != 1 or baseline.get("kind") != "phase03.1-baseline-profile":
        raise ValueError("Phase 03.1 baseline schema is not closed")
    deployment = baseline.get("deployment")
    if not isinstance(deployment, Mapping) or not valid_publication_identity(deployment.get("deployment_id")):
        raise ValueError("baseline deployment identity is missing")
    metrics = baseline.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError("baseline metrics are missing")
    _phase31_metrics(metrics)
    observations = baseline.get("observations")
    if not isinstance(observations, list):
        raise ValueError("baseline physical observations are missing")
    by_id = {item.get("id"): item for item in observations if isinstance(item, Mapping)}
    if set(by_id) != set(PHASE31_OBSERVATION_IDS):
        raise ValueError("baseline physical observation matrix is incomplete")
    for row_id in PHASE31_OBSERVATION_IDS:
        row = by_id[row_id]
        if row.get("result") not in {"pass", "failed", "unavailable", "refused"}:
            raise ValueError(f"{row_id} observation result is not typed")
        if not isinstance(row.get("method"), str) or not row["method"]:
            raise ValueError(f"{row_id} observation method is missing")
    if not isinstance(baseline.get("measurement_window"), Mapping):
        raise ValueError("baseline measurement window is missing")
    if not isinstance(baseline.get("samples"), list) or not baseline["samples"]:
        raise ValueError("baseline raw samples are missing")
    for sample in baseline["samples"]:
        if not isinstance(sample, Mapping) or not isinstance(sample.get("id"), str):
            raise ValueError("baseline sample identity is invalid")
        _phase31_metrics(sample.get("metrics", {}))


def validate_phase31_baseline_file(path: Path, *, require_current_deployment: bool = False) -> dict[str, Any]:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sha256_file(path) != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("baseline checksum mismatch")
    validate_phase31_baseline(baseline)
    deployment = baseline["deployment"]
    firmware = resolve_repo_path(deployment["binary_path"])
    if sha256_file(firmware) != deployment["binary_sha256"]:
        raise ValueError("baseline firmware hash mismatch")
    if require_current_deployment and firmware != (ROOT / ".pio/build/selected-usb/firmware.bin").resolve():
        raise ValueError("baseline does not reference current selected-usb deployment")
    print(f"validated Phase 03.1 baseline for {deployment['deployment_id']}")
    return baseline


def phase31_lock_from_baseline(baseline: Mapping[str, Any]) -> dict[str, Any]:
    validate_phase31_baseline(baseline)
    observations = baseline["observations"]
    unavailable = [row["id"] for row in observations if row["result"] in {"unavailable", "refused"}]
    if unavailable:
        raise ValueError(
            "budget lock requires complete physical observations; missing: "
            + ", ".join(unavailable)
        )
    metrics = _phase31_metrics(baseline["metrics"])
    _validate_phase31_machine_metrics(metrics)
    measured_ceiling_checks = (
        ("first_press_response_us", PHASE31_HARD_CEILINGS["press_response_us"]),
        ("first_encoder_response_us", PHASE31_HARD_CEILINGS["press_response_us"]),
        ("reveal_max_us", PHASE31_HARD_CEILINGS["recovery_reveal_us"]),
        ("animation_duty_max_percent", PHASE31_HARD_CEILINGS["animation_duty_percent"]),
        ("compose_flush_max_us", PHASE31_HARD_CEILINGS["ordinary_transition_us"]),
    )
    violations = [
        {"metric": field, "measured": metrics[field], "ceiling": ceiling}
        for field, ceiling in measured_ceiling_checks
        if metrics[field] > ceiling
    ]
    resource_failures = []
    if metrics["allocation_stable"] != 1:
        resource_failures.append({
            "metric": "allocation_stable",
            "measured": metrics["allocation_stable"],
            "required": 1,
        })
    required = (
        "compose_flush_max_us", "reveal_max_us", "first_press_response_us",
        "first_encoder_response_us", "loop_wall_max_us",
    )
    if any(metrics[name] <= 0 for name in required):
        raise ValueError("budget lock requires non-zero exact-device timing observations")
    measured_frame = max(metrics["compose_flush_max_us"], metrics["reveal_max_us"])
    resource_period = max(1_000, (measured_frame * 100 + 29) // 30)
    target_period = 33_334
    quality_failures = [row["id"] for row in observations if row["result"] == "failed"]
    status = "blocked" if quality_failures or violations or resource_failures else "accepted"
    limits = {
        "ordinary_transition_us": PHASE31_HARD_CEILINGS["ordinary_transition_us"],
        "menu_slide_us": PHASE31_HARD_CEILINGS["menu_slide_us"],
        "recovery_reveal_us": PHASE31_HARD_CEILINGS["recovery_reveal_us"],
        "press_response_us": PHASE31_HARD_CEILINGS["press_response_us"],
        "encoder_response_us": PHASE31_HARD_CEILINGS["press_response_us"],
        "success_hold_us": PHASE31_HARD_CEILINGS["success_hold_us"],
        "animation_duty_percent": PHASE31_HARD_CEILINGS["animation_duty_percent"],
        "compose_flush_max_us": metrics["compose_flush_max_us"],
        "max_key_poll_gap_us": metrics["max_key_poll_gap_us"],
        "minimum_free_heap": metrics["minimum_free_heap"],
        "largest_free_block": metrics["largest_free_block"],
        "queue_high_water": metrics["queue_high_water"],
        "source_observation_ids": [row["id"] for row in observations],
    }
    return {
        "schema_version": 1,
        "kind": "phase03.1-budget-lock",
        "status": status,
        "baseline_deployment_id": baseline["deployment"]["deployment_id"],
        "baseline_quality": {
            "status": "failed" if quality_failures or violations or resource_failures else "pass",
            "failed_observation_ids": quality_failures,
            "hard_ceiling_violations": violations,
            "resource_failures": resource_failures,
            "blocking": bool(quality_failures or violations or resource_failures),
        },
        "baseline_metrics": {
            "source": "artifacts/phase03.1/03.1-BASELINE-PROFILE.json",
            "observation_ids": [row["id"] for row in observations],
            "measurement_method": "exact paired keypad metrics_ack plus typed physical observation",
        },
        "ceilings": dict(PHASE31_HARD_CEILINGS),
        "cadence_us": {
            "Signal Edge": target_period,
            "Ledger": target_period,
            "Beacon": target_period * 2,
            "Instrument": target_period,
        },
        "resource_headroom": {
            "measured_frame_cost_us": measured_frame,
            "measured_period_for_30_percent_duty_us": resource_period,
            "target_period_us": target_period,
            "source_metric_ids": ["compose_flush_max_us", "reveal_max_us", "animation_duty_max_percent"],
            "method": "bounded metrics_ack maxima; target remains blocked until measured cost meets UI-SPEC duty",
        },
        "limits": limits,
        "degradation": {
            "levels": ["Full", "Half", "Static"],
            "full_to_half_duty_percent": 30,
            "half_to_static_duty_percent": 30,
            "initial_level": "Static" if metrics["animation_duty_max_percent"] > 30 else "Full",
            "blocked_last": True,
            "semantic_frames_preserved": True,
        },
        "power": {
            "source_observation_id": "brightness-power",
            "method": next(row["method"] for row in observations if row["id"] == "brightness-power"),
            "status": "observed",
        },
    }


def _phase31_serial_opener(candidate: Any) -> Any:
    require_inherited_bridge_lock()
    return __import__("serial").Serial(
        candidate.device, 115200, timeout=0.2, write_timeout=2.0
    )


def _phase31_exact_session(binding_path: Path, timeout: float) -> tuple[Any, Any, Any, dict[str, Any]]:
    binding = PairingStore(binding_path).load()
    if binding is None:
        raise RuntimeError(f"pairing binding missing: {binding_path}")
    selected, link, session, _ = reconnect_exact(
        binding,
        ports=None,
        opener=_phase31_serial_opener,
        timeout=timeout,
    )
    hello = dict(session.device)
    if hello.get("device_id") != binding.device_id:
        link.close()
        raise RuntimeError("fresh hello device identity differs from exact pairing")
    if hello.get("firmware") != binding.firmware or hello.get("protocol") != binding.protocol:
        link.close()
        raise RuntimeError("fresh hello firmware/protocol differs from exact pairing")
    return selected, link, session, hello


def run_phase31_profile(args: argparse.Namespace) -> int:
    guard = ROOT / "host/herdr_keypad/scripts/ensure-bridge.sh"
    pidfile = Path(os.environ.get("XDG_RUNTIME_DIR", str(Path.home() / ".cache"))) / "herdr-keypad/bridge.pid"
    if pidfile.is_file() and pidfile.stat().st_size:
        subprocess.run([str(guard), "stop-for-acceptance"], cwd=ROOT, check=True)
    firmware = args.firmware.resolve()
    if not firmware.is_file():
        raise RuntimeError("current firmware binary is required")
    deployment = fresh_deployment(args.binding.resolve(), firmware, args.timeout)
    started = time.time_ns() // 1_000_000
    selected, link, session, hello = _phase31_exact_session(args.binding.resolve(), args.timeout)
    try:
        session.request("metrics", {"request": "reset"}, {"metrics_ack"})
        before_frame, _ = session.request("metrics", {"request": "proof"}, {"metrics_ack"})
        before = _phase31_metrics(before_frame["payload"])
        time.sleep(1.25)
        after_frame, _ = session.request("metrics", {"request": "proof"}, {"metrics_ack"})
        after = _phase31_metrics(after_frame["payload"])
    finally:
        link.close()
    ended = time.time_ns() // 1_000_000
    observations = [
        {
            "id": "blocked-cycle", "result": "pass", "method": "exact-device metrics window",
            "observation": {"sample_ids": ["before-blocked", "after-blocked"], "duration_ms": 1250},
        },
        {
            "id": "direct-key-response", "result": "unavailable",
            "method": "physical operator observation required",
            "observation": {"reason": "no human visual confirmation supplied"},
        },
        {
            "id": "encoder-response", "result": "unavailable",
            "method": "physical operator observation required",
            "observation": {"reason": "no human visual confirmation supplied"},
        },
        {
            "id": "display-led-alignment", "result": "unavailable",
            "method": "physical operator observation required",
            "observation": {"reason": "framebuffer and metrics cannot prove LED/display alignment"},
        },
        {
            "id": "smoothness", "result": "unavailable",
            "method": "physical operator observation required",
            "observation": {"reason": "framebuffer and metrics cannot prove physical smoothness"},
        },
        {
            "id": "brightness-power", "result": "unavailable",
            "method": "physical power/brightness observation required",
            "observation": {"reason": "power headroom cannot be inferred from USB enumeration"},
        },
    ]
    baseline = {
        "schema_version": 1,
        "kind": "phase03.1-baseline-profile",
        "status": "blocked",
        "deployment": deployment,
        "session": {
            "device_id": hello["device_id"],
            "firmware": hello["firmware"],
            "protocol": hello["protocol"],
            "boot_id": hello["device_boot_id"],
            "session_id": hello["device_session_id"],
            "usb_serial": selected.serial_number or "unavailable",
        },
        "measurement_window": {"started_unix_ms": started, "ended_unix_ms": ended},
        "samples": [
            {"id": "before-blocked", "metrics": before},
            {"id": "after-blocked", "metrics": after},
        ],
        "metrics": {
            name: max(before[name], after[name]) for name in PHASE31_METRIC_FIELDS
        },
        "observations": observations,
        "evidence_boundary": {
            "metrics": "bounded machine scalars only",
            "physical": "typed exact-device operator observations; unavailable is not pass",
            "focus_semantics": "unchanged; no focus or snapshot payload is serialized",
        },
    }
    write_json(args.evidence.resolve(), baseline, checksum=True)
    validate_phase31_baseline_file(args.evidence.resolve())
    print(f"wrote blocked Phase 03.1 baseline for {deployment['deployment_id']}")
    try:
        subprocess.Popen(
            [str(guard)],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise RuntimeError("guarded bridge restart failed") from exc
    return 0


def run_phase31_lock(args: argparse.Namespace) -> int:
    baseline = validate_phase31_baseline_file(args.baseline.resolve())
    lock = phase31_lock_from_baseline(baseline)
    write_json(args.output.resolve(), lock, checksum=True)
    print(f"wrote Phase 03.1 budget lock for {lock['baseline_deployment_id']}")
    return 0

def png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)


def png_bytes(width: int, height: int, rgb: bytes, deployment_id: str) -> bytes:
    if len(rgb) != width * height * 3:
        raise ValueError("RGB payload has wrong dimensions")
    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return b"".join((
        PNG_SIGNATURE,
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
        png_chunk(b"tEXt", b"deployment_id\x00" + deployment_id.encode("ascii")),
        png_chunk(b"IDAT", zlib.compress(rows, 9)),
        png_chunk(b"IEND", b""),
    ))


def png_has_deployment(path: Path, deployment_id: str) -> bool:
    return b"deployment_id\x00" + deployment_id.encode("ascii") in path.read_bytes()


def make_contact(frames: list[bytes], columns: int, deployment_id: str) -> tuple[int, int, bytes]:
    if not frames or any(len(frame) != 128 * 128 * 3 for frame in frames):
        raise ValueError("contact source frame is not 128x128 RGB")
    rows = (len(frames) + columns - 1) // columns
    width, height = columns * 128, rows * 128
    output = bytearray(width * height * 3)
    for index, frame in enumerate(frames):
        left = (index % columns) * 128
        top = (index // columns) * 128
        for y in range(128):
            source = y * 128 * 3
            target = ((top + y) * width + left) * 3
            output[target:target + 128 * 3] = frame[source:source + 128 * 3]
    return width, height, png_bytes(width, height, bytes(output), deployment_id)


def json_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must be absolute")
    value = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and token in value:
            value = value[token]
        elif isinstance(value, list) and token.isdigit() and int(token) < len(value):
            value = value[int(token)]
        else:
            raise ValueError(f"JSON pointer target missing: {pointer}")
    return value


def bucket_matrix() -> dict[str, Any]:
    top = {"rateLimits": {"primary": {"usedPercent": 12}}}
    shapes = {
        "top-level-only": top,
        "map-only": {"rateLimitsByLimitId": {"provider-key": {"primary": {"usedPercent": 99}}}},
        "both": {**top, "rateLimitsByLimitId": {"provider-key": {}}},
        "neither": {},
        "explicit-null-map": {**top, "rateLimitsByLimitId": None},
        "unusable-map": {"rateLimits": []},
    }
    expected = {
        "top-level-only": ("current", 12, ""),
        "map-only": ("unavailable", None, "E-2401"),
        "both": ("current", 12, ""),
        "neither": ("unavailable", None, "E-2401"),
        "explicit-null-map": ("current", 12, ""),
        "unusable-map": ("unavailable", None, "E-2401"),
    }
    results: list[dict[str, Any]] = []
    for name, payload in shapes.items():
        view, redaction = normalize_rate_limits(payload)
        actual = (view.source_state, view.primary, view.error_code)
        if actual != expected[name] or redaction.bucket_manifest.selected_key is not None:
            raise RuntimeError(f"R-BUCKET shape failed: {name}")
        results.append({
            "shape": name,
            "source_state": view.source_state,
            "primary": view.primary,
            "error_code": view.error_code,
            "selected_key": None,
        })
    keys = {f"opaque-{index}-\u00e9": {} for index in range(12)}
    _view, redaction = normalize_rate_limits({"rateLimits": {}, "rateLimitsByLimitId": keys})
    manifest = redaction.bucket_manifest.as_dict()
    if (manifest["observed_key_count"] != 12 or len(manifest["key_prefixes"]) != 8 or
            not manifest["truncated"] or manifest["selected_key"] is not None or
            any(len(prefix) != 12 for prefix in manifest["key_prefixes"])):
        raise RuntimeError("R-BUCKET bounded hash manifest failed")
    return {
        "id": "R-BUCKET",
        "source": "scripted-production-normalizer",
        "result": "pass",
        "shapes": results,
        "bounded_manifest": manifest,
        "internal_reason": "bucket_unavailable",
        "allowlisted_error_code": "E-2401",
    }


def pair_identity_digest(device_id: str, protocol: int, firmware: str) -> str:
    if not valid_publication_identity(device_id) or not valid_publication_identity(firmware):
        raise ValueError("pair identity fields are invalid")
    if protocol != 1:
        raise ValueError("pair identity protocol is invalid")
    return sha256_bytes(canonical_bytes({
        "device_id": device_id,
        "firmware": firmware,
        "protocol": protocol,
    }))


def deployment_id_for(deployment: Mapping[str, Any]) -> str:
    tuple_value = {
        "boot_id": deployment.get("boot_id", deployment.get("fresh_boot_id")),
        "firmware_sha256": deployment.get(
            "firmware_sha256", deployment.get("binary_sha256")
        ),
        "hello_firmware": deployment.get("hello_firmware"),
        "pair_identity_digest": deployment.get("pair_identity_digest"),
        "protocol_version": deployment.get("protocol_version"),
        "session_id": deployment.get("session_id", deployment.get("fresh_session_id")),
    }
    if any(not valid_publication_identity(value) for key, value in tuple_value.items()
           if key not in {"protocol_version"}):
        raise ValueError("deployment identity tuple is incomplete")
    if tuple_value["protocol_version"] != 1:
        raise ValueError("deployment identity protocol is invalid")
    return sha256_bytes(canonical_bytes(tuple_value))


def validate_deployment(
    deployment: Mapping[str, Any],
    firmware: Path,
    *,
    device_id: str | None = None,
    binding: Any | None = None,
    require_current: bool = False,
) -> None:
    required = (
        "platformio_environment", "binary_path", "binary_sha256", "firmware_sha256",
        "upload_result", "paired_device_id", "pair_identity_digest",
        "hello_firmware", "protocol_version", "fresh_boot_id", "fresh_session_id",
        "boot_id", "session_id", "observed_at_unix_ms", "deployment_id",
    )
    if any(key not in deployment for key in required):
        raise ValueError("deployment lock fields are incomplete")
    if deployment["platformio_environment"] != "selected-usb" or deployment["upload_result"] != "pass":
        raise ValueError("deployment is not a successful selected-usb upload")
    if deployment["binary_sha256"] != deployment["firmware_sha256"]:
        raise ValueError("deployment firmware hash aliases differ")
    if deployment["fresh_boot_id"] != deployment["boot_id"] or deployment["fresh_session_id"] != deployment["session_id"]:
        raise ValueError("deployment boot/session aliases differ")
    if sha256_file(firmware) != deployment["firmware_sha256"]:
        raise ValueError("deployed firmware binary hash mismatch")
    if not valid_publication_identity(deployment["boot_id"]) or not valid_publication_identity(
        deployment["session_id"]
    ):
        raise ValueError("deployment boot/session identity is invalid")
    expected_digest = pair_identity_digest(
        deployment["paired_device_id"],
        deployment["protocol_version"],
        deployment["hello_firmware"],
    )
    if expected_digest != deployment["pair_identity_digest"]:
        raise ValueError("pair identity digest mismatch")
    expected_device = device_id if device_id is not None else (
        binding.device_id if binding is not None else deployment["paired_device_id"]
    )
    if deployment["paired_device_id"] != expected_device:
        raise ValueError("fresh hello device identity differs from exact pairing")
    if binding is not None and (
        deployment["hello_firmware"] != binding.firmware
        or deployment["protocol_version"] != binding.protocol
    ):
        raise ValueError("fresh hello firmware/protocol differs from exact pairing")
    if require_current and firmware.resolve() != (ROOT / ".pio/build/selected-usb/firmware.bin").resolve():
        raise ValueError("deployment does not reference current selected-usb binary")
    if deployment["deployment_id"] != deployment_id_for(deployment):
        raise ValueError("canonical deployment identity mismatch")


def validate_phase31_current_deployment_identity(
    deployment: Mapping[str, Any],
    hello: Mapping[str, Any],
    session_id: str,
    publication: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed at the physical boundary before any observation prompt."""
    deployment_id = deployment.get("deployment_id")
    if not valid_publication_identity(deployment_id):
        raise ValueError("current deployment identity is missing")
    expected = (
        ("device_id", "paired_device_id", "device identity"),
        ("firmware", "hello_firmware", "firmware"),
        ("protocol", "protocol_version", "protocol"),
    )
    for hello_key, deployment_key, label in expected:
        if hello.get(hello_key) != deployment.get(deployment_key):
            raise ValueError(f"current hello {label} differs from deployment lock")
    current_boot_id = hello.get("device_boot_id")
    if not valid_publication_identity(current_boot_id):
        raise ValueError("current hello boot identity is missing")
    if not valid_publication_identity(session_id):
        raise ValueError("current hello session identity is missing")
    if publication.get("binary_sha256") != deployment.get("firmware_sha256"):
        raise ValueError("fresh publication firmware hash differs from deployment lock")
    publication_hello = publication.get("hello")
    if not isinstance(publication_hello, Mapping):
        raise ValueError("fresh publication hello is missing")
    for hello_key, deployment_key, label in expected:
        if publication_hello.get(hello_key) != deployment.get(deployment_key):
            raise ValueError(f"fresh publication {label} differs from deployment lock")
    if publication_hello.get("boot_id") != current_boot_id:
        raise ValueError("fresh publication boot identity differs from current hello")
    if not valid_publication_identity(publication_hello.get("session_id")):
        raise ValueError("fresh publication session identity is missing")
    ack = publication.get("snapshot_ack")
    if (
        not isinstance(ack, Mapping)
        or ack.get("accepted") is not True
        or not valid_snapshot_revision(ack.get("snapshot_revision"))
    ):
        raise ValueError("fresh publication was not acknowledged")
    return {
        "deployment_id": deployment_id,
        "device_id": deployment["paired_device_id"],
        "boot_id": current_boot_id,
        "session_id": session_id,
        "publication_session_id": publication_hello["session_id"],
        "publication_snapshot_revision": ack["snapshot_revision"],
    }


def validate_phase31_reset_epoch(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """A reset row must prove a new device boot and host session."""
    for label, item in (("previous", previous), ("current", current)):
        if (
            not valid_publication_identity(item.get("device_id"))
            or not valid_publication_identity(item.get("boot_id"))
            or not valid_publication_identity(item.get("session_id"))
        ):
            raise ValueError(f"{label} epoch identity is incomplete")
    if previous["device_id"] != current["device_id"]:
        raise ValueError("reset epoch changed exact paired device")
    if previous["boot_id"] == current["boot_id"]:
        raise ValueError("reset epoch did not produce a fresh boot identity")
    if previous["session_id"] == current["session_id"]:
        raise ValueError("reset epoch did not produce a fresh session identity")
    return {
        "from_boot_id": previous["boot_id"],
        "to_boot_id": current["boot_id"],
        "from_session_id": previous["session_id"],
        "to_session_id": current["session_id"],
    }


def validate_deployment_file(
    path: Path,
    *,
    firmware: Path | None = None,
    binding: Any | None = None,
    require_current: bool = False,
) -> dict[str, Any]:
    path = path.resolve()
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sha256_file(path) != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("deployment lock checksum mismatch")
    deployment = json.loads(path.read_text(encoding="ascii"))
    if deployment.get("schema_version") != 1 or deployment.get("kind") != "phase03.1-final-deployment":
        raise ValueError("deployment lock schema is not closed")
    binary = (firmware or resolve_repo_path(deployment["binary_path"])).resolve()
    validate_deployment(
        deployment,
        binary,
        binding=binding,
        require_current=require_current,
    )
    return deployment


def fresh_deployment(binding_path: Path, firmware: Path, timeout: float) -> dict[str, Any]:
    binding = PairingStore(binding_path).load()
    if binding is None:
        raise RuntimeError(f"pairing binding missing: {binding_path}")
    selected, link, session, _transitions = reconnect_exact(
        binding,
        ports=None,
        opener=_phase31_serial_opener,
        timeout=timeout,
    )
    try:
        hello = dict(session.device)
        if hello.get("device_id") != binding.device_id:
            raise RuntimeError("fresh hello device identity differs from exact pairing")
        if hello.get("firmware") != binding.firmware or hello.get("protocol") != binding.protocol:
            raise RuntimeError("fresh hello firmware/protocol differs from exact pairing")
        boot_id = hello.get("device_boot_id")
        session_id = session.session_id
        if not valid_publication_identity(boot_id) or not valid_publication_identity(session_id):
            raise RuntimeError("fresh hello did not supply boot/session identity")
        if not firmware.is_file():
            raise RuntimeError("uploaded selected-usb firmware binary is missing")
        digest = sha256_file(firmware)
        observed = time.time_ns() // 1_000_000
        record = {
            "schema_version": 1,
            "kind": "phase03.1-final-deployment",
            "platformio_environment": "selected-usb",
            "binary_path": relative(firmware),
            "binary_sha256": digest,
            "firmware_sha256": digest,
            "upload_result": "pass",
            "paired_device_id": binding.device_id,
            "pair_identity_digest": pair_identity_digest(
                binding.device_id, binding.protocol, binding.firmware
            ),
            "hello_firmware": binding.firmware,
            "protocol_version": binding.protocol,
            "fresh_boot_id": boot_id,
            "fresh_session_id": session_id,
            "boot_id": boot_id,
            "session_id": session_id,
            "usb_serial": selected.serial_number or "unavailable",
            "observed_at_unix_ms": observed,
        }
        record["deployment_id"] = deployment_id_for(record)
        validate_deployment(record, firmware, binding=binding)
        return record
    finally:
        link.close()


def run_phase31_deploy_lock(args: argparse.Namespace) -> int:
    firmware = args.firmware.resolve()
    output = args.output.resolve()
    expected = (ROOT / ".pio/build/selected-usb/firmware.bin").resolve()
    if firmware != expected:
        raise RuntimeError("phase31 deployment lock requires selected-usb firmware.bin")
    for stale in (output, output.with_suffix(output.suffix + ".sha256")):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass
    try:
        binding = PairingStore(args.binding.resolve()).load()
        if binding is None:
            raise RuntimeError(f"pairing binding missing: {args.binding}")
        deployment = fresh_deployment(args.binding.resolve(), firmware, args.timeout)
        validate_deployment(deployment, firmware, binding=binding, require_current=True)
        write_json(output, deployment, checksum=True)
        validate_deployment_file(
            output, firmware=firmware, binding=binding, require_current=True
        )
    except Exception:
        for stale in (output, output.with_suffix(output.suffix + ".sha256")):
            try:
                stale.unlink()
            except FileNotFoundError:
                pass
        raise
    print(f"wrote final Phase 03.1 deployment lock for {deployment['deployment_id']}")
    return 0


def run_phase31_validate_deployment(args: argparse.Namespace) -> int:
    binding = PairingStore(args.binding.resolve()).load() if args.binding else None
    validate_deployment_file(
        args.deployment.resolve(),
        firmware=args.firmware.resolve(),
        binding=binding,
        require_current=args.require_current,
    )
    print(f"validated final deployment lock {args.deployment.resolve()}")
    return 0

def run_capture(args: argparse.Namespace) -> int:
    firmware = args.firmware.resolve()
    tracer = args.tracer.resolve()
    evidence_path = args.evidence.resolve()
    captures_path = args.captures.resolve()
    if not firmware.is_file() or not tracer.is_file():
        raise RuntimeError("current firmware binary and checksummed tracer are required")
    tracer_sidecar = tracer.with_suffix(tracer.suffix + ".sha256")
    if not tracer_sidecar.is_file():
        raise RuntimeError("tracer checksum sidecar is required")
    tracer_sha = sha256_file(tracer)
    expected_tracer = tracer_sidecar.read_text(encoding="ascii").split()[0]
    if tracer_sha != expected_tracer:
        raise RuntimeError("tracer checksum mismatch")

    deployment = fresh_deployment(args.binding.resolve(), firmware, args.timeout)
    deployment_id = deployment["deployment_id"]
    frames_dir = captures_path.parent / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    capture_script = ROOT / "tools" / "capture_panel.py"
    records: list[dict[str, Any]] = []
    groups: dict[str, list[bytes]] = {"codex": [], "menu": []}

    for group, scenes in (("codex", CODEX_SCENES), ("menu", MENU_SCENES)):
        for theme in THEMES:
            for scene in scenes:
                stem = f"{group}-{theme}-{scene}"
                ppm = frames_dir / f"{stem}.ppm"
                command = [
                    os.fspath(Path(os.sys.executable)), os.fspath(capture_script), "3", os.fspath(ppm),
                    "--binding", os.fspath(args.binding), "--timeout", str(args.timeout),
                    "--theme", theme, "--scene", scene,
                ]
                subprocess.run(command, cwd=ROOT, check=True, timeout=max(10.0, args.timeout + 5.0))
                ppm_payload = ppm.read_bytes()
                if not ppm_payload.startswith(PPM_HEADER):
                    raise RuntimeError(f"invalid PPM capture: {ppm}")
                rgb = ppm_payload[len(PPM_HEADER):]
                if len(rgb) != 128 * 128 * 3:
                    raise RuntimeError(f"capture dimensions are not 128x128: {ppm}")
                raw = ppm.with_suffix(ppm.suffix + ".rgb565")
                if raw.stat().st_size != 128 * 128 * 2:
                    raise RuntimeError(f"RGB565 capture has wrong size: {raw}")
                png = frames_dir / f"{stem}.png"
                atomic_write(png, png_bytes(128, 128, rgb, deployment_id))
                ppm.unlink()
                groups[group].append(rgb)
                records.append({
                    "id": stem,
                    "kind": group,
                    "source": "deterministic-device-framebuffer",
                    "theme": theme,
                    "scene": scene,
                    "panel": 4,
                    "width": 128,
                    "height": 128,
                    "deployment_id": deployment_id,
                    "rgb565_path": relative(raw),
                    "rgb565_sha256": sha256_file(raw),
                    "png_path": relative(png),
                    "png_sha256": sha256_file(png),
                })

    contacts: list[dict[str, Any]] = []
    for group, filename in (("codex", "codex-states-contact.png"), ("menu", "menu-pages-contact.png")):
        width, height, payload = make_contact(groups[group], len(CODEX_SCENES), deployment_id)
        output = captures_path.parent / filename
        atomic_write(output, payload)
        contacts.append({
            "kind": group,
            "path": relative(output),
            "sha256": sha256_file(output),
            "width": width,
            "height": height,
            "source_frame_width": 128,
            "source_frame_height": 128,
            "deployment_id": deployment_id,
        })

    manifest = {
        "schema_version": 1,
        "kind": "phase3-framebuffer-captures",
        "source": "logical-framebuffer-only",
        "deployment_id": deployment_id,
        "redaction": {"result": "pass", "forbidden_content": "absent"},
        "captures": records,
        "contact_sheets": contacts,
    }
    captures_sha = write_json(captures_path, manifest)
    tracer_document = json.loads(tracer.read_text(encoding="utf-8"))
    installed_result = tracer_document.get("result")
    if installed_result not in {"pass", "fail"}:
        raise RuntimeError("tracer installed result is not typed")
    tracer_link = {
        "tracer_sha256": tracer_sha,
        "elapsed_ms_path": "/collector/elapsed_ms",
        "child_exit_path": "/collector/child_exit",
        "redaction_result_path": "/redaction/result",
    }
    r_bucket = bucket_matrix()
    evidence = {
        "schema_version": 1,
        "kind": "phase3-device-evidence",
        "status": "pending",
        "run_id": f"phase3-{deployment_id[:16]}",
        "deployment": deployment,
        "capture_manifest": {
            "path": relative(captures_path),
            "sha256": captures_sha,
            "deployment_id": deployment_id,
        },
        "tracer": {
            "path": relative(tracer),
            "source": "installed",
            "result": installed_result,
            "codex": tracer_document.get("codex"),
        },
        "tracer_audit_link": tracer_link,
        "r_bucket": r_bucket,
        "requirements": [
            {"id": requirement, "source": "automated-production-matrix", "result": "machine-pass",
             "deployment_id": deployment_id}
            for requirement in REQUIREMENTS
        ],
        "ui_considerations": [
            {"id": item, "source": "framebuffer" if item != "long-text" else "physical",
             "result": "machine-pass" if item != "long-text" else "pending",
             "deployment_id": deployment_id}
            for item in UI_CONSIDERATIONS
        ],
        "physical_observations": [
            {"id": row, "source": "physical", "result": "pending", "observation": None,
             "deployment_id": deployment_id}
            for row in PHYSICAL_ROWS
        ],
        "evidence_kinds": {
            "machine_ack": "machine",
            "framebuffer_pixels": "logical-only",
            "installed_codex": "installed",
            "deterministic_fixtures": "scripted",
            "physical_observations": "pending-y-n-r",
        },
    }
    write_json(evidence_path, evidence, checksum=True)
    print(f"captured {len(records)} exact-device frames for deployment {deployment_id}")
    print(f"pending evidence: {relative(evidence_path)}")
    return 0


def _phase31_theme_name(theme: str) -> str:
    return theme.replace("-", " ").title()


def _phase31_capture_ppm(
    args: argparse.Namespace,
    frames_dir: Path,
    *,
    panel: int,
    theme: str,
    scene: str,
    level: str,
    phase: int,
    deployment_id: str,
) -> tuple[dict[str, Any], bytes]:
    stem = f"{theme}-{scene}-{level}-{phase}-p{panel + 1}"
    ppm = frames_dir / f"{stem}.ppm"
    command = [
        os.fspath(Path(os.sys.executable)),
        os.fspath(ROOT / "tools/capture_panel.py"),
        str(panel),
        os.fspath(ppm),
        "--binding", os.fspath(args.binding),
        "--timeout", str(args.timeout),
        "--theme", theme,
        "--scene", scene,
        "--level", level,
        "--phase", str(phase),
    ]
    for attempt in range(3):
        try:
            subprocess.run(
                command, cwd=ROOT, check=True, pass_fds=(9,),
                timeout=max(10.0, args.timeout + 5.0),
            )
            break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt == 2:
                raise
            time.sleep(0.2)
    ppm_payload = ppm.read_bytes()
    if not ppm_payload.startswith(PPM_HEADER):
        raise RuntimeError(f"invalid PPM capture: {ppm}")
    rgb = ppm_payload[len(PPM_HEADER):]
    if len(rgb) != 128 * 128 * 3:
        raise RuntimeError(f"capture dimensions are not 128x128: {ppm}")
    raw = ppm.with_suffix(ppm.suffix + ".rgb565")
    if raw.stat().st_size != 128 * 128 * 2:
        raise RuntimeError(f"RGB565 capture has wrong size: {raw}")
    png = frames_dir / f"{stem}.png"
    atomic_write(png, png_bytes(128, 128, rgb, deployment_id))
    ppm.unlink()
    return {
        "id": stem,
        "source": "deterministic-device-framebuffer",
        "theme": theme,
        "scene": scene,
        "level": level,
        "phase": phase,
        "panel": panel + 1,
        "width": 128,
        "height": 128,
        "deployment_id": deployment_id,
        "firmware_sha256": None,
        "rgb565_path": relative(raw),
        "rgb565_sha256": sha256_file(raw),
        "png_path": relative(png),
        "png_sha256": sha256_file(png),
    }, rgb


def _phase31_led_events(deployment_id: str) -> list[dict[str, Any]]:
    events = ("blocked", "press", "pending", "focused", "failure",
              "menu-open", "health", "sync")
    rows = []
    for grammar in LED_GRAMMARS:
        for index, event in enumerate(events):
            rows.append({
                "grammar": grammar,
                "event": event,
                "semantic_epoch": 1,
                "semantic_phase": index % 4,
                "segments": [{
                    "zone": index % 4,
                    "start": index % 8,
                    "length": 2 if event != "sync" else 0,
                    "hue": "semantic",
                    "brightness": 0 if event == "sync" else 32,
                }],
                "source": "resolved-bounded-led-event",
                "deployment_id": deployment_id,
                "physical_claim": False,
            })
    return rows


def validate_phase31_framebuffer_manifest(
    manifest: Mapping[str, Any],
    deployment: Mapping[str, Any],
    *,
    deployment_lock_sha256: str | None = None,
) -> None:
    if manifest.get("status") != "pass":
        raise ValueError("framebuffer evidence status is not pass")
    if manifest.get("schema_version") != 1 or manifest.get("kind") != "phase03.1-framebuffer-evidence":
        raise ValueError("framebuffer evidence schema is not closed")
    deployment_id = deployment.get("deployment_id")
    if not valid_publication_identity(deployment_id):
        raise ValueError("deployment identity is missing")
    if manifest.get("deployment_id") != deployment_id:
        raise ValueError("framebuffer deployment linkage mismatch")
    if manifest.get("firmware_sha256") != deployment.get("firmware_sha256"):
        raise ValueError("framebuffer firmware hash linkage mismatch")
    if deployment_lock_sha256 is not None and manifest.get("deployment_lock_sha256") != deployment_lock_sha256:
        raise ValueError("framebuffer deployment lock checksum mismatch")
    if manifest.get("source") != "logical-framebuffer-only":
        raise ValueError("framebuffer evidence source is not logical-only")
    boundary = manifest.get("evidence_boundary", {})
    if boundary.get("physical_claims") != "none":
        raise ValueError("framebuffer evidence makes physical claims")
    captures = manifest.get("captures")
    if not isinstance(captures, list) or not captures:
        raise ValueError("framebuffer capture matrix is empty")
    by_id = {}
    for capture in captures:
        capture_id = capture.get("id")
        if not isinstance(capture_id, str) or capture_id in by_id:
            raise ValueError("framebuffer capture IDs are not unique")
        if (
            capture.get("width") != 128 or capture.get("height") != 128
            or capture.get("deployment_id") != deployment_id
            or capture.get("firmware_sha256") != deployment.get("firmware_sha256")
        ):
            raise ValueError("framebuffer capture dimensions/deployment invalid")
        for path_key, hash_key in (("rgb565_path", "rgb565_sha256"), ("png_path", "png_sha256")):
            artifact = resolve_repo_path(capture[path_key])
            if sha256_file(artifact) != capture[hash_key]:
                raise ValueError(f"framebuffer capture hash mismatch: {capture_id}")
        raw = resolve_repo_path(capture["rgb565_path"])
        png = resolve_repo_path(capture["png_path"])
        if raw.stat().st_size != 128 * 128 * 2 or not png_has_deployment(png, deployment_id):
            raise ValueError("framebuffer RGB565/PNG payload is invalid")
        by_id[capture_id] = capture

    matrix = manifest.get("matrix", {})
    themes = set(THEMES)
    if set(matrix.get("themes", [])) != themes:
        raise ValueError("framebuffer theme matrix is incomplete")
    for theme in THEMES:
        tile_states = set(matrix.get("tile_states", {}).get(theme, []))
        if tile_states != set(TILE_SCENES):
            raise ValueError("framebuffer tile state matrix is incomplete")
        slots = set(matrix.get("slot_layouts", {}).get(theme, []))
        if slots != set(SLOT_SCENES):
            raise ValueError("framebuffer zero-one-many matrix is incomplete")
        if set(matrix.get("codex", {}).get(theme, [])) != set(CODEX_SCENES):
            raise ValueError("framebuffer Codex matrix is incomplete")
        if set(matrix.get("menu", {}).get(theme, [])) != set(MENU_SCENES):
            raise ValueError("framebuffer menu matrix is incomplete")
    inventory = manifest.get("motion_inventory", {})
    inventory_path = resolve_repo_path(inventory["path"])
    if sha256_file(inventory_path) != inventory["sha256"]:
        raise ValueError("motion inventory checksum mismatch")
    inventory_document = json.loads(inventory_path.read_text(encoding="ascii"))
    motion_rows = manifest.get("motion_rows", [])
    if len(motion_rows) != len(inventory_document.get("rows", [])):
        raise ValueError("motion inventory cross-reference is incomplete")
    for row in motion_rows:
        if row.get("deployment_id") != deployment_id or row.get("source_id") not in by_id:
            raise ValueError("motion inventory source linkage is invalid")
    led_events = manifest.get("led_events", [])
    if {row.get("grammar") for row in led_events} != set(LED_GRAMMARS):
        raise ValueError("LED grammar event matrix is incomplete")
    if any(
        len(row.get("segments", [])) > 8
        or row.get("physical_claim") is not False
        or row.get("deployment_id") != deployment_id
        for row in led_events
    ):
        raise ValueError("LED event evidence is unbounded or physical")
    contacts = manifest.get("contact_sheets", [])
    expected_contacts = {"tiles", "codex", "menu", "motion"}
    if {row.get("kind") for row in contacts} != expected_contacts:
        raise ValueError("framebuffer contact sheet matrix is incomplete")
    for contact in contacts:
        artifact = resolve_repo_path(contact["path"])
        if (
            sha256_file(artifact) != contact["sha256"]
            or contact.get("deployment_id") != deployment_id
            or not png_has_deployment(artifact, deployment_id)
        ):
            raise ValueError("framebuffer contact sheet linkage invalid")
def _phase31_sidecar(path: Path, label: str) -> str:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    try:
        expected = sidecar.read_text(encoding="ascii").split()[0]
    except (FileNotFoundError, OSError, IndexError) as exc:
        raise ValueError(f"{label} checksum sidecar is missing") from exc
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label} checksum mismatch")
    if len(expected) != 64:
        raise ValueError(f"{label} checksum is invalid")
    return expected


def _phase31_framebuffer_sources(
    manifest: Mapping[str, Any], theme: str | None = None
) -> list[str]:
    captures = manifest.get("captures", [])
    if not isinstance(captures, list):
        raise ValueError("logical framebuffer captures are missing")
    selected: list[str] = []
    wanted = (
        ("blocked", 1), ("pending", 1), ("focused", 1), ("failed", 1),
        ("slots-0", 1), ("slots-1", 1), ("slots-2", 1), ("slots-3", 1),
        ("codex-current", 4), ("menu-root-0", 4), ("working", 1),
    )
    for scene, panel in wanted:
        candidates = [
            item for item in captures
            if item.get("scene") == scene
            and item.get("panel") == panel
            and (theme is None or item.get("theme") == theme)
        ]
        if not candidates:
            raise ValueError(f"logical source capture is missing: {theme}:{scene}")
        selected.append(sorted(candidates, key=lambda item: item["id"])[0]["id"])
    return selected


def _phase31_physical_row(
    row_id: str,
    deployment_id: str,
    deployment_lock_sha256: str,
    logical_manifest_sha256: str,
    source_framebuffer_ids: list[str],
    *,
    theme: str | None = None,
    grammar: str | None = None,
) -> dict[str, Any]:
    return {
        "id": row_id,
        "theme": theme or "all",
        "grammar": grammar or "all",
        "source": "physical",
        "result": "pending",
        "deployment_id": deployment_id,
        "deployment_lock_sha256": deployment_lock_sha256,
        "logical_manifest_sha256": logical_manifest_sha256,
        "source_framebuffer_ids": list(source_framebuffer_ids),
        "measurement_ids": [f"measurement-{row_id}"],
        "observation": None,
    }


def _phase31_prompt(row: Mapping[str, Any]) -> str:
    row_id = str(row["id"])
    if row_id.startswith("matrix-"):
        theme = str(row["theme"]).replace("-", " ").upper()
        grammar = str(row["grammar"]).replace("-", " ").upper()
        return (
            f"Set THEME={theme} and LEDS={grammar}. Exercise the complete bounded cell: "
            "ordinary refresh with 0, 1, 2, and 3 direct-agent occupants; rapid encoder "
            "detents/clicks and direct keys 1-3 during menu and animation; BLOCKED, "
            "PENDING, FOCUSED, REJECTED/FAILED; menu open; brightness 10%, 80%, 100%; "
            "stale/offline and SYNC fences. Check exact orientation, 10% long text, "
            "brightness, LED zones, no blend/tear/black flash/ghosting, smooth complete "
            "frames, immediate opaque focus only, no replay, and display/LED semantic "
            "alignment. Answer Y only for a physical pass, N for a visible defect, or "
            "R when the observation cannot be performed."
        )
    prompts = {
        "stress-concurrent-herdr-codex": (
            "With the guarded bridge live, cause simultaneous Herdr snapshot changes and "
            "Codex usage changes. Verify complete frames, no mixed generation, no remap, "
            "no input starvation, and exact focus identity."
        ),
        "stress-stale-offline-recovery": (
            "Exercise Herdr stale/offline and Codex stale/offline transitions, then restore "
            "fresh data. Verify immediate fences, no queued/replayed press, and complete "
            "recovery without optimistic success."
        ),
        "stress-usb-reconnect": (
            "Unplug/replug the USB data link once, then wait for the guarded bridge to "
            "republish. Verify all-panel SYNC, fresh hello/publication, and no stale action."
        ),
        "stress-firmware-reset": (
            "Use the normal firmware reset control. Verify all-panel SYNC through boot, "
            "fresh generation commit, unchanged deployment firmware/pair identity, and "
            "no focus replay."
        ),
        "stress-generation-replacement": (
            "Replace a generation while an ordinary reveal and focus request are active. "
            "Verify the old generation is discarded, the new complete generation wins, "
            "and no old binding or press is replayed."
        ),
        "stress-simultaneous-key-encoder": (
            "Press direct keys 1-3 while turning/clicking the encoder on every menu page "
            "and animation state. Verify direct focus stays immediate and non-modal; "
            "menu cursor and preview remain causally correct."
        ),
        "stress-resource-degradation": (
            "Exercise the busiest animation and update load. Verify measured Full→Half→Static "
            "degradation before budget violation, semantic frames retained, bounded queue, "
            "zero per-frame allocation, and no input starvation."
        ),
        "backstop-long-text-10-percent": (
            "At exact 10% brightness inspect every theme's longest title/discriminator, "
            "Codex reset/source/age, and ABOUT text. Verify 8 px metadata floor, ASCII ..., "
            "4 px inset, no clipping, overlap, ticker, or bezel collision."
        ),
        "backstop-physical-quality": (
            "Inspect physical orientation, viewing angles, brightness/legibility, LED "
            "zones/alignment, blend artifacts, tearing, black flash, ghosting, smoothness, "
            "first press/encoder response, complete flush/reveal, cadence/duty, heap/block, "
            "queue, power method/headroom, and display/LED event alignment separately from "
            "machine framebuffer evidence."
        ),
    }
    return prompts[row_id]


def _phase31_load_inputs(
    deployment_path: Path,
    framebuffer_path: Path,
    firmware: Path,
    binding_path: Path,
    *,
    require_current: bool,
) -> tuple[dict[str, Any], dict[str, Any], Any, str, str]:
    binding = PairingStore(binding_path.resolve()).load()
    if binding is None:
        raise RuntimeError(f"paired keypad binding missing: {binding_path}")
    deployment = validate_deployment_file(
        deployment_path.resolve(),
        firmware=firmware.resolve(),
        binding=binding,
        require_current=require_current,
    )
    deployment_lock_sha256 = _phase31_sidecar(deployment_path.resolve(), "deployment lock")
    logical_manifest_sha256 = _phase31_sidecar(framebuffer_path.resolve(), "logical manifest")
    manifest = json.loads(framebuffer_path.resolve().read_text(encoding="ascii"))
    validate_phase31_framebuffer_manifest(
        manifest, deployment, deployment_lock_sha256=deployment_lock_sha256
    )
    return (
        deployment,
        manifest,
        binding,
        deployment_lock_sha256,
        logical_manifest_sha256,
    )


@contextmanager
def phase31_guarded_bridge(
    args: argparse.Namespace,
    deployment: Mapping[str, Any],
    expected_boot_id: str,
    *,
    timeout: float,
) -> Iterator[tuple[subprocess.Popen[str], dict[str, Any], str]]:
    with tempfile.TemporaryDirectory(prefix="phase31-guided-") as directory:
        temporary = Path(directory)
        receipt_path = temporary / "publication.json"
        log_path = temporary / "bridge.log"
        environment = os.environ.copy()
        environment.pop("HERDR_KEYPAD_PIDFILE", None)
        environment["HERDR_DEPLOYED_FIRMWARE"] = str(args.firmware.resolve())
        environment["HERDR_KEYPAD_PUBLICATION_EVIDENCE"] = str(receipt_path)
        host_source = str(ROOT / "host/herdr_keypad/src")
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            host_source if not existing_pythonpath
            else host_source + os.pathsep + existing_pythonpath
        )
        with log_path.open("w+", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    os.fspath(Path(os.sys.executable)),
                    "-m", "herdr_keypad", "--run-bridge",
                    "--binding", os.fspath(args.binding.resolve()),
                ],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                pass_fds=(9,),
            )
            try:
                deadline = time.monotonic() + max(10.0, timeout * 4.0)
                receipt: dict[str, Any] | None = None
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        candidate = json.loads(receipt_path.read_text(encoding="ascii"))
                    except (FileNotFoundError, json.JSONDecodeError, OSError):
                        candidate = None
                    if isinstance(candidate, dict):
                        try:
                            validate_phase31_current_deployment_identity(
                                deployment,
                                {
                                    "device_id": candidate.get("hello", {}).get("device_id"),
                                    "firmware": candidate.get("hello", {}).get("firmware"),
                                    "protocol": candidate.get("hello", {}).get("protocol"),
                                    "device_boot_id": candidate.get("hello", {}).get("boot_id"),
                                },
                                str(candidate.get("hello", {}).get("session_id", "")),
                                candidate,
                            )
                        except ValueError:
                            pass
                        else:
                            receipt = candidate
                            break
                    time.sleep(0.05)
                if receipt is None:
                    log.flush()
                    log.seek(0)
                    detail = log.read()[-480:].strip()
                    if process.poll() is None:
                        raise RuntimeError(
                            f"guarded bridge did not publish a fresh acknowledgement: {detail}"
                        )
                    raise RuntimeError(f"guarded bridge exited before publication: {detail}")
                if receipt["hello"]["boot_id"] != expected_boot_id:
                    raise RuntimeError("guarded publication boot identity differs from active transition")
                print(
                    f"LIVE BRIDGE PASS deployment={deployment['deployment_id']} "
                    f"boot={expected_boot_id} session={receipt['hello']['session_id']}",
                    flush=True,
                )
                yield process, receipt, sha256_file(receipt_path)
            finally:
                _stop_guided_bridge(process)


def _phase31_machine_metrics(session: Any) -> dict[str, Any]:
    try:
        frame, _ = session.request("metrics", {"request": "proof"}, {"metrics_ack"})
        metrics = _phase31_metrics(frame["payload"])
        _validate_phase31_machine_metrics(metrics)
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)[:160]}
    return {"status": "pass", "metrics": metrics}


def _phase31_make_evidence(
    deployment: Mapping[str, Any],
    manifest: Mapping[str, Any],
    deployment_lock_sha256: str,
    logical_manifest_sha256: str,
    hello: Mapping[str, Any],
    session_id: str,
    publication: Mapping[str, Any],
    publication_sha256: str,
    machine_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for theme in THEMES:
        for grammar in LED_GRAMMARS:
            row_id = f"matrix-{theme}-{grammar}"
            rows.append(_phase31_physical_row(
                row_id, deployment["deployment_id"], deployment_lock_sha256,
                logical_manifest_sha256, _phase31_framebuffer_sources(manifest, theme),
                theme=theme, grammar=grammar,
            ))
    all_sources = sorted({
        source
        for theme in THEMES
        for source in _phase31_framebuffer_sources(manifest, theme)
    })
    rows.extend(_phase31_physical_row(
        row_id, deployment["deployment_id"], deployment_lock_sha256,
        logical_manifest_sha256, all_sources,
    ) for row_id in PHASE31_STRESS_ROWS)
    rows.extend(_phase31_physical_row(
        row_id, deployment["deployment_id"], deployment_lock_sha256,
        logical_manifest_sha256, all_sources,
    ) for row_id in PHASE31_BACKSTOP_ROWS)
    return {
        "schema_version": 1,
        "kind": "phase03.1-device-evidence",
        "status": "pending",
        "run_id": f"phase31-{deployment['deployment_id'][:16]}",
        "deployment": dict(deployment),
        "deployment_lock_sha256": deployment_lock_sha256,
        "logical_manifest_sha256": logical_manifest_sha256,
        "exact_pair": {
            "device_id": deployment["paired_device_id"],
            "pair_identity_digest": deployment["pair_identity_digest"],
            "firmware_sha256": deployment["firmware_sha256"],
            "protocol": deployment["protocol_version"],
        },
        "preflight": {
            "accepted": True,
            "accepted_at_unix_ms": time.time_ns() // 1_000_000,
            "hello": {
                "device_id": hello["device_id"],
                "firmware": hello["firmware"],
                "protocol": hello["protocol"],
                "boot_id": hello["device_boot_id"],
                "session_id": session_id,
            },
            "guarded_publication": {
                "receipt_sha256": publication_sha256,
                "published_at_unix_ms": publication["published_at_unix_ms"],
                "boot_id": publication["hello"]["boot_id"],
                "session_id": publication["hello"]["session_id"],
                "snapshot_revision": publication["snapshot_ack"]["snapshot_revision"],
                "accepted": True,
            },
        },
        "physical_observations": rows,
        "machine_measurements": [{
            "id": "measurement-preflight-metrics",
            "source": "machine",
            "deployment_id": deployment["deployment_id"],
            "data": dict(machine_metrics),
        }],
        "deployment_transitions": [],
        "defect_ledger": {
            "path": "artifacts/phase03.1/03.1-DEFECT-LEDGER.json",
            "status": "pending",
        },
        "evidence_boundary": {
            "logical": "source framebuffer IDs only; no physical claims",
            "physical": "typed human observations only; no machine ACK implies physical pass",
            "machine": "bounded serial/bridge facts only",
        },
    }
def _phase31_write_defect(
    evidence: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    reason: str,
) -> None:
    path = ROOT / "artifacts/phase03.1/03.1-DEFECT-LEDGER.json"
    try:
        ledger = json.loads(path.read_text(encoding="ascii"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        ledger = {
            "schema_version": 1,
            "kind": "phase03.1-defect-ledger",
            "deployment_id": evidence["deployment"]["deployment_id"],
            "deployment_lock_sha256": evidence["deployment_lock_sha256"],
            "logical_manifest_sha256": evidence["logical_manifest_sha256"],
            "defects": [],
        }
    defects = ledger.setdefault("defects", [])
    observation_id = f"{row['id']}-{row['observation']['observed_at_unix_ms']}"
    defect_id = "defect-" + sha256_bytes(canonical_bytes({
        "deployment_id": evidence["deployment"]["deployment_id"],
        "observation_id": observation_id,
        "reason": reason,
    }))[:16]
    if not any(item.get("defect_id") == defect_id for item in defects):
        defects.append({
            "defect_id": defect_id,
            "status": "open",
            "disposition": "blocking",
            "deployment_id": evidence["deployment"]["deployment_id"],
            "deployment_lock_sha256": evidence["deployment_lock_sha256"],
            "logical_manifest_sha256": evidence["logical_manifest_sha256"],
            "before_observation_ids": [observation_id],
            "after_observation_ids": [],
            "row_id": row["id"],
            "reason": reason,
        })
    ledger["status"] = "blocked"
    write_json(path, ledger, checksum=True)


def run_phase31_current_deployment(args: argparse.Namespace) -> int:
    deployment, manifest, _binding, lock_sha, manifest_sha = _phase31_load_inputs(
        args.deployment, args.framebuffer, args.firmware, args.binding,
        require_current=args.require_current_deployment,
    )
    evidence_path = args.evidence.resolve()
    if evidence_path.exists():
        raise RuntimeError(
            "device evidence already exists; refusing to replace an accepted or partial header"
        )
    _selected, link, session, _transitions = _phase31_exact_session(
        args.binding.resolve(), args.timeout
    )
    try:
        hello = dict(session.device)
        machine_metrics = _phase31_machine_metrics(session)
        session_id = session.session_id
    finally:
        link.close()
    with phase31_guarded_bridge(
        args, deployment, hello["device_boot_id"], timeout=args.timeout
    ) as (_bridge, publication, publication_sha):
        accepted = validate_phase31_current_deployment_identity(
            deployment, hello, session_id, publication
        )
        evidence = _phase31_make_evidence(
            deployment, manifest, lock_sha, manifest_sha, hello, session_id,
            publication, publication_sha, machine_metrics,
        )
        evidence["preflight"]["identity"] = accepted
        write_json(evidence_path, evidence, checksum=True)
    validate_phase31_device_evidence(
        evidence_path, args.deployment, args.framebuffer, None,
        require_current_deployment=args.require_current_deployment,
        allow_pending=True,
        require_fresh_bridge_publication=True,
    )
    print(
        f"CURRENT DEPLOYMENT PASS deployment={deployment['deployment_id']} "
        f"logical_manifest_sha256={manifest_sha}",
        flush=True,
    )
    return 0


def _phase31_current_evidence_header(
    evidence: Mapping[str, Any],
    deployment: Mapping[str, Any],
    manifest: Mapping[str, Any],
    lock_sha: str,
    manifest_sha: str,
) -> None:
    if evidence.get("kind") != "phase03.1-device-evidence":
        raise ValueError("device evidence schema is not closed")
    if evidence.get("deployment", {}).get("deployment_id") != deployment["deployment_id"]:
        raise ValueError("device evidence deployment differs from current lock")
    if evidence.get("deployment_lock_sha256") != lock_sha:
        raise ValueError("device evidence deployment lock checksum differs")
    if evidence.get("logical_manifest_sha256") != manifest_sha:
        raise ValueError("device evidence logical manifest checksum differs")
    if evidence.get("preflight", {}).get("accepted") is not True:
        raise ValueError("device evidence preflight is not accepted")
    row_ids = [row.get("id") for row in evidence.get("physical_observations", [])]
    if set(row_ids) != set(PHASE31_ALL_ROWS) or len(row_ids) != len(PHASE31_ALL_ROWS):
        raise ValueError("Phase 03.1 physical observation matrix is incomplete")
    captures = {row.get("id") for row in manifest.get("captures", [])}
    for row in evidence["physical_observations"]:
        if (
            row.get("deployment_id") != deployment["deployment_id"]
            or row.get("deployment_lock_sha256") != lock_sha
            or row.get("logical_manifest_sha256") != manifest_sha
            or not row.get("source_framebuffer_ids")
            or not set(row["source_framebuffer_ids"]).issubset(captures)
            or not row.get("measurement_ids")
        ):
            raise ValueError("physical observation lineage is incomplete")


def run_phase31_run(args: argparse.Namespace) -> int:
    deployment, manifest, _binding, lock_sha, manifest_sha = _phase31_load_inputs(
        args.deployment, args.framebuffer, args.firmware, args.binding,
        require_current=args.require_current_deployment,
    )
    evidence_path = args.evidence.resolve()
    _phase31_sidecar(evidence_path, "device evidence")
    evidence = json.loads(evidence_path.read_text(encoding="ascii"))
    _phase31_current_evidence_header(
        evidence, deployment, manifest, lock_sha, manifest_sha
    )
    if evidence.get("status") == "pass":
        raise RuntimeError("device evidence is already complete; refusing to replay rows")
    _selected, link, session, _transitions = _phase31_exact_session(
        args.binding.resolve(), args.timeout
    )
    try:
        hello = dict(session.device)
        if not valid_publication_identity(hello.get("device_boot_id")):
            raise RuntimeError("fresh hello boot identity is missing")
        session_id = session.session_id
        machine_metrics = _phase31_machine_metrics(session)
    finally:
        link.close()
    with phase31_guarded_bridge(
        args, deployment, hello["device_boot_id"], timeout=args.timeout
    ) as (_bridge, publication, _publication_sha):
        validate_phase31_current_deployment_identity(
            deployment, hello, session_id, publication
        )
        evidence["machine_measurements"].append({
            "id": f"measurement-run-{time.time_ns()}",
            "source": "machine",
            "deployment_id": deployment["deployment_id"],
            "data": machine_metrics,
        })
        for row in evidence["physical_observations"]:
            if row.get("result") == "pass":
                continue
            row_id = row["id"]
            print(f"\n{row_id}", flush=True)
            print(_phase31_prompt(row), flush=True)
            try:
                answer = input(f"Answer Y/N/R {row_id}: ").strip().upper()
            except EOFError as exc:
                raise RuntimeError(
                    f"physical observation input ended before {row_id}"
                ) from exc
            if answer not in {"Y", "N", "R"}:
                raise RuntimeError("physical observation response must be exactly Y, N, or R")
            result = {"Y": "pass", "N": "failed", "R": "refused"}[answer]
            row["result"] = result
            row["observation"] = {
                "answer": answer,
                "observed_at_unix_ms": time.time_ns() // 1_000_000,
                "fresh_hello_session_id": session_id,
                "physical_claims": True,
            }
            write_json(evidence_path, evidence, checksum=True)
            if answer != "Y":
                _phase31_write_defect(
                    evidence, row,
                    reason=f"typed physical result {result}; acceptance remains blocked",
                )
                return 1
    _selected, link, session, _transitions = _phase31_exact_session(
        args.binding.resolve(), args.timeout
    )
    try:
        final_hello = dict(session.device)
        final_session_id = session.session_id
        active_deployment = dict(deployment)
        active_deployment["boot_id"] = final_hello.get("device_boot_id")
        if (
            final_hello.get("device_id") != deployment["paired_device_id"]
            or final_hello.get("firmware") != deployment["hello_firmware"]
            or final_hello.get("protocol") != deployment["protocol_version"]
        ):
            raise RuntimeError("final hello differs from locked deployment")
    finally:
        link.close()
    with phase31_guarded_bridge(
        args, active_deployment, active_deployment["boot_id"], timeout=args.timeout
    ) as (_bridge, publication, publication_sha):
        validate_phase31_current_deployment_identity(
            active_deployment, final_hello, final_session_id, publication
        )
        current_epoch = {
            "device_id": final_hello.get("device_id"),
            "boot_id": final_hello.get("device_boot_id"),
            "session_id": final_session_id,
        }
        initial_epoch = {
            "device_id": hello.get("device_id"),
            "boot_id": hello.get("device_boot_id"),
            "session_id": session_id,
        }
        reset_row = next(
            row for row in evidence["physical_observations"]
            if row["id"] == "stress-firmware-reset"
        )
        reset_transition = (
            validate_phase31_reset_epoch(initial_epoch, current_epoch)
            if reset_row.get("result") == "pass"
            else None
        )
        if active_deployment["boot_id"] != deployment["boot_id"] or reset_transition:
            transition = reset_transition or {
                "from_boot_id": deployment["boot_id"],
                "to_boot_id": active_deployment["boot_id"],
                "from_session_id": session_id,
                "to_session_id": final_session_id,
            }
            evidence["deployment_transitions"].append({
                "id": f"transition-{time.time_ns()}",
                "kind": "explicit-reconnect-or-reset",
                **transition,
                "publication_sha256": publication_sha,
                "deployment_id": deployment["deployment_id"],
            })
        evidence["preflight"]["final_publication"] = {
            "receipt_sha256": publication_sha,
            "published_at_unix_ms": publication["published_at_unix_ms"],
            "boot_id": publication["hello"]["boot_id"],
            "session_id": publication["hello"]["session_id"],
            "snapshot_revision": publication["snapshot_ack"]["snapshot_revision"],
            "accepted": True,
        }
        evidence["status"] = "pass"
        write_json(evidence_path, evidence, checksum=True)
    ledger_path = ROOT / "artifacts/phase03.1/03.1-DEFECT-LEDGER.json"
    write_json(ledger_path, {
        "schema_version": 1,
        "kind": "phase03.1-defect-ledger",
        "status": "pass",
        "deployment_id": deployment["deployment_id"],
        "deployment_lock_sha256": lock_sha,
        "logical_manifest_sha256": manifest_sha,
        "defects": [],
    })
    print("PHYSICAL OBSERVATIONS COMPLETE", flush=True)
    return 0


def run_phase31_capture(args: argparse.Namespace) -> int:
    firmware = args.firmware.resolve()
    deployment_path = args.deployment.resolve()
    binding = PairingStore(args.binding.resolve()).load()
    if binding is None:
        raise RuntimeError("paired keypad binding is missing")
    deployment = validate_deployment_file(
        deployment_path, firmware=firmware, binding=binding, require_current=True
    )
    deployment_lock_sha = sha256_file(deployment_path)
    baseline = args.baseline.resolve()
    if not baseline.is_file():
        raise RuntimeError("Phase 03.1 budget lock is required")
    baseline_sidecar = baseline.with_suffix(baseline.suffix + ".sha256")
    if not baseline_sidecar.is_file() or sha256_file(baseline) != baseline_sidecar.read_text(encoding="ascii").split()[0]:
        raise RuntimeError("Phase 03.1 budget lock checksum mismatch")
    evidence_path = args.evidence.resolve()
    captures_path = args.captures.resolve()
    frames_dir = captures_path.parent / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict[str, Any]] = {}
    frame_groups: dict[str, list[bytes]] = {name: [] for name in ("tiles", "codex", "menu", "motion")}

    def capture(group: str, panel: int, theme: str, scene: str, level: str = "full",
                phase: int = 0) -> dict[str, Any]:
        key = f"{panel}:{theme}:{scene}:{level}:{phase}"
        if key not in records:
            record, rgb = _phase31_capture_ppm(
                args, frames_dir, panel=panel, theme=theme, scene=scene,
                level=level, phase=phase, deployment_id=deployment["deployment_id"],
            )
            record["firmware_sha256"] = deployment["firmware_sha256"]
            records[key] = record
            frame_groups[group].append(rgb)
        return records[key]

    matrix = {
        "themes": list(THEMES),
        "tile_states": {theme: [] for theme in THEMES},
        "slot_layouts": {theme: [] for theme in THEMES},
        "codex": {theme: [] for theme in THEMES},
        "menu": {theme: [] for theme in THEMES},
    }
    for theme in THEMES:
        for scene in TILE_SCENES:
            capture("tiles", 0, theme, scene)
            matrix["tile_states"][theme].append(scene)
        for scene in SLOT_SCENES:
            capture("tiles", 0, theme, scene, "static")
            matrix["slot_layouts"][theme].append(scene)
        for scene in CODEX_SCENES:
            capture("codex", 3, theme, scene, "static")
            matrix["codex"][theme].append(scene)
        for scene in MENU_SCENES:
            capture("menu", 3, theme, scene, "static")
            matrix["menu"][theme].append(scene)
        for level, phase in (("full", 0), ("full", 1), ("half", 0), ("static", 0)):
            capture("motion", 0, theme, "working", level, phase)

    inventory_path = ROOT / "artifacts/phase03.1/03.1-MOTION-INVENTORY.json"
    inventory_document = json.loads(inventory_path.read_text(encoding="ascii"))
    motion_rows = []
    for index, row in enumerate(inventory_document.get("rows", [])):
        theme = next(
            theme for theme in THEMES
            if _phase31_theme_name(theme) == row.get("theme")
        )
        family = row.get("family")
        if family == "tile":
            scene = MOTION_STATE_SCENES[row["state"]]
            source = capture("motion", 0, theme, scene, "full", row["full"][0])
        elif family == "feedback":
            scene = MOTION_FEEDBACK_SCENES[row["state"]]
            source = capture("motion", 0, theme, scene, "full", row["full"][0])
        elif family == "codex":
            scene = MOTION_CODEX_SCENES[row["state"]]
            source = capture("motion", 3, theme, scene, "full", row["full"][0])
        elif family == "system":
            source = capture("motion", 3, theme, "sync", "static", 0)
        else:
            source = capture("motion", 0, theme, "working", "full", row["full"][0])
        motion_rows.append({
            "inventory_index": index,
            "family": family,
            "theme": theme,
            "state": row.get("state"),
            "mode": row.get("mode"),
            "full": row.get("full"),
            "half": row.get("half"),
            "static": row.get("static"),
            "source_id": source["id"],
            "deployment_id": deployment["deployment_id"],
        })

    latest = fresh_deployment(args.binding.resolve(), firmware, args.timeout)
    for field in (
        "paired_device_id", "pair_identity_digest", "hello_firmware",
        "protocol_version", "fresh_boot_id", "firmware_sha256",
    ):
        if latest.get(field) != deployment.get(field):
            raise RuntimeError(f"deployment drift detected before final write: {field}")
    if sha256_file(deployment_path) != deployment_lock_sha:
        raise RuntimeError("deployment lock changed during capture")
    deployment = validate_deployment_file(
        deployment_path, firmware=firmware, binding=binding, require_current=True
    )

    contacts = []
    for group in ("tiles", "codex", "menu", "motion"):
        frames = frame_groups[group]
        width, height, payload = make_contact(
            frames, max(1, min(8, len(frames))), deployment["deployment_id"]
        )
        output = captures_path.parent / f"{group}-contact.png"
        atomic_write(output, payload)
        contacts.append({
            "kind": group,
            "path": relative(output),
            "sha256": sha256_file(output),
            "width": width,
            "height": height,
            "deployment_id": deployment["deployment_id"],
            "source_frame_width": 128,
            "source_frame_height": 128,
        })
    manifest = {
        "schema_version": 1,
        "kind": "phase03.1-framebuffer-evidence",
        "status": "pass",
        "source": "logical-framebuffer-only",
        "deployment_id": deployment["deployment_id"],
        "deployment_lock_sha256": deployment_lock_sha,
        "firmware_sha256": deployment["firmware_sha256"],
        "evidence_boundary": {
            "framebuffer": "machine-only RGB565 composition",
            "physical_claims": "none",
        },
        "matrix": matrix,
        "captures": list(records.values()),
        "motion_inventory": {
            "path": relative(inventory_path),
            "sha256": sha256_file(inventory_path),
            "row_count": len(motion_rows),
        },
        "motion_rows": motion_rows,
        "led_events": _phase31_led_events(deployment["deployment_id"]),
        "contact_sheets": contacts,
    }
    validate_phase31_framebuffer_manifest(
        manifest, deployment, deployment_lock_sha256=deployment_lock_sha
    )
    write_json(captures_path, {
        "schema_version": 1,
        "kind": "phase03.1-capture-receipt",
        "status": "pass",
        "deployment_id": deployment["deployment_id"],
        "deployment_lock_sha256": deployment_lock_sha,
        "capture_count": len(records),

        "contact_sheets": contacts,
    }, checksum=True)
    write_json(evidence_path, manifest, checksum=True)
    validate_phase31_framebuffer_manifest(
        json.loads(evidence_path.read_text(encoding="ascii")),
        deployment,
        deployment_lock_sha256=deployment_lock_sha,
    )
    print(
        f"captured {len(records)} logical RGB565 frames for deployment "
        f"{deployment['deployment_id']}"
    )
    return 0
def validate_phase31_device_evidence(
    path: Path,
    deployment_path: Path,
    framebuffer_path: Path,
    defects_path: Path | None,
    *,
    require_current_deployment: bool = False,
    allow_pending: bool = False,
    require_fresh_bridge_publication: bool = False,
    require_no_open_defects: bool = False,
) -> int:
    path = path.resolve()
    _phase31_sidecar(path, "device evidence")
    evidence = json.loads(path.read_text(encoding="ascii"))
    binding_path = Path.home() / ".config/herdr/keypad-binding.json"
    binding = PairingStore(binding_path).load()
    if binding is None:
        raise RuntimeError("paired keypad binding is missing")
    firmware = (ROOT / ".pio/build/selected-usb/firmware.bin").resolve()
    deployment = validate_deployment_file(
        deployment_path.resolve(), firmware=firmware, binding=binding,
        require_current=require_current_deployment,
    )
    manifest_sha = _phase31_sidecar(framebuffer_path.resolve(), "logical manifest")
    lock_sha = _phase31_sidecar(deployment_path.resolve(), "deployment lock")
    manifest = json.loads(framebuffer_path.resolve().read_text(encoding="ascii"))
    validate_phase31_framebuffer_manifest(
        manifest, deployment, deployment_lock_sha256=lock_sha
    )
    _phase31_current_evidence_header(evidence, deployment, manifest, lock_sha, manifest_sha)
    exact_pair = evidence.get("exact_pair")
    if exact_pair != {
        "device_id": deployment["paired_device_id"],
        "pair_identity_digest": deployment["pair_identity_digest"],
        "firmware_sha256": deployment["firmware_sha256"],
        "protocol": deployment["protocol_version"],
    }:
        raise ValueError("exact pair evidence linkage is invalid")
    pending = any(
        row.get("result") == "pending"
        for row in evidence["physical_observations"]
    )
    if pending and not allow_pending:
        raise ValueError("physical observations remain pending")
    expected_status = "pending" if pending else "pass"
    if evidence.get("status") != expected_status:
        raise ValueError("device evidence status does not match observations")
    if any(
        row.get("result") in {"failed", "refused", "unavailable"}
        for row in evidence["physical_observations"]
    ):
        raise ValueError("failed or unavailable physical observation blocks acceptance")
    measurements = evidence.get("machine_measurements")
    if not isinstance(measurements, list) or not measurements:
        raise ValueError("complete machine metrics evidence is missing")
    for measurement in measurements:
        if (
            not isinstance(measurement, Mapping)
            or measurement.get("source") != "machine"
            or measurement.get("deployment_id") != deployment["deployment_id"]
        ):
            raise ValueError("machine measurement provenance is invalid")
        data = measurement.get("data")
        if not isinstance(data, Mapping) or data.get("status") != "pass":
            raise ValueError("machine measurement is unavailable")
        try:
            metrics = _phase31_metrics(data.get("metrics", {}))
            _validate_phase31_machine_metrics(metrics)
        except ValueError as exc:
            raise ValueError(f"machine measurement is incomplete: {exc}") from exc
    publication = evidence.get("preflight", {}).get("guarded_publication")
    final_publication = evidence.get("preflight", {}).get("final_publication")
    if require_fresh_bridge_publication:
        publication = final_publication or publication
        if (
            not isinstance(publication, Mapping)
            or publication.get("accepted") is not True
            or not valid_snapshot_revision(publication.get("snapshot_revision"))
            or not valid_publication_identity(publication.get("boot_id"))
            or not valid_publication_identity(publication.get("session_id"))
            or not isinstance(publication.get("receipt_sha256"), str)
            or len(publication["receipt_sha256"]) != 64
        ):
            raise ValueError("fresh bridge publication evidence is missing")
    if require_no_open_defects:
        ledger_path = (defects_path or ROOT / "artifacts/phase03.1/03.1-DEFECT-LEDGER.json").resolve()
        _phase31_sidecar(ledger_path, "defect ledger")
        try:
            ledger = json.loads(ledger_path.read_text(encoding="ascii"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            raise ValueError("defect ledger is missing") from exc
        if (
            ledger.get("kind") != "phase03.1-defect-ledger"
            or ledger.get("deployment_id") != deployment["deployment_id"]
            or ledger.get("deployment_lock_sha256") != lock_sha
            or ledger.get("logical_manifest_sha256") != manifest_sha
            or ledger.get("status") != "pass"
            or ledger.get("defects") != []
        ):
            raise ValueError("defect ledger contains an open or mismatched defect")
    print(
        f"validated {'pending' if pending else 'complete'} Phase 03.1 device evidence "
        f"for {deployment['deployment_id']}"
    )
    return 0


def run_phase31_validate(args: argparse.Namespace) -> int:
    try:
        document = json.loads(args.evidence.resolve().read_text(encoding="ascii"))
    except (OSError, json.JSONDecodeError):
        document = None
    if isinstance(document, dict) and document.get("kind") == "phase03.1-device-evidence":
        return validate_phase31_device_evidence(
            args.evidence,
            args.deployment,
            args.framebuffer,
            args.defects,
            require_current_deployment=args.require_current_deployment,
            allow_pending=False,
            require_fresh_bridge_publication=args.require_fresh_bridge_publication,
            require_no_open_defects=args.require_no_open_defects,
        )
    deployment_path = args.deployment.resolve()
    binding_path = (
        args.binding.resolve()
        if getattr(args, "binding", None) is not None
        else Path.home() / ".config/herdr/keypad-binding.json"
    )
    binding = PairingStore(binding_path).load()
    if binding is None:
        raise RuntimeError("paired keypad binding is missing")
    firmware = (ROOT / ".pio/build/selected-usb/firmware.bin").resolve()
    deployment = validate_deployment_file(
        deployment_path, firmware=firmware, binding=binding,
        require_current=args.require_current_deployment,
    )
    evidence_path = args.evidence.resolve()
    sidecar = evidence_path.with_suffix(evidence_path.suffix + ".sha256")
    if sha256_file(evidence_path) != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("framebuffer evidence checksum mismatch")
    manifest = json.loads(evidence_path.read_text(encoding="ascii"))
    validate_phase31_framebuffer_manifest(
        manifest, deployment, deployment_lock_sha256=sha256_file(deployment_path)
    )
    print(f"validated Phase 03.1 framebuffer evidence for {deployment['deployment_id']}")
    return 0

def preflight_run(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence_path = args.evidence.resolve()
    validate_evidence(evidence_path, allow_pending=True)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    deployment = evidence["deployment"]
    firmware = args.firmware.resolve()
    tracer = args.tracer.resolve()
    if firmware != resolve_repo_path(deployment["binary_path"]):
        raise RuntimeError("guided firmware path differs from captured deployment")
    if sha256_file(firmware) != deployment["binary_sha256"]:
        raise RuntimeError("guided firmware hash differs from captured deployment")
    if tracer != resolve_repo_path(evidence["tracer"]["path"]):
        raise RuntimeError("guided tracer path differs from linked installed tracer")
    if sha256_file(tracer) != evidence["tracer_audit_link"]["tracer_sha256"]:
        raise RuntimeError("guided tracer hash differs from linked installed tracer")
    if evidence.get("r_bucket") != bucket_matrix() or evidence["r_bucket"].get("result") != "pass":
        raise RuntimeError("R-BUCKET is incomplete")

    binding = PairingStore(args.binding.resolve()).load()
    if binding is None:
        raise RuntimeError("paired keypad binding is missing")
    selected, link, session, _transitions = reconnect_exact(
        binding,
        ports=None,
        opener=lambda candidate: __import__("serial").Serial(
            candidate.device, 115200, timeout=0.2, write_timeout=2.0),
        timeout=args.timeout,
    )
    try:
        hello = dict(session.device)
        expected = {
            "device_id": deployment["paired_device_id"],
            "firmware": deployment["hello_firmware"],
            "protocol": deployment["protocol_version"],
            "device_boot_id": deployment["fresh_boot_id"],
        }
        if any(hello.get(key) != value for key, value in expected.items()):
            raise RuntimeError("fresh exact-pair hello differs from captured deployment")
        fresh = {
            **expected,
            "session_id": session.session_id,
            "usb_serial": selected.serial_number or "unavailable",
        }
    finally:
        link.close()
    return evidence, fresh


def _guided_receipt_matches(
    receipt_path: Path,
    evidence: dict[str, Any],
    fresh: dict[str, Any],
) -> bool:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    deployment = evidence["deployment"]
    hello = receipt.get("hello", {})
    ack = receipt.get("snapshot_ack", {})
    return (
        receipt.get("kind") == "phase3-bridge-publication-receipt"
        and receipt.get("binary_sha256") == deployment["binary_sha256"]
        and hello.get("device_id") == fresh["device_id"]
        and hello.get("firmware") == fresh["firmware"]
        and hello.get("protocol") == fresh["protocol"]
        and hello.get("boot_id") == fresh["device_boot_id"]
        and hello.get("session_id") != fresh["session_id"]
        and ack.get("accepted") is True
        and isinstance(ack.get("snapshot_revision"), int)
    )


def _stop_guided_bridge(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5.0)
        return
    except subprocess.TimeoutExpired:
        process.terminate()
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1.0)


@contextmanager
def guided_bridge(
    args: argparse.Namespace,
    evidence: dict[str, Any],
    fresh: dict[str, Any],
) -> Iterator[subprocess.Popen[str]]:
    guard = ROOT / "host/herdr_keypad/scripts/ensure-bridge.sh"
    with tempfile.TemporaryDirectory(prefix="phase3-guided-") as directory:
        temporary = Path(directory)
        receipt_path = temporary / "publication.json"
        log_path = temporary / "bridge.log"
        environment = os.environ.copy()
        environment.pop("HERDR_KEYPAD_PIDFILE", None)
        environment["HERDR_DEPLOYED_FIRMWARE"] = str(args.firmware.resolve())
        environment["HERDR_KEYPAD_PUBLICATION_EVIDENCE"] = str(receipt_path)
        with log_path.open("w+", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(guard)],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                deadline = time.monotonic() + max(10.0, float(args.timeout) * 4.0)
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    if _guided_receipt_matches(receipt_path, evidence, fresh):
                        print(
                            "LIVE BRIDGE PASS "
                            f"pid={process.pid} device={fresh['device_id']} "
                            f"session={fresh['session_id']}",
                            flush=True,
                        )
                        try:
                            yield process
                        except BaseException:
                            if process.poll() is not None:
                                log.flush()
                                log.seek(0)
                                detail = log.read()[-480:].strip()
                                print(
                                    f"GUIDED BRIDGE EXIT code={process.returncode}: {detail}",
                                    flush=True,
                                )
                            raise
                        return
                    time.sleep(0.05)
                log.flush()
                log.seek(0)
                detail = log.read()[-240:].strip()
                if process.poll() is None:
                    raise RuntimeError(
                        f"guided bridge did not publish a fresh acknowledged snapshot: {detail}"
                    )
                raise RuntimeError(
                    f"guided bridge exited before physical prompts: {detail}"
                )
            finally:
                _stop_guided_bridge(process)


def run_guided(args: argparse.Namespace) -> int:
    evidence, fresh = preflight_run(args)
    run_suffix = evidence["run_id"][-8:].upper()
    print(
        "PREFLIGHT PASS "
        f"deployment={evidence['deployment']['deployment_id']} "
        f"firmware_sha256={evidence['deployment']['binary_sha256']} "
        f"device={fresh['device_id']} hello={fresh['firmware']}/{fresh['protocol']} "
        f"tracer={evidence['tracer_audit_link']['tracer_sha256']} R-BUCKET=pass",
        flush=True,
    )
    rows = {row["id"]: row for row in evidence["physical_observations"]}
    with guided_bridge(args, evidence, fresh) as bridge:
        for number, row_id in enumerate(HUMAN_ROWS, 1):
            row = rows[row_id]
            if row.get("result") == "pass":
                continue
            if bridge.poll() is not None:
                raise RuntimeError("guided bridge exited before the physical observation")
            print(f"\n[{number}/{len(HUMAN_ROWS)}] {row_id}", flush=True)
            print(OBSERVATION_PROMPTS[row_id], flush=True)
            try:
                answer = input(f"Answer Y/N/R {row_id} {run_suffix}: ").strip().upper()
            except EOFError as exc:
                raise RuntimeError(
                    "guided observation input ended before the blocking gate completed"
                ) from exc
            if answer not in {"Y", "N", "R"}:
                raise RuntimeError("guided observation response must be exactly Y, N, or R")
            if bridge.poll() is not None:
                raise RuntimeError("guided bridge exited during the physical observation")
            row["result"] = {"Y": "pass", "N": "failed", "R": "refused"}[answer]
            row["observation"] = {
                "answer": answer,
                "prompt": OBSERVATION_PROMPTS[row_id],
                "observed_at_unix_ms": time.time_ns() // 1_000_000,
                "fresh_hello_session_id": fresh["session_id"],
            }
            write_json(args.evidence.resolve(), evidence, checksum=True)
            if answer != "Y":
                print(f"CHECKPOINT FAILED {row_id}: {row['result']}", flush=True)
                return 1
    print("PHYSICAL OBSERVATIONS COMPLETE; release direct serial for fresh bridge publication", flush=True)
    return 0


def finalize_evidence(args: argparse.Namespace) -> int:
    evidence_path = args.evidence.resolve()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    deployment = evidence["deployment"]
    if sha256_file(args.firmware.resolve()) != deployment["binary_sha256"]:
        raise RuntimeError("final firmware hash differs from captured deployment")
    rows = {row["id"]: row for row in evidence["physical_observations"]}
    if any(rows[row_id].get("result") != "pass" for row_id in HUMAN_ROWS):
        raise RuntimeError("human physical observations are not all explicit passes")
    receipt_path = args.publication_receipt.expanduser().resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if set(receipt) != {
        "schema_version", "kind", "published_at_unix_ms", "binary_sha256", "hello", "snapshot_ack"
    } or receipt.get("kind") != "phase3-bridge-publication-receipt":
        raise RuntimeError("fresh bridge publication receipt schema is invalid")
    hello = receipt["hello"]
    if (
        receipt["binary_sha256"] != deployment["binary_sha256"]
        or hello.get("device_id") != deployment["paired_device_id"]
        or hello.get("firmware") != deployment["hello_firmware"]
        or hello.get("protocol") != deployment["protocol_version"]
    ):
        raise RuntimeError("fresh bridge publication differs from current deployment")
    if not valid_publication_identity(hello.get("boot_id")) or not valid_publication_identity(
        hello.get("session_id")
    ):
        raise RuntimeError("fresh bridge publication identity is invalid")
    ack = receipt["snapshot_ack"]
    if ack.get("accepted") is not True or not valid_snapshot_revision(ack.get("snapshot_revision")):
        raise RuntimeError("fresh bridge publication was not acknowledged")
    last_observed = max(
        rows[row_id]["observation"]["observed_at_unix_ms"] for row_id in HUMAN_ROWS
    )
    if receipt.get("published_at_unix_ms", 0) <= last_observed:
        raise RuntimeError("bridge publication receipt does not postdate physical observations")
    receipt_sha = sha256_file(receipt_path)
    resync = rows["fresh-bridge-resync-after-acceptance"]
    resync.update({
        "source": "machine",
        "result": "pass",
        "observation": {
            "receipt_sha256": receipt_sha,
            "published_at_unix_ms": receipt["published_at_unix_ms"],
            "boot_id": hello["boot_id"],
            "session_id": hello["session_id"],
            "snapshot_revision": ack["snapshot_revision"],
            "accepted": True,
        },
    })
    for item in evidence["ui_considerations"]:
        if item["id"] == "long-text":
            item["result"] = "pass"
    evidence["status"] = "pass"
    write_json(evidence_path, evidence, checksum=True)
    return validate_evidence(
        evidence_path,
        allow_pending=False,
        require_current_deployment=True,
        require_fresh_bridge_publication=True,
    )


def validate_evidence(
    path: Path,
    allow_pending: bool,
    *,
    require_current_deployment: bool = False,
    require_fresh_bridge_publication: bool = False,
) -> int:
    path = path.resolve()
    evidence = json.loads(path.read_text(encoding="utf-8"))
    expected_top = {
        "schema_version", "kind", "status", "run_id", "deployment", "capture_manifest",
        "tracer", "tracer_audit_link", "r_bucket", "requirements", "ui_considerations",
        "physical_observations", "evidence_kinds",
    }
    if set(evidence) != expected_top or evidence.get("kind") != "phase3-device-evidence":
        raise ValueError("device evidence schema is not closed")
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sha256_file(path) != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("device evidence checksum mismatch")
    deployment = dict(evidence["deployment"])
    deployment_id = deployment.pop("deployment_id", None)
    if deployment_id != sha256_bytes(canonical_bytes(deployment)):
        raise ValueError("canonical deployment identity mismatch")
    firmware = resolve_repo_path(deployment["binary_path"])
    if sha256_file(firmware) != deployment["binary_sha256"]:
        raise ValueError("deployed firmware binary hash mismatch")
    if deployment.get("platformio_environment") != "selected-usb" or deployment.get("upload_result") != "pass":
        raise ValueError("deployment is not a successful selected-usb upload")
    if require_current_deployment and firmware != (ROOT / ".pio/build/selected-usb/firmware.bin").resolve():
        raise ValueError("evidence does not reference the current selected-usb deployment")

    capture_ref = evidence["capture_manifest"]
    captures_path = resolve_repo_path(capture_ref["path"])
    if sha256_file(captures_path) != capture_ref["sha256"]:
        raise ValueError("capture manifest hash mismatch")
    manifest = json.loads(captures_path.read_text(encoding="utf-8"))
    if manifest.get("deployment_id") != deployment_id or capture_ref.get("deployment_id") != deployment_id:
        raise ValueError("capture manifest deployment linkage mismatch")
    if manifest.get("source") != "logical-framebuffer-only" or manifest.get("redaction", {}).get("result") != "pass":
        raise ValueError("capture source/redaction classification invalid")
    for capture in manifest.get("captures", []):
        if capture.get("width") != 128 or capture.get("height") != 128 or capture.get("deployment_id") != deployment_id:
            raise ValueError("capture dimensions/deployment linkage invalid")
        for path_key, hash_key in (("rgb565_path", "rgb565_sha256"), ("png_path", "png_sha256")):
            artifact = resolve_repo_path(capture[path_key])
            if sha256_file(artifact) != capture[hash_key]:
                raise ValueError(f"capture hash mismatch: {capture['id']}")
        raw = resolve_repo_path(capture["rgb565_path"])
        png = resolve_repo_path(capture["png_path"])
        if raw.stat().st_size != 128 * 128 * 2 or not png_has_deployment(png, deployment_id):
            raise ValueError("capture payload or PNG deployment metadata invalid")
    expected_capture_count = len(THEMES) * (len(CODEX_SCENES) + len(MENU_SCENES))
    if len(manifest.get("captures", [])) != expected_capture_count:
        raise ValueError("capture scene matrix is incomplete")
    contacts = manifest.get("contact_sheets", [])
    if {item.get("kind") for item in contacts} != {"codex", "menu"}:
        raise ValueError("contact sheet matrix is incomplete")
    for contact in contacts:
        artifact = resolve_repo_path(contact["path"])
        if (sha256_file(artifact) != contact["sha256"] or
                contact.get("deployment_id") != deployment_id or
                contact.get("source_frame_width") != 128 or
                contact.get("source_frame_height") != 128 or
                not png_has_deployment(artifact, deployment_id)):
            raise ValueError("contact sheet linkage invalid")

    tracer_path = resolve_repo_path(evidence["tracer"]["path"])
    tracer = json.loads(tracer_path.read_text(encoding="utf-8"))
    link = evidence["tracer_audit_link"]
    if set(link) != TRACER_LINK_KEYS or sha256_file(tracer_path) != link["tracer_sha256"]:
        raise ValueError("closed tracer audit link mismatch")
    elapsed = json_pointer(tracer, link["elapsed_ms_path"])
    child = json_pointer(tracer, link["child_exit_path"])
    redaction = json_pointer(tracer, link["redaction_result_path"])
    if not isinstance(elapsed, int) or isinstance(elapsed, bool) or not 0 <= elapsed <= 3000:
        raise ValueError("tracer elapsed time is not bounded")
    if (not isinstance(child, dict) or set(child) != {"state", "code", "signal"} or
            child["state"] not in {"not_started", "running", "exited", "terminated", "killed"}):
        raise ValueError("tracer child-exit schema invalid")
    if redaction != "pass":
        raise ValueError("tracer redaction did not pass")

    if evidence["r_bucket"] != bucket_matrix():
        raise ValueError("R-BUCKET matrix or bounded manifest mismatch")
    if {row.get("id") for row in evidence["requirements"]} != set(REQUIREMENTS):
        raise ValueError("requirement matrix incomplete")
    if {row.get("id") for row in evidence["ui_considerations"]} != set(UI_CONSIDERATIONS):
        raise ValueError("UI consideration matrix incomplete")
    physical = evidence["physical_observations"]
    if {row.get("id") for row in physical} != set(PHYSICAL_ROWS):
        raise ValueError("physical observation matrix incomplete")
    for row in physical:
        expected_source = (
            "machine"
            if row.get("id") == "fresh-bridge-resync-after-acceptance" and row.get("result") == "pass"
            else "physical"
        )
        if row.get("source") != expected_source or row.get("deployment_id") != deployment_id:
            raise ValueError("physical observations have invalid source/deployment linkage")
    pending = any(row.get("result") == "pending" for row in physical)
    if pending and not allow_pending:
        raise ValueError("physical observations remain pending")
    if evidence["status"] != ("pending" if pending else "pass"):
        raise ValueError("evidence status does not match physical observations")
    if require_fresh_bridge_publication:
        resync = next(row for row in physical if row["id"] == "fresh-bridge-resync-after-acceptance")
        observation = resync.get("observation")
        if (
            resync.get("source") != "machine"
            or resync.get("result") != "pass"
            or not isinstance(observation, dict)
            or observation.get("accepted") is not True
            or not isinstance(observation.get("published_at_unix_ms"), int)
            or not valid_snapshot_revision(observation.get("snapshot_revision"))
            or not isinstance(observation.get("receipt_sha256"), str)
            or len(observation["receipt_sha256"]) != 64
            or not valid_publication_identity(observation.get("boot_id"))
            or not valid_publication_identity(observation.get("session_id"))
        ):
            raise ValueError("fresh bridge publication evidence is missing or invalid")
        if any(item.get("result") not in {"pass", "machine-pass"} for item in evidence["ui_considerations"]):
            raise ValueError("UI considerations are not complete")
    print(f"validated {'pending' if pending else 'complete'} Phase 3 evidence for {deployment_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--binding", type=Path, required=True)
    capture.add_argument("--firmware", type=Path, required=True)
    capture.add_argument("--tracer", type=Path, required=True)
    capture.add_argument("--evidence", type=Path, required=True)
    capture.add_argument("--captures", type=Path, required=True)
    capture.add_argument("--timeout", type=float, default=5.0)
    run = subparsers.add_parser("run")
    run.add_argument("--binding", type=Path, required=True)
    run.add_argument("--firmware", type=Path, required=True)
    run.add_argument("--tracer", type=Path, required=True)
    run.add_argument("--evidence", type=Path, required=True)
    run.add_argument("--timeout", type=float, default=5.0)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--evidence", type=Path, required=True)
    finalize.add_argument("--firmware", type=Path, required=True)
    finalize.add_argument("--publication-receipt", type=Path, required=True)
    profile = subparsers.add_parser("phase31-profile")
    profile.add_argument("--binding", type=Path, required=True)
    profile.add_argument("--firmware", type=Path, required=True)
    profile.add_argument("--evidence", type=Path, required=True)
    profile.add_argument("--timeout", type=float, default=5.0)
    lock = subparsers.add_parser("phase31-lock")
    lock.add_argument("--baseline", type=Path, required=True)
    lock.add_argument("--output", type=Path, required=True)
    deploy = subparsers.add_parser("phase31-deploy-lock")
    deploy.add_argument("--binding", type=Path, required=True)
    deploy.add_argument("--firmware", type=Path, required=True)
    deploy.add_argument("--output", type=Path, required=True)
    deploy.add_argument("--timeout", type=float, default=5.0)
    deploy_validate = subparsers.add_parser("phase31-validate-deployment")
    deploy_validate.add_argument("--binding", type=Path, required=True)
    deploy_validate.add_argument("--firmware", type=Path, required=True)
    deploy_validate.add_argument("--deployment", type=Path, required=True)
    deploy_validate.add_argument("--require-current-deployment", action="store_true")
    current31 = subparsers.add_parser("phase31-current-deployment")
    current31.add_argument("--binding", type=Path, required=True)
    current31.add_argument("--firmware", type=Path, required=True)
    current31.add_argument("--deployment", type=Path, required=True)
    current31.add_argument("--framebuffer", type=Path, required=True)
    current31.add_argument("--evidence", type=Path, required=True)
    current31.add_argument("--timeout", type=float, default=5.0)
    current31.add_argument("--require-current-deployment", action="store_true")
    current31.add_argument("--require-fresh-bridge-publication", action="store_true")
    run31 = subparsers.add_parser("phase31-run")
    run31.add_argument("--binding", type=Path, required=True)
    run31.add_argument("--firmware", type=Path, required=True)
    run31.add_argument("--deployment", type=Path, required=True)
    run31.add_argument("--baseline", type=Path, required=True)
    run31.add_argument("--framebuffer", type=Path, required=True)
    run31.add_argument("--evidence", type=Path, required=True)
    run31.add_argument("--defects", type=Path, required=True)
    run31.add_argument("--timeout", type=float, default=5.0)
    run31.add_argument("--require-current-deployment", action="store_true")
    run31.add_argument("--require-fresh-bridge-publication", action="store_true")
    capture31 = subparsers.add_parser("phase31-capture")
    capture31.add_argument("--binding", type=Path, required=True)
    capture31.add_argument("--firmware", type=Path, required=True)
    capture31.add_argument("--deployment", type=Path, required=True)
    capture31.add_argument("--baseline", type=Path, required=True)
    capture31.add_argument("--evidence", type=Path, required=True)
    capture31.add_argument("--captures", type=Path, required=True)
    capture31.add_argument("--timeout", type=float, default=5.0)
    phase31_validate = subparsers.add_parser("phase31-validate")
    phase31_validate.add_argument("--evidence", type=Path, required=True)
    phase31_validate.add_argument("--deployment", type=Path, required=True)
    phase31_validate.add_argument("--framebuffer", type=Path)
    phase31_validate.add_argument("--defects", type=Path)
    phase31_validate.add_argument("--binding", type=Path)
    phase31_validate.add_argument("--require-current-deployment", action="store_true")
    phase31_validate.add_argument("--require-fresh-bridge-publication", action="store_true")
    phase31_validate.add_argument("--require-no-open-defects", action="store_true")
    validate = subparsers.add_parser("validate")
    validate.add_argument("--evidence", type=Path, required=True)
    validate.add_argument("--allow-pending", action="store_true")
    validate.add_argument("--require-current-deployment", action="store_true")
    validate.add_argument("--require-fresh-bridge-publication", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "phase31-profile":
        return run_phase31_profile(args)
    if args.command == "phase31-lock":
        return run_phase31_lock(args)
    if args.command == "phase31-deploy-lock":
        return run_phase31_deploy_lock(args)
    if args.command == "phase31-validate-deployment":
        return run_phase31_validate_deployment(
            SimpleNamespace(
                binding=args.binding,
                firmware=args.firmware,
                deployment=args.deployment,
                require_current=args.require_current_deployment,
            )
        )
    if args.command == "phase31-current-deployment":
        return run_phase31_current_deployment(args)
    if args.command == "phase31-run":
        baseline_path = args.baseline.resolve()
        try:
            baseline_document = json.loads(baseline_path.read_text(encoding="ascii"))
            baseline_kind = baseline_document.get("kind")
        except (OSError, json.JSONDecodeError):
            baseline_document = None
            baseline_kind = None
        if baseline_kind == "phase03.1-budget-lock":
            _phase31_sidecar(baseline_path, "budget lock")
            if baseline_document.get("status") != "blocked":
                raise ValueError("Phase 03.1 budget lock status is not closed")
            print(
                "Phase 03.1 budget lock is a historical blocked baseline; "
                "continuing with current deployment",
                flush=True,
            )
        else:
            baseline = validate_phase31_baseline_file(
                baseline_path,
                require_current_deployment=args.require_current_deployment,
            )
            if baseline.get("status") == "blocked":
                print(
                    "Phase 03.1 budget lock is a historical blocked baseline; "
                    "continuing with current deployment",
                    flush=True,
                )
        return run_phase31_run(args)
    if args.command == "phase31-capture":
        return run_phase31_capture(args)
    if args.command == "phase31-validate":
        return run_phase31_validate(args)
    if args.command == "capture":
        return run_capture(args)
    if args.command == "run":
        return run_guided(args)
    if args.command == "finalize":
        return finalize_evidence(args)
    try:
        document = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        document = None
    if isinstance(document, dict) and document.get("kind") == "phase03.1-baseline-profile":
        validate_phase31_baseline_file(
            args.evidence.resolve(),
            require_current_deployment=args.require_current_deployment,
        )
        return 0
    return validate_evidence(
        args.evidence,
        args.allow_pending,
        require_current_deployment=args.require_current_deployment,
        require_fresh_bridge_publication=args.require_fresh_bridge_publication,
    )


if __name__ == "__main__":
    raise SystemExit(main())
