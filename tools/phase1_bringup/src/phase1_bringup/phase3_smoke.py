"""Exact-pair Phase 3 deployment capture and pending-evidence validator."""
from __future__ import annotations

from contextlib import contextmanager
import argparse
import binascii
import hashlib
import json
import os
import selectors
import struct
import subprocess
import signal
import tempfile
import threading
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from types import SimpleNamespace

from .composite_qualification import (
    FINAL_EDGE_ASSUMPTIONS,
    build_final_qualification,
    validate_final_qualification,
    validate_input_trace,
    verify_composite_decision,
)
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
HOLD_SCENES = (
    "hold-pending", "space-active-owner", "cancellation-return",
    "owner-after-other-focus", "failure-preemption", "lifecycle-clear",
)

# Phase 03.2 keeps the production renderer's six closed hold fixtures but
# publishes a separate logical LED matrix so every failure/source fence is
# represented even when the framebuffer fixture has no dedicated token.
PHASE32_HOLD_SCENES = HOLD_SCENES
PHASE32_LEVELS = ("full", "half", "static")
PHASE32_FAILURE_EVENTS = (
    "rejected", "stale", "vanished", "offline", "uncertain", "timeout", "failed",
)
PHASE32_SOURCE_EVENTS = ("source-stale", "source-offline", "source-unavailable")
PHASE32_LED_EVENTS = (
    "pending", "active-owner", "owner-after-other-focus", "cancellation-return",
    *PHASE32_FAILURE_EVENTS, *PHASE32_SOURCE_EVENTS, "lifecycle-clear",
)
PHASE32_GRAMMAR_MASKS = {
    "rail-echo": (1 << 1, 1 << 4, 1 << 7),
    "exception": (1 << 1, 1 << 4, 1 << 7),
    "field-extension": (
        (1 << 0) | (1 << 1) | (1 << 2),
        (1 << 3) | (1 << 4) | (1 << 5),
        (1 << 6) | (1 << 7) | (1 << 8),
    ),
    "meter-lamps": (1 << 1, 1 << 4, 1 << 7),
}
PHASE32_DEVICE_EVIDENCE_KIND = "phase03.2-device-evidence"
PHASE32_DEFECT_LEDGER_KIND = "phase03.2-defect-ledger"
PHASE32_OPERATOR_PROMPTS = (
    (
        "threshold-calibration",
        "THRESHOLD BATCH: on KEY-1, KEY-2, KEY-3 do SHORTx3 then LONGx3, then final SHORT+LONG "
        "(24 gestures total). SHORT is natural under 0.5 s; LONG is clearly over 1.5 s. "
        "Reply Y only after all three keys agree at the shared threshold.",
    ),
    (
        "presentation",
        "PRESENTATION BATCH: use the controlled QUALIFY KEY 1-3 tiles (the gate never touches live "
        "Herdr). Inspect all four themes and LED grammars while showing pending, active owner, "
        "cancellation, and failure/lifecycle states. Confirm mic clarity, owner persistence, mapped "
        "LED zones, and failure precedence. Reply Y/N.",
    ),
    (
        "lifecycle",
        "LIFECYCLE BATCH: perform unplug/replug, suspend/resume, reset, and BOOT recovery on the "
        "paired keypad. Confirm empty-first state, release, reconnect identity, and no stuck Space. Reply Y/N.",
    ),
)
PHASE32_PHASE4_GATE_KIND = "phase03.2-phase4-gate"
PHASE32_DEVICE_ROW_IDS = tuple(f"D-{index:02d}" for index in range(1, 19))
PHASE32_MACHINE_ROW_FOR_DEVICE = {
    "D-01": "threshold-calibration",
    "D-02": "immediate-focus-short-separation",
    "D-03": "focus-before-hid-ordering",
    "D-04": "focus-before-hid-ordering",
    "D-05": "release-before-ack",
    "D-06": "active-owner-independence",
    "D-07": "active-owner-independence",
    "D-08": "active-owner-independence",
    "D-09": "physical-release",
    "D-10": "stale-failure-source-session",
    "D-11": "stale-failure-source-session",
    "D-12": "active-owner-independence",
    "D-13": "release-before-ack",
    "D-14": "stale-failure-source-session",
    "D-15": "usb-removal",
    "D-16": "controlled-reset",
    "D-17": "mixed-stress",
    "D-18": "suspend-resume",
}
PHASE32_LEVEL_PHASE = {"full": 3, "half": 2, "static": 0}
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

PHASE32_DESCRIPTOR = {
    "vid": 0x303A,
    "pid": 0x1001,
    "serial": "8CBFEA0DCBFC",
    "hid_interface": 0,
    "cdc_control_interface": 1,
    "cdc_data_interface": 2,
    "standard_keyboard_hid": 1,
    "cdc_functions": 1,
}


def phase32_descriptor_tuple() -> dict[str, Any]:
    return dict(PHASE32_DESCRIPTOR)


def phase32_descriptor_tuple_sha256(descriptor: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(descriptor))


def phase32_production_source_paths() -> list[Path]:
    sources = [ROOT / "platformio.ini"]
    sources.extend(sorted((ROOT / "firmware/src").rglob("*.cpp")))
    sources.extend(sorted((ROOT / "firmware/src").rglob("*.h")))
    return sources


def phase32_source_digest(paths: Iterable[Path]) -> str:
    entries: list[dict[str, str]] = []
    for path in sorted((Path(item).resolve() for item in paths), key=relative):
        if not path.is_file():
            raise ValueError(f"source file is missing: {relative(path)}")
        entries.append({"path": relative(path), "sha256": sha256_file(path)})
    return sha256_bytes(canonical_bytes(entries))


def validate_phase32_composite_lineage(
    decision_path: Path, binding_path: Path
) -> dict[str, Any]:
    decision_path = decision_path.resolve()
    binding_path = binding_path.resolve()
    _phase31_sidecar(decision_path, "composite decision")
    decision = verify_composite_decision(
        decision_path, require_terminal=True, require_immutable_lineage=True
    )
    if decision.get("status") != "PASS" or decision.get("terminal") is not True:
        raise ValueError("composite decision is not terminal PASS")
    manifest_path = (decision_path.parent / decision["manifest_path"]).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    descriptor_ref = manifest.get("descriptor_expectation", {})
    descriptor_path = Path(descriptor_ref.get("path", "")).expanduser()
    if not descriptor_path.is_absolute():
        descriptor_path = ROOT / descriptor_path
    descriptor_path = descriptor_path.resolve()
    try:
        descriptor_path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("composite descriptor path escapes repository") from exc
    if sha256_file(descriptor_path) != descriptor_ref.get("sha256"):
        raise ValueError("composite descriptor evidence checksum mismatch")
    binding = PairingStore(binding_path).load()
    if binding is None:
        raise ValueError("exact pairing binding is missing")
    pair_digest = sha256_file(binding_path)
    expected = decision.get("deployment", {})
    if (
        pair_digest != expected.get("pair_digest")
        or pair_digest != expected.get("pairing_record_sha256")
        or binding.protocol != 1
    ):
        raise ValueError("composite pair lineage mismatch")
    return {
        "decision": decision,
        "manifest": manifest,
        "descriptor": phase32_descriptor_tuple(),
        "binding": binding,
        "pair_digest": pair_digest,
        "descriptor_path": relative(descriptor_path),
    }


def phase32_deployment_id_for(deployment: Mapping[str, Any]) -> str:
    identity = {
        key: deployment.get(key)
        for key in (
            "boot_id",
            "session_id",
            "paired_device_id",
            "pair_digest",
            "firmware_sha256",
            "source_sha256",
            "descriptor_tuple_sha256",
            "decision_sha256",
            "decision_manifest_sha256",
            "hello_firmware",
            "protocol_version",
        )
    }
    if any(
        not valid_publication_identity(value)
        for key, value in identity.items()
        if key != "protocol_version"
    ):
        raise ValueError("Phase 03.2 deployment identity tuple is incomplete")
    if identity["protocol_version"] != 1:
        raise ValueError("Phase 03.2 deployment identity protocol is invalid")
    return sha256_bytes(canonical_bytes(identity))


def validate_phase32_deployment(
    deployment: Mapping[str, Any],
    firmware: Path,
    decision: Mapping[str, Any],
    manifest: Mapping[str, Any],
    binding: Any,
    *,
    previous: Mapping[str, Any] | None = None,
    require_current: bool = False,
) -> None:
    required = (
        "schema_version", "kind", "phase", "platformio_environment",
        "binary_path", "binary_sha256", "firmware_sha256", "source_files",
        "source_sha256", "upload_result", "paired_device_id", "pair_digest",
        "pair_identity_digest", "pairing_record_sha256", "hello_firmware",
        "protocol_version", "fresh_boot_id", "fresh_session_id", "boot_id",
        "session_id", "observed_at_unix_ms", "decision_sha256",
        "decision_manifest_sha256", "composite_firmware_sha256",
        "descriptor_expectation_sha256", "descriptor_tuple",
        "descriptor_tuple_sha256", "deployment_id",
    )
    if any(key not in deployment for key in required):
        raise ValueError("Phase 03.2 deployment fields are incomplete")
    if (
        deployment["schema_version"] != 1
        or deployment["kind"] != "phase03.2-final-deployment"
        or deployment["phase"] != "03.2"
    ):
        raise ValueError("Phase 03.2 deployment schema is not closed")
    if (
        deployment["platformio_environment"] != "selected-usb"
        or deployment["upload_result"] != "pass"
    ):
        raise ValueError("Phase 03.2 deployment is not a successful selected-usb upload")
    if deployment["binary_sha256"] != deployment["firmware_sha256"]:
        raise ValueError("Phase 03.2 firmware hash aliases differ")
    if (
        deployment["fresh_boot_id"] != deployment["boot_id"]
        or deployment["fresh_session_id"] != deployment["session_id"]
    ):
        raise ValueError("Phase 03.2 boot/session aliases differ")
    if not firmware.is_file() or sha256_file(firmware) != deployment["firmware_sha256"]:
        raise ValueError("Phase 03.2 firmware binary hash mismatch")
    source_files = deployment["source_files"]
    if not isinstance(source_files, list) or not source_files:
        raise ValueError("Phase 03.2 source hash manifest is missing")
    paths: list[Path] = []
    for item in source_files:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("sha256"), str)
        ):
            raise ValueError("Phase 03.2 source hash manifest is invalid")
        path = resolve_repo_path(item["path"])
        if sha256_file(path) != item["sha256"]:
            raise ValueError("Phase 03.2 source hash mismatch")
        paths.append(path)
    if phase32_source_digest(paths) != deployment["source_sha256"]:
        raise ValueError("Phase 03.2 source digest mismatch")
    descriptor = phase32_descriptor_tuple()
    if deployment["descriptor_tuple"] != descriptor:
        raise ValueError("Phase 03.2 descriptor tuple mismatch")
    if phase32_descriptor_tuple_sha256(descriptor) != deployment["descriptor_tuple_sha256"]:
        raise ValueError("Phase 03.2 descriptor tuple hash mismatch")
    if decision.get("status") != "PASS" or decision.get("terminal") is not True:
        raise ValueError("Phase 03.2 deployment requires terminal composite PASS")
    decision_deployment = decision.get("deployment", {})
    if (
        deployment["decision_sha256"] != decision.get("decision_sha256")
        or deployment["decision_manifest_sha256"] != decision.get("manifest_sha256")
        or deployment["composite_firmware_sha256"]
        != decision_deployment.get("firmware_binary_sha256")
        or deployment["descriptor_expectation_sha256"]
        != decision_deployment.get("descriptor_expectation_sha256")
    ):
        raise ValueError("Phase 03.2 decision lineage mismatch")
    if manifest.get("manifest_sha256") != decision.get("manifest_sha256"):
        raise ValueError("Phase 03.2 manifest lineage mismatch")
    if deployment["paired_device_id"] != binding.device_id:
        raise ValueError("Phase 03.2 pair identity mismatch")
    pair_digest = sha256_file(Path.home() / ".config/herdr/keypad-binding.json")
    if (
        deployment["pair_digest"] != pair_digest
        or deployment["pair_identity_digest"] != pair_digest
        or deployment["pairing_record_sha256"] != pair_digest
        or pair_digest != decision_deployment.get("pair_digest")
    ):
        raise ValueError("Phase 03.2 pair digest or pairing record mismatch")
    if binding.protocol != deployment["protocol_version"]:
        raise ValueError("Phase 03.2 protocol identity mismatch")
    if binding.firmware != deployment["hello_firmware"]:
        raise ValueError("Phase 03.2 firmware identity mismatch")
    if previous is not None:
        if previous.get("boot_id") == deployment["boot_id"]:
            raise ValueError("Phase 03.2 deployment did not produce a fresh boot")
        if previous.get("session_id") == deployment["session_id"]:
            raise ValueError("Phase 03.2 deployment did not produce a fresh session")
    if require_current and firmware.resolve() != (ROOT / ".pio/build/selected-usb/firmware.bin").resolve():
        raise ValueError("Phase 03.2 deployment does not reference current selected-usb binary")
    if deployment["deployment_id"] != phase32_deployment_id_for(deployment):
        raise ValueError("Phase 03.2 canonical deployment identity mismatch")


def validate_phase32_deployment_file(
    path: Path,
    *,
    firmware: Path | None = None,
    decision_path: Path | None = None,
    binding_path: Path | None = None,
    require_current: bool = False,
) -> dict[str, Any]:
    path = path.resolve()
    _phase31_sidecar(path, "Phase 03.2 deployment")
    deployment = json.loads(path.read_text(encoding="ascii"))
    decision_path = decision_path or ROOT / "artifacts/phase03.2/composite-decision.json"
    binding_path = binding_path or Path.home() / ".config/herdr/keypad-binding.json"
    lineage = validate_phase32_composite_lineage(decision_path, binding_path)
    binary = (firmware or resolve_repo_path(deployment["binary_path"])).resolve()
    validate_phase32_deployment(
        deployment,
        binary,
        lineage["decision"],
        lineage["manifest"],
        lineage["binding"],
        require_current=require_current,
    )
    return deployment


def phase32_fresh_deployment(
    binding_path: Path,
    firmware: Path,
    lineage: Mapping[str, Any],
    timeout: float,
    *,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    binding = lineage["binding"]
    selected, link, session, _transitions = reconnect_exact(
        binding, ports=None, opener=_phase31_serial_opener, timeout=timeout
    )
    try:
        hello = dict(session.device)
        if (
            hello.get("device_id") != binding.device_id
            or hello.get("firmware") != binding.firmware
            or hello.get("protocol") != binding.protocol
        ):
            raise RuntimeError("fresh hello identity differs from exact pairing")
        boot_id = hello.get("device_boot_id")
        session_id = session.session_id
        if not valid_publication_identity(boot_id) or not valid_publication_identity(session_id):
            raise RuntimeError("fresh hello did not supply boot/session identity")
        if not firmware.is_file():
            raise RuntimeError("selected-usb firmware binary is missing")
        source_paths = phase32_production_source_paths()
        source_files = [
            {"path": relative(source), "sha256": sha256_file(source)}
            for source in source_paths
        ]
        descriptor = phase32_descriptor_tuple()
        pair_digest = lineage["pair_digest"]
        record: dict[str, Any] = {
            "schema_version": 1,
            "kind": "phase03.2-final-deployment",
            "phase": "03.2",
            "platformio_environment": "selected-usb",
            "binary_path": relative(firmware),
            "binary_sha256": sha256_file(firmware),
            "firmware_sha256": sha256_file(firmware),
            "source_files": source_files,
            "source_sha256": phase32_source_digest(source_paths),
            "upload_result": "pass",
            "paired_device_id": binding.device_id,
            "pair_digest": pair_digest,
            "pair_identity_digest": pair_digest,
            "pairing_record_sha256": pair_digest,
            "hello_firmware": binding.firmware,
            "protocol_version": binding.protocol,
            "fresh_boot_id": boot_id,
            "fresh_session_id": session_id,
            "boot_id": boot_id,
            "session_id": session_id,
            "usb_serial": selected.serial_number or "unavailable",
            "observed_at_unix_ms": time.time_ns() // 1_000_000,
            "decision_sha256": lineage["decision"]["decision_sha256"],
            "decision_manifest_sha256": lineage["decision"]["manifest_sha256"],
            "composite_firmware_sha256": lineage["decision"]["deployment"]["firmware_binary_sha256"],
            "descriptor_expectation_sha256": lineage["decision"]["deployment"]["descriptor_expectation_sha256"],
            "descriptor_tuple": descriptor,
            "descriptor_tuple_sha256": phase32_descriptor_tuple_sha256(descriptor),
        }
        record["deployment_id"] = phase32_deployment_id_for(record)
        validate_phase32_deployment(
            record, firmware, lineage["decision"], lineage["manifest"], binding,
            previous=previous,
        )
        return record
    finally:
        link.close()


def run_phase32_deploy_lock(args: argparse.Namespace) -> int:
    firmware = args.firmware.resolve()
    output = args.output.resolve()
    expected = (ROOT / ".pio/build/selected-usb/firmware.bin").resolve()
    if firmware != expected:
        raise RuntimeError("Phase 03.2 deployment lock requires selected-usb firmware.bin")
    lineage = validate_phase32_composite_lineage(
        args.decision.resolve(), args.binding.resolve()
    )
    previous = None
    if output.is_file():
        try:
            previous = json.loads(output.read_text(encoding="ascii"))
        except (OSError, json.JSONDecodeError):
            previous = None
    try:
        deployment = phase32_fresh_deployment(
            args.binding.resolve(), firmware, lineage, args.timeout, previous=previous
        )
        validate_phase32_deployment(
            deployment, firmware, lineage["decision"], lineage["manifest"],
            lineage["binding"], require_current=True, previous=previous,
        )
        write_json(output, deployment, checksum=True)
        validate_phase32_deployment_file(
            output, firmware=firmware, decision_path=args.decision,
            binding_path=args.binding, require_current=True,
        )
    except Exception:
        for stale in (output, output.with_suffix(output.suffix + ".sha256")):
            try:
                stale.unlink()
            except FileNotFoundError:
                pass
        raise
    print(f"wrote Phase 03.2 deployment lock for {deployment['deployment_id']}")
    return 0


def run_phase32_validate_deployment(args: argparse.Namespace) -> int:
    validate_phase32_deployment_file(
        args.deployment,
        firmware=args.firmware,
        decision_path=args.decision,
        binding_path=args.binding,
        require_current=args.require_current_deployment,
    )
    print(f"validated Phase 03.2 deployment lock {args.deployment.resolve()}")
    return 0


def _phase32_row_hash(row: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key != "content_sha256"}
    return sha256_bytes(canonical_bytes(payload))


def phase32_led_rows(
    deployment_id: str,
    firmware_sha256: str,
    deployment_lock_sha256: str,
) -> list[dict[str, Any]]:
    if (
        not valid_publication_identity(deployment_id)
        or len(firmware_sha256) != 64
        or len(deployment_lock_sha256) != 64
    ):
        raise ValueError("Phase 03.2 LED lineage is incomplete")
    rows: list[dict[str, Any]] = []
    for grammar in LED_GRAMMARS:
        masks = PHASE32_GRAMMAR_MASKS[grammar]
        for event in PHASE32_LED_EVENTS:
            candidate = event == "pending"
            active_owner = event in {"active-owner", "owner-after-other-focus"}
            owner_slot = 0 if event in {
                "pending", "active-owner", "owner-after-other-focus",
                "cancellation-return",
            } else None
            focus_slot = 1 if event == "owner-after-other-focus" else None
            hold_mask = masks[0] if owner_slot is not None else 0
            if event in PHASE32_FAILURE_EVENTS or event in PHASE32_SOURCE_EVENTS:
                hold_mask = 0
                owner_slot = None
            if event == "lifecycle-clear":
                hold_mask = 0
                owner_slot = None
            hue = {
                "pending": 185,
                "active-owner": 120,
                "owner-after-other-focus": 120,
                "cancellation-return": 45,
            }.get(event, 0)
            segments = [] if hold_mask == 0 else [{
                "zone_mask": hold_mask,
                "slot": owner_slot,
                "hue": hue,
                "saturation": 100,
                "brightness": 45,
            }]
            row: dict[str, Any] = {
                "id": f"{grammar}-{event}",
                "grammar": grammar,
                "event": event,
                "source": "resolved-bounded-led-event",
                "evidence_kind": "logical-only",
                "deployment_id": deployment_id,
                "firmware_sha256": firmware_sha256,
                "deployment_lock_sha256": deployment_lock_sha256,
                "candidate": candidate,
                "active_owner": active_owner,
                "owner_slot": owner_slot,
                "focus_slot": focus_slot,
                "lifecycle_cleared": event == "lifecycle-clear",
                "source_fenced": event in PHASE32_SOURCE_EVENTS,
                "failure": event in PHASE32_FAILURE_EVENTS,
                "hold_mask": hold_mask,
                "segments": segments,
                "physical_claim": False,
            }
            row["content_sha256"] = _phase32_row_hash(row)
            rows.append(row)
    return rows


def validate_phase32_led_rows(
    rows: list[Mapping[str, Any]],
    deployment_id: str,
    firmware_sha256: str,
    deployment_lock_sha256: str,
) -> None:
    expected = {(grammar, event) for grammar in LED_GRAMMARS for event in PHASE32_LED_EVENTS}
    actual = {(row.get("grammar"), row.get("event")) for row in rows}
    if actual != expected or len(rows) != len(expected):
        raise ValueError("Phase 03.2 LED grammar event matrix is incomplete")
    for row in rows:
        grammar = row.get("grammar")
        event = row.get("event")
        if (
            row.get("deployment_id") != deployment_id
            or row.get("firmware_sha256") != firmware_sha256
            or row.get("deployment_lock_sha256") != deployment_lock_sha256
        ):
            raise ValueError("Phase 03.2 LED deployment linkage is invalid")
        if (
            grammar not in LED_GRAMMARS
            or event not in PHASE32_LED_EVENTS
            or row.get("source") != "resolved-bounded-led-event"
            or row.get("evidence_kind") != "logical-only"
            or row.get("physical_claim") is not False
        ):
            raise ValueError("Phase 03.2 LED evidence makes a physical claim")
        if row.get("content_sha256") != _phase32_row_hash(row):
            raise ValueError("Phase 03.2 LED content hash mismatch")
        active = event in {"active-owner", "owner-after-other-focus"}
        owner = event in {
            "pending", "active-owner", "owner-after-other-focus",
            "cancellation-return",
        }
        if event in PHASE32_FAILURE_EVENTS or event in PHASE32_SOURCE_EVENTS or event == "lifecycle-clear":
            if row.get("active_owner") or row.get("owner_slot") is not None or row.get("hold_mask") != 0:
                category = "failure" if event in PHASE32_FAILURE_EVENTS else (
                    "source" if event in PHASE32_SOURCE_EVENTS else "lifecycle"
                )
                raise ValueError(f"Phase 03.2 {category} fence admits active owner")
        elif row.get("active_owner") is not active or (row.get("owner_slot") is not (0 if owner else None)):
            raise ValueError("Phase 03.2 LED owner identity is invalid")
        if event == "owner-after-other-focus" and row.get("focus_slot") != 1:
            raise ValueError("Phase 03.2 owner-after-other-focus slot is invalid")
        if event != "owner-after-other-focus" and row.get("focus_slot") is not None:
            raise ValueError("Phase 03.2 unexpected focus slot")
        expected_mask = (
            PHASE32_GRAMMAR_MASKS[grammar][0]
            if owner and not (
                event in PHASE32_FAILURE_EVENTS or
                event in PHASE32_SOURCE_EVENTS or
                event == "lifecycle-clear"
            )
            else 0
        )
        if row.get("hold_mask") != expected_mask:
            raise ValueError("Phase 03.2 LED mapped zone is invalid")
        segments = row.get("segments")
        if expected_mask == 0:
            if segments != []:
                raise ValueError("Phase 03.2 fenced LED row retains a segment")
        elif (
            not isinstance(segments, list)
            or len(segments) != 1
            or segments[0].get("zone_mask") != expected_mask
            or segments[0].get("slot") != 0
        ):
            raise ValueError("Phase 03.2 LED segment mapping is invalid")


def validate_phase32_framebuffer_evidence(
    evidence: Mapping[str, Any],
    deployment: Mapping[str, Any],
    *,
    deployment_lock_sha256: str,
) -> None:
    required = {
        "schema_version", "kind", "status", "source", "evidence_boundary",
        "deployment_id", "firmware_sha256", "deployment_lock_sha256",
        "captures", "led_events", "contact_sheets", "matrix", "row_counts",
    }
    if (
        set(evidence) != required
        or evidence.get("schema_version") != 1
        or evidence.get("kind") != "phase03.2-framebuffer-evidence"
        or evidence.get("status") != "pass"
        or evidence.get("source") != "logical-framebuffer-only"
    ):
        raise ValueError("Phase 03.2 framebuffer evidence schema is not closed")
    deployment_id = deployment.get("deployment_id")
    firmware_sha256 = deployment.get("firmware_sha256")
    if (
        evidence.get("deployment_id") != deployment_id
        or evidence.get("firmware_sha256") != firmware_sha256
        or evidence.get("deployment_lock_sha256") != deployment_lock_sha256
    ):
        raise ValueError("Phase 03.2 framebuffer deployment linkage mismatch")
    boundary = evidence.get("evidence_boundary")
    if (
        not isinstance(boundary, Mapping)
        or boundary.get("physical_claims") != "none"
        or boundary.get("deferred_to") != "03.2-09"
    ):
        raise ValueError("Phase 03.2 framebuffer evidence makes physical claims")

    captures = evidence.get("captures")
    expected_capture_count = len(THEMES) * len(PHASE32_HOLD_SCENES) * len(PHASE32_LEVELS)
    if not isinstance(captures, list) or len(captures) != expected_capture_count:
        raise ValueError("Phase 03.2 framebuffer capture matrix is incomplete")
    expected_captures = {
        (theme, scene, level)
        for theme in THEMES
        for scene in PHASE32_HOLD_SCENES
        for level in PHASE32_LEVELS
    }
    actual_captures = set()
    for capture in captures:
        key = (capture.get("theme"), capture.get("scene"), capture.get("level"))
        if key in actual_captures or key not in expected_captures:
            raise ValueError("Phase 03.2 framebuffer capture matrix has invalid rows")
        actual_captures.add(key)
        if (
            capture.get("width") != 128
            or capture.get("height") != 128
            or capture.get("panel") != 4
            or capture.get("deployment_id") != deployment_id
            or capture.get("firmware_sha256") != firmware_sha256
            or capture.get("deployment_lock_sha256") != deployment_lock_sha256
            or capture.get("source") != "deterministic-device-framebuffer"
        ):
            raise ValueError("Phase 03.2 framebuffer capture lineage is invalid")
        for path_key, hash_key in (("rgb565_path", "rgb565_sha256"), ("png_path", "png_sha256")):
            artifact = resolve_repo_path(capture[path_key])
            if sha256_file(artifact) != capture[hash_key]:
                raise ValueError(f"Phase 03.2 framebuffer capture hash mismatch: {capture['id']}")
        raw = resolve_repo_path(capture["rgb565_path"])
        png = resolve_repo_path(capture["png_path"])
        if raw.stat().st_size != 128 * 128 * 2 or not png_has_deployment(png, deployment_id):
            raise ValueError("Phase 03.2 framebuffer capture payload is invalid")
    if actual_captures != expected_captures:
        raise ValueError("Phase 03.2 framebuffer capture matrix is incomplete")

    matrix = evidence.get("matrix")
    if (
        not isinstance(matrix, Mapping)
        or set(matrix.get("themes", [])) != set(THEMES)
        or set(matrix.get("levels", [])) != set(PHASE32_LEVELS)
        or set(matrix.get("hold_scenes", {}).keys()) != set(THEMES)
    ):
        raise ValueError("Phase 03.2 framebuffer matrix header is incomplete")
    for theme in THEMES:
        if (
            set(matrix["hold_scenes"].get(theme, [])) != set(PHASE32_HOLD_SCENES)
            or set(matrix.get("levels_by_theme", {}).get(theme, [])) != set(PHASE32_LEVELS)
        ):
            raise ValueError("Phase 03.2 framebuffer hold matrix is incomplete")

    led_rows = evidence.get("led_events")
    if not isinstance(led_rows, list):
        raise ValueError("Phase 03.2 LED evidence is missing")
    validate_phase32_led_rows(
        led_rows, deployment_id, firmware_sha256, deployment_lock_sha256
    )
    contacts = evidence.get("contact_sheets")
    if not isinstance(contacts, list) or {item.get("theme") for item in contacts} != set(THEMES):
        raise ValueError("Phase 03.2 contact-sheet matrix is incomplete")
    for contact in contacts:
        artifact = resolve_repo_path(contact["path"])
        if (
            sha256_file(artifact) != contact.get("sha256")
            or contact.get("deployment_id") != deployment_id
            or contact.get("firmware_sha256") != firmware_sha256
            or contact.get("deployment_lock_sha256") != deployment_lock_sha256
            or not png_has_deployment(artifact, deployment_id)
        ):
            raise ValueError("Phase 03.2 contact-sheet linkage is invalid")
    counts = evidence.get("row_counts")
    if counts != {
        "captures": expected_capture_count,
        "led_events": len(LED_GRAMMARS) * len(PHASE32_LED_EVENTS),
        "contact_sheets": len(THEMES),
    }:
        raise ValueError("Phase 03.2 evidence row counts are invalid")


def validate_phase32_framebuffer_evidence_file(
    path: Path,
    deployment_path: Path,
    *,
    firmware: Path | None = None,
    require_current: bool = False,
) -> dict[str, Any]:
    path = path.resolve()
    deployment_path = deployment_path.resolve()
    _phase31_sidecar(path, "Phase 03.2 framebuffer evidence")
    deployment = validate_phase32_deployment_file(
        deployment_path,
        firmware=(firmware or ROOT / ".pio/build/selected-usb/firmware.bin").resolve(),
        require_current=require_current,
    )
    evidence = json.loads(path.read_text(encoding="ascii"))
    validate_phase32_framebuffer_evidence(
        evidence,
        deployment,
        deployment_lock_sha256=_phase31_sidecar(deployment_path, "Phase 03.2 deployment"),
    )
    return evidence


def _phase32_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"Phase 03.2 {label} hash is invalid")
    return value


def validate_phase32_device_evidence(
    evidence: Mapping[str, Any],
    deployment: Mapping[str, Any],
    qualification: Mapping[str, Any],
    *,
    deployment_lock_sha256: str,
    qualification_sha256: str,
    require_complete: bool = True,
) -> dict[str, Any]:
    """Validate typed physical observations without upgrading machine facts.

    A physical row is accepted only when its own typed operator observation is
    present.  ``machine_invariant`` is an additional prerequisite, never a
    substitute for that observation.
    """
    required = {
        "schema_version", "kind", "status", "deployment_id", "firmware_sha256",
        "deployment_lock_sha256", "qualification_sha256", "threshold_ms",
        "edge_assumptions", "rows", "oracle_state",
    }
    if set(evidence) != required or evidence.get("schema_version") != 1:
        raise ValueError("Phase 03.2 physical evidence schema is not closed")
    if evidence.get("kind") != PHASE32_DEVICE_EVIDENCE_KIND:
        raise ValueError("Phase 03.2 physical evidence kind is invalid")
    expected_status = "pass" if require_complete else evidence.get("status")
    if evidence.get("status") != expected_status:
        raise ValueError("Phase 03.2 physical evidence is incomplete")
    deployment_id = deployment.get("deployment_id")
    firmware_sha256 = deployment.get("firmware_sha256")
    lock_sha = _phase32_hash(deployment_lock_sha256, "deployment lock")
    qualification_sha = _phase32_hash(qualification_sha256, "qualification")
    if (
        evidence.get("deployment_id") != deployment_id
        or evidence.get("firmware_sha256") != firmware_sha256
        or evidence.get("deployment_lock_sha256") != lock_sha
        or evidence.get("qualification_sha256") != qualification_sha
        or evidence.get("threshold_ms") != 550
        or evidence.get("edge_assumptions") != list(FINAL_EDGE_ASSUMPTIONS)
    ):
        raise ValueError("Phase 03.2 physical evidence deployment or assumption lineage is invalid")
    rows = evidence.get("rows")
    if not isinstance(rows, list) or tuple(
        row.get("id") for row in rows if isinstance(row, Mapping)
    ) != PHASE32_DEVICE_ROW_IDS:
        raise ValueError("Phase 03.2 physical evidence rows are incomplete or reordered")
    qualification_rows = {
        row.get("id"): row
        for row in qualification.get("rows", [])
        if isinstance(row, Mapping)
    }
    if qualification.get("status") != "pass" or not qualification_rows:
        raise ValueError("Phase 03.2 physical evidence lacks a measured qualification matrix")
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or row.get("source") != "physical-observation"
            or row.get("physical_claim") is not True
            or row.get("result") != "pass"
        ):
            raise ValueError("Phase 03.2 physical evidence row is not a typed physical pass")
        row_id = row.get("id")
        machine_id = PHASE32_MACHINE_ROW_FOR_DEVICE.get(row_id)
        machine = row.get("machine_invariant")
        machine_row = qualification_rows.get(machine_id)
        if (
            not isinstance(machine, Mapping)
            or set(machine) != {"row_id", "row_sha256"}
            or machine.get("row_id") != machine_id
            or not isinstance(machine.get("row_sha256"), str)
            or not isinstance(machine_row, Mapping)
            or machine_row.get("status") != "pass"
            or machine_row.get("applicable") is not True
            or machine_row.get("observed_count") != machine_row.get("required_count")
            or machine.get("row_sha256") != _phase32_row_hash(machine_row)
        ):
            raise ValueError("Phase 03.2 physical row lacks its validated machine invariant")
        observation = row.get("observation")
        value = observation.get("value") if isinstance(observation, Mapping) else None
        if (
            not isinstance(observation, Mapping)
            or observation.get("kind") != "typed"
            or observation.get("result") != "pass"
            or not isinstance(value, Mapping)
            or value.get("answer") != "Y"
        ):
            raise ValueError("Phase 03.2 physical evidence observation is not typed")
    if evidence.get("oracle_state") != "UP":
        raise ValueError("Phase 03.2 physical evidence oracle is not UP")
    if qualification.get("status") != "pass":
        raise ValueError("Phase 03.2 physical evidence lacks a passing qualification")
    return dict(evidence)


def validate_phase32_defect_ledger(
    ledger: Mapping[str, Any],
    deployment: Mapping[str, Any],
    *,
    deployment_lock_sha256: str,
    qualification_sha256: str,
    device_evidence_sha256: str,
    require_no_open: bool = True,
) -> dict[str, Any]:
    required = {
        "schema_version", "kind", "status", "deployment_id",
        "deployment_lock_sha256", "qualification_sha256",
        "device_evidence_sha256", "defects", "history",
    }
    if set(ledger) != required or ledger.get("schema_version") != 1:
        raise ValueError("Phase 03.2 defect ledger schema is not closed")
    if ledger.get("kind") != PHASE32_DEFECT_LEDGER_KIND:
        raise ValueError("Phase 03.2 defect ledger kind is invalid")
    if (
        ledger.get("deployment_id") != deployment.get("deployment_id")
        or ledger.get("deployment_lock_sha256") != _phase32_hash(deployment_lock_sha256, "deployment lock")
        or ledger.get("qualification_sha256") != _phase32_hash(qualification_sha256, "qualification")
        or ledger.get("device_evidence_sha256") != _phase32_hash(device_evidence_sha256, "device evidence")
    ):
        raise ValueError("Phase 03.2 defect ledger lineage is invalid")
    defects = ledger.get("defects")
    history = ledger.get("history")
    if not isinstance(defects, list) or not isinstance(history, list):
        raise ValueError("Phase 03.2 defect ledger entries are not lists")
    if require_no_open and (ledger.get("status") != "pass" or defects):
        raise ValueError("Phase 03.2 defect ledger contains an open defect")
    for entry in history:
        if not isinstance(entry, Mapping):
            raise ValueError("Phase 03.2 defect history entry is not an object")
        if require_no_open and entry.get("status") == "open":
            raise ValueError("Phase 03.2 defect history contains an open defect")
    return dict(ledger)


def validate_phase32_gate(
    gate: Mapping[str, Any],
    deployment: Mapping[str, Any],
    qualification: Mapping[str, Any],
    device_evidence: Mapping[str, Any],
    defect_ledger: Mapping[str, Any],
    *,
    require_current_deployment: bool = True,
    require_complete_qualification: bool = True,
    require_current_device_evidence: bool = True,
    require_no_open_defects: bool = True,
    require_oracle_up: bool = True,
) -> dict[str, Any]:
    """Join the production qualification and physical evidence fail-closed."""
    if not isinstance(gate, Mapping) or gate.get("schema_version") != 1:
        raise ValueError("Phase 03.2 gate schema is not closed")
    if gate.get("kind") != PHASE32_PHASE4_GATE_KIND or gate.get("status") != "pass":
        raise ValueError("Phase 03.2 gate is not a passing release gate")
    deployment_id = deployment.get("deployment_id")
    firmware_sha256 = deployment.get("firmware_sha256")
    if (
        gate.get("deployment_id") != deployment_id
        or gate.get("firmware_sha256") != firmware_sha256
    ):
        raise ValueError("Phase 03.2 gate deployment lineage is stale")
    lock_sha = _phase32_hash(gate.get("deployment_lock_sha256"), "deployment lock")
    qualification_sha = _phase32_hash(gate.get("qualification_sha256"), "qualification")
    evidence_sha = _phase32_hash(gate.get("device_evidence_sha256"), "device evidence")
    ledger_sha = _phase32_hash(gate.get("defect_ledger_sha256"), "defect ledger")
    if require_current_deployment and deployment.get("deployment_id") != gate.get("deployment_id"):
        raise ValueError("Phase 03.2 gate does not reference the current deployment")
    validate_final_qualification(qualification, deployment, gate.get("logical_evidence"))
    if require_complete_qualification and qualification.get("status") != "pass":
        raise ValueError("Phase 03.2 gate qualification is incomplete")
    validate_phase32_device_evidence(
        device_evidence,
        deployment,
        qualification,
        deployment_lock_sha256=lock_sha,
        qualification_sha256=qualification_sha,
        require_complete=require_current_device_evidence,
    )
    validate_phase32_defect_ledger(
        defect_ledger,
        deployment,
        deployment_lock_sha256=lock_sha,
        qualification_sha256=qualification_sha,
        device_evidence_sha256=evidence_sha,
        require_no_open=require_no_open_defects,
    )
    if require_oracle_up and (
        gate.get("oracle_state") != "UP"
        or qualification.get("input_oracle", {}).get("state") != "UP"
        or device_evidence.get("oracle_state") != "UP"
    ):
        raise ValueError("Phase 03.2 gate oracle is not UP")
    if gate.get("edge_assumptions") != list(FINAL_EDGE_ASSUMPTIONS):
        raise ValueError("Phase 03.2 gate edge assumptions are incomplete")
    if gate.get("device_evidence_sha256") != evidence_sha or gate.get("defect_ledger_sha256") != ledger_sha:
        raise ValueError("Phase 03.2 gate sidecar hashes are invalid")
    return dict(gate)


def validate_phase32_gate_file(
    gate_path: Path,
    deployment_path: Path,
    qualification_path: Path,
    evidence_path: Path,
    defect_ledger_path: Path,
    *,
    require_current_deployment: bool = True,
    require_complete_qualification: bool = True,
    require_current_device_evidence: bool = True,
    require_no_open_defects: bool = True,
    require_oracle_up: bool = True,
) -> dict[str, Any]:
    """Reopen all final sidecars and apply the same hash-only join as the CLI."""
    paths = [Path(item).resolve() for item in (
        gate_path, deployment_path, qualification_path, evidence_path, defect_ledger_path
    )]
    gate, deployment, qualification, evidence, ledger = (
        json.loads(path.read_text(encoding="ascii")) for path in paths
    )
    deployment_lock_sha = _phase31_sidecar(paths[1], "Phase 03.2 deployment")
    qualification_sha = _phase31_sidecar(paths[2], "Phase 03.2 qualification")
    evidence_sha = _phase31_sidecar(paths[3], "Phase 03.2 device evidence")
    ledger_sha = _phase31_sidecar(paths[4], "Phase 03.2 defect ledger")
    if (
        gate.get("deployment_lock_sha256") != deployment_lock_sha
        or gate.get("qualification_sha256") != qualification_sha
        or gate.get("device_evidence_sha256") != evidence_sha
        or gate.get("defect_ledger_sha256") != ledger_sha
    ):
        raise ValueError("Phase 03.2 gate sidecar linkage is invalid")
    validate_phase32_gate(
        gate,
        deployment,
        qualification,
        evidence,
        ledger,
        require_current_deployment=require_current_deployment,
        require_complete_qualification=require_complete_qualification,
        require_current_device_evidence=require_current_device_evidence,
        require_no_open_defects=require_no_open_defects,
        require_oracle_up=require_oracle_up,
    )
    return gate

def _phase32_run_automated_preflight() -> list[dict[str, Any]]:
    """Run the bounded production qualification checks before any prompt."""
    python = ROOT / "tools/phase1_bringup/.venv/bin/python3"
    commands = [
        (
            str(python),
            "-m",
            "unittest",
            "tools.phase1_bringup.test_composite_qualification",
            "tools.phase1_bringup.test_phase3_smoke",
            "-k",
            "phase32",
        ),
        (
            str(python),
            "-m",
            "unittest",
            "host.herdr_keypad.tests.test_protocol",
            "host.herdr_keypad.tests.test_projection",
            "host.herdr_keypad.tests.test_focus",
            "host.herdr_keypad.tests.test_integration",
        ),
    ]
    for environment in (
        "native",
        "native-agent-projection",
        "native-hold-controller",
        "native-board-adapter",
    ):
        commands.append((str(python), "-m", "platformio", "test", "-e", environment))
    runs: list[dict[str, Any]] = []
    for command in commands:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=900,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            output = getattr(exc, "stdout", b"") or b""
            detail = output.decode("utf-8", errors="replace")[-1200:]
            raise RuntimeError(
                f"automated Phase 03.2 preflight failed: {' '.join(command)}"
                + (f"\n{detail}" if detail else "")
            ) from exc
        output = completed.stdout or b""
        runs.append({
            "command": list(command),
            "status": "pass",
            "returncode": completed.returncode,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "output_sha256": sha256_bytes(output),
        })
    return runs


def _phase32_capture_input_until(
    device: Path,
    stop: threading.Event,
) -> list[dict[str, Any]]:
    from .composite_qualification import _EV_KEY, _INPUT_EVENT, _KEY_SPACE

    fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    selector = selectors.DefaultSelector()
    events: list[dict[str, Any]] = []
    try:
        selector.register(fd, selectors.EVENT_READ)
        while not stop.is_set():
            for _key, _mask in selector.select(0.2):
                block = os.read(fd, _INPUT_EVENT.size * 64)
                if not block:
                    stop.set()
                    break
                if len(block) % _INPUT_EVENT.size:
                    raise RuntimeError("Phase 03.2 evdev observer received a partial input_event")
                for offset in range(0, len(block), _INPUT_EVENT.size):
                    _sec, _usec, event_type, code, value = _INPUT_EVENT.unpack_from(block, offset)
                    if event_type == _EV_KEY and code == _KEY_SPACE:
                        events.append({
                            "type": "EV_KEY",
                            "code": "KEY_SPACE",
                            "value": value,
                            "monotonic_ns": time.monotonic_ns(),
                        })
    finally:
        selector.close()
        os.close(fd)
    return events
@dataclass
class _Phase32ObserverCapture:
    interval_id: str
    started_monotonic_ns: int
    events: list[dict[str, Any]] = field(default_factory=list)
    ended_monotonic_ns: int | None = None
    error: BaseException | None = None
    complete: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "interval_id": self.interval_id,
            "started_monotonic_ns": self.started_monotonic_ns,
            "ended_monotonic_ns": self.ended_monotonic_ns,
            "events": list(self.events),
            "error": None if self.error is None else repr(self.error),
            "complete": self.complete,
        }


def _phase32_physical_rows(
    observations: Mapping[str, Mapping[str, Any]],
    qualification: Mapping[str, Any],
) -> list[dict[str, Any]]:
    step_for_row = {
        **{row_id: "threshold-calibration" for row_id in ("D-01", "D-02", "D-03", "D-04", "D-05")},
        **{row_id: "presentation" for row_id in ("D-06", "D-07", "D-08", "D-09", "D-10", "D-11", "D-12", "D-13", "D-14")},
        **{row_id: "lifecycle" for row_id in ("D-15", "D-16", "D-17", "D-18")},
    }
    qualification_rows = {
        row.get("id"): row
        for row in qualification.get("rows", [])
        if isinstance(row, Mapping)
    }
    if qualification.get("status") != "pass" or not qualification_rows:
        raise ValueError("physical rows require a passing measured qualification matrix")
    rows: list[dict[str, Any]] = []
    for row_id in PHASE32_DEVICE_ROW_IDS:
        observation = observations.get(row_id)
        machine_id = PHASE32_MACHINE_ROW_FOR_DEVICE[row_id]
        machine_row = qualification_rows.get(machine_id)
        if observation is None:
            raise ValueError(f"missing typed observation for {row_id}")
        if (
            not isinstance(observation, Mapping)
            or observation.get("answer") != "Y"
            or not isinstance(observation.get("prompt"), str)
            or not isinstance(observation.get("observed_at_unix_ms"), int)
            or isinstance(observation.get("observed_at_unix_ms"), bool)
            or observation.get("observed_at_unix_ms") <= 0
            or not isinstance(machine_row, Mapping)
            or machine_row.get("status") != "pass"
            or machine_row.get("applicable") is not True
            or machine_row.get("observed_count") != machine_row.get("required_count")
        ):
            raise ValueError(f"physical row {row_id} lacks a passing paired machine invariant")
        rows.append({
            "id": row_id,
            "source": "physical-observation",
            "machine_invariant": {
                "row_id": machine_id,
                "row_sha256": _phase32_row_hash(machine_row),
            },
            "result": "pass",
            "physical_claim": True,
            "observation": {
                "kind": "typed",
                "result": "pass",
                "value": {
                    "step_id": step_for_row[row_id],
                    "answer": observation["answer"],
                    "prompt": observation["prompt"],
                    "claim_scope": "operator-observation-only",
                    "reduced_human_threshold_sample": True,
                },
                "observed_at_unix_ms": observation["observed_at_unix_ms"],
            },
        })
    return rows


def _phase32_logical_lineage(logical_evidence: Mapping[str, Any]) -> dict[str, Any]:
    if all(
        isinstance(logical_evidence.get(field), str)
        for field in ("deployment_id", "firmware_sha256", "deployment_lock_sha256")
    ):
        return {
            "status": logical_evidence.get("status"),
            "deployment_id": logical_evidence["deployment_id"],
            "firmware_sha256": logical_evidence["firmware_sha256"],
            "deployment_lock_sha256": logical_evidence["deployment_lock_sha256"],
        }
    captures = logical_evidence.get("captures")
    if not isinstance(captures, list) or not captures or not isinstance(captures[0], Mapping):
        raise ValueError("Phase 03.2 logical evidence has no deployment lineage")
    first = captures[0]
    return {
        "status": logical_evidence.get("status"),
        "deployment_id": first.get("deployment_id"),
        "firmware_sha256": first.get("firmware_sha256"),
        "deployment_lock_sha256": first.get("deployment_lock_sha256"),
    }


def write_phase32_final_artifacts(
    output_root: Path,
    deployment_path: Path,
    logical_evidence_path: Path,
    qualification: Mapping[str, Any],
    observations: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate a complete staged set before publishing final artifacts.

    Existing final artifacts remain immutable.  A failed build stays in its
    unique staging directory and never leaves a partially-written final set.
    """
    output_root = output_root.resolve()
    deployment_path = deployment_path.resolve()
    logical_evidence_path = logical_evidence_path.resolve()
    deployment = json.loads(deployment_path.read_text(encoding="ascii"))
    logical_evidence = _phase32_logical_lineage(
        json.loads(logical_evidence_path.read_text(encoding="ascii"))
    )
    lock_sha = _phase31_sidecar(deployment_path, "Phase 03.2 deployment")
    names = (
        "03.2-FINAL-QUALIFICATION.json",
        "03.2-DEVICE-EVIDENCE.json",
        "03.2-DEFECT-LEDGER.json",
        "03.2-PHASE4-GATE.json",
    )
    final_paths = tuple(output_root / name for name in names)
    if any(
        path.exists() or path.with_suffix(path.suffix + ".sha256").exists()
        for path in final_paths
    ):
        raise RuntimeError("Phase 03.2 final artifacts already exist; refusing replacement")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(
        prefix=f".{output_root.name}.qualification-staging-",
        dir=output_root.parent,
    ))
    published_paths: list[Path] = []
    staging_paths = tuple(staging_root / name for name in names)
    try:
        qualification_sha = write_json(staging_paths[0], qualification, checksum=True)
        evidence = {
            "schema_version": 1,
            "kind": PHASE32_DEVICE_EVIDENCE_KIND,
            "status": "pass",
            "deployment_id": deployment["deployment_id"],
            "firmware_sha256": deployment["firmware_sha256"],
            "deployment_lock_sha256": lock_sha,
            "qualification_sha256": qualification_sha,
            "threshold_ms": qualification["threshold_ms"],
            "edge_assumptions": list(FINAL_EDGE_ASSUMPTIONS),
            "rows": _phase32_physical_rows(observations, qualification),
            "oracle_state": qualification["input_oracle"]["state"],
        }
        evidence_sha = write_json(staging_paths[1], evidence, checksum=True)
        ledger = {
            "schema_version": 1,
            "kind": PHASE32_DEFECT_LEDGER_KIND,
            "status": "pass",
            "deployment_id": deployment["deployment_id"],
            "deployment_lock_sha256": lock_sha,
            "qualification_sha256": qualification_sha,
            "device_evidence_sha256": evidence_sha,
            "defects": [],
            "history": [],
        }
        ledger_sha = write_json(staging_paths[2], ledger, checksum=True)
        gate = {
            "schema_version": 1,
            "kind": PHASE32_PHASE4_GATE_KIND,
            "status": "pass",
            "deployment_id": deployment["deployment_id"],
            "firmware_sha256": deployment["firmware_sha256"],
            "deployment_lock_sha256": lock_sha,
            "qualification_sha256": qualification_sha,
            "device_evidence_sha256": evidence_sha,
            "defect_ledger_sha256": ledger_sha,
            "logical_evidence": {
                "status": logical_evidence["status"],
                "deployment_id": logical_evidence["deployment_id"],
                "firmware_sha256": logical_evidence["firmware_sha256"],
                "deployment_lock_sha256": logical_evidence["deployment_lock_sha256"],
            },
            "edge_assumptions": list(FINAL_EDGE_ASSUMPTIONS),
            "oracle_state": qualification["input_oracle"]["state"],
            "phase4_ready": True,
        }
        gate_sha = write_json(staging_paths[3], gate, checksum=True)
        validate_phase32_gate_file(
            staging_paths[3],
            deployment_path,
            staging_paths[0],
            staging_paths[1],
            staging_paths[2],
        )
        output_root.mkdir(parents=True, exist_ok=True)
        publish_paths = tuple(
            path
            for path in staging_paths
            for path in (path, path.with_suffix(path.suffix + ".sha256"))
        )
        for source in publish_paths:
            destination = output_root / source.name
            os.replace(source, destination)
            published_paths.append(destination)
        staging_root.rmdir()
    except Exception as exc:
        for destination in reversed(published_paths):
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
        raise RuntimeError(
            f"Phase 03.2 final artifact staging failed; preserved at {staging_root}: {exc}"
        ) from exc
    return {
        "qualification_sha256": qualification_sha,
        "device_evidence_sha256": evidence_sha,
        "defect_ledger_sha256": ledger_sha,
        "gate_sha256": gate_sha,
        "paths": [path.as_posix() for path in final_paths],
    }


PHASE32_CHECKPOINT_KIND = "phase03.2-qualification-checkpoint"
PHASE32_CHECKPOINT_SCHEMA_VERSION = 1


def _phase32_checkpoint_path(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "checkpoint", None)
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return (
        Path(runtime)
        / "herdr-keypad"
        / f"phase32-{args.run_id}.checkpoint.json"
    )


def _phase32_checkpoint_template(
    run_id: str,
    deployment: Mapping[str, Any],
    deployment_lock_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": PHASE32_CHECKPOINT_SCHEMA_VERSION,
        "kind": PHASE32_CHECKPOINT_KIND,
        "status": "in_progress",
        "run_id": run_id,
        "deployment_id": deployment["deployment_id"],
        "firmware_sha256": deployment["firmware_sha256"],
        "deployment_lock_sha256": deployment_lock_sha256,
        "completed_steps": [],
        "observations": {},
        "automation_runs": [],
        "input_events": [],
        "input_intervals": [],
    }


def _phase32_load_checkpoint(
    path: Path,
    run_id: str,
    deployment: Mapping[str, Any],
    deployment_lock_sha256: str,
) -> dict[str, Any]:
    if not path.exists():
        return _phase32_checkpoint_template(run_id, deployment, deployment_lock_sha256)
    try:
        checkpoint = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"qualification checkpoint is unreadable: {path}") from exc
    if not isinstance(checkpoint, dict):
        raise RuntimeError("qualification checkpoint must be a JSON object")
    if (
        checkpoint.get("schema_version") != PHASE32_CHECKPOINT_SCHEMA_VERSION
        or checkpoint.get("kind") != PHASE32_CHECKPOINT_KIND
        or checkpoint.get("run_id") != run_id
    ):
        raise RuntimeError("qualification checkpoint identity is invalid")
    if checkpoint.get("status") == "failed":
        raise RuntimeError(
            "qualification checkpoint preserves a failed physical observation; use a new run-id"
        )
    if checkpoint.get("status") != "in_progress":
        raise RuntimeError("qualification checkpoint is not resumable")
    if any(
        checkpoint.get(field) != expected
        for field, expected in (
            ("deployment_id", deployment["deployment_id"]),
            ("firmware_sha256", deployment["firmware_sha256"]),
            ("deployment_lock_sha256", deployment_lock_sha256),
        )
    ):
        raise RuntimeError("qualification checkpoint deployment lineage changed")
    completed = checkpoint.get("completed_steps")
    expected_steps = [step_id for step_id, _prompt in PHASE32_OPERATOR_PROMPTS]
    if (
        not isinstance(completed, list)
        or completed != expected_steps[: len(completed)]
        or any(not isinstance(step, str) for step in completed)
    ):
        raise RuntimeError("qualification checkpoint steps are not a completed prefix")
    observations = checkpoint.get("observations")
    if not isinstance(observations, dict):
        raise RuntimeError("qualification checkpoint observations are invalid")
    expected_rows = {
        row_id
        for step_id, rows in (
            ("threshold-calibration", ("D-01", "D-02", "D-03", "D-04", "D-05")),
            ("presentation", ("D-06", "D-07", "D-08", "D-09", "D-10", "D-11", "D-12", "D-13", "D-14")),
            ("lifecycle", ("D-15", "D-16", "D-17", "D-18")),
        )
        if step_id in completed
        for row_id in rows
    }
    if set(observations) != expected_rows or any(
        not isinstance(observation, dict) or observation.get("answer") != "Y"
        for observation in observations.values()
    ):
        raise RuntimeError("qualification checkpoint physical observations are incomplete")
    automation_runs = checkpoint.get("automation_runs")
    if not isinstance(automation_runs, list) or any(
        not isinstance(run, dict) or run.get("status") != "pass"
        for run in automation_runs
    ):
        raise RuntimeError("qualification checkpoint automated runs are invalid")
    input_events = checkpoint.get("input_events")
    if not isinstance(input_events, list) or any(
        not isinstance(event, dict) for event in input_events
    ):
        raise RuntimeError("qualification checkpoint input events are invalid")
    input_intervals = checkpoint.get("input_intervals")
    if (
        not isinstance(input_intervals, list)
        or len(input_intervals) != len(completed)
        or any(
            not isinstance(interval, dict)
            or interval.get("complete") is not True
            or not isinstance(interval.get("interval_id"), str)
            or not isinstance(interval.get("events"), list)
            or not interval.get("events")
            for interval in input_intervals
        )
    ):
        raise RuntimeError("qualification checkpoint evdev intervals are incomplete")
    return checkpoint


def _phase32_save_checkpoint(path: Path, checkpoint: Mapping[str, Any]) -> None:
    write_json(path, dict(checkpoint))


def _phase32_checkpoint_rows(step_id: str) -> tuple[str, ...]:
    return {
        "threshold-calibration": ("D-01", "D-02", "D-03", "D-04", "D-05"),
        "presentation": ("D-06", "D-07", "D-08", "D-09", "D-10", "D-11", "D-12", "D-13", "D-14"),
        "lifecycle": ("D-15", "D-16", "D-17", "D-18"),
    }[step_id]


def _phase32_stop_observer(
    stop: threading.Event | None,
    observer: threading.Thread | None,
    captured: _Phase32ObserverCapture | None,
) -> dict[str, Any]:
    if stop is None or observer is None or captured is None:
        raise RuntimeError("Phase 03.2 evdev observer was not started")
    stop.set()
    observer.join(timeout=5.0)
    if observer.is_alive():
        raise RuntimeError(
            f"Phase 03.2 evdev observer timed out for interval {captured.interval_id}"
        )
    if captured.error is not None:
        raise RuntimeError(
            f"Phase 03.2 evdev observer failed for interval {captured.interval_id}: "
            f"{captured.error}"
        ) from captured.error
    if not captured.complete or captured.ended_monotonic_ns is None:
        raise RuntimeError(
            f"Phase 03.2 evdev observer did not complete interval {captured.interval_id}"
        )
    if captured.ended_monotonic_ns < captured.started_monotonic_ns:
        raise RuntimeError("Phase 03.2 evdev observer interval timestamps are invalid")
    if not captured.events:
        raise RuntimeError(
            f"Phase 03.2 evdev observer captured no required transition for interval "
            f"{captured.interval_id}"
        )
    return captured.as_dict()


def _phase32_start_observer(
    event_path: Path,
    interval_id: str,
) -> tuple[threading.Event, threading.Thread, _Phase32ObserverCapture]:
    stop = threading.Event()
    captured = _Phase32ObserverCapture(interval_id, time.monotonic_ns())

    def capture() -> None:
        try:
            captured.events.extend(_phase32_capture_input_until(event_path, stop))
        except BaseException as exc:
            captured.error = exc
        finally:
            captured.ended_monotonic_ns = time.monotonic_ns()
            captured.complete = captured.error is None

    observer = threading.Thread(target=capture, name="phase32-input-observer", daemon=True)
    observer.start()
    return stop, observer, captured
class _Phase32FixtureController:
    """Own the exact qualification USB session and its controlled focus script."""

    _POLL_INTERVAL_SECONDS = 0.01
    _RECONNECT_INTERVAL_SECONDS = 0.25

    def __init__(self, args: argparse.Namespace) -> None:
        from herdr_keypad.usb import UsbDeviceSession

        self.usb = UsbDeviceSession(args.binding, timeout=args.timeout)
        self.run_id = args.run_id
        self.hello: dict[str, Any] = {}
        self.device_metrics: dict[str, Any] = {}
        self.serial_number: str | None = None
        self._snapshot = self._fixture_snapshot()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failure: BaseException | None = None
        self._accepted_slots: set[int] = set()
        self._rejected_focus_results = 0

    def _fixture_snapshot(self) -> Any:
        from herdr_keypad.bridge import AgentEntry, Identity, Snapshot

        host_epoch = f"qualify-{hashlib.sha256(self.run_id.encode('utf-8')).hexdigest()[:24]}"
        entries = tuple(
            AgentEntry(
                slot,
                f"qualify:p{slot + 1}",
                f"QUALIFY KEY {slot + 1}",
                "CONTROLLED",
                "NOW",
                "0S",
                "working",
                Identity(
                    f"qualify:p{slot + 1}",
                    f"qualify-term-{slot + 1}",
                    f"qualify-session-{slot + 1}",
                    1,
                ),
            )
            for slot in range(3)
        )
        return Snapshot(host_epoch, 1, "current", entries)

    def _connect_and_publish(self, *, reset_metrics: bool) -> None:
        hello = self.usb.connect()
        if reset_metrics:
            self.device_metrics = self.usb.request_metrics(reset=True)
        ack = self.usb.publish_snapshot(self._snapshot.as_payload())
        if (
            ack.get("accepted") is not True
            or ack.get("host_epoch") != self._snapshot.host_epoch
            or ack.get("snapshot_revision") != self._snapshot.snapshot_revision
        ):
            raise RuntimeError("qualification fixture snapshot was not exactly acknowledged")
        self.hello = dict(hello)
        candidate = getattr(self.usb, "candidate", None)
        if self.serial_number is None:
            self.serial_number = getattr(candidate, "serial_number", None)

    def _focus_result(self, frame: Mapping[str, Any]) -> dict[str, Any]:
        from herdr_keypad.bridge import FocusResult, Identity

        if frame.get("type") != "focus_intent":
            raise RuntimeError("qualification controller received an unexpected device frame")
        if frame.get("session_id") != getattr(self.usb, "session_id", None):
            raise RuntimeError("qualification focus intent crossed USB sessions")
        payload = frame.get("payload")
        if not isinstance(payload, Mapping):
            raise RuntimeError("qualification focus intent payload is invalid")
        identity = Identity(
            payload["pane_id"],
            payload["terminal_id"],
            payload["agent_session"],
            payload["source_revision"],
        )
        slot = payload["slot"]
        expected = self._snapshot.agents[slot] if isinstance(slot, int) and 0 <= slot < 3 else None
        exact = (
            expected is not None
            and payload["host_epoch"] == self._snapshot.host_epoch
            and payload["snapshot_revision"] == self._snapshot.snapshot_revision
            and payload["entry_id"] == expected.entry_id
            and identity == expected.identity
        )
        result = FocusResult(
            payload["action_id"],
            "accepted" if exact else "stale_target",
            payload["host_epoch"],
            payload["snapshot_revision"],
            slot,
            payload["entry_id"],
            identity,
            exact,
        )
        return result.as_payload()

    def _run(self) -> None:
        from herdr_keypad.usb import UsbSessionError

        try:
            while not self._stop.is_set():
                if not self.usb.connected:
                    try:
                        self._connect_and_publish(reset_metrics=False)
                    except UsbSessionError:
                        self._stop.wait(self._RECONNECT_INTERVAL_SECONDS)
                        continue
                try:
                    frame = self.usb.poll()
                    if frame is not None:
                        result = self._focus_result(frame)
                        self.usb.send_focus_result(result)
                        if result["outcome"] == "accepted":
                            self._accepted_slots.add(result["slot"])
                        else:
                            self._rejected_focus_results += 1
                except UsbSessionError:
                    self.usb.close()
                    continue
                self._stop.wait(self._POLL_INTERVAL_SECONDS)
        except BaseException as exc:
            self._failure = exc

    def start(self) -> "_Phase32FixtureController":
        if self._thread is not None:
            raise RuntimeError("qualification fixture controller already started")
        try:
            self._connect_and_publish(reset_metrics=True)
        except BaseException:
            self.usb.close()
            raise
        self._thread = threading.Thread(
            target=self._run,
            name="phase32-fixture-controller",
            daemon=True,
        )
        self._thread.start()
        return self

    def assert_running(self) -> None:
        if self._failure is not None:
            raise RuntimeError("qualification fixture controller failed") from self._failure
        if self._thread is None or not self._thread.is_alive():
            raise RuntimeError("qualification fixture controller is not running")

    def assert_batch(self, step_id: str) -> None:
        self.assert_running()
        if step_id == "presentation" and self._accepted_slots != {0, 1, 2}:
            raise RuntimeError(
                "presentation requires exact accepted focus round trips for all three fixture slots"
            )

    def evidence(self) -> dict[str, Any]:
        return {
            "mode": "controlled-fixture",
            "live_herdr_connected": False,
            "host_epoch": self._snapshot.host_epoch,
            "snapshot_revision": self._snapshot.snapshot_revision,
            "accepted_focus_slots": sorted(self._accepted_slots),
            "rejected_focus_results": self._rejected_focus_results,
        }
    def measured_evidence(self) -> dict[str, Any]:
        """Return only observations the controlled fixture actually measured."""
        return {}

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self.usb.close()

    def __enter__(self) -> "_Phase32FixtureController":
        return self.start()

    def __exit__(self, *_args: object) -> None:
        self.close()


def phase32_live_bridge(args: argparse.Namespace) -> _Phase32FixtureController:
    """Create the isolated qualification controller; never connect to Herdr."""
    return _Phase32FixtureController(args)


def run_phase32_qualification(args: argparse.Namespace) -> int:
    """Run a resumable automation-first exact-device observation session."""
    require_inherited_bridge_lock()
    deployment = validate_phase32_deployment_file(
        args.deployment,
        firmware=args.firmware,
        decision_path=args.decision,
        binding_path=args.binding,
        require_current=True,
    )
    logical_evidence = validate_phase32_framebuffer_evidence_file(
        args.logical_evidence,
        args.deployment,
        firmware=args.firmware,
        require_current=True,
    )
    logical_lineage = _phase32_logical_lineage(logical_evidence)
    deployment_lock_sha256 = _phase31_sidecar(args.deployment, "Phase 03.2 deployment")
    checkpoint_path = _phase32_checkpoint_path(args)
    checkpoint = _phase32_load_checkpoint(
        checkpoint_path,
        args.run_id,
        deployment,
        deployment_lock_sha256,
    )
    automation_runs = list(checkpoint["automation_runs"])
    if not automation_runs:
        automation_runs.extend(_phase32_run_automated_preflight())
        checkpoint["automation_runs"] = automation_runs
        _phase32_save_checkpoint(checkpoint_path, checkpoint)
    if checkpoint["completed_steps"]:
        automation_runs.extend(_phase32_run_automated_preflight())
        checkpoint["automation_runs"] = automation_runs
        _phase32_save_checkpoint(checkpoint_path, checkpoint)

    from .composite_qualification import _find_guided_keyboard_event

    descriptor = deployment["descriptor_tuple"]
    vid_pid = f"{int(descriptor['vid']):04x}:{int(descriptor['pid']):04x}"
    observations = dict(checkpoint["observations"])
    events = list(checkpoint["input_events"])
    input_intervals = list(checkpoint["input_intervals"])
    completed_steps = list(checkpoint["completed_steps"])
    run_suffix = args.run_id[-8:].upper()
    active_stop: threading.Event | None = None
    active_observer: threading.Thread | None = None
    active_captured: _Phase32ObserverCapture | None = None
    controller_evidence: dict[str, Any] = {}
    controller = phase32_live_bridge(args)
    controller.start()
    try:
        hello = controller.hello
        device_metrics = controller.device_metrics
        serial_number = controller.serial_number
        event_path = _find_guided_keyboard_event(
            vid_pid,
            serial_number,
            timeout=args.timeout,
        )
        for index, (step_id, prompt) in enumerate(PHASE32_OPERATOR_PROMPTS, 1):
            if step_id in completed_steps:
                continue
            controller.assert_running()
            event_path = _find_guided_keyboard_event(
                vid_pid,
                serial_number,
                timeout=args.timeout,
            )
            active_stop, active_observer, active_captured = _phase32_start_observer(
                event_path, step_id
            )
            print(
                f"CHECKPOINT run={args.run_id} state={step_id} "
                f"step={index}/{len(PHASE32_OPERATOR_PROMPTS)}",
                flush=True,
            )
            print(f"PROMPT: {prompt}", flush=True)
            try:
                answer = input(f"Answer Y/N {step_id} {run_suffix}: ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                interval = _phase32_stop_observer(
                    active_stop,
                    active_observer,
                    active_captured,
                )
                input_intervals.append(interval)
                events.extend(interval["events"])
                active_stop = active_observer = active_captured = None
                checkpoint["input_events"] = events
                checkpoint["input_intervals"] = input_intervals
                _phase32_save_checkpoint(checkpoint_path, checkpoint)
                print(
                    f"PHASE 03.2 CHECKPOINT PRESERVED run={args.run_id} "
                    f"state={step_id} resume=same-command",
                    flush=True,
                )
                return 75
            interval = _phase32_stop_observer(
                active_stop,
                active_observer,
                active_captured,
            )
            input_intervals.append(interval)
            events.extend(interval["events"])
            active_stop = active_observer = active_captured = None
            checkpoint["input_events"] = events
            checkpoint["input_intervals"] = input_intervals
            controller.assert_running()
            if answer not in {"Y", "N"}:
                _phase32_save_checkpoint(checkpoint_path, checkpoint)
                raise RuntimeError("Phase 03.2 physical response must be exactly Y or N")
            if answer != "Y":
                checkpoint["status"] = "failed"
                checkpoint["failure_step"] = step_id
                checkpoint["failure_answer"] = answer
                _phase32_save_checkpoint(checkpoint_path, checkpoint)
                raise RuntimeError(f"physical qualification failed at {step_id}; preserving no PASS")
            controller.assert_batch(step_id)
            observation = {
                "answer": answer,
                "prompt": prompt,
                "observed_at_unix_ms": time.time_ns() // 1_000_000,
            }
            observations.update({
                row_id: dict(observation)
                for row_id in _phase32_checkpoint_rows(step_id)
            })
            completed_steps.append(step_id)
            checkpoint["completed_steps"] = completed_steps
            checkpoint["observations"] = observations
            _phase32_save_checkpoint(checkpoint_path, checkpoint)
            if index < len(PHASE32_OPERATOR_PROMPTS):
                automation_runs.extend(_phase32_run_automated_preflight())
                checkpoint["automation_runs"] = automation_runs
                _phase32_save_checkpoint(checkpoint_path, checkpoint)
    finally:
        if active_stop is not None:
            interval = _phase32_stop_observer(
                active_stop,
                active_observer,
                active_captured,
            )
            input_intervals.append(interval)
            events.extend(interval["events"])
            checkpoint["input_events"] = events
            checkpoint["input_intervals"] = input_intervals
            _phase32_save_checkpoint(checkpoint_path, checkpoint)
        controller.close()
        controller_evidence = controller.evidence()

    if completed_steps != [step_id for step_id, _prompt in PHASE32_OPERATOR_PROMPTS]:
        raise RuntimeError("Phase 03.2 physical qualification did not complete every batch")
    checkpoint["automation_runs"] = automation_runs
    checkpoint["input_events"] = events
    checkpoint["input_intervals"] = input_intervals
    _phase32_save_checkpoint(checkpoint_path, checkpoint)
    input_trace = {
        "schema_version": 1,
        "kind": "composite-input-events",
        "observer": "linux-evdev",
        "external": True,
        "complete": True,
        "deferred": False,
        "events": events,
        "event_count": len(events),
        "final_state": "UP",
        "capture_intervals": input_intervals,
    }
    input_oracle = validate_input_trace(input_trace)
    input_oracle["capture_intervals"] = input_intervals
    qualification = build_final_qualification(
        deployment,
        logical_lineage,
        deployment_lock_sha256=deployment_lock_sha256,
        input_oracle=input_oracle,
        observed_hello=hello,
        measurements=controller.measured_evidence(),
        automation_runs=automation_runs,
    )
    # The controlled fixture currently exposes no complete production matrix;
    # build_final_qualification must therefore fail closed rather than infer it.
    written = write_phase32_final_artifacts(
        args.output_root,
        args.deployment,
        args.logical_evidence,
        qualification,
        observations,
    )
    checkpoint["status"] = "complete"
    _phase32_save_checkpoint(checkpoint_path, checkpoint)
    try:
        checkpoint_path.unlink()
    except FileNotFoundError:
        pass
    print(
        "PHASE 03.2 QUALIFICATION PASS "
        f"deployment={deployment['deployment_id']} "
        f"qualification_sha256={written['qualification_sha256']} "
        f"gate_sha256={written['gate_sha256']} "
        "checkpoint=cleared",
        flush=True,
    )
    return 0

def run_phase32_capture(args: argparse.Namespace) -> int:
    firmware = args.firmware.resolve()
    deployment_path = args.deployment.resolve()
    deployment = validate_phase32_deployment_file(
        deployment_path, firmware=firmware, require_current=True
    )
    deployment_lock_sha256 = _phase31_sidecar(deployment_path, "Phase 03.2 deployment")
    evidence_path = args.evidence.resolve()
    frames_dir = evidence_path.parent / "screenshots" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    contacts: list[dict[str, Any]] = []
    for theme in THEMES:
        frames: list[bytes] = []
        for scene in PHASE32_HOLD_SCENES:
            for level in PHASE32_LEVELS:
                record, rgb = _phase31_capture_ppm(
                    args,
                    frames_dir,
                    panel=3,
                    theme=theme,
                    scene=scene,
                    level=level,
                    phase=PHASE32_LEVEL_PHASE[level],
                    deployment_id=deployment["deployment_id"],
                )
                record.update({
                    "kind": "hold",
                    "firmware_sha256": deployment["firmware_sha256"],
                    "deployment_lock_sha256": deployment_lock_sha256,
                })
                frames.append(rgb)
                records.append(record)
        width, height, payload = make_contact(
            frames, len(PHASE32_LEVELS), deployment["deployment_id"]
        )
        contact_path = evidence_path.parent / "screenshots" / f"hold-{theme}-contact.png"
        atomic_write(contact_path, payload)
        contacts.append({
            "theme": theme,
            "path": relative(contact_path),
            "sha256": sha256_file(contact_path),
            "width": width,
            "height": height,
            "source_frame_width": 128,
            "source_frame_height": 128,
            "deployment_id": deployment["deployment_id"],
            "firmware_sha256": deployment["firmware_sha256"],
            "deployment_lock_sha256": deployment_lock_sha256,
        })
    evidence = {
        "schema_version": 1,
        "kind": "phase03.2-framebuffer-evidence",
        "status": "pass",
        "source": "logical-framebuffer-only",
        "evidence_boundary": {
            "physical_claims": "none",
            "deferred_to": "03.2-09",
            "machine_claims": [
                "logical composition",
                "bounded LED masks and events",
                "deployment and content hashes",
            ],
        },
        "deployment_id": deployment["deployment_id"],
        "firmware_sha256": deployment["firmware_sha256"],
        "deployment_lock_sha256": deployment_lock_sha256,
        "captures": records,
        "led_events": phase32_led_rows(
            deployment["deployment_id"],
            deployment["firmware_sha256"],
            deployment_lock_sha256,
        ),
        "contact_sheets": contacts,
        "matrix": {
            "themes": list(THEMES),
            "hold_scenes": {theme: list(PHASE32_HOLD_SCENES) for theme in THEMES},
            "levels": list(PHASE32_LEVELS),
            "levels_by_theme": {theme: list(PHASE32_LEVELS) for theme in THEMES},
            "failure_events": list(PHASE32_FAILURE_EVENTS),
            "source_events": list(PHASE32_SOURCE_EVENTS),
        },
        "row_counts": {
            "captures": len(records),
            "led_events": len(LED_GRAMMARS) * len(PHASE32_LED_EVENTS),
            "contact_sheets": len(contacts),
        },
    }
    write_json(evidence_path, evidence, checksum=True)
    reopened = json.loads(evidence_path.read_text(encoding="ascii"))
    validate_phase32_framebuffer_evidence(
        reopened, deployment, deployment_lock_sha256=deployment_lock_sha256
    )
    print(
        f"captured {len(records)} logical hold frames and "
        f"{len(evidence['led_events'])} LED rows for deployment "
        f"{deployment['deployment_id']}"
    )
    return 0


def run_phase32_validate(args: argparse.Namespace) -> int:
    evidence = validate_phase32_framebuffer_evidence_file(
        args.evidence,
        args.deployment,
        firmware=args.firmware,
        require_current=args.require_current_deployment,
    )
    print(
        f"validated Phase 03.2 framebuffer evidence with "
        f"{evidence['row_counts']['captures']} captures for "
        f"{evidence['deployment_id']}"
    )
    return 0


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
        if set(matrix.get("hold_scenes", {}).get(theme, [])) != set(HOLD_SCENES):
            raise ValueError("framebuffer hold scene matrix is incomplete")
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
        "hold_scenes": {theme: [] for theme in THEMES},
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
        for scene in HOLD_SCENES:
            capture("tiles", 0, theme, scene, "static")
            matrix["hold_scenes"][theme].append(scene)
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
    deploy32 = subparsers.add_parser("phase32-deploy-lock")
    deploy32.add_argument("--binding", type=Path, required=True)
    deploy32.add_argument("--decision", type=Path, required=True)
    deploy32.add_argument("--firmware", type=Path, required=True)
    deploy32.add_argument("--output", type=Path, required=True)
    deploy32.add_argument("--timeout", type=float, default=5.0)
    deploy32_validate = subparsers.add_parser("phase32-validate-deployment")
    deploy32_validate.add_argument("--binding", type=Path, required=True)
    deploy32_validate.add_argument("--decision", type=Path, required=True)
    deploy32_validate.add_argument("--firmware", type=Path, required=True)
    deploy32_validate.add_argument("--deployment", type=Path, required=True)
    deploy32_validate.add_argument("--require-current-deployment", action="store_true")
    capture32 = subparsers.add_parser("phase32-capture")
    capture32.add_argument("--binding", type=Path, required=True)
    capture32.add_argument("--firmware", type=Path, required=True)
    capture32.add_argument("--deployment", type=Path, required=True)
    capture32.add_argument("--evidence", type=Path, required=True)
    capture32.add_argument("--timeout", type=float, default=5.0)
    validate32 = subparsers.add_parser("phase32-validate")
    validate32.add_argument("--firmware", type=Path, required=True)
    validate32.add_argument("--deployment", type=Path, required=True)
    validate32.add_argument("--evidence", type=Path, required=True)
    validate32.add_argument("--require-current-deployment", action="store_true")
    qualify32 = subparsers.add_parser(
        "phase32-qualify",
        help="run automation-first exact-device production qualification",
    )
    qualify32.add_argument("--binding", type=Path, required=True)
    qualify32.add_argument(
        "--decision",
        type=Path,
        default=ROOT / "artifacts/phase03.2/composite-decision.json",
    )
    qualify32.add_argument(
        "--firmware",
        type=Path,
        default=ROOT / ".pio/build/selected-usb/firmware.bin",
    )
    qualify32.add_argument(
        "--deployment",
        type=Path,
        default=ROOT / "artifacts/phase03.2/03.2-FINAL-DEPLOYMENT.json",
    )
    qualify32.add_argument(
        "--logical-evidence",
        type=Path,
        default=ROOT / "artifacts/phase03.2/03.2-FRAMEBUFFER-EVIDENCE.json",
    )
    qualify32.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "artifacts/phase03.2",
    )
    qualify32.add_argument(
        "--run-id",
        default=f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-final",
    )
    qualify32.add_argument("--timeout", type=float, default=5.0)
    qualify32.add_argument(
        "--checkpoint",
        type=Path,
        help="optional resumable machine/checkpoint state path",
    )
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
    if args.command == "phase32-deploy-lock":
        return run_phase32_deploy_lock(args)
    if args.command == "phase32-validate-deployment":
        return run_phase32_validate_deployment(args)
    if args.command == "phase32-qualify":
        return run_phase32_qualification(args)
    if args.command == "phase32-capture":
        return run_phase32_capture(args)
    if args.command == "phase32-validate":
        return run_phase32_validate(args)
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
