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
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping
from .herdr import HerdrClient
from .codex import CodexResult, CodexView
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
BRIDGE_VERSION = "0.1.0"
SOURCE_STATUSES = {"current", "empty", "stale", "unavailable", "offline"}
AGENT_STATES = {"empty", "working", "idle", "blocked", "finished", "settled", "unknown"}
OUTCOMES = {"accepted", "rejected", "stale_target", "not_found", "herdr_offline", "timeout", "uncertain", "vanished", "failed"}
V2_SUFFIX_FALLBACK = "UNAVAL"
V2_DIAGNOSTIC_DEFAULTS: dict[str, Any] = {
    "link_status": "offline",
    "herdr_status": "unavailable",
    "codex_status": "unavailable",
    "sync_age": "AGE N/A",
    "codex_age": "AGE N/A",
    "firmware_version": "UNAVAL",
    "protocol_version": V2,
    "bridge_version": BRIDGE_VERSION,
    "device_suffix": V2_SUFFIX_FALLBACK,
    "session_suffix": V2_SUFFIX_FALLBACK,
    "revision_suffix": V2_SUFFIX_FALLBACK,
    "error_code": "",
}
FOCUS_RESULT_GRACE_SECONDS = 1.0
RECONNECT_INITIAL_DELAY_SECONDS = 0.5
RECONNECT_MAX_DELAY_SECONDS = 8.0



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
    since: str
    age: str
    state: str
    identity: Identity = field(default_factory=Identity)

    def as_payload(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "entry_id": self.entry_id,
            "title": self.title,
            "discriminator": self.discriminator,
            "since": self.since,
            "age": self.age,
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
    codex: CodexView = field(default_factory=CodexView)
    diagnostics: Mapping[str, Any] = field(default_factory=lambda: dict(V2_DIAGNOSTIC_DEFAULTS))

    def as_payload(self) -> dict[str, Any]:
        codex = self.codex.as_payload()
        diagnostics = dict(V2_DIAGNOSTIC_DEFAULTS)
        diagnostics.update(self.diagnostics)
        diagnostics.update(
            {
                "herdr_status": self.source_status if self.source_status in SOURCE_STATUSES else "unavailable",
                "codex_status": codex["source_state"],
                "error_code": codex["error_code"],
            }
        )
        return {
            "host_epoch": self.host_epoch,
            "snapshot_revision": self.snapshot_revision,
            "source_status": self.source_status,
            "agents": [agent.as_payload() for agent in self.agents],
            "codex": codex,
            "diagnostics": diagnostics,
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


def validate_v2_payload(frame_type: str, payload: Any) -> dict[str, Any]:
    """Adapt the sole Phase 1 validator without duplicating its rules."""
    try:
        return v1_protocol.validate_v2_payload(frame_type, payload)
    except v1_protocol.ProtocolError as exc:
        raise V2ProtocolError(exc.code, str(exc)) from exc


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
        "7m",
        "4h",
        state,
        Identity("w19:p1", "term_6593907102c45d", None, 1),
    )
    empty = AgentEntry(1, "", "NO AGENT", "EMPTY", "", "", "empty", Identity())
    empty2 = AgentEntry(2, "", "NO AGENT", "EMPTY", "", "", "empty", Identity())
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
def _projection_payload(snapshot: Any, *, codex: CodexView | None = None,
                        diagnostics: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Translate normalized Herdr plus bounded Codex state to v2."""
    agents = []
    for entry in snapshot.entries:
        identity = entry.identity
        agents.append(
            {
                "slot": entry.slot,
                "entry_id": entry.entry_id,
                "title": entry.title,
                "discriminator": entry.discriminator,
                "since": entry.since,
                "age": entry.age,
                "state": entry.state,
                "pane_id": identity.pane_id if identity else "",
                "terminal_id": identity.terminal_id if identity else "",
                "agent_session": identity.agent_session if identity else None,
                "source_revision": identity.source_revision if identity else 0,
            }
        )
    codex = codex or CodexView()
    merged_diagnostics: dict[str, Any] = dict(V2_DIAGNOSTIC_DEFAULTS)
    merged_diagnostics.update(
        {
            "link_status": getattr(snapshot, "link_status", merged_diagnostics["link_status"]),
            "herdr_status": getattr(snapshot, "herdr_status", "current" if snapshot.source_status == "current" else "offline"),
            "codex_status": getattr(snapshot, "codex_status", codex.source_state),
            "sync_age": getattr(snapshot, "sync_age", "AGE N/A"),
            "codex_age": getattr(snapshot, "codex_age", codex.observation_age),
            "error_code": getattr(snapshot, "error_code", codex.error_code),
        }
    )
    if diagnostics:
        merged_diagnostics.update(diagnostics)
    payload = {
        "host_epoch": snapshot.host_epoch,
        "snapshot_revision": snapshot.snapshot_revision,
        "source_status": snapshot.source_status,
        "agents": agents,
        "codex": codex.as_payload(),
        "diagnostics": merged_diagnostics,
    }
    validate_v2_payload("agent_snapshot", payload)
    return payload

def _age_text(clock: Callable[[], float], observed_at: float | None) -> str:
    if observed_at is None:
        return "AGE N/A"
    return f"AGE {max(0, int((clock() - observed_at) // 60))}M"

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

    GLOBAL_EVENT_TYPES = (
        "pane.created",
        "pane.updated",
        "pane.closed",
        "pane.focused",
        "pane.moved",
        "pane.exited",
        "pane.agent_detected",
        "workspace.closed",
        "tab.closed",
    )
    RECONNECT_INITIAL_DELAY_SECONDS = RECONNECT_INITIAL_DELAY_SECONDS
    STATUS_EVENT_TYPE = "pane.agent_status_changed"
    RECONNECT_MAX_DELAY_SECONDS = RECONNECT_MAX_DELAY_SECONDS

    def __init__(
        self,
        client: Any,
        usb: Any,
        projection: Any,
        *,
        contract_root: Path | None = None,
        clock: Callable[[], float] | None = None,
        codex_collector: Any | None = None,
    ) -> None:
        self.client = client
        self.usb = usb
        self.projection = projection
        self.contract_root = contract_root or _ROOT
        self._clock = clock or time.monotonic
        self.codex_collector = codex_collector
        self.codex_result: CodexResult | None = None
        self.codex_view = CodexView()
        self._herdr_observed_at: float | None = None
        self._codex_observed_at: float | None = None
        self._sync_observed_at: float | None = None
        self._link_observed_at: float | None = None
        self._link_status = "offline"
        self.last_snapshot_ack: dict[str, Any] | None = None
        self.ready = False
        self.last_error = ""
        self.focus = None
        self._last_event_refresh = 0.0
        self._event_stream: Any | None = None
        self.intake_mode = "unclassified"
        self._dirty = False
        self._refresh_active = False
        self._follow_up = False
        self._reestablish_attempts = 0
        self._last_reestablish = 0.0
        self.invalidation_count = 0
        self.publication_count = 0
        self.ready_transitions = 0
        self.last_focus: dict[str, Any] | None = None
        self._deferred_focus: list[dict[str, Any]] = []
        self._focus_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="herdr-focus")
        self._focus_jobs: list[tuple[Future[Any], FocusIntent, int, str | None]] = []
        self._focus_generation = 0
        self._focus_result_grace_until = 0.0
        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY_SECONDS
        self._reconnect_due: float | None = None

    def _clear_usb_pending_focus(self) -> None:
        clear = getattr(self.usb, "clear_pending_focus", None)
        if callable(clear):
            clear()

    def _clear_pending_focus(self) -> None:
        self._clear_usb_pending_focus()
        self._deferred_focus.clear()

    def _close_event_stream(self) -> None:
        stream, self._event_stream = self._event_stream, None
        self.intake_mode = "unclassified"
        if stream is not None:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

    def _fence_focus(self) -> None:
        self._focus_generation += 1
        for future, _intent, _generation, _session_id in self._focus_jobs:
            future.cancel()
        self._focus_jobs.clear()
        self.focus = None
        self._clear_pending_focus()

    def _schedule_reconnect(self, now: float) -> None:
        if self._reconnect_due is not None:
            return
        self._reconnect_due = now + self._reconnect_delay
        self._reconnect_delay = min(
            self._reconnect_delay * 2,
            self.RECONNECT_MAX_DELAY_SECONDS,
        )

    def _disconnect(self, reason: str, now: float) -> None:
        if self._reconnect_due is None:
            self._fence_disconnected(reason)
            try:
                self.usb.close()
            except Exception:
                pass
            self._schedule_reconnect(now)

    def _fence_disconnected(self, reason: str) -> None:
        self.last_error = reason
        self._link_status = "offline"
        self._link_observed_at = self._clock()
        if self.ready:
            self.ready_transitions += 1
        self.ready = False
        self._fence_focus()
        self._close_event_stream()

    def _focus_matches_snapshot(self, frame: Mapping[str, Any], snapshot: Any) -> bool:
        payload = frame.get("payload")
        return (
            isinstance(payload, Mapping)
            and frame.get("session_id") == getattr(self.usb, "session_id", None)
            and payload.get("host_epoch") == snapshot.host_epoch
            and payload.get("snapshot_revision") == snapshot.snapshot_revision
        )

    def _defer_focus(self, frame: Mapping[str, Any]) -> None:
        snapshot = getattr(self.projection, "current", None)
        if (
            snapshot is None
            or getattr(snapshot, "source_status", None) != "current"
            or not self._focus_matches_snapshot(frame, snapshot)
        ):
            return
        action_id = frame["payload"]["action_id"]
        if any(item["payload"]["action_id"] == action_id for item in self._deferred_focus):
            return
        capacity = min(16, max(1, int(getattr(self.usb, "pending_focus_capacity", 16))))
        if len(self._deferred_focus) < capacity:
            self._deferred_focus.append(dict(frame))
    def _drain_deferred_focus(self) -> None:
        pending, self._deferred_focus = self._deferred_focus, []
        for frame in pending:
            self.handle_frame(frame)

    def _mark_unavailable(self, reason: str) -> None:
        self.last_error = reason
        if self.ready:
            self.ready_transitions += 1
        self.ready = False
        self._fence_focus()
        try:
            stale = self.projection.invalidate(reason if reason in {"offline", "unavailable"} else "stale")
            if getattr(self.usb, "connected", False):
                self.usb.publish_snapshot(
                    _projection_payload(stale, codex=self.codex_view, diagnostics=self._diagnostics(stale))
                )
        except Exception:
            pass

    def _publish_snapshot(self, snapshot: Any) -> Any:
        # A current-source refresh is not focus downtime. Intents already read
        # from the device remain queued and are revalidated against live,
        # immutable pane identity after the snapshot acknowledgement.
        self._sync_observed_at = self._clock()
        joined = self._join_health(snapshot)
        if hasattr(self.projection, "current"):
            self.projection.current = joined
        ack = self.usb.publish_snapshot(
            _projection_payload(joined, codex=self.codex_view, diagnostics=self._diagnostics(joined))
        )
        if (
            ack.get("accepted") is not True
            or ack.get("host_epoch") != joined.host_epoch
            or ack.get("snapshot_revision") != joined.snapshot_revision
        ):
            raise V2ProtocolError("snapshot_rejected", "keypad did not acknowledge the complete generation")
        self.last_snapshot_ack = {
            "available": True,
            "accepted": ack.get("accepted"),
            "snapshot_revision": ack.get("snapshot_revision"),
        }
        self.publication_count += 1
        ready = joined.source_status == "current" and not self.projection.complete_refresh_required()
        if not ready:
            raise V2ProtocolError("snapshot_unavailable", "complete current projection was not committed")
        self.ready = True
        self.ready_transitions += 1
        self._drain_deferred_focus()
        return joined

    def _diagnostics(self, snapshot: Any) -> dict[str, Any]:
        herdr_status = getattr(snapshot, "source_status", "unavailable")
        if herdr_status not in SOURCE_STATUSES:
            herdr_status = "unavailable"
        codex_status = self.codex_view.source_state
        hello = self.usb.device.get("hello", {}) if isinstance(getattr(self.usb, "device", None), Mapping) else {}
        firmware_version = hello.get("firmware", V2_DIAGNOSTIC_DEFAULTS["firmware_version"])
        device_id = hello.get("device_id", "")
        session_id = getattr(self.usb, "session_id", None) or ""
        def suffix(value: Any) -> str:
            text = str(value).upper()
            text = "".join(char for char in text if char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
            return (text[-6:] or V2_SUFFIX_FALLBACK)
        diagnostics = dict(V2_DIAGNOSTIC_DEFAULTS)
        diagnostics.update(
            {
                "link_status": self._link_status,
                "herdr_status": herdr_status,
                "codex_status": codex_status,
                "sync_age": _age_text(self._clock, self._sync_observed_at),
                "codex_age": self.codex_view.observation_age,
                "firmware_version": firmware_version if isinstance(firmware_version, str) else V2_SUFFIX_FALLBACK,
                "device_suffix": suffix(device_id),
                "session_suffix": suffix(session_id),
                "revision_suffix": suffix(f"{getattr(snapshot, 'snapshot_revision', 0):06X}"),
                "error_code": self.codex_view.error_code,
            }
        )
        return diagnostics

    def _join_health(self, snapshot: Any) -> Any:
        if hasattr(snapshot, "with_health"):
            return snapshot.with_health(
                herdr_status=getattr(snapshot, "source_status", "unavailable"),
                codex_status=self.codex_view.source_state,
                link_status=self._link_status,
                sync_age=_age_text(self._clock, self._sync_observed_at),
                codex_age=self.codex_view.observation_age,
                herdr_age=_age_text(self._clock, self._herdr_observed_at),
                link_age=_age_text(self._clock, self._link_observed_at),
                error_code=self.codex_view.error_code,
            )
        return snapshot

    def _collect_codex(self) -> CodexResult | None:
        if self.codex_collector is None:
            return None
        result = self.codex_collector.collect()
        if not isinstance(result, CodexResult):
            raise V2ProtocolError("codex_invalid", "collector returned an invalid normalized result")
        self.codex_result = result
        self.codex_view = result.view
        observed_at = getattr(self.codex_collector, "last_observed_at", None)
        self._codex_observed_at = observed_at if isinstance(observed_at, (int, float)) else self._clock()
        return result
    def refresh_codex(self) -> CodexView:
        self._collect_codex()
        snapshot = getattr(self.projection, "current", None)
        if snapshot is not None and getattr(self.usb, "connected", False):
            self._publish_snapshot(snapshot)
        return self.codex_view

    def apply_codex_sparse(self, update: Mapping[str, Any]) -> bool:
        if self.codex_collector is None:
            return False
        accepted = bool(self.codex_collector.apply_sparse_update(update))
        if not accepted:
            return False
        self.codex_view = self.codex_collector.view()
        observed_at = getattr(self.codex_collector, "last_observed_at", None)
        self._codex_observed_at = observed_at if isinstance(observed_at, (int, float)) else self._clock()
        snapshot = getattr(self.projection, "current", None)
        if snapshot is not None and getattr(self.usb, "connected", False):
            self._publish_snapshot(snapshot)
        return True

    def account_changed(self, *, auth_required: bool = False) -> CodexView:
        if self.codex_collector is None:
            self.codex_view = CodexView(source_state="auth_required" if auth_required else "unavailable")
        else:
            self.codex_view = self.codex_collector.account_changed(auth_required=auth_required)
        self._codex_observed_at = None
        snapshot = getattr(self.projection, "current", None)
        if snapshot is not None and getattr(self.usb, "connected", False):
            self._publish_snapshot(snapshot)
        return self.codex_view

    def _publish_refresh(self, *, force: bool = False) -> Any:
        before = getattr(self.projection, "snapshot_revision", 0)
        snapshot = self.projection.bootstrap(self.client)
        self._herdr_observed_at = self._clock()
        if not force and getattr(snapshot, "snapshot_revision", before) == before:
            return snapshot
        return self._publish_snapshot(snapshot)

    def _configure_runtime(self, snapshot: Any) -> None:
        from .focus import FocusExecutor

        subscriptions = [{"type": event_type} for event_type in self.GLOBAL_EVENT_TYPES]
        status_panes = {
            entry.identity.pane_id
            for entry in snapshot.entries
            if entry.identity is not None and entry.identity.pane_id
        }
        subscriptions.extend(
            {"type": self.STATUS_EVENT_TYPE, "pane_id": pane_id}
            for pane_id in sorted(status_panes)
        )
        stream_factory = getattr(self.client, "event_stream_factory", None)
        if callable(stream_factory):
            self._event_stream = stream_factory()
        else:
            self._event_stream = getattr(self.client, "event_stream", None)
        if self._event_stream is not None:
            probe = getattr(self._event_stream, "probe", None)
            if callable(probe):
                self.intake_mode = probe(deadline_seconds=min(5.0, getattr(self.client, "timeout", 1.0)))
            else:
                self.client.subscribe(subscriptions=subscriptions)
                self.intake_mode = "poll"
        elif isinstance(self.client, HerdrClient) and getattr(self.client, "_requester", None) is None:
            from .herdr import HerdrEventStream

            self._event_stream = HerdrEventStream(self.client, subscriptions)
            self.intake_mode = self._event_stream.probe(deadline_seconds=min(5.0, self.client.timeout))
        else:
            self.client.subscribe(subscriptions=subscriptions)
            self.intake_mode = "poll"
        if self.intake_mode == "push" and self._event_stream is not None and self._event_stream.typed_event is not None:
            self._dirty = True
            self.invalidation_count += 1
        self.focus = FocusExecutor(
            self.client,
            self.projection,
            device_session=getattr(self.usb, "session_id", None),
        )

    def _rebuild_after_connect(self, *, force_publish: bool) -> Any:
        if getattr(getattr(self.projection, "current", None), "source_status", None) != "current":
            self.projection.current = None
        snapshot = self.projection.bootstrap(self.client)
        self._configure_runtime(snapshot)
        return self._publish_snapshot(snapshot) if force_publish else snapshot

    def _try_reconnect(self, now: float) -> bool:
        if getattr(self.usb, "connected", False):
            return False
        if self._reconnect_due is None:
            self._disconnect("offline", now)
        if self._reconnect_due is None or now < self._reconnect_due:
            return False
        self._reconnect_due = None
        try:
            self.usb.connect()
            self._link_status = "current"
            self._link_observed_at = now
            self._rebuild_after_connect(force_publish=True)
        except Exception as exc:
            self._fence_disconnected("offline" if "socket" in str(exc).lower() else "unavailable")
            try:
                self.usb.close()
            except Exception:
                pass
            self._schedule_reconnect(now)
            return False
        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY_SECONDS
        self._reconnect_due = None
        return True

    def bootstrap(self) -> Any:
        self._clear_pending_focus()
        verify_contract_inputs(self.contract_root)
        try:
            before = getattr(self.projection, "snapshot_revision", 0)
            snapshot = self.projection.bootstrap(self.client)
            self._herdr_observed_at = self._clock()
            self._collect_codex()
            self.usb.connect()
            self._link_status = "current"
            self._link_observed_at = self._clock()
            self._configure_runtime(snapshot)
            if getattr(snapshot, "snapshot_revision", before) != before:
                self._publish_snapshot(snapshot)
            return getattr(self.projection, "current", snapshot)
        except Exception as exc:
            self._mark_unavailable("offline" if "socket" in str(exc).lower() else "unavailable")
            if isinstance(exc, V2ProtocolError):
                raise
            raise V2ProtocolError("bootstrap_failed", str(exc)) from exc

    def _focus_intent_from_frame(self, frame: Mapping[str, Any]) -> FocusIntent | None:
        if frame.get("type") != "focus_intent":
            return None
        intent_payload = frame.get("payload")
        validate_v2_payload("focus_intent", intent_payload)
        if not self.ready or self.focus is None:
            if self.focus is not None:
                self._defer_focus(frame)
            return None
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
        return FocusIntent(intent_payload["action_id"], incoming)

    def _finish_focus(
        self,
        intent: FocusIntent,
        outcome: Any,
        *,
        generation: int | None = None,
        session_id: str | None = None,
    ) -> Any:
        if (
            generation is not None
            and (
                generation != self._focus_generation
                or session_id != getattr(self.usb, "session_id", None)
                or not self.ready
            )
        ):
            return None
        result = _wire_focus_result(intent, outcome)
        self.last_focus = {
            "status": getattr(outcome, "status", "failed"),
            "focused": bool(getattr(outcome, "success", False)),
            "slot": intent.binding.slot,
            "entry_id": intent.binding.entry_id,
            "snapshot_revision": intent.binding.snapshot_revision,
        }
        self.usb.send_focus_result(result.as_payload())
        self._focus_result_grace_until = self._clock() + FOCUS_RESULT_GRACE_SECONDS
        if outcome.status == "source_revision_changed":
            if self._focus_jobs:
                self._dirty = True
            else:
                self._publish_refresh()
        return outcome

    def _execute_focus(self, intent: FocusIntent, executor: Any | None = None) -> Any:
        from .focus import FocusOutcome
        try:
            target = executor if executor is not None else self.focus
            assert target is not None
            return target.execute(intent)
        except Exception as exc:
            return FocusOutcome("failed", intent.action_id, str(exc)[:160] or "focus worker failed")


    def _drain_focus_jobs(self) -> None:
        while self._focus_jobs and self._focus_jobs[0][0].done():
            future, intent, generation, session_id = self._focus_jobs.pop(0)
            if (
                generation != self._focus_generation
                or session_id != getattr(self.usb, "session_id", None)
                or not self.ready
            ):
                continue
            self._finish_focus(intent, future.result(), generation=generation, session_id=session_id)

    def _queue_focus_frame(self, frame: Mapping[str, Any]) -> bool:
        intent = self._focus_intent_from_frame(frame)
        if intent is None:
            return False
        capacity = max(1, int(getattr(self.usb, "pending_focus_capacity", 16)))
        if len(self._focus_jobs) >= capacity:
            return False
        generation = self._focus_generation
        session_id = getattr(self.usb, "session_id", None)
        executor = self.focus
        self._focus_jobs.append(
            (
                self._focus_pool.submit(self._execute_focus, intent, executor),
                intent,
                generation,
                session_id,
            )
        )
        return True

    def handle_frame(self, frame: Mapping[str, Any]) -> Any:
        intent = self._focus_intent_from_frame(frame)
        if intent is None:
            return None
        outcome = self._execute_focus(intent)
        return self._finish_focus(intent, outcome)

    def _refresh_if_dirty(self, now: float) -> Any:
        if not self._dirty:
            return None
        if self._focus_jobs:
            self._follow_up = True
            return None
        if now < self._focus_result_grace_until:
            self._follow_up = True
            return None
        if self._refresh_active:
            self._follow_up = True
            return None
        self._dirty = False
        self._refresh_active = True
        try:
            return self._publish_refresh()
        except Exception as exc:
            self._disconnect("offline" if "socket" in str(exc).lower() else "stale", now)
            return None
        finally:
            self._refresh_active = False
            if self._follow_up:
                self._follow_up = False
                self._dirty = True

    def _consume_events(self, now: float) -> None:
        stream = self._event_stream
        if self.intake_mode == "push" and stream is not None:
            for _ in range(16):
                event = stream.poll()
                if event is None:
                    break
                self.invalidation_count += 1
                self._dirty = True
            if getattr(stream, "mode", "push") != "push":
                self._clear_pending_focus()
                self.ready = False
                self.intake_mode = "poll"
                self._reestablish_attempts = 0
                self._last_reestablish = now
        if self.intake_mode == "poll":
            if now - self._last_event_refresh >= 1.0:
                self._last_event_refresh = now
                self._dirty = True
                if stream is not None and self._reestablish_attempts < 3 and now - self._last_reestablish >= 1.0:
                    self._last_reestablish = now
                    self._reestablish_attempts += 1
                    mode = stream.probe(deadline_seconds=min(1.0, getattr(self.client, "timeout", 1.0)))
                    if mode == "push":
                        self.intake_mode = "push"
                        self._reestablish_attempts = 0
                        self._dirty = True

    def run_once(self) -> Any:
        now = self._clock()
        if not getattr(self.usb, "connected", False):
            self._try_reconnect(now)
            return None
        self._drain_focus_jobs()
        self._consume_events(now)
        try:
            frame = self.usb.poll()
            if frame is not None and frame.get("type") == "focus_intent":
                self._queue_focus_frame(frame)
        except Exception:
            self._disconnect("offline", now)
            return None
        self._drain_focus_jobs()
        if self.codex_collector is not None:
            due = getattr(self.codex_collector, "should_poll", None)
            if callable(due) and due(now):
                self.refresh_codex()
        return self._refresh_if_dirty(now)

    def run(self, *, interval: float = 0.1, bootstrapped: bool = False) -> None:
        from .usb import UsbSessionError

        if not bootstrapped:
            try:
                self.bootstrap()
            except V2ProtocolError as exc:
                if exc.reason not in {"bootstrap_failed", "snapshot_rejected"}:
                    raise
                self._disconnect("unavailable", self._clock())
            except UsbSessionError:
                self._disconnect("offline", self._clock())
        try:
            while True:
                try:
                    self.run_once()
                except V2ProtocolError:
                    self._disconnect("unavailable", self._clock())
                except UsbSessionError:
                    self._disconnect("offline", self._clock())
                time.sleep(interval)
        except KeyboardInterrupt:
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
            "schema_sha256": _sha256(_ROOT / "protocol/schema/v2.json"),
            "fixture_sha256": _sha256(_ROOT / "protocol/fixtures/v2-golden.json"),
            "firmware_lock_sha256": _sha256(_ROOT / "artifacts/phase1/locks/final-build-gap-closure.json"),
            "firmware_binary_sha256": _sha256(_ROOT / ".pio/build/selected-usb/firmware.bin"),
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
def write_live_sync_evidence(path: Path, *, result: str, duration_seconds: float,
                             initial: Any, changed: Any | None, focus: Mapping[str, Any] | None,
                             metrics: Mapping[str, Any] | None, bridge: PermanentBridge,
                             error: str = "") -> Path:
    """Atomically write bounded smoke facts and a separately hashed sidecar."""
    def generation(snapshot: Any | None) -> Any:
        if snapshot is None:
            return None
        return {
            "host_epoch": snapshot.host_epoch,
            "snapshot_revision": snapshot.snapshot_revision,
            "source_status": snapshot.source_status,
            "slots": [
                {
                    "slot": entry.slot,
                    "entry_id": entry.entry_id,
                    "title": entry.title,
                    "discriminator": entry.discriminator,
                    "state": entry.state,
                    "pane_id": entry.identity.pane_id if entry.identity else "",
                    "source_revision": entry.identity.source_revision if entry.identity else 0,
                }
                for entry in snapshot.entries
            ],
        }
    safe_metrics = {}
    if metrics is not None:
        for key in ("max_display_flush_us", "minimum_free_heap", "max_key_poll_gap_us", "parser_high_water", "queue_high_water"):
            value = metrics.get(key)
            if isinstance(value, int) and value >= 0:
                safe_metrics[key] = value
    record = {
        "schema_version": 1,
        "result": result,
        "duration_seconds": max(0.0, min(float(duration_seconds), 30.0)),
        "initial_generation": generation(initial),
        "changed_generation": generation(changed),
        "focus": dict(focus or {"focused": False}),
        "metrics": safe_metrics,
        "counters": {
            "invalidations": bridge.invalidation_count,
            "publications": bridge.publication_count,
            "ready_transitions": bridge.ready_transitions,
            "intake_mode": bridge.intake_mode,
        },
    }
    if error:
        record["reason"] = str(error)[:160]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    digest = _sha256(path)
    checksum = path.with_suffix(".sha256")
    checksum_tmp = checksum.with_name(f".{checksum.name}.tmp")
    checksum_tmp.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    os.replace(checksum_tmp, checksum)
    if _sha256(path) != checksum.read_text(encoding="ascii").split()[0]:
        raise V2ProtocolError("evidence_hash", "live smoke evidence checksum reopen failed")

def _canonical_sha256(value: Mapping[str, Any]) -> str:
    import hashlib

    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_codex_tracer_evidence(
    path: Path,
    *,
    result: str,
    codex: CodexResult | None,
    hello: Mapping[str, Any] | None,
    deployment: Mapping[str, Any],
    error_code: str = "",
    device_ack: Mapping[str, Any] | None = None,
    rendered_frame: Mapping[str, Any] | None = None,
) -> Path:
    """Persist closed, installed-Codex tracer facts and re-open their checksum."""
    if result not in {"pass", "fail"}:
        raise V2ProtocolError("evidence_result", "Codex tracer result is not typed")
    hello = hello or {}
    hello_record = {
        "device_id": hello.get("device_id") if isinstance(hello.get("device_id"), str) else "unavailable",
        "firmware": hello.get("firmware") if isinstance(hello.get("firmware"), str) else "unavailable",
        "protocol": hello.get("protocol") if isinstance(hello.get("protocol"), int) else None,
        "boot_id": hello.get("boot_id") if isinstance(hello.get("boot_id"), str) else "unavailable",
        "session_id": hello.get("session_id") if isinstance(hello.get("session_id"), str) else "unavailable",
    }
    deployment_record = {
        "platformio_environment": str(deployment.get("environment", "selected-usb"))[:32],
        "binary_sha256": str(deployment.get("firmware_sha256", "unavailable"))[:64],
        "hello_firmware": hello_record["firmware"],
        "paired_device_id": hello_record["device_id"],
        "fresh_boot_id": hello_record["boot_id"],
        "fresh_session_id": hello_record["session_id"],
        "upload_result": str(deployment.get("upload", "unavailable"))[:16],
    }
    deployment_record["deployment_id"] = _canonical_sha256(deployment_record)
    collector = codex.as_evidence() if codex is not None else {
        "deadline_ms": 0,
        "elapsed_ms": 0,
        "child_exit": {"state": "not_started", "code": None, "signal": None},
        "handshake": [],
        "account_observed": False,
        "rate_limits_observed": False,
        "redaction": Redaction(result="fail").as_dict(),
    }
    redaction = collector["redaction"]
    ack = device_ack or {"available": False, "accepted": None}
    frame = rendered_frame or {"available": False, "source": "device-frame-not-returned"}
    record = {
        "kind": "phase3-codex-tracer",
        "schema_version": 1,
        "result": result,
        "source": {"live": "installed", "fixtures": "separate-scripted-tests"},
        "deployment": deployment_record,
        "hello": hello_record,
        "codex": codex.view.as_payload() if codex is not None else CodexView().as_payload(),
        "collector": collector,
        "redaction": redaction,
        "device_ack": {
            "available": bool(ack.get("available", False)),
            "accepted": ack.get("accepted") if isinstance(ack.get("accepted"), bool) else None,
            "snapshot_revision": ack.get("snapshot_revision") if isinstance(ack.get("snapshot_revision"), int) else None,
        },
        "rendered_frame": {
            "available": bool(frame.get("available", False)),
            "source": str(frame.get("source", "unavailable"))[:32],
        },
        "final_evidence_refs": {
            "elapsed_ms": "/collector/elapsed_ms",
            "child_exit": "/collector/child_exit",
            "redaction_result": "/redaction/result",
        },
        "error_code": error_code[:16],
    }
    from .codex import redaction_passes
    if not redaction_passes(record):
        raise V2ProtocolError("evidence_redaction", "Codex tracer evidence contains rejected fields")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    digest = _sha256(path)
    checksum = Path(str(path) + ".sha256")
    checksum_tmp = checksum.with_name(f".{checksum.name}.tmp")
    checksum_tmp.write_text(f"{digest}  {path.as_posix() if not path.is_absolute() else path.name}\n", encoding="ascii")
    os.replace(checksum_tmp, checksum)
    if _sha256(path) != checksum.read_text(encoding="ascii").split()[0]:
        raise V2ProtocolError("evidence_hash", "Codex tracer evidence checksum reopen failed")
    return path
