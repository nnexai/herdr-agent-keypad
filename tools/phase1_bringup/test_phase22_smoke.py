from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import patch
import pytest

import phase1_bringup.evidence as evidence_module
import phase1_bringup.phase22_smoke as smoke

from phase1_bringup.phase22_smoke import (
    FENCES,
    GRAMMARS,
    STATES,
    THEMES,
    DeviceSession,
    SmokeEvidence,
    canonical_payload,
    encode_frame,
    fnv1a64,
    snapshot_payload,
)
from phase1_bringup.protocol import PAYLOAD_KEYS
from phase1_bringup.serial_link import SerialLinkError


def test_frame_digest_matches_payload_bytes() -> None:
    payload = {"source_status": "current", "snapshot_revision": 4}
    frame = json.loads(encode_frame("agent_snapshot", "boot", "session", 1, payload))
    assert frame["digest"] == fnv1a64(canonical_payload(payload))
    assert frame["v"] == 2
    assert frame["seq"] == 1


def test_snapshot_builder_covers_bounded_state_shape() -> None:
    snapshot = snapshot_payload(7, "test-epoch", states=("blocked", "finished", "empty"))
    assert snapshot["snapshot_revision"] == 7
    assert [agent["state"] for agent in snapshot["agents"]] == ["blocked", "finished", "empty"]
    assert snapshot["agents"][2]["entry_id"] == ""
    assert all(snapshot["agents"][index]["entry_id"] for index in (0, 1))


def test_snapshot_builder_uses_supplied_epoch_for_revision_restart() -> None:
    first_run = snapshot_payload(11, "phase22-run-a")
    second_run = snapshot_payload(1, "phase22-run-b")

    assert first_run["host_epoch"] == "phase22-run-a"
    assert second_run["host_epoch"] == "phase22-run-b"
    assert second_run["snapshot_revision"] == 1


def test_device_run_uses_one_fresh_epoch_per_process() -> None:
    recorded_runs: list[list[dict[str, object]]] = []
    discard_counts: list[int] = []

    class FakeSerial:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeSerial":
            return self

        def __exit__(self, *args) -> None:
            pass

    class RecordingSession:
        def __init__(self, connection) -> None:
            self.snapshots: list[dict[str, object]] = []
            recorded_runs.append(self.snapshots)
            discard_counts.append(0)

        def hello(self) -> dict[str, object]:
            return {"payload": {"accepted": True}}

        def request(self, frame_type: str, payload: dict[str, object], **kwargs) -> dict[str, object]:
            assert frame_type == "agent_snapshot"
            self.snapshots.append(payload)
            return {"payload": {"accepted": True}}

        def discard_pending_input(self) -> None:
            discard_counts[-1] += 1

        def wait_for_type(self, frame_type: str, timeout: float) -> dict[str, object]:
            raise TimeoutError("end setup-only replay")

    fake_serial = types.SimpleNamespace(Serial=FakeSerial)
    with (
        patch.dict(sys.modules, {"serial": fake_serial}),
        patch.object(smoke, "DeviceSession", RecordingSession),
        patch("builtins.input", return_value=""),
    ):
        for run in range(2):
            try:
                smoke._run_device("/dev/fake", Path(f"/tmp/unused-{run}.json"), SmokeEvidence.skeleton())
            except TimeoutError as exc:
                assert str(exc) == "end setup-only replay"
            else:
                raise AssertionError("setup-only replay must stop before physical prompts")

    assert [len(snapshots) for snapshots in recorded_runs] == [11, 11]
    epochs = [{snapshot["host_epoch"] for snapshot in snapshots} for snapshots in recorded_runs]
    assert all(len(epoch) == 1 for epoch in epochs)
    assert epochs[0] != epochs[1]
    assert [snapshot["snapshot_revision"] for snapshot in recorded_runs[1]] == list(range(1, 12))
    assert discard_counts == [1, 1]


def test_evidence_skeleton_is_complete_but_never_fabricates_passes(tmp_path) -> None:
    evidence = SmokeEvidence.skeleton()
    assert len(evidence.combinations) == len(THEMES) * len(GRAMMARS) == 16
    assert len(evidence.sightings) >= 5
    assert {item["result"] for item in evidence.combinations} == {"pending"}
    assert {item.result for item in evidence.sightings} == {"pending"}
    output = tmp_path / "evidence.json"
    evidence.write(output)
    loaded = json.loads(output.read_text())
    assert loaded["status"] == "pending"
    assert len(loaded["combinations"]) == 16

def test_evidence_pair_replacement_rolls_back_on_interruption(tmp_path) -> None:
    path = tmp_path / "evidence.json"
    original = SmokeEvidence.skeleton()
    original.write(path)
    old_content = path.read_bytes()
    old_digest = path.with_suffix(".json.sha256").read_bytes()
    replacement = SmokeEvidence.skeleton()
    replacement.machine_facts["replacement"] = True
    real_replace = evidence_module.os.replace
    calls = 0

    def interrupt_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated interruption")
        return real_replace(source, destination)

    with patch.object(evidence_module.os, "replace", side_effect=interrupt_second_replace):
        with pytest.raises(OSError):
            replacement.write(path)
    assert path.read_bytes() == old_content
    assert path.with_suffix(".json.sha256").read_bytes() == old_digest


def test_vocabulary_is_explicit() -> None:
    assert len(THEMES) == 4
    assert len(GRAMMARS) == 4
    assert len(STATES) == 7
    assert len(FENCES) == 3
    assert fnv1a64(b"") == "cbf29ce484222325"


class FragmentedConnection:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.reset_count = 0
        self.writes: list[bytes] = []

    def readline(self) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def reset_input_buffer(self) -> None:
        self.reset_count += 1
        self.chunks.clear()

    def feed(self, *chunks: bytes) -> None:
        self.chunks.extend(chunks)

def metrics_ack_frame(*, boot_id: str = "device-boot", session_id: str = "host-session",
                      sequence: int = 2, reply_to: int = 1) -> bytes:
    payload = {name: 0 for name in PAYLOAD_KEYS["metrics_ack"]}
    payload.update({
        "acknowledged": 1,
        "largest_free_block": 1,
        "max_display_flush_us": 1,
        "max_key_poll_gap_us": 1,
        "minimum_free_heap": 1,
        "parser_high_water": 1,
        "queue_high_water": 1,
        "received": 1,
        "retained_boot_sequence": 1,
        "sent": 1,
    })
    return encode_frame(
        "metrics_ack",
        boot_id,
        session_id,
        sequence,
        payload,
        version=1,
        reply_to=reply_to,
    )


def test_session_rejects_unterminated_oversized_frame() -> None:
    session = DeviceSession(FragmentedConnection([b"x" * (smoke.MAX_LINE_BYTES + 1)]), timeout=0.01)
    with pytest.raises(SerialLinkError):
        session.wait_for_type("focus_intent", 0.01)


def test_session_rejects_short_serial_write() -> None:
    class ShortWrite(FragmentedConnection):
        def write(self, data: bytes) -> int:
            self.writes.append(data)
            return max(0, len(data) - 1)

    session = DeviceSession(ShortWrite([]), timeout=0.01)
    with pytest.raises(SerialLinkError):
        session.send("metrics", {"request": "proof"}, version=1)


def test_session_rejects_bad_digest_and_mismatched_identity() -> None:
    def session_after_hello(response: bytes) -> DeviceSession:
        hello_ack = encode_frame(
            "hello_ack",
            "device-boot",
            "host-session",
            1,
            {
                "accepted": True,
                "device_id": "phase22-device",
                "firmware": "phase22-firmware",
                "protocol": 1,
            },
            version=1,
            reply_to=1,
        )
        session = DeviceSession(FragmentedConnection([hello_ack, response]), timeout=0.01)
        session.session_id = "host-session"
        assert session.hello()["boot_id"] == "device-boot"
        return session

    bad = json.loads(metrics_ack_frame(reply_to=2))
    bad["digest"] = "0" * 16
    invalid_responses = (
        (json.dumps(bad) + "\n").encode("ascii"),
        metrics_ack_frame(boot_id="other-boot", reply_to=2),
        metrics_ack_frame(session_id="other-session", reply_to=2),
    )

    for response in invalid_responses:
        session = session_after_hello(response)
        with pytest.raises(TimeoutError):
            session.request("metrics", {"request": "proof"}, version=1)


def test_session_rejects_stale_matching_reply_sequence() -> None:
    connection = FragmentedConnection([metrics_ack_frame(sequence=1, reply_to=1)])
    session = DeviceSession(connection, timeout=0.01)
    session.session_id = "host-session"
    session._last_received_seq = 1
    with pytest.raises(TimeoutError):
        session.request("metrics", {"request": "proof"}, version=1)


def focus_intent_frame(action_id: str = "action-1") -> bytes:
    return encode_frame(
        "focus_intent",
        "device-boot",
        "host-session",
        37,
        {
            "action_id": action_id,
            "agent_session": None,
            "entry_id": "entry-1",
            "host_epoch": "epoch-1",
            "pane_id": "pane-1",
            "slot": 0,
            "snapshot_revision": 11,
            "source_revision": 7,
            "terminal_id": "terminal-1",
        },
    )


def test_focus_intent_survives_fragmented_usb_line() -> None:
    frame = focus_intent_frame()
    split = len(frame) // 2
    session = DeviceSession(FragmentedConnection([frame[:split], frame[split:]]), timeout=0.05)
    session.session_id = "host-session"

    assert session.wait_for_type("focus_intent", 0.05) == json.loads(frame)


def test_pre_arm_discard_removes_stale_complete_and_partial_intents() -> None:
    stale = focus_intent_frame("stale-action")
    fresh = focus_intent_frame("fresh-action")
    connection = FragmentedConnection([stale[31:]])
    session = DeviceSession(connection, timeout=0.05)
    session.session_id = "host-session"
    session._rx_buffer.extend(stale[:31])

    session.discard_pending_input()
    connection.feed(fresh[:63], fresh[63:])

    actual = session.wait_for_type("focus_intent", 0.05)
    assert actual["payload"]["action_id"] == "fresh-action"
    assert connection.reset_count == 1


def test_request_preserves_unmatched_focus_intent_for_later_wait() -> None:
    intent = focus_intent_frame("queued-action")
    metrics_ack = encode_frame(
        "metrics_ack",
        "device-boot",
        "host-session",
        38,
        {
            "acknowledged": 1,
            "digest_mismatch": 0,
            "duplicate": 0,
            "largest_free_block": 1,
            "malformed": 0,
            "max_display_flush_us": 1,
            "max_key_poll_gap_us": 1,
            "minimum_free_heap": 1,
            "out_of_order": 0,
            "parser_high_water": 1,
            "queue_high_water": 1,
            "received": 1,
            "rejected": 0,
            "sent": 1,
            "watchdog_reset": 0,
        },
        version=1,
        reply_to=1,
    )
    connection = FragmentedConnection([intent + metrics_ack])
    session = DeviceSession(connection, timeout=0.05)
    session.session_id = "host-session"

    response = session.request("metrics", {"request": "proof"}, version=1)
    preserved = session.wait_for_type("focus_intent", 0.05)

    assert response["type"] == "metrics_ack"
    assert preserved["payload"]["action_id"] == "queued-action"


def test_focus_intent_replay_covers_serial_read_boundaries() -> None:
    frame = focus_intent_frame()
    probe_ack = encode_frame(
        "probe_ack",
        "device-boot",
        "stale-session",
        36,
        {"accepted": True, "step_id": "stale-probe"},
        version=1,
        reply_to=9,
    )
    cases = (
        [frame],
        [frame.replace(b"\n", b"\r\n")],
        [frame[:1], frame[1:63], frame[63:255], frame[255:-1], frame[-1:]],
        [b"ESP-ROM boot chatter\r\n" + frame],
        [b"\xff\xfeinvalid utf-8\nnot-json\n" + frame],
        [probe_ack + frame],
        [b"boot\n", probe_ack[:17], probe_ack[17:] + frame[:31], frame[31:]],
    )

    expected = json.loads(frame)
    expected_payload_keys = {
        "action_id",
        "agent_session",
        "entry_id",
        "host_epoch",
        "pane_id",
        "slot",
        "snapshot_revision",
        "source_revision",
        "terminal_id",
    }
    for chunks in cases:
        session = DeviceSession(FragmentedConnection(chunks), timeout=0.05)
        session.session_id = "host-session"
        actual = session.wait_for_type("focus_intent", 0.05)
        assert actual == expected
        assert actual["v"] == 2
        assert actual["boot_id"] == "device-boot"
        assert actual["session_id"] == "host-session"
        assert set(actual["payload"]) == expected_payload_keys
