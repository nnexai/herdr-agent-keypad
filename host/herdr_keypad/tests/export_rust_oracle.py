"""Export black-box Python traces consumed by the native Rust parity tests.

This module is deliberately a test-only boundary.  It records normalized inputs
and observable outputs from the public bridge seams; it never serializes Python
objects, upstream payloads, or developer evidence.  ``--verify-determinism``
proves two isolated exports byte-identical before updating committed fixtures.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "host" / "herdr_keypad" / "src"
TOOLS = ROOT / "tools" / "phase1_bringup" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from herdr_keypad.bridge import Binding, FocusIntent, Identity, PermanentBridge, make_snapshot
from herdr_keypad.codex import CodexCollector, CodexView, ChildExit, normalize_rate_limits, redaction_passes
from herdr_keypad.focus import FocusExecutor
from herdr_keypad.herdr import HerdrClient, HerdrError
from herdr_keypad.projection import InboxProjection, ProjectionUnavailable
from phase1_bringup import protocol

FILE_FAMILIES = (
    ("protocol.json", "protocol"),
    ("projection-focus.json", "projection-focus"),
    ("codex.json", "codex"),
    ("lifecycle.json", "lifecycle"),
)
SOURCE_PATHS = (
    "host/herdr_keypad/src/herdr_keypad/bridge.py",
    "host/herdr_keypad/src/herdr_keypad/projection.py",
    "host/herdr_keypad/src/herdr_keypad/focus.py",
    "host/herdr_keypad/src/herdr_keypad/codex.py",
    "host/herdr_keypad/tests/test_protocol.py",
    "host/herdr_keypad/tests/test_projection.py",
    "host/herdr_keypad/tests/test_focus.py",
    "host/herdr_keypad/tests/test_codex.py",
    "host/herdr_keypad/tests/test_integration.py",
    "protocol/schema/v2.json",
    "protocol/fixtures/v2-golden.json",
)
PROTOCOL_TYPES = frozenset({"agent_snapshot", "snapshot_ack", "focus_intent", "focus_result"})
FORBIDDEN_WORDS = (
    "token", "secret", "password", "email", "codexhome", "path", "prompt", "transcript", "stderr", "stdout"
)
MAX_CASES = 256


def canonical(value: object) -> bytes:
    """Return the one canonical JSON representation used for fixture hashes."""
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_records() -> list[dict[str, str]]:
    records = []
    for relative in SOURCE_PATHS:
        path = ROOT / relative
        records.append({"kind": "oracle-source", "path": relative, "sha256": sha256(path.read_bytes())})
    return records


def case(name: str, input_value: object, expected: object) -> dict[str, object]:
    body = {"name": name, "input": input_value, "expected": expected}
    return {**body, "sha256": sha256(canonical(body))}


def corpus(family: str, cases: list[dict[str, object]]) -> dict[str, object]:
    if not 1 <= len(cases) <= MAX_CASES:
        raise ValueError(f"{family} case count is outside the fixed bound")
    body: dict[str, object] = {
        "schema_version": 1,
        "family": family,
        "sources": source_records(),
        "cases": cases,
    }
    return {**body, "fixture_sha256": sha256(canonical(body))}


def write_json(path: Path, value: object) -> bytes:
    encoded = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("ascii")
    path.write_bytes(encoded)
    return encoded


def _frame_result(raw: bytes) -> dict[str, object]:
    result = protocol.classify_v2_line(raw)
    return {"accepted": result.accepted, "reason": result.reason, "dispatch": result.dispatched}


def _raw_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def protocol_cases() -> list[dict[str, object]]:
    snapshot = make_snapshot(host_epoch="epoch-a").as_payload()
    valid_snapshot = protocol.new_v2_frame("agent_snapshot", "boot-a", "session-a", 1, snapshot)
    focus_payload = {
        "action_id": "action-a",
        "host_epoch": "epoch-a",
        "snapshot_revision": 1,
        "slot": 0,
        "entry_id": "w19:p1",
        "pane_id": "w19:p1",
        "terminal_id": "term_6593907102c45d",
        "agent_session": None,
        "source_revision": 1,
    }
    ack_payload = {
        "accepted": True,
        "host_epoch": "epoch-a",
        "snapshot_revision": 1,
        "source_status": "current",
        "reason": "complete",
    }
    result_payload = {**focus_payload, "outcome": "accepted", "focused": True}
    frames = {
        "agent_snapshot": protocol.new_v2_frame("agent_snapshot", "boot-a", "session-a", 1, snapshot),
        "snapshot_ack": protocol.new_v2_frame("snapshot_ack", "boot-a", "session-a", 2, ack_payload),
        "focus_intent": protocol.new_v2_frame("focus_intent", "boot-a", "session-a", 3, focus_payload),
        "focus_result": protocol.new_v2_frame("focus_result", "boot-a", "session-a", 4, result_payload),
    }
    traces: list[dict[str, object]] = []
    for frame_type in ("agent_snapshot", "snapshot_ack", "focus_intent", "focus_result"):
        raw = protocol.encode_v2_frame(frames[frame_type])
        traces.append(case(
            f"protocol.accepted.{frame_type}",
            {"kind": "classify", "type": frame_type, "line": raw.decode("ascii")},
            _frame_result(raw),
        ))

    unknown = copy.deepcopy(valid_snapshot)
    unknown["unexpected"] = True
    raw = _raw_json(unknown)
    traces.append(case("protocol.rejected.unknown-field", {"kind": "classify", "type": "agent_snapshot", "line": raw.decode("ascii")}, _frame_result(raw)))

    bad_digest = copy.deepcopy(valid_snapshot)
    bad_digest["digest"] = "0" * 16
    raw = _raw_json(bad_digest)
    traces.append(case("protocol.rejected.canonical-digest", {"kind": "classify", "type": "agent_snapshot", "line": raw.decode("ascii")}, _frame_result(raw)))

    duplicate = json.dumps(valid_snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    duplicate = duplicate[:-1] + ',"v":2}\n'
    raw = duplicate.encode("ascii")
    traces.append(case("protocol.rejected.duplicate-key", {"kind": "classify", "type": "agent_snapshot", "line": duplicate}, _frame_result(raw)))

    expanded = copy.deepcopy(valid_snapshot)
    expanded["type"] = "hold_intent"
    raw = _raw_json(expanded)
    traces.append(case("protocol.rejected.protocol-expansion", {"kind": "classify", "type": "agent_snapshot", "candidate": "hold_intent", "line": raw.decode("ascii")}, _frame_result(raw)))

    nested = (b'{"a":' * 9) + b"0" + (b"}" * 9) + b"\n"
    traces.append(case("protocol.rejected.nesting", {"kind": "classify", "type": "agent_snapshot", "line": nested.decode("ascii")}, _frame_result(nested)))

    oversized = b"x" * 4096 + b"\n"
    traces.append(case("protocol.rejected.4096-plus-lf", {"kind": "classify", "type": "agent_snapshot", "line_bytes": len(oversized)}, _frame_result(oversized)))

    boundary = protocol.encode_v2_frame(valid_snapshot)
    if len(boundary) > 4096:
        raise AssertionError("legal snapshot unexpectedly exceeds transport bound")
    boundary = boundary[:-1] + b" " * (4096 - len(boundary)) + b"\n"
    traces.append(case("protocol.accepted.exact-4096-boundary", {"kind": "classify", "type": "agent_snapshot", "line_bytes": len(boundary)}, _frame_result(boundary)))

    zero_payload = copy.deepcopy(snapshot)
    zero_payload["codex"] = {
        "source_state": "current", "primary": 0, "secondary": None, "reset_text": "RESET N/A",
        "observation_age": "AGE 0M", "reached_limit": False, "error_code": "",
    }
    zero_payload["diagnostics"]["codex_status"] = "current"
    zero_payload["diagnostics"]["codex_age"] = "AGE 0M"
    zero_frame = protocol.new_v2_frame("agent_snapshot", "boot-a", "session-a", 5, zero_payload)
    zero_raw = protocol.encode_v2_frame(zero_frame)
    traces.append(case("protocol.accepted.null-versus-zero", {"kind": "classify", "type": "agent_snapshot", "line": zero_raw.decode("ascii")}, _frame_result(zero_raw)))

    session = protocol.ProtocolSession(None, "boot-a", "session-a", queue_limit=4)
    first = session.accept(protocol.encode_v2_frame(valid_snapshot))
    duplicate_result = session.accept(protocol.encode_v2_frame(valid_snapshot))
    sequence_two = protocol.new_v2_frame("snapshot_ack", "boot-a", "session-a", 2, ack_payload)
    accepted_two = session.accept(protocol.encode_v2_frame(sequence_two))
    out_of_order = session.accept(protocol.encode_v2_frame(valid_snapshot))
    traces.append(case(
        "protocol.session-duplicate-and-sequence",
        {"kind": "session", "type": "focus_intent", "sequence": [1, 1, 2, 1]},
        {"first": first.reason, "duplicate": duplicate_result.reason, "second": accepted_two.reason, "out_of_order": out_of_order.reason},
    ))
    wrong_session = copy.deepcopy(valid_snapshot)
    wrong_session["session_id"] = "other-session"
    traces.append(case("protocol.rejected.session-mismatch", {"kind": "session", "type": "agent_snapshot"}, {"reason": session.accept(_raw_json(wrong_session)).reason}))
    return traces


def row(pane: str, rank: str, sequence: int, *, revision: int = 1, title: str | None = "Title", cwd: str = "repo") -> dict[str, object]:
    return {
        "pane_id": pane, "terminal_id": f"term-{pane}", "workspace_id": "workspace-1", "tab_id": f"tab-{pane}",
        "agent_status": "working", "focused": False, "revision": revision, "state_change_seq": sequence,
        "cwd": cwd, "title": title, "tokens": {"rank": rank, "title": "Plugin title"}, "agent": "agent",
    }


def identity_view(identity: Identity | None) -> dict[str, object] | None:
    if identity is None:
        return None
    return {
        "pane_id": identity.pane_id, "terminal_id": identity.terminal_id, "agent_session": identity.agent_session,
        "source_revision": identity.source_revision, "workspace_id": identity.workspace_id, "tab_id": identity.tab_id,
    }


def snapshot_view(snapshot: object) -> dict[str, object]:
    return {
        "host_epoch": snapshot.host_epoch,
        "snapshot_revision": snapshot.snapshot_revision,
        "source_status": snapshot.source_status,
        "actionable": snapshot.actionable,
        "entries": [
            {
                "slot": entry.slot, "entry_id": entry.entry_id, "title": entry.title,
                "discriminator": entry.discriminator, "since": entry.since, "age": entry.age,
                "state": entry.state, "rank": entry.rank, "state_change_seq": entry.state_change_seq,
                "stale": entry.stale, "identity": identity_view(entry.identity),
            }
            for entry in snapshot.entries
        ],
    }


def projection_cases() -> list[dict[str, object]]:
    traces: list[dict[str, object]] = []
    full_rows = [row("p3", "2", 1), row("p1", "0", 2), row("p2", "1", 3)]
    projection = InboxProjection(host_epoch="epoch-fixed")
    first = projection.refresh(full_rows)
    partial = projection.refresh([row("p1", "0", 2)])
    traces.append(case("projection.order-full-and-empty-fill", {"operation": "refresh", "scenario": "three-rank-order-plus-empty-fill"}, {"full": snapshot_view(first), "partial": snapshot_view(partial)}))

    tied = InboxProjection(host_epoch="epoch-fixed")
    one = tied.refresh([row("old", "2", 4), row("new", "2", 9)])
    two = tied.refresh([row("new", "2", 9), row("old", "2", 4)])
    traces.append(case("projection.rank-tie-state-sequence", {"operation": "refresh", "scenario": "equal-rank-newest-sequence"}, {"first": snapshot_view(one), "reversed": snapshot_view(two)}))

    missing_rank = row("missing-rank", "2", 1)
    del missing_rank["tokens"]["rank"]
    try:
        InboxProjection().refresh([missing_rank])
    except ProjectionUnavailable:
        missing_rank_result = {"status": "unavailable"}
    else:
        missing_rank_result = {"status": "unexpected"}
    missing_identity = row("missing-identity", "2", 1)
    del missing_identity["terminal_id"]
    try:
        InboxProjection().refresh([missing_identity])
    except ProjectionUnavailable:
        missing_identity_result = {"status": "unavailable"}
    else:
        missing_identity_result = {"status": "unexpected"}
    traces.append(case("projection.rejected.missing-rank-and-identity", {"operation": "refresh", "rows": ["malformed-rank", "malformed-identity"]}, {"rank": missing_rank_result, "identity": missing_identity_result}))

    bounded = InboxProjection(host_epoch="epoch-fixed")
    bounded_snapshot = bounded.refresh([row("p1", "2", 1, title=None)], [{"workspace_id": "workspace-1", "label": "Workspace"}])
    traces.append(case("projection.bounded-title-discriminator", {"operation": "refresh", "title": None, "workspace_label": "Workspace"}, {"entry": snapshot_view(bounded_snapshot)["entries"][0]}))

    invalidated = InboxProjection(host_epoch="epoch-fixed")
    current = invalidated.refresh([row("p1", "2", 1)])
    stale = invalidated.invalidate("offline")
    traces.append(case("projection.invalidation-preserves-stale-identity", {"operation": "invalidate", "reason": "offline"}, {"before": snapshot_view(current), "after": snapshot_view(stale), "binding": identity_view(invalidated.binding(0).identity if invalidated.binding(0) else None)}))

    revisions = InboxProjection(host_epoch="epoch-fixed")
    initial_row = row("p1", "0", 1)
    initial = revisions.refresh([initial_row])
    revision_only = revisions.refresh([{**initial_row, "revision": 99}])
    material = revisions.refresh([{**initial_row, "revision": 99, "state_change_seq": 2}])
    traces.append(case("projection.material-revision-rules", {"operation": "refresh", "revision_only": 99, "material_sequence": 2}, {"revision_only_same": initial is revision_only, "revision_only": revision_only.snapshot_revision, "material": material.snapshot_revision, "material_changed": material is not revision_only, "source_revision": material.entries[0].identity.source_revision}))

    statuses = InboxProjection(host_epoch="epoch-fixed")
    unavailable = statuses.refresh([], source_status="unavailable")
    traces.append(case("projection.source-unavailable-is-not-empty-current", {"operation": "refresh", "source_status": "unavailable"}, {"snapshot": snapshot_view(unavailable), "binding": identity_view(statuses.binding(0).identity if statuses.binding(0) else None)}))
    return traces


class FocusSpy:
    def __init__(self, rows: list[dict[str, object]] | None = None, responses: list[object] | None = None, error: Exception | None = None):
        self.rows = rows if rows is not None else [row("p1", "2", 4)]
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[tuple[str, str | None]] = []

    def agent_list(self) -> list[dict[str, object]]:
        self.calls.append(("agent.list", None))
        if self.error:
            raise self.error
        return self.rows

    def focus(self, pane_id: str) -> object:
        self.calls.append(("agent.focus", pane_id))
        if self.error:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        focused = dict(next(item for item in self.rows if item["pane_id"] == pane_id))
        focused["focused"] = True
        return {"type": "agent_info", "agent": focused}


def focus_case(name: str, spy: FocusSpy, projection: InboxProjection, intent: FocusIntent, scenario: str) -> dict[str, object]:
    outcome = FocusExecutor(spy, projection).execute(intent)
    return case(
        name,
        {"operation": "focus", "scenario": scenario},
        {
            "status": outcome.status,
            "success": outcome.success,
            "calls": [{"method": method, "target": target} for method, target in spy.calls],
        },
    )


def focus_cases() -> list[dict[str, object]]:
    traces: list[dict[str, object]] = []

    projection = InboxProjection(host_epoch="epoch-fixed")
    projection.refresh([row("p1", "2", 4)])
    intent = FocusIntent("action-valid", projection.binding(0))
    traces.append(focus_case("focus.accepted.exact-identity", FocusSpy(), projection, intent, "exact identity and sole write"))

    projection = InboxProjection(host_epoch="epoch-fixed")
    projection.refresh([row("p1", "2", 4)])
    intent = FocusIntent("action-retry", projection.binding(0))
    first = {"type": "agent_info", "agent": {**row("p1", "2", 4), "focused": False}}
    second = {"type": "agent_info", "agent": {**row("p1", "2", 4), "focused": True}}
    traces.append(focus_case("focus.accepted.one-unfocused-retry", FocusSpy(responses=[first, second]), projection, intent, "one retry"))

    projection = InboxProjection(host_epoch="epoch-fixed")
    projection.refresh([row("p1", "2", 4)])
    intent = FocusIntent("action-pane-reused", projection.binding(0))
    traces.append(focus_case("focus.rejected.pane-reused", FocusSpy(rows=[row("p1", "2", 4, revision=2).copy()]), projection, intent, "terminal identity mismatch"))
    reused_rows = [row("p1", "2", 4)]
    reused_rows[0]["terminal_id"] = "different-terminal"
    projection = InboxProjection(host_epoch="epoch-fixed")
    projection.refresh([row("p1", "2", 4)])
    intent = FocusIntent("action-pane-reused", projection.binding(0))
    traces[-1] = focus_case("focus.rejected.pane-reused", FocusSpy(rows=reused_rows), projection, intent, "terminal identity mismatch")

    projection = InboxProjection(host_epoch="epoch-fixed")
    projection.refresh([row("p1", "2", 4)])
    intent = FocusIntent("action-stale", projection.binding(0))
    projection.invalidate("stale")
    traces.append(focus_case("focus.rejected.stale", FocusSpy(), projection, intent, "stale projection"))

    projection = InboxProjection(host_epoch="epoch-fixed")
    projection.refresh([row("p1", "2", 4)])
    intent = FocusIntent("action-vanished", projection.binding(0))
    traces.append(focus_case("focus.rejected.vanished", FocusSpy(rows=[]), projection, intent, "pane vanished"))

    projection = InboxProjection(host_epoch="epoch-fixed")
    projection.refresh([row("p1", "2", 4)])
    intent = FocusIntent("action-timeout", projection.binding(0))
    traces.append(focus_case("focus.rejected.timeout-uncertain", FocusSpy(error=HerdrError("timeout")), projection, intent, "request timeout"))

    projection = InboxProjection(host_epoch="epoch-fixed")
    projection.refresh([row("p1", "2", 4)])
    intent = FocusIntent("action-malformed", projection.binding(0))
    traces.append(focus_case("focus.rejected.malformed-ack", FocusSpy(responses=[{"type": "error"}]), projection, intent, "malformed acknowledgement"))

    projection = InboxProjection(host_epoch="epoch-fixed")
    projection.refresh([row("p1", "2", 4)])
    intent = FocusIntent("action-not-found", projection.binding(0))
    traces.append(focus_case("focus.rejected.agent-not-found", FocusSpy(error=HerdrError("agent_not_found")), projection, intent, "not found write"))
    return traces


class ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeProcess:
    def __init__(self, messages: list[object], returncode: int | None = None):
        self.stdin = io.BytesIO()
        encoded = [message if isinstance(message, bytes) else json.dumps(message, separators=(",", ":")).encode("ascii") for message in messages]
        self.stdout = io.BytesIO(b"\n".join(encoded) + (b"\n" if encoded else b""))
        self.stderr = io.BytesIO()
        self.returncode = returncode
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int | None:
        return self.returncode


def codex_view(view: CodexView) -> dict[str, object]:
    return view.as_payload()


def codex_cases() -> list[dict[str, object]]:
    traces: list[dict[str, object]] = []
    with patch("herdr_keypad.codex.time.time", return_value=1000):
        view, redaction = normalize_rate_limits({"rateLimits": {"primary": {"usedPercent": 0}, "secondary": {"usedPercent": 57}}})
    traces.append(case("codex.current.full-baseline-zero", {"operation": "normalize", "shape": "full"}, {"view": codex_view(view), "redaction": redaction.as_dict()}))

    weekly, _ = normalize_rate_limits({"rateLimits": {"primary": {"usedPercent": 40, "windowDurationMins": 10_080}, "secondary": None}})
    traces.append(case("codex.current.weekly-window-mapping", {"operation": "normalize", "duration_minutes": 10080}, {"view": codex_view(weekly)}))

    collector = CodexCollector(clock=ManualClock())
    sparse_before = collector.apply_sparse_update({"rateLimits": {"primary": {"usedPercent": 99}}})
    traces.append(case("codex.unavailable.sparse-before-baseline", {"operation": "sparse", "baseline": "absent"}, {"accepted": sparse_before, "view": codex_view(collector.view()), "refetch_pending": collector.refetch_pending}))

    clock = ManualClock()
    collector = CodexCollector(clock=clock)
    collector.apply_full_response({"rateLimits": {"primary": {"usedPercent": 10}, "secondary": {"usedPercent": 20}, "rateLimitReachedType": "primary"}})
    sparse = collector.apply_sparse_update({"rateLimits": {"primary": {"usedPercent": 0}, "secondary": None, "rateLimitReachedType": None}})
    traces.append(case("codex.current.sparse-merge-and-refetch", {"operation": "sparse", "baseline": "full"}, {"accepted": sparse, "view": codex_view(collector.view()), "refetch_pending": collector.refetch_pending, "consume_refetch": collector.consume_refetch(), "consume_again": collector.consume_refetch()}))

    collector = CodexCollector(clock=clock)
    collector.apply_full_response({"rateLimits": {"primary": {"usedPercent": 12}}})
    reset = collector.account_changed(auth_required=True, account={"kind": "redacted"})
    traces.append(case("codex.auth-required.account-reset", {"operation": "account_changed", "auth_required": True}, {"view": codex_view(reset), "cache_cleared": collector.last_full_observed_at is None}))

    stale_clock = ManualClock()
    stale_collector = CodexCollector(clock=stale_clock)
    stale_collector.apply_full_response({"rateLimits": {"primary": {"usedPercent": 12}}})
    stale_clock.advance(901)
    traces.append(case("codex.stale.after-freshness-deadline", {"operation": "freshness", "elapsed_seconds": 901}, {"view": codex_view(stale_collector.view())}))

    unsupported, _ = normalize_rate_limits({"rateLimits": {"primary": {"usedPercent": 40, "windowDurationMins": 1440}}})
    traces.append(case("codex.unavailable.unsupported-duration", {"operation": "normalize", "duration_minutes": 1440}, {"view": codex_view(unsupported)}))

    auth_process = FakeProcess([{"id": 1, "result": {}}, {"id": 2, "result": {"account": None, "requiresOpenaiAuth": True}}])
    auth_collector = CodexCollector(process_factory=lambda *args, **kwargs: auth_process, deadline_ms=3000, clock=ManualClock())
    auth_result = auth_collector.collect()
    traces.append(case("codex.auth-required.child-handshake", {"operation": "collect", "scenario": "auth"}, {"view": codex_view(auth_result.view), "evidence": auth_result.as_evidence()}))

    offline_process = FakeProcess([{"id": 1, "result": {}}, b"not-json"])
    offline_collector = CodexCollector(process_factory=lambda *args, **kwargs: offline_process, deadline_ms=3000, clock=ManualClock())
    offline_result = offline_collector.collect()
    traces.append(case("codex.codex-offline.malformed-jsonl", {"operation": "collect", "scenario": "malformed"}, {"view": codex_view(offline_result.view), "evidence": offline_result.as_evidence()}))

    exit_process = FakeProcess([{"id": 1, "result": {}}, {"id": 2, "result": {"account": {"type": "chatgpt"}}}, {"id": 3, "result": {"rateLimits": {"primary": {"usedPercent": 1}}}}], returncode=7)
    exit_collector = CodexCollector(process_factory=lambda *args, **kwargs: exit_process, deadline_ms=3000, clock=ManualClock())
    exit_result = exit_collector.collect()
    traces.append(case("codex.child-exit.nonzero-observed", {"operation": "collect", "scenario": "already-exited"}, {"view": codex_view(exit_result.view), "child_exit": exit_result.as_evidence()["child_exit"]}))

    redaction_input = {"nested": [{"token": "secret"}, {"prompt": "private"}]}
    traces.append(case("codex.redaction.sensitive-shape-rejected", {"operation": "redaction", "shape": "nested-sensitive"}, {"redaction_passes": redaction_passes(redaction_input)}))
    return traces


class LifecycleHerdr:
    def __init__(self, rows: list[dict[str, object]] | None = None):
        self.rows = rows if rows is not None else [row("p1", "0", 4), row("p2", "1", 3), row("p3", "2", 2)]
        self.calls: list[str] = []

    def request(self, method: str, params: dict[str, object]) -> object:
        self.calls.append(method)
        if method == "session.snapshot":
            return {"version": "0.8.0", "protocol": 19, "workspaces": [], "tabs": [], "panes": [], "layouts": [], "agents": self.rows}
        if method == "agent.list":
            return {"agents": self.rows}
        if method == "workspace.list":
            return {"workspaces": [{"workspace_id": "workspace-1", "label": "repo"}]}
        if method == "events.subscribe":
            return {"subscribed": True}
        if method == "agent.focus":
            target = next(item for item in self.rows if item["pane_id"] == params["target"])
            return {"type": "agent_info", "agent": {**target, "focused": True}}
        raise AssertionError(method)


class LifecycleUsb:
    def __init__(self):
        self.connected = False
        self.session_id = "session-0"
        self.published: list[dict[str, object]] = []
        self.results: list[dict[str, object]] = []
        self.pending_focus: dict[str, object] | None = None
        self.connect_attempts = 0
        self.fail_poll = False

    def connect(self) -> dict[str, object]:
        self.connect_attempts += 1
        self.session_id = f"session-{self.connect_attempts}"
        self.connected = True
        return {"hello": {"device_id": "paired", "firmware": "phase1"}}

    def publish_snapshot(self, payload: dict[str, object]) -> dict[str, object]:
        self.published.append(payload)
        return {"accepted": True, "host_epoch": payload["host_epoch"], "snapshot_revision": payload["snapshot_revision"]}

    def send_focus_result(self, payload: dict[str, object]) -> None:
        self.results.append(payload)

    def poll(self) -> None:
        if self.fail_poll:
            self.fail_poll = False
            raise RuntimeError("temporary descriptor failure")
        return None

    def close(self) -> None:
        self.connected = False

    def clear_pending_focus(self) -> None:
        self.pending_focus = None


class LifecycleEventStream:
    def __init__(self):
        self.mode = "push"
        self.typed_event = None
        self.close_calls = 0
        self.poll_calls = 0

    def probe(self, **kwargs: object) -> str:
        del kwargs
        return self.mode

    def poll(self) -> None:
        self.poll_calls += 1
        return None

    def close(self) -> None:
        self.close_calls += 1
        self.mode = "closed"


def lifecycle_state(bridge: PermanentBridge, usb: LifecycleUsb, herdr: LifecycleHerdr) -> dict[str, object]:
    current = bridge.projection.current
    return {
        "ready": bridge.ready,
        "revision": current.snapshot_revision if current is not None else None,
        "link_status": "current" if usb.connected else "offline",
        "usb_connected": usb.connected,
        "publication_count": bridge.publication_count,
        "ready_transitions": bridge.ready_transitions,
        "connect_attempts": usb.connect_attempts,
        "herdr_calls": herdr.calls,
        "focus_writes": herdr.calls.count("agent.focus"),
        "usb_results": len(usb.results),
    }


def lifecycle_cases() -> list[dict[str, object]]:
    traces: list[dict[str, object]] = []
    herdr = LifecycleHerdr()
    usb = LifecycleUsb()
    bridge = PermanentBridge(HerdrClient(requester=herdr.request), usb, InboxProjection(host_epoch="epoch-fixed"), contract_root=ROOT)
    bridge.bootstrap()
    traces.append(case("lifecycle.ready-after-complete-snapshot-ack", {"operation": "bootstrap"}, lifecycle_state(bridge, usb, herdr)))

    clock = ManualClock()
    herdr = LifecycleHerdr()
    usb = LifecycleUsb()
    bridge = PermanentBridge(HerdrClient(requester=herdr.request), usb, InboxProjection(host_epoch="epoch-fixed"), contract_root=ROOT, clock=clock)
    bridge.bootstrap()
    old_session = usb.session_id
    usb.fail_poll = True
    bridge.run_once()
    offline = lifecycle_state(bridge, usb, herdr)
    clock.advance(PermanentBridge.RECONNECT_INITIAL_DELAY_SECONDS)
    bridge.run_once()
    recovered = lifecycle_state(bridge, usb, herdr)
    traces.append(case("lifecycle.usb-reconnect-backoff-and-fresh-session", {"operation": "run_once", "initial_session": old_session}, {"offline": offline, "recovered": recovered, "session_replaced": old_session != usb.session_id}))

    herdr = LifecycleHerdr()
    usb = LifecycleUsb()
    bridge = PermanentBridge(HerdrClient(requester=herdr.request), usb, InboxProjection(host_epoch="epoch-fixed"), contract_root=ROOT)
    bridge.bootstrap()
    binding = bridge.projection.binding(0)
    bridge.ready = False
    payload = {
        "action_id": "deferred", "host_epoch": binding.host_epoch, "snapshot_revision": binding.snapshot_revision,
        "slot": binding.slot, "entry_id": binding.entry_id, **binding.identity.as_payload(),
    }
    frame = protocol.new_v2_frame("focus_intent", "device", usb.session_id, 1, payload)
    queued = bridge.handle_frame(frame)
    usb.fail_poll = True
    bridge.run_once()
    traces.append(case("lifecycle.disconnect-discards-deferred-focus", {"operation": "disconnect", "deferred_focus": "queued-before-fence", "handler_result": queued}, {"focus_writes": herdr.calls.count("agent.focus"), "ready": bridge.ready, "last_focus": bridge.last_focus}))

    streams: list[LifecycleEventStream] = []
    herdr = LifecycleHerdr()
    usb = LifecycleUsb()
    client = HerdrClient(requester=herdr.request)
    client.event_stream_factory = lambda: streams.append(LifecycleEventStream()) or streams[-1]
    bridge = PermanentBridge(client, usb, InboxProjection(host_epoch="epoch-fixed"), contract_root=ROOT)
    bridge.bootstrap()
    before = herdr.calls.count("agent.list")
    bridge.run_once()
    traces.append(case("lifecycle.healthy-event-stream-idle", {"operation": "run_once", "stream_mode": "push"}, {"stream_count": len(streams), "agent_reads_before": before, "agent_reads_after": herdr.calls.count("agent.list"), "invalidation_count": bridge.invalidation_count, "poll_calls": streams[0].poll_calls}))

    herdr = LifecycleHerdr()
    usb = LifecycleUsb()
    bridge = PermanentBridge(HerdrClient(requester=herdr.request), usb, InboxProjection(host_epoch="epoch-fixed"), contract_root=ROOT)
    bridge.bootstrap()
    auth = bridge.account_changed(auth_required=True)
    usb.fail_poll = True
    bridge.run_once()
    traces.append(case("lifecycle.independent-codex-auth-on-link-loss", {"operation": "account_changed_then_disconnect"}, {"codex_state": auth.source_state, "bridge_codex_state": bridge.codex_view.source_state, "ready": bridge.ready}))
    return traces


def _absolute_path_shaped(value: str) -> bool:
    return value.startswith(("/", "\\", "~/", "~\\", "file://")) or (len(value) >= 3 and value[1] == ":" and value[2] in "/\\")


def _privacy_passes(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            lower = str(key).lower()
            if any(word in lower for word in FORBIDDEN_WORDS):
                return False
            if not _privacy_passes(child):
                return False

    elif isinstance(value, list):
        return all(_privacy_passes(item) for item in value)
    elif isinstance(value, str) and _absolute_path_shaped(value):
        return False
    return True
def _self_test_schema_and_redaction() -> None:
    """Exercise the exporter gate with positive and negative privacy shapes."""
    if redaction_passes({"nested": {"token": "secret"}}):
        raise AssertionError("redaction gate accepted a sensitive key")
    if _privacy_passes({"cwd": "/private/repository"}):
        raise AssertionError("privacy gate accepted an absolute path")
    if not _privacy_passes({"cwd": "repository", "state": "working"}):
        raise AssertionError("privacy gate rejected a safe normalized value")


def _validate_export_schema(corpora: dict[str, dict[str, object]]) -> None:
    _self_test_schema_and_redaction()
    if set(corpora) != {family for _, family in FILE_FAMILIES}:
        raise AssertionError("missing parity family")
    for family, fixture in corpora.items():
        if fixture["schema_version"] != 1 or fixture["family"] != family:
            raise AssertionError(f"invalid {family} envelope")
        cases = fixture["cases"]
        if not isinstance(cases, list) or not cases:
            raise AssertionError(f"empty {family} cases")
        names = [item["name"] for item in cases]
        if len(names) != len(set(names)):
            raise AssertionError(f"duplicate {family} case names")
        for item in cases:
            if not _privacy_passes(item["input"]) or not _privacy_passes(item["expected"]):
                raise AssertionError(f"private value in {family} fixture")
    protocol_types = {
        item["input"].get("type")
        for item in corpora["protocol"]["cases"]
        if isinstance(item.get("input"), dict) and isinstance(item["input"].get("type"), str)
    }
    if protocol_types != PROTOCOL_TYPES:
        raise AssertionError(f"protocol types are not closed: {protocol_types}")
    required_tokens = {
        "protocol": ("accepted", "rejected", "4096", "session", "duplicate", "null-versus-zero"),
        "projection-focus": ("order", "rank-tie", "invalidation", "revision", "rejected"),
        "codex": ("baseline", "sparse", "auth-required", "offline", "stale", "redaction"),
        "lifecycle": ("ready", "reconnect", "disconnect", "event-stream", "independent"),
    }
    for family, tokens in required_tokens.items():
        text = " ".join(item["name"] for item in corpora[family]["cases"])
        for token in tokens:
            if token.lower() not in text.lower():
                raise AssertionError(f"{family} lacks required trace family {token}")


def export_corpora(output_root: Path) -> dict[str, bytes]:
    output_root.mkdir(parents=True, exist_ok=True)
    corpora = {
        "protocol": corpus("protocol", protocol_cases()),
        "projection-focus": corpus("projection-focus", projection_cases() + focus_cases()),
        "codex": corpus("codex", codex_cases()),
        "lifecycle": corpus("lifecycle", lifecycle_cases()),
    }
    _validate_export_schema(corpora)
    encoded: dict[str, bytes] = {}
    for filename, family in FILE_FAMILIES:
        encoded[filename] = write_json(output_root / filename, corpora[family])
    return encoded


def _run_rust_validator(manifest: Path, fixture_root: Path) -> None:
    environment = os.environ.copy()
    environment["HERDR_ORACLE_FIXTURE_ROOT"] = str(fixture_root)
    subprocess.run(
        ["cargo", "test", "--manifest-path", str(manifest), "--test", "python_oracle_fixture", "synthetic_"],
        cwd=ROOT,
        env=environment,
        check=True,
    )


def verify_determinism(manifest: Path, output_root: Path) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="herdr-oracle-a-") as first_dir, tempfile.TemporaryDirectory(prefix="herdr-oracle-b-") as second_dir:
        first = Path(first_dir)
        second = Path(second_dir)
        first_files = export_corpora(first)
        second_files = export_corpora(second)
        if set(first_files) != {filename for filename, _ in FILE_FAMILIES} or set(second_files) != set(first_files):
            raise AssertionError("isolated export file set is not closed")
        if any(first_files[name] != second_files[name] for name in first_files):
            raise AssertionError("isolated exporter output is not byte-identical")
        first_manifest = {name: sha256(value) for name, value in sorted(first_files.items())}
        second_manifest = {name: sha256(value) for name, value in sorted(second_files.items())}
        if first_manifest != second_manifest:
            raise AssertionError("isolated exporter hash manifests differ")
        _run_rust_validator(manifest, first)
        _run_rust_validator(manifest, second)
        output_root.mkdir(parents=True, exist_ok=True)
        for filename, value in first_files.items():
            (output_root / filename).write_bytes(value)
        return first_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-determinism", action="store_true")
    parser.add_argument("--rust-manifest", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "host/herdr_keypad/native/tests/fixtures")
    args = parser.parse_args(argv)
    if args.verify_determinism:
        if args.rust_manifest is None:
            parser.error("--rust-manifest is required with --verify-determinism")
        manifest = args.rust_manifest if args.rust_manifest.is_absolute() else ROOT / args.rust_manifest
        hashes = verify_determinism(manifest, args.output_root)
    else:
        hashes = {name: sha256(value) for name, value in export_corpora(args.output_root).items()}
    print(json.dumps({"files": hashes, "case": "deterministic" if args.verify_determinism else "exported"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
