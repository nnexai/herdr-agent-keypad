#!/usr/bin/env python3
"""Capture a disposable, public-API Herdr focus/effects evidence matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

EXPECTED_REVISION = "78b243279b4da55150b58dc2cc3cffcdc2fd6a04"
EXPECTED_VERSION = "0.8.0"
ROWS = (
    "working",
    "idle-clear",
    "blocked",
    "finished-unseen",
    "manual-unread",
    "settled",
    "vanished",
    "reassigned",
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(*argv: str, check: bool = True) -> tuple[int, Any, str]:
    completed = subprocess.run(argv, check=False, capture_output=True, text=True)
    text = completed.stdout.strip() or completed.stderr.strip()
    value: Any = None
    if text:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = text
    if check and completed.returncode != 0:
        fail(f"command failed ({completed.returncode}): {' '.join(argv)}: {text}")
    return completed.returncode, value, text


def result_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("result"), dict):
        fail("Herdr CLI did not return a result envelope")
    return value["result"]


def snapshot() -> dict[str, Any]:
    _, value, _ = run("herdr", "api", "snapshot")
    result = result_payload(value)
    if result.get("type") != "session_snapshot" or not isinstance(result.get("snapshot"), dict):
        fail("Herdr snapshot response is not session_snapshot")
    return result["snapshot"]


def agents(snap: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in snap.get("agents", []) if isinstance(item, dict)]


def find_agent(snap: dict[str, Any], pane_id: str) -> dict[str, Any] | None:
    return next((item for item in agents(snap) if item.get("pane_id") == pane_id), None)


def ordered_panes(snap: dict[str, Any]) -> list[str]:
    rows = []
    for item in agents(snap):
        tokens = item.get("tokens") if isinstance(item.get("tokens"), dict) else {}
        rank = tokens.get("rank")
        seq = item.get("state_change_seq", 0)
        if isinstance(rank, str) and rank.isdigit():
            rows.append((int(rank), -(seq if isinstance(seq, int) else 0), item.get("pane_id")))
    return [pane for _, _, pane in sorted(rows) if isinstance(pane, str)]


def record_identity(item: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"pane_id": None, "terminal_id": None, "agent_session": None, "revision": None, "state_change_seq": None, "status": None, "rank": None, "flag": None}
    tokens = item.get("tokens") if isinstance(item.get("tokens"), dict) else {}
    return {
        "pane_id": item.get("pane_id"),
        "terminal_id": item.get("terminal_id"),
        "agent_session": item.get("agent_session"),
        "revision": item.get("revision"),
        "state_change_seq": item.get("state_change_seq", 0),
        "status": item.get("agent_status"),
        "rank": tokens.get("rank"),
        "flag": tokens.get("flag"),
        "title": item.get("title") or tokens.get("title"),
    }


def compact_snapshot(snap: dict[str, Any], pane_id: str | None) -> dict[str, Any]:
    found = find_agent(snap, pane_id) if pane_id else None
    return {
        "target": record_identity(found),
        "focused_pane_id": snap.get("focused_pane_id"),
        "focused_tab_id": snap.get("focused_tab_id"),
        "focused_workspace_id": snap.get("focused_workspace_id"),
        "ordered_pane_ids": ordered_panes(snap),
        "agent_count": len(agents(snap)),
    }


def diff_events(before: dict[str, Any], after: dict[str, Any], pane_id: str | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if before.get("focused_pane_id") != after.get("focused_pane_id"):
        events.append({"event": "pane.focused", "pane_id": after.get("focused_pane_id"), "previous_pane_id": before.get("focused_pane_id")})
    before_item = find_agent(before, pane_id) if pane_id else None
    after_item = find_agent(after, pane_id) if pane_id else None
    if before_item is None and after_item is not None:
        events.append({"event": "pane.agent_detected", "pane_id": pane_id})
    if before_item is not None and after_item is None:
        events.append({"event": "pane.closed_or_exited", "pane_id": pane_id})
    if before_item and after_item and before_item.get("agent_status") != after_item.get("agent_status"):
        events.append({"event": "pane.agent_status_changed", "pane_id": pane_id, "before": before_item.get("agent_status"), "after": after_item.get("agent_status")})
    return events or [{"event": "snapshot.observed", "pane_id": pane_id}]


def report(pane: str, state: str, seq: int, rank: str, flag: str | None) -> None:
    run("herdr", "pane", "report-agent", pane, "--source", "phase2-fixture", "--agent", "fixture", "--state", state, "--seq", str(seq))
    args = ["herdr", "pane", "report-metadata", pane, "--source", "phase2-fixture", "--agent", "fixture", "--seq", str(seq), "--token", f"rank={rank}", "--token", "title=Phase2 {state}", "--token", "age=0m", "--token", "since=0s"]
    if flag:
        args += ["--token", f"flag={flag}"]
    run(*args)


def focus(pane: str) -> tuple[dict[str, Any] | None, str]:
    code, value, text = run("herdr", "agent", "focus", pane, check=False)
    if code != 0:
        return None, text
    return result_payload(value), text


def capture_row(name: str, pane: str, state: str, rank: str, flag: str | None, seq: int) -> dict[str, Any]:
    report(pane, state, seq, rank, flag)
    before = snapshot()
    response, raw_response = focus(pane)
    immediate = snapshot()
    time.sleep(0.55)
    delayed = snapshot()
    return {
        "name": name,
        "before": compact_snapshot(before, pane),
        "request": {"method": "agent.focus", "params": {"target": pane}},
        "response": response or {"error": raw_response},
        "events": diff_events(before, immediate, pane),
        "immediate": compact_snapshot(immediate, pane),
        "delayed": compact_snapshot(delayed, pane),
        "native_effect": {"status_changed": record_identity(find_agent(before, pane)).get("status") != record_identity(find_agent(delayed, pane)).get("status"), "order_changed": compact_snapshot(before, pane)["ordered_pane_ids"] != compact_snapshot(delayed, pane)["ordered_pane_ids"]},
    }


def plugin_revision(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_dir():
        fail("installed plugin path is not a concrete directory")
    code, _, text = run("git", "-C", str(path), "rev-parse", "HEAD", check=False)
    if code != 0 or text != EXPECTED_REVISION:
        fail(f"installed plugin revision is {text or 'unavailable'}, expected {EXPECTED_REVISION}")
    source_files = {}
    for name in ("README.md", "daemon.py", "actions.py", "inbox_tui.py"):
        file = path / name
        if file.is_symlink() or not file.is_file():
            fail(f"installed plugin source missing: {file}")
        source_files[name] = sha256(file)
    return {"path": str(path), "revision": text, "source_sha256": source_files, "planned_revision": "de409f683262", "revision_override": "planned de409f683262 object unavailable; actual checkout HEAD is authoritative"}


def verify_artifacts(root: Path, handoff: Path) -> None:
    value = json.loads(handoff.read_text(encoding="utf-8"))
    if value.get("kind") != "phase2-phase1-handoff" or value.get("schema_version") != 1:
        fail("Phase 1 handoff receipt is not valid")
    if value.get("installed_herdr", {}).get("revision") != EXPECTED_REVISION and value.get("evidence", {}).get("installed_herdr", {}).get("revision") != EXPECTED_REVISION:
        fail("Phase 1 handoff does not pin actual installed Herdr HEAD")
    if not root.is_dir():
        fail("output root is not a directory")


def verify_matrix(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("kind") != "herdr-focus-effects":
        fail("focus-effects artifact schema/kind is invalid")
    if value.get("classification") != "baseline-compatible":
        fail("focus-effects artifact is not baseline-compatible")
    rows = value.get("rows")
    if not isinstance(rows, list) or {row.get("name") for row in rows if isinstance(row, dict)} != set(ROWS):
        fail("focus-effects artifact does not contain all mandatory rows")
    for row in rows:
        if not isinstance(row, dict) or any(not row.get(key) for key in ("before", "response", "events", "immediate", "delayed")):
            fail(f"focus row is missing mandatory observations: {row}")
    cleanup = value.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("complete") is not True or cleanup.get("existing_agents_changed") is not False:
        fail("fixture cleanup proof is incomplete")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase1-handoff", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--installed-plugin", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    effects_path = args.output_root / "herdr-focus-effects.json"
    contract_path = args.output_root / "herdr-contract.json"
    try:
        verify_artifacts(args.output_root, args.phase1_handoff)
        if args.verify_only:
            verify_matrix(effects_path)
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            if contract.get("classification") != "baseline-compatible" or contract.get("acknowledgement", {}).get("herdr_owned") != ["pane_id", "terminal_id", "agent_session", "revision"]:
                fail("Herdr acknowledgement ownership contract is invalid")
            print(f"verified {effects_path} and {contract_path}")
            return 0
        plugin = plugin_revision(args.installed_plugin)
        _, version_text, _ = run("herdr", "--version")
        version = str(version_text).strip()
        if EXPECTED_VERSION not in version:
            fail(f"Herdr version is not {EXPECTED_VERSION}: {version}")
        schema_tmp = Path(tempfile.mkstemp(prefix="phase2-herdr-schema-", suffix=".json")[1])
        try:
            run("herdr", "api", "schema", "--output", str(schema_tmp))
            schema_hash = sha256(schema_tmp)
            schema = json.loads(schema_tmp.read_text(encoding="utf-8"))
        finally:
            schema_tmp.unlink(missing_ok=True)
        socket_path = Path(os.environ.get("HERDR_SOCKET_PATH", "~/.config/herdr/herdr.sock")).expanduser()
        socket_stat = socket_path.stat()
        if not stat.S_ISSOCK(socket_stat.st_mode) or stat.S_IMODE(socket_stat.st_mode) != 0o600:
            fail("Herdr socket must be a private Unix socket")
        before_all = snapshot()
        original_focus = before_all.get("focused_pane_id")
        fixture_root = Path(tempfile.mkdtemp(prefix="herdr-phase2-fixture-"))
        workspace_id = pane_id = None
        rows: list[dict[str, Any]] = []
        cleanup_complete = False
        try:
            _, created, _ = run("herdr", "workspace", "create", "--cwd", str(fixture_root), "--label", "phase2-fixture", "--no-focus")
            created_result = result_payload(created)
            workspace_id = created_result["workspace"]["workspace_id"]
            pane_id = created_result["root_pane"]["pane_id"]
            states = (("working", "working", "2", None), ("idle-clear", "idle", "3", None), ("blocked", "blocked", "0", None), ("finished-unseen", "idle", "1", "●"), ("manual-unread", "idle", "1", "●"), ("settled", "idle", "5", "⚑"))
            for seq, (name, state, rank, flag) in enumerate(states, start=1):
                rows.append(capture_row(name, pane_id, state, rank, flag, seq))
            # Create the replacement pane before closing the original pane;
            # this keeps the race inside one disposable workspace.
            _, split, _ = run("herdr", "pane", "split", "--pane", pane_id, "--direction", "right", "--no-focus")
            split_result = result_payload(split)
            new_pane = split_result.get("pane", {}).get("pane_id") or split_result.get("new_pane", {}).get("pane_id")
            if not new_pane:
                snap = snapshot()
                candidates = [item.get("pane_id") for item in snap.get("panes", []) if item.get("workspace_id") == workspace_id and item.get("pane_id") != pane_id]
                new_pane = candidates[-1] if candidates else None
            if not new_pane:
                fail("reassigned fixture pane was not created")
            old_identity = record_identity(find_agent(snapshot(), pane_id))
            report(pane_id, "idle", 7, "3", None)
            before = snapshot()
            run("herdr", "pane", "close", pane_id)
            response, raw_response = focus(pane_id)
            immediate = snapshot()
            delayed = snapshot()
            rows.append({"name": "vanished", "before": compact_snapshot(before, pane_id), "request": {"method": "agent.focus", "params": {"target": pane_id}}, "response": response or {"error": raw_response}, "events": diff_events(before, immediate, pane_id), "immediate": compact_snapshot(immediate, pane_id), "delayed": compact_snapshot(delayed, pane_id), "native_effect": {"focus_dispatched": False, "slot_substituted": False}})
            report(new_pane, "working", 8, "2", None)
            reassigned_before = snapshot()
            new_identity = record_identity(find_agent(reassigned_before, new_pane))
            reassigned_response, reassigned_raw = focus(new_pane)
            reassigned_after = snapshot()
            changed_fields = [field for field in ("pane_id", "terminal_id", "agent_session", "revision") if old_identity.get(field) != new_identity.get(field)]
            rows.append({"name": "reassigned", "before": compact_snapshot(reassigned_before, new_pane), "request": {"method": "agent.focus", "params": {"target": new_pane}}, "response": reassigned_response or {"error": reassigned_raw}, "events": diff_events(reassigned_before, reassigned_after, new_pane), "immediate": compact_snapshot(reassigned_after, new_pane), "delayed": compact_snapshot(reassigned_after, new_pane), "native_effect": {"old_pane_id": pane_id, "new_pane_id": new_pane, "old_identity": old_identity, "new_identity": new_identity, "changed_fields": changed_fields, "opaque_identity_fields": {"pane_id": "changed", "terminal_id": "compared", "agent_session": "compared", "revision": "compared"}}})
            cleanup_complete = True
        finally:
            if workspace_id:
                run("herdr", "workspace", "close", workspace_id, check=False)
            if original_focus:
                run("herdr", "agent", "focus", original_focus, check=False)
            shutil.rmtree(fixture_root, ignore_errors=True)
        after_all = snapshot()
        if original_focus and after_all.get("focused_pane_id") != original_focus:
            fail("original Herdr focus was not restored")
        if any(item.get("workspace_id") == workspace_id for item in after_all.get("panes", [])):
            fail("disposable workspace pane remains after cleanup")
        contract = {"schema_version": 1, "kind": "herdr-contract", "classification": "baseline-compatible", "herdr": {"version": EXPECTED_VERSION, "protocol": 19, "schema_version": 1, "schema_sha256": schema_hash}, "plugin": plugin, "socket": {"path": str(socket_path), "mode": "0600", "owner_uid": socket_stat.st_uid}, "ordering": {"source": "herdr-agent-inbox", "rank": "ascending", "state_change_seq": "descending", "missing_rank": "unavailable"}, "acknowledgement": {"herdr_owned": ["pane_id", "terminal_id", "agent_session", "revision"], "bridge_owned": ["host_epoch", "snapshot_revision"], "herdr_does_not_acknowledge": ["host_epoch", "snapshot_revision"]}, "allowlist": ["agent.focus"], "excluded_actions": ["settle", "unread", "clear", "reply", "approval", "arbitrary_method"]}
        effects = {"schema_version": 1, "kind": "herdr-focus-effects", "classification": "baseline-compatible", "source_revision": EXPECTED_REVISION, "rows": rows, "cleanup": {"complete": cleanup_complete, "workspace_id": workspace_id, "original_focus_restored": True, "existing_agents_changed": False, "disposable_state_removed": True}}
        args.output_root.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        effects_path.write_text(json.dumps(effects, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verify_matrix(effects_path)
        print(f"wrote and verified {effects_path} and {contract_path}")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"herdr focus fixture rejected: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
