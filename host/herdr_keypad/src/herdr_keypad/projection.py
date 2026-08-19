"""Installed herdr-agent-inbox projection and lifecycle handling."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .herdr import HerdrClient, HerdrError
from .bridge import Identity
MAX_SLOTS = 3
MAX_TEXT = 64
MAX_DISCRIMINATOR = 32
PLUGIN_REVISION = "78b243279b4da55150b58dc2cc3cffcdc2fd6a04"
PLUGIN_PATH = "/home/nnex/.config/herdr/plugins/github/herdr-agent-inbox-de409f683262"
SOURCE_STATUSES = {"current", "empty", "stale", "unavailable", "offline"}
RANK_STATES = {0: "blocked", 1: "finished", 2: "working", 3: "idle", 4: "unknown", 5: "settled"}


class ProjectionUnavailable(RuntimeError):
    """The installed source is incomplete, incompatible, or currently absent."""



@dataclass(frozen=True)
class ProjectedEntry:
    slot: int
    entry_id: str
    title: str
    discriminator: str
    since: str
    age: str
    state: str
    rank: int | None
    state_change_seq: int
    identity: Identity | None
    stale: bool = False

    @property
    def occupied(self) -> bool:
        return self.identity is not None and self.state not in {"empty", "unavailable"}

    @classmethod
    def empty(cls, slot: int, state: str = "empty", *, stale: bool = False) -> "ProjectedEntry":
        return cls(slot, "", "NO AGENT", "NO WORKSPACE", "", "", state, None, 0, None, stale)


@dataclass(frozen=True)
class ProjectionSnapshot:
    host_epoch: str
    snapshot_revision: int
    source_status: str
    entries: tuple[ProjectedEntry, ...]
    plugin_revision: str = PLUGIN_REVISION
    schema_version: int = 1

    @property
    def actionable(self) -> bool:
        return self.source_status == "current" and any(entry.occupied and not entry.stale for entry in self.entries)



def _text(value: Any, name: str, maximum: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) >= 128 or ord(c) < 0x20 for c in value):
        raise ProjectionUnavailable(f"{name} is not bounded ASCII text")
    if not allow_empty and not value:
        raise ProjectionUnavailable(f"{name} is required")
    return value


def _opaque(value: Any, name: str, *, allow_empty: bool = False) -> str:
    result = _text(value, name, MAX_TEXT, allow_empty=allow_empty)
    if any(c in "\r\n\t" for c in result):
        raise ProjectionUnavailable(f"{name} contains control bytes")
    return result


def _uint(value: Any, name: str, *, allow_zero: bool = False) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < (0 if allow_zero else 1) or value > 0xFFFFFFFF:
        raise ProjectionUnavailable(f"{name} is not a bounded integer")
    return value
def _session_token(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _opaque(value, "agent_session")
    if isinstance(value, Mapping):
        pieces = [value.get(key) for key in ("source", "agent", "kind")]
        if all(isinstance(piece, str) and piece for piece in pieces):
            return _opaque(":".join(pieces), "agent_session")
    raise ProjectionUnavailable("agent_session is not a bounded identity")



def _repo_basename(cwd: Any) -> str | None:
    if not isinstance(cwd, str) or not cwd:
        return None
    name = os.path.basename(cwd.rstrip("/"))
    if not name or name in {".", ".."}:
        return None
    try:
        return _text(name, "repository", MAX_DISCRIMINATOR)
    except ProjectionUnavailable:
        return None


class InboxProjection:
    """Normalize only the installed plugin's rank/sequence contract."""

    def __init__(self, *, plugin_revision: str = PLUGIN_REVISION, schema_version: int = 1,
                 host_epoch: str = "host-epoch") -> None:
        self.plugin_revision = plugin_revision
        self.schema_version = schema_version
        self.host_epoch = _opaque(host_epoch, "host_epoch")
        self.snapshot_revision = 0
        self.current: ProjectionSnapshot | None = None
        self._last_entries: tuple[ProjectedEntry, ...] = tuple(ProjectedEntry.empty(i) for i in range(MAX_SLOTS))
        self._last_projection_key: tuple[Any, ...] | None = None
        self._last_workspace_labels: dict[str, str] = {}
    def _workspace_labels(self, workspaces: Iterable[Mapping[str, Any]]) -> dict[str, str]:
        labels: dict[str, str] = {}
        for workspace in workspaces:
            workspace_id = workspace.get("workspace_id")
            if not isinstance(workspace_id, str) or not workspace_id:
                continue
            label = workspace.get("label") or workspace.get("name")
            if isinstance(label, str) and label:
                try:
                    labels[workspace_id] = _text(label, "workspace label", MAX_DISCRIMINATOR)
                except ProjectionUnavailable:
                    continue
        return labels

    def _normalize(self, row: Mapping[str, Any], labels: Mapping[str, str]) -> ProjectedEntry:
        required = ("pane_id", "terminal_id", "workspace_id", "tab_id", "agent_status", "focused", "revision")
        if any(key not in row for key in required):
            raise ProjectionUnavailable("agent row is missing required identity fields")
        pane_id = _opaque(row.get("pane_id"), "pane_id")
        terminal_id = _opaque(row.get("terminal_id"), "terminal_id")
        workspace_id = _opaque(row.get("workspace_id"), "workspace_id")
        tab_id = _opaque(row.get("tab_id"), "tab_id")
        revision = _uint(row.get("revision"), "revision")
        if not isinstance(row.get("focused"), bool):
            raise ProjectionUnavailable("focused must be boolean")
        status = row.get("agent_status")
        if not isinstance(status, str) or not status:
            raise ProjectionUnavailable("agent_status is required")
        tokens = row.get("tokens")
        if not isinstance(tokens, Mapping) or "rank" not in tokens:
            raise ProjectionUnavailable("missing rank makes inbox unavailable")
        rank_value = tokens.get("rank")
        if not isinstance(rank_value, str) or rank_value not in {str(i) for i in range(6)}:
            raise ProjectionUnavailable("rank must be the installed literal 0..5 token")
        rank = int(rank_value)
        state_change_seq = _uint(row.get("state_change_seq"), "state_change_seq", allow_zero=True)
        title_value = row.get("title") or tokens.get("title") or row.get("terminal_title_stripped") or row.get("agent")
        if not isinstance(title_value, str):
            raise ProjectionUnavailable("title is required")
        title_value = title_value.encode("ascii", "ignore").decode("ascii").strip() or "UNKNOWN AGENT"
        title = _text(title_value, "title", MAX_TEXT)
        workspace_label = labels.get(workspace_id)
        discriminator = workspace_label or _repo_basename(row.get("cwd")) or "NO WORKSPACE"
        discriminator = _text(discriminator, "discriminator", MAX_DISCRIMINATOR)
        since_value = tokens.get("since", "-")
        age_value = tokens.get("age", "-")
        since = _text(since_value if isinstance(since_value, str) and since_value else "-", "since", 16)
        age = _text(age_value if isinstance(age_value, str) and age_value else "-", "age", 16)
        session = _session_token(row.get("agent_session"))
        identity = Identity(pane_id, terminal_id, session, revision, workspace_id, tab_id)
        return ProjectedEntry(-1, pane_id, title, discriminator, since, age, RANK_STATES[rank], rank, state_change_seq, identity)

    @staticmethod
    def _same_logical_entry(left: ProjectedEntry, right: ProjectedEntry) -> bool:
        if left.identity is None or right.identity is None:
            return left == right
        left_identity = left.identity
        right_identity = right.identity
        return (
            left.slot,
            left.entry_id,
            left.title,
            left.discriminator,
            left.since,
            left.age,
            left.state,
            left.rank,
            left.state_change_seq,
            left.stale,
            left_identity.pane_id,
            left_identity.terminal_id,
            left_identity.agent_session,
            left_identity.workspace_id,
            left_identity.tab_id,
        ) == (
            right.slot,
            right.entry_id,
            right.title,
            right.discriminator,
            right.since,
            right.age,
            right.state,
            right.rank,
            right.state_change_seq,
            right.stale,
            right_identity.pane_id,
            right_identity.terminal_id,
            right_identity.agent_session,
            right_identity.workspace_id,
            right_identity.tab_id,
        )

    def _project_entries(
        self, rows: Iterable[Mapping[str, Any]], labels: Mapping[str, str]
    ) -> tuple[ProjectedEntry, ...]:
        try:
            normalized = [self._normalize(row, labels) for row in rows]
        except (TypeError, ValueError) as exc:
            raise ProjectionUnavailable("incomplete inbox bootstrap") from exc
        normalized.sort(key=lambda entry: (entry.rank if entry.rank is not None else 99, -entry.state_change_seq))
        normalized = normalized[:MAX_SLOTS]
        entries = tuple(
            ProjectedEntry(
                index,
                entry.entry_id,
                entry.title,
                entry.discriminator,
                entry.since,
                entry.age,
                entry.state,
                entry.rank,
                entry.state_change_seq,
                entry.identity,
            )
            for index, entry in enumerate(normalized)
        ) + tuple(ProjectedEntry.empty(index) for index in range(len(normalized), MAX_SLOTS))
        if len(entries) != MAX_SLOTS:
            raise ProjectionUnavailable("projection did not produce fixed positions")
        if self.current is None:
            return entries

        stabilized: list[ProjectedEntry] = []
        for candidate, committed in zip(entries, self.current.entries):
            if (
                candidate.identity is not None
                and committed.identity is not None
                and self._same_logical_entry(candidate, committed)
            ):
                identity = candidate.identity
                candidate = ProjectedEntry(
                    candidate.slot,
                    candidate.entry_id,
                    candidate.title,
                    candidate.discriminator,
                    candidate.since,
                    candidate.age,
                    candidate.state,
                    candidate.rank,
                    candidate.state_change_seq,
                    Identity(
                        identity.pane_id,
                        identity.terminal_id,
                        identity.agent_session,
                        committed.identity.source_revision,
                        identity.workspace_id,
                        identity.tab_id,
                    ),
                    candidate.stale,
                )
            stabilized.append(candidate)
        return tuple(stabilized)

    def matches_current(self, rows: Iterable[Mapping[str, Any]]) -> bool:
        """Return whether live rows still describe the exact committed generation."""
        if self.current is None or self.current.source_status != "current":
            return False
        entries = self._project_entries(list(rows), self._last_workspace_labels)
        projection_key = (entries, "current", self.plugin_revision, self.schema_version)
        return projection_key == self._last_projection_key

    def refresh(self, rows: Iterable[Mapping[str, Any]], workspaces: Iterable[Mapping[str, Any]] = (), *,
                source_status: str = "current", plugin_revision: str | None = None,
                schema_version: int | None = None) -> ProjectionSnapshot:
        if source_status not in SOURCE_STATUSES:
            raise ProjectionUnavailable("unknown source status")
        if plugin_revision is not None and plugin_revision != self.plugin_revision:
            raise ProjectionUnavailable("incompatible plugin revision")
        if schema_version is not None and schema_version != self.schema_version:
            raise ProjectionUnavailable("incompatible Herdr schema")
        labels = self._workspace_labels(workspaces)
        entries = self._project_entries(list(rows), labels)
        projection_key = (entries, source_status, self.plugin_revision, self.schema_version)
        self._last_workspace_labels = dict(labels)
        if self.current is not None and projection_key == self._last_projection_key:
            return self.current
        self.snapshot_revision += 1
        snapshot = ProjectionSnapshot(self.host_epoch, self.snapshot_revision, source_status, entries,
                                      self.plugin_revision, self.schema_version)
        self.current = snapshot
        self._last_entries = entries
        self._last_projection_key = projection_key
        return snapshot

    def bootstrap(self, client: HerdrClient, *, source_status: str = "current") -> ProjectionSnapshot:
        """Read public bootstrap methods; events are invalidation triggers only."""
        try:
            client.session_snapshot()
            rows = client.agent_list()
            workspaces = client.workspace_list()
        except HerdrError as exc:
            return self.invalidate("offline")
        return self.refresh(rows, workspaces, source_status=source_status)

    def invalidate(self, reason: str = "stale") -> ProjectionSnapshot:
        if reason not in {"stale", "offline", "unavailable"}:
            reason = "stale"
        self.snapshot_revision += 1
        entries = tuple(
            ProjectedEntry(entry.slot, entry.entry_id, entry.title, entry.discriminator, entry.since, entry.age,
                           reason, entry.rank, entry.state_change_seq, entry.identity, stale=True)
            if entry.identity is not None else ProjectedEntry.empty(entry.slot, reason)
            for entry in self._last_entries
        )
        self.current = ProjectionSnapshot(self.host_epoch, self.snapshot_revision, reason, entries,
                                          self.plugin_revision, self.schema_version)
        return self.current

    def complete_refresh_required(self) -> bool:
        return self.current is None or self.current.source_status != "current" or any(entry.stale for entry in self.current.entries)

    def binding(self, slot: int):
        if self.current is None or not 0 <= slot < MAX_SLOTS:
            return None
        entry = self.current.entries[slot]
        if not self.current.actionable or not entry.occupied or entry.stale or entry.identity is None:
            return None
        from .bridge import Binding
        return Binding(self.current.host_epoch, self.current.snapshot_revision, slot, entry.entry_id, entry.identity)
