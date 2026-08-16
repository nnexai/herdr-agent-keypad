"""The fixed, host-owned eleven-gate physical bring-up state machine."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import EvidenceWriter
from .protocol import MachineFact, ProtocolSession
from .ui import AWAITING_COPY, TerminalUI, parse_response

GUIDED_ORDER = ("Identify", "Displays", "Keys", "Encoder", "LEDs", "Brightness", "Reboot", "Pair", "Recover", "Traffic", "Selection")


@dataclass(frozen=True)
class StimulusRow:
    step_id: str
    stimulus: str
    panel: int
    instruction: str
    expected: str
    physical_kind: str


@dataclass(frozen=True)
class Gate:
    name: str
    rows: tuple[StimulusRow, ...]
    dependent: bool = False


def _rows() -> tuple[Gate, ...]:
    return (
        Gate("Identify", (StimulusRow("IDENTIFY", "WAIT", 1, "Confirm the connected delivered keypad and visible identity facts.", "A bounded hello is acknowledged; physical identity remains unavailable until observed.", "identity"),)),
        Gate("Displays", tuple(StimulusRow(f"DISPLAY-{panel}", f"PANEL-{panel}", panel, f"Observe display {panel}: position, upright orientation, and requested color.", "The numbered panel is visible, upright from the agreed desk view, and the requested color is correct.", "display") for panel in range(1, 5))),
        Gate("Keys", tuple(StimulusRow(f"KEY-{key}", f"KEY-{key}", (key % 4) + 1, f"Press the physical key associated with the current display mapping for key {key}.", "Only the intended physical key produces the matching event.", "key") for key in range(5))),
        Gate("Encoder", (
            StimulusRow("ENCODER-CW", "ENC-CW", 1, "Turn the encoder clockwise by the prompted detent count.", "Clockwise movement is observed in the requested direction.", "encoder"),
            StimulusRow("ENCODER-CCW", "ENC-CCW", 1, "Turn the encoder counter-clockwise by the prompted detent count.", "Counter-clockwise movement is observed in the requested direction.", "encoder"),
            StimulusRow("ENCODER-CLICK", "ENC-CLICK", 1, "Click the encoder once.", "The physical encoder click is observed.", "encoder"),
        )),
        Gate("LEDs", tuple(StimulusRow(f"LED-{led}", f"LED-{led}", 1, f"Observe library LED {led} at the requested bounded color and brightness.", "The intended physical LED illuminates without assuming its position.", "led") for led in range(14))),
        Gate("Brightness", (
            StimulusRow("BRIGHTNESS-LOW", "BRIGHTNESS-LOW", 1, "Observe the low proof-brightness sample.", "Visible but lowest usable brightness is observed.", "brightness"),
            StimulusRow("BRIGHTNESS-MEDIUM", "BRIGHTNESS-MEDIUM", 1, "Observe the medium brightness sample.", "The medium requested brightness is observed.", "brightness"),
            StimulusRow("BRIGHTNESS-HIGH", "BRIGHTNESS-HIGH", 1, "Observe the high brightness sample.", "The high requested brightness is observed.", "brightness"),
        )),
        Gate("Reboot", (StimulusRow("REBOOT", "REBOOT", 1, "Reset the keypad through the bounded software reboot stimulus.", "The startup WAIT surface returns and a fresh session is established.", "reboot"),)),
        Gate("Pair", (), dependent=True),
        Gate("Recover", (), dependent=True),
        Gate("Traffic", (), dependent=True),
        Gate("Selection", (), dependent=True),
    )


GATES = _rows()
def _event_evidence(machine_details: dict[str, Any]) -> str | None:
    """Return the bounded, protocol-validated key event evidence line."""
    event = machine_details.get("event")
    if not isinstance(event, dict):
        return None
    if event.get("kind") != "key_transition":
        return None
    key_index = event.get("key")
    if not isinstance(key_index, int) or isinstance(key_index, bool) or not 0 <= key_index <= 4:
        return None
    return f"observed event: key_transition; key index: {key_index}"


class GuidedRun:
    """Bind one visible step, machine fact, and human response before recording PASS."""

    def __init__(self, session: ProtocolSession | Any | None, evidence: EvidenceWriter, ui: TerminalUI | None = None, run_id: str | None = None):
        self.session = session
        self.evidence = evidence
        self.ui = ui or TerminalUI()
        self.run_id = run_id or (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3))
        self.run_suffix = self.run_id[-6:]
        self.gate_index = 0
        self.row_index = 0
        self.started = False
        self.stable = False
        self.machine_fact: MachineFact | None = None
        self.machine_details: dict[str, Any] = {}
        self.response: str | None = None
        self.history: list[dict[str, Any]] = []

    @property
    def gate(self) -> Gate:
        return GATES[self.gate_index]

    @property
    def row(self) -> StimulusRow | None:
        return self.gate.rows[self.row_index] if self.gate.rows else None

    @property
    def step_id(self) -> str:
        return self.row.step_id if self.row else self.gate.name.upper()

    @property
    def complete_physical_gates(self) -> bool:
        return self.gate_index >= 7

    def start(self) -> None:
        self.started = True
        self.ui.start(self.run_suffix)
        self._render_not_started_or_current()

    def _render_not_started_or_current(self) -> None:
        if not self.started:
            return
        if self.row is None:
            self.ui.render_not_started(self.gate.name, self.gate_index + 1, len(GUIDED_ORDER), self.run_suffix)
            return
        evidence = []
        if self.machine_fact is not None:
            evidence.append(f"machine: {self.machine_fact.status}")
            if self.machine_fact.detail:
                evidence.append(self.machine_fact.detail)
        event_line = _event_evidence(self.machine_details)
        if event_line:
            evidence.append(event_line)
        self.ui.render_step(self.gate.name, self.step_id, self.gate_index + 1, len(GUIDED_ORDER), self.row.instruction, self.row.expected, evidence, run_suffix=self.run_suffix)

    def _record(self, action: str, physical_status: str, observed_value: Any = "unavailable") -> None:
        row = {
            "row_id": f"{self.run_id}:{len(self.history) + 1}",
            "run_id": self.run_id,
            "step_id": self.step_id,
            "gate": self.gate.name,
            "machine_status": self.machine_fact.status if self.machine_fact else "unavailable",
            "machine_reply_seq": self.machine_fact.reply_seq if self.machine_fact else None,
            "human_response": action,
            "physical_status": physical_status,
            "observed_value": observed_value if observed_value is not None else "unavailable",
            "timestamp": time.time(),
        }
        self.history.append(row)
        if hasattr(self.evidence, "record_row"):
            self.evidence.record_row(row)

    def stimulate(self) -> MachineFact:
        """Send only a fixed stimulus; ACK is retained as machine evidence, not PASS."""
        if not self.started or self.row is None:
            raise RuntimeError("no physical row is active")
        self.ui.begin_operation(self.row.stimulus)
        if self.session is None:
            raise RuntimeError("keypad session is unavailable")
        if self.step_id == "IDENTIFY":
            fact = self.session.hello()
        else:
            fact = self.session.stimulate(self.step_id, self.row.panel, self.row.stimulus)
            if self.row.physical_kind == "key" and hasattr(self.session, "wait_event"):
                event = self.session.wait_event(self.step_id)
                self.machine_details = {"event": event["payload"]}
        self.machine_fact = fact
        self.stable = fact.status == "acknowledged"
        if self.stable:
            self.ui.stable_result()
        self._render_not_started_or_current()
        return fact

    def respond(self, text: str) -> str:
        """Apply Y/N/R only to the currently visible stable step/run token."""
        if not self.started or self.row is None:
            raise RuntimeError("no confirmable physical row is active")
        parsed = parse_response(text, self.step_id, self.run_suffix)
        if parsed is None:
            raise ValueError(f"Enter alone cannot confirm; type Y {self.step_id} {self.run_suffix}, N {self.step_id} {self.run_suffix}, or R {self.step_id} {self.run_suffix}.")
        if not self.stable:
            raise RuntimeError("confirmation disabled until stable machine evidence exists")
        if parsed.action == "R":
            self._record("R", "repeated", "unavailable")
            self.response = "R"
            self.stable = False
            self.ui.add_history(f"{self.step_id}: repeat preserved")
            self.ui.confirmation_enabled = False
            return "repeat"
        if parsed.action == "N":
            self._record("N", "failed", "unavailable")
            self.response = "N"
            self.ui.render_step(self.gate.name, self.step_id, self.gate_index + 1, len(GUIDED_ORDER), self.row.instruction, self.row.expected, ["machine: acknowledged", "physical: failed"], "fail", self.run_suffix)
            return "fail"
        if self.machine_fact.status != "acknowledged":
            raise RuntimeError("physical PASS requires an acknowledged machine fact")
        self._record("Y", "pass", self.machine_details.get("event", "observed"))
        self.response = "Y"
        self._advance()
        return "pass"

    def _advance(self) -> None:
        self.ui.add_history(f"{self.step_id}: PASS")
        self.row_index += 1
        self.machine_fact = None
        self.machine_details = {}
        self.response = None
        self.stable = False
        if self.row_index >= len(self.gate.rows):
            self.gate_index += 1
            self.row_index = 0
        self._render_not_started_or_current()

    def result(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "result",
            "run_id": self.run_id,
            "status": "pass" if self.complete_physical_gates else "incomplete",
            "physical_map": {"rows": list(self.history), "guided_order": list(GUIDED_ORDER)},
            "machine_facts": {"last": self.machine_fact.status if self.machine_fact else "unavailable"},
        }


def guided_order_check() -> None:
    if tuple(gate.name for gate in GATES) != GUIDED_ORDER:
        raise AssertionError("guided gate order changed")
    if any(gate.dependent and gate.rows for gate in GATES):
        raise AssertionError("dependent gates must remain visibly not started")
    physical_ids = [row.step_id for gate in GATES[:7] for row in gate.rows]
    if len(physical_ids) != len(set(physical_ids)):
        raise AssertionError("physical step identifiers must be unique")


def confirmation_check() -> None:
    from .evidence import EvidenceWriter
    from tempfile import TemporaryDirectory

    class FakeSession:
        def hello(self):
            return MachineFact("acknowledged", time.time(), 1)

        def stimulate(self, step_id, panel, stimulus):
            return MachineFact("acknowledged", time.time(), 1)

        def wait_event(self, step_id):
            key_index = int(step_id.rsplit("-", 1)[1])
            return {"payload": {"kind": "key_transition", "step_id": step_id, "key": key_index}}

    with TemporaryDirectory() as directory:
        writer = EvidenceWriter(Path(directory), "test-run")
        run = GuidedRun(FakeSession(), writer, TerminalUI(), "test-run")
        run.start()
        run.stimulate()
        try:
            run.respond("Y")
        except ValueError:
            pass
        else:
            raise AssertionError("Enter alone must not confirm")
        if run.respond(f"Y IDENTIFY {run.run_suffix}") != "pass":
            raise AssertionError("explicit human confirmation did not pass")
        if run.history[0]["machine_status"] != "acknowledged" or run.history[0]["physical_status"] != "pass":
            raise AssertionError("machine and physical evidence were not kept distinct")
        for _ in range(4):
            run.stimulate()
            run.respond(f"Y {run.step_id} {run.run_suffix}")
        run.stimulate()
        expected_event = "observed event: key_transition; key index: 0"
        if expected_event not in run.ui.last_screen:
            raise AssertionError("key event detail was not visible before confirmation")
        if any(len(line) > 80 for line in run.ui.last_screen.splitlines()):
            raise AssertionError("key event detail exceeded the 80-column bound")
