from __future__ import annotations

import json

from phase1_bringup.phase22_smoke import (
    FENCES,
    GRAMMARS,
    STATES,
    THEMES,
    SmokeEvidence,
    canonical_payload,
    encode_frame,
    fnv1a64,
    snapshot_payload,
)


def test_frame_digest_matches_payload_bytes() -> None:
    payload = {"source_status": "current", "snapshot_revision": 4}
    frame = json.loads(encode_frame("agent_snapshot", "boot", "session", 1, payload))
    assert frame["digest"] == fnv1a64(canonical_payload(payload))
    assert frame["v"] == 2
    assert frame["seq"] == 1


def test_snapshot_builder_covers_bounded_state_shape() -> None:
    snapshot = snapshot_payload(7, states=("blocked", "finished", "empty"))
    assert snapshot["snapshot_revision"] == 7
    assert [agent["state"] for agent in snapshot["agents"]] == ["blocked", "finished", "empty"]
    assert snapshot["agents"][2]["entry_id"] == ""
    assert all(snapshot["agents"][index]["entry_id"] for index in (0, 1))


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


def test_vocabulary_is_explicit() -> None:
    assert len(THEMES) == 4
    assert len(GRAMMARS) == 4
    assert len(STATES) == 7
    assert len(FENCES) == 3
    assert fnv1a64(b"") == "cbf29ce484222325"
