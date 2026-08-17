"""Small public Herdr 0.8 socket adapter.

The adapter owns transport framing only.  Projection and focus policy stay in
separate modules so the installed inbox remains the authority for ordering and
``agent.focus`` remains the only write capability.
"""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Callable, Mapping


class HerdrError(RuntimeError):
    """A public Herdr request failed or returned an unusable response."""


@dataclass(frozen=True)
class HerdrResponse:
    request_id: int
    result: Any


class HerdrClient:
    """Bounded NDJSON client for the installed Herdr public Unix socket.

    Tests can inject ``requester``; production uses one request per connection,
    which avoids carrying stale response state across reconnects.
    """

    def __init__(self, socket_path: str = "/home/nnex/.config/herdr/herdr.sock", *, timeout: float = 2.0,
                 requester: Callable[[str, Mapping[str, Any]], Any] | None = None) -> None:
        self.socket_path = socket_path
        self.timeout = timeout
        self._requester = requester
        self._next_id = 1

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        if not isinstance(method, str) or not method or any(ord(c) < 0x21 or c in "\r\n" for c in method):
            raise HerdrError("invalid method")
        body = dict(params or {})
        if self._requester is not None:
            return self._requester(method, body)
        request_id = str(self._next_id)
        self._next_id += 1
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": body}
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(self.timeout)
                conn.connect(self.socket_path)
                conn.sendall((json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8"))
                raw = bytearray()
                while len(raw) <= 65536:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if b"\n" in chunk:
                        break
        except (OSError, TimeoutError) as exc:
            raise HerdrError(f"herdr socket unavailable: {exc}") from exc
        try:
            line = bytes(raw).split(b"\n", 1)[0]
            response = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HerdrError("malformed Herdr response") from exc
        if not isinstance(response, dict) or response.get("id") != request_id:
            raise HerdrError("unrelated Herdr response")
        if "error" in response:
            error = response["error"]
            if isinstance(error, dict):
                raise HerdrError(str(error.get("code") or error.get("message") or "herdr error"))
            raise HerdrError("herdr error")
        if "result" not in response:
            raise HerdrError("missing Herdr result")
        return response["result"]

    def session_snapshot(self) -> Mapping[str, Any]:
        result = self.request("session.snapshot", {})
        if isinstance(result, Mapping) and isinstance(result.get("snapshot"), Mapping):
            result = result["snapshot"]
        if not isinstance(result, Mapping):
            raise HerdrError("session.snapshot result is not an object")
        return result

    def agent_list(self) -> list[Mapping[str, Any]]:
        result = self.request("agent.list", {})
        rows = result.get("agents") if isinstance(result, Mapping) else None
        if not isinstance(rows, list):
            raise HerdrError("agent.list result has no agents array")
        return [row for row in rows if isinstance(row, Mapping)]

    def workspace_list(self) -> list[Mapping[str, Any]]:
        result = self.request("workspace.list", {})
        rows = result.get("workspaces") if isinstance(result, Mapping) else None
        if not isinstance(rows, list):
            raise HerdrError("workspace.list result has no workspaces array")
        return [row for row in rows if isinstance(row, Mapping)]

    def subscribe(self, *, events: list[str] | None = None) -> Any:
        return self.request("events.subscribe", {"events": events or ["*"]})

    def focus(self, pane_id: str) -> Any:
        return self.request("agent.focus", {"target": pane_id})
