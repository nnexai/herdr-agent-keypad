"""Production host-side v2 projection and exact focus correlation tracer.

This module deliberately keeps the device capability narrow: the host emits a
closed ``agent_snapshot`` and accepts only a typed ``focus_intent``.  Herdr's
opaque pane identity is never replaced by a slot lookup, and bridge-owned
``host_epoch``/``snapshot_revision`` are correlated independently of Herdr's
``agent_info`` acknowledgement.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

# Reuse the Phase 1 codec/session seam instead of introducing another transport
# or frame parser.  The repository root is added only for the source checkout
# invocation used by the tracer command.
_ROOT = Path(__file__).resolve().parents[4]
_TOOLS_SRC = _ROOT / "tools" / "phase1_bringup" / "src"
if str(_TOOLS_SRC) not in sys.path:
    sys.path.insert(0, str(_TOOLS_SRC))
from phase1_bringup import protocol as v1_protocol  # noqa: E402

MAX_LINE_BYTES = v1_protocol.MAX_LINE_BYTES
MAX_SLOTS = 3
V2 = 2
SOURCE_STATUSES = {"current", "empty", "stale", "unavailable", "offline"}
AGENT_STATES = {"empty", "working", "idle", "blocked", "finished", "settled", "unknown"}
OUTCOMES = {"accepted", "rejected", "stale_target", "not_found", "herdr_offline", "timeout", "uncertain", "vanished", "failed"}


class V2ProtocolError(ValueError):
    """Typed v2 product rejection."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        super().__init__(detail or reason)


@dataclass(frozen=True)
class Identity:
    pane_id: str = ""
    terminal_id: str = ""
    agent_session: str | None = None
    source_revision: int = 0
    workspace_id: str = ""
    tab_id: str = ""

    def as_payload(self) -> dict[str, Any]:
        return {
            "pane_id": self.pane_id,
            "terminal_id": self.terminal_id,
            "agent_session": self.agent_session,
            "source_revision": self.source_revision,
        }


@dataclass(frozen=True)
class AgentEntry:
    slot: int
    entry_id: str
    title: str
    discriminator: str
    state: str
    identity: Identity = field(default_factory=Identity)

    def as_payload(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "entry_id": self.entry_id,
            "title": self.title,
            "discriminator": self.discriminator,
            "state": self.state,
            **self.identity.as_payload(),
        }

    @property
    def occupied(self) -> bool:
        return self.state != "empty"


@dataclass(frozen=True)
class Snapshot:
    host_epoch: str
    snapshot_revision: int
    source_status: str
    agents: tuple[AgentEntry, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "host_epoch": self.host_epoch,
            "snapshot_revision": self.snapshot_revision,
            "source_status": self.source_status,
            "agents": [agent.as_payload() for agent in self.agents],
        }


@dataclass(frozen=True)
class Binding:
    host_epoch: str
    snapshot_revision: int
    slot: int
    entry_id: str
    identity: Identity

    @classmethod
    def from_entry(cls, snapshot: Snapshot, entry: AgentEntry) -> "Binding":
        return cls(snapshot.host_epoch, snapshot.snapshot_revision, entry.slot, entry.entry_id, entry.identity)


@dataclass(frozen=True)
class FocusIntent:
    action_id: str
    binding: Binding

    def as_payload(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "host_epoch": self.binding.host_epoch,
            "snapshot_revision": self.binding.snapshot_revision,
            "slot": self.binding.slot,
            "entry_id": self.binding.entry_id,
            **self.binding.identity.as_payload(),
        }


@dataclass(frozen=True)
class FocusResult:
    action_id: str
    outcome: str
    host_epoch: str
    snapshot_revision: int
    slot: int
    entry_id: str
    identity: Identity
    focused: bool
    reason: str = ""

    def as_payload(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "outcome": self.outcome,
            "host_epoch": self.host_epoch,
            "snapshot_revision": self.snapshot_revision,
            "slot": self.slot,
            "entry_id": self.entry_id,
            **self.identity.as_payload(),
            "focused": self.focused,
        }


def _bounded_text(value: Any, name: str, maximum: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or any(ord(char) >= 0x80 for char in value):
        raise V2ProtocolError("invalid_shape", f"{name} must be bounded ASCII text")
    if not allow_empty and not value:
        raise V2ProtocolError("invalid_shape", f"{name} must not be empty")
    return value


def _opaque(value: Any, name: str, *, allow_empty: bool = False) -> str:
    value = _bounded_text(value, name, 64, allow_empty=allow_empty)
    if value and any(char in "\r\n\t" or ord(char) < 0x21 for char in value):
        raise V2ProtocolError("invalid_identifier", f"{name} contains disallowed opaque bytes")
    return value

def _uint(value: Any, name: str, *, zero: bool = False) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < (0 if zero else 1) or value > 0xFFFFFFFF:
        raise V2ProtocolError("invalid_shape", f"{name} must be a bounded uint32")
    return value


def _identity(payload: Mapping[str, Any], *, empty: bool = False) -> Identity:
    pane = _opaque(payload.get("pane_id"), "pane_id", allow_empty=empty)
    terminal = _opaque(payload.get("terminal_id"), "terminal_id", allow_empty=empty)
    session = payload.get("agent_session")
    if session is not None:
        session = _opaque(session, "agent_session")
    revision = _uint(payload.get("source_revision"), "source_revision", zero=empty)
    if not empty and (not pane or not terminal or revision == 0):
        raise V2ProtocolError("invalid_identity", "occupied identity is incomplete")
    return Identity(pane, terminal, session, revision)


def validate_v2_payload(frame_type: str, payload: Any) -> dict[str, Any]:
    """Validate the closed v2 payload vocabulary before frame admission."""
    if not isinstance(payload, dict):
        raise V2ProtocolError("invalid_payload", "v2 payload must be an object")
    expected: dict[str, set[str]] = {
        "agent_snapshot": {"host_epoch", "snapshot_revision", "source_status", "agents"},
        "snapshot_ack": {"accepted", "host_epoch", "snapshot_revision", "source_status", "reason"},
        "focus_intent": {"action_id", "host_epoch", "snapshot_revision", "slot", "entry_id", "pane_id", "terminal_id", "agent_session", "source_revision"},
        "focus_result": {"action_id", "outcome", "host_epoch", "snapshot_revision", "slot", "entry_id", "pane_id", "terminal_id", "agent_session", "source_revision", "focused"},
    }
    if frame_type not in expected:
        raise V2ProtocolError("unknown_type", "v2 type is not in the closed product set")
    if set(payload) != expected[frame_type]:
        raise V2ProtocolError("unknown_field" if not set(payload).issubset(expected[frame_type]) else "invalid_shape", "v2 payload is closed")
    _opaque(payload["host_epoch"], "host_epoch")
    _uint(payload["snapshot_revision"], "snapshot_revision")
    if frame_type in {"agent_snapshot", "snapshot_ack"}:
        if payload["source_status"] not in SOURCE_STATUSES:
            raise V2ProtocolError("invalid_shape", "source_status is invalid")
    if frame_type == "agent_snapshot":
        agents = payload["agents"]
        if not isinstance(agents, list) or len(agents) != MAX_SLOTS:
            raise V2ProtocolError("invalid_shape", "agent_snapshot requires exactly three slots")
        seen: set[int] = set()
        for agent in agents:
            if not isinstance(agent, dict):
                raise V2ProtocolError("invalid_shape", "agent slot must be an object")
            required = {"slot", "entry_id", "title", "discriminator", "state", "pane_id", "terminal_id", "agent_session", "source_revision"}
            if set(agent) != required:
                raise V2ProtocolError("unknown_field", "agent slot is closed")
            slot = agent["slot"]
            if not isinstance(slot, int) or isinstance(slot, bool) or not 0 <= slot < MAX_SLOTS or slot in seen:
                raise V2ProtocolError("invalid_shape", "agent slot must be unique in 0..2")
            seen.add(slot)
            state = agent["state"]
            if state not in AGENT_STATES:
                raise V2ProtocolError("invalid_shape", "agent state is invalid")
            empty = state == "empty"
            _opaque(agent["entry_id"], "entry_id", allow_empty=empty)
            _bounded_text(agent["title"], "title", 64)
            _bounded_text(agent["discriminator"], "discriminator", 32)
            _identity(agent, empty=empty)
        if seen != set(range(MAX_SLOTS)):
            raise V2ProtocolError("invalid_shape", "agent slots must be 0, 1, and 2")
    elif frame_type == "snapshot_ack":
        if not isinstance(payload["accepted"], bool):
            raise V2ProtocolError("invalid_shape", "snapshot_ack accepted must be boolean")
        _bounded_text(payload["reason"], "reason", 64)
    elif frame_type == "focus_intent":
        _opaque(payload["action_id"], "action_id")
        if not isinstance(payload["slot"], int) or isinstance(payload["slot"], bool) or not 0 <= payload["slot"] < MAX_SLOTS:
            raise V2ProtocolError("invalid_shape", "focus slot must be 0..2")
        _opaque(payload["entry_id"], "entry_id")
        _identity(payload)
    elif frame_type == "focus_result":
        _opaque(payload["action_id"], "action_id")
        if payload["outcome"] not in OUTCOMES:
            raise V2ProtocolError("invalid_shape", "focus outcome is invalid")
        if not isinstance(payload["focused"], bool):
            raise V2ProtocolError("invalid_shape", "focused acknowledgement must be boolean")
        if not isinstance(payload["slot"], int) or isinstance(payload["slot"], bool) or not 0 <= payload["slot"] < MAX_SLOTS:
            raise V2ProtocolError("invalid_shape", "focus result slot must be 0..2")
        _opaque(payload["entry_id"], "entry_id")
        _identity(payload)
    return payload


def _frame(frame_type: str, payload: dict[str, Any], *, boot_id: str = "host", session_id: str = "session", seq: int = 1, reply_to: int | None = None) -> bytes:
    validate_v2_payload(frame_type, payload)
    return v1_protocol.encode_v2_frame(v1_protocol.new_v2_frame(frame_type, boot_id, session_id, seq, payload, reply_to))


def snapshot_frame(snapshot: Snapshot, *, boot_id: str = "host", session_id: str = "session", seq: int = 1) -> bytes:
    return _frame("agent_snapshot", snapshot.as_payload(), boot_id=boot_id, session_id=session_id, seq=seq)


def focus_intent_frame(intent: FocusIntent, *, boot_id: str = "device", session_id: str = "session", seq: int = 1) -> bytes:
    return _frame("focus_intent", intent.as_payload(), boot_id=boot_id, session_id=session_id, seq=seq)


class AgentProjection:
    """Fixed-capacity staged/committed generation and immutable bindings."""

    def __init__(self) -> None:
        self.committed: Snapshot | None = None
        self.staged: Snapshot | None = None
        self.pending: dict[str, FocusIntent] = {}
        self.feedback: dict[int, str] = {}

    def stage(self, snapshot: Snapshot) -> bytes:
        payload = snapshot.as_payload()
        validate_v2_payload("agent_snapshot", payload)
        self.staged = snapshot
        return snapshot_frame(snapshot)

    def commit(self) -> None:
        if self.staged is None:
            raise V2ProtocolError("invalid_generation", "cannot commit without a staged complete snapshot")
        self.committed = self.staged
        self.staged = None
        self.pending.clear()
        self.feedback = {slot: "ready" for slot in range(MAX_SLOTS)}

    def press(self, slot: int, *, action_id: str = "action-1") -> FocusIntent:
        if self.committed is None:
            raise V2ProtocolError("invalid_generation", "no committed snapshot")
        if not isinstance(slot, int) or isinstance(slot, bool) or not 0 <= slot < MAX_SLOTS:
            raise V2ProtocolError("invalid_slot", "slot is not bound")
        entry = self.committed.agents[slot]
        if not entry.occupied or self.committed.source_status != "current":
            self.feedback[slot] = "rejected"
            raise V2ProtocolError("empty" if not entry.occupied else "stale_target", "slot is not actionable")
        intent = FocusIntent(action_id, Binding.from_entry(self.committed, entry))
        validate_v2_payload("focus_intent", intent.as_payload())
        self.pending[action_id] = intent
        self.feedback[slot] = "pending"
        return intent

    def apply_result(self, result: FocusResult) -> str:
        intent = self.pending.pop(result.action_id, None)
        if intent is None:
            return "rejected:unknown_action"
        binding = intent.binding
        checks = (
            result.host_epoch == binding.host_epoch,
            result.snapshot_revision == binding.snapshot_revision,
            result.slot == binding.slot,
            result.entry_id == binding.entry_id,
            result.identity == binding.identity,
            result.focused,
            result.outcome == "accepted",
        )
        status = "accepted" if all(checks) else "rejected:identity_mismatch"
        self.feedback[binding.slot] = "success" if status == "accepted" else "rejected"
        return status


def make_snapshot(*, host_epoch: str | None = None, revision: int = 1, state: str = "working") -> Snapshot:
    epoch = host_epoch or secrets.token_hex(16)
    occupied = AgentEntry(
        0,
        "w19:p1",
        "Phase2",
        "fixture",
        state,
        Identity("w19:p1", "term_6593907102c45d", None, 1),
    )
    empty = AgentEntry(1, "", "NO AGENT", "EMPTY", "empty", Identity())
    empty2 = AgentEntry(2, "", "NO AGENT", "EMPTY", "empty", Identity())
    return Snapshot(epoch, revision, "current", (occupied, empty, empty2))


def _result_for(intent: FocusIntent, **changes: Any) -> FocusResult:
    payload = {
        "action_id": intent.action_id,
        "outcome": "accepted",
        "host_epoch": intent.binding.host_epoch,
        "snapshot_revision": intent.binding.snapshot_revision,
        "slot": intent.binding.slot,
        "entry_id": intent.binding.entry_id,
        **intent.binding.identity.as_payload(),
        "focused": True,
    }
    payload.update(changes)
    validate_v2_payload("focus_result", payload)
    return FocusResult(
        payload["action_id"], payload["outcome"], payload["host_epoch"], payload["snapshot_revision"], payload["slot"], payload["entry_id"],
        Identity(payload["pane_id"], payload["terminal_id"], payload["agent_session"], payload["source_revision"]), payload["focused"],
    )


def self_check_tracer() -> None:
    projection = AgentProjection()
    snapshot = make_snapshot()
    encoded = projection.stage(snapshot)
    assert len(encoded) <= MAX_LINE_BYTES
    assert v1_protocol.classify_v2_line(encoded).accepted
    assert projection.committed is None
    projection.commit()
    intent = projection.press(0, action_id="action-opaque-1")
    intent_frame = focus_intent_frame(intent)
    assert v1_protocol.classify_v2_line(intent_frame).accepted
    assert projection.feedback[0] == "pending"
    assert projection.apply_result(_result_for(intent)) == "accepted"
    assert projection.feedback[0] == "success"

    mismatches = (
        {"pane_id": "w19:p2"},
        {"terminal_id": "term-new"},
        {"action_id": "action-other"},
        {"host_epoch": "different-epoch"},
        {"source_revision": 2},
        {"snapshot_revision": 2},
    )
    for index, change in enumerate(mismatches, 2):
        projection.press(0, action_id=f"action-{index}")
        assert projection.apply_result(_result_for(projection.pending[f"action-{index}"], **change)).startswith("rejected:")
    try:
        projection.press(1, action_id="empty")
    except V2ProtocolError as exc:
        assert exc.reason == "empty"
    else:
        raise AssertionError("empty slot was actionable")
    assert projection.feedback[2] == "ready"  # key/panel 4 is outside the three product slots
    print("v2 tracer: snapshot staged/committed, exact binding pending, matching focus accepted, six identity/generation mismatches rejected")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check-tracer", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check_tracer:
        self_check_tracer()
        return 0
    parser.error("use --self-check-tracer")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
 
 
def _wire_focus_result(intent: FocusIntent, outcome: Any) -> FocusResult:
    """Convert the typed host outcome to the closed firmware result vocabulary."""
    status = getattr(outcome, "status", "failed")
    wire_outcome = {
        "accepted": "accepted",
        "vanished": "vanished",
        "not_found": "not_found",
        "offline": "herdr_offline",
        "uncertain": "uncertain",
        "stale": "stale_target",
        "wrong_epoch": "stale_target",
        "wrong_revision": "stale_target",
        "pane_reused": "stale_target",
        "session_changed": "stale_target",
        "source_revision_changed": "stale_target",
        "empty": "rejected",
        "rejected": "rejected",
        "incompatible": "rejected",
        "wrong_slot": "rejected",
        "failed": "failed",
    }.get(status, "failed")
    identity = intent.binding.identity
    return FocusResult(
        intent.action_id,
        wire_outcome,
        intent.binding.host_epoch,
        intent.binding.snapshot_revision,
        intent.binding.slot,
        intent.binding.entry_id,
        identity,
        wire_outcome == "accepted" and bool(getattr(outcome, "success", False)),
        str(getattr(outcome, "reason", ""))[:64],
    )


def _projection_payload(snapshot: Any) -> dict[str, Any]:
    """Translate the production normalized projection to the v2 wire shape."""
    agents = []
    for entry in snapshot.entries:
        identity = entry.identity
        agents.append(
            {
                "slot": entry.slot,
                "entry_id": entry.entry_id,
                "title": entry.title,
                "discriminator": entry.discriminator,
                "state": entry.state,
                "pane_id": identity.pane_id if identity else "",
                "terminal_id": identity.terminal_id if identity else "",
                "agent_session": identity.agent_session if identity else None,
                "source_revision": identity.source_revision if identity else 0,
            }
        )
    payload = {
        "host_epoch": snapshot.host_epoch,
        "snapshot_revision": snapshot.snapshot_revision,
        "source_status": snapshot.source_status,
        "agents": agents,
    }
    validate_v2_payload("agent_snapshot", payload)
    return payload


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_contract_inputs(root: Path | None = None) -> dict[str, Any]:
    """Reopen the immutable Herdr contract/effects inputs before live focus."""
    root = root or _ROOT
    contract_path = root / "artifacts/phase2/herdr-contract.json"
    effects_path = root / "artifacts/phase2/herdr-focus-effects.json"
    if contract_path.is_symlink() or effects_path.is_symlink():
        raise V2ProtocolError("contract_drift", "contract inputs must not be symlinks")
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        effects = json.loads(effects_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise V2ProtocolError("contract_drift", "contract inputs are unreadable") from exc
    if contract.get("classification") != "baseline-compatible":
        raise V2ProtocolError("contract_drift", "Herdr contract is not baseline-compatible")
    if contract.get("allowlist") != ["agent.focus"] or contract.get("excluded_actions") != [
        "settle",
        "unread",
        "clear",
        "reply",
        "approval",
        "arbitrary_method",
    ]:
        raise V2ProtocolError("contract_drift", "focus-only allowlist changed")
    plugin = contract.get("plugin", {})
    if plugin.get("revision") != "78b243279b4da55150b58dc2cc3cffcdc2fd6a04":
        raise V2ProtocolError("contract_drift", "installed inbox revision changed")
    if effects.get("classification") != "baseline-compatible" or not effects.get("cleanup", {}).get("complete"):
        raise V2ProtocolError("contract_drift", "focus-effects evidence is incomplete")
    rows = effects.get("rows")
    if not isinstance(rows, list) or len(rows) < 8:
        raise V2ProtocolError("contract_drift", "focus-effects matrix is incomplete")
    return {
        "contract": str(contract_path),
        "contract_sha256": _sha256(contract_path),
        "effects": str(effects_path),
        "effects_sha256": _sha256(effects_path),
        "herdr_version": contract.get("herdr", {}).get("version"),
        "plugin_revision": plugin.get("revision"),
    }


class PermanentBridge:
    """One host authority joining public Herdr to one exact USB session."""

    EVENTS = [
        "pane.created",
        "pane.updated",
        "pane.closed",
        "pane.focused",
        "pane.moved",
        "pane.exited",
        "pane.agent_detected",
        "pane.agent_status_changed",
        "workspace.closed",
        "tab.closed",
    ]

    def __init__(self, client: Any, usb: Any, projection: Any, *, contract_root: Path | None = None) -> None:
        self.client = client
        self.usb = usb
        self.projection = projection
        self.contract_root = contract_root or _ROOT
        self.ready = False
        self.last_error = ""
        self.focus = None
        self._last_event_refresh = 0.0

    def _mark_unavailable(self, reason: str) -> None:
        self.last_error = reason
        self.ready = False
        try:
            stale = self.projection.invalidate(reason if reason in {"offline", "unavailable"} else "stale")
            if getattr(self.usb, "connected", False):
                self.usb.publish_snapshot(_projection_payload(stale))
        except Exception:
            pass

    def bootstrap(self) -> Any:
        verify_contract_inputs(self.contract_root)
        from .focus import FocusExecutor

        try:
            snapshot = self.projection.bootstrap(self.client)
            self.usb.connect()
            ack = self.usb.publish_snapshot(_projection_payload(snapshot))
            if (
                ack.get("accepted") is not True
                or ack.get("host_epoch") != snapshot.host_epoch
                or ack.get("snapshot_revision") != snapshot.snapshot_revision
            ):
                raise V2ProtocolError("snapshot_rejected", "keypad did not acknowledge the complete generation")
            self.client.subscribe(events=self.EVENTS)
            self.focus = FocusExecutor(self.client, self.projection, device_session=getattr(self.usb, "session_id", None))
            self.ready = snapshot.source_status == "current" and not self.projection.complete_refresh_required()
            if not self.ready:
                raise V2ProtocolError("snapshot_unavailable", "complete current projection was not committed")
            return snapshot
        except Exception as exc:
            self._mark_unavailable("offline" if "socket" in str(exc).lower() else "unavailable")
            if isinstance(exc, V2ProtocolError):
                raise
            raise V2ProtocolError("bootstrap_failed", str(exc)) from exc

    def handle_frame(self, frame: Mapping[str, Any]) -> Any:
        if frame.get("type") != "focus_intent" or not self.ready or self.focus is None:
            return None
        intent_payload = frame.get("payload")
        validate_v2_payload("focus_intent", intent_payload)
        identity = Identity(
            intent_payload["pane_id"],
            intent_payload["terminal_id"],
            intent_payload["agent_session"],
            intent_payload["source_revision"],
        )
        incoming = Binding(
            intent_payload["host_epoch"],
            intent_payload["snapshot_revision"],
            intent_payload["slot"],
            intent_payload["entry_id"],
            identity,
        )
        # Workspace/tab identity is host-only in the bounded wire frame.
        # Reattach it only after every device-visible identity matches.
        canonical = self.projection.binding(incoming.slot)
        if (
            canonical is not None
            and canonical.host_epoch == incoming.host_epoch
            and canonical.snapshot_revision == incoming.snapshot_revision
            and canonical.entry_id == incoming.entry_id
            and canonical.identity.pane_id == incoming.identity.pane_id
            and canonical.identity.terminal_id == incoming.identity.terminal_id
            and canonical.identity.agent_session == incoming.identity.agent_session
            and canonical.identity.source_revision == incoming.identity.source_revision
        ):
            incoming = canonical
        intent = FocusIntent(intent_payload["action_id"], incoming)
        outcome = self.focus.execute(intent)
        result = _wire_focus_result(intent, outcome)
        self.usb.send_focus_result(result.as_payload())
        return outcome

    def run_once(self) -> Any:
        if not self.ready:
            return None
        frame = self.usb.poll()
        if frame is None:
            return None
        return self.handle_frame(frame)

    def run(self, *, interval: float = 0.1) -> None:
        from .usb import UsbSessionError

        self.bootstrap()
        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except (KeyboardInterrupt, UsbSessionError):
            self._mark_unavailable("offline")
            self.usb.close()


def write_acceptance_evidence(path: Path, *, contract: Mapping[str, Any], snapshot: Any, observed: Mapping[str, Any]) -> None:
    """Write bounded evidence atomically; never include paths or credentials."""
    record = {
        "kind": "phase2-automated-acceptance",
        "schema_version": 1,
        "source": {
            "contract_sha256": contract["contract_sha256"],
            "effects_sha256": contract["effects_sha256"],
            "plugin_revision": contract["plugin_revision"],
            "herdr_version": contract["herdr_version"],
        },
        "snapshot": {
            "host_epoch": snapshot.host_epoch,
            "snapshot_revision": snapshot.snapshot_revision,
            "source_status": snapshot.source_status,
            "slots": len(snapshot.entries),
        },
        "observed": dict(observed),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
