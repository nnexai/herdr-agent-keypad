"""Bounded Codex app-server collector and truthful normalized capacity view.

The collector is the only code that sees app-server JSONL.  It never forwards
upstream objects, account identities, paths, credentials, or raw error text.
"""
from __future__ import annotations

import hashlib
import json
import os
import select
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

MAX_LINE_BYTES = 4096
MAX_BUCKET_KEYS = 8
MAX_KEY_PREFIX = 12
MAX_ERROR_CODE = 16
DEFAULT_DEADLINE_MS = 15_000

CODEX_STATES = {"current", "stale", "unavailable", "auth_required", "codex_offline", "host_offline"}


@dataclass(frozen=True)
class ChildExit:
    state: str
    code: int | None = None
    signal: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "code": self.code, "signal": self.signal}


@dataclass(frozen=True)
class BucketManifest:
    present: bool = False
    observed_key_count: int = 0
    key_prefixes: tuple[str, ...] = ()
    truncated: bool = False
    selected_key: None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "observed_key_count": self.observed_key_count,
            "key_prefixes": list(self.key_prefixes),
            "truncated": self.truncated,
            "selected_key": self.selected_key,
        }


@dataclass(frozen=True)
class Redaction:
    result: str = "pass"
    rejected_field_count: int = 0
    bucket_manifest: BucketManifest = field(default_factory=BucketManifest)

    def as_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "rejected_field_count": self.rejected_field_count,
            "bucket_manifest": self.bucket_manifest.as_dict(),
        }


@dataclass(frozen=True)
class CodexView:
    source_state: str = "unavailable"
    primary: int | None = None
    secondary: int | None = None
    reset_text: str = "RESET N/A"
    observation_age: str = "AGE N/A"
    reached_limit: bool | None = None
    error_code: str = ""

    def __post_init__(self) -> None:
        if self.source_state not in CODEX_STATES:
            raise ValueError("invalid Codex source state")
        for value in (self.primary, self.secondary):
            if (value is not None and not isinstance(value, int)) or isinstance(value, bool):
                raise ValueError("capacity must be null or integer")
            if value is not None and not 0 <= value <= 100:
                raise ValueError("capacity percentage is out of bounds")
        if self.reached_limit is not None and not isinstance(self.reached_limit, bool):
            raise ValueError("reached_limit must be null or boolean")

    def as_payload(self) -> dict[str, Any]:
        return {
            "source_state": self.source_state,
            "primary": self.primary,
            "secondary": self.secondary,
            "reset_text": self.reset_text[:32],
            "observation_age": self.observation_age[:16],
            "reached_limit": self.reached_limit,
            "error_code": self.error_code[:MAX_ERROR_CODE],
        }


@dataclass(frozen=True)
class CodexResult:
    view: CodexView
    handshake: tuple[str, ...]
    deadline_ms: int
    elapsed_ms: int
    child_exit: ChildExit
    redaction: Redaction
    account_observed: bool = False
    rate_limits_observed: bool = False

    def as_evidence(self) -> dict[str, Any]:
        return {
            "deadline_ms": self.deadline_ms,
            "elapsed_ms": self.elapsed_ms,
            "child_exit": self.child_exit.as_dict(),
            "handshake": list(self.handshake),
            "account_observed": self.account_observed,
            "rate_limits_observed": self.rate_limits_observed,
            "redaction": self.redaction.as_dict(),
        }


def _manifest(rate_limits_by_id: Any) -> BucketManifest:
    if rate_limits_by_id is None:
        return BucketManifest()
    if not isinstance(rate_limits_by_id, dict):
        return BucketManifest(present=True)
    keys = sorted(str(key) for key in rate_limits_by_id)
    prefixes = tuple(sorted(hashlib.sha256(key.encode("utf-8")).hexdigest()[:MAX_KEY_PREFIX] for key in keys[:MAX_BUCKET_KEYS]))
    return BucketManifest(
        present=True,
        observed_key_count=min(len(keys), 0xFFFF),
        key_prefixes=prefixes,
        truncated=len(keys) > MAX_BUCKET_KEYS,
    )


def _window(window: Any) -> int | None:
    if window is None:
        return None
    if not isinstance(window, Mapping) or "usedPercent" not in window:
        return None
    value = window.get("usedPercent")
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100 else None


def _reset_text(rate_limits: Mapping[str, Any]) -> str:
    candidates: list[tuple[int, str]] = []
    labels = (("primary", "5H"), ("secondary", "WEEK"))
    now = int(time.time())
    for key, label in labels:
        window = rate_limits.get(key)
        if isinstance(window, Mapping):
            reset = window.get("resetsAt")
            if isinstance(reset, int) and not isinstance(reset, bool) and reset > now:
                remaining = max(1, (reset - now) // 60)
                candidates.append((reset, f"RESET {label} {remaining}M"))
    return min(candidates)[1] if candidates else "RESET N/A"


def normalize_rate_limits(response: Mapping[str, Any]) -> tuple[CodexView, Redaction]:
    """Normalize one complete response, selecting only top-level rateLimits."""
    manifest = _manifest(response.get("rateLimitsByLimitId"))
    rate_limits = response.get("rateLimits")
    if not isinstance(rate_limits, Mapping):
        return CodexView(error_code="E-2401"), Redaction(bucket_manifest=manifest)
    primary = _window(rate_limits.get("primary"))
    secondary = _window(rate_limits.get("secondary"))
    if any(window is not None and _window(window) is None for window in (rate_limits.get("primary"), rate_limits.get("secondary"))):
        return CodexView(error_code="E-2401"), Redaction(bucket_manifest=manifest)
    reached = rate_limits.get("rateLimitReachedType")
    if reached is not None and not isinstance(reached, str):
        reached = None
    return CodexView(
        source_state="current" if primary is not None or secondary is not None else "unavailable",
        primary=primary,
        secondary=secondary,
        reset_text=_reset_text(rate_limits),
        reached_limit=True if reached else (False if reached is not None else None),
    ), Redaction(bucket_manifest=manifest)


class _CollectorFailure(RuntimeError):
    def __init__(self, state: str, code: str = "") -> None:
        self.state = state
        self.code = code
        super().__init__(state)


def _auth_evidence(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if value.get("account") is None and value.get("requiresOpenaiAuth") is True:
        return True
    error = value.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")
        return isinstance(code, str) and code.lower() in {"unauthorized", "not_authenticated", "auth_required", "401"}
    return False


class CodexCollector:
    """Supervise exactly one installed ``codex app-server --stdio`` child."""

    def __init__(self, *, executable: str = "codex", deadline_ms: int = DEFAULT_DEADLINE_MS,
                 clock: Callable[[], float] | None = None,
                 process_factory: Callable[..., Any] | None = None) -> None:
        if not 1 <= deadline_ms <= 120_000:
            raise ValueError("deadline_ms is out of bounds")
        self.executable = executable
        self.deadline_ms = deadline_ms
        self.clock = clock or time.monotonic
        self.process_factory = process_factory or subprocess.Popen
        self.process: Any | None = None
        self.last_result: CodexResult | None = None

    def _readline(self, deadline: float) -> bytes:
        assert self.process is not None
        stream = self.process.stdout
        if stream is None:
            raise _CollectorFailure("codex_offline")
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise _CollectorFailure("codex_offline", "E-2402")
        try:
            fileno = stream.fileno()
        except (AttributeError, OSError):
            fileno = None
        if fileno is not None:
            ready, _, _ = select.select([fileno], [], [], remaining)
            if not ready:
                raise _CollectorFailure("codex_offline", "E-2402")
        line = stream.readline()
        if not line:
            raise _CollectorFailure("codex_offline", "E-2403")
        if len(line) > MAX_LINE_BYTES:
            raise _CollectorFailure("codex_offline", "E-2404")
        return line

    def _message(self, request_id: int, deadline: float) -> Mapping[str, Any]:
        assert self.process is not None and self.process.stdin is not None
        while True:
            try:
                line = self._readline(deadline)
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise _CollectorFailure("codex_offline", "E-2405") from exc
            if not isinstance(value, Mapping):
                raise _CollectorFailure("codex_offline", "E-2405")
            if value.get("id") == request_id:
                if "error" in value:
                    if _auth_evidence(value):
                        raise _CollectorFailure("auth_required")
                    raise _CollectorFailure("codex_offline", "E-2406")
                result = value.get("result")
                if not isinstance(result, Mapping):
                    raise _CollectorFailure("codex_offline", "E-2407")
                return result

    def _send(self, value: Mapping[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        encoded = (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > MAX_LINE_BYTES:
            raise _CollectorFailure("codex_offline", "E-2408")
        self.process.stdin.write(encoded)
        self.process.stdin.flush()

    def _stop(self) -> ChildExit:
        process = self.process
        if process is None:
            return ChildExit("not_started")
        code = process.poll()
        if code is None:
            try:
                process.terminate()
                process.wait(timeout=1)
                code = process.returncode
                state = "terminated"
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=1)
                    code = process.returncode
                    state = "killed"
                except Exception:
                    state = "killed"
                    code = None
        else:
            state = "exited"
        if code is not None and code < 0:
            return ChildExit(state, None, -code)
        return ChildExit(state, code, None)

    def collect(self) -> CodexResult:
        started = self.clock()
        deadline = started + self.deadline_ms / 1000
        stages: list[str] = []
        redaction = Redaction()
        account_observed = False
        rate_limits_observed = False
        view = CodexView()
        failure: _CollectorFailure | None = None
        try:
            executable = shutil.which(self.executable) or self.executable
            self.process = self.process_factory([executable, "app-server", "--stdio"], stdin=subprocess.PIPE,
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self._send({"id": 1, "method": "initialize", "params": {}})
            self._message(1, deadline)
            stages.append("initialize")
            self._send({"method": "initialized", "params": {}})
            stages.append("initialized")
            self._send({"id": 2, "method": "account/read", "params": {"refreshToken": False}})
            account = self._message(2, deadline)
            account_observed = True
            stages.append("account/read")
            if _auth_evidence(account):
                raise _CollectorFailure("auth_required")
            self._send({"id": 3, "method": "account/rateLimits/read", "params": None})
            response = self._message(3, deadline)
            stages.append("account/rateLimits/read")
            rate_limits_observed = True
            view, redaction = normalize_rate_limits(response)
        except FileNotFoundError:
            failure = _CollectorFailure("codex_offline", "E-2400")
        except _CollectorFailure as exc:
            failure = exc
        except (OSError, subprocess.SubprocessError, BrokenPipeError, TimeoutError):
            failure = _CollectorFailure("codex_offline", "E-2409")
        finally:
            child_exit = self._stop()
        if failure is not None:
            view = CodexView(source_state=failure.state, error_code=failure.code)
            if failure.state == "auth_required":
                redaction = Redaction(bucket_manifest=redaction.bucket_manifest)
        elapsed_ms = min(self.deadline_ms, max(0, int((self.clock() - started) * 1000)))
        result = CodexResult(view, tuple(stages), self.deadline_ms, elapsed_ms, child_exit, redaction,
                             account_observed, rate_limits_observed)
        self.last_result = result
        return result


def redaction_passes(value: Any) -> bool:
    """Reject evidence-shaped values recursively without exposing their text."""
    forbidden = {"token", "secret", "password", "email", "codexhome", "path", "prompt", "transcript", "stderr", "stdout"}
    if isinstance(value, Mapping):
        for key, item in value.items():
            if any(word in str(key).lower() for word in forbidden):
                return False
            if not redaction_passes(item):
                return False
    elif isinstance(value, (list, tuple)):
        return all(redaction_passes(item) for item in value)
    return True
