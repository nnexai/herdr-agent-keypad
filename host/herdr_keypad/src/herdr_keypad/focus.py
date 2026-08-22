"""Fail-closed, focus-only execution for an exact displayed binding."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .bridge import Binding, FocusIntent
from .herdr import HerdrClient, HerdrError
from .projection import InboxProjection, _session_token
OUTCOME_NAMES = {
    "accepted", "empty", "stale", "offline", "incompatible", "wrong_epoch", "wrong_revision",
    "wrong_slot", "pane_reused", "session_changed", "source_revision_changed", "vanished",
    "rejected", "uncertain", "failed",
}


@dataclass(frozen=True)
class FocusOutcome:
    status: str
    action_id: str
    reason: str = ""
    agent_info: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in OUTCOME_NAMES:
            raise ValueError(f"unknown focus outcome {self.status}")

    @property
    def success(self) -> bool:
        return self.status == "accepted"


class FocusExecutor:
    """The sole device-action dispatcher; it can emit only ``agent.focus``."""

    def __init__(self, client: HerdrClient, projection: InboxProjection, *, device_session: str | None = None) -> None:
        self.client = client
        self.projection = projection
        self.device_session = device_session

    def _reject(self, status: str, intent: FocusIntent, reason: str, agent_info: Mapping[str, Any] | None = None) -> FocusOutcome:
        return FocusOutcome(status, intent.action_id, reason, agent_info)

    @staticmethod
    def _agent_result(response: Any) -> Mapping[str, Any] | None:
        if not isinstance(response, Mapping):
            return None
        if response.get("type") == "agent_info" and isinstance(response.get("agent"), Mapping):
            return response["agent"]
        for key in ("agent_info", "agent"):
            if isinstance(response.get(key), Mapping):
                return response[key]
        if "pane_id" in response and "terminal_id" in response:
            return response
        return None

    @staticmethod
    def _same_identity(agent: Mapping[str, Any], binding: Binding) -> str | None:
        if agent.get("pane_id") != binding.identity.pane_id:
            return "pane_reused"
        if agent.get("terminal_id") != binding.identity.terminal_id:
            return "pane_reused"
        if binding.identity.workspace_id and agent.get("workspace_id") != binding.identity.workspace_id:
            return "pane_reused"
        if binding.identity.tab_id and agent.get("tab_id") != binding.identity.tab_id:
            return "pane_reused"
        try:
            current_session = _session_token(agent.get("agent_session"))
        except Exception:
            return "session_changed"
        if current_session != binding.identity.agent_session:
            return "session_changed"
        return None

    def execute(self, intent: FocusIntent) -> FocusOutcome:
        """Validate the typed intent, then make one exact public focus call."""
        if not isinstance(intent, FocusIntent):
            raise TypeError("FocusExecutor accepts a typed FocusIntent")
        binding = intent.binding
        current = self.projection.current
        if current is None:
            return self._reject("offline", intent, "no committed projection")
        if current.source_status in {"offline", "unavailable"}:
            return self._reject(current.source_status, intent, "source is not current")
        if current.source_status == "stale" or any(entry.stale for entry in current.entries):
            return self._reject("stale", intent, "projection generation is stale")
        if self.device_session is not None and getattr(intent, "device_session", self.device_session) != self.device_session:
            return self._reject("wrong_epoch", intent, "device session differs")
        if binding.host_epoch != current.host_epoch:
            return self._reject("wrong_epoch", intent, "host epoch differs")
        if not 0 <= binding.slot < len(current.entries):
            return self._reject("wrong_slot", intent, "slot is outside fixed projection")
        if binding.entry_id != binding.identity.pane_id:
            return self._reject("pane_reused", intent, "entry and pane identity differ")
        try:
            rows = self.client.agent_list()
        except HerdrError as exc:
            text = str(exc).lower()
            return self._reject("uncertain" if "timeout" in text else "offline", intent, str(exc))
        agent = next((row for row in rows if row.get("pane_id") == binding.identity.pane_id), None)
        if agent is None:
            return self._reject("vanished", intent, "pane is absent from current agent.list")
        mismatch = self._same_identity(agent, binding)
        if mismatch is not None:
            return self._reject(mismatch, intent, "current AgentInfo identity differs")
        # Inbox ordering, status, and state_change_seq may change immediately
        # after a prior focus. Those mutable projection fields must not turn a
        # subsequent physical press into downtime. The live immutable identity
        # check above is the focus authorization boundary.
        try:
            response = self.client.focus(binding.identity.pane_id)
        except HerdrError as exc:
            text = str(exc).lower()
            if "not_found" in text or "agent_not_found" in text:
                return self._reject("vanished", intent, str(exc))
            return self._reject("uncertain" if "timeout" in text else "failed", intent, str(exc))
        focused = self._agent_result(response)
        if focused is None:
            return self._reject("rejected", intent, "focus response is not AgentInfo")
        mismatch = self._same_identity(focused, binding)
        if mismatch is not None:
            return self._reject(mismatch, intent, "focus acknowledgement identity differs", focused)
        if focused.get("focused") is not True:
            try:
                retry_response = self.client.focus(binding.identity.pane_id)
            except HerdrError as exc:
                text = str(exc).lower()
                if "not_found" in text or "agent_not_found" in text:
                    return self._reject("vanished", intent, str(exc))
                return self._reject("uncertain" if "timeout" in text else "failed", intent, str(exc))
            retry_focused = self._agent_result(retry_response)
            if retry_focused is None:
                return self._reject("rejected", intent, "focus retry response is not AgentInfo")
            mismatch = self._same_identity(retry_focused, binding)
            if mismatch is not None:
                return self._reject(mismatch, intent, "focus retry identity differs", retry_focused)
            focused = retry_focused
        if focused.get("focused") is not True:
            return self._reject("rejected", intent, "AgentInfo is not focused", focused)
        return FocusOutcome("accepted", intent.action_id, "agent.focus acknowledged", focused)
