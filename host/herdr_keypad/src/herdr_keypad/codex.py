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
FULL_POLL_SECONDS = 300.0
STALE_AFTER_SECONDS = 900.0


CODEX_STATES = {"current", "stale", "unavailable", "auth_required", "codex_offline", "host_offline"}
INTERNAL_REASONS = {"", "bucket_unavailable"}
ERROR_CODES = {"", *(f"E-{number:04d}" for number in range(2400, 2410))}


@dataclass(frozen=True)
class ChildExit:
    state: str
    code: int | None = None
    signal: int | None = None

    def __post_init__(self) -> None:
        if self.state not in {"not_started", "running", "exited", "terminated", "killed"}:
            raise ValueError("invalid child exit state")
        if self.code is not None and (not isinstance(self.code, int) or isinstance(self.code, bool) or self.code < 0):
            raise ValueError("child exit code must be a non-negative integer or null")
        if self.signal is not None and (not isinstance(self.signal, int) or isinstance(self.signal, bool) or self.signal <= 0):
            raise ValueError("child exit signal must be a positive integer or null")
        if self.code is not None and self.signal is not None:
            raise ValueError("child exit cannot contain both code and signal")
        if self.state in {"not_started", "running"} and (self.code is not None or self.signal is not None):
            raise ValueError("unfinished child exit cannot contain code or signal")
        if self.state == "exited" and self.signal is not None:
            raise ValueError("exited child cannot contain a signal")

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "code": self.code, "signal": self.signal}


_MISSING = object()


@dataclass(frozen=True)
class _CacheSnapshot:
    primary: int | None = None
    secondary: int | None = None
    primary_reset: int | None = None
    secondary_reset: int | None = None
    reached_limit: bool | None = None
    plan_type: str | None = None
    spend_control_reached: bool | None = None

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
    internal_reason: str = ""

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
        if self.internal_reason not in INTERNAL_REASONS:
            raise ValueError("invalid internal reason")
        if self.error_code not in ERROR_CODES:
            raise ValueError("error code is not allowlisted")

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
    if rate_limits_by_id is _MISSING:
        return BucketManifest()
    if rate_limits_by_id is None or not isinstance(rate_limits_by_id, Mapping):
        return BucketManifest(present=True)
    keys = [str(key) for key in rate_limits_by_id]
    prefixes = tuple(sorted({
        hashlib.sha256(key.encode("utf-8")).hexdigest()[:MAX_KEY_PREFIX]
        for key in keys
    })[:MAX_BUCKET_KEYS])
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
        raise ValueError("window is ambiguous")
    value = window.get("usedPercent")
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
        raise ValueError("window percentage is invalid")
    return value


def _cache_from_full(rate_limits: Mapping[str, Any]) -> _CacheSnapshot:
    primary = _window(rate_limits.get("primary"))
    secondary = _window(rate_limits.get("secondary"))
    resets: list[int | None] = []
    for name in ("primary", "secondary"):
        window = rate_limits.get(name)
        reset = window.get("resetsAt") if isinstance(window, Mapping) else None
        if reset is not None and (not isinstance(reset, int) or isinstance(reset, bool)):
            raise ValueError("window reset is invalid")
        resets.append(reset)
    reached = rate_limits.get("rateLimitReachedType")
    if reached is not None and not isinstance(reached, str):
        raise ValueError("reached state is invalid")
    spend = rate_limits.get("spendControlReached")
    if spend is not None and not isinstance(spend, bool):
        raise ValueError("spend state is invalid")
    plan = rate_limits.get("planType")
    if plan is not None and not isinstance(plan, str):
        raise ValueError("plan type is invalid")
    return _CacheSnapshot(
        primary=primary,
        secondary=secondary,
        primary_reset=resets[0],
        secondary_reset=resets[1],
        reached_limit=True if reached else (False if reached is not None else None),
        plan_type=plan,
        spend_control_reached=spend,
    )


def _reset_text_from_cache(cache: _CacheSnapshot) -> str:
    candidates: list[tuple[int, str]] = []
    now = int(time.time())
    for reset, label in ((cache.primary_reset, "5H"), (cache.secondary_reset, "WEEK")):
        if isinstance(reset, int) and reset > now:
            candidates.append((reset, f"RESET {label} {max(1, (reset - now) // 60)}M"))
    return min(candidates)[1] if candidates else "RESET N/A"


def normalize_rate_limits(response: Mapping[str, Any]) -> tuple[CodexView, Redaction]:
    """Normalize one complete response, selecting only top-level rateLimits."""
    manifest = _manifest(response["rateLimitsByLimitId"] if "rateLimitsByLimitId" in response else _MISSING)
    rate_limits = response.get("rateLimits")
    if not isinstance(rate_limits, Mapping):
        return CodexView(error_code="E-2401", internal_reason="bucket_unavailable"), Redaction(bucket_manifest=manifest)
    try:
        cache = _cache_from_full(rate_limits)
    except ValueError:
        return CodexView(error_code="E-2401", internal_reason="bucket_unavailable"), Redaction(bucket_manifest=manifest)
    if cache.primary is None and cache.secondary is None:
        return CodexView(error_code="E-2401", internal_reason="bucket_unavailable"), Redaction(bucket_manifest=manifest)
    return CodexView(
        source_state="current",
        primary=cache.primary,
        secondary=cache.secondary,
        reset_text=_reset_text_from_cache(cache),
        reached_limit=cache.reached_limit,
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

    POLL_INTERVAL_SECONDS = FULL_POLL_SECONDS
    STALE_AFTER_SECONDS = STALE_AFTER_SECONDS

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
        self._cache: _CacheSnapshot | None = None
        self._baseline_known = False
        self._last_full_observed_at: float | None = None
        self._last_observed_at: float | None = None
        self._next_full_at: float | None = None
        self._refetch_pending = False
        self._state = "unavailable"
        self._error_code = ""
        self._internal_reason = ""

    @property
    def last_full_observed_at(self) -> float | None:
        return self._last_full_observed_at

    @property
    def last_observed_at(self) -> float | None:
        return self._last_observed_at

    @property
    def refetch_pending(self) -> bool:
        return self._refetch_pending

    def _observation_age(self) -> str:
        if self._last_observed_at is None:
            return "AGE N/A"
        return f"AGE {max(0, int((self.clock() - self._last_observed_at) // 60))}M"

    def view(self) -> CodexView:
        cache = self._cache or _CacheSnapshot()
        state = self._state
        if not self._baseline_known and state not in {"auth_required", "codex_offline", "host_offline"}:
            state = "unavailable"
        elif state == "current" and self._last_observed_at is not None and (
            self.clock() - self._last_observed_at >= self.STALE_AFTER_SECONDS
        ):
            state = "stale"
        return CodexView(
            source_state=state,
            primary=cache.primary,
            secondary=cache.secondary,
            reset_text=_reset_text_from_cache(cache),
            observation_age=self._observation_age(),
            reached_limit=cache.reached_limit,
            error_code=self._error_code,
            internal_reason=self._internal_reason,
        )

    def should_poll(self, now: float | None = None) -> bool:
        now = self.clock() if now is None else now
        return self._refetch_pending or self._next_full_at is None or now >= self._next_full_at

    def consume_refetch(self) -> bool:
        pending = self._refetch_pending
        self._refetch_pending = False
        return pending

    def _schedule_refetch(self) -> None:
        self._refetch_pending = True

    def apply_full_response(self, response: Mapping[str, Any]) -> CodexView:
        if not isinstance(response, Mapping):
            self._state = "unavailable"
            self._error_code = "E-2401"
            self._internal_reason = "bucket_unavailable"
            return self.view()
        rate_limits = response.get("rateLimits")
        if not isinstance(rate_limits, Mapping):
            self._state = "unavailable"
            self._error_code = "E-2401"
            self._internal_reason = "bucket_unavailable"
            if not self._baseline_known:
                self._cache = None
            return self.view()
        try:
            cache = _cache_from_full(rate_limits)
        except ValueError:
            self._state = "unavailable"
            self._error_code = "E-2401"
            self._internal_reason = "bucket_unavailable"
            return self.view()
        now = self.clock()
        self._cache = cache
        self._baseline_known = True
        self._last_full_observed_at = now
        self._last_observed_at = now
        self._next_full_at = now + self.POLL_INTERVAL_SECONDS
        self._refetch_pending = False
        self._error_code = "" if cache.primary is not None or cache.secondary is not None else "E-2401"
        self._internal_reason = "" if not self._error_code else "bucket_unavailable"
        self._state = "current" if not self._error_code else "unavailable"
        return self.view()

    def apply_sparse_update(self, update: Mapping[str, Any]) -> bool:
        if isinstance(update, Mapping) and update.get("method") == "account/rateLimits/updated":
            params = update.get("params")
            if not isinstance(params, Mapping):
                return False
            update = params
        if not self._baseline_known or not isinstance(update, Mapping):
            self._schedule_refetch()
            return False
        rate_limits = update.get("rateLimits")
        if not isinstance(rate_limits, Mapping):
            return False
        current = self._cache or _CacheSnapshot()
        values = {
            "primary": current.primary,
            "secondary": current.secondary,
            "primary_reset": current.primary_reset,
            "secondary_reset": current.secondary_reset,
            "reached_limit": current.reached_limit,
            "plan_type": current.plan_type,
            "spend_control_reached": current.spend_control_reached,
        }
        seen = False
        try:
            for name, reset_name in (("primary", "primary_reset"), ("secondary", "secondary_reset")):
                if name not in rate_limits:
                    continue
                seen = True
                window = rate_limits[name]
                if window is None:
                    values[name] = None
                    values[reset_name] = None
                elif isinstance(window, Mapping):
                    unknown = set(window) - {"usedPercent", "resetsAt"}
                    if unknown or not ({"usedPercent", "resetsAt"} & set(window)):
                        raise ValueError("unknown sparse window field")
                    if "usedPercent" in window:
                        values[name] = _window(window)
                    if "resetsAt" in window:
                        reset = window["resetsAt"]
                        if reset is not None and (not isinstance(reset, int) or isinstance(reset, bool)):
                            raise ValueError("invalid sparse reset")
                        values[reset_name] = reset
                else:
                    raise ValueError("invalid sparse window")
            if "rateLimitReachedType" in rate_limits:
                seen = True
                reached = rate_limits["rateLimitReachedType"]
                if reached is not None and not isinstance(reached, str):
                    raise ValueError("invalid sparse reached state")
                if reached is not None:
                    values["reached_limit"] = bool(reached)
            if "planType" in rate_limits:
                seen = True
                plan = rate_limits["planType"]
                if plan is not None and not isinstance(plan, str):
                    raise ValueError("invalid sparse plan type")
                if plan is not None:
                    values["plan_type"] = plan
            if "spendControlReached" in rate_limits:
                seen = True
                spend = rate_limits["spendControlReached"]
                if spend is not None and not isinstance(spend, bool):
                    raise ValueError("invalid sparse spend state")
                if spend is not None:
                    values["spend_control_reached"] = spend
            if not seen:
                return False
        except (TypeError, ValueError):
            return False
        self._cache = _CacheSnapshot(**values)
        self._last_observed_at = self.clock()
        self._state = "current"
        self._error_code = "" if self._cache.primary is not None or self._cache.secondary is not None else "E-2401"
        self._internal_reason = "" if not self._error_code else "bucket_unavailable"
        self._schedule_refetch()
        return True

    def account_changed(self, *, auth_required: bool = False, account: Any = None) -> CodexView:
        del account
        self._cache = None
        self._baseline_known = False
        self._last_full_observed_at = None
        self._last_observed_at = None
        self._next_full_at = None
        self._refetch_pending = True
        self._state = "auth_required" if auth_required else "unavailable"
        self._error_code = ""
        self._internal_reason = ""
        return self.view()

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
        view = self.view()
        failure: _CollectorFailure | None = None
        try:
            executable = shutil.which(self.executable) or self.executable
            self.process = self.process_factory(
                [executable, "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
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
            self.apply_full_response(response)
            view = self.view()
        except FileNotFoundError:
            failure = _CollectorFailure("codex_offline", "E-2400")
        except _CollectorFailure as exc:
            failure = exc
        except (OSError, subprocess.SubprocessError, BrokenPipeError, TimeoutError):
            failure = _CollectorFailure("codex_offline", "E-2409")
        finally:
            child_exit = self._stop()
        if failure is not None:
            if failure.state == "auth_required":
                self.account_changed(auth_required=True)
                redaction = Redaction(bucket_manifest=redaction.bucket_manifest)
            else:
                self._state = failure.state
                self._error_code = failure.code if failure.code in ERROR_CODES else ""
                self._internal_reason = ""
            view = self.view()
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
