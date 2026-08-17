"""Small public Herdr 0.8 socket adapter.

The adapter owns transport framing only.  Projection and focus policy stay in
separate modules so the installed inbox remains the authority for ordering and
``agent.focus`` remains the only write capability.
"""
from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


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

    def subscribe(self, *, subscriptions: Sequence[Mapping[str, Any]]) -> Any:
        if isinstance(subscriptions, (str, bytes)) or not subscriptions:
            raise HerdrError("events.subscribe requires explicit typed subscriptions")
        typed = []
        for subscription in subscriptions:
            if not isinstance(subscription, Mapping):
                raise HerdrError("events.subscribe subscription is invalid")
            item = dict(subscription)
            event_type = item.get("type")
            if (
                not isinstance(event_type, str)
                or not event_type
                or event_type == "*"
                or any(ord(char) < 0x21 or char in "\r\n" for char in event_type)
            ):
                raise HerdrError("events.subscribe event type is invalid")
            typed.append(item)
        return self.request("events.subscribe", {"subscriptions": typed})

    def focus(self, pane_id: str) -> Any:
        return self.request("agent.focus", {"target": pane_id})

class HerdrEventStream:
    """Persistent bounded subscription stream used only for invalidation.

    The stream admits ``push`` after the same socket returns the correlated
    JSON-RPC subscribe response. Typed ``{event,data}`` envelopes are consumed
    later without inventing a polling projection source.
    """

    MAX_LINE_BYTES = 65_536
    DEFAULT_EVENTS = (
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

    def __init__(
        self,
        client: HerdrClient,
        subscriptions: Sequence[Mapping[str, Any]] | None = None,
        *,
        socket_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.subscriptions = tuple(subscriptions or ({"type": item} for item in self.DEFAULT_EVENTS))
        self.socket_factory = socket_factory
        self.clock = clock
        self.sock: Any | None = None
        self.mode = "unclassified"
        self.typed_event: Mapping[str, Any] | None = None
        self.reason = ""
        self._next_id = 1
        self._request_id: str | int | None = None
        self._deadline = 0.0

    @property
    def active(self) -> bool:
        return self.sock is not None and self.mode == "push"

    def _open(self) -> Any:
        if self.socket_factory is not None:
            return self.socket_factory()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(max(0.05, self.client.timeout))
        sock.connect(self.client.socket_path)
        return sock

    def _close_socket(self) -> None:
        sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def close(self) -> None:
        self._close_socket()
        self.mode = "closed"
        self.typed_event = None
        self._request_id = None

    def reset(self) -> None:
        self.close()
        self.mode = "unclassified"
        self.reason = ""

    def _send_subscribe(self) -> None:
        self._request_id = str(self._next_id)
        self._next_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "events.subscribe",
            "params": {"subscriptions": [dict(item) for item in self.subscriptions]},
        }
        payload = (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
        self.sock.sendall(payload)

    def _readline(self, *, deadline: float) -> bytes | None:
        if self.sock is None:
            return None
        while self.clock() < deadline:
            try:
                remaining = min(0.05, max(0.001, deadline - self.clock()))
                settimeout = getattr(self.sock, "settimeout", None)
                if callable(settimeout):
                    settimeout(remaining)
                chunk = self.sock.recv(4096)
            except (BlockingIOError, TimeoutError, socket.timeout):
                continue
            except OSError as exc:
                raise HerdrError(f"event socket unavailable: {exc}") from exc
            if not chunk:
                return None
            if not hasattr(self, "_buffer"):
                self._buffer = bytearray()
            self._buffer.extend(chunk)
            if len(self._buffer) > self.MAX_LINE_BYTES:
                raise HerdrError("event response exceeds bounded line limit")
            if b"\n" in self._buffer:
                line, remainder = bytes(self._buffer).split(b"\n", 1)
                self._buffer = bytearray(remainder)
                return line
        return None

    @staticmethod
    def _typed_event(value: Any) -> Mapping[str, Any] | None:
        if not isinstance(value, Mapping):
            return None
        event = value.get("event")
        data = value.get("data")
        if not isinstance(event, str) or not event or not isinstance(data, Mapping):
            return None
        if any(ord(char) < 0x21 or char in "\r\n" for char in event):
            return None
        return value

    def probe(self, *, deadline_seconds: float = 5.0) -> str:
        """Classify the installed socket as ``push`` or bounded ``poll``."""
        if deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        self.reset()
        deadline = self.clock() + deadline_seconds
        self._deadline = deadline
        try:
            self.sock = self._open()
            self._send_subscribe()
            line = self._readline(deadline=deadline)
            if line is None:
                self.reason = "timeout_or_eof_before_subscribe_ack"
                self.mode = "poll"
                self._close_socket()
                return self.mode
            try:
                response = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.reason = "malformed_subscribe_ack"
                self.mode = "poll"
                self._close_socket()
                return self.mode
            if (
                not isinstance(response, Mapping)
                or response.get("id") != self._request_id
                or "result" not in response
            ):
                self.reason = "uncorrelated_subscribe_ack"
                self.mode = "poll"
                self._close_socket()
                return self.mode
            self.mode = "push"
            self.reason = "subscribe_ack"
            return self.mode
        except (OSError, HerdrError, TimeoutError) as exc:
            self.reason = type(exc).__name__.lower()
            self.mode = "poll"
            self._close_socket()
            return self.mode

    def poll(self) -> Mapping[str, Any] | None:
        """Return one typed invalidation without blocking beyond the deadline."""
        if self.typed_event is not None:
            event, self.typed_event = self.typed_event, None
            return event
        if not self.active:
            return None
        try:
            line = self._readline(deadline=min(self._deadline, self.clock() + 0.001))
        except HerdrError:
            self._close_socket()
            self.mode = "poll"
            self.reason = "stream_read_failure"
            return None
        if line is None:
            self._close_socket()
            self.mode = "poll"
            self.reason = "stream_eof"
            return None
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._close_socket()
            self.mode = "poll"
            self.reason = "malformed_event"
            return None
        return self._typed_event(event)


def _contract_record(stream: HerdrEventStream, *, deadline_seconds: float) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": stream.mode,
        "reason": stream.reason,
        "deadline_seconds": deadline_seconds,
        "observed": {
            "subscribe_ack": stream.reason == "subscribe_ack",
            "typed_event": stream.typed_event is not None,
        },
        "recovery": {
            "max_reestablish_attempts": 3,
            "max_attempts_per_tick": 1,
            "poll_interval_seconds": 1.0,
        },
    }


def probe_event_contract(argv: list[str] | None = None) -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline-seconds", type=float, default=5.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if not 0 < args.deadline_seconds <= 5:
        parser.error("--deadline-seconds must be in (0, 5]")
    client = HerdrClient(timeout=args.deadline_seconds)
    stream = HerdrEventStream(client)
    stream.probe(deadline_seconds=args.deadline_seconds)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(_contract_record(stream, deadline_seconds=args.deadline_seconds), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(json.dumps(_contract_record(stream, deadline_seconds=args.deadline_seconds), sort_keys=True))
    return 0


def verify_event_contract(argv: list[str] | None = None) -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args(argv)
    data = json.loads(Path(args.path).read_text(encoding="utf-8"))
    if data.get("mode") == "push":
        if data.get("reason") != "subscribe_ack":
            raise SystemExit("push requires correlated subscribe ACK")
    elif data.get("mode") != "poll":
        raise SystemExit("contract mode must be push or poll")
    if data.get("recovery", {}).get("max_reestablish_attempts") != 3:
        raise SystemExit("recovery bounds missing")
    print("event contract valid")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "probe-event-contract":
        raise SystemExit(probe_event_contract(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "verify-event-contract":
        raise SystemExit(verify_event_contract(sys.argv[2:]))
