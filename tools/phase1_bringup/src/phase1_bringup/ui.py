"""Fixed-width host UI for the one-step physical bring-up guide."""
from __future__ import annotations

import textwrap
import time
from collections import deque
from dataclasses import dataclass
from typing import Iterable

MIN_WIDTH = 80
MIN_HEIGHT = 24
NO_KEYPAD_HEADING = "No keypad detected"
NO_KEYPAD_BODY = "Connect the T-Keyboard S3 Pro with a data-capable USB cable, then retry detection."
LINK_LOST_COPY = "Keypad link lost. Reconnect the paired keypad; this run will continue only after a new session is established."
START_COPY = "Start physical bring-up"
AWAITING_COPY = "Observe the keypad, then choose: [Y] Pass  [N] Fail  [R] Repeat."
PASS_COPY = "Observation recorded as PASS."
FAIL_COPY = "Observation recorded as FAIL. Correct the issue or repeat this step before qualification."
REPEAT_COPY = "Repeating this step; the prior result remains until you confirm a replacement."


@dataclass(frozen=True)
class Response:
    action: str
    step_id: str
    run_suffix: str | None = None


def abbreviate_identity(identity: str, suffix_length: int = 4) -> str:
    """Display only a bounded suffix; full opaque identities stay in evidence."""
    if not identity:
        return "unavailable"
    suffix = identity[-suffix_length:]
    return f"Device ••••{suffix}"


def parse_response(text: str, step_id: str, run_suffix: str | None = None) -> Response | None:
    """Parse a response bound to the currently visible step and optional run suffix."""
    tokens = text.strip().upper().split()
    if len(tokens) not in {2, 3} or tokens[0] not in {"Y", "N", "R"} or tokens[1] != step_id.upper():
        return None
    if run_suffix is not None and (len(tokens) != 3 or tokens[2] != run_suffix.upper()):
        return None
    if run_suffix is None and len(tokens) == 3:
        return None
    return Response(tokens[0], step_id, tokens[2] if len(tokens) == 3 else None)


class TerminalUI:
    """An 80x24 minimum, non-ambiguous terminal surface."""

    def __init__(self, width: int = MIN_WIDTH, height: int = MIN_HEIGHT, output=None):
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            raise ValueError("terminal must be at least 80x24")
        self.width = width
        self.height = height
        self.output = output
        self.history: deque[str] = deque(maxlen=128)
        self.operation_name = "not started"
        self.operation_started: float | None = None
        self.confirmation_enabled = False
        self.last_screen = ""

    @property
    def elapsed(self) -> float:
        return 0.0 if self.operation_started is None else max(0.0, time.monotonic() - self.operation_started)

    def _wrap(self, text: str) -> list[str]:
        return textwrap.wrap(text, width=self.width, break_long_words=False, break_on_hyphens=False) or [""]

    def _emit(self, lines: Iterable[str]) -> str:
        bounded: list[str] = []
        for line in lines:
            bounded.extend(self._wrap(line))
        screen = "\n".join(line[: self.width] for line in bounded[: self.height])
        self.last_screen = screen
        if self.output is not None:
            self.output.write(screen + "\n")
            self.output.flush()
        return screen

    def show_no_keypad(self) -> str:
        return self._emit((NO_KEYPAD_HEADING, NO_KEYPAD_BODY))

    def start(self, run_suffix: str) -> str:
        self.history.clear()
        self.operation_name = "not started"
        self.operation_started = None
        self.confirmation_enabled = False
        return self._emit(("Phase 1 bring-up", START_COPY, f"run ID ••••{run_suffix}"))

    def begin_operation(self, name: str) -> None:
        self.operation_name = name
        self.operation_started = time.monotonic()
        self.confirmation_enabled = False

    def stable_result(self) -> None:
        self.confirmation_enabled = True

    def add_history(self, text: str) -> None:
        self.history.append(text)

    def render_step(
        self,
        gate_name: str,
        step_id: str,
        step_number: int,
        total_steps: int,
        instruction: str,
        expected: str,
        evidence: Iterable[str],
        status: str = "awaiting-confirmation",
        run_suffix: str = "",
        identity: str = "",
    ) -> str:
        prompt = AWAITING_COPY if self.confirmation_enabled else "Stimulating keypad; confirmation is disabled until stable machine evidence exists."
        if status == "pass":
            prompt = PASS_COPY
        elif status == "fail":
            prompt = FAIL_COPY
        elif status == "repeat":
            prompt = REPEAT_COPY
        lines = [
            "Phase 1 bring-up",
            f"{gate_name}  |  step {step_number} of {total_steps}  |  run ID ••••{run_suffix}",
            f"{self.operation_name} ({self.elapsed:.1f}s)",
            "-" * min(self.width, 80),
            f"CURRENT STEP [{step_id}] — {status.upper()}",
            instruction,
            f"Expected: {expected}",
            f"Device: {abbreviate_identity(identity) if identity else 'unavailable'}",
            "Evidence:",
        ]
        evidence_lines = list(evidence)
        if not evidence_lines:
            evidence_lines = ["unavailable"]
        lines.extend(f"  {item}" for item in evidence_lines)
        if self.history:
            lines.append("Prior evidence:")
            lines.extend(f"  {item}" for item in list(self.history)[-3:])
        lines.extend(("Response:", prompt))
        if self.confirmation_enabled:
            lines.append(f"Type Y {step_id} {run_suffix}, N {step_id} {run_suffix}, or R {step_id} {run_suffix}.")
        return self._emit(lines)

    def render_not_started(self, gate_name: str, step_number: int, total_steps: int, run_suffix: str) -> str:
        self.confirmation_enabled = False
        return self._emit((
            "Phase 1 bring-up",
            f"{gate_name}  |  step {step_number} of {total_steps}  |  run ID ••••{run_suffix}",
            "not started",
            "Evidence: unavailable",
            "Response: blocked until dependent plans establish this gate.",
        ))

    def render_link_lost(self) -> str:
        self.confirmation_enabled = False
        return self._emit(("LINK LOST", LINK_LOST_COPY, "Evidence preserved; uncertain in-flight work is discarded."))
