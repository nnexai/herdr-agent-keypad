from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import tomllib

from herdr_keypad.bridge import (
    PermanentBridge,
    V2ProtocolError,
    _projection_payload,
    make_snapshot,
    snapshot_frame,
    verify_contract_inputs,
)
from herdr_keypad.herdr import HerdrClient, HerdrError
from herdr_keypad.projection import InboxProjection
from herdr_keypad.usb import UsbDeviceSession
from phase1_bringup import protocol
from phase1_bringup.discovery import Candidate
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


class PluginLifecycleTests(unittest.TestCase):
    def test_manifest_is_startup_only_and_guard_is_flock_based(self):
        manifest = tomllib.loads((ROOT / "host/herdr_keypad/herdr-plugin.toml").read_text())
        self.assertEqual(manifest["id"], "herdr-keypad")
        self.assertEqual(len(manifest["startup"]), 1)
        self.assertNotIn("actions", manifest)
        self.assertNotIn("panes", manifest)
        script = (ROOT / "host/herdr_keypad/scripts/ensure-bridge.sh").read_text()
        self.assertIn("flock -n 9", script)
        self.assertIn("stop-for-acceptance", script)
        self.assertNotIn("pkill", script)

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
        self.assertEqual(usb.published[-1]["snapshot_revision"], 2)
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
        self.assertEqual(len(usb.published), 2)

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


class ExactUsbSessionTests(unittest.TestCase):
    class Port:
        device = "/dev/fake-keypad"
        vid = 0x303A
        pid = 0x1001
        serial_number = "usb-serial"
        location = "1-1"
        manufacturer = "Espressif"
        product = "USB JTAG"
        interface = "if00"

    class Raw:
        def __init__(self):
            self.outbound: list[bytes] = []
            self.inbound: list[bytes] = []
            self.closed = False

        def write(self, data: bytes) -> int:
            self.outbound.append(data)
            parsed = protocol.classify_line(data)
            if parsed.accepted and parsed.frame and parsed.frame["type"] == "hello":
                request = parsed.frame
                payload = {"accepted": True, "device_id": "paired-device", "firmware": "phase1-bringup", "protocol": 1}
                self.inbound.append(protocol.encode_frame(protocol.new_frame("hello_ack", "device-boot", request["session_id"], 1, payload, request["seq"])))
            else:
                parsed_v2 = protocol.classify_v2_line(data)
                if parsed_v2.accepted and parsed_v2.frame and parsed_v2.frame["type"] == "agent_snapshot":
                    request = parsed_v2.frame
                    p = request["payload"]
                    ack = {"accepted": True, "host_epoch": p["host_epoch"], "snapshot_revision": p["snapshot_revision"], "source_status": p["source_status"], "reason": "committed"}
                    self.inbound.append(protocol.encode_v2_frame(protocol.new_v2_frame("snapshot_ack", "device-boot", request["session_id"], 2, ack, request["seq"])))
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
            fixture = InboxProjection(host_epoch="epoch")
            payload = _projection_payload(fixture.refresh([], source_status="empty"))
            ack = session.publish_snapshot(payload)
            self.assertTrue(ack["accepted"])
            self.assertEqual(len(raw.outbound), 2)
            session.close()
            self.assertTrue(raw.closed)
