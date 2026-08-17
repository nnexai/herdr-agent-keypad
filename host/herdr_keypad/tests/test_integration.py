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
    write_live_sync_evidence,
)
from herdr_keypad.__main__ import main
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

    def test_not_ready_focus_is_discarded_when_snapshot_generation_changes(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        bridge = PermanentBridge(HerdrClient(requester=fake.request), usb, InboxProjection(host_epoch="epoch"))
        bridge.bootstrap()
        binding = bridge.projection.binding(0)
        payload = {
            "action_id": "stale-during-ack",
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
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 0)
        self.assertEqual(usb.results, [])

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

    def test_material_projection_drift_rebinds_before_fresh_retry(self):
        fake = FakeHerdr()
        usb = FakeUsb()
        bridge = PermanentBridge(HerdrClient(requester=fake.request), usb, InboxProjection(host_epoch="epoch"))
        bridge.bootstrap()
        stale = bridge.projection.binding(0)
        fake.rows[0] = {**fake.rows[0], "revision": 2, "state_change_seq": 5}

        stale_payload = {
            "action_id": "action-stale",
            "host_epoch": stale.host_epoch,
            "snapshot_revision": stale.snapshot_revision,
            "slot": stale.slot,
            "entry_id": stale.entry_id,
            **stale.identity.as_payload(),
        }
        stale_outcome = bridge.handle_frame(protocol.new_v2_frame("focus_intent", "boot", "session", 1, stale_payload))
        self.assertEqual(stale_outcome.status, "source_revision_changed")
        self.assertEqual(usb.results[-1]["outcome"], "stale_target")
        self.assertEqual(usb.published[-1]["snapshot_revision"], 2)
        self.assertEqual(usb.published[-1]["agents"][0]["source_revision"], 2)
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 0)

        fresh = bridge.projection.binding(0)
        fresh_payload = {
            "action_id": "action-fresh",
            "host_epoch": fresh.host_epoch,
            "snapshot_revision": fresh.snapshot_revision,
            "slot": fresh.slot,
            "entry_id": fresh.entry_id,
            **fresh.identity.as_payload(),
        }
        fresh_outcome = bridge.handle_frame(protocol.new_v2_frame("focus_intent", "boot", "session", 2, fresh_payload))
        self.assertEqual(fresh_outcome.status, "accepted")
        self.assertEqual(usb.results[-1]["outcome"], "accepted")
        self.assertEqual([name for name, _ in fake.calls].count("agent.focus"), 1)


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
            self.inject_focus = False

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
            b'{"jsonrpc":"2.0","id":1,"result":{"subscribed":true}}\n',
            b'{"event":"pane.updated","data":{"pane_id":"partial"}}\n',
        )
        stream = __import__("herdr_keypad.herdr", fromlist=["HerdrEventStream"]).HerdrEventStream(
            HerdrClient(timeout=0.1), socket_factory=lambda: sock
        )
        self.assertEqual(stream.probe(deadline_seconds=1), "push")
        self.assertEqual(stream.poll()["event"], "pane.updated")
        self.assertEqual(json.loads(sock.sent[0])["method"], "events.subscribe")

    def test_ack_only_falls_back_to_poll(self):
        sock = self.Socket(b'{"jsonrpc":"2.0","id":1,"result":{"subscribed":true}}\n')
        stream = __import__("herdr_keypad.herdr", fromlist=["HerdrEventStream"]).HerdrEventStream(
            HerdrClient(timeout=0.1), socket_factory=lambda: sock
        )
        self.assertEqual(stream.probe(deadline_seconds=1), "poll")
        self.assertEqual(stream.reason, "ack_without_typed_event")

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
            checksum = path.with_name(path.name + ".sha256").read_text().split()[0]
            import hashlib
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checksum)

