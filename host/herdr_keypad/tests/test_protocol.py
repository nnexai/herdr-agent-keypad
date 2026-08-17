from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from herdr_keypad.bridge import AgentProjection, V2ProtocolError, _result_for, make_snapshot
from phase1_bringup import protocol

ROOT = Path(__file__).resolve().parents[3]


class V2ProtocolTests(unittest.TestCase):
    def test_v1_inputs_remain_hash_bound(self) -> None:
        schema = ROOT / "protocol/schema/v1.json"
        fixture = ROOT / "protocol/fixtures/v1-golden.json"
        self.assertEqual(hashlib.sha256(schema.read_bytes()).hexdigest(), "f538512c517dab6588a64ea24a06c8464e46d605fd48fa669e68358a9bfbdcd8")
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), "9633d4a2fa47267bb39cece549c92ac2fe6949ceef1570bb2cd05b1920967c52")

    def test_v2_golden_vectors_have_host_results(self) -> None:
        fixture = json.loads((ROOT / "protocol/fixtures/v2-golden.json").read_text())
        self.assertEqual(fixture["schema_version"], 1)
        self.assertGreaterEqual(len(fixture["vectors"]), 4)
        for vector in fixture["vectors"]:
            line = vector["line"]
            if line == "synthetic:oversized":
                raw = b"x" * 4096 + b"\n"
            else:
                raw = line.encode()
            result = protocol.classify_line(raw)
            expected = vector["expected"]
            self.assertEqual(result.reason, expected["reason"], vector["id"])
            self.assertEqual(result.accepted, expected["outcome"] == "accepted", vector["id"])
            if result.accepted:
                session = protocol.ProtocolSession(None, "boot-a", "session-a", queue_limit=4)
                admitted = session.accept(raw)
                self.assertEqual(admitted.reason, expected["reason"], vector["id"])
                self.assertEqual(admitted.dispatched, expected["dispatch"], vector["id"])

    def test_closed_v2_rejects_fourth_slot_and_unknown_fields(self) -> None:
        snapshot = make_snapshot(host_epoch="epoch-a").as_payload()
        with self.assertRaises(protocol.ProtocolError) as fourth:
            protocol.validate_v2_payload("agent_snapshot", {**snapshot, "agents": snapshot["agents"] + [snapshot["agents"][0]]})
        self.assertEqual(fourth.exception.code, "invalid_shape")
        with self.assertRaises(protocol.ProtocolError) as unknown:
            protocol.validate_v2_payload("agent_snapshot", {**snapshot, "unexpected": 1})
        self.assertEqual(unknown.exception.code, "unknown_field")

    def test_generation_and_focus_result_are_fail_closed(self) -> None:
        projection = AgentProjection()
        projection.stage(make_snapshot(host_epoch="epoch-a"))
        with self.assertRaises(V2ProtocolError):
            projection.press(0)
        projection.commit()
        intent = projection.press(0, action_id="action-a")
        self.assertEqual(projection.feedback[0], "pending")
        bad = _result_for(intent, terminal_id="term-reassigned")
        self.assertTrue(projection.apply_result(bad).startswith("rejected:"))
        projection.press(0, action_id="action-b")
        self.assertEqual(projection.apply_result(_result_for(projection.pending["action-b"])), "accepted")

    def test_legal_snapshot_is_below_transport_bound(self) -> None:
        snapshot = make_snapshot(host_epoch="e" * 64).as_payload()
        frame = protocol.new_v2_frame("agent_snapshot", "boot-a", "session-a", 1, snapshot)
        self.assertLessEqual(len(protocol.encode_v2_frame(frame)), protocol.MAX_LINE_BYTES)


if __name__ == "__main__":
    unittest.main()
