from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tomllib
from herdr_keypad.bridge import (
    PermanentBridge,
    V2ProtocolError,
    _projection_payload,
    make_snapshot,
    snapshot_frame,
    verify_contract_inputs,
    write_live_sync_evidence,
)
from herdr_keypad.codex import ChildExit, CodexResult, CodexView, Redaction
from herdr_keypad.__main__ import main, write_publication_receipt
from herdr_keypad.herdr import HerdrClient, HerdrError
from herdr_keypad.projection import InboxProjection
from herdr_keypad.usb import UsbDeviceSession, UsbSessionError
from phase1_bringup import protocol
from phase1_bringup.discovery import (
    EXPECTED_CDC_INTERFACE,
    EXPECTED_SERIAL,
    Candidate,
    enumerate_candidates,
)
from phase1_bringup.pairing import PairingBinding, PairingStore

ROOT = Path(__file__).resolve().parents[3]
BINDING = Path(os.path.expanduser("~/.config/herdr/keypad-binding.json"))


def row(pane: str, rank: str, seq: int, *, revision: int = 1) -> dict:
    return {
        "pane_id": pane,
        "terminal_id": f"term-{pane}",
        "workspace_id": "workspace-1",
        "tab_id": f"tab-{pane}",
        "agent_status": "working",
        "focused": False,
        "revision": revision,
        "state_change_seq": seq,
        "title": f"Agent {pane}",
        "cwd": "/work/repo",
        "tokens": {"rank": rank, "title": f"Agent {pane}"},
    }


class FakeHerdr:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows if rows is not None else [row("pane-1", "0", 4), row("pane-2", "1", 3), row("pane-3", "2", 2)]
        self.calls: list[tuple[str, dict]] = []

    def request(self, method: str, params: dict):
        self.calls.append((method, params))
        if method == "session.snapshot":
            return {"version": "0.8.0", "protocol": 19, "workspaces": [], "tabs": [], "panes": [], "layouts": [], "agents": self.rows}
        if method == "agent.list":
            return {"agents": self.rows}
        if method == "workspace.list":
            return {"workspaces": [{"workspace_id": "workspace-1", "label": "repo"}]}
        if method == "events.subscribe":
            return {"subscribed": True}
        if method == "agent.focus":
            target = params["target"]
            focused = next(r for r in self.rows if r["pane_id"] == target).copy()
            focused["focused"] = True
            return {"type": "agent_info", "agent": focused}
        raise AssertionError(f"unexpected Herdr method {method}")


class FakeUsb:
    def __init__(self):
        self.connected = False
        self.session_id = "fake-session"
        self.published: list[dict] = []
        self.results: list[dict] = []
        self.pending_focus = None

    def connect(self):
        self.connected = True
        return {"hello": {"device_id": "paired"}}

    def publish_snapshot(self, payload):
        self.published.append(payload)
        return {"accepted": True, "host_epoch": payload["host_epoch"], "snapshot_revision": payload["snapshot_revision"]}

    def send_focus_result(self, payload):
        self.results.append(payload)

    def poll(self):
        return None

    def close(self):
        self.connected = False

    def clear_pending_focus(self):
        self.pending_focus = None


class ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class RecoveringUsb(FakeUsb):
    def __init__(self, *, unavailable_attempts: int = 0):
        super().__init__()
        self.session_id = "session-0"
        self.connect_attempts = 0
        self.unavailable_attempts = unavailable_attempts
        self.fail_poll = False
        self.connect_calls: list[str] = []
        self.poll_calls = 0
        self.close_calls = 0

    def connect(self):
        self.connect_attempts += 1
        self.connect_calls.append(self.session_id)
        if self.unavailable_attempts:
            self.unavailable_attempts -= 1
            self.connected = False
            raise RuntimeError("CDC endpoint has not re-enumerated")
        self.session_id = f"session-{self.connect_attempts}"
        self.connected = True
        return {"hello": {"device_id": "paired"}}

    def poll(self):
        self.poll_calls += 1
        if self.fail_poll:
            self.fail_poll = False
            raise RuntimeError("stale descriptor")
        return None

    def close(self):
        self.close_calls += 1
        super().close()


class RecordingEventStream:
    def __init__(self):
        self.mode = "push"
        self.typed_event = None
        self.close_calls = 0
        self.probe_calls = 0

    def close(self):
        self.close_calls += 1
        self.mode = "closed"

    def probe(self, **_kwargs):
        self.probe_calls += 1
        self.mode = "push"
        return self.mode

    def poll(self):
        return None
class FakeCodexCollector:
    def __init__(self, view: CodexView | None = None):
        self._view = view or CodexView(source_state="current", primary=11)
        self.collect_calls = 0
        self.poll = False

    def collect(self):
        self.collect_calls += 1
        return CodexResult(
            self._view, (), 1000, 0, ChildExit("terminated", 0, None), Redaction()
        )

    def should_poll(self, now=None):
        return self.poll


class PluginLifecycleTests(unittest.TestCase):
    def test_manifest_is_startup_only_and_guard_is_flock_based(self):
        manifest = tomllib.loads((ROOT / "host/herdr_keypad/herdr-plugin.toml").read_text())
        self.assertEqual(manifest["id"], "herdr-keypad")
        self.assertEqual(len(manifest["startup"]), 1)
        self.assertNotIn("actions", manifest)
        self.assertNotIn("panes", manifest)
        script = (ROOT / "host/herdr_keypad/scripts/ensure-bridge.sh").read_text()
        self.assertIn("flock -n 9", script)
        self.assertIn("flock -u 9", script)
        self.assertIn("HERDR_KEYPAD_EXCLUSIVE_LOCK=1", script)
        self.assertIn("exit 125", script)
        self.assertIn("stop-for-acceptance", script)
        self.assertIn('set +e', script)
        self.assertIn('exit "$wrapped_status"', script)
        self.assertLess(script.index("flock -u 9"), script.index('ensure-bridge.sh" >/dev/null'))
        self.assertNotIn("pkill", script)

    def test_run_exclusive_retains_lock_and_preserves_status(self):
        guard = ROOT / "host/herdr_keypad/scripts/ensure-bridge.sh"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            fake_python = root / "herdr_keypad_fake"
            fake_python.write_text(
                "#!/usr/bin/env python3\n"
                "import signal, sys, time\n"
                "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\n"
                "while True: time.sleep(1)\n",
                encoding="ascii",
            )
            fake_python.chmod(0o755)
            environment = os.environ.copy()
            environment.update({
                "XDG_RUNTIME_DIR": str(runtime),
                "HERDR_KEYPAD_PYTHON": str(fake_python),
            })
            environment.pop("HERDR_KEYPAD_PIDFILE", None)
            launcher = subprocess.Popen(
                ["sh", "-c", f"{guard} >/dev/null 2>&1 &"],
                cwd=ROOT,
                env=environment,
            )
            launcher.wait(timeout=5)
            pidfile = runtime / "herdr-keypad" / "bridge.pid"
            lock = runtime / "herdr-keypad" / "bridge.lock"
            deadline = time.monotonic() + 5
            while not pidfile.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(pidfile.exists())
            ready = root / "wrapped-ready"
            wrapped = subprocess.Popen(
                [
                    str(guard), "run-exclusive", "--", "sh", "-c",
                    f"flock -n 9 && touch {ready}; sleep 0.3; exit 37",
                ],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                time.sleep(0.1)
                probe = subprocess.run(
                    ["flock", "-n", str(lock), "sh", "-c", "exit 0"],
                    cwd=ROOT,
                    env=environment,
                )
                self.assertNotEqual(probe.returncode, 0)
                self.assertEqual(wrapped.wait(timeout=8), 37)
                self.assertTrue(pidfile.exists())
            finally:
                if pidfile.exists():
                    try:
                        os.kill(int(pidfile.read_text(encoding="ascii")), 15)
                    except (FileNotFoundError, ProcessLookupError, ValueError):
                        pass
                try:
                    wrapped.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    wrapped.kill()
                    wrapped.communicate()
                if wrapped.poll() is None:
                    wrapped.kill()

    def test_subscribe_uses_installed_typed_public_schema(self):
        calls = []
        client = HerdrClient(requester=lambda method, params: calls.append((method, params)) or {"subscribed": True})
        subscriptions = ({"type": "pane.created"}, {"type": "pane.agent_status_changed", "pane_id": "pane-1"})
        client.subscribe(subscriptions=subscriptions)
        self.assertEqual(
            calls,
            [
                (
                    "events.subscribe",
                    {"subscriptions": [dict(subscription) for subscription in subscriptions]},
                )
            ],
        )
        with self.assertRaises(HerdrError):
            client.subscribe(subscriptions=({"type": "*"},))
        with self.assertRaises(HerdrError):
            client.subscribe(subscriptions=())

    def test_two_bootstrap_triggers_have_one_host_epoch_and_one_snapshot_owner(self):
        fake = FakeHerdr()
        client = HerdrClient(requester=fake.request)
        usb = FakeUsb()
        projection = InboxProjection(host_epoch="epoch-fixed")
        bridge = PermanentBridge(client, usb, projection)
        first = bridge.bootstrap()
        second = bridge.bootstrap()
        self.assertEqual(first.host_epoch, second.host_epoch)
        self.assertEqual(usb.published[-1]["snapshot_revision"], 1)
        self.assertEqual([name for name, _ in fake.calls].count("events.subscribe"), 2)
        subscribe_calls = [params for name, params in fake.calls if name == "events.subscribe"]
        expected_subscriptions = [{"type": event_type} for event_type in PermanentBridge.GLOBAL_EVENT_TYPES]
        expected_subscriptions.extend(
            {"type": PermanentBridge.STATUS_EVENT_TYPE, "pane_id": pane_id}
            for pane_id in ("pane-1", "pane-2", "pane-3")
        )
        self.assertEqual(
            subscribe_calls,
            [{"subscriptions": expected_subscriptions}] * 2,
        )
        self.assertEqual(len(usb.published), 1)
    def test_codex_only_refresh_preserves_agents_bindings_and_focus_allowlist(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        codex = FakeCodexCollector()
        bridge = PermanentBridge(
            HerdrClient(requester=fake.request),
            usb,
            InboxProjection(host_epoch="epoch-fixed"),
            codex_collector=codex,
        )
        bridge.bootstrap()
        before_agents = tuple(usb.published[-1]["agents"])
        before_binding = bridge.projection.binding(0)
        self.assertEqual(bridge.refresh_codex().source_state, "current")
        self.assertEqual(tuple(usb.published[-1]["agents"]), before_agents)
        self.assertEqual(bridge.projection.binding(0), before_binding)
        codex._view = CodexView(source_state="auth_required")
        bridge.refresh_codex()
        usb.pending_focus = {"action_id": "pending-focus"}
        bridge.refresh_codex()
        self.assertEqual(usb.pending_focus, {"action_id": "pending-focus"})
        self.assertEqual(tuple(usb.published[-1]["agents"]), before_agents)
        self.assertEqual(bridge.projection.binding(0), before_binding)
        self.assertEqual(usb.published[-1]["diagnostics"]["codex_status"], "auth_required")
        self.assertEqual(usb.published[-1]["diagnostics"]["link_status"], "current")

    def test_link_loss_does_not_relabel_codex_authentication(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        codex = FakeCodexCollector(CodexView(source_state="auth_required"))
        bridge = PermanentBridge(
            HerdrClient(requester=fake.request),
            usb,
            InboxProjection(host_epoch="epoch-fixed"),
            codex_collector=codex,
        )
        bridge.bootstrap()
        usb.fail_poll = True if hasattr(usb, "fail_poll") else False
        bridge._disconnect("offline", bridge._clock())
        self.assertEqual(bridge.codex_view.source_state, "auth_required")
        self.assertNotEqual(bridge.codex_view.source_state, "host_offline")

    def test_contract_drift_blocks_startup_before_usb(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts/phase2").mkdir(parents=True)
            (root / "artifacts/phase2/herdr-contract.json").write_text('{"classification":"drifted"}')
            (root / "artifacts/phase2/herdr-focus-effects.json").write_text('{}')
            bridge = PermanentBridge(HerdrClient(requester=fake.request), usb, InboxProjection(), contract_root=root)
            with self.assertRaises(V2ProtocolError):
                bridge.bootstrap()
            self.assertFalse(usb.connected)
            self.assertEqual(fake.calls, [])

    def test_focus_path_is_exact_and_only_calls_public_focus(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        bridge = PermanentBridge(HerdrClient(requester=fake.request), usb, InboxProjection(host_epoch="epoch"))
        bridge.bootstrap()
        entry = bridge.projection.current.entries[0]
        binding = bridge.projection.binding(0)
        payload = {
            "action_id": "action-1",
            "host_epoch": binding.host_epoch,
            "snapshot_revision": binding.snapshot_revision,
            "slot": 0,
            "entry_id": entry.entry_id,
            **binding.identity.as_payload(),
        }
        frame = protocol.new_v2_frame("focus_intent", "boot", "session", 1, payload)
        outcome = bridge.handle_frame(frame)
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(usb.results[-1]["outcome"], "accepted")
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 1)
        self.assertNotIn("settle", [name for name, _ in fake.calls])
        self.assertNotIn("unread", [name for name, _ in fake.calls])
        self.assertNotIn("clear", [name for name, _ in fake.calls])

    def test_not_ready_focus_is_processed_once_after_matching_snapshot_ack(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        bridge = PermanentBridge(HerdrClient(requester=fake.request), usb, InboxProjection(host_epoch="epoch"))
        snapshot = bridge.bootstrap()
        binding = bridge.projection.binding(0)
        payload = {
            "action_id": "during-ack",
            "host_epoch": binding.host_epoch,
            "snapshot_revision": binding.snapshot_revision,
            "slot": binding.slot,
            "entry_id": binding.entry_id,
            **binding.identity.as_payload(),
        }
        frame = protocol.new_v2_frame("focus_intent", "boot", usb.session_id, 1, payload)

        bridge.ready = False
        self.assertIsNone(bridge.handle_frame(frame))
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 0)
        bridge._publish_snapshot(snapshot)
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 1)
        self.assertEqual(usb.results[-1]["outcome"], "accepted")

        bridge._publish_snapshot(snapshot)
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 1)

    def test_not_ready_focus_survives_generation_change_when_exact_identity_is_alive(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        bridge = PermanentBridge(HerdrClient(requester=fake.request), usb, InboxProjection(host_epoch="epoch"))
        bridge.bootstrap()
        binding = bridge.projection.binding(0)
        payload = {
            "action_id": "during-refresh",
            "host_epoch": binding.host_epoch,
            "snapshot_revision": binding.snapshot_revision,
            "slot": binding.slot,
            "entry_id": binding.entry_id,
            **binding.identity.as_payload(),
        }
        bridge.ready = False
        bridge.handle_frame(protocol.new_v2_frame("focus_intent", "boot", usb.session_id, 1, payload))

        fake.rows[0] = {**fake.rows[0], "revision": 2, "state_change_seq": 5}
        changed = bridge.projection.bootstrap(bridge.client)
        bridge._publish_snapshot(changed)
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 1)
        self.assertEqual(usb.results[-1]["outcome"], "accepted")

    def test_current_refresh_keeps_ready_state_and_pending_focus(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        bridge = PermanentBridge(HerdrClient(requester=fake.request), usb, InboxProjection(host_epoch="epoch"))
        bridge.bootstrap()
        usb.pending_focus = {"action_id": "already-read-from-device"}

        fake.rows[0] = {**fake.rows[0], "revision": 2, "state_change_seq": 5}
        changed = bridge.projection.bootstrap(bridge.client)
        bridge._publish_snapshot(changed)

        self.assertTrue(bridge.ready)
        self.assertEqual(usb.pending_focus, {"action_id": "already-read-from-device"})

    def test_revision_only_poll_reuses_generation_and_focuses_exact_target(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        bridge = PermanentBridge(HerdrClient(requester=fake.request), usb, InboxProjection(host_epoch="epoch"))
        initial = bridge.bootstrap()
        binding = bridge.projection.binding(0)
        fake.rows[0] = {**fake.rows[0], "revision": 99}

        refreshed = bridge._publish_refresh()
        self.assertIs(refreshed, initial)
        self.assertEqual(len(usb.published), 1)
        self.assertEqual(bridge.projection.binding(0), binding)

        payload = {
            "action_id": "revision-only",
            "host_epoch": binding.host_epoch,
            "snapshot_revision": binding.snapshot_revision,
            "slot": binding.slot,
            "entry_id": binding.entry_id,
            **binding.identity.as_payload(),
        }
        outcome = bridge.handle_frame(protocol.new_v2_frame("focus_intent", "boot", "session", 1, payload))
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(usb.results[-1]["outcome"], "accepted")
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 1)

    def test_material_projection_drift_does_not_block_live_exact_target(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        bridge = PermanentBridge(HerdrClient(requester=fake.request), usb, InboxProjection(host_epoch="epoch"))
        bridge.bootstrap()
        displayed = bridge.projection.binding(0)
        fake.rows[0] = {**fake.rows[0], "revision": 2, "state_change_seq": 5}

        payload = {
            "action_id": "action-during-drift",
            "host_epoch": displayed.host_epoch,
            "snapshot_revision": displayed.snapshot_revision,
            "slot": displayed.slot,
            "entry_id": displayed.entry_id,
            **displayed.identity.as_payload(),
        }
        outcome = bridge.handle_frame(
            protocol.new_v2_frame("focus_intent", "boot", "session", 1, payload)
        )

        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(usb.results[-1]["outcome"], "accepted")
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 1)
    def test_alive_bridge_reconnects_and_acks_complete_snapshot_before_ready(self):
        clock = ManualClock()
        fake = FakeHerdr()
        usb = RecoveringUsb()
        bridge = PermanentBridge(
            HerdrClient(requester=fake.request),
            usb,
            InboxProjection(host_epoch="epoch-fixed"),
        )
        bridge._clock = clock
        bridge.bootstrap()
        old_session = usb.session_id
        old_epoch = bridge.projection.current.host_epoch
        old_revision = bridge.projection.current.snapshot_revision
        usb.fail_poll = True

        bridge.run_once()
        self.assertFalse(bridge.ready)
        self.assertFalse(usb.connected)
        self.assertEqual(usb.connect_attempts, 1)

        clock.advance(PermanentBridge.RECONNECT_INITIAL_DELAY_SECONDS)
        bridge.run_once()
        self.assertTrue(bridge.ready)
        self.assertTrue(usb.connected)
        self.assertNotEqual(usb.session_id, old_session)
        self.assertEqual(bridge.projection.current.snapshot_revision, old_revision)
        self.assertEqual(bridge.projection.current.host_epoch, old_epoch)
        self.assertEqual([agent["slot"] for agent in usb.published[-1]["agents"]], [0, 1, 2])
        self.assertEqual(usb.published[-1]["host_epoch"], old_epoch)
        self.assertEqual(
            usb.published[-1]["snapshot_revision"],
            bridge.projection.current.snapshot_revision,
        )

        binding = bridge.projection.binding(0)
        payload = {
            "action_id": "fresh-after-recovery",
            "host_epoch": binding.host_epoch,
            "snapshot_revision": binding.snapshot_revision,
            "slot": binding.slot,
            "entry_id": binding.entry_id,
            **binding.identity.as_payload(),
        }
        outcome = bridge.handle_frame(protocol.new_v2_frame("focus_intent", "boot", usb.session_id, 1, payload))
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 1)

    def test_recovery_rebuilds_event_stream_and_discards_old_focus_intake(self):
        clock = ManualClock()
        fake = FakeHerdr()
        streams: list[RecordingEventStream] = []

        def make_stream():
            stream = RecordingEventStream()
            streams.append(stream)
            return stream

        client = HerdrClient(requester=fake.request)
        client.event_stream_factory = make_stream
        usb = RecoveringUsb()
        bridge = PermanentBridge(client, usb, InboxProjection(host_epoch="epoch-fixed"), clock=clock)
        bridge.bootstrap()
        self.assertEqual(len(streams), 1)
        binding = bridge.projection.binding(0)
        payload = {
            "action_id": "stale-before-disconnect",
            "host_epoch": binding.host_epoch,
            "snapshot_revision": binding.snapshot_revision,
            "slot": binding.slot,
            "entry_id": binding.entry_id,
            **binding.identity.as_payload(),
        }
        bridge.ready = False
        bridge.handle_frame(protocol.new_v2_frame("focus_intent", "boot", usb.session_id, 1, payload))
        self.assertEqual(len(bridge._deferred_focus), 1)

        usb.fail_poll = True
        bridge.ready = True
        bridge.run_once()
        self.assertEqual(streams[0].close_calls, 1)
        self.assertEqual(bridge._deferred_focus, [])

        clock.advance(PermanentBridge.RECONNECT_INITIAL_DELAY_SECONDS)
        bridge.run_once()
        self.assertEqual(len(streams), 2)
        self.assertGreaterEqual(streams[1].probe_calls, 1)
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 0)


    def test_usb_reconnect_backoff_is_single_attempt_and_capped(self):
        clock = ManualClock()
        usb = RecoveringUsb()
        bridge = PermanentBridge(
            HerdrClient(requester=FakeHerdr().request),
            usb,
            InboxProjection(host_epoch="epoch-fixed"),
        )
        bridge._clock = clock
        bridge.bootstrap()
        usb.fail_poll = True
        usb.unavailable_attempts = 2
        bridge.run_once()

        initial_delay = 0.5
        clock.advance(initial_delay - 0.001)
        bridge.run_once()
        self.assertEqual(usb.connect_attempts, 1)
        clock.advance(0.001)
        bridge.run_once()
        self.assertEqual(usb.connect_attempts, 2)
        bridge.run_once()
        self.assertEqual(usb.connect_attempts, 2)
        clock.advance(initial_delay * 2)
        bridge.run_once()
        self.assertEqual(usb.connect_attempts, 3)
        self.assertFalse(bridge.ready)

        clock.advance(initial_delay * 4)
        bridge.run_once()
        self.assertEqual(usb.connect_attempts, 4)
        self.assertTrue(bridge.ready)
        self.assertEqual(bridge._reconnect_delay, initial_delay)
        self.assertIsNone(bridge._reconnect_due)




    def test_run_fences_and_reconnects_after_transient_usb_error(self):
        bridge = object.__new__(PermanentBridge)
        disconnects: list[tuple[str, float]] = []
        closed: list[bool] = []
        marked: list[str] = []

        def fail_once():
            raise UsbSessionError("closed", "transient USB failure")

        bridge.run_once = fail_once
        bridge._clock = lambda: 12.5
        bridge._disconnect = lambda reason, now: disconnects.append((reason, now))
        bridge._mark_unavailable = lambda reason: marked.append(reason)
        bridge.usb = SimpleNamespace(close=lambda: closed.append(True))

        with patch("herdr_keypad.bridge.time.sleep", side_effect=KeyboardInterrupt):
            bridge.run(bootstrapped=True)

        self.assertEqual(disconnects, [("offline", 12.5)])
        self.assertEqual(marked, ["offline"])
        self.assertEqual(closed, [True])

    def test_run_reconnects_after_initial_usb_bootstrap_failure(self):
        clock = ManualClock()
        usb = RecoveringUsb(unavailable_attempts=1)
        bridge = PermanentBridge(
            HerdrClient(requester=FakeHerdr().request),
            usb,
            InboxProjection(host_epoch="epoch-bootstrap-recovery"),
        )
        bridge._clock = clock

        def advance_until_published(_interval: float) -> None:
            if usb.published:
                raise KeyboardInterrupt
            clock.advance(0.5)

        with patch("herdr_keypad.bridge.time.sleep", side_effect=advance_until_published):
            bridge.run()


        self.assertEqual(usb.connect_attempts, 2)
        self.assertEqual(len(usb.published), 1)
        self.assertTrue(bridge.last_snapshot_ack["accepted"])


class ExactUsbSessionTests(unittest.TestCase):
    def test_composite_discovery_requires_measured_cdc_tuple(self):
        class Port:
            def __init__(self, device: str, serial_number: str, interface: str):
                self.device = device
                self.vid = 0x303A
                self.pid = 0x1001
                self.serial_number = serial_number
                self.location = f"{device}:1.1"
                self.manufacturer = "Espressif"
                self.product = "USB composite CDC + keyboard"
                self.interface = interface

        candidates = enumerate_candidates(
            [
                Port("/dev/ttyACM9", "lookalike", "if01"),
                Port("/dev/ttyACM0", EXPECTED_SERIAL, "if01"),
                Port("/dev/ttyACM1", EXPECTED_SERIAL, "if00"),
            ]
        )
        self.assertEqual([candidate.device for candidate in candidates], ["/dev/ttyACM0"])
        self.assertEqual(candidates[0].interface, EXPECTED_CDC_INTERFACE)

    def test_pyserial_hex_serial_without_separators_matches_measured_pair(self):
        class Port:
            device = "/dev/ttyACM0"
            vid = 0x303A
            pid = 0x1001
            serial_number = "8CBFEA0DCBFC"
            location = "1-1:1.1"
            manufacturer = "Espressif"
            product = "USB composite CDC + keyboard"
            interface = "TinyUSB CDC"

        candidates = enumerate_candidates([Port()])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].serial_number, EXPECTED_SERIAL)

    def test_wrong_composite_descriptor_cannot_reach_application_hello(self):
        class WrongSerialPort(self.Port):
            serial_number = "lookalike"

        raw = self.Raw()
        with tempfile.TemporaryDirectory() as directory:
            binding_path = Path(directory) / "binding.json"
            PairingStore(binding_path).save(PairingBinding("paired-device", 1, "phase1-bringup"))
            session = UsbDeviceSession(
                binding_path,
                ports=[WrongSerialPort()],
                opener=lambda _candidate: raw,
                timeout=0.1,
            )
            with self.assertRaises(UsbSessionError) as context:
                session.connect()
            self.assertEqual(context.exception.code, "zero")
            self.assertFalse(raw.outbound)

    def test_composite_udev_rule_matches_only_measured_cdc_interface(self):
        rule = (ROOT / "host/udev/99-herdr-keypad.rules").read_text(encoding="ascii")
        self.assertIn('SUBSYSTEM=="tty"', rule)
        self.assertIn('ATTRS{idVendor}=="303a"', rule)
        self.assertIn('ATTRS{idProduct}=="1001"', rule)
        self.assertIn(f'ENV{{ID_SERIAL_SHORT}}=="{EXPECTED_SERIAL}"', rule)
        self.assertIn(f'ENV{{ID_USB_INTERFACE_NUM}}=="{EXPECTED_CDC_INTERFACE}"', rule)
        self.assertNotIn('ENV{ID_USB_INTERFACE_NUM}=="00"', rule)
        self.assertNotIn('KERNEL=="ttyACM*"', rule)
        self.assertNotIn('MODE="0666"', rule)

    def test_v2_response_session_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            binding_path = Path(directory) / "binding.json"
            PairingStore(binding_path).save(PairingBinding("paired-device", 1, "phase1-bringup"))
            raw = self.Raw()
            session = UsbDeviceSession(binding_path, ports=[self.Port()], opener=lambda _candidate: raw, timeout=0.1)
            session.connect()
            raw.inbound.insert(
                0,
                protocol.encode_v2_frame(
                    protocol.new_v2_frame(
                        "snapshot_ack",
                        "wrong-boot",
                        "stale-session",
                        2,
                        {
                            "accepted": True,
                            "host_epoch": "epoch",
                            "snapshot_revision": 1,
                            "source_status": "empty",
                            "reason": "committed",
                        },
                        2,
                    )
                ),
            )
            with self.assertRaises(UsbSessionError) as context:
                session.publish_snapshot(
                    _projection_payload(InboxProjection(host_epoch="epoch").refresh([], source_status="empty"))
                )
            self.assertEqual(context.exception.code, "session_mismatch")
            session.close()
    class Port:
        device = "/dev/fake-keypad"
        vid = 0x303A
        pid = 0x1001
        serial_number = EXPECTED_SERIAL
        location = "1-1:1.1"
        manufacturer = "Espressif"
        product = "USB composite CDC + keyboard"
        interface = "if01"
    def test_reenumerated_usb_keeps_exact_stored_device_identity(self):
        class Port:
            def __init__(self, device: str):
                self.device = device
                self.vid = 0x303A
                self.pid = 0x1001
                self.serial_number = EXPECTED_SERIAL
                self.location = f"{device}:1.1"
                self.manufacturer = "Espressif"
                self.product = "USB composite CDC + keyboard"
                self.interface = "if01"

        with tempfile.TemporaryDirectory() as directory:
            binding_path = Path(directory) / "binding.json"
            PairingStore(binding_path).save(PairingBinding("paired-device", 1, "phase1-bringup"))
            raws = {
                "/dev/ttyACM-wrong": self.Raw(),
                "/dev/ttyACM-reenumerated": self.Raw(),
            }
            raws["/dev/ttyACM-wrong"].device_id = "lookalike"
            raws["/dev/ttyACM-reenumerated"].device_id = "paired-device"
            session = UsbDeviceSession(
                binding_path,
                ports=[Port("/dev/ttyACM-wrong"), Port("/dev/ttyACM-reenumerated")],
                opener=lambda candidate: raws[candidate.device],
                timeout=0.1,
            )
            hello = session.connect()
            self.assertEqual(hello["hello"]["device_id"], "paired-device")
            self.assertEqual(session.candidate.device, "/dev/ttyACM-reenumerated")
            self.assertTrue(raws["/dev/ttyACM-wrong"].closed)
            session.close()
    def test_fresh_hello_rejects_stale_firmware_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            binding_path = Path(directory) / "binding.json"
            PairingStore(binding_path).save(PairingBinding("paired-device", 1, "phase1-bringup"))
            raw = self.Raw()
            raw.firmware = "stale-firmware"
            session = UsbDeviceSession(binding_path, ports=[self.Port()], opener=lambda _candidate: raw, timeout=0.1)
            with self.assertRaises(UsbSessionError) as context:
                session.connect()
            self.assertEqual(context.exception.code, "firmware_mismatch")
            self.assertTrue(raw.closed)


    class Raw:
        def __init__(self):
            self.outbound: list[bytes] = []
            self.inbound: list[bytes] = []
            self.closed = False
            self.inject_focus = False

        def write(self, data: bytes) -> int:
            self.outbound.append(data)
            parsed = protocol.classify_line(data)
            if parsed.accepted and parsed.frame and parsed.frame["type"] == "hello":
                request = parsed.frame
                payload = {"accepted": True, "device_id": getattr(self, "device_id", "paired-device"), "firmware": getattr(self, "firmware", "phase1-bringup"), "protocol": 1}
                self.inbound.append(protocol.encode_frame(protocol.new_frame("hello_ack", "device-boot", request["session_id"], 1, payload, request["seq"])))
            else:
                parsed_v2 = protocol.classify_v2_line(data)
                if parsed_v2.accepted and parsed_v2.frame and parsed_v2.frame["type"] == "agent_snapshot":
                    request = parsed_v2.frame
                    p = request["payload"]
                    ack = {"accepted": True, "host_epoch": p["host_epoch"], "snapshot_revision": p["snapshot_revision"], "source_status": p["source_status"], "reason": "committed"}
                    ack_seq = 3 if self.inject_focus else 2
                    if self.inject_focus:
                        entry = p["agents"][0]
                        intent = {key: entry[key] for key in ("pane_id", "terminal_id", "agent_session", "source_revision")}
                        intent.update({"action_id": "queued", "host_epoch": p["host_epoch"], "snapshot_revision": p["snapshot_revision"], "slot": 0, "entry_id": entry["entry_id"]})
                        self.inbound.append(protocol.encode_v2_frame(protocol.new_v2_frame("focus_intent", "device-boot", request["session_id"], 2, intent)))
                    self.inbound.append(protocol.encode_v2_frame(protocol.new_v2_frame("snapshot_ack", "device-boot", request["session_id"], ack_seq, ack, request["seq"])))
            return len(data)

        def readline(self, *_args):
            return self.inbound.pop(0) if self.inbound else b""

        def close(self):
            self.closed = True

    def test_exact_identity_and_v2_snapshot_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            binding_path = Path(directory) / "binding.json"
            PairingStore(binding_path).save(PairingBinding("paired-device", 1, "phase1-bringup"))
            raw = self.Raw()
            session = UsbDeviceSession(binding_path, ports=[self.Port()], opener=lambda _candidate: raw, timeout=0.1)
            hello = session.connect()
            self.assertEqual(hello["hello"]["device_id"], "paired-device")
            self.assertEqual(hello["hello"]["boot_id"], "device-boot")
            self.assertTrue(hello["hello"]["session_id"])
            fixture = InboxProjection(host_epoch="epoch")
            payload = _projection_payload(fixture.refresh([], source_status="empty"))
            ack = session.publish_snapshot(payload)
            self.assertTrue(ack["accepted"])
            self.assertEqual(len(raw.outbound), 2)
            session.close()
            self.assertTrue(raw.closed)

    def test_interleaved_focus_is_queued_once_and_cleared_on_close(self):
        with tempfile.TemporaryDirectory() as directory:
            binding_path = Path(directory) / "binding.json"
            PairingStore(binding_path).save(PairingBinding("paired-device", 1, "phase1-bringup"))
            raw = self.Raw()
            raw.inject_focus = True
            session = UsbDeviceSession(binding_path, ports=[self.Port()], opener=lambda _candidate: raw, timeout=0.1)
            session.connect()
            fixture = InboxProjection(host_epoch="epoch")
            snapshot = fixture.refresh([row("p1", "0", 1)])
            session.publish_snapshot(_projection_payload(snapshot))
            self.assertEqual(session.pending_focus_count, 1)
            self.assertEqual(session.poll()["type"], "focus_intent")
            self.assertEqual(session.pending_focus_count, 0)
            session.close()
            self.assertEqual(session.pending_focus_count, 0)

class HerdrEventContractTests(unittest.TestCase):
    class Socket:
        def __init__(self, *lines: bytes):
            self.lines = list(lines)
            self.sent = []
            self.closed = False

        def settimeout(self, _timeout):
            return None

        def sendall(self, payload):
            self.sent.append(payload)

        def recv(self, _size):
            return self.lines.pop(0) if self.lines else b""

        def close(self):
            self.closed = True

    def test_ack_plus_typed_event_admits_push_and_retains_invalidation(self):
        sock = self.Socket(
            b'{"jsonrpc":"2.0","id":"1","result":{"subscribed":true}}\n',
            b'{"event":"pane.updated","data":{"pane_id":"partial"}}\n',
        )
        stream = __import__("herdr_keypad.herdr", fromlist=["HerdrEventStream"]).HerdrEventStream(
            HerdrClient(timeout=0.1), socket_factory=lambda: sock
        )
        self.assertEqual(stream.probe(deadline_seconds=1), "push")
        self.assertEqual(stream.poll()["event"], "pane.updated")
        self.assertEqual(json.loads(sock.sent[0])["method"], "events.subscribe")

    def test_ack_only_admits_push_without_waiting_for_first_event(self):
        sock = self.Socket(b'{"jsonrpc":"2.0","id":"1","result":{"subscribed":true}}\n')
        stream = __import__("herdr_keypad.herdr", fromlist=["HerdrEventStream"]).HerdrEventStream(
            HerdrClient(timeout=0.1), socket_factory=lambda: sock
        )
        self.assertEqual(stream.probe(deadline_seconds=1), "push")
        self.assertEqual(stream.reason, "subscribe_ack")
        self.assertTrue(stream.active)
    def test_idle_push_poll_does_not_drop_focus_ready_state(self):
        class IdleSocket(self.Socket):
            def recv(self, _size):
                if self.lines:
                    return self.lines.pop(0)
                raise TimeoutError()

        sock = IdleSocket(b'{"jsonrpc":"2.0","id":"1","result":{"subscribed":true}}\n')
        stream = __import__("herdr_keypad.herdr", fromlist=["HerdrEventStream"]).HerdrEventStream(
            HerdrClient(timeout=0.1), socket_factory=lambda: sock
        )
        self.assertEqual(stream.probe(deadline_seconds=1), "push")
        self.assertIsNone(stream.poll())
        self.assertEqual(stream.mode, "push")
        self.assertTrue(stream.active)


    def test_live_smoke_rejects_unbounded_window_before_device_access(self):
        self.assertEqual(main(["--smoke-live-sync", "4"]), 2)
        self.assertEqual(main(["--smoke-live-sync", "31"]), 2)

    def test_live_evidence_is_redacted_atomic_and_hash_reopenable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live-sync-smoke.json"
            fake = SimpleNamespace(invalidation_count=1, publication_count=2, ready_transitions=3, intake_mode="poll")
            projection = InboxProjection(host_epoch="epoch")
            initial = projection.refresh([row("p1", "0", 1)])
            changed = projection.refresh([row("p2", "0", 2)])
            write_live_sync_evidence(
                path,
                result="pass",
                duration_seconds=5,
                initial=initial,
                changed=changed,
                focus={"focused": True, "snapshot_revision": 2},
                metrics={"max_display_flush_us": 4, "minimum_free_heap": 5, "max_key_poll_gap_us": 6, "parser_high_water": 7, "queue_high_water": 8},
                bridge=fake,
            )
            data = json.loads(path.read_text())
            self.assertEqual(data["result"], "pass")
            self.assertEqual(len(data["initial_generation"]["slots"]), 3)
            self.assertEqual(len(data["changed_generation"]["slots"]), 3)
            self.assertNotIn("raw", json.dumps(data).lower())
            checksum = path.with_suffix(".sha256").read_text().split()[0]
            import hashlib
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checksum)

class Phase3PublicationReceiptTests(unittest.TestCase):
    def test_receipt_is_atomic_bounded_and_acknowledgement_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = root / "firmware.bin"
            firmware.write_bytes(b"current-firmware")
            receipt = root / "publication.json"
            usb = SimpleNamespace(
                device={"hello": {
                    "device_id": "device-1",
                    "firmware": "phase1-bringup",
                    "protocol": 1,
                    "boot_id": "boot-1",
                    "session_id": "session-1",
                }},
                candidate=SimpleNamespace(serial_number="SERIAL-1"),
            )
            bridge = SimpleNamespace(
                usb=usb,
                last_snapshot_ack={"accepted": True, "snapshot_revision": 9},
            )
            write_publication_receipt(receipt, firmware, bridge)
            record = json.loads(receipt.read_text(encoding="ascii"))
            self.assertEqual(record["kind"], "phase3-bridge-publication-receipt")
            self.assertEqual(record["hello"]["device_id"], "device-1")
            self.assertEqual(record["snapshot_ack"], {"accepted": True, "snapshot_revision": 9})
            self.assertEqual(len(record["binary_sha256"]), 64)
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(root.glob(".*.tmp-*")), [])

    def test_receipt_rejects_missing_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = root / "firmware.bin"
            firmware.write_bytes(b"current-firmware")
            bridge = SimpleNamespace(
                usb=SimpleNamespace(device={"hello": {}}, candidate=None),
                last_snapshot_ack=None,
            )
            with self.assertRaisesRegex(RuntimeError, "not acknowledged"):
                write_publication_receipt(root / "publication.json", firmware, bridge)


class Phase3ProtocolAdmissionTests(unittest.TestCase):
    def extended_payload(self):
        agents = []
        for slot in range(3):
            occupied = slot == 0
            agents.append({
                "slot": slot,
                "entry_id": f"entry-{slot}" if occupied else "",
                "title": "Agent" if occupied else "NO AGENT",
                "discriminator": "repo" if occupied else "NO WORKSPACE",
                "since": "1m" if occupied else "",
                "age": "0m" if occupied else "",
                "state": "working" if occupied else "empty",
                "pane_id": f"pane-{slot}" if occupied else "",
                "terminal_id": f"term-{slot}" if occupied else "",
                "agent_session": None,
                "source_revision": 1 if occupied else 0,
            })
        return {
            "host_epoch": "epoch",
            "snapshot_revision": 1,
            "source_status": "current",
            "agents": agents,
            "codex": {
                "source_state": "current",
                "primary": 0,
                "secondary": None,
                "reset_text": "RESET 5H 01:20",
                "observation_age": "AGE 0M",
                "reached_limit": None,
                "error_code": "",
            },
            "diagnostics": {
                "link_status": "current",
                "herdr_status": "current",
                "codex_status": "current",
                "sync_age": "AGE 0M",
                "codex_age": "AGE 0M",
                "firmware_version": "phase1",
                "protocol_version": 2,
                "bridge_version": "0.1.0",
                "device_suffix": "ABC123",
                "session_suffix": "DEF456",
                "revision_suffix": "000001",
                "error_code": "",
            },
        }

    def test_extended_snapshot_is_admitted_by_the_sole_codec(self):
        payload = self.extended_payload()
        frame = protocol.new_v2_frame("agent_snapshot", "boot", "session", 1, payload)
        self.assertEqual(frame["payload"]["codex"]["primary"], 0)
        self.assertEqual(frame["payload"]["codex"]["secondary"], None)
        self.assertEqual(protocol.validate_v2_payload("agent_snapshot", payload), payload)

    def test_null_and_zero_are_distinct_and_bounds_are_closed(self):
        payload = self.extended_payload()
        self.assertIsNone(payload["codex"]["secondary"])
        payload["codex"]["primary"] = 100
        protocol.validate_v2_payload("agent_snapshot", payload)
        payload["codex"]["primary"] = 101
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_v2_payload("agent_snapshot", payload)
        payload = self.extended_payload()
        payload["codex"]["unexpected"] = 1
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_v2_payload("agent_snapshot", payload)

        payload = self.extended_payload()
        payload["codex"]["reset_text"] = "R" * 32
        frame = protocol.new_v2_frame("agent_snapshot", "boot", "session", 1, payload)
        encoded = protocol.encode_v2_frame(frame)
        self.assertLessEqual(len(encoded), protocol.MAX_LINE_BYTES)
        payload["diagnostics"]["error_code"] = "E-2410"
        frame = protocol.new_v2_frame("agent_snapshot", "boot", "session", 1, payload)
        self.assertLessEqual(len(protocol.encode_v2_frame(frame)), protocol.MAX_LINE_BYTES)
