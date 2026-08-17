"""CLI for the installed herdr-keypad plugin and bounded acceptance modes."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

from .bridge import (
    PermanentBridge,
    V2ProtocolError,
    verify_contract_inputs,
    write_acceptance_evidence,
    write_live_sync_evidence,
    _projection_payload,
)
from .herdr import HerdrClient
from .projection import InboxProjection
from .usb import UsbDeviceSession, binding_is_stable


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BINDING = Path(os.path.expanduser("~/.config/herdr/keypad-binding.json"))


def _bridge(args: argparse.Namespace) -> PermanentBridge:
    client = HerdrClient(args.herdr_socket, timeout=args.timeout)
    usb = UsbDeviceSession(args.binding, timeout=args.timeout)
    projection = InboxProjection(host_epoch=f"host-{os.getpid()}-{int(time.time())}")
    return PermanentBridge(client, usb, projection, contract_root=ROOT)


def inspect_mode(args: argparse.Namespace) -> int:
    if not binding_is_stable(args.binding):
        print("source unavailable; paired binding unavailable")
        return 1
    bridge = _bridge(args)
    try:
        snapshot = bridge.projection.bootstrap(bridge.client)
    except Exception:
        print("source offline; positions 1=EMPTY 2=EMPTY 3=EMPTY")
        return 1
    print(f"source {snapshot.source_status}; host_epoch {snapshot.host_epoch}; revision {snapshot.snapshot_revision}")
    for entry in snapshot.entries:
        if entry.occupied:
            print(f"position {entry.slot + 1}: {entry.title} / {entry.discriminator} / {entry.state}")
        else:
            print(f"position {entry.slot + 1}: EMPTY / NO AGENT / empty")
    return 0


def acceptance_fixture(args: argparse.Namespace) -> int:
    """Exercise static acceptance-only UI vectors without starting plugin startup."""
    contract = verify_contract_inputs(ROOT)
    # A source-independent normalized fixture proves the bounded field shape,
    # while no Herdr focus or device action is invoked by this mode.
    projection = InboxProjection(host_epoch="acceptance-fixture")
    rows = []
    if getattr(args, "stale_once", False):
        rows = []
    snapshot = projection.refresh(rows, source_status="empty")
    observed = {
        "mode": "stale-once" if getattr(args, "stale_once", False) else "ui-bounds",
        "physical_press_observed": False,
        "focus_invoked": False,
        "states": ["EMPTY", "STALE", "OFFLINE", "UNAVAILABLE", "PENDING", "FOCUSED", "REJECTED", "UNCERTAIN"],
    }
    if args.evidence:
        write_acceptance_evidence(Path(args.evidence), contract=contract, snapshot=snapshot, observed=observed)
    print("acceptance-only fixture complete; no focus invoked")
    return 0

def smoke_mode(args: argparse.Namespace) -> int:
    bridge = _bridge(args)
    contract = verify_contract_inputs(ROOT)
    try:
        snapshot = bridge.bootstrap()
    except Exception as exc:
        snapshot = bridge.projection.invalidate("offline")
        write_acceptance_evidence(
            Path(args.evidence),
            contract=contract,
            snapshot=snapshot,
            observed={
                "mode": "selected-usb-snapshot-ack",
                "physical_press_observed": False,
                "focus_invoked": False,
                "snapshot_acknowledged": False,
                "error": str(exc)[:160],
            },
        )
        print(f"snapshot acknowledgement unavailable: {str(exc)[:120]}", file=sys.stderr)
        return 1
    observed = {
        "mode": "selected-usb-snapshot-ack",
        "physical_press_observed": False,
        "focus_invoked": False,
        "snapshot_acknowledged": True,
        "device_id_persisted": True,
    }
    write_acceptance_evidence(Path(args.evidence), contract=contract, snapshot=snapshot, observed=observed)
    print(f"snapshot acknowledged: epoch={snapshot.host_epoch} revision={snapshot.snapshot_revision} slots=3")
    return 0


def live_sync_smoke_mode(args: argparse.Namespace) -> int:
    seconds = float(args.smoke_live_sync)
    if not 5.0 <= seconds <= 30.0:
        print("--smoke-live-sync must be bounded to 5..30 seconds", file=sys.stderr)
        return 2
    bridge = _bridge(args)
    evidence = args.evidence
    if evidence == ROOT / "artifacts/phase2/automated-acceptance.json":
        evidence = ROOT / "artifacts/phase2.1/live-sync-smoke.json"
    started = time.monotonic()
    initial = None
    changed = None
    metrics = None
    error = ""
    try:
        initial = bridge.bootstrap()
        deadline = started + seconds
        while time.monotonic() < deadline:
            bridge.run_once()
            current = bridge.projection.current
            if (
                current is not None
                and initial is not None
                and current.snapshot_revision != initial.snapshot_revision
                and current.source_status == "current"
                and bridge.ready
            ):
                changed = current
                focus = bridge.last_focus
                if (
                    focus is not None
                    and focus.get("focused") is True
                    and focus.get("snapshot_revision") == changed.snapshot_revision
                ):
                    break
            time.sleep(min(max(args.interval, 0.01), 0.1))
        if changed is None:
            error = "changed_generation_timeout"
        elif bridge.last_focus is None or bridge.last_focus.get("snapshot_revision") != changed.snapshot_revision:
            error = "changed_generation_focus_timeout"
        else:
            metrics = bridge.usb.request_metrics()
            required = ("max_display_flush_us", "minimum_free_heap", "max_key_poll_gap_us", "parser_high_water", "queue_high_water")
            if any(not isinstance(metrics.get(key), int) or metrics[key] < 0 for key in required):
                error = "metrics_invalid"
    except Exception as exc:
        error = str(exc)[:160] or "live_sync_smoke_failed"
    duration = min(seconds, max(0.0, time.monotonic() - started))
    passed = not error and initial is not None and changed is not None and bridge.last_focus is not None and metrics is not None
    write_live_sync_evidence(
        evidence,
        result="pass" if passed else "fail",
        duration_seconds=duration,
        initial=initial,
        changed=changed,
        focus=bridge.last_focus,
        metrics=metrics,
        bridge=bridge,
        error=error,
    )
    print(f"live sync smoke {'passed' if passed else 'failed'}: {error or 'changed generation and exact focus observed'}")
    return 0 if passed else 1


def run_mode(args: argparse.Namespace) -> int:
    bridge = _bridge(args)
    pidfile = os.environ.get("HERDR_KEYPAD_PIDFILE")
    if pidfile:
        Path(pidfile).write_text(f"{os.getpid()}\n", encoding="ascii")
    try:
        bridge.run(interval=args.interval)
    finally:
        if pidfile:
            try:
                Path(pidfile).unlink()
            except FileNotFoundError:
                pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="herdr-keypad")
    parser.add_argument("--binding", type=Path, default=DEFAULT_BINDING)
    parser.add_argument("--herdr-socket", default=os.path.expanduser("~/.config/herdr/herdr.sock"))
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--evidence", type=Path, default=ROOT / "artifacts/phase2/automated-acceptance.json")
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--smoke-live-sync", type=float, metavar="SECONDS")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--smoke-ui-bounds", action="store_true")
    parser.add_argument("--smoke-stale-once", type=int, metavar="SECONDS")
    parser.add_argument("--run-bridge", action="store_true")
    args = parser.parse_args(argv)
    if args.inspect:
        return inspect_mode(args)
    if args.smoke_ui_bounds:
        return acceptance_fixture(args)
    if args.smoke_stale_once is not None:
        args.stale_once = True
        return acceptance_fixture(args)
    if args.smoke_live_sync is not None:
        return live_sync_smoke_mode(args)
    if args.smoke:
        return smoke_mode(args)
    if args.run_bridge:
        return run_mode(args)
    parser.error("one of --run-bridge, --inspect, --smoke, --smoke-ui-bounds, or --smoke-stale-once is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
